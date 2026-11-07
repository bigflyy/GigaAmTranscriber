"""Settings file: defaults, v0.1 files, validation and a save/load round trip."""

import json

import pytest

from gigaam_app import config
from gigaam_app.vad import VadOptions


def test_missing_file_gives_defaults(tmp_path):
    settings = config.load(tmp_path / "none.json")
    assert settings == config.Settings()
    assert settings.model == "RNNT" and settings.device == "Auto" and settings.outputs == ["txt", "timestamps"]


def test_v01_file_loads(tmp_path):
    path = tmp_path / "gigaam-config.json"
    # A v0.1 file as the old GUI wrote it, with a byte order mark, CUDA and retired keys.
    data = {"version": 1, "model": "CTC", "device": "CUDA", "cpu_threads": 4, "include_timestamps": True,
            "vad_threshold": 0.4, "vad_min_speech_ms": 300, "vad_max_speech_s": 20.0,
            "vad_min_silence_ms": 1500, "vad_speech_pad_ms": 200, "new_chunk_threshold": 0.2,
            "max_duration": 22.0, "strict_limit_duration": 25.0, "min_duration": 5.0,
            "vad_window_samples": 512, "some_future_key": "ignored"}
    path.write_text(json.dumps(data), encoding="utf-8-sig")
    settings = config.load(path)
    assert settings.model == "CTC" and settings.device == "GPU" and settings.engine_device == "gpu"
    assert settings.cpu_threads == 4 and settings.include_timestamps is True
    assert settings.vad == VadOptions(vad_threshold=0.4, vad_max_speech_s=20.0, vad_min_silence_ms=1500,
                                      vad_speech_pad_ms=200, max_duration=22.0)


def test_round_trip(tmp_path):
    path = tmp_path / "gigaam-config.json"
    original = config.Settings(model="CTC", device="CPU", cpu_threads=6, outputs=["srt", "json"],
                               vad=VadOptions(vad_threshold=0.6, vad_min_speech_ms=250))
    config.save(original, path)
    assert config.load(path) == original
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 2 and data["vad_threshold"] == 0.6 and "vad" not in data
    assert [item.name for item in tmp_path.iterdir()] == ["gigaam-config.json"]  # no temporary left


def test_example_config_in_repository_is_valid():
    settings = config.load(config.app_dir() / "gigaam-config.example.json")
    assert settings.model in ("RNNT", "CTC")


@pytest.mark.parametrize("old", ["Multilingual CTC (220M)", "Multilingual CTC Large (600M)"])
def test_dropped_multilingual_models_load_as_rnnt(old):
    # v0.1 offered these; a settings file that chose one still opens.
    settings = config.parse({"version": 1, "model": old})
    assert settings.model == "RNNT" and json.loads(settings.to_json())["model"] == "RNNT"


def test_whisper_and_its_language_load():
    settings = config.parse({"model": "Whisper", "language": "en"})
    assert (settings.model, settings.language) == ("Whisper", "en")
    assert config.parse({}).language == "auto"
    assert json.loads(settings.to_json())["language"] == "en"


def test_doubt_marks_default_on_and_round_trip():
    assert (config.Settings().doubt_marks, config.Settings().doubt_style) == (True, "underline")
    settings = config.parse({"doubt_marks": False, "doubt_style": "colors", "doubt_light": 0.9, "doubt_strong": 0.5})
    again = config.parse(json.loads(settings.to_json()))
    assert (again.doubt_marks, again.doubt_style, again.doubt_light, again.doubt_strong) == (False, "colors", 0.9, 0.5)
    assert (config.Settings().doubt_light, config.Settings().doubt_strong) == (0.97, 0.80)


def test_vad_ints_stay_ints():
    settings = config.parse({"vad_min_speech_ms": 300.0, "max_duration": 20})
    assert type(settings.vad.vad_min_speech_ms) is int and type(settings.vad.max_duration) is float


@pytest.mark.parametrize("data, message", [
    ([], "JSON object"),
    ({"version": 3}, "version"),
    ({"model": "Parakeet"}, "model"),
    ({"language": "English"}, "language"),
    ({"language": ""}, "language"),
    ({"language": 1}, "language"),
    ({"device": "TPU"}, "device"),
    ({"cpu_threads": -1}, "cpu_threads"),
    ({"cpu_threads": 2.5}, "cpu_threads"),
    ({"cpu_threads": True}, "cpu_threads"),
    ({"include_timestamps": "yes"}, "include_timestamps"),
    ({"doubt_marks": 1}, "doubt_marks"),
    ({"doubt_style": "bold"}, "doubt_style"),
    ({"doubt_light": 0}, "doubt_light"),
    ({"doubt_light": 1.5}, "doubt_light"),
    ({"doubt_strong": "0.8"}, "doubt_strong"),
    ({"doubt_light": 0.7, "doubt_strong": 0.8}, "below doubt_light"),
    ({"outputs": []}, "outputs"),
    ({"outputs": ["txt", "docx"]}, "outputs"),
    ({"vad_threshold": 0}, "vad_threshold"),
    ({"vad_threshold": 1.5}, "vad_threshold"),
    ({"vad_threshold": "0.5"}, "vad_threshold"),
    ({"vad_min_speech_ms": 12.5}, "whole number"),
    ({"vad_speech_pad_ms": -10}, "non-negative"),
    ({"max_duration": float("inf")}, "max_duration"),
    ({"max_duration": 0}, "max_duration"),
    ({"vad_max_speech_s": 0}, "vad_max_speech_s"),
])
def test_invalid_values_are_rejected(data, message):
    with pytest.raises(ValueError, match=message):
        config.parse(data)


def test_duplicate_outputs_are_merged():
    assert config.parse({"outputs": ["txt", "srt", "txt"]}).outputs == ["txt", "srt"]
