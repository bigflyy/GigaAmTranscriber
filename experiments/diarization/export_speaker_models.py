"""Export the community-1 speaker models for the app (plan 07 B1): ONNX + numpy files.

Runs in the torch env (cuda-torch2, pyannote.audio 4.0.5), offline from the
Hugging Face cache. The app then needs only ONNX Runtime and numpy:

- segmentation.onnx: pyannote segmentation-3.0, waveform (batch, 1, 160000)
  -> powerset log-probabilities (batch, 589, 7).
- embedding.onnx: WeSpeaker ResNet34-LM with the weighted statistics pooling of
  every local speaker inside: centred fbank (batch, frames, 80) and weights
  (batch, speakers, frames') -> voice prints (batch, speakers, 256), frames' =
  the trunk's time steps (frames / 8, rounded up). The trunk runs once per
  window instead of once per speaker, and only the voice prints leave the GPU.
- speakers.npz: the powerset mapping (7 x 3) and the community-1 PLDA with its
  generalised eigen-decomposition done here (the app has no scipy).

Also writes reference values for one audio file (reference.npz) so the numpy
port can be compared step by step (check_port.py).

Usage: python export_speaker_models.py OUT_DIR [AUDIO_FOR_REFERENCE]
"""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from pyannote.audio import Model  # noqa: E402
from scipy.linalg import eigh  # noqa: E402

PLDA_DIR = next((Path.home() / ".cache/huggingface/hub/models--pyannote--speaker-diarization-community-1/snapshots").glob("*/plda"))
WINDOW_SAMPLES = 160000


class Embedder(torch.nn.Module):
    """ResNet34 trunk once, then pyannote's StatsPool + seg_1 for each local speaker."""

    def __init__(self, resnet):
        super().__init__()
        self.resnet = resnet

    def forward(self, fbank, weights):
        frames = self.resnet.forward_frames(fbank)                    # (B, 256, 10, T')
        frames = frames.reshape(frames.shape[0], -1, frames.shape[-1])  # (B, C, T')
        w = weights.unsqueeze(2)                                      # (B, S, 1, T')
        x = frames.unsqueeze(1)                                       # (B, 1, C, T')
        v1 = w.sum(dim=3) + 1e-8                                      # (B, S, 1)
        mean = (x * w).sum(dim=3) / v1                                # (B, S, C)
        dx2 = torch.square(x - mean.unsqueeze(3))
        v2 = torch.square(w).sum(dim=3)
        std = torch.sqrt((dx2 * w).sum(dim=3) / (v1 - v2 / v1 + 1e-8))
        return self.resnet.seg_1(torch.cat([mean, std], dim=2))      # (B, S, 256)


def export_segmentation(out_dir):
    """Export segmentation-3.0 and return (model, powerset mapping, frame grid)."""
    model = Model.from_pretrained("pyannote/segmentation-3.0").eval()
    dummy = torch.zeros(2, 1, WINDOW_SAMPLES)
    torch.onnx.export(model, dummy, out_dir / "segmentation.onnx", input_names=["waveform"],
                      output_names=["logits"], dynamic_axes={"waveform": {0: "batch"}, "logits": {0: "batch"}},
                      opset_version=17, dynamo=False)
    from pyannote.audio.utils.powerset import Powerset
    spec = model.specifications
    mapping = Powerset(len(spec.classes), spec.powerset_max_classes).mapping.cpu().numpy().astype(np.float32)
    frames = model.receptive_field
    grid = {"start": frames.start, "duration": frames.duration, "step": frames.step}
    return model, mapping, grid


def export_embedding(out_dir):
    """Export the voice print model with its pooling; return the torch model."""
    model = Model.from_pretrained("pyannote/wespeaker-voxceleb-resnet34-LM").eval()
    embedder = Embedder(model.resnet).eval()
    dummy = (torch.zeros(2, 998, 80), torch.ones(2, 3, 125))
    torch.onnx.export(embedder, dummy, out_dir / "embedding.onnx", input_names=["fbank", "weights"],
                      output_names=["embeddings"],
                      dynamic_axes={"fbank": {0: "batch", 1: "time"}, "weights": {0: "batch", 1: "speakers", 2: "steps"},
                                    "embeddings": {0: "batch", 1: "speakers"}},
                      opset_version=17, dynamo=False)
    return model


def plda_arrays():
    """community-1 PLDA, as in pyannote.audio.utils.vbx.vbx_setup, decomposed here."""
    x = np.load(PLDA_DIR / "xvec_transform.npz")
    p = np.load(PLDA_DIR / "plda.npz")
    plda_tr, plda_psi = p["tr"], p["psi"]
    within = np.linalg.inv(plda_tr.T.dot(plda_tr))
    between = np.linalg.inv((plda_tr.T / plda_psi).dot(plda_tr))
    acvar, wccn = eigh(between, within)
    return {"plda_mean1": x["mean1"], "plda_mean2": x["mean2"], "plda_lda": x["lda"], "plda_mu": p["mu"],
            "plda_tr": wccn.T[::-1].copy(), "plda_psi": acvar[::-1].copy()}


def reference(out_dir, audio_path):
    """Run the torch community-1 pipeline on one file, keeping its intermediate arrays."""
    sys.path.insert(0, str(Path(__file__).parent))
    from run_pyannote import build  # noqa: E402
    from common import SAMPLE_RATE, load_audio  # noqa: E402
    pipeline = build("c1")
    kept = {}

    def hook(step, artefact, file=None, **kwargs):
        if artefact is None or "completed" in kwargs:
            return
        data = getattr(artefact, "data", artefact)
        if isinstance(data, np.ndarray):
            kept[step] = data
    waveform = torch.from_numpy(load_audio(audio_path)).unsqueeze(0)
    output = pipeline({"waveform": waveform, "sample_rate": SAMPLE_RATE}, hook=hook)
    turns = [(seg.start, seg.end, label) for seg, _, label in output.exclusive_speaker_diarization.itertracks(yield_label=True)]
    kept["exclusive_turns"] = np.array([(s, e, int(label.split("_")[1])) for s, e, label in turns])
    np.savez_compressed(out_dir / "reference.npz", **kept)
    print("reference steps:", {k: v.shape for k, v in kept.items()})


def main():
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    seg_model, mapping, grid = export_segmentation(out_dir)
    emb_model = export_embedding(out_dir)
    np.savez(out_dir / "speakers.npz", powerset=mapping, **plda_arrays())
    (out_dir / "speakers.json").write_text(json.dumps({
        "window_samples": WINDOW_SAMPLES, "frames": grid,
        "embedding_steps": "ceil(ceil(ceil(frames / 2) / 2) / 2)",
        "fbank": {"num_mel_bins": 80, "frame_length_ms": 25, "frame_shift_ms": 10, "window": "hamming"},
        "clustering": {"threshold": 0.6, "Fa": 0.07, "Fb": 0.8, "lda_dimension": 128},
    }, indent=1), encoding="utf-8")
    # Check the ONNX copies against torch on random input.
    import onnxruntime as ort
    wave = torch.randn(3, 1, WINDOW_SAMPLES) * 0.1
    masks = (torch.rand(3, 3, 589) > 0.5).float()   # pyannote's own call: one speaker's mask at a time
    with torch.no_grad():
        torch_seg = seg_model(wave).numpy()
        fbank = emb_model.compute_fbank(wave)
        torch_emb = np.stack([emb_model(wave, weights=masks[:, s]).numpy() for s in range(3)], axis=1)
    steps = torch.nn.functional.interpolate(masks, size=125, mode="nearest").numpy()
    onnx_seg = ort.InferenceSession(str(out_dir / "segmentation.onnx")).run(None, {"waveform": wave.numpy()})[0]
    onnx_emb = ort.InferenceSession(str(out_dir / "embedding.onnx")).run(
        None, {"fbank": fbank.numpy(), "weights": steps})[0]
    print("segmentation", onnx_seg.shape, "max diff", float(np.abs(onnx_seg - torch_seg).max()))
    print("voice prints", onnx_emb.shape, "max diff", float(np.abs(onnx_emb - torch_emb).max()),
          "of max", float(np.abs(torch_emb).max()))
    print("frame grid", grid)
    np.savez(out_dir / "fbank_check.npz", wave=wave.numpy()[:, 0], fbank=fbank.numpy())
    if len(sys.argv) > 2:
        reference(out_dir, sys.argv[2])
    for path in sorted(out_dir.iterdir()):
        print(f"{path.name}: {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
