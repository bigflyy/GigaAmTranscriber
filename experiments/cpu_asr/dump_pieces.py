"""Plan 08 A1: the pieces the app's suggestion search reads, saved for every runtime to read.

    python experiments/cpu_asr/dump_pieces.py AUDIO NAME OUT_DIR [--model RNNT] [--device auto]

Transcribes AUDIO with the app's own Transcriber, finds the doubtful groups the way the window
does (fix.doubt_groups below Settings.doubt_light), joins them into pieces the way
controller._suggest_pieces does (one piece per line, or one per group on a line longer than
fix.MAX_SECONDS), and cuts each piece's audio the way worker._reread does (quietest point in
each search window). Writes OUT_DIR/NAME/pieces.json and OUT_DIR/NAME/NNNN.npy (float32, 16 kHz).
Run from the repository root with the dev venv.
"""

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app import fix  # noqa: E402
from gigaam_app.audio import SAMPLE_RATE, decode_range  # noqa: E402
from gigaam_app.config import Settings  # noqa: E402
from gigaam_app.engine import Transcriber  # noqa: E402
from gigaam_app.worker import REREAD_MARGIN  # noqa: E402


def app_pieces(segments, groups):
    """Like controller._suggest_pieces, but with positions: [(line or None, [(first, last)])].
    line is the segment index when the whole line is read, None when only the group with
    its usual context is read (a line longer than fix.MAX_SECONDS)."""
    pieces = []
    for first, last in groups:
        words = segments[first[0]].words
        whole = words[-1].end - words[0].start <= fix.MAX_SECONDS
        if whole and pieces and pieces[-1][0] == first[0]:
            pieces[-1][1].append((first, last))
        else:
            pieces.append((first[0] if whole else None, [(first, last)]))
    return pieces


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("name")
    parser.add_argument("out_dir")
    parser.add_argument("--model", default="RNNT")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    folder = Path(args.out_dir) / args.name
    folder.mkdir(parents=True, exist_ok=True)
    engine = Transcriber(args.model, device=args.device)
    started = time.perf_counter()
    transcript = engine.transcribe(args.audio)
    print(f"{args.name}: transcribed in {time.perf_counter() - started:.1f} s")
    segments = transcript.segments
    below = Settings().doubt_light
    groups = fix.doubt_groups(segments, below)

    saved = []
    for number, (line, piece_groups) in enumerate(app_pieces(segments, groups)):
        if line is not None:
            context_first, context_last = (line, 0), (line, len(segments[line].words) - 1)
        else:
            context_first, context_last = fix.context_bounds(segments, *piece_groups[0])
        context = fix.positions_between(segments, context_first, context_last)
        (left, right) = fix.search_windows(segments, context_first, context_last, transcript.audio_seconds)
        offset = max(0.0, left[0] - REREAD_MARGIN)
        samples = decode_range(args.audio, offset, right[1] + REREAD_MARGIN - offset)
        start = fix.quietest_point(samples, offset, *left)
        end = fix.quietest_point(samples, offset, *right)
        piece = samples[int(round((start - offset) * SAMPLE_RATE)):int(round((end - offset) * SAMPLE_RATE))]
        np.save(folder / f"{number:04d}.npy", piece.astype(np.float32))
        context_words = [fix.word_at(segments, position) for position in context]
        saved.append({
            "number": number, "start": start, "end": end, "seconds": len(piece) / SAMPLE_RATE,
            "whole_line": line is not None,
            "words": [[w.start, w.end, w.text, w.confidence] for w in context_words],
            "selected": [[context.index(first), context.index(last)] for first, last in piece_groups],
        })
    words_total = sum(len(segment.words) for segment in segments)
    info = {"audio": str(args.audio), "model": args.model, "below": below, "audio_seconds": transcript.audio_seconds,
            "lines": len(segments), "words": words_total, "groups": len(groups), "pieces": saved}
    (folder / "pieces.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    seconds = sum(p["seconds"] for p in saved)
    print(f"{args.name}: {len(segments)} lines, {words_total} words, {len(groups)} groups, "
          f"{len(saved)} pieces, {seconds:.0f} s of audio in pieces")


if __name__ == "__main__":
    main()
