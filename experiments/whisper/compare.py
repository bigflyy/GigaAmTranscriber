"""Word-level comparison of a Whisper transcript with the GigaAM reference (plan 04 A4).

    python experiments/whisper/compare.py GIGAAM.json OTHER.json [--samples 15]

OTHER.json is either a chunk JSON (gigaam_ref.py / ort_whisper.py: {"chunks": [{"text"}]})
or whisper.cpp's own JSON (-oj: {"transcription": [{"text"}]}).

Both texts are normalised before comparing: lower case, "ё" -> "е", punctuation
dropped, hyphens split words. There is no human reference: "differ" means the two
models disagree, not that Whisper is wrong. Differences that involve digits are
counted apart, because Whisper writes "40" where GigaAM writes "сорок".
"""

import argparse
import difflib
import json
import re
from pathlib import Path

WORD = re.compile(r"[0-9a-zа-я]+")


def load_text(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "chunks" in data:
        return " ".join(chunk["text"] for chunk in data["chunks"]), data
    return " ".join(item["text"] for item in data["transcription"]), data


def words(text):
    return WORD.findall(text.lower().replace("ё", "е"))


def repeated_runs(tokens, n=3, times=4):
    """Places where the same n words repeat at least `times` in a row (a Whisper loop)."""
    found = []
    i = 0
    while i + n * times <= len(tokens):
        gram = tokens[i:i + n]
        count = 1
        while tokens[i + count * n:i + (count + 1) * n] == gram:
            count += 1
        if count >= times:
            found.append((i, " ".join(gram), count))
            i += count * n
        else:
            i += 1
    return found


def compare(reference_words, other_words):
    matcher = difflib.SequenceMatcher(a=reference_words, b=other_words, autojunk=False)
    ops = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    errors = digit_errors = 0
    for tag, i1, i2, j1, j2 in ops:
        size = max(i2 - i1, j2 - j1)
        errors += size
        if any(ch.isdigit() for w in reference_words[i1:i2] + other_words[j1:j2] for ch in w):
            digit_errors += size
    return ops, errors, digit_errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference")
    parser.add_argument("other")
    parser.add_argument("--samples", type=int, default=15)
    args = parser.parse_args()

    ref_text, _ = load_text(args.reference)
    other_text, other = load_text(args.other)
    ref_words, other_words = words(ref_text), words(other_text)
    ops, errors, digit_errors = compare(ref_words, other_words)
    loops = repeated_runs(other_words)
    long_chunks = sum(1 for c in other.get("chunks", []) if c.get("hit_max_length"))
    summary = {
        "reference_words": len(ref_words),
        "other_words": len(other_words),
        "differ_percent": round(100 * errors / max(1, len(ref_words)), 2),
        "differ_percent_without_digits": round(100 * (errors - digit_errors) / max(1, len(ref_words)), 2),
        "loops": [(gram, count) for _, gram, count in loops],
        "chunks_at_max_length": long_chunks,
    }
    print(json.dumps(summary, ensure_ascii=False))
    big = sorted(ops, key=lambda op: -max(op[2] - op[1], op[4] - op[3]))[:5]
    shown = sorted(set((ops[:: max(1, len(ops) // args.samples)][: args.samples] if args.samples else [])) | set(big if args.samples else []), key=lambda op: op[1])
    for tag, i1, i2, j1, j2 in shown:
        before = " ".join(ref_words[max(0, i1 - 4):i1])
        print(f"  ...{before} [G: {' '.join(ref_words[i1:i2]) or '-'} | W: {' '.join(other_words[j1:j2]) or '-'}] "
              f"{' '.join(ref_words[i2:i2 + 3])}...")


if __name__ == "__main__":
    main()
