"""How fast the diarization ONNX models run on DirectML and on the CPU.

Runs the pyannote segmentation-3.0 model and a speaker embedding model on
random input of the real shapes (10 s windows) and converts the time into
"seconds per hour of audio" for a pyannote-style pipeline with a 1 s step:
3600 windows per hour; embeddings once per window ("per window", our
planned shared-trunk version) or three times ("x3", one per local speaker,
as sherpa-onnx and pyannote do it).

Usage: python speed_probe.py SEGMENTATION.onnx EMBEDDING.onnx [BATCH]
"""
import sys
import time

import numpy as np
import onnxruntime as ort

WINDOW_SAMPLES = 160000   # 10 s at 16 kHz
FBANK_FRAMES = 998        # 10 s of 25 ms / 10 ms fbank frames
WINDOWS_PER_HOUR = 3600   # 1 s step


def timed(session, feeds, repeats=5):
    """Median seconds of one run after two warm-up runs."""
    for _ in range(2):
        session.run(None, feeds)
    times = []
    for _ in range(repeats):
        started = time.perf_counter()
        session.run(None, feeds)
        times.append(time.perf_counter() - started)
    return float(np.median(times))


def main():
    segmentation_path, embedding_path = sys.argv[1], sys.argv[2]
    batch = int(sys.argv[3]) if len(sys.argv) > 3 else 32
    rng = np.random.default_rng(0)
    audio = (0.1 * rng.standard_normal((batch, 1, WINDOW_SAMPLES))).astype(np.float32)
    fbank = rng.standard_normal((batch, FBANK_FRAMES, 80)).astype(np.float32)
    for provider in ("DmlExecutionProvider", "CPUExecutionProvider"):
        options = ort.SessionOptions()
        if provider == "CPUExecutionProvider":
            options.intra_op_num_threads = 8
        seg = ort.InferenceSession(segmentation_path, options, providers=[provider])
        emb = ort.InferenceSession(embedding_path, options, providers=[provider])
        seg_name, emb_name = seg.get_inputs()[0].name, emb.get_inputs()[0].name
        seg_time = timed(seg, {seg_name: audio}) / batch * WINDOWS_PER_HOUR
        emb_time = timed(emb, {emb_name: fbank}) / batch * WINDOWS_PER_HOUR
        print(f"{provider[:-17]:>4}: per hour of audio: segmentation {seg_time:6.1f} s, "
              f"embeddings per window {emb_time:6.1f} s, x3 {3 * emb_time:6.1f} s", flush=True)


if __name__ == "__main__":
    main()
