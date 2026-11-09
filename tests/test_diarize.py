"""Speaker labelling maths (gigaam_app.diarize) without the models.

The pieces that stand in for scipy and sklearn are checked against plain,
slow versions written here from their definitions.
"""
from itertools import permutations

import numpy as np
import pytest

from gigaam_app import diarize
from gigaam_app.diarize import Turn


def naive_centroid_clusters(x, threshold):
    """Centroid-linkage AHC from the definition: merge the two clusters with the closest
    centroids until the closest pair is farther than the threshold."""
    clusters = [[i] for i in range(len(x))]
    while len(clusters) > 1:
        centres = [x[c].mean(axis=0) for c in clusters]
        best = None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = np.linalg.norm(centres[a] - centres[b])
                if best is None or d < best[0]:
                    best = (d, a, b)
        if best[0] > threshold:
            break
        _, a, b = best
        clusters[a] = clusters[a] + clusters[b]
        del clusters[b]
    labels = np.zeros(len(x), dtype=int)
    for k, members in enumerate(clusters):
        labels[members] = k
    return labels


def same_partition(a, b):
    return all((a[i] == a[j]) == (b[i] == b[j]) for i in range(len(a)) for j in range(len(a)))


@pytest.mark.parametrize("seed", range(6))
def test_centroid_linkage_matches_the_definition(seed):
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(4, 8))
    x = np.vstack([c + 0.35 * rng.normal(size=(12, 8)) for c in centres])
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    for threshold in (0.3, 0.6, 0.9):
        assert same_partition(diarize.centroid_linkage_clusters(x, threshold), naive_centroid_clusters(x, threshold))


def test_centroid_linkage_single_point_and_far_points():
    assert list(diarize.centroid_linkage_clusters(np.ones((1, 3)), 0.6)) == [0]
    far = np.eye(3) * 10
    assert len(set(diarize.centroid_linkage_clusters(far, 0.6))) == 3


@pytest.mark.parametrize("clusters", [1, 2, 3, 5])
def test_constrained_argmax_is_the_best_assignment(clusters):
    rng = np.random.default_rng(clusters)
    scores = rng.random((20, 3, clusters))
    hard = diarize.constrained_argmax(scores)
    for chunk in range(20):
        best = max(
            (sum(scores[chunk, s, k] for s, k in pairs), pairs)
            for pairs in (
                [tuple(zip(range(3), p)) for p in permutations(range(clusters), 3)] if clusters >= 3 else
                [tuple(zip(p, range(clusters))) for p in permutations(range(3), clusters)]
            )
        )[1]
        expected = np.full(3, -2)
        for s, k in best:
            expected[s] = k
        assert list(hard[chunk]) == list(expected)
        assigned = [k for k in hard[chunk] if k >= 0]
        assert len(assigned) == len(set(assigned))


def test_vbx_keeps_two_clear_groups():
    rng = np.random.default_rng(0)
    x = np.vstack([rng.normal(3, 1, size=(30, 16)), rng.normal(-3, 1, size=(30, 16))])
    init = np.zeros(60, dtype=int)
    init[::2] = 1  # a poor start: VBx must sort it out
    init[:5] = 2
    gamma, pi = diarize.vbx(init, x, np.ones(16) * 4.0, fa=0.07, fb=0.8)
    labels = gamma[:, pi > 1e-7].argmax(axis=1)
    assert len(set(labels[:30])) == 1 and len(set(labels[30:])) == 1 and labels[0] != labels[-1]


def test_kmeans_finds_the_groups():
    rng = np.random.default_rng(1)
    x = np.vstack([rng.normal(c, 0.1, size=(20, 2)) for c in ((0, 0), (5, 5), (0, 5))])
    labels = diarize.kmeans(x, 3)
    assert sorted(np.bincount(labels)) == [20, 20, 20]
    assert all(len(set(labels[i:i + 20])) == 1 for i in (0, 20, 40))


def test_runs_become_turns_at_frame_middles():
    binary = np.array([[0, 1], [1, 1], [1, 0], [0, 0], [1, 0]], dtype=float)
    middles = np.array([0.5, 1.5, 2.5, 3.5, 4.5])
    runs = sorted(diarize._runs(binary, middles))
    assert runs == [(0.5, 2.5, 1), (1.5, 3.5, 0), (4.5, 4.5, 0)]


def test_words_get_the_speaker_with_most_time_or_the_nearest():
    turns = [Turn(0.0, 2.0, 0), Turn(2.0, 5.0, 1), Turn(8.0, 9.0, 0)]
    words = [(0.5, 1.0), (1.8, 2.6), (6.0, 6.5), (7.5, 7.9)]
    assert diarize.words_speakers(words, turns) == [0, 1, 1, 0]
    assert diarize.words_speakers(words, []) == [None] * 4


def test_nearest_follows_torch_interpolate():
    masks = np.arange(10, dtype=np.float32).reshape(1, 10, 1)
    assert list(diarize._nearest(masks, 4)[0, :, 0]) == [0, 2, 5, 7]   # floor(i * 10 / 4)


def test_chunk_starts_cover_the_end():
    model = diarize.SpeakerModel.__new__(diarize.SpeakerModel)
    sr = diarize.SAMPLE_RATE
    assert list(model._chunk_starts(5 * sr, sr)) == [0]
    assert list(model._chunk_starts(10 * sr, sr)) == [0]
    assert list(model._chunk_starts(12 * sr, sr)) == [0, sr, 2 * sr]
    assert list(model._chunk_starts(int(12.5 * sr), 2 * sr)) == [0, 2 * sr, 4 * sr]


def test_fbank_shape_and_silence_floor():
    model = diarize.SpeakerModel.__new__(diarize.SpeakerModel)
    model.mel_banks = diarize._mel_banks()
    model.hamming = np.hamming(diarize.FBANK_LENGTH)
    bank = model._fbank(np.zeros(diarize.WINDOW_SAMPLES, dtype=np.float32))
    assert bank.shape == (998, 80)
    assert np.allclose(bank, np.log(np.finfo(np.float32).eps))


# ---------------------------------------------------------------------- words and the worker job

def line(*items):
    from gigaam_app.engine import Segment
    from gigaam_app.asr import Word
    words = [Word(start=start, end=end, text=text) for text, start, end in items]
    return Segment(start=words[0].start, end=words[-1].end, text=" ".join(w.text for w in words), words=words)


def test_assign_speakers_numbers_by_first_word_and_keeps_names():
    segments = [line(("а", 0.0, 0.5), ("б", 0.6, 1.0)), line(("в", 3.0, 3.5), ("г", 6.0, 6.4))]
    turns = [Turn(0.0, 2.0, 5), Turn(2.5, 4.0, 2), Turn(5.5, 7.0, 5), Turn(9.0, 9.5, 7)]
    names = diarize.assign_speakers(segments, turns)
    assert [w.speaker for s in segments for w in s.words] == [0, 0, 1, 0]
    assert names == ["Говорящий 1", "Говорящий 2"]   # speaker 7 has no words: no number
    assert diarize.assign_speakers(segments, turns, names=["Анна", ""]) == ["Анна", "Говорящий 2"]


def test_worker_diarize_job_sends_turns(monkeypatch, tmp_path):
    import queue
    from gigaam_app import catalog, worker as worker_module
    from gigaam_app.worker import Worker

    class FakeModel:
        loads = 0

        def __init__(self, folder, device="auto", cpu_threads=None):
            FakeModel.loads += 1

        def diarize(self, audio, num_speakers=None, on_progress=None, should_cancel=None):
            on_progress(1, 2)
            on_progress(2, 2)
            assert num_speakers == 3 and len(audio) == 16000
            return diarize.Diarization(exclusive_turns=[Turn(0.0, 1.0, 0), Turn(1.0, 2.0, 1)], speakers=2, found=4)

    monkeypatch.setattr(diarize, "SpeakerModel", FakeModel)
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path)
    monkeypatch.setattr(worker_module, "decode_audio", lambda path: np.zeros(16000, dtype=np.float32))
    events = queue.Queue()
    worker = Worker(events)
    worker._diarize(7, "a.wav", "cpu", 0, 3)
    worker._diarize(8, "a.wav", "cpu", 0, 3)
    got = []
    while not events.empty():
        got.append(events.get())
    assert got[0] == ("diarize_loading", 7)
    assert ("diarize_result", 7, [(0.0, 1.0, 0), (1.0, 2.0, 1)], None) in got
    # The model's own count comes just before the result (the window's hint).
    assert got.index(("diarize_found", 7, 4)) + 1 == got.index(("diarize_result", 7, [(0.0, 1.0, 0), (1.0, 2.0, 1)], None))
    assert ("diarize_result", 8, [(0.0, 1.0, 0), (1.0, 2.0, 1)], None) in got
    assert FakeModel.loads == 1   # loaded once, kept for the next file


def test_worker_diarize_reports_a_missing_model(monkeypatch):
    import queue
    from gigaam_app import catalog
    from gigaam_app.worker import Worker
    monkeypatch.setattr(catalog, "installed_folder", lambda info: None)
    events = queue.Queue()
    Worker(events)._diarize(1, "a.wav", "cpu", 0)
    kind, request, turns, error = events.get()
    assert (kind, request, turns) == ("diarize_result", 1, None) and "Speakers" in error
