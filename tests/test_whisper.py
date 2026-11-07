"""Whisper on whisper.cpp: word joining, the ctypes structures, cancelling, and the engine switch.

Most tests use fakes and need neither the libraries nor a model. The library test
runs when tools/build_whisper_cpp.py has built whisper.cpp into third_party/ (or
GIGAAM_WHISPER_LIB points to a build). The real-model test also needs a Whisper model
folder (model.json type "whisper" and the ggml file) beside silero_vad_scan.onnx:

    set GIGAAM_WHISPER_MODEL_ROOT=C:\\path\\models     (holds the folder and the VAD model)
    set GIGAAM_WHISPER_MODEL=whisper_large_v3_turbo_q5_0
"""

import json
import os
from pathlib import Path
import shutil

import numpy as np
import pytest

from gigaam_app import engine, whisper_cpp
from gigaam_app.whisper_cpp import Token
from gigaam_app.whisper_model import WhisperModel, is_whisper_folder, whisper_confidence, words_from_tokens


def tokens(*items):
    """Tokens from (text, start, end); text as str, encoded to UTF-8."""
    return [Token(text.encode("utf-8") if isinstance(text, str) else text, start, end, 1.0)
            for text, start, end in items]


# ------------------------------------------------------------------ words from tokens


def test_tokens_join_into_words_at_leading_spaces():
    words = words_from_tokens(tokens((" При", 0.0, 0.2), ("вет", 0.2, 0.4), (",", 0.4, 0.45),
                                     (" мир", 0.6, 0.9), ("!", 0.9, 0.95)), offset_seconds=10.0)
    assert [(w.start, w.end, w.text) for w in words] == [(10.0, 10.45, "Привет,"), (10.6, 10.95, "мир!")]


def test_character_split_between_tokens_is_joined_before_decoding():
    data = " ж".encode("utf-8")  # b" \xd0\xb6": the Cyrillic letter is two bytes
    words = words_from_tokens(tokens((data[:2], 0.0, 0.1), (data[2:], 0.1, 0.2), (" да", 0.3, 0.5)), 0.0)
    assert [w.text for w in words] == ["ж", "да"]


def test_space_only_token_starts_the_next_word_without_its_time():
    words = words_from_tokens(tokens(("один", 0.0, 0.3), (" ", 0.3, 0.3), ("два", 0.8, 1.0)), 0.0)
    assert [(w.start, w.end, w.text) for w in words] == [(0.0, 0.3, "один"), (0.8, 1.0, "два")]


def test_times_stay_inside_the_chunk_and_in_order():
    words = words_from_tokens(tokens((" a", -0.5, 0.2), (" b", 0.5, 0.4), (" c", 0.3, 0.6), (" d", 2.0, 3.5)),
                              offset_seconds=1.0, duration=3.0)
    starts = [w.start for w in words]
    assert starts == sorted(starts)
    assert words[0].start == 1.0                      # negative token time clamped to the chunk start
    assert all(w.end >= w.start for w in words)       # end before start is lifted to the start
    assert words[-1].end == 4.0                       # past the end of the chunk clamped to it


def test_word_confidence_is_the_lowest_letter_token_and_skips_punctuation():
    cyrillic = "да".encode("utf-8")
    items = [Token(b" " + cyrillic[:1], 0.0, 0.1, 0.7), Token(cyrillic[1:], 0.1, 0.2, 0.9),
             Token(b",", 0.2, 0.2, 0.1), Token(b" no", 0.3, 0.5, 0.95)]
    words = words_from_tokens(items, 0.0)
    # The half of a Cyrillic letter counts; the comma's low probability does not.
    assert [(w.text, w.confidence) for w in words] == [("да,", round(whisper_confidence(0.7), 3)),
                                                       ("no", round(whisper_confidence(0.95), 3))]


def test_whisper_confidence_puts_the_two_marks_where_gigaam_has_them():
    assert whisper_confidence(0.5) == pytest.approx(0.80)
    assert whisper_confidence(0.7) == pytest.approx(0.97)
    assert whisper_confidence(0.0) == 0.0 and whisper_confidence(1.0) == pytest.approx(1.0)
    assert whisper_confidence(1.2) == pytest.approx(1.0) and whisper_confidence(-1) == 0.0
    values = [whisper_confidence(p / 20) for p in range(21)]
    assert values == sorted(values)


def test_no_tokens_no_words():
    assert words_from_tokens([], 5.0) == []
    assert words_from_tokens(tokens((" ", 0.0, 0.0)), 5.0) == []


# ------------------------------------------------------------------ ctypes structures


def test_layout_check_rejects_a_zeroed_structure():
    assert not whisper_cpp.check_layout(whisper_cpp.FullParams())


def test_preferred_gpu_takes_a_discrete_card_first():
    integrated = (whisper_cpp.DEVICE_IGPU, "Vulkan0", "Radeon 780M", 0)
    discrete = (whisper_cpp.DEVICE_GPU, "Vulkan1", "RTX 4070", 0)
    assert whisper_cpp.preferred_gpu([integrated, discrete]) == 1
    assert whisper_cpp.preferred_gpu([integrated]) == 0
    assert whisper_cpp.preferred_gpu([]) is None


def built_library_dir():
    folder = whisper_cpp.library_dir()
    name = "whisper.dll" if os.name == "nt" else "libwhisper.so*"
    return folder if list(folder.glob(name)) else None


needs_library = pytest.mark.skipif(built_library_dir() is None,
                                   reason="whisper.cpp not built (tools/build_whisper_cpp.py)")


@needs_library
def test_library_loads_with_the_expected_layout_and_a_cpu_backend():
    library = whisper_cpp.Library.get()  # raises if check_layout fails
    assert library.version.startswith(whisper_cpp.WHISPER_CPP_VERSION)
    assert "CPU" in library.backends()
    assert any(kind == whisper_cpp.DEVICE_CPU for kind, *_ in library.devices())


# ------------------------------------------------------------------ the model with a fake context


class FakeContext:
    """Stands in for whisper_cpp.Context: one token per call; cancels on request."""

    def __init__(self, cancel_on=None):
        self.calls = []
        self.prompts = []
        self.cancel_on = cancel_on

    def transcribe(self, samples, language=None, n_threads=4, should_cancel=None, prompt=None):
        if self.cancel_on is not None and len(self.calls) == self.cancel_on:
            raise whisper_cpp.Cancelled()
        self.calls.append((len(samples), language))
        self.prompts.append(prompt)
        return "ru", tokens((f" w{len(self.calls)}", 0.1, 0.3))

    def is_language(self, code):
        return code in ("ru", "en")


def fake_model(context, language=None):
    model = object.__new__(WhisperModel)
    model.context, model.gpu_name, model.cpu_threads = context, None, 2
    model.language, model.last_language = language, ""
    return model


def test_encode_recognises_every_chunk_and_passes_the_language():
    model = fake_model(FakeContext(), language="en")
    results = model.encode([np.zeros(16000, np.float32), np.zeros(8000, np.float32)])
    assert [r[2] for r in results] == [1.0, 0.5]
    assert model.context.calls == [(16000, "en"), (8000, "en")]
    words = model.words(model.decode(results[1]), offset_seconds=2.0)
    assert [(w.start, w.end, w.text) for w in words] == [(2.1, 2.3, "w2")]


def test_prompt_goes_to_every_chunk_and_reread_piece_uses_it():
    from gigaam_app import fix
    model = fake_model(FakeContext())
    model.encode([np.zeros(100, np.float32)] * 2, prompt="LLM, fine tuning")
    assert model.context.prompts == ["LLM, fine tuning"] * 2
    words = fix.reread_piece(model, np.zeros(1600, np.float32), 10.0, prompt="DeepSeek")
    assert model.context.prompts[-1] == "DeepSeek"
    assert [(w.start, w.text) for w in words] == [(10.1, "w3")]


def test_auto_language_is_sent_as_none():
    model = fake_model(FakeContext(), language="auto")
    model.encode([np.zeros(100, np.float32)])
    assert model.context.calls == [(100, None)]


def test_cancel_returns_the_chunks_finished_before_it():
    model = fake_model(FakeContext(cancel_on=1))
    results = model.encode([np.zeros(10, np.float32)] * 3, should_cancel=lambda: True)
    assert len(results) == 1


def test_unknown_language_is_refused():
    model = fake_model(FakeContext())
    model.set_language("ru")
    with pytest.raises(ValueError):
        model.set_language("xx")


def write_whisper_folder(folder, size=4):
    folder.mkdir(parents=True)
    (folder / "ggml-model.bin").write_bytes(b"\0" * size)
    meta = {"format": 1, "name": folder.name, "type": "whisper", "sample_rate": 16000,
            "files": {"model": {"name": "ggml-model.bin", "size": size, "sha256": "0" * 64}}}
    (folder / "model.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def test_whisper_folder_is_recognised(tmp_path):
    assert is_whisper_folder(write_whisper_folder(tmp_path / "whisper"))
    (tmp_path / "gigaam").mkdir()
    (tmp_path / "gigaam" / "model.json").write_text('{"type": "rnnt"}', encoding="utf-8")
    assert not is_whisper_folder(tmp_path / "gigaam")
    assert not is_whisper_folder(tmp_path / "missing")


def test_damaged_model_file_is_reported(tmp_path):
    folder = write_whisper_folder(tmp_path / "whisper")
    (folder / "ggml-model.bin").write_bytes(b"\0")
    with pytest.raises(RuntimeError, match="missing or damaged"):
        WhisperModel(folder, library=object())


def test_transcriber_opens_a_whisper_folder_with_the_whisper_model(tmp_path, monkeypatch):
    write_whisper_folder(tmp_path / "whisper")
    opened = {}

    class Recorder:
        joins_chunks = False
        device_label = "Fake"

        def __init__(self, folder, device, cpu_threads, language):
            opened.update(folder=Path(folder), device=device, language=language)

    monkeypatch.setattr(engine, "WhisperModel", Recorder)
    monkeypatch.setattr(engine, "create_session", lambda *args, **kwargs: (None, "CPUExecutionProvider"))
    monkeypatch.setattr(engine, "SileroVad", lambda session: None)
    transcriber = engine.Transcriber("whisper", device="cpu", model_root=tmp_path, language="en")
    assert isinstance(transcriber.asr, Recorder)
    assert opened == {"folder": tmp_path / "whisper", "device": "cpu", "language": "en"}


def test_chunks_are_kept_inside_the_whisper_window():
    transcriber = object.__new__(engine.Transcriber)
    transcriber.asr = fake_model(FakeContext())
    fitted = transcriber._fit_options(engine.VadOptions(max_duration=40, strict_limit_duration=45, vad_max_speech_s=20))
    assert (fitted.max_duration, fitted.strict_limit_duration, fitted.vad_max_speech_s) == (30.0, 30.0, 20)


# ------------------------------------------------------------------ the real model


MODEL_ROOT = os.environ.get("GIGAAM_WHISPER_MODEL_ROOT")
MODEL = os.environ.get("GIGAAM_WHISPER_MODEL", "whisper_large_v3_turbo_q5_0")
needs_model = pytest.mark.skipif(
    built_library_dir() is None or not MODEL_ROOT or not (Path(MODEL_ROOT or ".") / MODEL / "model.json").is_file()
    or shutil.which("ffmpeg") is None,
    reason="set GIGAAM_WHISPER_MODEL_ROOT (and GIGAAM_WHISPER_MODEL) to run Whisper on a real model")


@needs_model
def test_real_model_transcribes_speech_with_word_times(tmp_path):
    """A short spoken file: generated by ffmpeg's flite voice when present, else the first
    10 s of GIGAAM_PARITY_AUDIO; the test checks structure, not exact words."""
    import subprocess
    audio = tmp_path / "speech.wav"
    source = os.environ.get("GIGAAM_PARITY_AUDIO")
    if not source:
        pytest.skip("set GIGAAM_PARITY_AUDIO to a recording with speech")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source, "-t", "20", "-ac", "1", "-ar", "16000", str(audio)],
                   check=True)
    transcriber = engine.Transcriber(MODEL, device=os.environ.get("GIGAAM_PARITY_DEVICE", "auto"),
                                     model_root=MODEL_ROOT, language="auto")
    transcript = transcriber.transcribe(audio)
    assert transcript.segments and transcript.text.strip()
    for segment in transcript.segments:
        assert segment.words
        assert segment.start - 0.01 <= segment.words[0].start <= segment.words[-1].end <= segment.end + 0.01
    assert transcriber.asr.last_language
