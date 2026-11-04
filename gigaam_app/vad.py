"""Silero VAD on ONNX Runtime and grouping of speech into recognition chunks.

GigaAM accepts at most about 25 s per call, so long recordings are cut at
pauses. Silero gives a speech probability for every 32 ms window; the
hysteresis in ChunkFinder (ported from silero-vad 6.2.1, MIT licence,
Silero Team) turns those into speech regions and packs them into chunks.
"""

from dataclasses import dataclass

import numpy as np

from .audio import SAMPLE_RATE

WINDOW = 512      # samples per Silero step at 16 kHz
CONTEXT = 64      # samples of the previous window that Silero v5+ expects in front
STATE_SIZE = 128


@dataclass
class VadOptions:
    """User-tunable segmentation settings. Names match the JSON config keys."""
    vad_threshold: float = 0.5          # probability at or above which a window is speech
    vad_min_speech_ms: int = 300        # shorter speech regions are dropped
    vad_max_speech_s: float = 25.0      # longer regions are split at the longest pause inside
    vad_min_silence_ms: int = 2000      # a pause must last this long to end a region
    vad_speech_pad_ms: int = 250        # padding added on both sides of every region
    max_duration: float = 25.0          # regions are merged into chunks up to this length
    strict_limit_duration: float = 25.0  # longer chunks are split into equal parts
    new_chunk_threshold: float = 0.2    # chunks this short or shorter are dropped


class SileroVad:
    """Speech probability for every 512-sample window, exactly as silero-vad computes it.

    Uses models/silero_vad_scan.onnx from tools/make_silero_scan.py: the
    unchanged Silero model inside an ONNX loop, so one call covers a whole
    block of windows. Silero is recurrent with a long memory, so the windows
    must be walked in order. (Splitting the file into parallel rows was tried:
    faster, but it moved up to 60 % of the speech regions on noisy audio.)
    """

    BLOCK = 1024  # windows per call, about 33 s of audio; fastest of 256 / 1024 / 4096

    def __init__(self, session):
        self.session = session

    def blocks(self, audio):
        """Yield (first window index, probabilities) for consecutive blocks of windows."""
        n_windows = max(1, -(-len(audio) // WINDOW))
        # Window i is fed with the CONTEXT samples before it plus its own WINDOW
        # samples; the file is zero-padded in front and at the end.
        padded = np.zeros(CONTEXT + n_windows * WINDOW, dtype=np.float32)
        padded[CONTEXT:CONTEXT + len(audio)] = audio
        view = np.lib.stride_tricks.sliding_window_view(padded, CONTEXT + WINDOW)[::WINDOW]
        state = np.zeros((2, 1, STATE_SIZE), dtype=np.float32)
        for first in range(0, n_windows, self.BLOCK):
            windows = np.ascontiguousarray(view[first:first + self.BLOCK])[:, None, :]
            state, probabilities = self.session.run(None, {"state": state, "windows": windows})
            yield first, probabilities[:, 0, 0]

    def windows(self, audio):
        """Yield the probability of each window in order."""
        for _, probabilities in self.blocks(audio):
            yield from probabilities.tolist()


class ChunkFinder:
    """Turns window probabilities into recognition chunks while they arrive.

    Same result as silero_vad.get_speech_timestamps (6.2.1, MIT licence,
    Silero Team, use_max_poss_sil_at_max_speech=True) followed by the v0.1
    chunk grouping, but incremental: feed() one probability at a time and
    finished chunks come back as soon as nothing later can change them. That
    lets recognition start long before the whole file has been searched.
    tests/silero_reference.py holds the batch original for comparison.

    Three stages, each holding back only what the next window could change:
    1. hysteresis: probability -> raw speech regions;
    2. padding: a region is final once the next one starts (they share the gap);
    3. grouping: regions are merged into chunks of at most max_duration.
    """

    def __init__(self, n_samples, options: VadOptions):
        self.n_samples = n_samples
        rate = SAMPLE_RATE
        self.min_speech = rate * options.vad_min_speech_ms / 1000
        self.pad = rate * options.vad_speech_pad_ms / 1000
        self.max_speech = rate * options.vad_max_speech_s - WINDOW - 2 * self.pad
        self.min_silence = rate * options.vad_min_silence_ms / 1000
        self.min_silence_at_max_speech = rate * 98 / 1000
        self.threshold = options.vad_threshold
        self.neg_threshold = max(options.vad_threshold - 0.15, 0.01)  # leaving speech needs less
        # Stage 1 state, named as in silero-vad.
        self.triggered = False
        self.current = {}
        self.temp_end = self.prev_end = self.next_start = 0
        self.possible_ends = []  # (pause start, pause length) candidates for a forced cut
        # Stage 2: the last raw region, waiting for its successor.
        self.waiting = None
        # Stage 3: the chunk being built.
        self.chunk = None
        self.max_len = options.max_duration * rate
        self.hard_limit = options.strict_limit_duration * rate
        self.min_len = options.new_chunk_threshold * rate
        self.regions = []  # final padded regions, for statistics

    def feed(self, index, probability):
        """Add the probability of window `index`; returns chunks that became final."""
        closed = self._hysteresis(index, probability)
        return self._pad(closed) if closed else []

    def finish(self):
        """End of audio: flush every stage; returns the remaining chunks."""
        chunks = []
        if self.current and self.n_samples - self.current["start"] > self.min_speech:
            self.current["end"] = self.n_samples
            chunks += self._pad(self.current)
        self.current = {}
        if self.waiting is not None:
            last, self.waiting = self.waiting, None
            last["end"] = int(min(self.n_samples, last["end"] + self.pad))
            chunks += self._group(last)
        if self.chunk is not None and self.chunk[1] - self.chunk[0] > self.min_len:
            chunks += self._split(*self.chunk)
        self.chunk = None
        return chunks

    # ----------------------------------------------------------- stage 1

    def _hysteresis(self, index, probability):
        """One step of the silero state machine; returns a closed raw region or None."""
        sample = WINDOW * index
        closed = None
        # Speech is back after a pause: remember the pause as a possible cut point.
        if probability >= self.threshold and self.temp_end:
            silence = sample - self.temp_end
            if silence > self.min_silence_at_max_speech:
                self.possible_ends.append((self.temp_end, silence))
            self.temp_end = 0
            if self.next_start < self.prev_end:
                self.next_start = sample
        # Start of speech.
        if probability >= self.threshold and not self.triggered:
            self.triggered = True
            self.current["start"] = sample
            return None
        # Region too long: cut at the longest pause seen inside it.
        if self.triggered and sample - self.current["start"] > self.max_speech:
            if self.possible_ends:
                self.prev_end, length = max(self.possible_ends, key=lambda item: item[1])
                self.current["end"] = self.prev_end
                closed = self.current
                self.current = {}
                self.next_start = self.prev_end + length
                if self.next_start < self.prev_end + sample:
                    self.current["start"] = self.next_start
                else:
                    self.triggered = False
            else:
                self.current["end"] = sample
                closed = self.current
                self.current = {}
                self.triggered = False
            self.prev_end = self.next_start = self.temp_end = 0
            self.possible_ends = []
            if not self.triggered:
                return closed
        # Silence while in speech: end the region once the pause is long enough.
        if probability < self.neg_threshold and self.triggered:
            if not self.temp_end:
                self.temp_end = sample
            if sample - self.temp_end < self.min_silence:
                return closed
            # Reached only with closed None: a forced cut above resets temp_end,
            # so a normal end needs at least min_silence of later windows.
            self.current["end"] = self.temp_end
            if self.current["end"] - self.current["start"] > self.min_speech:
                closed = self.current
            self.current = {}
            self.prev_end = self.next_start = self.temp_end = 0
            self.triggered = False
            self.possible_ends = []
        return closed

    # ----------------------------------------------------------- stage 2

    def _pad(self, region):
        """Pad the waiting region now that its successor is known; returns new chunks."""
        if self.waiting is None:
            region["start"] = int(max(0, region["start"] - self.pad))  # the very first region
            self.waiting = region
            return []
        previous, self.waiting = self.waiting, region
        gap = region["start"] - previous["end"]
        if gap < 2 * self.pad:  # close neighbours share the gap between them
            previous["end"] += int(gap // 2)
            region["start"] = int(max(0, region["start"] - gap // 2))
        else:
            previous["end"] = int(min(self.n_samples, previous["end"] + self.pad))
            region["start"] = int(max(0, region["start"] - self.pad))
        return self._group(previous)

    # ----------------------------------------------------------- stage 3

    def _group(self, region):
        """Add one final region to the chunk being built; returns chunks that are complete."""
        # Silero reports seconds rounded to 0.1 s (time_resolution=1); the same
        # rounding keeps the chunks, and so the text, identical to v0.1.
        total = self.n_samples / SAMPLE_RATE
        start = max(round(region["start"] / SAMPLE_RATE, 1), 0)
        end = min(round(region["end"] / SAMPLE_RATE, 1), total)
        start, end = int(start * SAMPLE_RATE), int(end * SAMPLE_RATE)
        self.regions.append((start, end))
        if self.chunk is None:
            self.chunk = (start, end)
            return []
        chunk_start, chunk_end = self.chunk
        done = []
        if chunk_end - chunk_start > self.min_len and end - chunk_start > self.max_len:
            done = self._split(chunk_start, chunk_end)
            chunk_start = start
        self.chunk = (chunk_start, end)
        return done

    def _split(self, start, end):
        """A chunk longer than strict_limit_duration becomes equal parts."""
        length = end - start
        if length <= self.hard_limit:
            return [(start, end)]
        parts = int(length / self.hard_limit) + 1
        step = length / parts
        return [(int(start + part * step), int(start + (part + 1) * step) if part < parts - 1 else end)
                for part in range(parts)]

    @property
    def speech_seconds(self):
        """Total speech; padded regions never overlap."""
        return sum(end - start for start, end in self.regions) / SAMPLE_RATE


