"""Command-line argument handling that needs no model."""

import pytest

from gigaam_app import cli


def test_vad_overrides_are_typed():
    args = cli.build_parser().parse_args(["a.wav", "--vad-threshold", "0.4", "--vad-min-speech-ms", "250"])
    assert args.vad_threshold == 0.4 and args.vad_min_speech_ms == 250 and args.max_duration is None


def test_unknown_format_exits_2(tmp_path, capsys):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    assert cli.main([str(audio), "--formats", "txt,docx", "--config", str(tmp_path / "none.json")]) == 2
    assert "docx" in capsys.readouterr().err


def test_missing_file_exits_2(tmp_path, capsys):
    assert cli.main([str(tmp_path / "missing.wav"), "--config", str(tmp_path / "none.json")]) == 2
    assert "File not found" in capsys.readouterr().err


def test_bad_settings_file_exits_2(tmp_path, capsys):
    bad = tmp_path / "gigaam-config.json"
    bad.write_text('{"model": "nope"}', encoding="utf-8")
    assert cli.main([str(tmp_path / "a.wav"), "--config", str(bad)]) == 2
    assert "Settings error" in capsys.readouterr().err


class FakeTranscriber:
    """Records what the CLI asks for and stops before any audio is read."""
    made = []

    def __init__(self, model, device, cpu_threads, language):
        if language == "xx":
            raise ValueError("Whisper does not know the language 'xx'")
        FakeTranscriber.made.append((model, language))
        self.uses_language = model == "Whisper"
        raise SystemExit(0)


@pytest.mark.parametrize("argv, expected", [
    (["--model", "Whisper", "--language", "en"], ("Whisper", "en")),
    (["--model", "Whisper"], ("Whisper", "auto")),
])
def test_language_reaches_the_model(tmp_path, monkeypatch, argv, expected):
    monkeypatch.setattr(cli, "Transcriber", FakeTranscriber)
    FakeTranscriber.made.clear()
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    with pytest.raises(SystemExit):
        cli.main([str(audio), *argv, "--config", str(tmp_path / "none.json")])
    assert FakeTranscriber.made == [expected]


@pytest.mark.parametrize("whisper_cpu, downloaded, argv, expected", [
    ("faster-whisper", True, [], "faster-whisper"),
    ("faster-whisper", True, ["--device", "cpu"], "faster-whisper"),
    ("faster-whisper", True, ["--device", "gpu"], "Whisper"),  # a video card: whisper.cpp (Vulkan)
    ("faster-whisper", False, [], "Whisper"),  # not downloaded: whisper.cpp, as in the window
    ("whisper.cpp", True, [], "Whisper"),
])
def test_whisper_cpu_setting_picks_the_reader(tmp_path, monkeypatch, whisper_cpu, downloaded, argv, expected):
    """The CLI reads Whisper's text with the engine chosen in the window's Настройки (plan 08 C3a)."""
    monkeypatch.setattr(cli, "Transcriber", FakeTranscriber)
    fast = cli.catalog.FAST_WHISPER_MODEL
    monkeypatch.setattr(cli.catalog, "installed_folder",
                        lambda info: tmp_path if info is fast and downloaded else None)
    FakeTranscriber.made.clear()
    settings = tmp_path / "gigaam-config.json"
    settings.write_text(f'{{"model": "Whisper", "whisper_cpu": "{whisper_cpu}"}}', encoding="utf-8")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    with pytest.raises(SystemExit):
        cli.main([str(audio), *argv, "--config", str(settings)])
    assert FakeTranscriber.made == [(expected, "auto")]


def test_whisper_cpu_setting_leaves_gigaam_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(cli.catalog, "installed_folder", lambda info: tmp_path)
    FakeTranscriber.made.clear()
    settings = tmp_path / "gigaam-config.json"
    settings.write_text('{"model": "RNNT", "whisper_cpu": "faster-whisper"}', encoding="utf-8")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    with pytest.raises(SystemExit):
        cli.main([str(audio), "--config", str(settings)])
    assert FakeTranscriber.made == [("RNNT", "auto")]


def test_unknown_language_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Transcriber", FakeTranscriber)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    assert cli.main([str(audio), "--model", "Whisper", "--language", "xx", "--config", str(tmp_path / "n.json")]) == 2
    assert "xx" in capsys.readouterr().err


def test_version(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0 and "0.6.0" in capsys.readouterr().out


def test_wildcards_are_expanded(tmp_path):
    for name in ("b.mp3", "a.mp3", "c.wav"):
        (tmp_path / name).write_bytes(b"")
    expanded = cli.expand_wildcards([tmp_path / "*.mp3", tmp_path / "c.wav", tmp_path / "none*.ogg"])
    # A pattern that matches nothing stays as given, so the user sees "File not found".
    assert [path.name for path in expanded] == ["a.mp3", "b.mp3", "c.wav", "none*.ogg"]


# ---------------------------------------------------------------------- speakers (plan 07)

@pytest.mark.parametrize("value, expected", [("off", None), ("auto", 0), ("AUTO", 0), ("3", 3), ("20", 20)])
def test_speaker_count(value, expected):
    assert cli.speaker_count(value) == expected


@pytest.mark.parametrize("value", ["0", "21", "two", "-1"])
def test_a_wrong_speaker_count_exits_2(tmp_path, capsys, value):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    assert cli.main([str(audio), "--speakers", value, "--config", str(tmp_path / "none.json")]) == 2
    assert "--speakers" in capsys.readouterr().err


def test_speakers_alone_means_auto():
    assert cli.build_parser().parse_args(["a.wav", "--speakers"]).speakers == "auto"
    assert cli.build_parser().parse_args(["--download", "Speakers"]).download == "Speakers"


class SpokenTranscriber:
    """Gives two lines of words for any file."""

    def __init__(self, model, device, cpu_threads, language):
        self.uses_language, self.device_label, self.load_seconds = False, "CPU", 0.1

    def transcribe(self, path, options, on_progress=None):
        from gigaam_app.engine import Segment, Transcript, Word
        words = [Word(0.0, 0.5, "Привет."), Word(2.0, 2.5, "Здравствуйте.")]
        return Transcript(source=str(path), model="RNNT", device="CPU", audio_seconds=3.0, elapsed_seconds=0.1,
                          segments=[Segment(0.0, 0.5, "Привет.", words[:1]), Segment(2.0, 2.5, "Здравствуйте.", words[1:])])


class FakeSpeakerModel:
    asked = []

    def diarize(self, audio, num_speakers=None):
        from gigaam_app.diarize import Diarization, Turn
        FakeSpeakerModel.asked.append(num_speakers)
        return Diarization(exclusive_turns=[Turn(0.0, 1.0, 7), Turn(1.8, 3.0, 4)], speakers=2)


def test_speakers_are_named_in_the_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Transcriber", SpokenTranscriber)
    monkeypatch.setattr(cli, "load_speaker_model", lambda device, threads, quiet: FakeSpeakerModel())
    monkeypatch.setattr(cli, "decode_audio", lambda path: None)
    FakeSpeakerModel.asked.clear()
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    assert cli.main([str(audio), "--speakers", "2", "--formats", "txt", "--config", str(tmp_path / "none.json")]) == 0
    assert FakeSpeakerModel.asked == [2]
    assert (tmp_path / "a-transcript.txt").read_text(encoding="utf-8") == \
        "Говорящий 1: Привет.\n\nГоворящий 2: Здравствуйте.\n"
    assert "2 speaker(s) found" in capsys.readouterr().out


def test_the_settings_file_turns_speakers_on(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "Transcriber", SpokenTranscriber)
    monkeypatch.setattr(cli, "load_speaker_model", lambda device, threads, quiet: FakeSpeakerModel())
    monkeypatch.setattr(cli, "decode_audio", lambda path: None)
    FakeSpeakerModel.asked.clear()
    settings = tmp_path / "gigaam-config.json"
    settings.write_text('{"speakers": true}', encoding="utf-8")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    assert cli.main([str(audio), "--formats", "txt", "--config", str(settings), "--quiet"]) == 0
    assert FakeSpeakerModel.asked == [None]
    assert cli.main([str(audio), "--formats", "txt", "--config", str(settings), "--quiet", "--speakers", "off"]) == 0
    assert FakeSpeakerModel.asked == [None]
    assert (tmp_path / "a-transcript.txt").read_text(encoding="utf-8") == "Привет.\nЗдравствуйте.\n"
