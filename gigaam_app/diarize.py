"""Speaker labels (plan 07): who speaks when, on ONNX Runtime and numpy, no torch.

A port of pyannote.audio 4's "community-1" speaker diarization, the pipeline the
owner chose in session 18 (HANDOFF.md): on an unseen Russian set it put 0.3% of
the words under the wrong speaker and found the right number of speakers in
every event. The models come from experiments/diarization/export_speaker_models.py:

- segmentation.onnx (pyannote segmentation-3.0, MIT): for every 10 s window, which
  of up to 3 local speakers talks in each of 589 frames (one every 16.875 ms);
- embedding.onnx (WeSpeaker ResNet34-LM, CC BY 4.0, with pyannote's weighted
  statistics pooling inside): one voice print per local speaker of a window;
- speakers.npz: the powerset table and the community-1 PLDA (CC BY 4.0) for
  the VBx clustering.

The steps, with pyannote's names in brackets so the two can be compared:

1. Windows of 10 s every `step` seconds; each gives a 0/1 activity per frame for
   3 local speakers [get_segmentations, powerset to multilabel].
2. The number of people talking in each frame: the average over the windows
   that cover it, rounded [speaker_count].
3. A voice print for each window and local speaker: the network runs once per
   window, its features are averaged with each speaker's activity as the
   weights (mean and standard deviation), then a linear layer [get_embeddings].
4. Clustering [VBxClustering]: voice prints of speakers who talk alone for at
   least 20% of their window are grouped by centroid-linkage AHC (distance 0.6
   on unit vectors), which starts VBx (a Bayesian model in the PLDA space) that
   decides how many speakers there are; with a known count, k-means instead.
   Every local speaker of every window then goes to the closest speaker, two
   local speakers of one window never to the same one.
5. Back to time [reconstruct, to_diarization]: per frame, the `count` speakers
   with the most activity; the exclusive version allows one speaker per frame,
   which is the one used to label words.
"""

from dataclasses import dataclass, field
from itertools import permutations
import json
from pathlib import Path

import numpy as np

from .asr import create_session

SAMPLE_RATE = 16000
WINDOW_SAMPLES = 160000          # 10 s windows, as the segmentation model was trained
LOCAL_SPEAKERS = 3               # speakers one window can hold
MIN_ACTIVE_RATIO = 0.2           # share of a window a speaker must talk alone to shape the clusters
SEGMENTATION_BATCH = 32
EMBEDDING_BATCH = 32
FBANK_SHIFT = 160                # 10 ms
FBANK_LENGTH = 400               # 25 ms


@dataclass
class Turn:
    start: float
    end: float
    speaker: int  # 0, 1, ... in order of first appearance


@dataclass
class Diarization:
    turns: list = field(default_factory=list)            # overlapping speech kept
    exclusive_turns: list = field(default_factory=list)  # one speaker at a time (for words)
    speakers: int = 0
    centroids: np.ndarray = None  # (speakers, 256) voice print of each speaker
    cancelled: bool = False
    # How many speakers the clustering found by itself (VBx), also when the user gave a
    # number: the window shows it as a hint next to the count (owner, 2026-11-09).
    found: int = 0


class Cancelled(Exception):
    pass


class SpeakerModel:
    """The loaded speaker models. One diarization at a time per instance."""

    def __init__(self, folder, device="auto", cpu_threads=None):
        folder = Path(folder)
        self.segmentation, self.segmentation_provider = create_session(folder / "segmentation.onnx", device, cpu_threads)
        self.embedding, self.provider = create_session(folder / "embedding.onnx", device, cpu_threads)
        config = json.loads((folder / "speakers.json").read_text(encoding="utf-8"))
        grid = config["frames"]
        self.frame_start, self.frame_duration, self.frame_step = grid["start"], grid["duration"], grid["step"]
        clustering = config["clustering"]
        self.threshold, self.fa, self.fb = clustering["threshold"], clustering["Fa"], clustering["Fb"]
        arrays = np.load(folder / "speakers.npz")
        self.powerset = arrays["powerset"]                  # (7, 3): local speakers in each class
        self.plda = Plda(arrays, clustering["lda_dimension"])
        self.mel_banks = _mel_banks()
        self.hamming = np.hamming(FBANK_LENGTH)
        self.timings = {}

    @property
    def on_gpu(self):
        return self.provider != "CPUExecutionProvider"

    def diarize(self, audio, num_speakers=None, step=None, exclude_overlap=False,
                on_progress=None, should_cancel=None):
        """Speaker turns of `audio` (float32 mono, 16 kHz).

        num_speakers: None to find the number, or the number the user knows.
        step: window step in seconds (a multiple of 10 ms); None = 1 s on a GPU, 2 s on
        the CPU (half the work; the same results on the Russian test set, HANDOFF.md).
        on_progress(done, total) is called after each batch; should_cancel() -> True
        stops at the next batch and returns a Diarization with cancelled=True.
        """
        if step is None:
            step = 1.0 if self.on_gpu else 2.0
        step_samples = int(round(step * SAMPLE_RATE))
        if step_samples % FBANK_SHIFT:
            raise ValueError("step must be a multiple of 10 ms")
        progress = _Progress(on_progress, should_cancel)
        try:
            return self._diarize(np.asarray(audio, dtype=np.float32), num_speakers, step_samples,
                                 exclude_overlap, progress)
        except Cancelled:
            return Diarization(cancelled=True)

    # 1. Segmentation ---------------------------------------------------------------

    def _chunk_starts(self, num_samples, step_samples):
        """Start sample of every window: full windows, then a zero-padded last one."""
        full = 1 + (num_samples - WINDOW_SAMPLES) // step_samples if num_samples >= WINDOW_SAMPLES else 0
        starts = [c * step_samples for c in range(full)]
        if num_samples < WINDOW_SAMPLES or (num_samples - WINDOW_SAMPLES) % step_samples > 0:
            starts.append(full * step_samples)
        return np.array(starts, dtype=np.int64)

    def _segment(self, padded, starts, progress):
        """(chunks, 589, 3) 0/1 activity of the local speakers in each window."""
        name = self.segmentation.get_inputs()[0].name
        out = []
        for first in range(0, len(starts), SEGMENTATION_BATCH):
            batch = np.stack([padded[s:s + WINDOW_SAMPLES] for s in starts[first:first + SEGMENTATION_BATCH]])
            logits = self.segmentation.run(None, {name: batch[:, None, :]})[0]
            classes = np.argmax(logits, axis=-1)
            out.append(self.powerset[classes].astype(np.uint8))
            progress.advance(len(batch))
        return np.concatenate(out)

    # 3. Voice prints ---------------------------------------------------------------

    def _fbank(self, samples):
        """Kaldi-style 80-bin log mel filterbank (as torchaudio.compliance.kaldi.fbank with
        pyannote's WeSpeaker settings: 25 ms hamming frames every 10 ms, no dither, power
        spectrum, pre-emphasis 0.97, DC offset removed), not yet mean-normalised."""
        count = 1 + (len(samples) - FBANK_LENGTH) // FBANK_SHIFT
        index = np.arange(FBANK_LENGTH)[None, :] + FBANK_SHIFT * np.arange(count)[:, None]
        frames = samples[index].astype(np.float64) * 32768.0
        frames -= frames.mean(axis=1, keepdims=True)
        frames[:, 1:] -= 0.97 * frames[:, :-1].copy()
        frames[:, 0] -= 0.97 * frames[:, 0]
        frames *= self.hamming
        power = np.abs(np.fft.rfft(frames, n=512)) ** 2
        mel = power[:, :256] @ self.mel_banks.T
        return np.log(np.maximum(mel, np.finfo(np.float32).eps)).astype(np.float32)

    def _embed(self, padded, starts, segmentations, exclude_overlap, progress):
        """(chunks, 3, 256) voice print of every local speaker of every window."""
        window_frames = 1 + (WINDOW_SAMPLES - FBANK_LENGTH) // FBANK_SHIFT
        masks = segmentations.astype(np.float32)
        if exclude_overlap:
            clean = masks * (masks.sum(axis=2, keepdims=True) < 2)
            # pyannote keeps the full mask when too little clean speech is left (fewer frames
            # than the shortest input the voice print model accepts, about 25 ms)
            min_frames = int(np.ceil(masks.shape[1] * FBANK_LENGTH / WINDOW_SAMPLES))
            enough = clean.sum(axis=1, keepdims=True) > min_frames
            masks = np.where(enough, clean, masks)
        steps = window_frames
        for _ in range(3):              # the network halves the time axis three times
            steps = (steps + 1) // 2
        out = []
        for first in range(0, len(starts), EMBEDDING_BATCH):
            chosen = starts[first:first + EMBEDDING_BATCH]
            # One filterbank over the span of the batch: windows start on whole 10 ms frames,
            # so a window's frames are a slice of it.
            span = padded[chosen[0]:chosen[-1] + WINDOW_SAMPLES]
            bank = self._fbank(span)
            offsets = (chosen - chosen[0]) // FBANK_SHIFT
            batch = np.stack([bank[o:o + window_frames] for o in offsets])
            batch -= batch.mean(axis=1, keepdims=True)
            weights = _nearest(masks[first:first + len(chosen)], steps).transpose(0, 2, 1)  # (B, 3, steps)
            out.append(self.embedding.run(None, {"fbank": batch, "weights": np.ascontiguousarray(weights)})[0])
            progress.advance(len(chosen))
        return np.concatenate(out)

    # The whole pipeline -----------------------------------------------------------

    def _diarize(self, audio, num_speakers, step_samples, exclude_overlap, progress):
        clock = _Clock()
        starts = self._chunk_starts(len(audio), step_samples)
        padded = np.zeros(int(starts[-1]) + WINDOW_SAMPLES, dtype=np.float32)
        padded[:len(audio)] = audio
        progress.total = 2 * len(starts)
        segmentations = self._segment(padded, starts, progress)
        clock.lap("segmentation")
        step_seconds = step_samples / SAMPLE_RATE
        count = self._speaker_count(segmentations, step_seconds)
        if count.max() == 0:
            return Diarization()
        embeddings = self._embed(padded, starts, segmentations, exclude_overlap, progress)
        clock.lap("voice prints")
        hard_clusters, centroids, found = self._cluster(embeddings, segmentations, num_speakers)
        clock.lap("clustering")
        if num_speakers:
            count = np.minimum(count, num_speakers)
        hard_clusters[segmentations.sum(axis=1) == 0] = -2   # silent local speakers
        binary = self._reconstruct(segmentations, hard_clusters, count, step_seconds)
        exclusive = self._reconstruct(segmentations, hard_clusters, np.minimum(count, 1), step_seconds)
        turns, exclusive_turns, order = self._turns(binary, exclusive)
        clock.lap("turns")
        self.timings = clock.laps
        if centroids is not None and len(order):
            centroids = np.pad(centroids, ((0, max(0, binary.shape[1] - len(centroids))), (0, 0)))[order]
        return Diarization(turns=turns, exclusive_turns=exclusive_turns, speakers=len(order), centroids=centroids,
                           found=found)

    # 2. Speaker count ----------------------------------------------------------------

    def _frame_offsets(self, num_chunks, step_seconds):
        """First global frame of every window, and the number of global frames."""
        offsets = np.rint(np.arange(num_chunks) * step_seconds / self.frame_step).astype(np.int64)
        last = WINDOW_SAMPLES / SAMPLE_RATE + (num_chunks - 1) * step_seconds
        return offsets, int(np.rint(last / self.frame_step)) + 1

    def _overlap_add(self, values, step_seconds):
        """Sum (and number) of the windows' frame values on the global frame grid."""
        num_chunks, num_frames, width = values.shape
        offsets, total = self._frame_offsets(num_chunks, step_seconds)
        summed = np.zeros((total, width), dtype=np.float64)
        covered = np.zeros((total, 1), dtype=np.float64)
        for chunk, offset in enumerate(offsets):
            summed[offset:offset + num_frames] += values[chunk]
            covered[offset:offset + num_frames] += 1
        return summed, covered

    def _speaker_count(self, segmentations, step_seconds):
        summed, covered = self._overlap_add(segmentations.sum(axis=2, keepdims=True).astype(np.float64), step_seconds)
        average = np.where(covered > 0, summed / np.maximum(covered, 1e-12), 0.0)
        return np.rint(average[:, 0]).astype(np.int64)

    # 4. Clustering -------------------------------------------------------------------

    def _cluster(self, embeddings, segmentations, num_speakers):
        """(chunks, 3) speaker of each local speaker, the speakers' centroids, and the number
        of speakers VBx found by itself (before a number given by the user is forced)."""
        num_chunks, local, dimension = embeddings.shape
        num_frames = segmentations.shape[1]
        alone = segmentations * (segmentations.sum(axis=2, keepdims=True) == 1)
        active = alone.sum(axis=1) >= MIN_ACTIVE_RATIO * num_frames
        valid = ~np.any(np.isnan(embeddings), axis=2)
        chunk_idx, speaker_idx = np.where(active & valid)
        train = embeddings[chunk_idx, speaker_idx].astype(np.float64)
        if len(train) < 2:
            hard = np.zeros((num_chunks, local), dtype=np.int64)
            return hard, train.mean(axis=0, keepdims=True) if len(train) else None, len(train)
        normed = train / np.linalg.norm(train, axis=1, keepdims=True)
        ahc = centroid_linkage_clusters(normed, self.threshold)
        responsibilities, priors = vbx(ahc, self.plda.transform(train), self.plda.phi, self.fa, self.fb)
        kept = responsibilities[:, priors > 1e-7]
        centroids = kept.T @ train / kept.sum(axis=0)[:, None]
        found = len(centroids)
        constrained = True
        if num_speakers and num_speakers != len(centroids):
            constrained = False   # as pyannote: forcing the count turns the constraint off
            labels = kmeans(normed, min(num_speakers, len(train)), seed=42)
            centroids = np.vstack([train[labels == k].mean(axis=0) for k in range(labels.max() + 1)])
        flat = embeddings.reshape(-1, dimension).astype(np.float64)
        similarity = 1 + (flat / np.linalg.norm(flat, axis=1, keepdims=True)) @ \
            (centroids / np.linalg.norm(centroids, axis=1, keepdims=True)).T   # 2 - cosine distance
        similarity = similarity.reshape(num_chunks, local, -1)
        if constrained:
            similarity[segmentations.sum(axis=1) == 0] = similarity.min() - 1.0
            hard = constrained_argmax(similarity)
        else:
            hard = np.argmax(similarity, axis=2)
        return hard.astype(np.int64), centroids, found

    # 5. Back to time ----------------------------------------------------------------

    def _reconstruct(self, segmentations, hard_clusters, count, step_seconds):
        """(frames, speakers) 0/1: in each frame the `count` speakers with the most activity."""
        num_chunks, num_frames, _ = segmentations.shape
        num_clusters = max(int(hard_clusters.max()) + 1, 1)
        clustered = np.zeros((num_chunks, num_frames, num_clusters), dtype=np.float64)
        for k in range(num_clusters):
            members = (hard_clusters == k)[:, None, :]                  # (chunks, 1, 3)
            clustered[:, :, k] = np.max(np.where(members, segmentations, 0), axis=2)
        activations, _ = self._overlap_add(clustered, step_seconds)
        frames = min(len(activations), len(count))
        activations, count = activations[:frames], count[:frames]
        width = max(num_clusters, int(count.max()))
        if width > num_clusters:
            activations = np.pad(activations, ((0, 0), (0, width - num_clusters)))
        order = np.argsort(-activations, axis=-1)
        chosen = (np.arange(width)[None, :] < count[:, None]).astype(np.float64)
        binary = np.zeros_like(activations)
        np.put_along_axis(binary, order, chosen, axis=1)
        return binary

    def _turns(self, binary, exclusive):
        """Turns of both versions, speakers renumbered by first appearance in either."""
        middles = self.frame_start + self.frame_duration / 2 + self.frame_step * np.arange(len(binary))
        raw, raw_exclusive = _runs(binary, middles), _runs(exclusive, middles)
        first = {}
        for start, _, speaker in sorted(raw + raw_exclusive):
            first.setdefault(speaker, len(first))
        order = sorted(first, key=first.get)
        turns = sorted((Turn(s, e, first[k]) for s, e, k in raw), key=lambda t: (t.start, t.speaker))
        exclusive_turns = sorted((Turn(s, e, first[k]) for s, e, k in raw_exclusive), key=lambda t: (t.start, t.speaker))
        return turns, exclusive_turns, order


class Plda:
    """community-1 PLDA: voice prints into the space where VBx works (pyannote vbx_setup;
    the eigen-decomposition is done at export time)."""

    def __init__(self, arrays, lda_dimension):
        self.mean1, self.mean2, self.lda = arrays["plda_mean1"], arrays["plda_mean2"], arrays["plda_lda"]
        self.mu, self.tr = arrays["plda_mu"], arrays["plda_tr"]
        self.lda_dimension = lda_dimension
        self.phi = arrays["plda_psi"][:lda_dimension]

    def transform(self, x):
        rows, columns = self.lda.shape
        x = np.sqrt(rows) * _l2_rows(x - self.mean1)
        x = np.sqrt(columns) * _l2_rows(x @ self.lda - self.mean2)
        return ((x - self.mu) @ self.tr.T)[:, :self.lda_dimension]


def centroid_linkage_clusters(x, threshold):
    """Flat clusters of centroid-linkage AHC cut at `threshold` (Euclidean), as
    scipy's linkage(method="centroid") + fcluster(criterion="distance").

    Merges stop at the first pair farther apart than the threshold: every later
    merge would contain a merge above it, so fcluster would not join it either.
    Distances are kept squared and updated with the Lance-Williams formula.
    """
    n = len(x)
    if n == 1:
        return np.zeros(1, dtype=np.int64)
    squares = np.einsum("ij,ij->i", x, x)
    dist = (squares[:, None] + squares[None, :] - 2 * (x @ x.T)).astype(np.float32)
    np.maximum(dist, 0, out=dist)
    np.fill_diagonal(dist, np.inf)
    size = np.ones(n)
    parent = np.arange(n)
    active = np.ones(n, dtype=bool)
    nearest = np.argmin(dist, axis=1)
    nearest_dist = dist[np.arange(n), nearest]
    limit = threshold ** 2
    while True:
        i = int(np.argmin(nearest_dist))
        d = float(nearest_dist[i])
        if not np.isfinite(d) or d > limit:
            break
        j = int(nearest[i])
        ni, nj = size[i], size[j]
        merged = (ni * dist[i].astype(np.float64) + nj * dist[j] - ni * nj / (ni + nj) * d) / (ni + nj)
        merged = np.maximum(merged, 0).astype(np.float32)
        merged[~active] = np.inf
        merged[i] = merged[j] = np.inf
        dist[i, :] = merged
        dist[:, i] = merged
        dist[j, :] = np.inf
        dist[:, j] = np.inf
        size[i] = ni + nj
        active[j] = False
        parent[j] = i
        nearest_dist[j] = np.inf
        stale = np.flatnonzero(active & ((nearest == i) | (nearest == j)))
        for row in stale:
            nearest[row] = np.argmin(dist[row])
            nearest_dist[row] = dist[row, nearest[row]]
        closer = active & (merged < nearest_dist)
        nearest[closer] = i
        nearest_dist[closer] = merged[closer]
        nearest[i] = np.argmin(dist[i])
        nearest_dist[i] = dist[i, nearest[i]]
    roots = parent.copy()
    while True:
        moved = roots[roots]
        if np.array_equal(moved, roots):
            break
        roots = moved
    return np.unique(roots, return_inverse=True)[1]


def vbx(init_labels, features, phi, fa, fb, max_iters=20, init_smoothing=7.0, epsilon=1e-4):
    """VBx clustering (Landini et al.), as pyannote's cluster_vbx + VBx with return_model."""
    clusters = int(init_labels.max()) + 1
    gamma = np.zeros((len(init_labels), clusters))
    gamma[np.arange(len(init_labels)), init_labels] = 1.0
    gamma = _softmax(gamma * init_smoothing)
    pi = np.ones(clusters) / clusters
    dimension = features.shape[1]
    constant = -0.5 * (np.sum(features ** 2, axis=1, keepdims=True) + dimension * np.log(2 * np.pi))
    rho = features * np.sqrt(phi)
    previous = None
    for iteration in range(max_iters):
        inv_l = 1.0 / (1 + fa / fb * gamma.sum(axis=0, keepdims=True).T * phi)
        alpha = fa / fb * inv_l * gamma.T.dot(rho)
        log_p = fa * (rho.dot(alpha.T) - 0.5 * (inv_l + alpha ** 2).dot(phi) + constant)
        log_pi = np.log(pi + 1e-8)
        log_px = _logsumexp(log_p + log_pi)
        gamma = np.exp(log_p + log_pi - log_px[:, None])
        pi = gamma.sum(axis=0)
        pi = pi / pi.sum()
        elbo = log_px.sum() + fb * 0.5 * np.sum(np.log(inv_l) - inv_l - alpha ** 2 + 1)
        if iteration > 0 and elbo - previous < epsilon:
            break
        previous = elbo
    return gamma, pi


def kmeans(x, k, seed=42, n_init=3, max_iter=300, tol=1e-4):
    """k-means with k-means++ starts, the best of n_init runs (stands in for sklearn's KMeans)."""
    rng = np.random.default_rng(seed)
    best, best_inertia = None, np.inf
    for _ in range(n_init):
        centres = [x[rng.integers(len(x))]]
        for _ in range(1, k):
            d2 = np.min(((x[:, None, :] - np.array(centres)[None]) ** 2).sum(-1), axis=1)
            centres.append(x[rng.choice(len(x), p=d2 / d2.sum())] if d2.sum() > 0 else x[rng.integers(len(x))])
        centres = np.array(centres)
        for _ in range(max_iter):
            d2 = (x ** 2).sum(1)[:, None] - 2 * x @ centres.T + (centres ** 2).sum(1)[None]
            labels = np.argmin(d2, axis=1)
            moved = np.array([x[labels == c].mean(axis=0) if np.any(labels == c) else x[np.argmax(d2.min(1))]
                              for c in range(k)])
            shift = ((moved - centres) ** 2).sum()
            centres = moved
            if shift < tol:
                break
        d2 = (x ** 2).sum(1)[:, None] - 2 * x @ centres.T + (centres ** 2).sum(1)[None]
        labels = np.argmin(d2, axis=1)
        inertia = d2[np.arange(len(x)), labels].sum()
        if inertia < best_inertia:
            best, best_inertia = labels, inertia
    return np.unique(best, return_inverse=True)[1]


def constrained_argmax(scores):
    """Per window, the assignment of local speakers to speakers with the highest total
    score, two local speakers never sharing one (scipy's linear_sum_assignment, by
    trying every assignment: 3 local speakers, a few dozen speakers at most)."""
    num_chunks, local, clusters = scores.shape
    hard = np.full((num_chunks, local), -2, dtype=np.int64)
    if clusters >= local:
        options = np.array(list(permutations(range(clusters), local)))      # option -> cluster of each speaker
        block = max(1, 2_000_000 // (len(options) * local))                # keeps the array near 16 MB
        for first in range(0, num_chunks, block):
            part = scores[first:first + block]
            totals = part[:, np.arange(local)[None, :], options].sum(axis=2)  # (block, options)
            hard[first:first + block] = options[np.argmax(totals, axis=1)]
    else:
        options = np.array(list(permutations(range(local), clusters)))     # option -> speaker of each cluster
        for chunk in range(num_chunks):
            totals = scores[chunk][options, np.arange(clusters)[None, :]].sum(axis=1)
            for cluster, speaker in enumerate(options[np.argmax(totals)]):
                hard[chunk, speaker] = cluster
    return hard


def words_speakers(words, turns):
    """Speaker of each (start, end) word span: the turn with the most time inside the
    span, or the nearest turn when none overlaps it (None when there are no turns)."""
    if not turns:
        return [None] * len(words)
    starts = np.array([t.start for t in turns])
    ends = np.array([t.end for t in turns])
    speakers = np.array([t.speaker for t in turns])
    result = []
    for start, end in words:
        overlap = np.minimum(ends, end) - np.maximum(starts, start)
        best = int(np.argmax(overlap))
        if overlap[best] <= 0:
            gap = np.maximum(starts - end, start - ends)
            best = int(np.argmin(gap))
        result.append(int(speakers[best]))
    return result


def default_name(index):
    return f"Говорящий {index + 1}"


def assign_speakers(segments, turns, names=None):
    """Give every word of the segments its speaker from the (exclusive) turns.

    Speakers are numbered by their first word, so "Говорящий 1" speaks first; a
    speaker without words gets no number. Returns the speaker names: `names` (the
    user's renames from an earlier run, by number) where given, else default ones.
    """
    words = [word for segment in segments for word in segment.words]
    raw = words_speakers([(word.start, word.end) for word in words], turns)
    numbers = {}
    for word, speaker in zip(words, raw):
        if speaker is not None:
            speaker = numbers.setdefault(speaker, len(numbers))
        word.speaker = speaker
    names = list(names or [])
    return [names[i] if i < len(names) and names[i] else default_name(i) for i in range(len(numbers))]


class _Clock:
    """Seconds spent in each step of the last diarization (SpeakerModel.timings)."""

    def __init__(self):
        import time
        self._now = time.perf_counter
        self._last = self._now()
        self.laps = {}

    def lap(self, name):
        now = self._now()
        self.laps[name] = round(now - self._last, 2)
        self._last = now


class _Progress:
    def __init__(self, on_progress, should_cancel):
        self.on_progress, self.should_cancel = on_progress, should_cancel
        self.done, self.total = 0, 0

    def advance(self, amount):
        if self.should_cancel and self.should_cancel():
            raise Cancelled()
        self.done += amount
        if self.on_progress:
            self.on_progress(self.done, self.total)


def _runs(binary, middles):
    """(start, end, speaker) for every run of 1s in each column (pyannote's Binarize at 0.5)."""
    runs = []
    for speaker in range(binary.shape[1]):
        column = binary[:, speaker] > 0.5
        if not column.any():
            continue
        edges = np.flatnonzero(np.diff(column.astype(np.int8)))
        bounds = np.concatenate([[0], edges + 1, [len(column)]])
        for a, b in zip(bounds[:-1], bounds[1:]):
            if column[a]:
                end = middles[b] if b < len(column) else middles[-1]
                runs.append((float(middles[a]), float(end), speaker))
    return runs


def _nearest(masks, size):
    """(B, frames, 3) masks -> (B, size, 3) by nearest-neighbour (torch interpolate "nearest")."""
    index = np.floor(np.arange(size) * (masks.shape[1] / size)).astype(np.int64)
    return masks[:, np.minimum(index, masks.shape[1] - 1), :]


def _mel_banks(num_bins=80, padded=512, low=20.0, high=8000.0):
    """Kaldi mel filter bank (torchaudio.compliance.kaldi.get_mel_banks), (bins, padded / 2)."""
    def mel(f):
        return 1127.0 * np.log(1.0 + f / 700.0)
    fft_bins = padded // 2
    bin_width = SAMPLE_RATE / padded
    low_mel, high_mel = mel(low), mel(high)
    delta = (high_mel - low_mel) / (num_bins + 1)
    left = low_mel + np.arange(num_bins)[:, None] * delta
    centre = left + delta
    right = centre + delta
    freq_mel = mel(bin_width * np.arange(fft_bins))[None, :]
    up = (freq_mel - left) / (centre - left)
    down = (right - freq_mel) / (right - centre)
    return np.maximum(0.0, np.minimum(up, down))


def _l2_rows(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def _softmax(x):
    x = x - x.max(axis=1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=1, keepdims=True)


def _logsumexp(x):
    top = x.max(axis=1, keepdims=True)
    return (top + np.log(np.exp(x - top).sum(axis=1, keepdims=True)))[:, 0]
