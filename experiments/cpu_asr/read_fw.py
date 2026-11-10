"""Plan 08 A3: faster-whisper (CTranslate2) reading every dumped piece on the CPU.

    python -I experiments/cpu_asr/read_fw.py MODEL_DIR DATA_DIR NAME [NAME ...]
        --mode one|batch --language auto|ru|hint [--threads 8] [--batch 8] [--compute int8] [--most N]

MODEL_DIR: a CTranslate2 Whisper model (mobiuslabsgmbh/faster-whisper-large-v3-turbo, fp16,
quantised to --compute when loaded). Settings as close to the app's whisper.cpp as faster-whisper
allows: greedy (beam 1), nothing carried over from the previous piece, word times, no VAD.
--mode one: WhisperModel.transcribe per piece (what the search does now, one piece at a time);
the language is detected per piece when --language auto.
--mode batch: BatchedInferencePipeline over all pieces of a file at once (the pieces put end to
end, each one its own clip of clip_timestamps, --batch per encoder call); the language is detected
once, on the first pieces. Per-piece time there is the file's time divided by the pieces.
--language hint: "ru" for pieces whose GigaAM text is almost all Cyrillic, detected otherwise
(common.hint_language).
Writes DATA_DIR/readings/LABEL/NAME.json (LABEL fw-MODE-LANGUAGE). Run with the cpu-asr-exp venv.
"""

import argparse
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import hint_language, load_pieces, peak_ram_mb, piece_path, save_readings  # noqa: E402

SAMPLE_RATE = 16000


def word_rows(words, shift):
    """faster-whisper Words -> [start, end, text, probability] with times moved by shift."""
    rows = []
    for word in words:
        text = word.word.strip()
        if not text:
            continue
        # faster-whisper splits "LLM-агентов" into " LLM" and "-агентов": a piece without a
        # leading space belongs to the word before, as in the app's words_from_tokens.
        if rows and not word.word.startswith(" "):
            rows[-1][1] = round(word.end + shift, 3)
            rows[-1][2] += text
            rows[-1][3] = min(rows[-1][3], round(word.probability, 3))
            continue
        rows.append([round(word.start + shift, 3), round(word.end + shift, 3), text, round(word.probability, 3)])
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir")
    parser.add_argument("data_dir")
    parser.add_argument("names", nargs="+")
    parser.add_argument("--mode", choices=("one", "batch"), default="one")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--compute", default="int8")
    parser.add_argument("--most", type=int)
    parser.add_argument("--label", help="output folder name instead of fw-MODE-LANGUAGE")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from faster_whisper import BatchedInferencePipeline, WhisperModel

    label = args.label or f"fw-{args.mode}-{args.language}" + ("" if args.compute == "int8" else f"-{args.compute}")
    language = None if args.language in ("auto", "hint") else args.language
    started = time.perf_counter()
    model = WhisperModel(args.model_dir, device="cpu", compute_type=args.compute, cpu_threads=args.threads)
    pipeline = BatchedInferencePipeline(model) if args.mode == "batch" else None
    print(f"{label}: loaded in {time.perf_counter() - started:.1f} s")

    for name in args.names:
        info = load_pieces(args.data_dir, name, args.most)
        pieces = info["pieces"]
        samples = [np.load(piece_path(args.data_dir, name, piece)) for piece in pieces]
        results = []
        if args.mode == "one":
            total = 0.0
            for piece, audio in zip(pieces, samples):
                began = time.perf_counter()
                piece_language = hint_language(piece) if args.language == "hint" else language
                segments, details = model.transcribe(audio, language=piece_language, beam_size=1,
                                                     condition_on_previous_text=False, word_timestamps=True,
                                                     vad_filter=False)
                rows = [row for segment in segments for row in word_rows(segment.words or [], piece["start"])]
                spent = time.perf_counter() - began
                total += spent
                results.append({"number": piece["number"], "spent": round(spent, 3),
                                "language": details.language, "words": rows})
        else:
            # One pipeline call per language: with --language hint the Russian pieces and the
            # pieces whose language Whisper must detect go in separate calls.
            if args.language == "hint":
                parts = {}
                for index, piece in enumerate(pieces):
                    parts.setdefault(hint_language(piece), []).append(index)
            else:
                parts = {language: list(range(len(pieces)))}
            total, by_index = 0.0, {}
            for part_language, indices in parts.items():
                joined = np.concatenate([samples[i] for i in indices])
                bounds, position = [], 0
                for i in indices:
                    bounds.append((position, position + len(samples[i])))
                    position += len(samples[i])
                clips = [{"start": a / SAMPLE_RATE, "end": b / SAMPLE_RATE} for a, b in bounds]
                began = time.perf_counter()
                segments, details = pipeline.transcribe(joined, language=part_language, beam_size=1,
                                                        word_timestamps=True, clip_timestamps=clips,
                                                        batch_size=args.batch)
                per_clip = [[] for _ in indices]
                for segment in segments:
                    for word in segment.words or []:
                        middle = (word.start + word.end) / 2 * SAMPLE_RATE
                        slot = next((k for k, (a, b) in enumerate(bounds) if a <= middle < b), len(bounds) - 1)
                        per_clip[slot].append(word)
                total += time.perf_counter() - began
                for slot, i in enumerate(indices):
                    shift = pieces[i]["start"] - bounds[slot][0] / SAMPLE_RATE
                    by_index[i] = (details.language, word_rows(per_clip[slot], shift))
            for index, piece in enumerate(pieces):
                found_language, rows = by_index[index]
                results.append({"number": piece["number"], "spent": round(total / len(pieces), 3),
                                "language": found_language, "words": rows})
        audio_seconds = sum(p["seconds"] for p in pieces)
        save_readings(args.data_dir, label, name, total, results, {"peak_ram_mb": peak_ram_mb()})
        print(f"{label} {name}: {len(pieces)} pieces, {audio_seconds:.0f} s of audio, {total:.1f} s "
              f"({total / max(1, len(pieces)):.2f} s per piece), peak RAM {peak_ram_mb()} MB")


if __name__ == "__main__":
    main()
