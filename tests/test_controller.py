"""The window's logic (gigaam_app/controller.py) with a fake worker: no model, no window."""

from pathlib import Path
import queue
import threading

import pytest

from gigaam_app import catalog, config
from gigaam_app import controller as controller_module
from gigaam_app.catalog import ModelInfo, RemoteFile
from gigaam_app.controller import Controller, about_text, duration_text, times_text
from gigaam_app.engine import Segment, Transcript, Word


class FakeWorker:
    """Takes jobs like gigaam_app.worker.Worker but runs nothing; tests play its events."""

    def __init__(self):
        self.jobs = queue.Queue()
        self.cancel = threading.Event()
        self.engine_key = None

    def take(self):
        return [self.jobs.get_nowait() for _ in range(self.jobs.qsize())]


class FakeDesktop:
    def __init__(self):
        self.opened = []
        self.shown = []

    def open_path(self, path):
        self.opened.append(Path(path))

    def show_in_folder(self, path):
        self.shown.append(Path(path))


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def media(tmp_path):
    files = []
    for name in ("a.mp3", "b.wav", "c.m4a"):
        path = tmp_path / name
        path.write_bytes(b"fake")
        files.append(path)
    return files


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A ready controller whose bundled models count as installed."""
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path if info.bundled else None)
    sent = []
    worker = FakeWorker()
    desktop = FakeDesktop()
    clock = Clock()
    control = Controller(worker, queue.Queue(), send=sent.append, clock=clock, probe=lambda path: 61.0,
                         desktop=desktop, settings_path=tmp_path / "settings.json")
    control.sent, control.fake_worker, control.desktop, control.fake_clock = sent, worker, desktop, clock
    snapshot = control.ready()
    control.snapshot = snapshot
    return control


def kinds(sent):
    return [message["kind"] for message in sent]


def last(sent, kind):
    return next(message["data"] for message in reversed(sent) if message["kind"] == kind)


def segment(start, end, text):
    return Segment(start=start, end=end, text=text, words=[Word(text=text, start=start, end=end)])


def finish(control, item_path, segments, cancelled=False, formats=("txt", "timestamps")):
    """Play a whole transcription of the running file and write real outputs."""
    for seg in segments:
        control.handle(("segment", seg))
    result = Transcript(source=str(item_path), model="RNNT", device="CPU", audio_seconds=61.0,
                        segments=list(segments), cancelled=cancelled)
    from gigaam_app.outputs import write_outputs
    written = write_outputs(result, list(formats)) if segments else []
    control.handle(("finished", result, written))
    return written


# ---------------------------------------------------------------------- texts

def test_texts():
    assert duration_text(455) == "7:35"
    assert duration_text(3723) == "1:02:03"
    assert about_text(3) == "около 3 с"
    assert about_text(130) == "около 2 мин"
    assert about_text(3900) == "около 1 ч 5 мин"
    assert times_text(87) == "в 87 раз"
    assert times_text(33) == "в 33 раза"
    assert times_text(12) == "в 12 раз"
    assert times_text(21) == "в 21 раз"


# ---------------------------------------------------------------------- start-up

def test_ready_loads_the_model_and_returns_a_snapshot(app):
    assert app.snapshot["files"] == []
    assert app.snapshot["settings"]["model"] == "RNNT"
    assert [m["key"] for m in app.snapshot["options"]["models"]] == ["RNNT", "CTC"]
    assert app.fake_worker.take() == [("load", ("RNNT", "auto", 0))]


def test_nothing_is_sent_before_the_page_is_ready(tmp_path, monkeypatch, media):
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path)
    sent = []
    worker = FakeWorker()
    control = Controller(worker, queue.Queue(), send=sent.append, probe=lambda path: None,
                         settings_path=tmp_path / "s.json", initial_files=[str(media[0])])
    control.handle(("loading", "RNNT"))
    assert sent == [] and worker.jobs.empty()
    snapshot = control.ready()
    # Files from the command line are in the snapshot and start at once.
    assert [f["name"] for f in snapshot["files"]] == ["a.mp3"]
    assert [job[0] for job in worker.take()] == ["load", "transcribe"]
    assert all(message["seq"] > snapshot["seq"] for message in sent)


def test_a_broken_settings_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path)
    bad = tmp_path / "settings.json"
    bad.write_text("{not json", encoding="utf-8")
    sent = []
    control = Controller(FakeWorker(), queue.Queue(), send=sent.append, settings_path=bad)
    control.ready()
    assert "Файл настроек не прочитан" in last(sent, "error")["text"]


def test_engine_status_follows_the_worker(app):
    app.handle(("loading", "RNNT"))
    assert app.engine["state"] == "busy"
    app.fake_worker.engine_key = ("RNNT", "auto", 0)
    app.handle(("loaded", "GPU (DirectML)", 1.25, "RNNT"))
    assert app.engine == {"state": "ready", "text": "RNNT - видеокарта (DirectML)", "detail": "Загружена за 1.2 с"}
    app.handle(("load_failed", "RNNT", "no GPU"))
    app.handle(("error", "no GPU"))
    assert app.engine["state"] == "error"
    assert last(app.sent, "error") == {"text": "Не удалось загрузить модель RNNT: no GPU", "source": "engine"}


# ---------------------------------------------------------------------- queue (B3)

def test_files_run_one_at_a_time_in_order(app, media):
    app.fake_worker.take()
    assert app.add_files([str(p) for p in media]) == 3
    jobs = app.fake_worker.take()
    assert len(jobs) == 1 and jobs[0][0] == "transcribe" and jobs[0][1] == media[0].resolve()
    states = [f["state"] for f in last(app.sent, "files")]
    assert states == ["running", "waiting", "waiting"]
    finish(app, media[0], [segment(0.0, 2.0, "Раз.")])
    jobs = app.fake_worker.take()
    assert [job[1] for job in jobs] == [media[1].resolve()]
    assert app.files[0].state == "done" and app.files[1].state == "running"


def test_duplicates_and_missing_files_are_not_added(app, media, tmp_path):
    app.add_files([str(media[0])])
    assert app.add_files([str(media[0]), str(tmp_path / "missing.mp3")]) == 0
    assert last(app.sent, "notice")["text"].startswith("Файл не найден")
    assert len(app.files) == 1


def test_a_dropped_folder_adds_its_media_files(app, media, tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    assert app.add_files([str(tmp_path)]) == 3
    assert [item.path.name for item in app.files] == ["a.mp3", "b.wav", "c.m4a"]


def test_cancel_keeps_the_text_found_so_far(app, media):
    app.add_files([str(media[0]), str(media[1])])
    app.fake_worker.take()
    item = app.files[0]
    assert app.cancel(item.id)
    assert app.fake_worker.cancel.is_set()
    assert app._file_view(item)["status"].startswith("Отмена")
    assert not app._file_view(item)["can_cancel"]
    written = finish(app, media[0], [segment(0.0, 9.5, "Начало.")], cancelled=True)
    view = app._file_view(item)
    assert view["state"] == "cancelled"
    assert view["status"] == "Отменено на 0:10 из 1:01, готовые фрагменты сохранены."
    assert [o["path"] for o in view["outputs"] if o["path"]] == [str(p) for p in written]
    # The next file starts after a cancel.
    assert app.files[1].state == "running"


def test_cancel_before_the_first_fragment(app, media):
    app.add_files([str(media[0])])
    app.cancel(app.files[0].id)
    app.handle(("finished", None, []))
    view = app._file_view(app.files[0])
    assert view["state"] == "cancelled" and view["outputs"] == []
    assert view["status"] == "Отменено до первого фрагмента, файлы не созданы."


def test_remove_and_retry(app, media):
    app.add_files([str(media[0]), str(media[1])])
    running, waiting = app.files
    assert not app.remove(running.id)       # a running file is cancelled, not removed
    assert app.remove(waiting.id)
    assert [item.path.name for item in app.files] == ["a.mp3"]
    app.handle(("error", "Could not read audio"))
    assert app.files[0].state == "failed"
    assert app._file_view(app.files[0])["status"] == "Ошибка: Could not read audio"
    app.fake_worker.take()
    assert app.retry(app.files[0].id)
    assert {"kind": "lines_reset", "data": {"id": running.id}} in [
        {"kind": m["kind"], "data": m["data"]} for m in app.sent]
    assert app.files[0].state == "running"
    assert app.fake_worker.take()[0][0] == "transcribe"


def test_progress_and_time_left(app, media):
    app.add_files([str(media[0])])
    item = app.files[0]
    item.duration = 400.0
    app.handle(("loading", "RNNT"))
    assert app._file_view(item)["status"] == "Загрузка модели RNNT..."
    app.handle(("status", "Поиск речи..."))
    app.fake_clock.now += 10
    app.handle(("progress", 0.6, 0.25))
    view = app._file_view(item)
    assert view["progress"] == 0.25
    assert view["status"] == "Распознаю: 1:40 из 6:40, осталось около 30 с"
    assert view["detail"] == "6:40 - 25%"


def test_durations_come_from_the_probe(app, media):
    app.add_files([str(media[1])])
    app.probe_jobs.put(None)
    app._probe_loop()  # probes the queued file, then stops at None
    assert app.files[0].duration == 61.0


def test_done_status_and_speed(app, media):
    app.add_files([str(media[0])])
    app.handle(("stats", Transcript(source="", model="", device="", audio_seconds=61.0, speech_seconds=50.0)))
    app.fake_clock.now += 4
    finish(app, media[0], [segment(0.0, 3.0, "Текст.")])
    view = app._file_view(app.files[0])
    assert view["status"] == "1:01 - речь 0:50 - готово за 4 с, в 15 раз быстрее записи"
    assert view["detail"] == "1:01 - готово"


def test_no_speech(app, media):
    app.add_files([str(media[0])])
    finish(app, media[0], [])
    view = app._file_view(app.files[0])
    assert view["status"] == "1:01 - речь не найдена, файлы не созданы."
    assert view["outputs"] == []


# ---------------------------------------------------------------------- text and files (B4)

def test_live_segments_and_copy(app, media):
    app.add_files([str(media[0])])
    item = app.files[0]
    app.handle(("segment", segment(1.0, 2.5, "Первая.")))
    app.handle(("segment", segment(3.0, 4.0, "Вторая.")))
    pushed = [m["data"] for m in app.sent if m["kind"] == "segment"]
    assert [(p["index"], p["text"]) for p in pushed] == [(0, "Первая."), (1, "Вторая.")]
    assert app.segments(item.id)[1] == {"index": 1, "start": 3.0, "end": 4.0, "text": "Вторая."}
    assert app.copy_text(item.id, False) == "Первая.\nВторая.\n"
    assert app.copy_text(item.id, True).startswith("[00:01.000 - 00:02.500] Первая.\n")


def test_open_create_and_show_outputs(app, media):
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], [segment(0.0, 2.0, "Текст.")])
    view = app._file_view(item)
    assert [(o["format"], bool(o["path"])) for o in view["outputs"]] == [
        ("txt", True), ("timestamps", True), ("srt", False), ("json", False)]
    assert app.open_output(item.id, "txt")
    assert app.desktop.opened == [media[0].with_name("a-transcript.txt").resolve()]
    assert app.create_output(item.id, "srt")
    srt = media[0].with_name("a-transcript.srt")
    assert srt.read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> ")
    assert app._file_view(item)["outputs"][2]["path"] == str(srt.resolve())
    assert app.show_folder(item.id)
    assert app.desktop.shown == [media[0].with_name("a-transcript.txt").resolve()]


def test_open_output_of_a_deleted_file(app, media):
    app.add_files([str(media[0])])
    written = finish(app, media[0], [segment(0.0, 2.0, "Текст.")])
    written[0].unlink()
    assert not app.open_output(app.files[0].id, "txt")
    assert last(app.sent, "notice")["text"].startswith("Файл не найден")


# ---------------------------------------------------------------------- settings (B5)

def test_settings_apply_to_the_next_file_and_reload_the_model(app, media):
    app.fake_worker.take()
    app.set_settings({"device": "CPU", "cpu_threads": 4, "outputs": ["srt", "txt"]})
    assert last(app.sent, "settings") == {"model": "RNNT", "device": "CPU", "cpu_threads": 4,
                                          "outputs": ["txt", "srt"], "include_timestamps": False}
    assert app.fake_worker.take() == [("load", ("RNNT", "cpu", 4))]
    app.add_files([str(media[0])])
    job = app.fake_worker.take()[0]
    assert job[2] == ("RNNT", "cpu", 4) and job[4] == ["txt", "srt"]
    # While a file runs, a change does not load at once; the next file loads it.
    app.set_settings({"model": "CTC"})
    assert app.fake_worker.take() == []


def test_unknown_device_is_refused(app):
    with pytest.raises(ValueError):
        app.set_settings({"device": "TPU"})


def test_save_default(app, tmp_path):
    app.set_settings({"model": "CTC", "include_timestamps": True})
    note = app.save_default()
    assert str(tmp_path / "settings.json") in note
    saved = config.load(tmp_path / "settings.json")
    assert saved.model == "CTC" and saved.include_timestamps


# ---------------------------------------------------------------------- downloads (B5)

EXTRA = ModelInfo("Extra", "extra_model", "A test model", files=(RemoteFile("model.json", 2048 ** 2, "0" * 64),))


@pytest.fixture
def extra(monkeypatch, tmp_path):
    """One downloadable model, not on disk until `installed` is set."""
    state = {"installed": False}
    monkeypatch.setattr(catalog, "BY_KEY", {**catalog.BY_KEY, "Extra": EXTRA})
    monkeypatch.setattr(controller_module, "MODELS", {**controller_module.MODELS, "Extra": "extra_model"})
    monkeypatch.setattr(catalog, "installed_folder",
                        lambda info: tmp_path if info.bundled or state["installed"] else None)
    return state


def test_choosing_a_missing_model_asks_to_download(app, extra):
    app.fake_worker.take()
    app.set_settings({"model": "Extra"})
    ask = last(app.sent, "download")
    assert ask["phase"] == "ask" and ask["model"] == "Extra" and "4 МБ" in ask["text"]
    assert app.engine["state"] == "missing"
    assert app.fake_worker.take() == []
    assert app.download()
    assert app.fake_worker.take() == [("download", "Extra")]
    app.fake_clock.now += 5
    app.handle(("download_progress", "Extra", 1024 ** 2, 4 * 1024 ** 2))
    progress = last(app.sent, "download")
    assert progress["fraction"] == 0.25 and progress["status"].startswith("1 из 4 МБ, осталось около 15 с")
    extra["installed"] = True
    app.handle(("download_done", "Extra", Path("x")))
    assert last(app.sent, "download")["phase"] == "done"
    assert app.fake_worker.take() == [("load", ("Extra", "auto", 0))]


def test_queue_waits_for_a_declined_model(app, extra, media):
    app.set_settings({"model": "Extra"})
    app.decline_download()
    app.fake_worker.take()
    app.add_files([str(media[0])])  # adding asks again
    assert last(app.sent, "download")["phase"] == "ask"
    app.decline_download()
    assert app.files[0].state == "waiting"
    assert "Ждёт модель Extra" in app._file_view(app.files[0])["status"]
    assert app.fake_worker.take() == []
    # Choosing a bundled model starts the queue.
    app.set_settings({"model": "RNNT"})
    assert app.files[0].state == "running"


def test_a_stopped_download_leaves_the_queue_waiting(app, extra, media):
    app.set_settings({"model": "Extra"})
    app.add_files([str(media[0])])
    app.download()
    app.cancel_download()
    assert app.fake_worker.cancel.is_set()
    app.handle(("download_done", "Extra", None))
    assert last(app.sent, "download")["phase"] == "cancelled"
    assert app.files[0].state == "waiting" and app.downloading is None


def test_a_failed_download_shows_the_error(app, extra):
    app.set_settings({"model": "Extra"})
    app.download()
    app.handle(("error", "HTTP 404"))
    assert last(app.sent, "download")["phase"] == "failed"
    assert last(app.sent, "error")["text"] == "Не удалось скачать модель Extra: HTTP 404"


# ---------------------------------------------------------------------- closing

def test_closing_asks_only_while_something_runs(app, media):
    assert app.close_question() is None and app.ask_close() is False
    app.add_files([str(path) for path in media])
    question = app.close_question()
    assert "a.mp3" in question and "Файлов в очереди: 2" in question
    assert app.ask_close() is True
    assert last(app.sent, "confirm_close")["text"] == question
    assert not app.fake_worker.cancel.is_set()  # asking stops nothing


def test_closing_during_a_download_asks(app, extra):
    app.set_settings({"model": "Extra"})
    app.download()
    assert "Идёт скачивание модели" in app.close_question()


def test_worker_stop_ends_the_running_job_and_drops_waiting_ones():
    """Closing the window waits for the worker: a cancelled job still ends normally."""
    from gigaam_app.worker import Worker
    events = queue.Queue()
    worker = Worker(events)
    started, ran = threading.Event(), []

    def slow_job(*args):
        started.set()
        worker.cancel.wait(5)  # like the engine, it stops once cancel is set
        ran.append("first")
    worker._transcribe = slow_job
    worker.start()
    worker.jobs.put(("transcribe", "a"))
    started.wait(5)
    worker.jobs.put(("transcribe", "b"))
    worker.stop(timeout=5)
    assert not worker.is_alive() and ran == ["first"]
