"""The window's logic (gigaam_app/controller.py) with a fake worker: no model, no window."""

import copy
import json
from pathlib import Path
import queue
import threading
import time
from urllib.request import urlopen

import pytest

from gigaam_app import catalog, config, fix
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


def fake_sound_check(path):
    """Stands in for ffmpeg: files named *.txt or *.jpg have no sound, the rest have."""
    return Path(path).suffix.lower() not in (".txt", ".jpg")


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
    control = Controller(worker, queue.Queue(), send=sent.append, clock=clock, probe=lambda path: 61.0, sound_check=fake_sound_check,
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


def finish(control, item_path, segments, cancelled=False, formats=("txt", "timestamps"), model="RNNT",
           device="GPU (DirectML)"):
    """Play a whole transcription of the running file and write real outputs. The result holds
    copies of the lines, as it does when it comes from the model process (worker.WorkerProcess)."""
    for seg in segments:
        control.handle(("segment", seg))
    result = Transcript(source=str(item_path), model=model, device=device, audio_seconds=61.0,
                        segments=copy.deepcopy(list(segments)), cancelled=cancelled)
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
    assert [m["key"] for m in app.snapshot["options"]["models"]] == ["RNNT", "CTC", "Whisper"]
    assert app.fake_worker.take() == [("load", ("RNNT", "auto", 0))]


def test_nothing_is_sent_before_the_page_is_ready(tmp_path, monkeypatch, media):
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path)
    sent = []
    worker = FakeWorker()
    control = Controller(worker, queue.Queue(), send=sent.append, probe=lambda path: None, sound_check=fake_sound_check,
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


def test_files_without_sound_are_refused_with_one_notice(app, media, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("x", encoding="utf-8")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"x")
    assert app.add_files([str(notes), str(media[0]), str(photo)]) == 1
    assert [item.path.name for item in app.files] == ["a.mp3"]
    assert last(app.sent, "notice")["text"] == "Не добавлено, в файле нет звука: notes.txt, photo.jpg"


def test_the_notice_names_three_files_and_counts_the_rest():
    assert controller_module.refused_text(["1.txt", "2.txt", "3.txt", "4.txt", "5.txt"]) == \
        "Не добавлено, в файле нет звука: 1.txt, 2.txt, 3.txt и ещё 2"


def test_a_folder_without_media_gets_a_notice(app, tmp_path):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    assert app.add_files([str(folder)]) == 0
    assert last(app.sent, "notice")["text"] == "В папке нет аудио и видео: docs"


@pytest.mark.parametrize("header, expected", [
    (b"  Stream #0:0[0x1](und): Video: h264\n  Stream #0:1[0x2](rus): Audio: aac (LC)\n", True),
    (b"  Stream #0:0: Audio: mp3, 44100 Hz\n  Stream #0:1: Video: mjpeg (attached pic)\n", True),
    (b"  Stream #0:0: Video: mjpeg (Baseline), yuvj420p\n", False),   # a photo or a silent video
    (b"notes.txt: Invalid data found when processing input\n", False),  # not media at all
    (None, True),                                                    # ffmpeg missing: let the job say so
])
def test_has_sound_reads_the_streams(monkeypatch, header, expected):
    monkeypatch.setattr(controller_module, "ffmpeg_header", lambda path: header)
    assert controller_module.has_sound("x") is expected


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
    assert view["detail"] == "1:01 - отменено, RNNT" and view["model"] == "GigaAM v3 RNNT"
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
    assert view["detail"] == "1:01 - готово, RNNT"
    assert view["model"] == "GigaAM v3 RNNT"


def test_the_model_is_shown_while_running_and_after(app, media):
    """The page names the model that recognises a file, and keeps naming the one that made
    a finished file after the settings choose another."""
    app.add_files([str(media[0]), str(media[1])])
    first, second = app.files
    assert app._file_view(first)["model"] == "GigaAM v3 RNNT"
    assert app._file_view(second)["model"] == ""          # waiting: not decided yet
    finish(app, media[0], [segment(0.0, 3.0, "Текст.")])
    app.settings.model = "CTC"                             # a later choice does not rename it
    assert app._file_view(first)["model"] == "GigaAM v3 RNNT"
    # A Whisper result is named by its full title, and its list line by the short key.
    hello = segment(0.0, 2.0, "Hello.")
    app.handle(("segment", hello))
    app.handle(("finished", Transcript(source=str(media[1]), model="Whisper", device="CPU",
                                       audio_seconds=61.0, segments=[hello]), []))
    view = app._file_view(second)
    assert view["model"] == "Whisper large-v3-turbo (q5_0)" and view["detail"] == "1:01 - готово, Whisper"


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
    assert app.segments(item.id)[1] == {"index": 1, "start": 3.0, "end": 4.0, "text": "Вторая.",
                                         "words": [[3.0, 4.0, "Вторая.", None, None, None]]}
    assert app.copy_text(item.id, False) == "Первая.\nВторая.\n"
    assert app.copy_text(item.id, True).startswith("[00:01.000 - 00:02.500] Первая.\n")
    for_llm = app.copy_text(item.id, False, True)
    assert for_llm.startswith("Автоматическая расшифровка речи") and for_llm.endswith("Первая.\nВторая.\n")


def test_open_create_and_show_outputs(app, media):
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], [segment(0.0, 2.0, "Текст.")])
    view = app._file_view(item)
    assert [(o["format"], bool(o["path"])) for o in view["outputs"]] == [
        ("txt", True), ("timestamps", True), ("md", False), ("srt", False), ("json", False), ("llm", False)]
    assert app.open_output(item.id, "txt")
    assert app.desktop.opened == [media[0].with_name("a-transcript.txt").resolve()]
    assert app.create_output(item.id, "srt")
    srt = media[0].with_name("a-transcript.srt")
    assert srt.read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> ")
    assert app._file_view(item)["outputs"][3]["path"] == str(srt.resolve())
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
    assert last(app.sent, "settings") == {"model": "RNNT", "language": "auto", "device": "CPU", "cpu_threads": 4,
                                          "outputs": ["txt", "srt"], "include_timestamps": False, "terms": "",
                                          "doubt_marks": True, "doubt_style": "underline",
                                          "doubt_light": 0.97, "doubt_strong": 0.80, "player_volume": 1.0,
                                          "suggest": "gpu", "speakers": False}
    assert app.fake_worker.take() == [("load", ("RNNT", "cpu", 4))]
    app.add_files([str(media[0])])
    job = app.fake_worker.take()[0]
    assert job[2] == ("RNNT", "cpu", 4) and job[4] == ["txt", "srt"]
    # While a file runs, a change does not load at once; the next file loads it.
    app.set_settings({"model": "CTC"})
    assert app.fake_worker.take() == []


def test_doubt_marks_are_a_view_setting_without_a_reload(app):
    app.fake_worker.take()
    app.set_settings({"doubt_marks": False, "doubt_style": "colors"})
    assert app.fake_worker.take() == []
    view = last(app.sent, "settings")
    assert (view["doubt_marks"], view["doubt_style"]) == (False, "colors")
    assert (config.load(app.settings_path).doubt_marks, config.load(app.settings_path).doubt_style) == (False, "colors")
    with pytest.raises(ValueError):
        app.set_settings({"doubt_style": "bold"})
    app.set_settings({"doubt_light": 0.9, "doubt_strong": 0.6})
    assert (config.load(app.settings_path).doubt_light, config.load(app.settings_path).doubt_strong) == (0.9, 0.6)
    with pytest.raises(ValueError):
        app.set_settings({"doubt_strong": 0.95})  # the wavy threshold must stay below the dotted one
    assert app.settings.doubt_strong == 0.6
    app.reset_settings()
    view = last(app.sent, "settings")
    assert (view["doubt_marks"], view["doubt_style"], view["doubt_light"], view["doubt_strong"]) == \
        (True, "underline", 0.97, 0.80)


def test_language_goes_with_each_file_without_a_reload(app, media):
    app.fake_worker.take()
    app.set_settings({"language": "en"})
    assert app.fake_worker.take() == []  # Whisper takes the language per file
    assert config.load(app.settings_path).language == "en"
    app.add_files([str(media[0])])
    job = app.fake_worker.take()[0]
    assert job[0] == "transcribe" and job[5] == "en"
    with pytest.raises(ValueError):
        app.set_settings({"language": "klingon"})


def test_options_offer_whisper_with_its_language_choice(app):
    options = app.snapshot["options"]
    models = {model["key"]: model for model in options["models"]}
    assert models["Whisper"]["language"] and not models["RNNT"]["language"]
    assert "Скачивается отдельно, 547 МБ." in models["Whisper"]["note"]
    assert options["languages"][0] == {"key": "auto", "label": "Определять автоматически"}


def test_a_language_from_the_file_outside_the_list_is_still_offered(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path)
    config.save(config.Settings(model="Whisper", language="haw"), tmp_path / "settings.json")
    control = Controller(FakeWorker(), queue.Queue(), send=lambda message: None, clock=Clock(),
                         probe=lambda path: 1.0, sound_check=fake_sound_check, desktop=FakeDesktop(),
                         settings_path=tmp_path / "settings.json")
    snapshot = control.ready()
    assert snapshot["options"]["languages"][-1] == {"key": "haw", "label": "haw"}
    assert snapshot["settings"]["language"] == "haw"


def test_unknown_device_is_refused(app):
    with pytest.raises(ValueError):
        app.set_settings({"device": "TPU"})


def test_settings_are_saved_at_once_and_reset_keeps_the_speech_search(app, tmp_path):
    path = tmp_path / "settings.json"
    app.set_settings({"model": "CTC", "include_timestamps": True, "outputs": ["srt"]})
    saved = config.load(path)
    assert saved.model == "CTC" and saved.include_timestamps and saved.outputs == ["srt"]
    app.settings.vad.vad_threshold = 0.7  # only the file sets these
    assert app.reset_settings()
    saved = config.load(path)
    assert (saved.model, saved.include_timestamps, saved.outputs) == ("RNNT", False, ["txt", "timestamps"])
    assert saved.vad.vad_threshold == 0.7
    assert last(app.sent, "settings")["model"] == "RNNT"


def test_a_settings_file_that_cannot_be_written_shows_an_error(app, tmp_path):
    app.settings_path = tmp_path / "missing-folder" / "settings.json"
    app.set_settings({"cpu_threads": 4})
    assert app.settings.cpu_threads == 4  # still applied
    assert last(app.sent, "error")["text"].startswith("Не удалось сохранить настройки")


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


def test_has_sound_with_the_real_ffmpeg(tmp_path):
    from gigaam_app.paths import ffmpeg_executable
    import subprocess
    try:
        ffmpeg = ffmpeg_executable()
    except RuntimeError:
        pytest.skip("no ffmpeg")
    notes = tmp_path / "notes.txt"
    notes.write_text("просто текст", encoding="utf-8")
    sound = tmp_path / "tone.oddext"     # an extension the app does not know: the streams decide
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=d=1", "-f", "wav", str(sound)], check=True)
    assert controller_module.has_sound(notes) is False
    assert controller_module.has_sound(sound) is True


# ---------------------------------------------------------------------- fixing a selected part (plan 03 A3-A4)

def line_of(*items):
    """A segment from (text, start, end) word triples."""
    words = [Word(text=text, start=start, end=end) for text, start, end in items]
    return Segment(start=words[0].start, end=words[-1].end, text=" ".join(w.text for w in words), words=words)


@pytest.fixture
def finished(app, media):
    """A finished file with two lines; the hard words are "Tullz Colling"."""
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], [line_of(("наш", 1.0, 1.3), ("любимый", 1.4, 1.9), ("механизм", 2.0, 2.6),
                                   ("Tullz", 2.7, 3.0), ("Colling,", 3.0, 3.5), ("и", 3.6, 3.7)),
                           line_of(("вся", 5.0, 5.3), ("мозаика.", 5.4, 6.0))])
    app.fake_worker.take()
    return item


def test_reread_sends_the_piece_with_context(app, finished, monkeypatch):
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "CTC", "Whisper"))
    answer = app.reread(finished.id, [0, 3], [0, 4], "  Tools   Calling, LLM ")
    assert answer["current"] == "Tullz Colling,"
    assert [model["key"] for model in answer["models"]] == ["RNNT", "CTC", "Whisper"]
    assert not answer["whisper_missing"] and not answer["waiting"]
    [job] = app.fake_worker.take()
    kind, request, path, windows, models, device, threads, language, terms = job
    assert (kind, request, path, models, terms) == ("reread", answer["request"], finished.path,
                                                     ["RNNT", "CTC", "Whisper"], "Tools Calling, LLM")
    # Context: the words within 1.5 s on each side ("любимый" .. "и"), cut in the gaps outside them.
    (left_lo, left_hi), (right_lo, right_hi) = windows
    assert left_hi == pytest.approx(1.4) and right_lo == pytest.approx(3.7)
    # The terms are kept for the next time.
    assert app.settings.terms == "Tools Calling, LLM"
    assert last(app.sent, "settings")["terms"] == "Tools Calling, LLM"


def test_readings_keep_only_the_selected_words(app, finished):
    answer = app.reread(finished.id, [0, 3], [0, 4])
    request = answer["request"]
    heard = [Word(text=t, start=s, end=e) for t, s, e in (("любимый", 1.4, 1.9), ("механизм", 2.0, 2.6),
                                                          ("Tools", 2.7, 3.0), ("Calling,", 3.0, 3.5), ("и", 3.6, 3.7))]
    app.handle(("reread_range", request, 1.35, 3.75))
    app.handle(("reread_loading", request, "CTC"))
    app.handle(("reread_result", request, "RNNT", heard, None))
    app.handle(("reread_result", request, "CTC", None, "broken"))
    app.handle(("reread_result", request + 1, "RNNT", heard, None))  # an old or other request: ignored
    app.handle(("reread_done", request))
    readings = [m["data"] for m in app.sent if m["kind"] == "reading"]
    assert [r["phase"] for r in readings] == ["range", "loading", "result", "result", "done"]
    assert readings[2] == {"request": request, "phase": "result", "model": "RNNT", "text": "Tools Calling,", "same": False}
    assert readings[3]["error"] == "broken"


def test_take_a_reading_keeps_its_times_and_writes_the_files(app, finished):
    answer = app.reread(finished.id, [0, 3], [0, 4])
    heard = [Word(text="Tools", start=2.72, end=3.0, confidence=0.9), Word(text="Calling,", start=3.02, end=3.5)]
    app.handle(("reread_result", answer["request"], "RNNT", heard, None))
    assert app.apply_fix(finished.id, [0, 3], [0, 4], "Tools Calling,", "RNNT")
    line = finished.segments[0]
    assert line.text == "наш любимый механизм Tools Calling, и"
    # A reading taken as it is keeps its times and its confidence (plan 03 B2).
    assert [(w.text, w.start, w.confidence) for w in line.words[3:5]] == [("Tools", 2.72, 0.9), ("Calling,", 3.02, None)]
    assert app.segments(finished.id)[0]["words"][3][3] == 0.9
    assert finished.result.segments[0] is line
    assert "Tools Calling, и" in finished.written["txt"].read_text(encoding="utf-8")
    assert "lines_changed" in kinds(app.sent)
    assert app.rereading is None


def test_text_typed_by_hand_gets_times_spread_over_the_part(app, finished):
    assert app.apply_fix(finished.id, [0, 5], [1, 0], "и весь", None)
    first, second = finished.segments
    assert first.text == "наш любимый механизм Tullz Colling, и весь"
    assert second.text == "мозаика."
    starts = [w.start for w in first.words[5:]]
    assert starts == sorted(starts) and 3.5 <= starts[0] < 3.7
    assert all(w.confidence is None for w in first.words[5:])  # typed by hand: no confidence


def test_fixing_is_refused_while_running_and_for_long_parts(app, media, finished):
    with pytest.raises(ValueError):
        app.apply_fix(finished.id, [0, 2], [0, 1], "x")  # ends before it starts
    with pytest.raises(ValueError):
        app.apply_fix(finished.id, [0, 1], [0, 1], "   ")
    long_line = line_of(*[(f"w{i}", i * 1.0, i * 1.0 + 0.5) for i in range(40)])
    finished.segments.append(long_line)
    with pytest.raises(ValueError, match="25"):
        app.reread(finished.id, [2, 0], [2, 39])
    app.add_files([str(media[1])])
    running = app.files[1]
    assert running.state == "running"
    with pytest.raises(ValueError):
        app.reread(running.id, [0, 0], [0, 0])


# ---------------------------------------------------------------------- audio player (plan 05)


class FakeCopy:
    """Stands in for the ffmpeg process that makes a playable copy."""

    def __init__(self, target, works):
        self.target, self.works, self.killed = target, works, False
        self.returncode = None

    def communicate(self):
        if self.works:
            Path(self.target).write_bytes(b"ogg")
        self.returncode = 0 if self.works else 1
        return b"", b"" if self.works else b"Unknown encoder 'libopus'"

    def kill(self):
        self.killed = True

    def wait(self):
        return self.returncode


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    return condition()


def test_audio_serves_a_playable_file_as_it_is(app, media):
    app.add_files([str(media[0])])
    answer = app.audio(app.files[0].id)
    assert answer["preparing"] is False and answer["url"].endswith("/a.mp3")
    with urlopen(answer["url"], timeout=5) as reply:
        assert reply.read() == b"fake"
    assert app.audio("nope") is None
    app.close()
    assert not app.audio_server.running  # closing the window stops the server


def test_other_formats_get_a_copy_made_once_and_deleted_at_close(app, tmp_path, monkeypatch):
    source = tmp_path / "call.wma"
    source.write_bytes(b"fake")
    started = []

    def start(path, target, codec="libopus"):
        started.append(codec)
        return FakeCopy(target, works=codec == "libmp3lame")  # this ffmpeg "has no Opus"

    monkeypatch.setattr(controller_module.audio_module, "start_playable_copy", start)
    app.add_files([str(source)])
    item = app.files[0]
    assert app.audio(item.id) == {"id": item.id, "url": None, "preparing": True}
    assert wait_for(lambda: "audio_ready" in kinds(app.sent))
    ready = last(app.sent, "audio_ready")
    assert ready["id"] == item.id and ready["url"].endswith(".mp3") and started == ["libopus", "libmp3lame"]
    again = app.audio(item.id)
    assert again["url"] == ready["url"] and len(started) == 2  # made once
    folder = app.audio_dir
    assert any(folder.iterdir())
    app.close()
    assert not folder.exists()


def test_convert_asks_for_a_copy_even_of_a_playable_format(app, media, monkeypatch):
    monkeypatch.setattr(controller_module.audio_module, "start_playable_copy",
                        lambda path, target, codec="libopus": FakeCopy(target, works=False))
    app.add_files([str(media[2])])
    assert app.audio(app.files[0].id, convert=True)["preparing"] is True
    assert wait_for(lambda: "audio_ready" in kinds(app.sent))
    assert last(app.sent, "audio_ready")["url"] is None  # both codecs failed
    assert wait_for(lambda: any("звук" in str(m["data"]) for m in app.sent if m["kind"] in ("notice", "error")))
    app.close()


# ---------------------------------------------------------------------- suggested fixes (plan 06)

def doubtful_line(*items):
    """A segment from (text, start, end, confidence) words."""
    words = [Word(text=text, start=start, end=end, confidence=conf) for text, start, end, conf in items]
    return Segment(start=words[0].start, end=words[-1].end, text=" ".join(w.text for w in words), words=words)


def doubtful_lines():
    # "Tullz" and "мозаика." are doubtful (below 0.97): two groups.
    return [doubtful_line(("наш", 1.0, 1.3, 0.99), ("любимый", 1.4, 1.9, 0.99), ("механизм", 2.0, 2.6, 0.99),
                          ("Tullz", 2.7, 3.0, 0.5), ("Colling,", 3.0, 3.5, 0.99), ("и", 3.6, 3.7, 0.99)),
            doubtful_line(("вся", 5.0, 5.3, 0.99), ("мозаика.", 5.4, 6.0, 0.9))]


def heard_words(*texts_and_times):
    return [Word(text=text, start=start, end=end) for text, start, end in texts_and_times]


TOOLS_READING = heard_words(("любимый", 1.4, 1.9), ("механизм", 2.0, 2.6), ("Tools", 2.72, 3.0),
                            ("Calling,", 3.02, 3.5), ("и", 3.6, 3.7))


@pytest.fixture
def searching(app, media, monkeypatch):
    """A finished RNNT file with doubtful words; Whisper counts as downloaded."""
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "CTC", "Whisper"))
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], doubtful_lines())
    return item


def suggest_jobs(app):
    return [job for job in app.fake_worker.take() if job[0] == "suggest"]


def test_doubtful_words_are_read_again_by_whisper(app, searching):
    [job] = suggest_jobs(app)
    kind, request, path, windows, models, device, threads, language, terms = job
    assert (path, models) == (searching.path, ["Whisper"])  # not CTC (plan 06 A5), not RNNT (made the text)
    # The whole first line is read: the cuts lie before "наш" and after "и".
    (left_lo, left_hi), (right_lo, right_hi) = windows
    assert left_hi <= 1.0 and right_lo >= 3.7
    assert app._file_view(searching)["suggest"]["text"] == "Ищу варианты для сомнительных слов: 0 из 2"
    app.handle(("suggest_loading", request, "Whisper"))
    assert "загрузка Whisper" in app._file_view(searching)["suggest"]["text"]
    app.handle(("suggest_result", request, "Whisper", [Word(text="наш", start=1.0, end=1.3)] + TOOLS_READING, None))
    word = searching.segments[0].words[3]
    assert word.suggestions == [{"models": ["Whisper"], "count": 2,
                                 "words": [[2.7, 3.008, "Tools", None], [3.008, 3.5, "Calling,", None]]}]
    line_message = last(app.sent, "line")
    assert line_message["index"] == 0 and line_message["words"][3][4] == word.suggestions
    app.handle(("suggest_done", request))
    assert app._file_view(searching)["suggest"]["text"] == "Ищу варианты для сомнительных слов: 1 из 2"
    [second] = suggest_jobs(app)  # the next line: "мозаика."
    app.handle(("suggest_result", second[1], "Whisper", heard_words(("вся", 5.0, 5.3), ("мозаика", 5.4, 6.0)), None))
    app.handle(("suggest_done", second[1]))
    assert suggest_jobs(app) == [] and app.suggesting is None
    assert searching.result.suggestions_searched
    view = app._file_view(searching)["suggest"]
    assert view == {"text": "Другие модели предлагают варианты: 1 место", "can_find": True, "busy": False,
                    "searched": True}


def test_take_an_offer_in_the_replaced_words_times_and_write_the_files(app, searching):
    [job] = suggest_jobs(app)
    reading = [Word(text=w.text, start=w.start, end=w.end, confidence=0.8) for w in TOOLS_READING]
    app.handle(("suggest_result", job[1], "Whisper", reading, None))
    assert app.take_suggestion(searching.id, [0, 3], 0)
    line = searching.segments[0]
    assert line.text == "наш любимый механизм Tools Calling, и"
    # The span of "Tullz Colling," (2.7-3.5 s, GigaAM's times), not Whisper's; chosen, so not doubtful.
    assert [(w.text, w.start, w.end, w.confidence, w.suggestions) for w in line.words[3:5]] == [
        ("Tools", 2.7, 3.008, None, None), ("Calling,", 3.008, 3.5, None, None)]
    assert "Tools Calling, и" in searching.written["txt"].read_text(encoding="utf-8")
    assert "lines_changed" in kinds(app.sent)
    with pytest.raises(ValueError):
        app.take_suggestion(searching.id, [0, 3], 0)  # taken: no offer left there


def test_leave_an_offer(app, searching):
    [job] = suggest_jobs(app)
    app.handle(("suggest_result", job[1], "Whisper", TOOLS_READING, None))
    assert app.leave_suggestion(searching.id, [0, 3], 0)
    assert searching.segments[0].words[3].suggestions is None
    assert searching.segments[0].text.startswith("наш любимый механизм Tullz")
    assert last(app.sent, "line")["words"][3][4] is None
    assert not app.leave_suggestion(searching.id, [0, 3], 0)


def test_a_new_file_goes_before_the_next_group(app, media, searching):
    [job] = suggest_jobs(app)
    app.add_files([str(media[1])])
    assert [j[0] for j in app.fake_worker.take()] == ["transcribe"]
    app.handle(("suggest_done", job[1]))  # the group on the worker ends; the file runs first
    assert suggest_jobs(app) == []
    finish(app, media[1], [doubtful_line(("да", 1.0, 1.2, 0.5))])
    second = suggest_jobs(app)
    assert len(second) == 1 and second[0][2] == searching.path  # the first file's search goes on
    assert app._file_view(app.files[1])["suggest"]["text"].endswith("в очереди")


def test_offers_reach_the_result_and_the_file_for_an_ai(app, media, monkeypatch):
    """The result from the model process is a copy of the lines shown: offers found later must
    still reach it (the history and the files are written from it), and the llm file is
    written again with both versions once the search ends, and again when an offer is left."""
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "CTC", "Whisper"))
    app.set_settings({"outputs": ["txt", "llm"]})
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], doubtful_lines(), formats=("txt", "llm"))
    assert item.segments is item.result.segments
    [job] = suggest_jobs(app)
    app.handle(("suggest_result", job[1], "Whisper", TOOLS_READING, None))
    assert item.result.segments[0].words[3].suggestions  # in the result, so in the history
    app.handle(("suggest_done", job[1]))
    [second] = suggest_jobs(app)
    app.handle(("suggest_done", second[1]))
    llm_file = item.written["llm"]
    text = llm_file.read_text(encoding="utf-8")
    assert "{GigaAM v3 RNNT: Tullz[?50%] Colling, | Whisper" in text and ": Tools Calling,}" in text
    assert "Мест с разными версиями: 1." in text
    assert "{" not in item.written["txt"].read_text(encoding="utf-8")  # plain text has no versions
    assert "{GigaAM v3 RNNT: Tullz" in app.copy_text(item.id, False, True)
    assert app.leave_suggestion(item.id, [0, 3], 0)
    assert "Tullz[?50%] Colling, и" in llm_file.read_text(encoding="utf-8")
    assert "{" not in llm_file.read_text(encoding="utf-8")


def test_an_edit_during_the_search_drops_the_offer_for_changed_words(app, searching):
    [job] = suggest_jobs(app)
    app.apply_fix(searching.id, [0, 3], [0, 4], "Tools Calling,", None)
    app.handle(("suggest_result", job[1], "Whisper", TOOLS_READING, None))
    assert all(w.suggestions is None for w in searching.segments[0].words)


def test_recognising_again_ends_the_search(app, searching):
    [job] = suggest_jobs(app)
    assert app.retry(searching.id)
    app.fake_worker.take()
    app.handle(("suggest_done", job[1]))
    assert app.suggesting is None
    fresh = app.files[0]
    finish(app, fresh.path, doubtful_lines())  # the new text is searched again
    [again] = suggest_jobs(app)
    assert app.suggesting["transcript"] is fresh.result


def test_search_off_in_settings_and_the_button(app, media, monkeypatch):
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "CTC", "Whisper"))
    app.set_settings({"suggest": "off"})
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], doubtful_lines())
    assert suggest_jobs(app) == []
    assert app._file_view(item)["suggest"] == {"text": "", "can_find": True, "busy": False, "searched": False}
    with pytest.raises(ValueError):
        app.set_settings({"suggest": "sometimes"})
    assert app.find_suggestions(item.id)
    [job] = suggest_jobs(app)
    assert job[4] == ["Whisper"]


def test_on_the_cpu_only_the_button_searches_unless_always(app, media, monkeypatch):
    """Whisper on the CPU is slower than the recording (699 s for the 455 s lecture)."""
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "Whisper"))
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], doubtful_lines(), device="CPU")
    assert suggest_jobs(app) == []
    view = app._file_view(item)["suggest"]
    assert view["can_find"] and view["text"].startswith("На процессоре варианты ищутся долго")
    assert app.find_suggestions(item.id)
    assert len(suggest_jobs(app)) == 1
    # "always" searches by itself on the CPU too.
    app.set_settings({"suggest": "always"})
    app.add_files([str(media[1])])
    finish(app, media[1], doubtful_lines(), device="CPU")
    assert app._suggest_by_itself(app.files[1])
    assert app.files[1].id in app.suggest_queue or app.suggesting["id"] == app.files[1].id


def test_without_whisper_there_is_no_search_and_a_hint(app, media, monkeypatch):
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "CTC"))
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], doubtful_lines())
    assert suggest_jobs(app) == [] and app.suggesting is None
    view = app._file_view(item)["suggest"]
    assert view["can_find"] is False and "Whisper" in view["text"] and "Настройках" in view["text"]
    with pytest.raises(ValueError):
        app.find_suggestions(item.id)


def test_whisper_text_is_checked_by_rnnt(app, media, monkeypatch):
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "CTC", "Whisper"))
    app.add_files([str(media[0])])
    finish(app, media[0], doubtful_lines(), model="Whisper")
    [job] = suggest_jobs(app)
    assert job[4] == ["RNNT"]


def test_groups_of_one_line_are_read_once(app, media, monkeypatch):
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "Whisper"))
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], [doubtful_line(("Tullz", 1.0, 1.4, 0.5), ("Colling", 1.4, 1.9, 0.99), ("и", 2.0, 2.1, 0.99),
                                         ("это", 2.2, 2.4, 0.99), ("DepS,", 2.5, 3.0, 0.4), ("ok", 3.1, 3.3, 0.99))])
    [job] = suggest_jobs(app)
    app.handle(("suggest_result", job[1], "Whisper",
                heard_words(("Tools", 1.0, 1.4), ("Calling", 1.4, 1.9), ("и", 2.0, 2.1), ("это", 2.2, 2.4),
                            ("DeepSeek.", 2.5, 3.0), ("ok", 3.1, 3.3)), None))
    words = item.segments[0].words
    assert [w.text for w in fix.suggestion_words(words[0].suggestions[0])] == ["Tools", "Calling"]
    assert [w.text for w in fix.suggestion_words(words[4].suggestions[0])] == ["DeepSeek,"]  # the text's comma
    app.handle(("suggest_done", job[1]))
    assert suggest_jobs(app) == [] and item.result.suggestions_searched
    assert app._file_view(item)["suggest"]["text"] == "Другие модели предлагают варианты: 2 места"


def test_a_line_longer_than_whisper_hears_is_read_by_groups(app, media, monkeypatch):
    monkeypatch.setattr(app, "_model_installed", lambda key: key in ("RNNT", "Whisper"))
    app.add_files([str(media[0])])
    item = app.files[0]
    long_line = [(f"w{i}", i * 2.0, i * 2.0 + 1.0, 0.5 if i in (1, 12) else 0.99) for i in range(16)]
    finish(app, media[0], [doubtful_line(*long_line)])  # 31 s, two groups far apart
    [job] = suggest_jobs(app)
    (left_lo, left_hi), (right_lo, right_hi) = job[3]
    assert right_hi - left_lo < 20  # the first group with its own context, not the line
    app.handle(("suggest_done", job[1]))
    [second] = suggest_jobs(app)
    assert second[3][0][0] > 15


def test_a_failed_search_says_so_and_ends(app, searching):
    [job] = suggest_jobs(app)
    app.handle(("suggest_failed", job[1], "no such file"))
    app.handle(("suggest_done", job[1]))
    assert app.suggesting is None and not searching.result.suggestions_searched
    assert "no such file" in last(app.sent, "notice")["text"]
    assert suggest_jobs(app) == []


# ---------------------------------------------------------------------- speaker labels (plan 07)

def two_voices():
    """Two lines; the second speaker says the last word of the first line."""
    return [doubtful_line(("Привет,", 0.0, 0.5, 0.99), ("как", 0.6, 0.8, 0.99), ("дела?", 0.9, 1.2, 0.99),
                          ("Хорошо.", 1.6, 2.0, 0.99)),
            doubtful_line(("А", 3.0, 3.1, 0.99), ("у", 3.2, 3.3, 0.99), ("тебя?", 3.4, 3.8, 0.99))]


TURNS = [(0.0, 1.3, 5), (1.5, 2.1, 2), (2.9, 4.0, 5)]  # raw speaker numbers of the diarization


def speaker_jobs(app):
    return [job for job in app.fake_worker.take() if job[0] in ("diarize", "download")]


@pytest.fixture
def spoken(app, media, monkeypatch, tmp_path):
    """A finished file; the speaker models count as downloaded."""
    app.set_settings({"outputs": ["txt", "json"]})
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path)
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], two_voices(), formats=("txt", "json"))
    app.fake_worker.take()
    return item


def test_speakers_are_off_by_default(spoken, app):
    assert app.settings.speakers is False
    assert app.speaker_queue == [] and app.diarizing is None
    view = app._file_view(spoken)["speakers"]
    assert view == {"names": [], "list": [], "found": None, "text": "", "can_find": True, "busy": False,
                    "can_cancel": False, "error": False}


def test_the_setting_downloads_the_models_then_finds_the_speakers(app, media, monkeypatch, tmp_path):
    app.set_settings({"speakers": True, "outputs": ["txt", "json"]})
    assert config.load(tmp_path / "settings.json").speakers is True
    app.add_files([str(media[0])])
    item = app.files[0]
    app.fake_worker.take()
    finish(app, media[0], two_voices(), formats=("txt", "json"))
    [job] = speaker_jobs(app)
    assert job == ("download", catalog.SPEAKER_MODEL)
    assert app._file_view(item)["speakers"]["text"].startswith("Скачиваю модели для определения говорящих: 0 из 3")
    app.handle(("download_progress", "Speakers", 16 * 1024 ** 2, 32 * 1024 ** 2))
    assert "16 из 32 МБ" in app._file_view(item)["speakers"]["text"]
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path)
    app.handle(("download_done", "Speakers", tmp_path))
    [job] = speaker_jobs(app)
    assert job[0] == "diarize" and job[2] == item.path and job[3:] == ("auto", 0, None)
    request = job[1]
    app.handle(("diarize_loading", request))
    assert app._file_view(item)["speakers"]["text"] == "Определяю говорящих: загрузка моделей..."
    app.handle(("diarize_progress", request, 1, 4))
    view = app._file_view(item)["speakers"]
    assert view["text"] == "Определяю говорящих: 25%" and view["busy"] and view["can_cancel"]
    app.handle(("diarize_result", request, TURNS, None))
    assert app.diarizing is None
    assert [w.speaker for s in item.segments for w in s.words] == [0, 0, 0, 1, 0, 0, 0]
    assert item.result.speakers == ["Говорящий 1", "Говорящий 2"]
    assert app._file_view(item)["speakers"]["text"] == "Найдено: 2 говорящих"
    assert app.segments(item.id)[0]["words"][3][5] == 1
    assert {"id": item.id} in [m["data"] for m in app.sent if m["kind"] == "lines_changed"]
    saved = json.loads(item.written["json"].read_text(encoding="utf-8"))
    assert saved["speakers"] == ["Говорящий 1", "Говорящий 2"]


def test_the_button_with_a_known_count_holds_the_next_file(spoken, app, media):
    assert app.find_speakers(spoken.id, 3)
    [job] = speaker_jobs(app)
    assert job[0] == "diarize" and job[5] == 3
    with pytest.raises(ValueError):
        app.find_speakers(spoken.id)  # already running
    app.add_files([str(media[1])])
    waiting = app.files[1]
    assert waiting.state == "waiting" and app.fake_worker.take() == []
    assert "определение говорящих" in app._file_view(waiting)["status"]
    app.handle(("diarize_result", job[1], TURNS, None))
    [transcribe] = app.fake_worker.take()
    assert transcribe[0] == "transcribe" and transcribe[1] == waiting.path


def test_a_wrong_count_is_refused(spoken, app):
    with pytest.raises(ValueError):
        app.find_speakers(spoken.id, controller_module.MAX_SPEAKERS + 1)


def test_rename_reaches_every_file_without_redrawing_the_text(spoken, app):
    app.find_speakers(spoken.id)
    [job] = speaker_jobs(app)
    app.handle(("diarize_result", job[1], TURNS, None))
    app.sent.clear()
    assert app.rename_speaker(spoken.id, 1, "  Мария   Ивановна ")
    assert spoken.result.speakers == ["Говорящий 1", "Мария Ивановна"]
    assert "lines_changed" not in kinds(app.sent)
    assert last(app.sent, "file")["speakers"]["names"] == ["Говорящий 1", "Мария Ивановна"]
    assert json.loads(spoken.written["json"].read_text(encoding="utf-8"))["speakers"][1] == "Мария Ивановна"
    app.rename_speaker(spoken.id, 1, "")  # an empty name gives the number back
    assert spoken.result.speakers[1] == "Говорящий 2"
    with pytest.raises(ValueError):
        app.rename_speaker(spoken.id, 5, "Кто-то")


def test_a_search_again_keeps_the_names(spoken, app):
    app.find_speakers(spoken.id)
    app.handle(("diarize_result", speaker_jobs(app)[0][1], TURNS, None))
    app.rename_speaker(spoken.id, 0, "Анна")
    app.find_speakers(spoken.id, 2)
    app.handle(("diarize_result", speaker_jobs(app)[0][1], TURNS, None))
    assert spoken.result.speakers == ["Анна", "Говорящий 2"]


def test_a_fixed_word_takes_the_speaker_of_the_word_it_replaces(spoken, app):
    app.find_speakers(spoken.id)
    app.handle(("diarize_result", speaker_jobs(app)[0][1], TURNS, None))
    app.apply_fix(spoken.id, [0, 3], [0, 3], "Отлично, спасибо.")
    assert [(w.text, w.speaker) for w in spoken.segments[0].words[3:]] == [("Отлично,", 1), ("спасибо.", 1)]


def found_speakers(app, item, count=None, found=None):
    """A speaker search of item with TURNS as its result (speakers [0, 0, 0, 1, 0, 0, 0])."""
    app.find_speakers(item.id, count)
    request = speaker_jobs(app)[0][1]
    if found is not None:
        app.handle(("diarize_found", request, found))
    app.handle(("diarize_result", request, TURNS, None))


def speakers_of(item):
    return [word.speaker for segment in item.segments for word in segment.words]


def test_the_view_lists_the_speakers_with_their_share_of_the_speech(spoken, app):
    found_speakers(app, spoken)
    view = app._file_view(spoken)["speakers"]
    # Words: 0.5 + 0.2 + 0.3 + 0.1 + 0.1 + 0.4 = 1.6 s of speaker 1, 0.4 s of speaker 2.
    assert view["list"] == [{"index": 0, "name": "Говорящий 1", "share": 80},
                            {"index": 1, "name": "Говорящий 2", "share": 20}]
    assert view["found"] == 2 and view["error"] is False


def test_words_go_to_another_speaker_or_a_new_one(spoken, app):
    found_speakers(app, spoken)
    app.sent.clear()
    assert app.set_words_speaker(spoken.id, [0, 0], [0, 1], 1)
    assert speakers_of(spoken) == [1, 1, 0, 1, 0, 0, 0]
    assert "lines_changed" in kinds(app.sent)
    assert app.set_words_speaker(spoken.id, [1, 0], [1, 2], None)   # a new speaker
    assert speakers_of(spoken) == [1, 1, 0, 1, 2, 2, 2]
    assert spoken.result.speakers == ["Говорящий 1", "Говорящий 2", "Говорящий 3"]
    saved = json.loads(spoken.written["json"].read_text(encoding="utf-8"))
    assert [w["speaker"] for w in saved["segments"][1]["words"]] == [2, 2, 2]
    assert "Говорящий 3: А у тебя?" in spoken.written["txt"].read_text(encoding="utf-8")
    # Speaker 3's words go back: the next new speaker takes the free number again.
    app.set_words_speaker(spoken.id, [1, 0], [1, 2], 0)
    app.set_words_speaker(spoken.id, [1, 2], [1, 2], None)
    assert speakers_of(spoken)[-1] == 2 and len(spoken.result.speakers) == 3
    with pytest.raises(ValueError):
        app.set_words_speaker(spoken.id, [0, 0], [0, 0], 7)
    with pytest.raises(ValueError):
        app.set_words_speaker(spoken.id, [0, 2], [0, 1], 0)   # ends before it starts


def test_words_need_speakers_first(spoken, app):
    with pytest.raises(ValueError):
        app.set_words_speaker(spoken.id, [0, 0], [0, 1], None)


def test_merge_gives_every_word_of_one_speaker_to_another(spoken, app):
    found_speakers(app, spoken)
    app.rename_speaker(spoken.id, 0, "Анна")
    assert app.merge_speakers(spoken.id, 1, 0)
    assert speakers_of(spoken) == [0] * 7
    view = app._file_view(spoken)["speakers"]
    assert view["list"] == [{"index": 0, "name": "Анна", "share": 100}]
    assert view["text"] == "Найдено: 1 говорящий"
    assert "Говорящий 2" not in spoken.written["txt"].read_text(encoding="utf-8")
    for source, target in ((1, 0), (0, 0), (0, 5)):   # nothing left to move, the same one, unknown
        with pytest.raises(ValueError):
            app.merge_speakers(spoken.id, source, target)


def test_the_models_own_count_is_kept_as_a_hint(spoken, app):
    found_speakers(app, spoken, count=2, found=3)
    assert spoken.result.speakers_found == 3
    assert app._file_view(spoken)["speakers"]["found"] == 3
    assert "speakers_found" not in json.loads(spoken.written["json"].read_text(encoding="utf-8"))
    found_speakers(app, spoken, found=5)   # automatic: the speakers it did find
    assert spoken.result.speakers_found == 2


def test_copy_leaves_the_names_out_when_they_are_hidden(spoken, app):
    found_speakers(app, spoken)
    assert app.copy_text(spoken.id, False).startswith("Говорящий 1: ")
    assert "Говорящий" not in app.copy_text(spoken.id, False, False, False)
    assert "Говорящий" not in app.copy_text(spoken.id, True, False, False)


def test_cancel_a_search_or_take_it_out_of_the_line(spoken, app, media):
    app.find_speakers(spoken.id)
    [job] = speaker_jobs(app)
    assert app.cancel_speakers(spoken.id) and app.fake_worker.cancel.is_set()
    assert app._file_view(spoken)["speakers"]["text"] == "Определение говорящих: отмена..."
    app.handle(("diarize_result", job[1], None, None))
    view = app._file_view(spoken)["speakers"]
    assert spoken.result.speakers is None and view["can_find"] and view["text"] == ""
    # Waiting behind a file: taken out of the line.
    app.add_files([str(media[1])])
    app.fake_worker.take()
    app.find_speakers(spoken.id)
    assert app._file_view(spoken)["speakers"]["text"] == "Определение говорящих: в очереди"
    assert app.cancel_speakers(spoken.id) and app.speaker_queue == []


def test_a_failed_search_says_why(spoken, app):
    app.find_speakers(spoken.id)
    [job] = speaker_jobs(app)
    app.handle(("diarize_result", job[1], None, "out of memory"))
    assert app._file_view(spoken)["speakers"]["text"] == "Не удалось определить говорящих: out of memory"
    assert "out of memory" in last(app.sent, "notice")["text"]
    app.find_speakers(spoken.id)  # a new try clears the error
    assert app._file_view(spoken)["speakers"]["text"] == "Определяю говорящих..."


def test_a_failed_download_says_why(app, media):
    app.add_files([str(media[0])])
    item = app.files[0]
    finish(app, media[0], two_voices())
    app.fake_worker.take()
    app.find_speakers(item.id)
    assert speaker_jobs(app) == [("download", catalog.SPEAKER_MODEL)]
    app.handle(("error", "no network"))
    assert app.speaker_download is None and app.speaker_queue == []
    assert "no network" in app._file_view(item)["speakers"]["text"]
    assert "no network" in last(app.sent, "error")["text"]


def test_speakers_found_for_an_older_result_are_ignored(spoken, app):
    app.find_speakers(spoken.id)
    [job] = speaker_jobs(app)
    app.retry(spoken.id)
    app.handle(("diarize_result", job[1], TURNS, None))
    assert app.files[0].result is None and app.diarizing is None
    assert app.fake_worker.take()[0][0] == "transcribe"


def test_closing_during_a_search_asks_first(spoken, app):
    app.find_speakers(spoken.id)
    assert "определение говорящих" in app.close_question()
