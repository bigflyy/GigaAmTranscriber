"""Text, timestamped text, SRT and JSON writers."""

import json

import pytest

from gigaam_app.asr import Word
from gigaam_app.engine import Segment, Transcript
from gigaam_app.outputs import clock, json_text, output_paths, plain_text, srt_text, subtitle_cues, \
    timestamped_text, write_outputs


def make_transcript(source="talk.mp3"):
    first = [Word(0.5, 0.9, "Привет."), Word(1.0, 1.4, "Как"), Word(1.5, 1.9, "дела?")]
    # A 3 s pause inside the second segment forces a new subtitle cue.
    second = [Word(30.0, 30.4, "Хорошо"), Word(33.5, 34.0, "спасибо.")]
    return Transcript(source=str(source), model="RNNT", device="CPU", audio_seconds=40.0, segments=[
        Segment(0.2, 2.0, "Привет. Как дела?", first),
        Segment(29.8, 34.2, "", []),
        Segment(29.8, 34.2, "Хорошо спасибо.", second),
    ])


@pytest.mark.parametrize("seconds, separator, expected", [
    (0, ".", "00:00.000"),
    (61.2345, ".", "01:01.234"),
    (3725.5, ".", "01:02:05.500"),
    (5.0, ",", "00:00:05,000"),
    (59.9996, ".", "01:00.000"),  # rounding carries into the minutes
])
def test_clock(seconds, separator, expected):
    assert clock(seconds, separator) == expected


def test_plain_and_timestamped_skip_empty_segments():
    transcript = make_transcript()
    assert plain_text(transcript) == "Привет. Как дела?\nХорошо спасибо.\n"
    assert timestamped_text(transcript) == ("[00:00.200 - 00:02.000] Привет. Как дела?\n"
                                            "[00:29.800 - 00:34.200] Хорошо спасибо.\n")


def test_cues_split_at_long_pauses():
    assert subtitle_cues(make_transcript()) == [
        (0.5, 1.9, "Привет. Как дела?"), (30.0, 30.4, "Хорошо"), (33.5, 34.0, "спасибо.")]


def test_cues_split_after_a_sentence_end_once_the_cue_is_long_enough():
    words = [Word(0.0, 1.0, "Да."), Word(1.2, 1.4, "Нет."), Word(1.6, 2.0, "Может")]
    transcript = Transcript("x.wav", "RNNT", "CPU", segments=[Segment(0, 2, "Да. Нет. Может", words)])
    # "Да." alone is too short to stand as a cue; after "Нет." the cue is 1.4 s, then 2.0 s.
    assert subtitle_cues(transcript) == [(0.0, 1.4, "Да. Нет."), (1.6, 2.0, "Может")]


def test_cues_respect_length_limits():
    words = [Word(i * 0.5, i * 0.5 + 0.4, "слово") for i in range(60)]
    transcript = Transcript("x.wav", "RNNT", "CPU", segments=[Segment(0, 30, " ".join(["слово"] * 60), words)])
    for start, end, text in subtitle_cues(transcript):
        assert end - start <= 6.0 + 1e-9
        assert len(text) <= 84
    assert sum(len(text.split()) for _, _, text in subtitle_cues(transcript)) == 60


def test_srt_format():
    srt = srt_text(make_transcript())
    blocks = srt.split("\n\n")
    assert blocks[0] == "1\n00:00:00,500 --> 00:00:01,900\nПривет. Как дела?"
    assert srt.endswith("спасибо.\n")
    assert [block.splitlines()[0] for block in blocks] == [str(n) for n in range(1, len(blocks) + 1)]


def test_json_has_words_and_full_text():
    data = json.loads(json_text(make_transcript()))
    assert data["text"] == "Привет. Как дела?\nХорошо спасибо."
    assert data["segments"][0]["words"][0] == {"start": 0.5, "end": 0.9, "text": "Привет."}
    assert data["model"] == "RNNT" and data["audio_seconds"] == 40.0


def test_output_paths(tmp_path):
    paths = output_paths(tmp_path / "a" / "talk.final.mp3", ["txt", "timestamps", "srt", "json"])
    assert {fmt: path.name for fmt, path in paths.items()} == {
        "txt": "talk.final-transcript.txt", "timestamps": "talk.final-transcript-timestamps.txt",
        "srt": "talk.final-transcript.srt", "json": "talk.final-transcript.json"}
    assert all(path.parent == tmp_path / "a" for path in paths.values())
    assert output_paths("x.wav", ["txt"], tmp_path / "out")["txt"] == tmp_path / "out" / "x-transcript.txt"


def test_write_outputs_creates_files_without_leftovers(tmp_path):
    source = tmp_path / "talk.mp3"
    source.write_bytes(b"not really audio")
    written = write_outputs(make_transcript(source), ["txt", "srt"], tmp_path / "out")
    assert [path.name for path in written] == ["talk-transcript.txt", "talk-transcript.srt"]
    assert (tmp_path / "out" / "talk-transcript.txt").read_bytes() == \
        "Привет. Как дела?\nХорошо спасибо.\n".encode("utf-8")
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == \
        ["talk-transcript.srt", "talk-transcript.txt"]
