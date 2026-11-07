"""Run the app's own Transcriber (GigaAM or Whisper) on one file and save chunks with word times.

    python experiments/whisper/app_engine.py MODEL AUDIO OUT.json [--device auto|gpu|cpu]
        [--language auto|ru|...] [--model-root FOLDER]

MODEL is a catalog key (RNNT, CTC) or, with --model-root, a model folder name inside
FOLDER (which also holds silero_vad_scan.onnx), for example a Whisper folder with
model.json type "whisper". The JSON has the chunk format of gigaam_ref.py (compare.py
reads it) plus every chunk's words, which word_times.py compares between two runs.
Run from the repository root.
"""

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app.engine import Transcriber  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("audio")
    parser.add_argument("out")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--language")
    parser.add_argument("--model-root")
    args = parser.parse_args()
    started = time.perf_counter()
    transcriber = Transcriber(args.model, device=args.device, model_root=args.model_root, language=args.language)
    load_seconds = time.perf_counter() - started
    languages = []
    transcript = transcriber.transcribe(
        args.audio, on_segment=lambda segment: languages.append(getattr(transcriber.asr, "last_language", "")))
    result = {
        "model": args.model,
        "device": transcriber.device_label,
        "gpu": getattr(transcriber.asr, "gpu_name", None),
        "audio_seconds": transcript.audio_seconds,
        "speech_seconds": transcript.speech_seconds,
        "load_seconds": round(load_seconds, 2),
        "transcribe_seconds": round(transcript.elapsed_seconds, 2),
        "chunks": [{"start": s.start, "end": s.end, "text": s.text, "language": language,
                    "words": [[w.start, w.end, w.text] for w in s.words]}
                   for s, language in zip(transcript.segments, languages)],
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.audio}: {len(result['chunks'])} chunks, load {load_seconds:.1f} s, "
          f"transcribe {transcript.elapsed_seconds:.1f} s on {transcriber.device_label} {result['gpu'] or ''}")


if __name__ == "__main__":
    main()
