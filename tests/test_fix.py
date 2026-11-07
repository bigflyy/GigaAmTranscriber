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


# ---------------------------------------------------------------------- suggested fixes (plan 06)

def sure_line(*items):
    """A segment from (text, start, end, confidence) words."""
    found = [Word(start, end, text, confidence) for text, start, end, confidence in items]
    return Segment(start=found[0].start, end=found[-1].end, text=" ".join(w.text for w in found), words=found)


def test_doubt_groups_join_near_words_and_stay_in_one_line():
    segments = [sure_line(("a", 0, 1, 0.5), ("b", 1, 2, 0.99), ("c", 2, 3, 0.6), ("d", 3, 4, 0.99),
                          ("e", 4, 5, 0.99), ("f", 5, 6, 0.9), ("g", 6, 7, None)),
                sure_line(("h", 8, 9, 0.9), ("i", 9, 10, 0.99))]
    # a and c have one sure word between them: one group; f is two sure words away: its own;
    # g has no confidence; h starts a new line, so a new group.
    assert fix.doubt_groups(segments, 0.97) == [((0, 0), (0, 2)), ((0, 5), (0, 5)), ((1, 0), (1, 0))]
    assert fix.doubt_groups(segments, 0.55) == [((0, 0), (0, 0))]


def test_doubt_groups_split_when_too_long():
    long_line = sure_line(*[(f"w{i}", i * 2.0, i * 2.0 + 1.0, 0.5) for i in range(20)])
    groups = fix.doubt_groups([long_line], 0.97)
    assert len(groups) == 2
    for first, last in groups:
        assert long_line.words[last[1]].end - long_line.words[first[1]].start <= fix.MAX_SECONDS


CONTEXT = words(("любимый", 1.4, 1.9), ("механизм", 2.0, 2.6), ("Tullz", 2.7, 3.0), ("Colling,", 3.0, 3.5),
                ("и", 3.6, 3.7))


def test_suggestion_covers_the_whole_differing_run():
    heard = words(("любимый", 1.4, 1.9), ("механизм", 2.0, 2.6), ("Tools", 2.7, 3.0), ("Calling,", 3.0, 3.5),
                  ("и", 3.6, 3.7))
    first, count, offered = fix.suggestion_from(heard, CONTEXT, 2, 2)  # only "Tullz" was doubtful
    assert (first, count, [w.text for w in offered]) == (2, 2, ["Tools", "Calling,"])


def test_suggestion_none_when_the_reading_agrees_or_differs_elsewhere():
    same = words(("Любимый", 1.4, 1.9), ("механизм", 2.0, 2.6), ("Tullz", 2.7, 3.0), ("Colling", 3.0, 3.5),
                 ("и.", 3.6, 3.7))
    assert fix.suggestion_from(same, CONTEXT, 2, 2) is None  # case and punctuation do not count
    elsewhere = words(("любимой", 1.4, 1.9), ("механизм", 2.0, 2.6), ("Tullz", 2.7, 3.0), ("Colling,", 3.0, 3.5),
                      ("и", 3.6, 3.7))
    assert fix.suggestion_from(elsewhere, CONTEXT, 2, 2) is None


def test_suggestion_of_an_added_or_dropped_word_takes_a_neighbour():
    current = words(("решение", 0, 1), ("принятии", 1, 2), ("задачи", 2, 3))
    added = words(("решение", 0, 1), ("в", 1, 1.1), ("принятии", 1.1, 2), ("задачи", 2, 3))
    first, count, offered = fix.suggestion_from(added, current, 1, 1)
    assert (first, count, [w.text for w in offered]) == (0, 1, ["решение", "в"])
    dropped = words(("решение", 0, 1), ("задачи", 2, 3))
    first, count, offered = fix.suggestion_from(dropped, current, 1, 1)
    assert (first, count, [w.text for w in offered]) == (0, 2, ["решение"])


def test_suggestion_none_when_the_reading_went_its_own_way():
    current = words(*[(f"w{i}", i, i + 1) for i in range(12)])
    other = words(*[(f"x{i}", i, i + 1) for i in range(12)])
    assert fix.suggestion_from(other, current, 5, 5) is None


def test_add_suggestion_joins_the_same_offer_from_two_models():
    segments = [sure_line(("Tullz", 2.7, 3.0, 0.5), ("Colling,", 3.0, 3.5, 0.99))]
    offer = words(("Tools", 2.7, 3.0), ("Calling,", 3.0, 3.5))
    assert fix.add_suggestion(segments, (0, 0), 2, offer, "Whisper")
    assert not fix.add_suggestion(segments, (0, 0), 2, words(("tools", 2.7, 3.0), ("calling", 3.0, 3.5)), "CTC")
    assert fix.add_suggestion(segments, (0, 0), 1, words(("Tulls", 2.7, 3.0)), "RNNT")
    offers = segments[0].words[0].suggestions
    assert [(o["models"], o["count"]) for o in offers] == [(["Whisper", "CTC"], 2), (["RNNT"], 1)]
    assert [w.text for w in fix.suggestion_words(offers[0])] == ["Tools", "Calling,"]
    fix.drop_suggestion(segments, (0, 0), 0)
    fix.drop_suggestion(segments, (0, 0), 0)
    assert segments[0].words[0].suggestions is None


def test_replace_words_drops_offers_that_reach_into_the_change():
    segments = [sure_line(("a", 0, 1, 0.5), ("b", 1, 2, 0.5), ("c", 2, 3, 0.99)),
                sure_line(("d", 4, 5, 0.99), ("e", 5, 6, 0.99))]
    fix.add_suggestion(segments, (0, 0), 1, words(("A", 0, 1)), "CTC")      # covers a only
    fix.add_suggestion(segments, (0, 1), 3, words(("B", 1, 5)), "Whisper")  # covers b c d
    fix.replace_words(segments, (1, 0), (1, 0), words(("D", 4, 5)))
    assert segments[0].words[0].suggestions is not None
    assert segments[0].words[1].suggestions is None
