"""Write a Transcript as plain text, timestamped text, SRT subtitles or JSON."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile

FORMATS = ("txt", "timestamps", "srt", "json")
DEFAULT_FORMATS = ("txt", "timestamps")

# Subtitle cues: split at these limits, preferring sentence ends.
CUE_MAX_SECONDS = 6.0
CUE_MAX_CHARS = 84
CUE_BREAK_GAP = 1.0  # a pause this long between words always starts a new cue


def clock(seconds, millis_separator="."):
    """HH:MM:SS.mmm, or MM:SS.mmm below one hour (SRT always uses the full form)."""
    total_ms = int(round(seconds * 1000))
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    if hours or millis_separator == ",":
        return f"{hours:02d}:{minutes:02d}:{secs:02d}{millis_separator}{ms:03d}"
    return f"{minutes:02d}:{secs:02d}{millis_separator}{ms:03d}"


def plain_text(transcript):
    return "".join(segment.text + "\n" for segment in transcript.segments if segment.text)


def timestamped_text(transcript):
    return "".join(f"[{clock(segment.start)} - {clock(segment.end)}] {segment.text}\n"
                   for segment in transcript.segments if segment.text)


def subtitle_cues(transcript):
    """Group words into short cues: [(start, end, text)]."""
    cues = []
    for segment in transcript.segments:
        current = []
        for word in segment.words:
            if current:
                text_length = sum(len(w.text) + 1 for w in current) + len(word.text)
                too_long = word.end - current[0].start > CUE_MAX_SECONDS or text_length > CUE_MAX_CHARS
                paused = word.start - current[-1].end > CUE_BREAK_GAP
                sentence_end = current[-1].text[-1:] in ".?!" and word.end - current[0].start > 1.5
                if too_long or paused or sentence_end:
                    cues.append(current)
                    current = []
            current.append(word)
        if current:
            cues.append(current)
    return [(cue[0].start, cue[-1].end, " ".join(w.text for w in cue)) for cue in cues]


def srt_text(transcript):
    blocks = []
    for number, (start, end, text) in enumerate(subtitle_cues(transcript), 1):
        blocks.append(f"{number}\n{clock(start, ',')} --> {clock(end, ',')}\n{text}\n")
    return "\n".join(blocks)


def json_text(transcript):
    data = asdict(transcript)
    data["text"] = transcript.text
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


RENDERERS = {"txt": plain_text, "timestamps": timestamped_text, "srt": srt_text, "json": json_text}


def output_paths(source, formats, out_dir=None):
    """Default names beside the source: name-transcript.txt, name-transcript-timestamps.txt, ..."""
    source = Path(source)
    folder = Path(out_dir) if out_dir else source.parent
    stem = source.stem + "-transcript"
    names = {"txt": stem + ".txt", "timestamps": stem + "-timestamps.txt",
             "srt": stem + ".srt", "json": stem + ".json"}
    return {fmt: folder / names[fmt] for fmt in formats}


def write_outputs(transcript, formats=DEFAULT_FORMATS, out_dir=None):
    """Write the chosen formats atomically and return their paths."""
    paths = output_paths(transcript.source, formats, out_dir)
    source = Path(transcript.source).resolve()
    for fmt, path in paths.items():
        if path.resolve() == source:
            raise ValueError(f"Refusing to overwrite the source file: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file first so a crash never leaves half a transcript.
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(RENDERERS[fmt](transcript))
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    return list(paths.values())
