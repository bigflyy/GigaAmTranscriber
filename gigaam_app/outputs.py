"""Write a Transcript as plain text, timestamped text, Markdown, SRT subtitles or JSON."""

from dataclasses import asdict
import datetime
import json
import os
from pathlib import Path
import re
import tempfile

from .catalog import model_title
from .paths import replace_file

FORMATS = ("txt", "timestamps", "md", "srt", "json")
DEFAULT_FORMATS = ("txt", "timestamps")

# Subtitle cues: split at these limits, preferring sentence ends.
CUE_MAX_SECONDS = 6.0
CUE_MAX_CHARS = 84
CUE_BREAK_GAP = 1.0  # a pause this long between words always starts a new cue

# Markdown sections: a new "## MM:SS" heading after about a minute of text, or earlier
# at a long pause once the section has some text.
SECTION_SECONDS = 60.0
SECTION_PAUSE = 5.0
SECTION_MIN_SECONDS = 15.0


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


def short_clock(seconds):
    """M:SS, or H:MM:SS from one hour on; whole seconds, rounded down."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def section_clock(seconds, with_hours=False):
    """Section heading time: MM:SS (00:00, 01:12); H:MM:SS (0:01:12) in files of an hour or more,
    so all headings of one file look alike."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if with_hours or hours else f"{minutes:02d}:{secs:02d}"


# Characters that would turn plain words into Markdown markup.
_MARKUP = re.compile(r"([\\`*\[\]<>])")
# An underscore starts or ends emphasis only at a word edge; inside a word (my_lecture) it is plain.
_EDGE_UNDERSCORE = re.compile(r"(?<!\w)_|_(?!\w)")
# A paragraph starting like this would become a heading, quote, list or rule.
_BLOCK_START = re.compile(r"^([#>+=-])")
# "1. " or "1) " at the start would become a numbered list; the dot or bracket gets the backslash
# (a backslash before a digit is not an escape in Markdown).
_LIST_NUMBER = re.compile(r"^(\d+)([.)])(?=\s|$)")


def markdown_escape(text):
    """Escape a line of plain text so a Markdown viewer shows it as it is."""
    text = _MARKUP.sub(r"\\\1", text)
    text = _EDGE_UNDERSCORE.sub(r"\\_", text)
    text = _BLOCK_START.sub(r"\\\1", text)
    return _LIST_NUMBER.sub(r"\1\\\2", text)


def markdown_sections(transcript):
    """Group segments into [(start seconds, text)] sections of about a minute each."""
    sections = []
    current = []
    for segment in transcript.segments:
        if not segment.text:
            continue
        if current:
            length = segment.start - current[0].start
            pause = segment.start - current[-1].end
            if length >= SECTION_SECONDS or (pause >= SECTION_PAUSE and length >= SECTION_MIN_SECONDS):
                sections.append(current)
                current = []
        current.append(segment)
    if current:
        sections.append(current)
    return [(section[0].start, " ".join(segment.text for segment in section)) for section in sections]


def markdown_text(transcript, today=None):
    """The file name as the title, a line with the date, length and model, then the text
    in sections of about a minute, each under its start time (owner's choice, 2026-11-06)."""
    today = today or datetime.date.today()
    info = [today.isoformat()]
    if transcript.audio_seconds:
        info.append(short_clock(transcript.audio_seconds))
    if transcript.model:
        info.append(model_title(transcript.model))
    lines = [f"# {markdown_escape(Path(transcript.source).name)}", "",
             "*" + " \u00b7 ".join(markdown_escape(part) for part in info) + "*"]  # middle dot between parts
    sections = markdown_sections(transcript)
    with_hours = max(transcript.audio_seconds, sections[-1][0] if sections else 0) >= 3600
    for start, text in sections:
        lines += ["", f"## {section_clock(start, with_hours)}", "", markdown_escape(text)]
    return "\n".join(lines) + "\n"


RENDERERS = {"txt": plain_text, "timestamps": timestamped_text, "md": markdown_text, "srt": srt_text,
             "json": json_text}


def output_paths(source, formats, out_dir=None):
    """Default names beside the source: name-transcript.txt, name-transcript-timestamps.txt, ..."""
    source = Path(source)
    folder = Path(out_dir) if out_dir else source.parent
    stem = source.stem + "-transcript"
    names = {"txt": stem + ".txt", "timestamps": stem + "-timestamps.txt",
             "md": stem + ".md", "srt": stem + ".srt", "json": stem + ".json"}
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
            replace_file(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    return list(paths.values())
