"""The model thread behind the window: owns the Transcriber, runs one job at a time.

Jobs come in through `jobs`, events go out through the queue given to it:
("loading", model), ("load_failed", model, text), ("loaded", device_label, seconds, model),
("status", text), ("progress", searched, recognised),
("stats", transcript), ("segment", segment), ("finished", transcript or None, written paths),
("download_progress", model, done, total), ("download_done", model, folder or None), ("error", text).
"""

import queue
import threading
import time

from . import catalog, download
from .engine import Transcriber
from .outputs import write_outputs


class Worker(threading.Thread):
    """Owns the Transcriber. Jobs come in through a queue, events go out through another."""

    def __init__(self, events):
        super().__init__(daemon=True)
        self.jobs = queue.Queue()
        self.events = events
        self.cancel = threading.Event()
        self.engine = None
        self.engine_key = None

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

    def _transcribe(self, path, key, options, formats):
        self.cancel.clear()
        engine = self._ensure(key)
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
        written = write_outputs(result, formats) if result.segments else []
        self.events.put(("finished", result, written))
