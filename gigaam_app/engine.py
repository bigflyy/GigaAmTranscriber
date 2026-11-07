"""Transcription pipeline: decode audio, find speech, recognise chunks in order.

Load a Transcriber once and reuse it for many files: opening the model is the
slow part of starting up (two to three seconds), not the transcription itself.

One file runs as three overlapping stages, each on its own thread:

    speech search (Silero, CPU) -> encoder (GPU or CPU) -> decoder (numpy)

Chunks flow through queues as soon as they are final, so recognition starts
a few seconds into the file instead of after the whole file has been searched.
Order is kept, so segments come out in time order.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path
import queue
import threading
import time

from . import catalog
from .asr import AsrModel, Word, create_session
from .audio import SAMPLE_RATE, decode_audio
from .catalog import ModelNotInstalled
from .paths import models_dir
from .vad import WINDOW, ChunkFinder, SileroVad, VadOptions
from .whisper_model import WhisperModel, is_whisper_folder

# Model key -> exported model folder, for every model in the catalog.
MODELS = {info.key: info.folder for info in catalog.CATALOG}
BUNDLED_MODELS = {info.key: info.folder for info in catalog.CATALOG if info.bundled}
DEFAULT_MODEL = "RNNT"

# GPU batches: at most this many chunks and this much padded audio per encoder call.
GPU_BATCH_CHUNKS = 8
GPU_BATCH_SECONDS = 200
_END = object()  # queue sentinel: the stage before has finished


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list = field(default_factory=list)


@dataclass
class Transcript:
    source: str
    model: str
    device: str
    audio_seconds: float = 0.0
    speech_seconds: float = 0.0
    recognised_seconds: float = 0.0  # audio inside recognition chunks (speech plus short pauses)
    segments: list = field(default_factory=list)
    cancelled: bool = False
    elapsed_seconds: float = 0.0
    # The window looked for other readings of the doubtful words (plan 06); they are kept
    # in Word.suggestions. Not written to the transcript files.
    suggestions_searched: bool = False

    @property
    def text(self):
        return "\n".join(segment.text for segment in self.segments if segment.text)


class Transcriber:
    """A loaded model plus VAD. One transcription at a time per instance."""

    def __init__(self, model=DEFAULT_MODEL, device="auto", cpu_threads=None, model_root=None, language=None):
        """model: a catalog key (or a v0.1 name). model_root: one folder holding the
        model folder and the VAD model, instead of the normal lookup (tests, experiments).
        language: Whisper only, a code such as "ru", or None / "auto" to detect it per chunk
        (GigaAM models are Russian and ignore it).
        Raises ModelNotInstalled for a downloadable model that is not downloaded yet."""
        started = time.perf_counter()
        if model_root:
            root = Path(model_root)
            folder = root / MODELS.get(model, model)
        else:
            root = models_dir()
            info = catalog.find(model)
            model = info.key
            folder = catalog.installed_folder(info)
            if folder is None:
                if info.bundled:
                    raise FileNotFoundError(f"Model not found: {root / info.folder}")
                raise ModelNotInstalled(info)
        self.model_label = model
        if is_whisper_folder(folder):
            self.asr = WhisperModel(folder, device=device, cpu_threads=cpu_threads, language=language)
        else:
            self.asr = AsrModel(folder, device=device, cpu_threads=cpu_threads)
        # Silero does tiny sequential steps; one CPU thread is fastest.
        vad_session, _ = create_session(root / "silero_vad_scan.onnx", device="cpu", cpu_threads=1)
        self.vad = SileroVad(vad_session)
        self.load_seconds = time.perf_counter() - started

    @property
    def device_label(self):
        return self.asr.device_label

    @property
    def uses_language(self):
        """True for Whisper, which can be told the language; GigaAM knows only Russian."""
        return hasattr(self.asr, "set_language")

    def set_language(self, language):
        """Language for the next files (Whisper only; GigaAM ignores it): a code such as
        "en", or None / "auto" to detect it per chunk. No reload is needed.
        ValueError for a code Whisper does not know."""
        if self.uses_language:
            self.asr.set_language(language)

    def transcribe(self, path, options=None, on_progress=None, on_segment=None,
                   should_cancel=None, on_stats=None):
        """Transcribe one file and return a Transcript.

        Callbacks run on the calling thread:
        on_progress(searched, recognised): fractions of the file searched for
            speech and recognised so far, both in [0, 1].
        on_stats(transcript): once, when the speech search has finished.
        on_segment(segment): for every recognised chunk, in time order.
        should_cancel(): may also be called from worker threads. Segments
            finished before cancelling are kept in the result.
        """
        options = self._fit_options(options or VadOptions())
        stop = threading.Event()

        def cancelled():
            return stop.is_set() or (should_cancel is not None and should_cancel())

        started = time.perf_counter()
        result = Transcript(source=str(path), model=self.model_label, device=self.device_label)
        audio = decode_audio(path)
        n_samples = len(audio)
        result.audio_seconds = n_samples / SAMPLE_RATE
        finder = ChunkFinder(n_samples, options)
        chunk_queue = queue.Queue()
        encoded_queue = queue.Queue(maxsize=2)  # keeps the encoder at most two batches ahead
        progress = {"searched": 0, "search_done": False, "chunk_samples": 0}
        errors = []

        def search():
            try:
                for first, probabilities in self.vad.blocks(audio):
                    for index, probability in enumerate(probabilities.tolist(), first):
                        for chunk in finder.feed(index, probability):
                            progress["chunk_samples"] += chunk[1] - chunk[0]
                            chunk_queue.put(chunk)
                    progress["searched"] = min(n_samples, (first + len(probabilities)) * WINDOW)
                    if cancelled():
                        return
                for chunk in finder.finish():
                    progress["chunk_samples"] += chunk[1] - chunk[0]
                    chunk_queue.put(chunk)
                progress["searched"] = n_samples
                progress["search_done"] = True
            except BaseException as error:
                errors.append(error)
            finally:
                chunk_queue.put(_END)

        def encode():
            try:
                for batch in self._batches(chunk_queue):
                    if cancelled():
                        return
                    encoded_queue.put((batch, self._encode(audio, batch, cancelled)))
            except BaseException as error:
                errors.append(error)
            finally:
                encoded_queue.put(_END)

        workers = [threading.Thread(target=search, daemon=True), threading.Thread(target=encode, daemon=True)]
        for worker in workers:
            worker.start()
        stats_sent = False
        recognised = 0
        try:
            while True:
                if not stats_sent and progress["search_done"]:
                    stats_sent = True
                    result.speech_seconds = finder.speech_seconds
                    result.recognised_seconds = progress["chunk_samples"] / SAMPLE_RATE
                    if on_stats is not None:
                        on_stats(result)
                try:
                    item = encoded_queue.get(timeout=0.1)
                except queue.Empty:
                    item = None
                if item is _END:
                    break
                if item is not None:
                    for (start, end), features in zip(*item):
                        segment = self._segment(features, start, end)
                        result.segments.append(segment)
                        recognised = end
                        if on_segment is not None:
                            on_segment(segment)
                        if cancelled():
                            break
                if cancelled():
                    result.cancelled = True
                    break
                if on_progress is not None:
                    on_progress(progress["searched"] / n_samples if n_samples else 1.0,
                                recognised / n_samples if n_samples else 1.0)
        finally:
            # Normally both workers are already done. After a cancel, an error or
            # an exception in a callback, tell them to stop, and drain so one
            # blocked on the full queue can finish.
            stop.set()
            while any(worker.is_alive() for worker in workers):
                try:
                    encoded_queue.get(timeout=0.05)
                except queue.Empty:
                    pass
        if errors:
            raise errors[0]
        if not stats_sent and progress["search_done"]:
            result.speech_seconds = finder.speech_seconds
            result.recognised_seconds = progress["chunk_samples"] / SAMPLE_RATE
            if on_stats is not None:
                on_stats(result)
        if not result.cancelled and on_progress is not None:
            on_progress(1.0, 1.0)
        result.elapsed_seconds = time.perf_counter() - started
        return result

    def _fit_options(self, options):
        """Keep chunks inside the model's window: Whisper hears at most 30 s per call,
        and settings may allow longer chunks (GigaAM has no such limit)."""
        limit = getattr(self.asr, "max_chunk_seconds", None)
        if limit is None:
            return options
        return replace(options, **{key: min(getattr(options, key), limit)
                                   for key in ("max_duration", "strict_limit_duration", "vad_max_speech_s")})

    def _batches(self, chunk_queue):
        """Yield encoder batches of consecutive chunks as they arrive.

        On CPU every chunk runs alone: batching gave nothing there (measured)
        and padding wastes work. On GPU the chunks already waiting are joined
        into one call, without waiting for more. Whisper always takes one chunk
        per call (whisper.cpp recognises one window at a time).
        """
        carried = None
        while True:
            chunk = carried if carried is not None else chunk_queue.get()
            carried = None
            if chunk is _END:
                return
            batch, longest = [chunk], chunk[1] - chunk[0]
            if self.asr.joins_chunks:
                while len(batch) < GPU_BATCH_CHUNKS:
                    try:
                        following = chunk_queue.get_nowait()
                    except queue.Empty:
                        break
                    if following is _END:
                        carried = _END
                        break
                    grown = max(longest, following[1] - following[0])
                    if grown * (len(batch) + 1) > GPU_BATCH_SECONDS * SAMPLE_RATE:
                        carried = following
                        break
                    batch.append(following)
                    longest = grown
            yield batch

    def _encode(self, audio, batch, should_cancel=None):
        """Encoder output per chunk. Whisper does the whole recognition here and may
        return fewer results than chunks after a cancel (zip() below drops the rest)."""
        return self.asr.encode([audio[start:end] for start, end in batch], should_cancel=should_cancel)

    def _segment(self, features, start, end):
        tokens = self.asr.decode(features)
        words = self.asr.words(tokens, start / SAMPLE_RATE)
        return Segment(start=round(start / SAMPLE_RATE, 3), end=round(end / SAMPLE_RATE, 3),
                       text=" ".join(word.text for word in words), words=words)


__all__ = ["MODELS", "BUNDLED_MODELS", "DEFAULT_MODEL", "ModelNotInstalled", "Segment", "Transcript", "Transcriber", "VadOptions", "Word"]
