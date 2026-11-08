"""Suggested fixes for doubtful words (plan 06 A5), measured without the window.

    python experiments/suggest/suggest_check.py AUDIO [--model RNNT] [--terms "..."]
        [--below 0.97] [--out FILE.json]

Transcribes AUDIO with --model, groups its doubtful words (confidence below --below) the
way the window does (fix.doubt_groups), recognises each group again with the other installed
models through the worker's "suggest" job, and prints every offer: the current words, the
offered words and which models offered them. Ends with counts and times. --out keeps the
offers as JSON for judging by hand. Uses the normal model folders. Run from the repository root.
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--model", default="RNNT")
    parser.add_argument("--terms", default="")
    parser.add_argument("--below", type=float, default=0.97)
    parser.add_argument("--out")
    args = parser.parse_args()

    events = queue.Queue()
    worker = Worker(events)
    worker.engine_key = (args.model, "auto", 0)
    worker.engine = Transcriber(args.model, device="auto")
    started = time.perf_counter()
    transcript = worker.engine.transcribe(args.audio)
    print(f"transcribed in {time.perf_counter() - started:.1f} s")
    segments = transcript.segments
    words_total = sum(len(segment.words) for segment in segments)
    groups = fix.doubt_groups(segments, args.below)
    doubtful = sum(len(fix.positions_between(segments, a, b)) for a, b in groups)
    models = [key for key in ("RNNT", "CTC", "Whisper")
              if key != args.model and catalog.installed_folder(catalog.find(key))]
    print(f"{words_total} words, {len(groups)} groups ({doubtful} words incl. gaps), models {models}")

    found, per_model, timings = [], {model: 0 for model in models}, []
    search_started = time.perf_counter()
    for number, (first, last) in enumerate(groups, 1):
        context_first, context_last = fix.context_bounds(segments, first, last)
        context = fix.positions_between(segments, context_first, context_last)
        context_words = [fix.word_at(segments, position) for position in context]
        selected = (context.index(first), context.index(last))
        windows = fix.search_windows(segments, context_first, context_last, transcript.audio_seconds)
        group_started = time.perf_counter()
        worker._reread(number, args.audio, windows, models, "auto", 0, "auto", args.terms or None, prefix="suggest")
        timings.append(time.perf_counter() - group_started)
        group_text = " ".join(w.text for w in context_words[selected[0]:selected[1] + 1])
        confidence = min(w.confidence for w in context_words[selected[0]:selected[1] + 1])
        offers = {}
        while not events.empty():
            event = events.get()
            if event[0] != "suggest_result" or event[3] is None:
                continue
            _, _, model, reading, _ = event
            offer = fix.suggestion_from(reading, context_words, *selected)
            if offer is None:
                continue
            index, count, new_words = offer
            key = (index, count, tuple(fix.word_key(w.text) for w in new_words))
            entry = offers.setdefault(key, {"now": " ".join(w.text for w in context_words[index:index + count]),
                                            "offer": " ".join(w.text for w in new_words), "models": []})
            entry["models"].append(model)
            per_model[model] += 1
        line = " ".join(w.text for w in context_words)
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
    print(f"search {spent:.1f} s (first group {timings[0] if timings else 0:.1f} s incl. loads, "
          f"median {sorted(timings)[len(timings) // 2] if timings else 0:.2f} s)")
    if args.out:
        Path(args.out).write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
