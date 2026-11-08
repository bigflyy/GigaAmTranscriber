"""Build speaker labels for a kremlin.ru event from its transcript and an ASR run.

The transcript names the speaker of every turn but has no times. The app's
own recognition (JSON with word times) has times but no speakers. Lining the
two word sequences up (difflib) gives each recognised word the speaker of
the transcript word it matches. Recognised words that match nothing take the
speaker of their neighbours when both neighbours agree; otherwise they stay
unknown ("?") and are left out of scoring.

Usage: python kremlin_labels.py TURNS.json ASR.json OUT_STEM
Writes:
  OUT_STEM.words.tsv  start, end, word, speaker ("?" when unknown)
  OUT_STEM.rttm       reference turns (labelled words joined across gaps < 1 s)
  OUT_STEM.uem        scored time: everything except spans of unknown words
  OUT_STEM.srt        subtitles "[speaker] words" to check the labels by ear
and prints how much of the recording got a label.
"""
import difflib
import json
import re
import sys
from pathlib import Path

MAX_JOIN_GAP = 1.0     # seconds: words of one speaker closer than this form one segment
CUE_SECONDS = 6.0      # longest subtitle cue


def normalise(word):
    """Lower case, ё as е, letters and digits only, so both texts compare equal."""
    return re.sub(r"[^0-9a-zа-я]", "", word.lower().replace("ё", "е"))


def transcript_words(turns):
    """Flatten the turns into [(normalised word, speaker)]."""
    words = []
    for speaker, text in turns:
        for token in text.split():
            key = normalise(token)
            if key:
                words.append((key, speaker))
    return words


def asr_words(data):
    """Read the app's JSON into [(start, end, text)]."""
    words = []
    for segment in data["segments"]:
        for word in segment["words"]:
            text = word.get("word") or word.get("text") or ""
            words.append((float(word["start"]), float(word["end"]), text))
    return words


def label(turns, recognised):
    """Return one speaker (or "?") per recognised word."""
    reference = transcript_words(turns)
    keys = [normalise(text) for _, _, text in recognised]
    matcher = difflib.SequenceMatcher(None, [k for k, _ in reference], keys, autojunk=False)
    speakers = ["?"] * len(recognised)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            speakers[block.b + offset] = reference[block.a + offset][1]
    # Fill unmatched words whose nearest labelled neighbours on both sides agree.
    filled = list(speakers)
    previous = None
    for index, speaker in enumerate(speakers):
        if speaker != "?":
            previous = speaker
            continue
        following = next((s for s in speakers[index + 1:] if s != "?"), None)
        if previous is not None and previous == following:
            filled[index] = previous
    return filled, matcher.ratio()


def segments_of(recognised, speakers):
    """Join consecutive words of one speaker into (start, end, speaker) segments."""
    segments = []
    for (start, end, _), speaker in zip(recognised, speakers):
        if speaker == "?":
            continue
        if segments and segments[-1][2] == speaker and start - segments[-1][1] < MAX_JOIN_GAP:
            segments[-1][1] = end
        else:
            segments.append([start, end, speaker])
    return segments


def unknown_spans(recognised, speakers):
    """Time spans covered by unknown words, widened to the neighbouring words."""
    spans = []
    for index, speaker in enumerate(speakers):
        if speaker != "?":
            continue
        start = recognised[index - 1][1] if index > 0 else 0.0
        end = recognised[index + 1][0] if index + 1 < len(recognised) else recognised[index][1]
        if spans and start <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return spans


def clock(seconds):
    """SRT time: HH:MM:SS,mmm."""
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def subtitles(recognised, speakers):
    """Cues of at most CUE_SECONDS, never mixing two speakers."""
    cues = []
    for (start, end, text), speaker in zip(recognised, speakers):
        if cues and cues[-1][2] == speaker and end - cues[-1][0] <= CUE_SECONDS and start - cues[-1][1] < MAX_JOIN_GAP:
            cues[-1][1] = end
            cues[-1][3].append(text)
        else:
            cues.append([start, end, speaker, [text]])
    blocks = []
    for number, (start, end, speaker, texts) in enumerate(cues, 1):
        blocks.append(f"{number}\n{clock(start)} --> {clock(end)}\n[{speaker}] {' '.join(texts)}\n")
    return "\n".join(blocks)


def main():
    turns = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    recognised = asr_words(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    stem = Path(sys.argv[3])
    file_id = stem.name
    speakers, ratio = label(turns, recognised)

    with open(f"{stem}.words.tsv", "w", encoding="utf-8") as out:
        for (start, end, text), speaker in zip(recognised, speakers):
            out.write(f"{start:.2f}\t{end:.2f}\t{text}\t{speaker}\n")
    segments = segments_of(recognised, speakers)
    Path(f"{stem}.rttm").write_text("".join(
        f"SPEAKER {file_id} 1 {s:.3f} {e - s:.3f} <NA> <NA> {spk} <NA> <NA>\n" for s, e, spk in segments),
        encoding="utf-8")
    # Scored time: from the first to the last word, minus the unknown spans.
    scored, cursor = [], max(0.0, recognised[0][0] - 0.5)
    for span_start, span_end in unknown_spans(recognised, speakers):
        if span_start > cursor:
            scored.append((cursor, span_start))
        cursor = max(cursor, span_end)
    scored.append((cursor, recognised[-1][1] + 0.5))
    Path(f"{stem}.uem").write_text("".join(f"{file_id} 1 {s:.3f} {e:.3f}\n" for s, e in scored if e > s),
                                   encoding="utf-8")
    Path(f"{stem}.srt").write_text(subtitles(recognised, speakers), encoding="utf-8")

    known = sum(speaker != "?" for speaker in speakers)
    names = sorted({speaker for speaker in speakers if speaker != "?"})
    print(f"{file_id}: {len(recognised)} words, {100 * known / len(recognised):.1f}% labelled, "
          f"text match {100 * ratio:.0f}%, {len(names)} speakers: {', '.join(names)}")


if __name__ == "__main__":
    main()
