"""Whisper's word confidence against the GigaAM readings (plan 03 B2b).

    python experiments/confidence/whisper_confidence.py AUDIO [--terms "..."] [--show 40]

Transcribes AUDIO with Whisper (the app's Transcriber: VAD chunks, greedy) and with
RNNT and CTC. A Whisper word's confidence is the lowest token probability among its
tokens with letters (whisper_model.words_from_tokens), on the GigaAM scale since
whisper_model.WHISPER_SCALE (the first run, before that scale, gave raw probabilities). Prints, per confidence band, how
many Whisper words fall in it and how many of them the GigaAM readings do not have at
that place, then the least sure words. Run from the repository root.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app.engine import Transcriber  # noqa: E402
from word_confidence import BANDS, disputed  # noqa: E402


def words_of(key, audio, terms=None):
    transcriber = Transcriber(key, device="auto")
    if terms:
        original = transcriber.asr.encode
        transcriber.asr.encode = lambda pieces, should_cancel=None: original(pieces, should_cancel, prompt=terms)
    result = transcriber.transcribe(audio)
    print(f"{key}: {result.elapsed_seconds:.1f} s on {transcriber.device_label}")
    return [(w.text, w.start, 1.0 if w.confidence is None else w.confidence)
            for segment in result.segments for w in segment.words]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--terms")
    parser.add_argument("--show", type=int, default=40)
    args = parser.parse_args()
    whisper = words_of("Whisper", args.audio, args.terms)
    others = {key: [text for text, _, _ in words_of(key, args.audio)] for key in ("RNNT", "CTC")}
    print(f"\n=== Whisper: {len(whisper)} words")
    for name, other in others.items():
        bad = disputed(whisper, other)
        print(f"  disputed by {name}: {len(bad)} ({100 * len(bad) / max(1, len(whisper)):.1f} %)")
        print("    band        words   share   disputed")
        for low, high in zip(BANDS, BANDS[1:]):
            inside = [i for i, (_, _, p) in enumerate(whisper) if low <= p < high]
            hits = sum(1 for i in inside if i in bad)
            print(f"    {low:.2f}-{min(high, 1):.2f}  {len(inside):6d}  {100 * len(inside) / max(1, len(whisper)):5.1f} %"
                  f"  {100 * hits / max(1, len(inside)):5.1f} %")
    both = disputed(whisper, others["RNNT"]) & disputed(whisper, others["CTC"])
    print(f"\n=== Whisper: the {args.show} least sure words (x: neither RNNT nor CTC has it)")
    order = sorted(range(len(whisper)), key=lambda i: whisper[i][2])[:args.show]
    for i in sorted(order):
        before = " ".join(text for text, _, _ in whisper[max(0, i - 3):i])
        after = " ".join(text for text, _, _ in whisper[i + 1:i + 4])
        print(f"  {whisper[i][1]:7.1f}s {whisper[i][2]:.2f} {'x' if i in both else ' '} {before} [{whisper[i][0]}] {after}")


if __name__ == "__main__":
    main()
