"""Plan 08 A2: the app's whisper.cpp (q5_0) reading every dumped piece on the CPU.

    python experiments/cpu_asr/read_wcpp.py DATA_DIR NAME [NAME ...] --language auto|ru
        [--threads 8] [--label wcpp-auto]

Reads DATA_DIR/NAME/pieces.json and its .npy pieces (dump_pieces.py) with the installed Whisper
model, the same way the search does (fix.reread_piece, no terms), and writes
DATA_DIR/readings/LABEL/NAME.json: per piece the seconds spent and the words. Prints totals.
Run from the repository root with the dev venv.
"""

import argparse
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_pieces, peak_ram_mb, piece_path, save_readings  # noqa: E402

from gigaam_app import fix  # noqa: E402
from gigaam_app.engine import Transcriber  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir")
    parser.add_argument("names", nargs="+")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--label")
    parser.add_argument("--most", type=int, help="at most this many pieces per file, picked evenly")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    label = args.label or f"wcpp-{args.language}"

    started = time.perf_counter()
    engine = Transcriber("Whisper", device="cpu", cpu_threads=args.threads)
    engine.set_language(args.language)
    print(f"{label}: loaded in {time.perf_counter() - started:.1f} s ({engine.device_label})")
    for name in args.names:
        info = load_pieces(args.data_dir, name, args.most)
        results, total = [], 0.0
        for piece in info["pieces"]:
            samples = np.load(piece_path(args.data_dir, name, piece))
            began = time.perf_counter()
            words = fix.reread_piece(engine.asr, samples, piece["start"])
            spent = time.perf_counter() - began
            total += spent
            results.append({"number": piece["number"], "spent": round(spent, 3),
                            "language": getattr(engine.asr, "last_language", None),
                            "words": [[w.start, w.end, w.text, w.confidence] for w in words]})
        audio = sum(p["seconds"] for p in info["pieces"])
        save_readings(args.data_dir, label, name, total, results, {"peak_ram_mb": peak_ram_mb()})
        print(f"{label} {name}: {len(results)} pieces, {audio:.0f} s of audio, {total:.1f} s "
              f"({total / max(1, len(results)):.2f} s per piece)")


if __name__ == "__main__":
    main()
