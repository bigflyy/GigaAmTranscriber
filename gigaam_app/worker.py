"""The model thread behind the window: owns the Transcriber, runs one job at a time.

Jobs come in through `jobs`, events go out through the queue given to it:
("loading", model), ("load_failed", model, text), ("loaded", device_label, seconds, model),
("status", text), ("progress", searched, recognised),
("stats", transcript), ("segment", segment), ("finished", transcript or None, written paths),
("download_progress", model, done, total), ("download_done", model, folder or None), ("error", text).

Recognising a selected part again (plan 03, fix.py) sends ("reread_range", request, start, end),
("reread_loading", request, model), ("reread_result", request, model, words or None, error text)
for each model, and ("reread_done", request).
"""

import queue
import threading
import time

from . import catalog, download, fix
from .audio import SAMPLE_RATE, decode_range
from .engine import Transcriber
from .outputs import LLM_DOUBT_BELOW, write_outputs

# Audio decoded around a selection beyond its search windows, so the cut never ends the samples.
REREAD_MARGIN = 0.05


class Worker(threading.Thread):
    """Owns the Transcriber. Jobs come in through a queue, events go out through another."""

    def __init__(self, events):
        super().__init__(daemon=True)
        self.jobs = queue.Queue()
        self.events = events
        self.cancel = threading.Event()
        self.engine = None
        self.engine_key = None
        self.spare = {}  # other models loaded to recognise a selected part again: key -> Transcriber

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
        # Opening the model holds the interpreter for about two seconds; let the
        # window's threads show "loading" first instead of a stale status.
        time.sleep(0.1)
        try:
            engine = Transcriber(model, device=device, cpu_threads=threads or None)
        except Exception as error:
            self.events.put(("load_failed", model, str(error) or type(error).__name__))
            raise
        self.engine, self.engine_key = engine, key
        self.events.put(("loaded", engine.device_label, engine.load_seconds, model))
        return engine

    def _download(self, model):
        self.cancel.clear()
        info = catalog.find(model)
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

    def _reread(self, request, path, windows, models, device, threads, language=None, prompt=None):
        """Recognise a selected part again with each model in turn (plan 03 A3).

        windows: ((left_lo, left_hi), (right_lo, right_hi)) from fix.search_windows; the
        cuts go to the quietest point of each. A model that fails reports its error and
        the others still run.
        """
        (left, right) = windows
        offset = max(0.0, left[0] - REREAD_MARGIN)
        samples = decode_range(path, offset, right[1] + REREAD_MARGIN - offset)
        start = fix.quietest_point(samples, offset, *left)
        end = fix.quietest_point(samples, offset, *right)
        piece = samples[int(round((start - offset) * SAMPLE_RATE)):int(round((end - offset) * SAMPLE_RATE))]
        self.events.put(("reread_range", request, start, end))
        for model in models:
            try:
                engine = self._engine_for((model, device, threads),
                                          on_load=lambda: self.events.put(("reread_loading", request, model)))
                if engine.uses_language:
                    engine.set_language(language)
                words = fix.reread_piece(engine.asr, piece, start, prompt=prompt if engine.uses_language else None)
                self.events.put(("reread_result", request, model, words, None))
            except Exception as error:  # one model failing must not hide the others' readings
                self.events.put(("reread_result", request, model, None, str(error) or type(error).__name__))
        self.events.put(("reread_done", request))
