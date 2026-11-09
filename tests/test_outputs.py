"""Text, timestamped text, Markdown, SRT and JSON writers."""

import datetime
import json

import pytest

from gigaam_app.asr import Word
from gigaam_app.engine import Segment, Transcript
from gigaam_app.outputs import clock, ends_sentence, json_text, llm_text, markdown_escape, markdown_text, output_paths, plain_text, \
    srt_text, subtitle_cues, timestamped_text, write_outputs


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


DAY = datetime.date(2026, 11, 6)


def test_json_keeps_a_known_confidence_and_leaves_out_an_unknown_one():
    transcript = make_transcript()
    transcript.segments[0].words[1].confidence = 0.62
    words = json.loads(json_text(transcript))["segments"][0]["words"]
    assert words[1]["confidence"] == 0.62
    assert "confidence" not in words[0]


def test_json_leaves_out_the_windows_offers():
    transcript = make_transcript()
    transcript.suggestions_searched = True
    transcript.segments[0].words[0].suggestions = [{"models": ["CTC"], "count": 1, "words": [[0.5, 0.9, "Пока.", None]]}]
    data = json.loads(json_text(transcript))
    assert "suggestions_searched" not in data
    assert "suggestions" not in data["segments"][0]["words"][0]


def test_llm_text_marks_doubtful_words_before_their_punctuation():
    transcript = make_transcript()
    transcript.segments[0].words[0].confidence = 0.66   # "Привет." -> "Привет[?66%]."
    transcript.segments[0].words[2].confidence = 0.97   # at the threshold: not marked
    transcript.segments[2].words[0].confidence = 0.5
    text = llm_text(transcript)
    lines = text.splitlines()
    assert "слово[?66%]" in lines[0] and "GigaAM v3 RNNT" in lines[0]
    assert "ошибки возможны и в неотмеченных словах" in lines[0]
    assert lines[1] == "Отмечено слов: 2 из 5."
    assert lines[3:] == ["Привет[?66%]. Как дела?", "Хорошо[?50%] спасибо."]
    assert llm_text(transcript, doubt_below=0.6).splitlines()[3] == "Привет. Как дела?"


def test_llm_text_gives_both_versions_where_another_model_heard_otherwise():
    transcript = make_transcript()
    words = transcript.segments[0].words              # "Привет." "Как" "дела?"
    words[1].confidence = 0.6
    words[1].suggestions = [{"models": ["Whisper"], "count": 2,
                             "words": [[0.0, 0.5, "Как", None], [0.5, 1.0, "дела?", None]]},
                            {"models": ["CTC", "Whisper"], "count": 1, "words": [[0.0, 0.5, "Каг", None]]}]
    lines = llm_text(transcript).splitlines()
    assert "даны в нескольких версиях" in lines[1] and "GigaAM v3 RNNT" in lines[1]
    assert lines[2] == "Отмечено слов: 1 из 5. Мест с разными версиями: 1."
    # A shorter offer keeps the rest of the span, so every version covers the same words.
    assert lines[4] == ("Привет. {GigaAM v3 RNNT: Как[?60%] дела? | Whisper large-v3-turbo (q5_0): Как дела? | "
                        "GigaAM v3 CTC, Whisper large-v3-turbo (q5_0): Каг дела?}")
    assert "версиях" not in llm_text(make_transcript())  # no offers: no note


def test_llm_file_uses_the_given_threshold(tmp_path):
    transcript = make_transcript(tmp_path / "talk.mp3")
    transcript.segments[0].words[1].confidence = 0.9
    [path] = write_outputs(transcript, ["llm"], doubt_below=0.95)
    assert path.name == "talk-transcript-llm.txt"
    assert "Как[?90%] дела?" in path.read_text(encoding="utf-8")
    [path] = write_outputs(transcript, ["llm"], doubt_below=0.8)
    assert "Как дела?" in path.read_text(encoding="utf-8")


def test_markdown_layout():
    """Title, info line, then one section per minute or long pause (owner's choice, 2026-11-06)."""
    assert markdown_text(make_transcript(), today=DAY) == (
        "# talk.mp3\n\n"
        "*2026-11-06 · 0:40 · GigaAM v3 RNNT*\n\n"
        "## 00:00\n\nПривет. Как дела?\n\n"
        "## 00:29\n\nХорошо спасибо.\n")


def test_markdown_sections_join_segments_until_a_minute_or_a_long_pause():
    segments = [Segment(0, 20, "Один."), Segment(21, 50, "Два."), Segment(51, 70, "Три."),
                Segment(71, 75, "Четыре."),            # 71 s after the section start: new section
                Segment(82, 90, "Пять."),              # 7 s pause but the section is only 11 s long
                Segment(96, 99, "Шесть.")]             # 6 s pause after 25 s of section: new section
    text = markdown_text(Transcript(source="a.wav", model="", device="", segments=segments), today=DAY)
    assert text == ("# a.wav\n\n*2026-11-06*\n\n## 00:00\n\nОдин. Два. Три.\n\n"
                    "## 01:11\n\nЧетыре. Пять.\n\n## 01:36\n\nШесть.\n")


def test_markdown_long_files_use_hours_in_every_heading():
    segments = [Segment(5, 8, "Начало."), Segment(3700, 3710, "Через час.")]
    text = markdown_text(Transcript(source="a.wav", model="CTC", device="", audio_seconds=3712.4,
                                    segments=segments), today=DAY)
    assert "*2026-11-06 · 1:01:52 · GigaAM v3 CTC*" in text
    assert "## 0:00:05\n" in text and "## 1:01:40\n" in text


@pytest.mark.parametrize("plain, escaped", [
    ("my_lecture.mp3", "my_lecture.mp3"),          # an underscore inside a word stays plain
    ("_draft_ notes", "\\_draft\\_ notes"),
    ("*x* [a](b) <b> a\\b `c`", "\\*x\\* \\[a\\](b) \\<b\\> a\\\\b \\`c\\`"),
    ("# hi", "\\# hi"),
    ("- dash", "\\- dash"),
    ("1. one", "1\\. one"),
    ("2024 год", "2024 год"),
])
def test_markdown_escape(plain, escaped):
    assert markdown_escape(plain) == escaped


def test_output_paths(tmp_path):
    paths = output_paths(tmp_path / "a" / "talk.final.mp3", ["txt", "timestamps", "md", "srt", "json"])
    assert {fmt: path.name for fmt, path in paths.items()} == {
        "txt": "talk.final-transcript.txt", "timestamps": "talk.final-transcript-timestamps.txt",
        "md": "talk.final-transcript.md", "srt": "talk.final-transcript.srt", "json": "talk.final-transcript.json"}
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


# ---------------------------------------------------------------------- speaker names (plan 07)

def spoken_transcript():
    """Anna asks, Boris answers inside the same line, then Anna again in the next line."""
    first = [Word(0.5, 0.9, "Привет.", speaker=0), Word(1.0, 1.4, "Как", speaker=0),
             Word(1.5, 1.9, "дела?", speaker=0), Word(2.5, 3.0, "Хорошо.", speaker=1)]
    second = [Word(30.0, 30.4, "А", speaker=0), Word(30.5, 31.0, "у", speaker=None),  # typed by hand
              Word(31.1, 31.6, "тебя?", speaker=0)]
    third = [Word(32.0, 32.5, "Тоже.", speaker=0)]
    return Transcript(source="talk.mp3", model="RNNT", device="CPU", audio_seconds=40.0,
                      speakers=["Анна", "Говорящий 2"], segments=[
                          Segment(0.2, 3.1, "Привет. Как дела? Хорошо.", first),
                          Segment(29.8, 31.8, "А у тебя?", second),
                          Segment(31.9, 32.6, "Тоже.", third)])


def test_plain_text_starts_each_turn_with_the_name():
    assert plain_text(spoken_transcript()) == ("Анна: Привет. Как дела?\n\nГоворящий 2: Хорошо.\n\n"
                                               "Анна: А у тебя?\nТоже.\n")


def test_timestamped_text_names_the_speaker_on_every_line():
    assert timestamped_text(spoken_transcript()) == (
        "[00:00.200 - 00:01.900] Анна: Привет. Как дела?\n"
        "[00:02.500 - 00:03.100] Говорящий 2: Хорошо.\n"
        "[00:29.800 - 00:31.800] Анна: А у тебя?\n"
        "[00:31.900 - 00:32.600] Анна: Тоже.\n")


def test_subtitles_never_mix_speakers_and_name_the_turn():
    cues = [text for _, _, text in subtitle_cues(spoken_transcript())]
    assert cues == ["Анна: Привет. Как дела?", "Говорящий 2: Хорошо.", "Анна: А у тебя?", "Тоже."]


def test_markdown_paragraph_per_turn_with_the_name_in_bold():
    text = markdown_text(spoken_transcript(), today=DAY)
    assert text.endswith("## 00:00\n\n**Анна:** Привет. Как дела?\n\n**Говорящий 2:** Хорошо.\n\n"
                         "## 00:29\n\n**Анна:** А у тебя? Тоже.\n")


def test_llm_text_names_speakers_and_says_they_may_be_wrong():
    text = llm_text(spoken_transcript())
    assert "Текст разделён по говорящим" in text
    assert text.endswith("Анна: Привет. Как дела?\n\nГоворящий 2: Хорошо.\n\nАнна: А у тебя?\nТоже.\n")


def test_json_keeps_names_and_word_speakers():
    data = json.loads(json_text(spoken_transcript()))
    assert data["speakers"] == ["Анна", "Говорящий 2"]
    assert [w.get("speaker") for w in data["segments"][1]["words"]] == [0, None, 0]


def test_without_speakers_nothing_changes():
    transcript = spoken_transcript()
    transcript.speakers = None
    assert plain_text(transcript) == "Привет. Как дела? Хорошо.\nА у тебя?\nТоже.\n"
    assert "Анна" not in markdown_text(transcript, today=DAY) + srt_text(transcript) + llm_text(transcript)


# ------------------------------------------------- lines cut mid-sentence (plan 07 G6)

def cut_transcript():
    """Sonya speaks, then Anna's turn starts inside the same line; her sentence is cut into
    the next line by a breath (owner's example, 2026-11-09), then a line after a full stop."""
    first = [Word(30.0, 30.5, "Меня", speaker=0), Word(30.6, 31.0, "зовут", speaker=0),
             Word(31.1, 31.5, "Соня.", speaker=0), Word(47.0, 47.5, "Мы", speaker=1),
             Word(47.6, 48.0, "показываем,", speaker=1), Word(48.1, 48.6, "могут", speaker=1)]
    second = [Word(55.0, 55.5, "Решить", speaker=1), Word(55.6, 56.0, "проблемы.", speaker=1)]
    third = [Word(58.0, 58.5, "Подкаст", speaker=1), Word(58.6, 59.0, "выходит.", speaker=1)]
    return Transcript(source="talk.mp3", model="RNNT", device="CPU", audio_seconds=60.0,
                      speakers=["Соня", "Анна"], segments=[
                          Segment(29.9, 48.7, "Меня зовут Соня. Мы показываем, могут", first),
                          Segment(54.9, 56.1, "Решить проблемы.", second),
                          Segment(57.9, 59.1, "Подкаст выходит.", third)])


@pytest.mark.parametrize("text, expected", [
    ("могут", False), ("проблем.", True), ("Да?", True), ("Ура!", True), ("ну...", True),
    ("«Да!»", True), ("(так.)", True), ("слово,", False), ("  конец.  ", True), ("", False),
])
def test_ends_sentence(text, expected):
    assert ends_sentence(text) is expected


def test_plain_text_joins_a_line_cut_mid_sentence():
    assert plain_text(cut_transcript()) == ("Соня: Меня зовут Соня.\n\n"
                                            "Анна: Мы показываем, могут Решить проблемы.\nПодкаст выходит.\n")


def test_llm_text_joins_a_line_cut_mid_sentence():
    assert llm_text(cut_transcript()).endswith(
        "Соня: Меня зовут Соня.\n\nАнна: Мы показываем, могут Решить проблемы.\nПодкаст выходит.\n")


def test_markdown_starts_no_section_in_the_middle_of_a_sentence():
    # Anna's turn after a 15 s pause starts a section (Sonya's sentence ended); the 6 s pause
    # before "Решить" would start one too, but there the sentence goes on.
    text = markdown_text(cut_transcript(), today=DAY)
    assert text.endswith("## 00:29\n\n**Соня:** Меня зовут Соня.\n\n## 00:47\n\n"
                         "**Анна:** Мы показываем, могут Решить проблемы. Подкаст выходит.\n")


def test_srt_and_timestamps_keep_each_line():
    transcript = cut_transcript()
    assert timestamped_text(transcript).splitlines()[2] == "[00:54.900 - 00:56.100] Анна: Решить проблемы."
    assert "Решить проблемы." in [text for _, _, text in subtitle_cues(transcript)]


def test_without_speakers_lines_stay_apart():
    transcript = cut_transcript()
    transcript.speakers = None
    assert plain_text(transcript) == "Меня зовут Соня. Мы показываем, могут\nРешить проблемы.\nПодкаст выходит.\n"
