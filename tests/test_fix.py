"""Fixing a selected part of the text (gigaam_app/fix.py, plan 03 Stage A): no models needed."""

import numpy as np
import pytest

from gigaam_app import fix
from gigaam_app.audio import SAMPLE_RATE
from gigaam_app.engine import Segment, Word


def words(*items):
    """Words from (text, start, end) triples."""
    return [Word(start, end, text) for text, start, end in items]


def line(*items):
    found = words(*items)
    return Segment(start=found[0].start, end=found[-1].end, text=" ".join(w.text for w in found), words=found)


@pytest.fixture
def segments():
    # Two lines; a long pause before "четыре", touching words "два" and "три".
    return [line(("Раз", 0.0, 0.4), ("два", 0.5, 0.9), ("три", 0.9, 1.3)),
            line(("четыре", 5.0, 5.5), ("пять.", 5.6, 6.0))]


def test_positions_and_neighbours(segments):
    assert fix.positions_between(segments, (0, 1), (1, 0)) == [(0, 1), (0, 2), (1, 0)]
    assert fix.neighbour(segments, (0, 2), +1) == (1, 0)
    assert fix.neighbour(segments, (1, 0), -1) == (0, 2)
    assert fix.neighbour(segments, (0, 0), -1) is None
    assert fix.neighbour(segments, (1, 1), +1) is None
    assert fix.selected_text(segments, (0, 2), (1, 0)) == "три четыре"


def test_check_selection(segments):
    fix.check_selection(segments, (0, 0), (1, 1))
    with pytest.raises(ValueError):
        fix.check_selection(segments, (1, 0), (0, 2))
    with pytest.raises(ValueError):
        fix.check_selection(segments, (0, 0), (0, 3))


def test_search_windows(segments):
    # "два": gap of 0.1 s before it; touching "три" after it.
    left, right = fix.search_windows(segments, (0, 1), (0, 1))
    assert left == pytest.approx((0.4, 0.5))
    assert right == pytest.approx((0.9 - fix.TOUCH_SEARCH, 0.9 + fix.TOUCH_SEARCH))
    # "четыре": a long pause before it is searched only near the word; the file starts at 0.
    left, _ = fix.search_windows(segments, (1, 0), (1, 0))
    assert left == pytest.approx((5.0 - fix.MAX_PAUSE_SEARCH, 5.0))
    left, right = fix.search_windows(segments, (0, 0), (1, 1), audio_seconds=6.2)
    assert left == pytest.approx((0.0, 0.0))
    assert right == pytest.approx((6.0, 6.2))


def test_context_bounds(segments):
    # Words starting within 1.5 s before / ending within 1.5 s after the selection.
    assert fix.context_bounds(segments, (0, 2), (0, 2)) == ((0, 0), (0, 2))
    assert fix.context_bounds(segments, (1, 0), (1, 0)) == ((1, 0), (1, 1))


def test_quietest_point_finds_the_pause():
    samples = np.ones(SAMPLE_RATE, np.float32)  # 1 s of loud sound starting at 10 s
    samples[int(0.6 * SAMPLE_RATE):int(0.62 * SAMPLE_RATE)] = 0.0
    point = fix.quietest_point(samples, 10.0, 10.5, 10.7)
    assert 10.6 <= point <= 10.62
    assert fix.quietest_point(samples, 10.0, 10.5, 10.505) == pytest.approx(10.5025)


def test_trim_reading_by_matching_context():
    context = words(("через", 0, 1), ("наш", 1, 2), ("любимый", 2, 3), ("механизм", 3, 4),
                    ("Tullz", 4, 5), ("Colling,", 5, 6), ("и", 6, 7), ("вся", 7, 8))
    # Selected: "механизм Tullz Colling," (indices 3..5).
    reading = words(("Подключим", 0, 0.5), ("их", 0.5, 0.8), ("через", 0.8, 1), ("наш", 1, 2), ("любимый", 2, 3),
                    ("механизм", 3, 4), ("Tools", 4, 5), ("Calling,", 5, 6), ("и", 6, 7), ("вся", 7, 8))
    assert [w.text for w in fix.trim_reading(reading, context, 3, 5)] == ["механизм", "Tools", "Calling,"]
    # A changed word right at the start of the selection still belongs to it.
    reading[5] = Word(3, 4, "Механизмы")
    assert [w.text for w in fix.trim_reading(reading, context, 3, 5)] == ["Механизмы", "Tools", "Calling,"]


def test_trim_reading_falls_back_to_times():
    context = words(("один", 0, 1), ("два", 1, 2), ("три", 2, 3))
    # Nothing matches: the words whose middle lies inside the selected word's time.
    reading = words(("a", 0, 1), ("b", 1, 2), ("c", 2, 3))
    assert [w.text for w in fix.trim_reading(reading, context, 1, 1)] == ["b"]
    assert fix.trim_reading([], context, 1, 1) == []


def test_same_words():
    assert fix.same_words("Вроде той же, DeepSeek.", "вроде той же deepseek")
    assert fix.same_words("ещё", "еще")
    assert not fix.same_words("Tools Calling", "Tullz Colling")


def test_spread_words():
    found = fix.spread_words("ab abcd", 1.0, 4.0)
    assert [(w.text, w.start, w.end) for w in found] == [("ab", 1.0, 2.0), ("abcd", 2.0, 4.0)]
    assert fix.spread_words("   ", 0, 1) == []


def test_replace_words_in_one_line(segments):
    changed = fix.replace_words(segments, (0, 1), (0, 2), words(("два-три", 0.5, 1.3)))
    assert changed == [0]
    assert segments[0].text == "Раз два-три"
    assert [w.text for w in segments[0].words] == ["Раз", "два-три"]


def test_replace_words_across_lines(segments):
    fix.replace_words(segments, (0, 2), (1, 0), words(("три,", 0.9, 1.3), ("четыре", 5.0, 5.5)))
    assert segments[0].text == "Раз два три, четыре"
    assert segments[1].text == "пять."
    assert [w.text for w in segments[1].words] == ["пять."]
