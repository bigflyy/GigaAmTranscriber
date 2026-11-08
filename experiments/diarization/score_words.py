"""Word speaker error: the share of recognised words that get the wrong speaker.

This is what the app needs: every word of the transcript is given the
speaker that covers most of the word's time in the diarization result (as
the app will do it), and compared with the word's true speaker. System
speaker names (spk0, spk1, ...) are matched to the true names one to one so
that the most words agree (Hungarian method); a word whose system speaker has
no partner counts as wrong.

Usage: python score_words.py REF_DIR HYP_DIR
REF_DIR/<id>.words.tsv (from kremlin_labels.py) against HYP_DIR/<id>.rttm.
Words labelled "?" in the reference are skipped.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from common import read_rttm, speaker_at


def score(words_path, rttm_path):
    """Return (wrong words, scored words, true speaker count, system speaker count)."""
    segments = read_rttm(rttm_path)
    pairs = []
    for line in Path(words_path).read_text(encoding="utf-8").splitlines():
        start, end, _, truth = line.split("\t")
        if truth != "?":
            pairs.append((truth, speaker_at(segments, float(start), float(end)) or "none"))
    truths = sorted({t for t, _ in pairs})
    systems = sorted({s for _, s in pairs})
    counts = np.zeros((len(truths), len(systems)))
    for truth, system in pairs:
        counts[truths.index(truth), systems.index(system)] += 1
    rows, cols = linear_sum_assignment(-counts)
    right = counts[rows, cols].sum()
    found = len({s for _, _, s in segments})
    return len(pairs) - right, len(pairs), len(truths), found


def main():
    ref_dir, hyp_dir = Path(sys.argv[1]), Path(sys.argv[2])
    total_wrong = total_words = 0
    print(f"{'file':<10}{'wrong%':>8}{'words':>8}{'true spk':>10}{'found':>7}")
    for words_path in sorted(ref_dir.glob("*.words.tsv")):
        file_id = words_path.name[:-len(".words.tsv")]
        rttm_path = hyp_dir / f"{file_id}.rttm"
        if not rttm_path.exists():
            continue
        wrong, words, true_count, found = score(words_path, rttm_path)
        total_wrong += wrong
        total_words += words
        print(f"{file_id:<10}{100 * wrong / words:8.1f}{words:8d}{true_count:10d}{found:7d}")
    if total_words:
        print(f"{'TOTAL':<10}{100 * total_wrong / total_words:8.1f}{total_words:8d}")


if __name__ == "__main__":
    main()
