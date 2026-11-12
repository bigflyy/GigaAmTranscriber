"""The model process frees DirectML models only all together (plan 08 C3f).

ONNX Runtime 1.23's DirectML provider crashes the process when another DirectML session
runs after the newest one was freed, so Worker never frees one DirectML model alone.
These tests use stand-ins for the models: no ONNX Runtime, no video card.
"""
import queue
from types import SimpleNamespace

import pytest

from gigaam_app import worker as worker_module
from gigaam_app.worker import Worker, _uses_directml

DML = "DmlExecutionProvider"
CPU = "CPUExecutionProvider"


class FakeTranscriber:
    """A Transcriber stand-in: GigaAM models on "auto" use DirectML, Whisper never does
    (whisper.cpp runs on Vulkan or the CPU, with no ONNX session of its own)."""

    def __init__(self, model, device="auto", cpu_threads=None):
        on_directml = device == "auto" and model != "Whisper"
        self.asr = SimpleNamespace(provider=DML if on_directml else CPU) if model != "Whisper" else SimpleNamespace()
        self.device_label = "GPU (DirectML)" if on_directml else "CPU"
        self.load_seconds = 0.0


def speakers(provider):
    """A loaded speaker model as Worker keeps it: (device, threads, model)."""
    return ("auto", 0, SimpleNamespace(provider=provider, segmentation_provider=provider))


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setattr(worker_module, "Transcriber", FakeTranscriber)
    return Worker(queue.Queue())


def test_uses_directml_looks_at_gigaam_and_speaker_sessions():
    assert _uses_directml(FakeTranscriber("RNNT", "auto"))
    assert not _uses_directml(FakeTranscriber("RNNT", "cpu"))
    assert not _uses_directml(FakeTranscriber("Whisper", "auto"))
    assert _uses_directml(speakers(DML)[2])
    assert not _uses_directml(speakers(CPU)[2])


def test_replacing_a_directml_main_model_frees_every_directml_model(worker):
    # The crash the owner hit (2026-11-12): speakers on, model Whisper -> RNNT -> Whisper.
    worker._ensure(("RNNT", "auto", 0))
    worker.speaker_model = speakers(DML)
    worker.spare[("CTC", "auto", 0)] = FakeTranscriber("CTC", "auto")
    whisper_spare = FakeTranscriber("Whisper", "auto")
    worker.spare[("Whisper", "auto", 0)] = whisper_spare
    worker._ensure(("Whisper", "cpu", 0))
    assert worker.speaker_model is None                       # loads again at the next "diarize"
    assert ("CTC", "auto", 0) not in worker.spare
    assert worker.spare[("Whisper", "auto", 0)] is whisper_spare  # no DirectML: kept
    assert worker.engine_key == ("Whisper", "cpu", 0) and worker.engine is not None


def test_replacing_a_main_model_without_directml_keeps_the_others(worker):
    worker._ensure(("Whisper", "auto", 0))
    worker.speaker_model = speakers(DML)
    worker.spare[("RNNT", "auto", 0)] = FakeTranscriber("RNNT", "auto")
    worker._ensure(("Whisper", "auto", 4))
    assert worker.speaker_model is not None
    assert ("RNNT", "auto", 0) in worker.spare


def test_a_main_model_moved_to_the_spares_frees_nothing(worker):
    worker._ensure(("RNNT", "auto", 0))
    worker.speaker_model = speakers(DML)
    worker.spare[("Whisper", "auto", 0)] = FakeTranscriber("Whisper", "auto")
    worker._ensure(("Whisper", "auto", 0))                    # swap: RNNT goes to the spares
    assert worker.speaker_model is not None
    assert _uses_directml(worker.spare[("RNNT", "auto", 0)])


def test_dropping_a_directml_spare_frees_the_directml_main_model_too(worker):
    worker._ensure(("CTC", "auto", 0))
    worker.speaker_model = speakers(DML)
    worker.spare[("RNNT", "auto", 0)] = FakeTranscriber("RNNT", "auto")
    engine = worker._engine_for(("RNNT", "cpu", 0))           # another device: the old spare goes
    assert not _uses_directml(engine)
    assert worker.engine is None                              # the next file loads CTC again
    assert worker.speaker_model is None
    assert list(worker.spare) == [("RNNT", "cpu", 0)]
    worker._ensure(("CTC", "auto", 0))
    assert worker.engine is not None


def test_replacing_directml_speaker_models_frees_the_directml_main_model(worker, monkeypatch, tmp_path):
    import numpy as np

    from gigaam_app import catalog, diarize

    class FakeSpeakerModel:
        def __init__(self, folder, device="auto", cpu_threads=None):
            self.provider = self.segmentation_provider = DML if device == "auto" else CPU

        def diarize(self, audio, num_speakers=None, on_progress=None, should_cancel=None):
            return diarize.Diarization(exclusive_turns=[], speakers=0, found=0)

    monkeypatch.setattr(diarize, "SpeakerModel", FakeSpeakerModel)
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path)
    monkeypatch.setattr(worker_module, "decode_audio", lambda path: np.zeros(16000, dtype=np.float32))
    worker._ensure(("RNNT", "auto", 0))
    worker._diarize(1, "a.wav", "auto", 0)
    assert worker.engine is not None                          # first load: nothing freed
    worker._diarize(2, "a.wav", "auto", 4)                    # other thread count: reloaded
    assert worker.engine is None
    assert worker.speaker_model[:2] == ("auto", 4)
