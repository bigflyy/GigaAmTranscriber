"""Does an int8 (unsigned weights: the CPU engine has no signed ConvInteger) copy of the speaker embedding model run faster on the CPU, and how close is it?

Makes a dynamically quantized (int8 weights) copy of the embedding ONNX model,
then compares the CPU time per hour of audio (10 s windows, 1 s step, one
embedding per window) and the cosine similarity between the float and int8
embeddings of the same real speech (a value near 1.0 means the speaker
clustering will hardly notice).

Usage: python quantize_probe.py EMBEDDING.onnx AUDIO
"""
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from onnxruntime.quantization import QuantType, quantize_dynamic

from common import SAMPLE_RATE, load_audio

WINDOWS_PER_HOUR = 3600


def fbank(piece):
    """80-bin Kaldi-style log mel filterbank, 25 ms / 10 ms, mean-normalised (numpy)."""
    frame, shift, bins = 400, 160, 80
    piece = piece * 32768.0
    count = 1 + (len(piece) - frame) // shift
    frames = np.stack([piece[i * shift:i * shift + frame] for i in range(count)])
    frames = frames - frames.mean(axis=1, keepdims=True)
    frames = np.concatenate([frames[:, :1], frames[:, 1:] - 0.97 * frames[:, :-1]], axis=1)
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(frame) / (frame - 1))) ** 0.85
    spectrum = np.abs(np.fft.rfft(frames * window, n=512)) ** 2
    mel = lambda f: 1127 * np.log(1 + f / 700.0)  # noqa: E731
    edges = np.linspace(mel(20), mel(8000), bins + 2)
    freqs = mel(np.arange(257) * SAMPLE_RATE / 512)
    weights = np.zeros((bins, 257))
    for b in range(bins):
        left, centre, right = edges[b:b + 3]
        weights[b] = np.clip(np.minimum((freqs - left) / (centre - left), (right - freqs) / (right - centre)), 0, None)
    features = np.log(np.maximum(spectrum @ weights.T, 1.19e-7))
    return (features - features.mean(axis=0)).astype(np.float32)


def run_time(session, batch, repeats=3):
    """Median seconds for one batch after a warm-up."""
    name = session.get_inputs()[0].name
    session.run(None, {name: batch})
    times = []
    for _ in range(repeats):
        started = time.perf_counter()
        session.run(None, {name: batch})
        times.append(time.perf_counter() - started)
    return float(np.median(times))


def main():
    model_path, audio_path = Path(sys.argv[1]), sys.argv[2]
    int8_path = model_path.with_name(model_path.stem + ".int8-dynamic.onnx")
    if not int8_path.exists():
        quantize_dynamic(str(model_path), str(int8_path), weight_type=QuantType.QUInt8)
    audio = load_audio(audio_path)
    batch = np.stack([fbank(audio[(30 + 10 * i) * SAMPLE_RATE:(40 + 10 * i) * SAMPLE_RATE]) for i in range(32)])
    options = ort.SessionOptions()
    options.intra_op_num_threads = 8
    results = {}
    for label, path in (("float", model_path), ("int8", int8_path)):
        session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
        seconds = run_time(session, batch) / len(batch) * WINDOWS_PER_HOUR
        results[label] = session.run(None, {session.get_inputs()[0].name: batch})[0]
        print(f"{label:>5}: {path.stat().st_size / 1e6:6.1f} MB, CPU {seconds:6.1f} s per hour of audio", flush=True)
    a, b = results["float"], results["int8"]
    cosine = np.sum(a * b, axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    print(f"cosine float vs int8 on real speech: min {cosine.min():.4f}, mean {cosine.mean():.4f}")


if __name__ == "__main__":
    main()
