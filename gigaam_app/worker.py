"""The models behind the window: the Worker owns the Transcriber and runs one job at a time.

The window runs the Worker in a process of its own (WorkerProcess, below). ONNX Runtime holds
Python's interpreter lock for seconds while it opens a GigaAM model, and pywebview runs Python
on every move of the window, so a Worker thread in the window's process froze the window for
about 4 s at each load (measured in session 16). Experiments still use Worker as a thread.

Jobs come in through `jobs`, events go out through the queue given to it:
("loading", model), ("load_failed", model, text), ("loaded", device_label, seconds, model),
("status", text), ("progress", searched, recognised),
("stats", transcript), ("segment", segment), ("finished", transcript or None, written paths),
("download_progress", model, done, total), ("download_done", model, folder or None), ("error", text).

Recognising a selected part again (plan 03, fix.py) sends ("reread_range", request, start, end),
("reread_loading", request, model), ("reread_result", request, model, words or None, error text)
for each model, and ("reread_done", request); when the audio cannot be read,
("reread_failed", request, error text) comes before "reread_done".

Looking for suggested fixes (plan 06) recognises one group of doubtful words the same way:
the job "suggest" sends the same events named suggest_range, suggest_loading, suggest_result
suggest_failed and suggest_done.

Looking for speakers (plan 07, diarize.py), job ("diarize", request, path, device, threads,
num_speakers), sends ("diarize_loading", request) when the speaker models load,
("diarize_progress", request, done, total) and at the end one
("diarize_result", request, turns or None, error text or None): turns are
(start, end, speaker) of the exclusive diarization (one speaker at a time); None with
no error text when the job was cancelled.
"""

import multiprocessing
import os
import queue
import threading
import time

from . import catalog, diarize, download, fix
from .audio import SAMPLE_RATE, decode_audio, decode_range
from .engine import Transcriber
from .outputs import LLM_DOUBT_BELOW, write_outputs
from .paths import restore_child_environment

# Audio decoded around a selection beyond its search windows, so the cut never ends the samples.
REREAD_MARGIN = 0.05
# How often the window's side checks that the model process is still alive, in seconds.
ALIVE_CHECK = 0.5
# Seconds the model process gets to end by itself after its last job, before it is ended.
EXIT_WAIT = 5


class Worker(threading.Thread):
    """Owns the Transcriber. Jobs come in through a queue, events go out through another.

    jobs and cancel may be given (the model process passes its multiprocessing ones);
    by default they are a queue.Queue and a threading.Event."""

    def __init__(self, events, jobs=None, cancel=None):
        super().__init__(daemon=True)
        self.jobs = queue.Queue() if jobs is None else jobs
        self.events = events
        self.cancel = threading.Event() if cancel is None else cancel
        self.engine = None
        self.engine_key = None
        self.spare = {}  # other models loaded to recognise a selected part again: key -> Transcriber
        self.speaker_model = None  # (device, threads, diarize.SpeakerModel), loaded at the first "diarize"

    def run(self):
        while True:
            job = self.jobs.get()
            if job is None:  # stop(): the window has closed
                return
            try:
                if job[0] == "load":
                    self._ensure(job[1])
                elif job[0] == "transcribe":
                    self._transcribe(*job[1:])
                elif job[0] == "download":
                    self._download(job[1])
                elif job[0] == "reread":
                    self._reread(*job[1:])
                elif job[0] == "suggest":
                    self._reread(*job[1:], prefix="suggest")
                elif job[0] == "diarize":
                    self._diarize(*job[1:])
            except Exception as error:  # every failure is shown in the window
                self.events.put(("error", str(error) or type(error).__name__))

    def stop(self, timeout=60):
        """Cancel the running job and wait until it has ended: a cancelled file still
        writes the text found so far. Leaving earlier would also end the process while
        ONNX Runtime threads run, which aborts it on Linux."""
        self.cancel.set()
        while True:  # jobs not started yet are dropped
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                break
        self.jobs.put(None)
        self.join(timeout)

    def _ensure(self, key):
        if self.engine is not None and self.engine_key == key:
            return self.engine
        model, device, threads = key
        if key in self.spare:  # loaded earlier for a selected part: no second load
            if self.engine is not None:
                self.spare[self.engine_key] = self.engine
            self.engine, self.engine_key = self.spare.pop(key), key
            self.events.put(("loaded", self.engine.device_label, 0.0, model))
            return self.engine
        self.engine = None
        self.events.put(("loading", model))
        try:
            engine = Transcriber(model, device=device, cpu_threads=threads or None)
        except Exception as error:
            self.events.put(("load_failed", model, str(error) or type(error).__name__))
            raise
        self.engine, self.engine_key = engine, key
        self.events.put(("loaded", engine.device_label, engine.load_seconds, model))
        return engine

    def _download(self, model):
        """model: a catalog key, or its ModelInfo (WorkerProcess sends the ModelInfo, so a
        model registered only in the window's process, like window_check's test model, works)."""
        self.cancel.clear()
        info = model if isinstance(model, catalog.ModelInfo) else catalog.find(model)
        model = info.key
        last = [0.0]

        def progress(done, total):
            now = time.perf_counter()
            if now - last[0] > 0.1 or done == total:
                last[0] = now
                self.events.put(("download_progress", model, done, total))

        try:
            folder = download.install(info, on_progress=progress, should_cancel=self.cancel.is_set)
        except download.DownloadCancelled:
            self.events.put(("download_done", model, None))
            return
        self.events.put(("download_done", model, folder))

    def _transcribe(self, path, key, options, formats, language=None, doubt_below=LLM_DOUBT_BELOW):
        self.cancel.clear()
        engine = self._ensure(key)
        engine.set_language(language)  # Whisper only; changing it needs no reload
        if self.cancel.is_set():
            self.events.put(("finished", None, []))
            return
        self.events.put(("status", "Поиск речи..."))
        result = engine.transcribe(
            path, options,
            on_progress=lambda stage, fraction: self.events.put(("progress", stage, fraction)),
            on_segment=lambda segment: self.events.put(("segment", segment)),
            on_stats=lambda transcript: self.events.put(("stats", transcript)),
            should_cancel=self.cancel.is_set)
        written = write_outputs(result, formats, doubt_below=doubt_below) if result.segments else []
        self.events.put(("finished", result, written))

    def _engine_for(self, key, on_load=None):
        """A loaded Transcriber for key (model, device, threads): the main one when it
        matches, else a spare one, loaded once and kept. Spares for another device or
        thread count are dropped first, so at most one copy of each model stays loaded."""
        if self.engine is not None and self.engine_key == key:
            return self.engine
        if key not in self.spare:
            for other in [other for other in self.spare if other[1:] != key[1:]]:
                del self.spare[other]
            if on_load is not None:
                on_load()
            model, device, threads = key
            self.spare[key] = Transcriber(model, device=device, cpu_threads=threads or None)
        return self.spare[key]

    def _reread(self, request, path, windows, models, device, threads, language=None, prompt=None,
                prefix="reread"):
        """Recognise a selected part again with each model in turn (plan 03 A3).

        windows: ((left_lo, left_hi), (right_lo, right_hi)) from fix.search_windows; the
        cuts go to the quietest point of each. A model that fails reports its error and
        the others still run. prefix names the events: "reread" for a selection,
        "suggest" for a group of doubtful words (plan 06).
        """
        (left, right) = windows
        try:
            offset = max(0.0, left[0] - REREAD_MARGIN)
            samples = decode_range(path, offset, right[1] + REREAD_MARGIN - offset)
        except Exception as error:  # the file is gone or unreadable: no model can run
            self.events.put((prefix + "_failed", request, str(error) or type(error).__name__))
            self.events.put((prefix + "_done", request))
            return
        start = fix.quietest_point(samples, offset, *left)
        end = fix.quietest_point(samples, offset, *right)
        piece = samples[int(round((start - offset) * SAMPLE_RATE)):int(round((end - offset) * SAMPLE_RATE))]
        self.events.put((prefix + "_range", request, start, end))
        for model in models:
            try:
                engine = self._engine_for((model, device, threads),
                                          on_load=lambda: self.events.put((prefix + "_loading", request, model)))
                if engine.uses_language:
                    engine.set_language(language)
                words = fix.reread_piece(engine.asr, piece, start, prompt=prompt if engine.uses_language else None)
                self.events.put((prefix + "_result", request, model, words, None))
            except Exception as error:  # one model failing must not hide the others' readings
                self.events.put((prefix + "_result", request, model, None, str(error) or type(error).__name__))
        self.events.put((prefix + "_done", request))

    def _diarize(self, request, path, device, threads, num_speakers=None):
        """Find who speaks when in a whole file (plan 07)."""
        self.cancel.clear()
        try:
            folder = catalog.installed_folder(catalog.SPEAKER_MODEL)
            if folder is None:
                raise catalog.ModelNotInstalled(catalog.SPEAKER_MODEL)
            if self.speaker_model is None or self.speaker_model[:2] != (device, threads):
                self.events.put(("diarize_loading", request))
                self.speaker_model = None
                model = diarize.SpeakerModel(folder, device=device, cpu_threads=threads or None)
                self.speaker_model = (device, threads, model)
            model = self.speaker_model[2]
            audio = decode_audio(path)
            last = [0.0]

            def progress(done, total):
                now = time.perf_counter()
                if now - last[0] > 0.2 or done == total:
                    last[0] = now
                    self.events.put(("diarize_progress", request, done, total))

            result = model.diarize(audio, num_speakers=num_speakers, on_progress=progress,
                                   should_cancel=self.cancel.is_set)
        except Exception as error:
            self.events.put(("diarize_result", request, None, str(error) or type(error).__name__))
            return
        if result.cancelled:
            self.events.put(("diarize_result", request, None, None))
            return
        turns = [(turn.start, turn.end, turn.speaker) for turn in result.exclusive_turns]
        self.events.put(("diarize_result", request, turns, None))


# ---------------------------------------------------------------------- the model process

def _job_subject(job):
    """What a job is about, for WorkerProcess when the process ends unexpectedly:
    the model key of a load or a file, the request of a reread or a suggestion search."""
    if job[0] == "load":
        return job[1]
    if job[0] == "transcribe":
        return job[2]
    if job[0] in ("reread", "suggest", "diarize"):
        return job[1]
    return None


class _ChildJobs:
    """The model process's job queue: tells the window when the last job has ended and
    which job starts, before it runs."""

    def __init__(self, jobs, events):
        self.jobs = jobs
        self.events = events

    def get(self):
        self.events.put(("_job", None, None))  # between jobs
        job = self.jobs.get()
        if job is not None:
            self.events.put(("_job", job[0], _job_subject(job)))
        return job


class _ChildEvents:
    """The model process's event queue: before "loaded" it sends the Worker's engine_key,
    which the controller reads from WorkerProcess.engine_key when "loaded" arrives."""

    def __init__(self, events):
        self.events = events
        self.worker = None

    def put(self, event):
        if event[0] == "loaded":
            self.events.put(("_engine_key", self.worker.engine_key))
        self.events.put(event)


def _end_with_parent(parent):
    """Model process: end at once when the window's process has gone (also when it was
    killed), so no model stays loaded in memory with nobody to use it."""
    parent.join()
    os._exit(0)


def run_model_process(jobs, events, cancel):
    """The model process's main function: a Worker reading jobs until None arrives."""
    restore_child_environment()  # ffmpeg started from here must get the user's libraries (Linux build)
    parent = multiprocessing.parent_process()
    if parent is not None:
        threading.Thread(target=_end_with_parent, args=(parent,), name="gigaam-parent-watch", daemon=True).start()
    outbox = _ChildEvents(events)
    worker = Worker(outbox, jobs=_ChildJobs(jobs, events), cancel=cancel)
    outbox.worker = worker
    worker.run()
    events.put(("_exit",))


class _Jobs:
    """WorkerProcess.jobs: put() sends a job to the model process (a download carries the
    ModelInfo, not only its key); get_nowait() and empty() as on a queue."""

    def __init__(self, owner):
        self.owner = owner

    def put(self, job):
        if job is not None and job[0] == "download" and not isinstance(job[1], catalog.ModelInfo):
            job = ("download", catalog.find(job[1]))
        with self.owner.lock:
            self.owner.inbox.put(job)

    def get_nowait(self):
        return self.owner.inbox.get_nowait()

    def empty(self):
        return self.owner.inbox.empty()


class WorkerProcess:
    """The Worker in a process of its own, used by the window like the Worker thread:
    jobs.put(job), cancel (set / clear / is_set), engine_key, start() and stop().

    A thread here passes the process's events on to the window's events queue. If the
    process ends unexpectedly (a crash in a model library), the window gets an error for
    the job that was running and a new process takes the jobs that were waiting."""

    def __init__(self, events):
        self.events = events
        self.context = multiprocessing.get_context("spawn")  # never fork: the window has threads
        self.cancel = self.context.Event()
        self.engine_key = None
        self.jobs = _Jobs(self)
        self.lock = threading.Lock()   # guards inbox while a new process replaces it
        self.inbox = None              # jobs to the process
        self.process = None
        self.forwarder = None
        self.current = None            # (kind, subject) of the job the process started last
        self.loading = None            # the model the process is opening, between loading and loaded
        self.stopping = False

    def start(self):
        with self.lock:
            self._launch()

    def _launch(self):
        """Start a model process with new queues (called with self.lock held)."""
        self.inbox = self.context.Queue()
        outbox = self.context.Queue()
        self.process = self.context.Process(target=run_model_process, args=(self.inbox, outbox, self.cancel),
                                            name="gigaam-models", daemon=True)
        self.process.start()
        self.forwarder = threading.Thread(target=self._forward, args=(self.process, outbox),
                                          name="gigaam-model-events", daemon=True)
        self.forwarder.start()

    def _forward(self, process, outbox):
        """Pass the process's events on until it says it has ended, or is found gone."""
        while True:
            try:
                event = outbox.get(timeout=ALIVE_CHECK)
            except queue.Empty:
                if process.is_alive():
                    continue
                # Gone: take what it sent just before, then report the job it was on.
                while True:
                    try:
                        event = outbox.get(timeout=0.1)
                    except queue.Empty:
                        break
                    if not self._pass_on(event):
                        return
                self._lost(process)
                return
            if not self._pass_on(event):
                return

    def _pass_on(self, event):
        """Handle one event from the process; False once the process has said it ends."""
        kind = event[0]
        if kind == "_exit":
            return False
        if kind == "_engine_key":
            self.engine_key = event[1]
        elif kind == "_job":
            self.current = event[1:]
        else:
            if kind == "loading":
                self.loading = event[1]
            elif kind in ("loaded", "load_failed"):
                self.loading = None
            self.events.put(event)
        return True

    def _lost(self, process):
        """The process ended without being asked: tell the window, start a new one."""
        if self.stopping:
            return
        text = (f"Процесс распознавания неожиданно завершился (код {process.exitcode}). "
                "Модель загрузится заново при следующем запуске.")
        with self.lock:
            waiting = []
            while True:  # jobs the old process had not started yet go to the new one
                try:
                    waiting.append(self.inbox.get(timeout=0.1))
                except (queue.Empty, OSError, EOFError):
                    break
            self.engine_key = None
            current, self.current = self.current, None
            loading, self.loading = self.loading, None
            self._launch()
            for job in waiting:
                self.inbox.put(job)
        kind, subject = current if current else (None, None)
        if kind in ("reread", "suggest"):
            self.events.put((kind + "_failed", subject, text))
            self.events.put((kind + "_done", subject))
            return
        if kind == "diarize":
            self.events.put(("diarize_result", subject, None, text))
            return
        if loading is not None:
            self.events.put(("load_failed", loading, text))
        self.events.put(("error", text))

    def stop(self, timeout=60):
        """Cancel the running job and wait until the process has ended: a cancelled file
        still writes the text found so far, and its last events reach the window."""
        self.stopping = True
        self.cancel.set()
        with self.lock:
            while True:  # jobs not started yet are dropped
                try:
                    self.inbox.get_nowait()
                except (queue.Empty, OSError, EOFError):
                    break
            self.inbox.put(None)
        self.forwarder.join(timeout)
        self.process.join(EXIT_WAIT)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(EXIT_WAIT)
