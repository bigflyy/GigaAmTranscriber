"""Collect whisper.cpp's per-chunk JSON files into one chunk JSON (plan 04 A3).

whisper-cli is run once with every chunk WAV of a file (-f 0000.wav -f 0001.wav ...
-oj), so the model loads once and every chunk is the same piece of audio GigaAM
heard (the chunk WAVs are cut from the GigaAM reference JSON). This script joins
the outputs in chunk order:

    python experiments/whisper/wcpp_chunks.py CHUNK_DIR REF.json OUT.json
"""

import json
import sys
from pathlib import Path


def main():
    chunk_dir, ref_path, out_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    reference = json.loads(ref_path.read_text(encoding="utf-8"))
    chunks = []
    for index, chunk in enumerate(reference["chunks"]):
        data = json.loads((chunk_dir / f"{index:04d}.wav.json").read_text(encoding="utf-8"))
        text = " ".join(item["text"].strip() for item in data["transcription"])
        chunks.append({"start": chunk["start"], "end": chunk["end"], "text": text})
    out = {"model": "whisper-large-v3-turbo whisper.cpp q5_0 (chunks)", "chunks": chunks,
           "audio_seconds": reference["audio_seconds"]}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
