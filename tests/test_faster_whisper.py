"""faster-whisper (plan 08 C2): word joining, batched reading, the engine switch, the catalog entry.

The fakes need neither CTranslate2 nor a model. The real-model test runs when
GIGAAM_FW_MODEL points to a faster-whisper model folder (with model.json, type
"faster-whisper") and GIGAAM_PARITY_AUDIO to a recording with speech; it loads a 0.8 GB
model, so run it through the work queue.
"""

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from gigaam_app import catalog, engine, fix
from gigaam_app.faster_whisper_model import FasterWhisperModel, is_fast_whisper_folder, words_from_fw


def fw_word(text, start, end, probability=1.0):
    return SimpleNamespace(word=text, start=start, end=end, probability=probability)


# ------------------------------------------------------------------ words

def test_words_get_file_times_and_hyphen_pieces_join_the_word_before():
    words = words_from_fw([fw_word(" Про", 0.0, 0.3), fw_word(" LLM", 0.4, 0.7, 0.9),
                           fw_word("-агентов", 0.7, 1.2, 0.4), fw_word(" говорим.", 1.3, 1.8)], 10.0)
    assert [(w.start, w.end, w.text) for w in words] == [(10.0, 10.3, "Про"), (10.4, 11.2, "LLM-агентов"),
                                                         (11.3, 11.8, "говорим.")]
    # The joined word keeps the lowest confidence of its pieces (0.4 -> below 0.80 on the GigaAM scale).
    assert words[1].confidence < 0.80 and words[0].confidence == 1.0


def test_times_stay_inside_the_piece_and_in_order():
    words = words_from_fw([fw_word(" a", 0.5, 0.9), fw_word(" b", 0.3, 0.4), fw_word(" c", 1.8, 2.6)], 0.0, duration=2.0)
    assert [(w.start, w.end) for w in words] == [(0.5, 0.9), (0.5, 0.5), (1.8, 2.0)]


def test_empty_words_are_skipped():
    assert words_from_fw([fw_word(" ", 0.0, 0.1)], 0.0) == []


# ------------------------------------------------------------------ the model with fakes

class FakeFw:
    """Stands in for faster_whisper.WhisperModel: one word per piece, records the calls."""

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append((len(audio), options))
        number = len(self.calls)
        segments = iter([SimpleNamespace(words=[fw_word(f" w{number}", 0.1, 0.3)])])
        return segments, SimpleNamespace(language=options.get("language") or "ru")


class FakePipeline:
    """Stands in for BatchedInferencePipeline: one word in the middle of every clip."""

    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append((len(audio), options))
        segments = [SimpleNamespace(words=[fw_word(f" c{index}", clip["start"] + 0.1, clip["start"] + 0.2)])
                    for index, clip in enumerate(options["clip_timestamps"])]
        return iter(segments), SimpleNamespace(language=options.get("language") or "en")


def fake_model(language=None):
    model = object.__new__(FasterWhisperModel)
    model.model, model.pipeline = FakeFw(), FakePipeline()
    model.cpu_threads, model.known_languages = 2, {"ru", "en"}
    model.language, model.last_language = language, ""
    return model


def test_encode_reads_each_piece_with_the_app_settings():
    model = fake_model(language="ru")
    results = model.encode([np.zeros(16000, np.float32), np.zeros(8000, np.float32)], prompt="LLM")
    assert [r[2] for r in results] == [1.0, 0.5]
    lengths = [length for length, _ in model.model.calls]
    assert lengths == [16000, 8000]
    options = model.model.calls[0][1]
    assert options["language"] == "ru" and options["beam_size"] == 1 and options["initial_prompt"] == "LLM"
    assert options["condition_on_previous_text"] is False and options["word_timestamps"] and not options["vad_filter"]
    words = model.words(model.decode(results[1]), offset_seconds=2.0)
    assert [(w.start, w.end, w.text) for w in words] == [(2.1, 2.3, "w2")]


def test_auto_language_is_sent_as_none_and_unknown_is_refused():
    model = fake_model(language="auto")
    model.encode([np.zeros(100, np.float32)])
    assert model.model.calls[0][1]["language"] is None
    with pytest.raises(ValueError):
        model.set_language("xx")


def test_cancel_returns_the_pieces_finished_before_it():
    model = fake_model()
    asked = []

    def cancel():
        asked.append(1)
        return len(asked) > 2  # before piece 1, after its segment, then before piece 2

    assert len(model.encode([np.zeros(10, np.float32)] * 3, should_cancel=cancel)) == 1


def test_reread_piece_works_with_this_model():
    model = fake_model()
    words = fix.reread_piece(model, np.zeros(1600, np.float32), 10.0, prompt="DeepSeek")
    assert model.model.calls[-1][1]["initial_prompt"] == "DeepSeek"
    assert [(w.start, w.text) for w in words] == [(10.1, "w1")]


def test_read_many_puts_pieces_end_to_end_and_gives_each_its_own_words():
    model = fake_model(language="ru")
    pieces = [np.zeros(16000, np.float32), np.zeros(32000, np.float32), np.zeros(8000, np.float32)]
    results = model.read_many(pieces, offsets=[100.0, 200.0, 300.0], prompt="ARP")
    length, options = model.pipeline.calls[0]
    assert length == 56000 and options["batch_size"] == 8 and options["initial_prompt"] == "ARP"
    assert options["clip_timestamps"] == [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 3.0},
                                          {"start": 3.0, "end": 3.5}]
    assert options["language"] == "ru" and options["beam_size"] == 1 and options["word_timestamps"]
    # Each word is moved back into its own piece, then to the piece's place in the file.
    assert [[(w.start, w.text) for w in words] for words in results] == [[(100.1, "c0")], [(200.1, "c1")],
                                                                         [(300.1, "c2")]]
    assert model.read_many([], []) == []


# ------------------------------------------------------------------ the worker's search job

def run_suggest(engine_asr, job_parts, models=("faster-whisper",)):
    """Worker._suggest with fake audio cuts (each piece 1 s from its window's start) and a
    fake engine; returns the events."""
    import queue
    from gigaam_app.worker import Worker
    events = queue.Queue()
    worker = Worker(events)
    worker._cut = lambda path, windows: (np.zeros(16000, np.float32), windows[0][0])
    engine_stub = SimpleNamespace(asr=engine_asr, uses_language=True, set_language=engine_asr.set_language)
    worker._engine_for = lambda key, on_load=None: engine_stub
    (windows, language), more = job_parts[0], tuple(job_parts[1:])
    worker._suggest(7, "file.mp3", windows, list(models), "cpu", 4, language, "LLM", more)
    return [events.get_nowait() for _ in range(events.qsize())]


def test_worker_reads_a_batch_in_one_call_and_sends_each_piece_its_words():
    model = fake_model()
    events = run_suggest(model, [(((10.0, 11.0), (12.0, 13.0)), "ru"), (((20.0, 21.0), (22.0, 23.0)), "ru")])
    assert len(model.pipeline.calls) == 1 and model.model.calls == []
    assert model.pipeline.calls[0][1]["language"] == "ru" and model.pipeline.calls[0][1]["initial_prompt"] == "LLM"
    results = [event for event in events if event[0] == "suggest_result"]
    assert [(event[5], [(w.start, w.text) for w in event[3]]) for event in results] == [
        (0, [(10.1, "c0")]), (1, [(20.1, "c1")])]
    assert [event[0] for event in events] == ["suggest_range", "suggest_range", "suggest_result", "suggest_result",
                                              "suggest_done"]


def test_worker_reads_a_single_piece_one_at_a_time():
    model = fake_model()
    events = run_suggest(model, [(((10.0, 11.0), (12.0, 13.0)), None)])
    assert model.pipeline.calls == [] and len(model.model.calls) == 1
    assert model.model.calls[0][1]["language"] is None
    [result] = [event for event in events if event[0] == "suggest_result"]
    assert result[2] == "faster-whisper" and result[5] == 0 and [w.text for w in result[3]] == ["w1"]


def test_worker_reports_a_failing_model_for_every_piece():
    model = fake_model()
    model.read_many = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("out of memory"))
    events = run_suggest(model, [(((10.0, 11.0), (12.0, 13.0)), "ru"), (((20.0, 21.0), (22.0, 23.0)), "ru")])
    results = [event for event in events if event[0] == "suggest_result"]
    assert [(event[3], event[4], event[5]) for event in results] == [(None, "out of memory", 0),
                                                                     (None, "out of memory", 1)]
    assert events[-1] == ("suggest_done", 7)


# ------------------------------------------------------------------ folders and the catalog

def write_fw_folder(folder, size=4):
    folder.mkdir(parents=True)
    (folder / "model.bin").write_bytes(b"\0" * size)
    meta = {"format": 1, "name": folder.name, "type": "faster-whisper", "sample_rate": 16000,
            "files": {"model": {"name": "model.bin", "size": size, "sha256": "0" * 64}}}
    (folder / "model.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def test_folder_is_recognised_and_a_damaged_file_reported(tmp_path):
    folder = write_fw_folder(tmp_path / "fw")
    assert is_fast_whisper_folder(folder)
    assert not is_fast_whisper_folder(tmp_path / "missing")
    (folder / "model.bin").write_bytes(b"\0")
    with pytest.raises(RuntimeError, match="missing or damaged"):
        FasterWhisperModel(folder)


def test_gpu_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="processor"):
        FasterWhisperModel(write_fw_folder(tmp_path / "fw"), device="gpu")


def test_transcriber_opens_a_faster_whisper_folder(tmp_path, monkeypatch):
    write_fw_folder(tmp_path / "fw")
    opened = {}

    class Recorder:
        joins_chunks = False
        device_label = "CPU"

        def __init__(self, folder, device, cpu_threads, language):
            opened.update(folder=Path(folder), device=device, language=language)

        def set_language(self, language):
            pass

    monkeypatch.setattr(engine, "FasterWhisperModel", Recorder)
    monkeypatch.setattr(engine, "create_session", lambda *args, **kwargs: (None, "CPUExecutionProvider"))
    monkeypatch.setattr(engine, "SileroVad", lambda session: None)
    transcriber = engine.Transcriber("fw", device="cpu", model_root=tmp_path, language="ru")
    assert isinstance(transcriber.asr, Recorder) and transcriber.uses_language
    assert opened == {"folder": tmp_path / "fw", "device": "cpu", "language": "ru"}


def test_catalog_entry_is_found_by_key_but_not_in_the_model_list():
    info = catalog.find("faster-whisper")
    assert info is catalog.FAST_WHISPER_MODEL and info not in catalog.CATALOG
    assert info.model_type == "faster-whisper" and not info.bundled
    names = {file.name for file in info.files}
    assert names == {"model.bin", "config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.json"}
    assert len({file.role for file in info.files}) == len(info.files)  # one key each in model.json
    for file in info.files:
        assert info.urls(file)[0].startswith("https://github.com/")
        assert info.urls(file)[1].startswith("https://huggingface.co/Zoont/") and "/resolve/846f747" in info.urls(file)[1]
    assert set(catalog.manifest(info)["files"]) == {"model", "config", "preprocessor", "tokenizer", "vocabulary"}


def test_vendored_package_imports_without_av_or_huggingface_hub():
    import gigaam_app.faster_whisper as vendored
    assert vendored.__version__ == "1.2.1"
    assert "av" not in sys.modules and "huggingface_hub" not in sys.modules


# ------------------------------------------------------------------ the real model

FW_MODEL = os.environ.get("GIGAAM_FW_MODEL")
needs_model = pytest.mark.skipif(not FW_MODEL or not (Path(FW_MODEL or ".") / "model.json").is_file()
                                 or not os.environ.get("GIGAAM_PARITY_AUDIO"),
                                 reason="set GIGAAM_FW_MODEL and GIGAAM_PARITY_AUDIO to run faster-whisper on a real model")


@needs_model
def test_real_model_reads_one_piece_and_a_batch_with_word_times():
    from gigaam_app.audio import SAMPLE_RATE, decode_range
    samples = decode_range(os.environ["GIGAAM_PARITY_AUDIO"], 0.0, 20.0)
    model = FasterWhisperModel(FW_MODEL, cpu_threads=4, language="ru")
    one = model.words(model.encode([samples[:10 * SAMPLE_RATE]])[0], 0.0)
    assert one and all(0.0 <= w.start <= w.end <= 10.0 for w in one)
    many = model.read_many([samples[:10 * SAMPLE_RATE], samples[10 * SAMPLE_RATE:]], offsets=[0.0, 10.0])
    assert len(many) == 2 and all(many)
    assert all(10.0 <= w.start <= 20.0 for w in many[1])
