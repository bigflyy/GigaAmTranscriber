"""Write a Transcript as plain text, timestamped text, Markdown, SRT subtitles, JSON,
or text for an LLM (doubtful words marked).

When speakers were looked for (plan 07, Transcript.speakers), every format names them:
a new paragraph at each change of speaker starts with "Name: ", as in the window; the
timestamped text names the speaker on every line, subtitles on the first cue of a turn.
"""

from dataclasses import asdict, dataclass
import datetime
import json
import os
from pathlib import Path
import re
import tempfile

from .catalog import model_title
from .paths import replace_file

FORMATS = ("txt", "timestamps", "md", "srt", "json", "llm")
DEFAULT_FORMATS = ("txt", "timestamps")

# Subtitle cues: split at these limits, preferring sentence ends.
CUE_MAX_SECONDS = 6.0
CUE_MAX_CHARS = 84
CUE_BREAK_GAP = 1.0  # a pause this long between words always starts a new cue

# Text for an LLM: a word below this confidence gets a mark (the window's dotted threshold).
LLM_DOUBT_BELOW = 0.97
# Punctuation that stays after the mark: "слово[?66%]," rather than "слово,[?66%]".
TRAILING_PUNCTUATION = re.compile(r"^(.*?)([.,!?;:\u00bb\")\]]*)$", re.S)

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


@dataclass
class Part:
    """A line of the transcript, or a piece of one where the speaker changes inside it."""
    start: float
    end: float
    text: str
    words: list
    speaker: int = None    # index into Transcript.speakers; None without speakers
    new_turn: bool = False  # a different speaker starts here (always False without speakers)


def speaker_name(transcript, index):
    """The name of speaker `index` ("Говорящий 2" when the list has no name for it)."""
    names = transcript.speakers or []
    return names[index] if 0 <= index < len(names) and names[index] else f"Говорящий {index + 1}"


def line_parts(transcript):
    """The lines with text, as Parts. Without speakers one Part per line. With speakers a
    line is cut where the speaker of its words changes; a word without a speaker (text typed
    where there was no neighbour) stays with the speaker before it."""
    parts = []
    with_speakers = bool(transcript.speakers)
    current = None
    for segment in transcript.segments:
        if not segment.text:
            continue
        pieces = []  # [speaker, new_turn, words]
        for word in segment.words if with_speakers else ():
            if word.speaker is not None and word.speaker != current:
                current = word.speaker
                pieces.append([current, True, []])
            elif not pieces:
                pieces.append([current, False, []])
            pieces[-1][2].append(word)
        if len(pieces) <= 1:
            speaker, new_turn = (pieces[0][0], pieces[0][1]) if pieces else (current if with_speakers else None, False)
            parts.append(Part(segment.start, segment.end, segment.text, list(segment.words), speaker, new_turn))
            continue
        for index, (speaker, new_turn, words) in enumerate(pieces):
            start = segment.start if index == 0 else words[0].start
            end = segment.end if index == len(pieces) - 1 else words[-1].end
            parts.append(Part(start, end, " ".join(word.text for word in words), words, speaker, new_turn))
    return parts


def turn_lines(transcript, render, label=lambda name: f"{name}: "):
    """Text lines with a speaker's name at each new turn, after a blank line (as the window
    shows it); render(part) gives a part's own text."""
    lines = []
    for part in line_parts(transcript):
        text = render(part)
        if part.new_turn:
            if lines:
                lines.append("")
            text = label(speaker_name(transcript, part.speaker)) + text
        lines.append(text)
    return lines


def plain_text(transcript):
    if not transcript.speakers:
        return "".join(segment.text + "\n" for segment in transcript.segments if segment.text)
    return "".join(line + "\n" for line in turn_lines(transcript, lambda part: part.text))


def timestamped_text(transcript):
    """[start - end] text per line; with speakers every line names its speaker."""
    lines = []
    for part in line_parts(transcript):
        name = f"{speaker_name(transcript, part.speaker)}: " if part.speaker is not None else ""
        lines.append(f"[{clock(part.start)} - {clock(part.end)}] {name}{part.text}\n")
    return "".join(lines)


def subtitle_cues(transcript):
    """Group words into short cues: [(start, end, text)]. A cue never holds two speakers;
    the first cue of a speaker's turn starts with the name."""
    cues = []  # (words, name or "")
    for part in line_parts(transcript):
        current = []
        name = f"{speaker_name(transcript, part.speaker)}: " if part.new_turn else ""
        for word in part.words:
            if current:
                text_length = sum(len(w.text) + 1 for w in current) + len(word.text)
                too_long = word.end - current[0].start > CUE_MAX_SECONDS or text_length > CUE_MAX_CHARS
                paused = word.start - current[-1].end > CUE_BREAK_GAP
                sentence_end = current[-1].text[-1:] in ".?!" and word.end - current[0].start > 1.5
                if too_long or paused or sentence_end:
                    cues.append((current, name))
                    current, name = [], ""
            current.append(word)
        if current:
            cues.append((current, name))
    return [(cue[0].start, cue[-1].end, name + " ".join(w.text for w in cue)) for cue, name in cues]


def srt_text(transcript):
    blocks = []
    for number, (start, end, text) in enumerate(subtitle_cues(transcript), 1):
        blocks.append(f"{number}\n{clock(start, ',')} --> {clock(end, ',')}\n{text}\n")
    return "\n".join(blocks)


def json_text(transcript):
    """The whole transcript as JSON: segments with word times and, where known, each
    word's confidence (0..1, how sure the model was; left out when unknown) and speaker
    (an index into "speakers", the names; both left out when speakers were not looked for)."""
    data = asdict(transcript)
    data.pop("suggestions_searched", None)  # the window's state (plan 06), not part of the text
    data.pop("speakers_found", None)        # the window's hint (plan 07)
    if data.get("speakers") is None:
        data.pop("speakers", None)
    for segment in data["segments"]:
        for word in segment["words"]:
            if word.get("confidence") is None:
                word.pop("confidence", None)
            if word.get("speaker") is None:
                word.pop("speaker", None)
            word.pop("suggestions", None)  # the window's offers (plan 06), not part of the text
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
    """Group the lines into [(start seconds, paragraphs)] sections of about a minute each.
    Without speakers a section is one paragraph of text; with speakers a paragraph per turn,
    as (name or None, text): a section that starts inside a turn repeats no name."""
    sections = []
    current = []
    for part in line_parts(transcript):
        if current:
            length = part.start - current[0].start
            pause = part.start - current[-1].end
            if length >= SECTION_SECONDS or (pause >= SECTION_PAUSE and length >= SECTION_MIN_SECONDS):
                sections.append(current)
                current = []
        current.append(part)
    if current:
        sections.append(current)
    result = []
    for section in sections:
        paragraphs = []
        for part in section:
            if part.new_turn or not paragraphs:
                name = speaker_name(transcript, part.speaker) if part.new_turn else None
                paragraphs.append((name, [part.text]))
            else:
                paragraphs[-1][1].append(part.text)
        result.append((section[0].start, [(name, " ".join(texts)) for name, texts in paragraphs]))
    return result


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
    for start, paragraphs in sections:
        lines += ["", f"## {section_clock(start, with_hours)}"]
        for name, text in paragraphs:
            label = f"**{markdown_escape(name)}:** " if name else ""
            lines += ["", label + markdown_escape(text)]
    return "\n".join(lines) + "\n"


def marked_word(word, doubt_below):
    """A word as text, with [?NN%] (the model's confidence) when it is below doubt_below."""
    if word.confidence is None or word.confidence >= doubt_below:
        return word.text
    body, tail = TRAILING_PUNCTUATION.match(word.text).groups()
    if not body:
        return word.text
    return f"{body}[?{round(word.confidence * 100)}%]{tail}"


def versions_line(words, transcript_title, doubt_below):
    """One line of the llm text. Where another model heard the words differently (offers kept
    on the first word, plan 06), both versions are given:
    {GigaAM v3 RNNT: Tullz[?60%] Colling | Whisper large-v3-turbo (q5_0): Tools Calling}.
    Returns (line, number of places with versions)."""
    parts, places, index = [], 0, 0
    while index < len(words):
        offers = words[index].suggestions or []
        if not offers:
            parts.append(marked_word(words[index], doubt_below))
            index += 1
            continue
        # The span the offers replace; an offer never reaches past its line (fix.doubt_groups).
        span = min(max(offer["count"] for offer in offers), len(words) - index)
        own = " ".join(marked_word(word, doubt_below) for word in words[index:index + span])
        versions = [f"{transcript_title}: {own}"]
        for offer in offers:
            # A shorter offer keeps the rest of the span from the text, so every version
            # covers the same words.
            text = " ".join([item[2] for item in offer["words"]] +
                            [word.text for word in words[index + offer["count"]:index + span]])
            names = ", ".join(model_title(model) for model in offer["models"])
            versions.append(f"{names}: {text}")
        parts.append("{" + " | ".join(versions) + "}")
        places += 1
        index += span
    return " ".join(parts), places


def llm_text(transcript, doubt_below=LLM_DOUBT_BELOW):
    """Text to paste into a chat with an LLM (plan 03, owner's idea 2026-11-08): a short note
    on how it was made and what the marks mean, then one paragraph per speech fragment with
    doubtful words marked as слово[?66%]. The model can then check exactly those words
    against the sentence around them. Where another model heard a place differently
    (suggested fixes, plan 06), both versions are given in {...} (owner 2026-11-08)."""
    words = [word for segment in transcript.segments for word in segment.words]
    marked = sum(1 for word in words if word.confidence is not None and word.confidence < doubt_below)
    title = model_title(transcript.model) if transcript.model else "Основная модель"
    made_by = f" (модель {title})" if transcript.model else ""
    places = 0

    def render(part):
        nonlocal places
        if not part.words:
            return part.text
        line, found = versions_line(part.words, title, doubt_below)
        places += found
        return line
    body = turn_lines(transcript, render)
    lines = [f"Автоматическая расшифровка речи{made_by}. Слова, в которых модель распознавания "
             "не уверена, отмечены так: слово[?66%], где число - её уверенность в слове. "
             "Эти слова могли быть распознаны неверно. Но весь текст получен распознаванием речи, "
             "поэтому ошибки возможны и в неотмеченных словах: в именах, терминах, иностранных "
             "словах, окончаниях и знаках препинания."]  # owner 2026-11-08
    if places:
        other = next(model_title(word.suggestions[0]["models"][0]) for word in words if word.suggestions)
        lines.append("Места, которые другая модель распознала иначе, даны в нескольких версиях: "
                     f"{{{title}: как услышала она | {other}: как услышала другая модель}}. "
                     "Первая версия - основной текст. Выберите версию, которая лучше подходит по "
                     "смыслу, или исправьте её: правы могут быть обе модели или ни одна.")
    if transcript.speakers:
        lines.append("Текст разделён по говорящим: реплика начинается с имени и двоеточия. Говорящие "
                     "определены автоматически по голосу, поэтому граница реплики или говорящий "
                     "иногда указаны неверно.")
    lines.append(f"Отмечено слов: {marked} из {len(words)}." +
                 (f" Мест с разными версиями: {places}." if places else ""))
    return "\n".join(lines + [""] + body) + "\n"


RENDERERS = {"txt": plain_text, "timestamps": timestamped_text, "md": markdown_text, "srt": srt_text,
             "json": json_text, "llm": llm_text}


def output_paths(source, formats, out_dir=None):
    """Default names beside the source: name-transcript.txt, name-transcript-timestamps.txt, ..."""
    source = Path(source)
    folder = Path(out_dir) if out_dir else source.parent
    stem = source.stem + "-transcript"
    names = {"txt": stem + ".txt", "timestamps": stem + "-timestamps.txt",
             "md": stem + ".md", "srt": stem + ".srt", "json": stem + ".json", "llm": stem + "-llm.txt"}
    return {fmt: folder / names[fmt] for fmt in formats}


def write_outputs(transcript, formats=DEFAULT_FORMATS, out_dir=None, doubt_below=LLM_DOUBT_BELOW):
    """Write the chosen formats atomically and return their paths.
    doubt_below: the confidence below which the llm format marks a word."""
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
                stream.write(llm_text(transcript, doubt_below) if fmt == "llm" else RENDERERS[fmt](transcript))
            replace_file(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    return list(paths.values())
