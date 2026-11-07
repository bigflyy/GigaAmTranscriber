"""Fixing a selected part of a finished transcript (plan 03 Stage A).

The window lets the user select words in the text. This module turns such a
selection into a piece of audio and back into words:

- context: the piece also holds a few words before and after the selection (up to
  CONTEXT_SECONDS each side, context_bounds). Cut tightly at the selection, the models
  heard the ends of the neighbouring words ("Маш" for "наш") and wrote the part as a
  sentence of its own (a capital letter, a final period); with context they do not;
- where to cut: in the gaps outside the context words, at the quietest 10 ms of each
  gap (search_windows, quietest_point);
- recognising the piece again with one model (reread_piece), Whisper optionally with
  the user's terms as its prompt;
- keeping only the selected part of a reading (trim_reading): the reading is lined up
  word by word with the current text of the piece, and the context words found in both
  mark where the selection starts and ends; word times decide only where that fails;
- putting new words in place of the selected ones (replace_words), with times either
  from the reading or spread over the range for text typed by hand (spread_words).

A word position is (segment index, word index) inside Transcript.segments.
"""

import difflib
import re

import numpy as np

from .asr import Word
from .audio import SAMPLE_RATE

# Longest selection that may be recognised again: with the context on both sides the
# piece stays inside Whisper's 30 s window.
MAX_SECONDS = 25.0
# Context recognised with the selection on each side: at most this long, at most CONTEXT_WORDS words.
CONTEXT_SECONDS = 1.5
CONTEXT_WORDS = 6
# How far a cut may move into a long pause before (or after) the selection.
MAX_PAUSE_SEARCH = 0.6
# When two words touch (no gap), the cut is searched this far on each side of the boundary.
TOUCH_SEARCH = 0.15
# Window for the loudness measure when looking for the quietest point.
QUIET_WINDOW = int(0.01 * SAMPLE_RATE)

_WORD_KEY = re.compile(r"[\w]+")


def word_at(segments, position):
    segment_index, word_index = position
    return segments[segment_index].words[word_index]


def positions_between(segments, first, last):
    """Every (segment, word) position from first to last, both included, in order."""
    found = []
    for segment_index in range(first[0], last[0] + 1):
        words = segments[segment_index].words
        start = first[1] if segment_index == first[0] else 0
        end = last[1] if segment_index == last[0] else len(words) - 1
        found.extend((segment_index, word_index) for word_index in range(start, end + 1))
    return found


def neighbour(segments, position, step):
    """The word position before (step -1) or after (step +1) position, or None at the ends."""
    segment_index, word_index = position
    word_index += step
    while 0 <= segment_index < len(segments):
        words = segments[segment_index].words
        if 0 <= word_index < len(words):
            return segment_index, word_index
        segment_index += step
        if 0 <= segment_index < len(segments):
            word_index = 0 if step > 0 else len(segments[segment_index].words) - 1
    return None


def context_bounds(segments, first, last):
    """(context first, context last): the selection widened by the words that start
    (or end) within CONTEXT_SECONDS before (after) it, at most CONTEXT_WORDS each side."""
    start, end = word_at(segments, first).start, word_at(segments, last).end
    before, after = first, last
    for _ in range(CONTEXT_WORDS):
        candidate = neighbour(segments, before, -1)
        if candidate is None or word_at(segments, candidate).start < start - CONTEXT_SECONDS:
            break
        before = candidate
    for _ in range(CONTEXT_WORDS):
        candidate = neighbour(segments, after, +1)
        if candidate is None or word_at(segments, candidate).end > end + CONTEXT_SECONDS:
            break
        after = candidate
    return before, after


def check_selection(segments, first, last):
    """ValueError unless first..last are real word positions in order."""
    for position in (first, last):
        segment_index, word_index = position
        if not (0 <= segment_index < len(segments) and 0 <= word_index < len(segments[segment_index].words)):
            raise ValueError(f"No word at {position}")
    if tuple(first) > tuple(last):
        raise ValueError("The selection ends before it starts")


def search_windows(segments, first, last, audio_seconds=None):
    """Where the two cuts may go: ((left_lo, left_hi), (right_lo, right_hi)) in seconds.

    The left cut lies in the gap between the word before the selection and its first
    word, the right cut in the gap after its last word. A long pause is searched only
    near the selected words; touching words get a small window around the boundary.
    """
    first_word, last_word = word_at(segments, first), word_at(segments, last)
    before = neighbour(segments, first, -1)
    after = neighbour(segments, last, +1)
    if before is None:
        left = (max(0.0, first_word.start - MAX_PAUSE_SEARCH), first_word.start)
    else:
        previous_end = word_at(segments, before).end
        if previous_end < first_word.start:
            left = (max(previous_end, first_word.start - MAX_PAUSE_SEARCH), first_word.start)
        else:
            left = (first_word.start - TOUCH_SEARCH, first_word.start + TOUCH_SEARCH)
    if after is None:
        right = (last_word.end, last_word.end + MAX_PAUSE_SEARCH)
    else:
        next_start = word_at(segments, after).start
        if last_word.end < next_start:
            right = (last_word.end, min(next_start, last_word.end + MAX_PAUSE_SEARCH))
        else:
            right = (last_word.end - TOUCH_SEARCH, last_word.end + TOUCH_SEARCH)
    left = (max(0.0, left[0]), max(0.0, left[1]))
    if audio_seconds:
        right = (min(right[0], audio_seconds), min(right[1], audio_seconds))
    return left, right


def play_range(segments, first, last, audio_seconds=None):
    """The range to play for a selection: the middle of each search window."""
    left, right = search_windows(segments, first, last, audio_seconds)
    return (left[0] + left[1]) / 2, (right[0] + right[1]) / 2


def quietest_point(samples, offset, lo, hi):
    """The time in [lo, hi] (seconds) where 10 ms of samples are quietest.

    samples start at `offset` seconds. A window outside the samples gives its middle.
    """
    a = max(0, int(round((lo - offset) * SAMPLE_RATE)))
    b = min(len(samples), int(round((hi - offset) * SAMPLE_RATE)))
    if b - a <= QUIET_WINDOW:
        return (lo + hi) / 2
    energy = np.convolve(np.square(samples[a:b].astype(np.float64)), np.ones(QUIET_WINDOW), mode="valid")
    best = int(np.argmin(energy))
    return offset + (a + best + QUIET_WINDOW / 2) / SAMPLE_RATE


def reread_piece(asr, samples, offset, prompt=None):
    """Recognise one piece of audio with a loaded model (asr.AsrModel or
    whisper_model.WhisperModel). Words get times from the start of the file.
    prompt: Whisper only, text it is told came before (the user's terms)."""
    if prompt and hasattr(asr, "set_language"):
        encoded = asr.encode([samples], prompt=prompt)
    else:
        encoded = asr.encode([samples])
    if not encoded:
        return []
    return asr.words(asr.decode(encoded[0]), offset)


def spread_words(text, start, end):
    """Words of text typed by hand, with times spread over start..end by their length."""
    pieces = text.split()
    if not pieces:
        return []
    total = sum(len(piece) for piece in pieces)
    words, position = [], start
    for piece in pieces:
        length = (end - start) * len(piece) / total
        words.append(Word(round(position, 3), round(position + length, 3), piece))
        position += length
    return words


def word_key(text):
    """A word as compared between readings: lower case, ё as е, letters and digits only."""
    return "".join(_WORD_KEY.findall(text.lower().replace("ё", "е")))


def same_words(a, b):
    """True if two texts have the same words, ignoring case, punctuation and ё/е."""
    def keys(text):
        return [key for key in (word_key(word) for word in text.split()) if key]
    return keys(a) == keys(b)


def _boundary(opcodes, index, low):
    """Where a boundary before word `index` of the current text falls in the reading,
    from difflib opcodes; None when it lies inside a changed run. Words the reading
    adds right at the boundary go to the selection: low picks the start of such a
    run (for the selection's start), not low its end (for the selection's end)."""
    found = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            if i1 <= index <= i2:
                found.append(j1 + index - i1)
        elif i1 < index < i2:
            return None
        else:
            if i1 == index:
                found.append(j1)
            if i2 == index:
                found.append(j2)
    if not found:
        return None
    return min(found) if low else max(found)


def trim_reading(reading, context_words, first_selected, last_selected):
    """The words of a reading of the whole piece that stand for the selection.

    reading: Words recognised from the piece (selection plus context).
    context_words: the current Words of the piece; first_selected..last_selected
    (indices into it, both included) are the selected ones.
    """
    current = [word_key(word.text) for word in context_words]
    heard = [word_key(word.text) for word in reading]
    opcodes = difflib.SequenceMatcher(a=current, b=heard, autojunk=False).get_opcodes()
    start = _boundary(opcodes, first_selected, low=True)
    end = _boundary(opcodes, last_selected + 1, low=False)
    if start is None:  # by time: the first word that ends after the selection starts
        begin = context_words[first_selected].start
        start = next((i for i, word in enumerate(reading) if (word.start + word.end) / 2 >= begin), len(reading))
    if end is None:
        finish = context_words[last_selected].end
        end = next((i for i in range(len(reading) - 1, -1, -1)
                    if (reading[i].start + reading[i].end) / 2 <= finish), -1) + 1
    return list(reading[start:max(start, end)])


def selected_text(segments, first, last):
    return " ".join(word_at(segments, position).text for position in positions_between(segments, first, last))


def replace_words(segments, first, last, new_words):
    """Put new_words in place of the words first..last, in place.

    The new words go where the first selected word was; selected words in later
    segments are removed. Every touched segment gets its text joined again from its
    words, so segment.text and segment.words stay in step. Segment boundaries do
    not move. Returns the indices of the changed segments.
    """
    check_selection(segments, first, last)
    changed = list(range(first[0], last[0] + 1))
    for segment_index in reversed(changed):
        segment = segments[segment_index]
        start = first[1] if segment_index == first[0] else 0
        end = last[1] if segment_index == last[0] else len(segment.words) - 1
        inserted = list(new_words) if segment_index == first[0] else []
        segment.words[start:end + 1] = inserted
        segment.text = " ".join(word.text for word in segment.words)
    return changed
