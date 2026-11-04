"""Convert GigaAM PyTorch checkpoints into model folders for the ONNX Runtime app.

This is a developer tool. It needs PyTorch, torchaudio, hydra-core, onnx and
onnxruntime (see requirements-export.txt). The app itself never imports torch.

Each model folder contains:
    encoder.onnx  - raw 16 kHz waveform in; log-mel front-end + Conformer encoder
                    inside the graph. CTC models also include the CTC head, so the
                    output is log-probabilities.
    head.npz      - RNNT only: prediction LSTM and joint network weights (run in numpy).
    vocab.json    - token pieces; index = token id, blank id = len(vocab).
    model.json    - model type, frame duration and file checksums.

Usage (from the repository root):
    python tools/export_models.py v3_e2e_rnnt v3_e2e_ctc --out models
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import warnings

import numpy as np
import onnx
from onnx import helper, numpy_helper, TensorProto
import onnxruntime as ort
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gigaam  # noqa: E402  (the upstream PyTorch package in this repository)

SAMPLE_RATE = 16000


class ConvLogMel(nn.Module):
    """Log-mel spectrogram equal to gigaam.preprocess.FeatureExtractor, built from exportable ops.

    torchaudio's STFT produces complex tensors that the ONNX exporter rejects.
    Here the windowed DFT is a fixed Conv1d basis: real and imaginary rows,
    stride = hop length. The power spectrum goes through the same mel matrix.
    """

    def __init__(self, feature_extractor):
        super().__init__()
        mel = feature_extractor.featurizer[0]
        spec = mel.spectrogram
        if spec.power != 2.0 or spec.normalized or spec.win_length != spec.n_fft:
            raise ValueError("Unsupported spectrogram settings for the conv front-end")
        self.center = spec.center
        self.pad = spec.n_fft // 2
        self.hop = spec.hop_length
        self.freqs = spec.n_fft // 2 + 1
        window = spec.window.double()
        samples = torch.arange(spec.n_fft, dtype=torch.float64)
        freqs = torch.arange(self.freqs, dtype=torch.float64)
        angle = 2 * torch.pi * freqs[:, None] * samples[None, :] / spec.n_fft
        basis = torch.cat([torch.cos(angle) * window, -torch.sin(angle) * window]).float()
        self.register_buffer("basis", basis.unsqueeze(1))  # (2 * freqs, 1, n_fft)
        self.register_buffer("mel_matrix", mel.mel_scale.fb.T.contiguous())  # (n_mels, freqs)

    def forward(self, wav):
        x = wav.unsqueeze(1)
        if self.center:
            x = nn.functional.pad(x, (self.pad, self.pad), mode="reflect")
        y = nn.functional.conv1d(x, self.basis, stride=self.hop)
        power = y[:, :self.freqs] ** 2 + y[:, self.freqs:] ** 2
        return torch.log(torch.matmul(self.mel_matrix, power).clamp(1e-9, 1e9))


class EncoderGraph(nn.Module):
    """wav (B, N), wav_len (B) -> encoder output and its lengths (plus CTC head if present)."""

    def __init__(self, model, is_ctc):
        super().__init__()
        self.model = model
        self.is_ctc = is_ctc
        self.mel = ConvLogMel(model.preprocessor)

    def forward(self, wav, wav_len):
        features = self.mel(wav)
        feature_len = self.model.preprocessor.out_len(wav_len)
        encoded, encoded_len = self.model.encoder(features, feature_len)
        if self.is_ctc:
            return self.model.head(encoder_output=encoded), encoded_len  # (B, T, C)
        return encoded.transpose(1, 2), encoded_len  # (B, T, D)


def store_weights_as_fp16(path):
    """Keep exactly-representable float32 weights as float16 plus a Cast node.

    GigaAM v3 checkpoints already hold float16 weights, so this halves the file
    without changing any value. ONNX Runtime folds the Cast when the session loads,
    so inference still runs in float32. Tensors that would change are left alone.
    """
    model = onnx.load(str(path))
    graph = model.graph
    casts, converted, kept = [], 0, 0
    for index, tensor in enumerate(list(graph.initializer)):
        if tensor.data_type != TensorProto.FLOAT:
            continue
        values = numpy_helper.to_array(tensor)
        if values.size < 1024:
            continue
        half = values.astype(np.float16)
        if not np.array_equal(half.astype(np.float32), values):
            kept += 1
            continue
        original = tensor.name  # tensor is a live reference; CopyFrom renames it
        stored = numpy_helper.from_array(half, original + "__fp16")
        graph.initializer[index].CopyFrom(stored)
        casts.append(helper.make_node("Cast", [stored.name], [original], to=TensorProto.FLOAT,
                                      name=original + "__cast"))
        converted += 1
    for node in reversed(casts):
        graph.node.insert(0, node)
    onnx.save(model, str(path))
    return converted, kept


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def vocabulary(model):
    """Token pieces in id order; SentencePiece word starts keep their U+2581 marker."""
    tokenizer = model.decoding.tokenizer
    if tokenizer.charwise:
        return list(tokenizer.vocab)
    sp = tokenizer.model
    return [sp.id_to_piece(i) for i in range(sp.get_piece_size())]


def export(name, out_root, fp16_storage):
    print(f"== {name}", flush=True)
    model = gigaam.load_model(name, device="cpu", fp16_encoder=False).float().eval()
    is_ctc = "ctc" in name
    folder = Path(out_root) / name
    folder.mkdir(parents=True, exist_ok=True)
    encoder_path = folder / "encoder.onnx"

    graph = EncoderGraph(model, is_ctc).eval()
    example = (torch.randn(2, SAMPLE_RATE * 6), torch.tensor([SAMPLE_RATE * 6, SAMPLE_RATE * 4]))
    out_name = "log_probs" if is_ctc else "encoded"
    with warnings.catch_warnings(), torch.no_grad():
        warnings.simplefilter("ignore")
        torch.onnx.export(
            graph, example, str(encoder_path),
            input_names=["wav", "wav_len"], output_names=[out_name, "encoded_len"],
            dynamic_axes={"wav": {0: "batch", 1: "samples"}, "wav_len": {0: "batch"},
                          out_name: {0: "batch", 1: "frames"}, "encoded_len": {0: "batch"}},
            opset_version=17, dynamo=False)
    if fp16_storage:
        converted, kept = store_weights_as_fp16(encoder_path)
        print(f"   fp16 storage: {converted} tensors converted, {kept} kept in fp32", flush=True)

    files = {"encoder": "encoder.onnx", "vocab": "vocab.json"}
    vocab = vocabulary(model)
    (folder / "vocab.json").write_text(json.dumps(vocab, ensure_ascii=False), encoding="utf-8")

    if not is_ctc:
        decoder, joint = model.head.decoder, model.head.joint
        if decoder.lstm.num_layers != 1:
            raise ValueError("Only a one-layer prediction LSTM is supported")
        np.savez(folder / "head.npz",
                 embed=decoder.embed.weight.detach().numpy(),
                 w_ih=decoder.lstm.weight_ih_l0.detach().numpy(),
                 w_hh=decoder.lstm.weight_hh_l0.detach().numpy(),
                 bias=(decoder.lstm.bias_ih_l0 + decoder.lstm.bias_hh_l0).detach().numpy(),
                 enc_w=joint.enc.weight.detach().numpy(), enc_b=joint.enc.bias.detach().numpy(),
                 pred_w=joint.pred.weight.detach().numpy(), pred_b=joint.pred.bias.detach().numpy(),
                 out_w=joint.joint_net[1].weight.detach().numpy(),
                 out_b=joint.joint_net[1].bias.detach().numpy())
        files["head"] = "head.npz"

    # Numerical check: ONNX Runtime against PyTorch on random audio of a new length.
    wav = torch.randn(1, SAMPLE_RATE * 9) * 0.1
    length = torch.tensor([wav.shape[1]])
    with torch.no_grad():
        expected = graph(wav, length)[0].numpy()
    session = ort.InferenceSession(str(encoder_path), providers=["CPUExecutionProvider"])
    actual = session.run(None, {"wav": wav.numpy(), "wav_len": length.numpy()})[0]
    difference = float(np.abs(actual - expected).max())
    print(f"   max |onnx - torch| = {difference:.2e}", flush=True)
    if difference > 1e-2:
        raise RuntimeError(f"Exported encoder for {name} does not match PyTorch")

    meta = {
        "format": 1,
        "name": name,
        "type": "ctc" if is_ctc else "rnnt",
        "sample_rate": SAMPLE_RATE,
        # 10 ms hop times the encoder's subsampling factor.
        "frame_seconds": model.preprocessor.hop_length / SAMPLE_RATE * model.cfg.encoder.subsampling_factor,
        "blank_id": len(vocab),
        "files": {role: {"name": file, "sha256": sha256(folder / file),
                         "size": os.path.getsize(folder / file)} for role, file in files.items()},
    }
    (folder / "model.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    size = sum(f["size"] for f in meta["files"].values()) / 1024 ** 2
    print(f"   wrote {folder} ({size:.0f} MiB)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+", help="GigaAM model names, e.g. v3_e2e_rnnt v3_e2e_ctc")
    parser.add_argument("--out", type=Path, default=ROOT / "models")
    parser.add_argument("--fp32-storage", action="store_true",
                        help="Do not store exactly-representable weights as float16")
    args = parser.parse_args()
    for name in args.models:
        export(name, args.out, fp16_storage=not args.fp32_storage)


if __name__ == "__main__":
    main()
