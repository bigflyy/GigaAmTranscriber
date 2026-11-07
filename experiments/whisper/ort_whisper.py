"""Whisper large-v3-turbo on ONNX Runtime (plan 04 A2): DirectML or CPU.

Uses the onnx-community export (encoder_model_*.onnx, decoder_model_merged_*.onnx,
vocab.json, added_tokens.json, generation_config.json in one folder, the ONNX
files under onnx/). The audio chunks come from a GigaAM reference JSON
(gigaam_ref.py), so Whisper hears exactly the pieces GigaAM heard.

    python experiments/whisper/ort_whisper.py MODEL_DIR AUDIO REF.json OUT.json
        [--variant fp16|q4f16] [--device dml|dml:1|cpu] [--language ru|auto] [--batch 8]

What it does, step by step:
1. log-mel features of every chunk (numpy, the same recipe as Whisper's
   feature extractor: 30 s window, 128 Slaney mel bands, log10, clamp to max-8);
2. encoder on a batch of chunks; its output stays on the GPU (IOBinding);
3. greedy decoding with the KV cache, the cache also kept on the GPU, with the
   prompt <|startoftranscript|><|lang|><|transcribe|><|notimestamps|>.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app.audio import SAMPLE_RATE, decode_audio  # noqa: E402

N_FFT = 400
HOP = 160
N_MELS = 128
WINDOW_SAMPLES = 30 * SAMPLE_RATE  # Whisper always sees 30 s: shorter chunks are padded with silence
MAX_TOKENS = 448                   # decoder positions, prompt included


# ---------------------------------------------------------------- features

def mel_filters(sample_rate=SAMPLE_RATE, n_fft=N_FFT, n_mels=N_MELS):
    """Slaney-style mel filter bank (librosa.filters.mel with htk=False, norm="slaney")."""
    def hz_to_mel(hz):
        hz = np.asanyarray(hz, dtype=np.float64)
        linear = hz / (200.0 / 3)
        log_part = 15.0 + np.log(np.maximum(hz, 1e-10) / 1000.0) / (np.log(6.4) / 27.0)
        return np.where(hz >= 1000.0, log_part, linear)

    def mel_to_hz(mel):
        mel = np.asanyarray(mel, dtype=np.float64)
        linear = mel * (200.0 / 3)
        log_part = 1000.0 * np.exp((np.log(6.4) / 27.0) * (mel - 15.0))
        return np.where(mel >= 15.0, log_part, linear)

    fft_freqs = np.fft.rfftfreq(n_fft, 1.0 / sample_rate)
    mel_points = mel_to_hz(np.linspace(hz_to_mel(0.0), hz_to_mel(sample_rate / 2), n_mels + 2))
    widths = np.diff(mel_points)
    ramps = mel_points[:, None] - fft_freqs[None, :]
    lower = -ramps[:-2] / widths[:-1, None]
    upper = ramps[2:] / widths[1:, None]
    weights = np.maximum(0.0, np.minimum(lower, upper))
    weights *= (2.0 / (mel_points[2:] - mel_points[:-2]))[:, None]
    return weights.astype(np.float32)


FILTERS = mel_filters()
HANN = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)  # periodic


def log_mel(audio):
    """Whisper input features for one chunk of at most 30 s: float32 [128, 3000]."""
    padded = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
    padded[:min(len(audio), WINDOW_SAMPLES)] = audio[:WINDOW_SAMPLES]
    padded = np.pad(padded, N_FFT // 2, mode="reflect")  # center=True
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP][:-1]  # 3000 frames
    power = np.abs(np.fft.rfft(frames * HANN, axis=-1)) ** 2
    mel = FILTERS @ power.T.astype(np.float32)
    log_spec = np.log10(np.maximum(mel, 1e-10))
    log_spec = np.maximum(log_spec, log_spec.max() - 8.0)
    return ((log_spec + 4.0) / 4.0).astype(np.float32)


# ---------------------------------------------------------------- tokens

def bytes_to_unicode():
    """GPT-2 byte-level BPE alphabet: byte value -> printable character."""
    keep = list(range(ord("!"), ord("~") + 1)) + list(range(ord("\xa1"), ord("\xac") + 1)) \
        + list(range(ord("\xae"), ord("\xff") + 1))
    chars = keep[:]
    extra = 0
    for byte in range(256):
        if byte not in keep:
            keep.append(byte)
            chars.append(256 + extra)
            extra += 1
    return dict(zip(keep, map(chr, chars)))


class Tokens:
    def __init__(self, folder):
        vocab = json.loads((folder / "vocab.json").read_text(encoding="utf-8"))
        self.added = json.loads((folder / "added_tokens.json").read_text(encoding="utf-8"))
        self.id_to_piece = {index: piece for piece, index in vocab.items()}
        self.byte_of = {char: byte for byte, char in bytes_to_unicode().items()}
        self.eot = self.added["<|endoftext|>"]
        self.sot = self.added["<|startoftranscript|>"]
        self.transcribe = self.added["<|transcribe|>"]
        self.no_timestamps = self.added["<|notimestamps|>"]
        self.languages = {name[2:-2]: index for name, index in self.added.items()
                          if self.sot < index < self.added["<|translate|>"]}

    def text(self, ids):
        pieces = "".join(self.id_to_piece.get(i, "") for i in ids if i < self.eot)
        return bytes(self.byte_of[c] for c in pieces).decode("utf-8", errors="replace").strip()


# ---------------------------------------------------------------- model

def open_session(path, device):
    options = ort.SessionOptions()
    options.log_severity_level = 3
    if device.startswith("dml"):
        device_id = int(device.split(":")[1]) if ":" in device else 0
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        providers = [("DmlExecutionProvider", {"device_id": device_id}), "CPUExecutionProvider"]
    else:
        providers = ["CPUExecutionProvider"]
    # ENABLE_ALL hits an ORT 1.23 fusion bug on these fp16 graphs (SimplifiedLayerNormFusion
    # on the CPU provider); fall back to fewer optimizations.
    for level in (ort.GraphOptimizationLevel.ORT_ENABLE_ALL, ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
                  ort.GraphOptimizationLevel.ORT_ENABLE_BASIC):
        options.graph_optimization_level = level
        try:
            return ort.InferenceSession(str(path), options, providers=providers), level
        except Exception as error:  # noqa: BLE001
            last_error = error
    raise last_error


class WhisperOnnx:
    def __init__(self, folder, variant="fp16", device="dml"):
        folder = Path(folder)
        started = time.perf_counter()
        self.encoder, enc_level = open_session(folder / "onnx" / f"encoder_model_{variant}.onnx", device)
        self.decoder, dec_level = open_session(folder / "onnx" / f"decoder_model_merged_{variant}.onnx", device)
        # The merged decoder's If node costs about 6 ms per chunk per step on DirectML
        # (it copies the encoder part of the cache); the plain with-past model has no If.
        with_past = folder / "onnx" / f"decoder_with_past_model_{variant}.onnx"
        self.with_past = open_session(with_past, device)[0] if with_past.exists() else None
        self.load_seconds = time.perf_counter() - started
        self.levels = (str(enc_level), str(dec_level))
        self.tokens = Tokens(folder)
        config = json.loads((folder / "generation_config.json").read_text(encoding="utf-8"))
        self.suppress = np.array(sorted(set(config["suppress_tokens"])), dtype=np.int64)
        self.begin_suppress = np.array(config["begin_suppress_tokens"], dtype=np.int64)
        self.gpu = device.startswith("dml")
        self.device_type = "dml" if self.gpu else "cpu"
        self.device_id = int(device.split(":")[1]) if ":" in device else 0
        self.layers = sum(1 for i in self.decoder.get_inputs() if i.name.endswith(".decoder.key"))
        self.providers = self.encoder.get_providers()[0], self.decoder.get_providers()[0]

    def _ortvalue(self, array):
        return ort.OrtValue.ortvalue_from_numpy(array, self.device_type, self.device_id)

    def encode(self, features):
        """features [b, 128, 3000] -> encoder output as an OrtValue on the device."""
        binding = self.encoder.io_binding()
        binding.bind_ortvalue_input("input_features", self._ortvalue(features))
        binding.bind_output("last_hidden_state", self.device_type, self.device_id)
        self.encoder.run_with_iobinding(binding)
        return binding.get_outputs()[0]

    def detect_language(self, encoded, batch):
        """Most likely language token for every chunk of the batch."""
        logits = self._step(encoded, np.full((batch, 1), self.tokens.sot, np.int64), None)[0]
        ids = np.array(list(self.tokens.languages.values()))
        names = list(self.tokens.languages.keys())
        return [names[i] for i in logits[:, -1, ids].argmax(axis=1)]

    def _step(self, encoded, input_ids, past):
        binding_session = self.with_past if (past is not None and self.with_past is not None) else self.decoder
        binding = binding_session.io_binding()
        input_names = {i.name for i in binding_session.get_inputs()}
        output_names = [o.name for o in binding_session.get_outputs()]
        binding.bind_cpu_input("input_ids", input_ids)
        if "encoder_hidden_states" in input_names:
            binding.bind_ortvalue_input("encoder_hidden_states", encoded)
        batch = input_ids.shape[0]
        names = [f"{layer}.{part}" for layer in range(self.layers)
                 for part in ("decoder.key", "decoder.value", "encoder.key", "encoder.value")]
        if past is None:
            empty = np.zeros((batch, 20, 0, 64), np.float32)
            for name in names:
                binding.bind_cpu_input(f"past_key_values.{name}", empty)
        else:
            for name in names:
                binding.bind_ortvalue_input(f"past_key_values.{name}", past[name])
        if "use_cache_branch" in input_names:
            binding.bind_cpu_input("use_cache_branch", np.array([past is not None]))
        binding.bind_output("logits", "cpu")
        for name in output_names[1:]:
            binding.bind_output(name, self.device_type, self.device_id)
        binding_session.run_with_iobinding(binding)
        outputs = binding.get_outputs()
        logits = outputs[0].numpy()
        present = {name[len("present."):]: value for name, value in zip(output_names[1:], outputs[1:])}
        if past is not None:  # the encoder part of the cache never changes: keep the first one
            for name in names:
                if ".encoder." in name:
                    present[name] = past[name]
        return logits, present

    def decode(self, encoded, languages):
        """Greedy decoding of a batch; returns (token lists, hit_max_length flags)."""
        batch = len(languages)
        prompt = np.array([[self.tokens.sot, self.tokens.languages[lang], self.tokens.transcribe,
                            self.tokens.no_timestamps] for lang in languages], dtype=np.int64)
        logits, past = self._step(encoded, prompt, None)
        results = [[] for _ in range(batch)]
        done = np.zeros(batch, dtype=bool)
        for step in range(MAX_TOKENS - prompt.shape[1]):
            last = logits[:, -1, :].copy()
            last[:, self.suppress] = -np.inf
            last[:, self.tokens.eot + 1:] = -np.inf  # no special or timestamp tokens in the text
            if step == 0:
                last[:, self.begin_suppress] = -np.inf
            chosen = last.argmax(axis=1)
            for i in range(batch):
                if not done[i]:
                    if chosen[i] == self.tokens.eot:
                        done[i] = True
                    else:
                        results[i].append(int(chosen[i]))
            if done.all():
                break
            chosen[done] = self.tokens.eot
            logits, past = self._step(encoded, chosen[:, None].astype(np.int64), past)
        return results, [not d for d in done]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir")
    parser.add_argument("audio")
    parser.add_argument("ref_json")
    parser.add_argument("out_json")
    parser.add_argument("--variant", default="fp16")
    parser.add_argument("--device", default="dml")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="only the first N chunks")
    args = parser.parse_args()

    model = WhisperOnnx(args.model_dir, args.variant, args.device)
    print(f"load {model.load_seconds:.1f} s, providers {model.providers}, opt levels {model.levels}", flush=True)
    reference = json.loads(Path(args.ref_json).read_text(encoding="utf-8"))
    chunks = reference["chunks"][:args.limit] if args.limit else reference["chunks"]

    started = time.perf_counter()
    audio = decode_audio(args.audio)
    timings = {"decode_audio": time.perf_counter() - started, "features": 0.0, "encoder": 0.0,
               "decoder": 0.0, "language": 0.0}
    out_chunks = []
    batch_size = args.batch if model.gpu else 1
    for first in range(0, len(chunks), batch_size):
        part = chunks[first:first + batch_size]
        t = time.perf_counter()
        features = np.stack([log_mel(audio[int(c["start"] * SAMPLE_RATE):int(c["end"] * SAMPLE_RATE)])
                             for c in part])
        timings["features"] += time.perf_counter() - t
        t = time.perf_counter()
        encoded = model.encode(features)
        timings["encoder"] += time.perf_counter() - t
        if args.language == "auto":
            t = time.perf_counter()
            languages = model.detect_language(encoded, len(part))
            timings["language"] += time.perf_counter() - t
        else:
            languages = [args.language] * len(part)
        t = time.perf_counter()
        token_lists, too_long = model.decode(encoded, languages)
        timings["decoder"] += time.perf_counter() - t
        for chunk, ids, long_, lang in zip(part, token_lists, too_long, languages):
            out_chunks.append({"start": chunk["start"], "end": chunk["end"], "text": model.tokens.text(ids),
                               "tokens": len(ids), "hit_max_length": long_, "language": lang})
        done = first + len(part)
        print(f"  {done}/{len(chunks)} chunks, {time.perf_counter() - started:.1f} s", flush=True)
    total = time.perf_counter() - started
    result = {"model": f"whisper-large-v3-turbo onnx {args.variant}", "device": args.device,
              "providers": model.providers, "load_seconds": round(model.load_seconds, 2),
              "transcribe_seconds": round(total, 2),
              "timings": {k: round(v, 2) for k, v in timings.items()},
              "audio_seconds": reference["audio_seconds"], "chunks": out_chunks}
    Path(args.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {total:.1f} s for {len(chunks)} chunks; {result['timings']}")


if __name__ == "__main__":
    main()
