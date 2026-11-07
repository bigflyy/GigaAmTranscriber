"""Re-recognise selected parts of a file the way the window does (plan 03 A3), without the window.

    python experiments/whisper/reread_check.py AUDIO WORD [WORD ...] [--terms "..."]
        [--words-before 3] [--words-after 3]

Transcribes AUDIO with RNNT, then for each WORD (a word as RNNT writes it, lower case,
without punctuation) selects its first occurrence with a few words around it and runs
the worker's "reread" job on it: RNNT, CTC and, when downloaded, Whisper (with --terms
as its prompt). Prints the current text and each reading (the selected part, and the
whole piece with its context) with its time. Uses the normal model folders (models/ and
the per-user downloads). Run from the repository root.
"""

import argparse
from pathlib import Path
import queue
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app import catalog, fix  # noqa: E402
from gigaam_app.engine import Transcriber  # noqa: E402
from gigaam_app.worker import Worker  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("words", nargs="+")
    parser.add_argument("--terms", default="")
    parser.add_argument("--words-before", type=int, default=3)
    parser.add_argument("--words-after", type=int, default=3)
    args = parser.parse_args()

    events = queue.Queue()
    worker = Worker(events)
    worker.engine_key = ("RNNT", "auto", 0)
    worker.engine = Transcriber("RNNT", device="auto")
    transcript = worker.engine.transcribe(args.audio)
    segments = transcript.segments
    flat = [(s, w) for s, segment in enumerate(segments) for w in range(len(segment.words))]
    plain = [re.sub(r"[^\w-]", "", segments[s].words[w].text.lower()) for s, w in flat]
    models = [key for key in ("RNNT", "CTC", "Whisper") if catalog.installed_folder(catalog.find(key))]
    for target in args.words:
        if target not in plain:
            print(f"\n{target!r}: not in the RNNT text")
            continue
        index = plain.index(target)
        first = flat[max(0, index - args.words_before)]
        last = flat[min(len(flat) - 1, index + args.words_after)]
        context_first, context_last = fix.context_bounds(segments, first, last)
        windows = fix.search_windows(segments, context_first, context_last, transcript.audio_seconds)
        context = fix.positions_between(segments, context_first, context_last)
        context_words = [fix.word_at(segments, position) for position in context]
        selected = (context.index(first), context.index(last))
        print(f"\n== {target}: now  \"{fix.selected_text(segments, first, last)}\"")
        started = time.perf_counter()
        worker._reread(1, args.audio, windows, models, "auto", 0, "auto", args.terms or None)
        while not events.empty():
            event = events.get()
            elapsed = time.perf_counter() - started
            if event[0] == "reread_range":
                print(f"   cut {event[2]:.2f}-{event[3]:.2f} s (windows {windows[0][0]:.2f}-{windows[0][1]:.2f}, "
                      f"{windows[1][0]:.2f}-{windows[1][1]:.2f})")
            elif event[0] == "reread_result":
                _, _, model, words, error = event
                if words is None:
                    print(f"   {model:8s} ERROR {error}")
                    continue
                whole = " ".join(w.text for w in words)
                text = " ".join(w.text for w in fix.trim_reading(words, context_words, *selected))
                print(f"   {model:8s} \"{text}\"  (+{elapsed:.1f} s)")
                print(f"            piece: {whole}")


if __name__ == "__main__":
    main()
