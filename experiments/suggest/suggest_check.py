"""Suggested fixes for doubtful words (plan 06 A5), measured without the window.

    python experiments/suggest/suggest_check.py AUDIO [--model RNNT] [--terms "..."]
        [--below 0.97] [--context words|chunk|centred] [--device auto] [--out FILE.json]

Transcribes AUDIO with --model, groups its doubtful words (confidence below --below) the
way the window does (fix.doubt_groups), recognises each group again with the other installed
models through the worker's "suggest" job, and prints every offer: the current words, the
offered words and which models offered them. Ends with counts and times. --out keeps the
offers as JSON for judging by hand. Uses the normal model folders. Run from the repository root.

--context words (what the app does now): each group is read with up to 1.5 s / 6 words of context
on each side (fix.context_bounds), one reading per group. --context chunk: each line (one VAD
chunk, at most 25 s) that holds doubtful words is read once as a whole, and every group in it takes
its offer from that reading: more context for Whisper, and fewer 30 s Whisper windows.
--context centred (owner's question, 2026-11-08): each group is read with about 25 s around it,
half before and half after, across line ends; one reading per group.
"""

import argparse
import json
from pathlib import Path
import queue
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app import catalog, fix  # noqa: E402
from gigaam_app.engine import Transcriber  # noqa: E402
from gigaam_app.worker import Worker  # noqa: E402


CENTRED_SECONDS = 25.0


def centred_bounds(segments, first, last):
    """The first and last word of about CENTRED_SECONDS around a group, half on each side
    (less at the ends of the file), crossing line ends."""
    start, end = fix.word_at(segments, first).start, fix.word_at(segments, last).end
    half = max(0.0, (CENTRED_SECONDS - (end - start)) / 2)
    low, high = first, last
    while (before := fix.neighbour(segments, low, -1)) is not None and \
            fix.word_at(segments, before).start >= start - half:
        low = before
    while (after := fix.neighbour(segments, high, +1)) is not None and \
            fix.word_at(segments, after).end <= end + half:
        high = after
    return low, high


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--model", default="RNNT")
    parser.add_argument("--terms", default="")
    parser.add_argument("--below", type=float, default=0.97)
    parser.add_argument("--context", choices=("words", "chunk", "centred"), default="words")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--out")
    args = parser.parse_args()
    # The log usually goes to a file whose default encoding (cp1251) lacks some symbols.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    events = queue.Queue()
    worker = Worker(events)
    worker.engine_key = (args.model, "auto", 0)
    worker.engine = Transcriber(args.model, device=args.device)
    started = time.perf_counter()
    transcript = worker.engine.transcribe(args.audio)
    print(f"transcribed in {time.perf_counter() - started:.1f} s")
    segments = transcript.segments
    words_total = sum(len(segment.words) for segment in segments)
    groups = fix.doubt_groups(segments, args.below)
    doubtful = sum(len(fix.positions_between(segments, a, b)) for a, b in groups)
    models = [key for key in ("RNNT", "CTC", "Whisper")
              if key != args.model and catalog.installed_folder(catalog.find(key))]
    print(f"{words_total} words, {len(groups)} groups ({doubtful} words incl. gaps), models {models}, "
          f"context {args.context}")

    # One reading per piece: a piece is a group with its context ("words") or a whole line
    # with all its groups ("chunk"). Each piece: (context positions, [(first, last) per group]).
    pieces = []
    if args.context == "centred":
        for first, last in groups:
            pieces.append((fix.positions_between(segments, *centred_bounds(segments, first, last)),
                           [(first, last)]))
    elif args.context == "words":
        for first, last in groups:
            pieces.append((fix.positions_between(segments, *fix.context_bounds(segments, first, last)),
                           [(first, last)]))
    else:
        for line in sorted({first[0] for first, _ in groups}):
            line_groups = [(first, last) for first, last in groups if first[0] == line]
            count = len(segments[line].words)
            pieces.append((fix.positions_between(segments, (line, 0), (line, count - 1)), line_groups))

    found, per_model, timings = [], {model: 0 for model in models}, []
    search_started = time.perf_counter()
    number = 0
    for piece_number, (context, piece_groups) in enumerate(pieces, 1):
        context_words = [fix.word_at(segments, position) for position in context]
        windows = fix.search_windows(segments, context[0], context[-1], transcript.audio_seconds)
        group_started = time.perf_counter()
        worker._reread(piece_number, args.audio, windows, models, args.device, 0, "auto", args.terms or None,
                       prefix="suggest")
        timings.append(time.perf_counter() - group_started)
        readings = []
        while not events.empty():
            event = events.get()
            if event[0] == "suggest_result" and event[3] is not None:
                readings.append((event[2], event[3]))
        for first, last in piece_groups:
            number += 1
            selected = (context.index(first), context.index(last))
            group_text = " ".join(w.text for w in context_words[selected[0]:selected[1] + 1])
            confidence = min(w.confidence for w in context_words[selected[0]:selected[1] + 1])
            offers = {}
            for model, reading in readings:
                offer = fix.suggestion_from(reading, context_words, *selected)
                if offer is None:
                    continue
                index, count, new_words = offer
                key = (index, count, tuple(fix.word_key(w.text) for w in new_words))
                entry = offers.setdefault(key, {"now": " ".join(w.text for w in context_words[index:index + count]),
                                                "offer": " ".join(w.text for w in new_words), "models": []})
                entry["models"].append(model)
                per_model[model] += 1
            # Shown with up to 6 words around the group, also for a whole line.
            low, high = max(0, selected[0] - 6), min(len(context_words), selected[1] + 7)
            line = " ".join(w.text for w in context_words[low:high])
            print(f"\n[{number}] {group_text!r} ({confidence:.2f})  in: {line}")
            if not offers:
                print("    (no offer)")
            for entry in offers.values():
                print(f"    {'+'.join(entry['models']):12s} {entry['now']!r} -> {entry['offer']!r}")
                found.append({"group": group_text, "confidence": round(confidence, 3), "context": line, **entry})
    spent = time.perf_counter() - search_started
    agreed = sum(1 for entry in found if len(entry["models"]) > 1)
    with_offer = len({entry["group"] for entry in found})
    print(f"\n{len(groups)} groups, {with_offer} with an offer, {len(found)} offers "
          f"({agreed} from two models); per model {per_model}")
    print(f"search {spent:.1f} s, {len(pieces)} readings (first {timings[0] if timings else 0:.1f} s incl. loads, "
          f"median {sorted(timings)[len(timings) // 2] if timings else 0:.2f} s)")
    if args.out:
        Path(args.out).write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
