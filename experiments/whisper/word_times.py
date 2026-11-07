"""Compare the word times of two app_engine.py runs (for example GigaAM and Whisper).

    python experiments/whisper/word_times.py REFERENCE.json OTHER.json

Words are matched where both texts agree (lower case, punctuation dropped, difflib on
the word lists). For the matched words it prints how far the start and end times lie
apart: GigaAM's times come from the acoustic frames of its encoder (40 ms), so they
are a fair reference for Whisper's heuristic token times.
"""

import difflib
import json
from pathlib import Path
import re
import statistics
import sys

WORD = re.compile(r"[0-9a-zа-яё]+")


def load_words(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    found = []
    for chunk in data["chunks"]:
        for start, end, text in chunk["words"]:
            key = "".join(WORD.findall(text.lower().replace("ё", "е")))
            if key:
                found.append((key, start, end))
    return found


def percentile(values, share):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(share * len(ordered)))]


def main():
    reference, other = load_words(sys.argv[1]), load_words(sys.argv[2])
    matcher = difflib.SequenceMatcher(None, [w[0] for w in reference], [w[0] for w in other], autojunk=False)
    starts, ends = [], []
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            a, b = reference[block.a + offset], other[block.b + offset]
            starts.append(b[1] - a[1])
            ends.append(b[2] - a[2])
    print(f"matched {len(starts)} of {len(reference)} reference words")
    for name, values in (("start", starts), ("end", ends)):
        absolute = [abs(v) for v in values]
        print(f"{name}: median offset {statistics.median(values):+.3f} s, median |diff| "
              f"{statistics.median(absolute):.3f} s, 90% within {percentile(absolute, 0.9):.3f} s, "
              f"over 0.5 s: {sum(v > 0.5 for v in absolute)} ({sum(v > 0.5 for v in absolute) / len(values):.1%})")


if __name__ == "__main__":
    main()
