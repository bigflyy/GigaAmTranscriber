"""Prototype: torch-free GigaAM RNNT pipeline on ONNX Runtime (CPU / CUDA / DirectML).

Only numpy + onnxruntime + an ffmpeg executable are needed at run time.
This file is a measurement prototype, not the final application code.
"""

import json
import os
import subprocess
import sys
import time

import numpy as np

T0 = time.perf_counter()
import onnxruntime as ort  # noqa: E402

IMPORT_ORT_SECONDS = time.perf_counter() - T0
SAMPLE_RATE = 16000
SILERO_ONNX = r"C:\Users\User\.conda\envs\cuda-torch2\Lib\site-packages\silero_vad\data\silero_vad.onnx"


def decode_audio(path):
    """Decode any ffmpeg-readable file once into mono 16 kHz float32 samples."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-threads", "0", "-i", path,
           "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def make_session(path, provider, threads):
    """Create an ORT session for one of: cpu, cuda, dml."""
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if provider == "cuda":
        # EXHAUSTIVE (the default) benchmarks every conv per new input shape: slow warm-up.
        providers = [("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"}), "CPUExecutionProvider"]
    elif provider == "dml":
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
    else:
        providers = ["CPUExecutionProvider"]
    return ort.InferenceSession(path, options, providers=providers)


# ---------------------------------------------------------------- Silero VAD

def silero_probs(audio, session, row_seconds=60.0, warmup_windows=64):
    """Speech probability per 512-sample window.

    The recurrent model is sequential in time, so the audio is cut into rows
    that run side by side as one batch. Each row starts warmup_windows early
    so its state has settled before the windows it reports.
    """
    window, context = 512, 64
    n_windows = (len(audio) + window - 1) // window
    padded = np.zeros(n_windows * window, dtype=np.float32)
    padded[:len(audio)] = audio
    frames = padded.reshape(n_windows, window)
    per_row = max(1, int(row_seconds * SAMPLE_RATE / window))
    starts = list(range(0, n_windows, per_row))
    rows = len(starts)
    steps = per_row + warmup_windows
    batch = np.zeros((rows, steps, window), dtype=np.float32)
    for r, s in enumerate(starts):
        begin = max(0, s - warmup_windows)
        piece = frames[begin:s + per_row]
        offset = warmup_windows - (s - begin)  # first row has no earlier audio
        batch[r, offset:offset + len(piece)] = piece
    state = np.zeros((2, rows, 128), dtype=np.float32)
    ctx = np.zeros((rows, context), dtype=np.float32)
    sr = np.array(SAMPLE_RATE, dtype=np.int64)
    out = np.zeros((rows, steps), dtype=np.float32)
    for step in range(steps):
        x = np.concatenate([ctx, batch[:, step]], axis=1)
        prob, state = session.run(None, {"input": x, "state": state, "sr": sr})
        out[:, step] = prob[:, 0]
        ctx = x[:, -context:]
    probs = out[:, warmup_windows:].reshape(-1)[:n_windows]
    return probs


def speech_regions(probs, n_samples, threshold=0.5, min_speech_ms=300, max_speech_s=25.0,
                   min_silence_ms=2000, speech_pad_ms=250, min_silence_at_max_speech=98):
    """Port of silero_vad.get_speech_timestamps post-processing (MIT, Silero Team).

    Returns (start, end) in samples. Behaviour follows silero-vad 6.2.1 with
    use_max_poss_sil_at_max_speech=True.
    """
    ws = 512
    min_speech = SAMPLE_RATE * min_speech_ms / 1000
    pad = SAMPLE_RATE * speech_pad_ms / 1000
    max_speech = SAMPLE_RATE * max_speech_s - ws - 2 * pad
    min_silence = SAMPLE_RATE * min_silence_ms / 1000
    min_sil_max = SAMPLE_RATE * min_silence_at_max_speech / 1000
    neg_threshold = max(threshold - 0.15, 0.01)
    triggered = False
    speeches, cur = [], {}
    temp_end = prev_end = next_start = 0
    possible_ends = []
    for i, p in enumerate(probs.tolist()):
        cur_sample = ws * i
        if p >= threshold and temp_end:
            sil = cur_sample - temp_end
            if sil > min_sil_max:
                possible_ends.append((temp_end, sil))
            temp_end = 0
            if next_start < prev_end:
                next_start = cur_sample
        if p >= threshold and not triggered:
            triggered = True
            cur["start"] = cur_sample
            continue
        if triggered and cur_sample - cur["start"] > max_speech:
            if possible_ends:
                prev_end, dur = max(possible_ends, key=lambda x: x[1])
                cur["end"] = prev_end
                speeches.append(cur)
                cur = {}
                next_start = prev_end + dur
                if next_start < prev_end + cur_sample:
                    cur["start"] = next_start
                else:
                    triggered = False
                prev_end = next_start = temp_end = 0
                possible_ends = []
            else:
                cur["end"] = cur_sample
                speeches.append(cur)
                cur = {}
                prev_end = next_start = temp_end = 0
                triggered = False
                possible_ends = []
                continue
        if p < neg_threshold and triggered:
            if not temp_end:
                temp_end = cur_sample
            if cur_sample - temp_end < min_silence:
                continue
            cur["end"] = temp_end
            if cur["end"] - cur["start"] > min_speech:
                speeches.append(cur)
            cur = {}
            prev_end = next_start = temp_end = 0
            triggered = False
            possible_ends = []
            continue
    if cur and n_samples - cur["start"] > min_speech:
        cur["end"] = n_samples
        speeches.append(cur)
    for i, s in enumerate(speeches):
        if i == 0:
            s["start"] = int(max(0, s["start"] - pad))
        if i != len(speeches) - 1:
            gap = speeches[i + 1]["start"] - s["end"]
            if gap < 2 * pad:
                s["end"] += int(gap // 2)
                speeches[i + 1]["start"] = int(max(0, speeches[i + 1]["start"] - gap // 2))
            else:
                s["end"] = int(min(n_samples, s["end"] + pad))
                speeches[i + 1]["start"] = int(max(0, speeches[i + 1]["start"] - pad))
        else:
            s["end"] = int(min(n_samples, s["end"] + pad))
    total = n_samples / SAMPLE_RATE
    return [(max(round(s["start"] / SAMPLE_RATE, 1), 0), min(round(s["end"] / SAMPLE_RATE, 1), total))
            for s in speeches]


def group_chunks(regions, max_duration=25.0, strict_limit=25.0, new_chunk_threshold=0.2):
    """Same grouping as the current app: merge regions up to max_duration, split overlong evenly."""
    chunks = []

    def emit(start, end):
        duration = end - start
        if duration > strict_limit:
            parts = int(duration / strict_limit) + 1
            step = duration / parts
            for k in range(parts - 1):
                chunks.append((start + k * step, start + (k + 1) * step))
            chunks.append((start + (parts - 1) * step, end))
        else:
            chunks.append((start, end))

    cur_start = cur_end = 0.0
    cur_dur = 0.0
    for index, (start, end) in enumerate(regions):
        start = max(0.0, start)
        if index == 0:
            cur_start = cur_end = start
        if cur_dur > new_chunk_threshold and cur_dur + (end - cur_end) > max_duration:
            emit(cur_start, cur_end)
            cur_start = start
        cur_end = end
        cur_dur = cur_end - cur_start
    if cur_dur > new_chunk_threshold:
        emit(cur_start, cur_end)
    return chunks


# ---------------------------------------------------------------- GigaAM RNNT

class RNNTHeadNumpy:
    """Prediction network (1-layer LSTM) and joint network in numpy, greedy decoding."""

    def __init__(self, path, max_symbols=10):
        w = np.load(path)
        self.embed = w["embed"]
        self.w_ih, self.w_hh, self.b = w["w_ih"].T.copy(), w["w_hh"].T.copy(), w["b"]
        self.enc_w, self.enc_b = w["enc_w"].T.copy(), w["enc_b"]
        self.pred_w, self.pred_b = w["pred_w"].T.copy(), w["pred_b"]
        self.out_w, self.out_b = w["out_w"].T.copy(), w["out_b"]
        self.blank = int(w["blank_id"])
        self.hidden = self.w_hh.shape[0]
        self.max_symbols = max_symbols

    def _step(self, x, h, c):
        """One LSTM step; PyTorch gate order is input, forget, cell, output."""
        z = x @ self.w_ih + h @ self.w_hh + self.b
        H = self.hidden
        i, f = 1 / (1 + np.exp(-z[:H])), 1 / (1 + np.exp(-z[H:2 * H]))
        g, o = np.tanh(z[2 * H:3 * H]), 1 / (1 + np.exp(-z[3 * H:]))
        c = f * c + i * g
        return o * np.tanh(c), c

    def decode(self, encoded):
        """encoded: (T, D) float32 for one utterance -> token ids."""
        enc_proj = encoded @ self.enc_w + self.enc_b  # all frames at once
        h = np.zeros(self.hidden, np.float32)
        c = np.zeros(self.hidden, np.float32)
        h, c = self._step(np.zeros(self.hidden, np.float32), h, c)
        pred_proj = h @ self.pred_w + self.pred_b  # only changes after an emission
        tokens = []
        for t in range(enc_proj.shape[0]):
            emitted = 0
            while emitted < self.max_symbols:
                logits = np.maximum(enc_proj[t] + pred_proj, 0) @ self.out_w + self.out_b
                k = int(logits.argmax())
                if k == self.blank:
                    break
                tokens.append(k)
                h, c = self._step(self.embed[k], h, c)
                pred_proj = h @ self.pred_w + self.pred_b
                emitted += 1
        return tokens


def encode_batches(session, audio, chunks, batch_seconds, max_batch):
    """Run the encoder on chunks grouped into length-sorted, padded batches."""
    pieces = [audio[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)] for s, e in chunks]
    order = sorted(range(len(pieces)), key=lambda i: -len(pieces[i]))
    results = [None] * len(pieces)
    i = 0
    while i < len(order):
        longest = len(pieces[order[i]])
        size = max(1, min(max_batch, int(batch_seconds * SAMPLE_RATE // max(longest, 1))))
        group = order[i:i + size]
        wav = np.zeros((len(group), longest), dtype=np.float32)
        lens = np.zeros(len(group), dtype=np.int64)
        for row, idx in enumerate(group):
            wav[row, :len(pieces[idx])] = pieces[idx]
            lens[row] = len(pieces[idx])
        enc, enc_len = session.run(None, {"wav": wav, "wav_len": lens})
        for row, idx in enumerate(group):
            results[idx] = np.ascontiguousarray(enc[row, :, :enc_len[row]].T, dtype=np.float32)
        i += size
    return results


def main():
    audio_path, provider, model_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    encoder_file = sys.argv[4] if len(sys.argv) > 4 else "v3_e2e_rnnt_encoder.onnx"
    batch_seconds = float(os.environ.get("BATCH_SECONDS", "200"))
    max_batch = int(os.environ.get("MAX_BATCH", "16"))
    threads = int(os.environ.get("THREADS", "8"))
    if provider == "cuda":
        torch_lib = r"C:\Users\User\.conda\envs\cuda-torch2\Lib\site-packages\torch\lib"
        ort.preload_dlls(cuda=True, cudnn=True, msvc=True, directory=torch_lib)
    timings = {"import_onnxruntime": IMPORT_ORT_SECONDS}

    def mark(name, start):
        timings[name] = round(time.perf_counter() - start, 3)

    t = time.perf_counter()
    vad = make_session(SILERO_ONNX, "cpu", 1)
    mark("load_vad", t)
    t = time.perf_counter()
    encoder = make_session(os.path.join(model_dir, encoder_file), provider, threads)
    head = RNNTHeadNumpy(os.path.join(model_dir, "v3_e2e_rnnt_head.npz"))
    mark("load_asr", t)
    timings["providers"] = encoder.get_providers()[0]
    timings["startup_total"] = round(time.perf_counter() - T0, 3)
    import sentencepiece  # noqa: only for turning ids into text
    sp = sentencepiece.SentencePieceProcessor(model_file=os.path.expanduser(
        "~/.cache/gigaam/v3_e2e_rnnt_tokenizer.model"))

    for run in (1, 2):
        t_run = time.perf_counter()
        t = time.perf_counter()
        audio = decode_audio(audio_path)
        mark(f"r{run}_decode_audio", t)
        t = time.perf_counter()
        probs = silero_probs(audio, vad)
        regions = speech_regions(probs, len(audio))
        chunks = group_chunks(regions)
        mark(f"r{run}_vad", t)
        t = time.perf_counter()
        encoded = encode_batches(encoder, audio, chunks, batch_seconds, max_batch)
        mark(f"r{run}_encoder", t)
        t = time.perf_counter()
        texts = [sp.decode(head.decode(e)) for e in encoded]
        mark(f"r{run}_rnnt_decode", t)
        mark(f"r{run}_total", t_run)
    timings["audio_seconds"] = round(len(audio) / SAMPLE_RATE, 1)
    timings["chunks"] = len(chunks)
    print(json.dumps(timings))
    out = os.environ.get("OUT_JSON")
    if out:
        json.dump([{"b": list(b), "t": x} for b, x in zip(chunks, texts)],
                  open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
