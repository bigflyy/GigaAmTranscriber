"""Score RTTM results against reference RTTM files with pyannote.metrics.

Runs in an environment that has pyannote.metrics (no torch needed), for
example the owner's conda env cuda-torch2.

Usage: python score_der.py REF_DIR HYP_DIR [COLLAR] [--skip-overlap]
Each REF_DIR/<id>.rttm is compared with HYP_DIR/<id>.rttm; REF_DIR/<id>.uem,
when present, limits the scored time. Prints per-file DER with its parts
(missed speech, false alarm, speaker confusion) and the speaker counts.
Default: collar 0, overlap scored (the way pyannote reports its numbers).
"""
import sys
from pathlib import Path

from pyannote.core import Annotation, Segment, Timeline
from pyannote.metrics.diarization import DiarizationErrorRate


def load_rttm(path):
    """Read an RTTM file into a pyannote Annotation."""
    annotation = Annotation()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0] == "SPEAKER":
            start, duration = float(fields[3]), float(fields[4])
            annotation[Segment(start, start + duration)] = fields[7]
    return annotation


def load_uem(path):
    """Read a UEM file ("<id> 1 <start> <end>" per line) into a Timeline."""
    timeline = Timeline()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 4:
            timeline.add(Segment(float(fields[2]), float(fields[3])))
    return timeline


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ref_dir, hyp_dir = Path(args[0]), Path(args[1])
    collar = float(args[2]) if len(args) > 2 else 0.0
    metric = DiarizationErrorRate(collar=collar, skip_overlap="--skip-overlap" in sys.argv)
    print(f"{'file':<14}{'DER%':>7}{'miss%':>7}{'FA%':>7}{'conf%':>7}{'ref spk':>9}{'hyp spk':>9}")
    for ref_path in sorted(ref_dir.glob("*.rttm")):
        hyp_path = hyp_dir / ref_path.name
        if not hyp_path.exists():
            continue
        reference, hypothesis = load_rttm(ref_path), load_rttm(hyp_path)
        uem_path = ref_path.with_suffix(".uem")
        uem = load_uem(uem_path) if uem_path.exists() else None
        parts = metric(reference, hypothesis, uem=uem, detailed=True)
        total = parts["total"] or 1.0
        print(f"{ref_path.stem:<14}{100 * parts['diarization error rate']:7.1f}"
              f"{100 * parts['missed detection'] / total:7.1f}{100 * parts['false alarm'] / total:7.1f}"
              f"{100 * parts['confusion'] / total:7.1f}{len(reference.labels()):9d}{len(hypothesis.labels()):9d}")
    print(f"{'TOTAL':<14}{100 * abs(metric):7.1f}")


if __name__ == "__main__":
    main()
