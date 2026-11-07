"""Does a low word confidence point at the wrong words? (plan 03 B2)

    python experiments/confidence/word_confidence.py AUDIO [--whisper RESULT.json] [--show 40]

Transcribes AUDIO with RNNT and with CTC (the app's Transcriber, greedy) and keeps,
for every token, the probability the model gave it:
- RNNT: softmax of the joint network's output at the step that emitted the token;
- CTC: the frame's probability of the token (exp of the log-probability).
A word's confidence is the lowest probability among its tokens.

There is no reference text, so "disputed" stands in for "wrong": a word is disputed
when the other reading does not have it at that place (difflib over lower-case words
without punctuation). The other readings are CTC and, with --whisper, a Whisper result
from experiments/whisper/variants.py (its "chunks" texts). Prints, per confidence band,
how many words fall in it and how many of them are disputed, then the least sure words
with the words around them. Run from the repository root.
"""

import argparse
import difflib
import json
from pathlib import Path
import re
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app.engine import Transcriber  # noqa: E402

BANDS = (0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.97, 1.01)


def rnnt_decode_with_probabilities(head, encoded):
    """asr.RnntHead.decode, plus the probability of each emitted token."""
    encoder_part = encoded @ head.enc_w + head.enc_b
    h = np.zeros(head.hidden, np.float32)
    c = np.zeros(head.hidden, np.float32)
    h, c = head._lstm_step(np.zeros(head.hidden, np.float32), h, c)
    prediction_part = h @ head.pred_w + head.pred_b
    tokens = []
    for frame in range(encoder_part.shape[0]):
        for _ in range(head.max_symbols):
            logits = np.maximum(encoder_part[frame] + prediction_part, 0.0) @ head.out_w + head.out_b
            token = int(logits.argmax())
            if token == head.blank_id:
                break
            probabilities = np.exp(logits - logits.max())
            tokens.append((token, frame, probabilities / probabilities.sum()))
            h, c = head._lstm_step(head.embed[token], h, c)
            prediction_part = h @ head.pred_w + head.pred_b
    return tokens


def ctc_decode_with_probabilities(log_probs, blank_id):
    best = log_probs.argmax(axis=-1)
    keep = best != blank_id
    keep[1:] &= best[1:] != best[:-1]
    frames = np.nonzero(keep)[0]
    return [(int(best[f]), int(f), np.exp(log_probs[f])) for f in frames]


VARIANT = "raw"


def letters(piece):
    """A vocabulary piece without punctuation and case; the word-start mark stays."""
    return ("▁" if piece.startswith("▁") else "") + "".join(ch for ch in piece.lower() if ch.isalnum())


def token_probability(model, token, distribution):
    """The probability of one emitted token under VARIANT, or None to skip the token.
    raw: as the model gave it; noblank: renormalised without blank;
    letters: noblank, punctuation tokens skipped, pieces that differ only in case or
    punctuation counted together."""
    p = distribution / (1.0 - distribution[model.blank_id]) if VARIANT != "raw" else distribution
    if VARIANT != "letters":
        return float(p[token])
    key = letters(model.vocab[token])
    if key in ("", "▁"):
        return None
    group = model.letter_groups.setdefault(key, [i for i, piece in enumerate(model.vocab)
                                                  if i != model.blank_id and letters(piece) == key])
    return float(p[group].sum())


def words_with_confidence(model, tokens, offset):
    """[(text, start, confidence)]: model.words() on the tokens, each word's confidence
    the lowest probability among the tokens that fall inside its frames."""
    if not hasattr(model, "letter_groups"):
        model.letter_groups = {}
    words = model.words([(t, f) for t, f, _ in tokens], offset)
    result, index = [], 0
    for word in words:
        lowest = 1.0
        while index < len(tokens) and offset + tokens[index][1] * model.frame_seconds < word.end - 1e-6:
            if model.vocab[tokens[index][0]].replace("▁", "").strip():
                p = token_probability(model, tokens[index][0], tokens[index][2])
                if p is not None:
                    lowest = min(lowest, p)
            index += 1
        result.append((word.text, word.start, lowest))
    return result


def run(audio, key):
    """Transcribe with one model -> (model, [(tokens with distributions, offset seconds)])."""
    transcriber = Transcriber(key, device="auto")
    model = transcriber.asr
    pieces = []
    original_segment = transcriber._segment

    def segment(features, start, end):
        if model.kind == "rnnt":
            tokens = rnnt_decode_with_probabilities(model.head, features)
        else:
            tokens = ctc_decode_with_probabilities(features, model.blank_id)
        pieces.append((tokens, start / 16000))
        return original_segment(features, start, end)

    transcriber._segment = segment
    transcriber.transcribe(audio)
    return model, pieces


def all_words(model, pieces):
    return [word for tokens, offset in pieces for word in words_with_confidence(model, tokens, offset)]


def key(text):
    return re.sub(r"[^\w]", "", text.lower().replace("ё", "е"))


def disputed(words, other_texts):
    """Set of indexes of words that the other reading does not have at that place."""
    mine = [key(text) for text, _, _ in words]
    theirs = [key(text) for text in other_texts]
    matched = set()
    for block in difflib.SequenceMatcher(None, mine, theirs, autojunk=False).get_matching_blocks():
        matched.update(range(block.a, block.a + block.size))
    return {index for index in range(len(mine)) if index not in matched}


def report(name, words, against):
    print(f"\n=== {name}: {len(words)} words")
    for other_name, other in against.items():
        bad = disputed(words, other)
        print(f"  disputed by {other_name}: {len(bad)} ({100 * len(bad) / max(1, len(words)):.1f} %)")
        print("    band        words   share   disputed")
        for low, high in zip(BANDS, BANDS[1:]):
            inside = [i for i, (_, _, p) in enumerate(words) if low <= p < high]
            hits = sum(1 for i in inside if i in bad)
            print(f"    {low:.2f}-{min(high, 1):.2f}  {len(inside):6d}  {100 * len(inside) / max(1, len(words)):5.1f} %"
                  f"  {100 * hits / max(1, len(inside)):5.1f} %")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--whisper", help="a variants.py result JSON for the same audio")
    parser.add_argument("--show", type=int, default=40)
    parser.add_argument("--variant", choices=("raw", "noblank", "letters", "all"), default="all")
    args = parser.parse_args()

    rnnt_model, rnnt_pieces = run(args.audio, "RNNT")
    ctc_model, ctc_pieces = run(args.audio, "CTC")
    whisper = None
    if args.whisper:
        data = json.loads(Path(args.whisper).read_text(encoding="utf-8"))
        whisper = " ".join(chunk["text"] for chunk in data["chunks"]).split()
    variants = ("raw", "noblank", "letters") if args.variant == "all" else (args.variant,)
    for variant in variants:
        globals()["VARIANT"] = variant
        rnnt, ctc = all_words(rnnt_model, rnnt_pieces), all_words(ctc_model, ctc_pieces)
        print(f"\n######## variant {variant}")
        report("RNNT", rnnt, {"CTC": [text for text, _, _ in ctc], **({"Whisper": whisper} if whisper else {})})
        report("CTC", ctc, {"RNNT": [text for text, _, _ in rnnt], **({"Whisper": whisper} if whisper else {})})

    print(f"\n=== RNNT ({variants[-1]}): the {args.show} least sure words")
    order = sorted(range(len(rnnt)), key=lambda i: rnnt[i][2])[:args.show]
    bad = disputed(rnnt, whisper or [text for text, _, _ in ctc])
    for i in sorted(order):
        around = " ".join(text for text, _, _ in rnnt[max(0, i - 3):i])
        after = " ".join(text for text, _, _ in rnnt[i + 1:i + 4])
        mark = "x" if i in bad else " "
        print(f"  {rnnt[i][1]:7.1f}s {rnnt[i][2]:.2f} {mark} {around} [{rnnt[i][0]}] {after}")


if __name__ == "__main__":
    main()
