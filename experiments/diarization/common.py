"""Shared helpers for the diarization experiments (plan 07 Stage A).

Audio is always 16 kHz mono float32, decoded with ffmpeg. Results are RTTM
files: one "SPEAKER <file> 1 <start> <duration> <NA> <NA> <speaker> <NA> <NA>"
line per speech segment, the format the public test sets use.
"""
import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000


def load_audio(path):
    """Decode any audio or video file to 16 kHz mono float32 with ffmpeg."""
    command = ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
               "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"]
    raw = subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def write_rttm(path, file_id, segments):
    """Write [(start, end, speaker)] as an RTTM file."""
    lines = []
    for start, end, speaker in sorted(segments):
        if end > start:
            lines.append(f"SPEAKER {file_id} 1 {start:.3f} {end - start:.3f} <NA> <NA> {speaker} <NA> <NA>")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_rttm(path):
    """Read an RTTM file as [(start, end, speaker)]."""
    segments = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0] == "SPEAKER":
            start, duration = float(fields[3]), float(fields[4])
            segments.append((start, start + duration, fields[7]))
    return segments


def speaker_at(segments, start, end):
    """Return the speaker with the most time inside [start, end], or None.

    This is how a word gets its speaker: the word's span is compared with
    every segment and the speaker that covers most of it wins. A word in a
    gap between segments takes the nearest segment's speaker.
    """
    overlap = {}
    for seg_start, seg_end, speaker in segments:
        shared = min(end, seg_end) - max(start, seg_start)
        if shared > 0:
            overlap[speaker] = overlap.get(speaker, 0.0) + shared
    if overlap:
        return max(overlap, key=overlap.get)
    if not segments:
        return None
    middle = (start + end) / 2
    nearest = min(segments, key=lambda seg: min(abs(seg[0] - middle), abs(seg[1] - middle)))
    return nearest[2]
