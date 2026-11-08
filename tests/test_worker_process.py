"""The model process (gigaam_app.worker.WorkerProcess) with a model that does not exist:
no model is loaded, so this stays light (each process only imports the app)."""

import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gigaam_app.worker import WorkerProcess  # noqa: E402

WAIT = 60  # seconds: a new process imports ONNX Runtime and NumPy first
MISSING = ("NoSuchModel", "cpu", 0)


def next_event(events, kinds):
    """The next event whose kind is one of kinds; other events are skipped."""
    while True:
        event = events.get(timeout=WAIT)
        if event[0] in kinds:
            return event


def test_events_come_from_the_process_and_stop_ends_it():
    events = queue.Queue()
    worker = WorkerProcess(events)
    worker.start()
    try:
        worker.jobs.put(("load", MISSING))
        assert next_event(events, {"loading"}) == ("loading", "NoSuchModel")
        failed = next_event(events, {"load_failed"})
        assert failed[1] == "NoSuchModel" and "NoSuchModel" in failed[2]
        assert next_event(events, {"error"})[0] == "error"
        assert worker.engine_key is None
    finally:
        worker.stop()
    assert not worker.process.is_alive()
    assert worker.cancel.is_set()


def test_a_crashed_process_is_reported_and_replaced():
    events = queue.Queue()
    worker = WorkerProcess(events)
    worker.start()
    try:
        worker.jobs.put(("load", MISSING))
        next_event(events, {"error"})  # the process is up and has run a job
        first = worker.process
        first.kill()
        error = next_event(events, {"error"})
        assert "неожиданно завершился" in error[1]
        assert worker.process is not first
        # The new process takes jobs.
        worker.jobs.put(("load", MISSING))
        assert next_event(events, {"loading"}) == ("loading", "NoSuchModel")
    finally:
        worker.stop()
    assert not worker.process.is_alive()
