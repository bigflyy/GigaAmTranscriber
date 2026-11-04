"""The streaming ChunkFinder must give exactly the regions and chunks of the batch port."""

import random

import numpy as np
import pytest

from gigaam_app.vad import WINDOW, ChunkFinder, VadOptions
from tests.silero_reference import group_chunks, speech_regions


def bursty_probabilities(rng, n_windows):
    """Markov chain of speech and pause runs, with noisy probabilities near the thresholds."""
    values, speaking = [], rng.random() < 0.5
    while len(values) < n_windows:
        # Long runs exercise the forced cut at vad_max_speech_s; short ones the min-speech rule.
        run = rng.choice([1, 3, 10, 40, 150, 600, 1500])
        centre = rng.uniform(0.45, 0.99) if speaking else rng.uniform(0.0, 0.55)
        values += [min(1.0, max(0.0, rng.gauss(centre, 0.12))) for _ in range(run)]
        speaking = not speaking
    return np.array(values[:n_windows], dtype=np.float32)


def streaming(probabilities, n_samples, options):
    finder = ChunkFinder(n_samples, options)
    chunks = []
    for index, probability in enumerate(probabilities.tolist()):
        chunks += finder.feed(index, probability)
    chunks += finder.finish()
    return finder.regions, chunks


OPTION_SETS = [
    VadOptions(),
    VadOptions(vad_min_silence_ms=100, vad_speech_pad_ms=30, vad_max_speech_s=8, max_duration=12,
               strict_limit_duration=12),
    VadOptions(vad_threshold=0.3, vad_min_speech_ms=50, vad_max_speech_s=60, max_duration=20,
               strict_limit_duration=9, new_chunk_threshold=1.0),
    VadOptions(vad_speech_pad_ms=0, vad_min_silence_ms=500, vad_max_speech_s=3, max_duration=5),
]


@pytest.mark.parametrize("options", OPTION_SETS)
@pytest.mark.parametrize("seed", range(40))
def test_streaming_matches_reference(options, seed):
    rng = random.Random(seed)
    n_windows = rng.choice([1, 5, 300, 3000, 12000])
    n_samples = n_windows * WINDOW - rng.randrange(WINDOW)  # the last window is usually partial
    probabilities = bursty_probabilities(rng, n_windows)
    expected_regions = speech_regions(probabilities, n_samples, options)
    expected_chunks = group_chunks(expected_regions, options)
    regions, chunks = streaming(probabilities, n_samples, options)
    assert regions == expected_regions
    assert chunks == expected_chunks


def test_silence_gives_no_chunks():
    regions, chunks = streaming(np.zeros(1000, dtype=np.float32), 1000 * WINDOW, VadOptions())
    assert regions == [] and chunks == []
