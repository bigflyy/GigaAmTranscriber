"""Measure model loading and transcription speed on a PCM WAV file."""

import argparse
import json
from pathlib import Path
from time import perf_counter
import wave

import gigaam
import torch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path, help="PCM WAV input")
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--cpu-threads", type=int, default=4)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if args.cpu_threads < 1:
        parser.error("--cpu-threads must be at least 1")
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA is unavailable")

    with wave.open(str(args.audio), "rb") as audio:
        audio_seconds = audio.getnframes() / audio.getframerate()

    start = perf_counter()
    model = gigaam.load_model("v3_e2e_rnnt", device=args.device)
    if args.device == "cuda":
        torch.cuda.synchronize()
    model_load_seconds = perf_counter() - start
    results = []
    for number in range(1, args.runs + 1):
        if args.device == "cuda":
            torch.cuda.synchronize()
        start = perf_counter()
        segments = model.transcribe_longform(str(args.audio), cpu_threads=args.cpu_threads)
        if args.device == "cuda":
            torch.cuda.synchronize()
        elapsed = perf_counter() - start
        results.append({
            "run": number,
            "seconds": round(elapsed, 3),
            "x_realtime": round(audio_seconds / elapsed, 2),
            "segments": len(segments),
        })

    print(json.dumps({
        "device": args.device,
        "torch": torch.__version__,
        "torch_threads_after_transcription": torch.get_num_threads(),
        "gigaam_cpu_threads": args.cpu_threads if args.device == "cpu" else None,
        "silero_threads": 1,
        "model": "v3_e2e_rnnt",
        "encoder_dtype": str(model._dtype),
        "audio_seconds": round(audio_seconds, 3),
        "model_load_seconds": round(model_load_seconds, 3),
        "runs": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
