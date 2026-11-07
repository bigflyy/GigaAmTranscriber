"""GigaAM reference for the Whisper test (plan 04 A1).

Runs the app's own pipeline (Silero VAD chunks, GigaAM RNNT) on one file and
writes a JSON with the chunk boundaries, the text of every chunk and timings.
The Whisper scripts read the chunks from this JSON, so both models hear exactly
the same pieces of audio.

    python experiments/whisper/gigaam_ref.py AUDIO OUT.json [auto|dml|cpu]

Run from the repository root (it imports gigaam_app).
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app.engine import Transcriber  # noqa: E402


def main():
    audio_path, out_path = sys.argv[1], sys.argv[2]
    device = sys.argv[3] if len(sys.argv) > 3 else "auto"
    started = time.perf_counter()
    transcriber = Transcriber("RNNT", device=device)
    load_seconds = time.perf_counter() - started
    transcript = transcriber.transcribe(audio_path)
    result = {
        "model": "GigaAM v3 RNNT",
        "device": transcriber.device_label,
        "audio_seconds": transcript.audio_seconds,
        "speech_seconds": transcript.speech_seconds,
        "load_seconds": round(load_seconds, 2),
        "transcribe_seconds": round(transcript.elapsed_seconds, 2),
        "chunks": [{"start": s.start, "end": s.end, "text": s.text} for s in transcript.segments],
    }
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{audio_path}: {len(result['chunks'])} chunks, load {load_seconds:.1f} s, "
          f"transcribe {transcript.elapsed_seconds:.1f} s on {transcriber.device_label}")


if __name__ == "__main__":
    main()
