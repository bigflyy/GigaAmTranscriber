"""The three-thread pipeline (search -> encode -> decode) with a fake model and fake VAD.

The fakes make the pipeline logic testable without ONNX files: order of
segments, GPU batching limits, cancellation, and errors in any stage.
"""

import threading

import numpy as np
import pytest

from gigaam_app import engine
from gigaam_app.asr import Word
from gigaam_app.audio import SAMPLE_RATE
from gigaam_app.vad import WINDOW, ChunkFinder, VadOptions


def speech_pattern(repeats=12, speech=300, pause=100):
    """Window probabilities: 9.6 s of speech, 3.2 s of silence, repeated."""
    one = [0.9] * speech + [0.05] * pause
    return np.array(one * repeats, dtype=np.float32)


class FakeVad:
    def __init__(self, probabilities, block=256):
        self.probabilities, self.block = probabilities, block

    def blocks(self, audio):
        for first in range(0, len(self.probabilities), self.block):
            yield first, self.probabilities[first:first + self.block]


class FakeAsr:
    """Encoder output: one row holding the piece's start sample. Decoder: one token per chunk."""

    device_label = "Fake"

    def __init__(self, on_gpu, fail_on_batch=None):
        self.on_gpu = on_gpu
        self.joins_chunks = on_gpu
        self.batches = []
        self.fail_on_batch = fail_on_batch

    def encode(self, pieces, should_cancel=None):
        if self.fail_on_batch is not None and len(self.batches) == self.fail_on_batch:
            raise RuntimeError("encoder failed")
        self.batches.append([len(piece) for piece in pieces])
        return [np.array([[piece[0]]], dtype=np.float32) for piece in pieces]

    def decode(self, encoded):
        return [(0, 0)]

    def words(self, tokens, offset_seconds):
        return [Word(offset_seconds, offset_seconds + 0.04, f"w{offset_seconds:.1f}")]


def make_transcriber(monkeypatch, probabilities, on_gpu=False, fail_on_batch=None):
    n_samples = len(probabilities) * WINDOW
    # Each sample holds its own index, so the fake encoder can report where a piece starts.
    audio = np.arange(n_samples, dtype=np.float32)
    monkeypatch.setattr(engine, "decode_audio", lambda path: audio)
    transcriber = object.__new__(engine.Transcriber)
    transcriber.model_label = "RNNT"
    transcriber.asr = FakeAsr(on_gpu, fail_on_batch)
    transcriber.vad = FakeVad(probabilities)
    return transcriber, n_samples


def expected_chunks(probabilities, n_samples, options=None):
    finder = ChunkFinder(n_samples, options or VadOptions())
    chunks = []
    for index, probability in enumerate(probabilities.tolist()):
        chunks += finder.feed(index, probability)
    return chunks + finder.finish()


@pytest.mark.parametrize("on_gpu", [False, True])
def test_segments_match_chunks_in_order(monkeypatch, on_gpu):
    probabilities = speech_pattern()
    transcriber, n_samples = make_transcriber(monkeypatch, probabilities, on_gpu)
    seen, progress, stats = [], [], []
    result = transcriber.transcribe("x.wav", on_segment=seen.append,
                                    on_progress=lambda s, r: progress.append((s, r)), on_stats=stats.append)
    chunks = expected_chunks(probabilities, n_samples)
    assert len(chunks) > 3
    assert [(s.start, s.end) for s in result.segments] == \
        [(round(a / SAMPLE_RATE, 3), round(b / SAMPLE_RATE, 3)) for a, b in chunks]
    assert seen == result.segments and not result.cancelled
    assert result.audio_seconds == n_samples / SAMPLE_RATE
    assert len(stats) == 1 and 0 < result.speech_seconds < result.audio_seconds
    assert progress[-1] == (1.0, 1.0)
    assert all(b[1] >= a[1] for a, b in zip(progress, progress[1:]))  # recognised never goes back
    assert sum(len(batch) for batch in transcriber.asr.batches) == len(chunks)
    if not on_gpu:
        assert all(len(batch) == 1 for batch in transcriber.asr.batches)


def test_gpu_batches_respect_limits(monkeypatch):
    # Many short chunks: VAD regions of 1 s separated by 3 s pauses, each grouped alone.
    options = VadOptions(max_duration=1.5, strict_limit_duration=1.5)
    probabilities = speech_pattern(repeats=40, speech=30, pause=95)
    transcriber, _ = make_transcriber(monkeypatch, probabilities, on_gpu=True)
    # Hold the encoder back until search is done, so chunks pile up in the queue.
    gate = threading.Event()
    original = transcriber.asr.encode

    def slow_encode(pieces, should_cancel=None):
        gate.wait(5)
        return original(pieces)

    transcriber.asr.encode = slow_encode
    transcriber.vad = FakeVad(probabilities, block=len(probabilities))
    result = transcriber.transcribe("x.wav", options, on_stats=lambda t: gate.set())
    sizes = [len(batch) for batch in transcriber.asr.batches]
    assert max(sizes) == engine.GPU_BATCH_CHUNKS and len(result.segments) == 40
    for batch in transcriber.asr.batches:
        assert max(batch) * len(batch) <= engine.GPU_BATCH_SECONDS * SAMPLE_RATE


def test_cancel_keeps_finished_segments(monkeypatch):
    transcriber, _ = make_transcriber(monkeypatch, speech_pattern(repeats=30))
    seen = []
    result = transcriber.transcribe("x.wav", on_segment=seen.append, should_cancel=lambda: len(seen) >= 2)
    assert result.cancelled
    assert 2 <= len(result.segments) < 10 and result.segments == seen


def test_encoder_error_is_raised(monkeypatch):
    transcriber, _ = make_transcriber(monkeypatch, speech_pattern(), fail_on_batch=1)
    with pytest.raises(RuntimeError, match="encoder failed"):
        transcriber.transcribe("x.wav")


def test_callback_error_stops_the_workers(monkeypatch):
    transcriber, _ = make_transcriber(monkeypatch, speech_pattern(repeats=30))

    def broken(segment):
        raise KeyError("callback")

    before = threading.active_count()
    with pytest.raises(KeyError):
        transcriber.transcribe("x.wav", on_segment=broken)
    assert threading.active_count() == before


def test_silence_gives_empty_transcript(monkeypatch):
    transcriber, _ = make_transcriber(monkeypatch, np.zeros(2000, dtype=np.float32))
    result = transcriber.transcribe("x.wav")
    assert result.segments == [] and result.speech_seconds == 0 and not result.cancelled
