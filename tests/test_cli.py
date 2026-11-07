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


def test_unknown_language_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Transcriber", FakeTranscriber)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    assert cli.main([str(audio), "--model", "Whisper", "--language", "xx", "--config", str(tmp_path / "n.json")]) == 2
    assert "xx" in capsys.readouterr().err


def test_version(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0 and "0.4.0" in capsys.readouterr().out


def test_wildcards_are_expanded(tmp_path):
    for name in ("b.mp3", "a.mp3", "c.wav"):
        (tmp_path / name).write_bytes(b"")
    expanded = cli.expand_wildcards([tmp_path / "*.mp3", tmp_path / "c.wav", tmp_path / "none*.ogg"])
    # A pattern that matches nothing stays as given, so the user sees "File not found".
    assert [path.name for path in expanded] == ["a.mp3", "b.mp3", "c.wav", "none*.ogg"]
