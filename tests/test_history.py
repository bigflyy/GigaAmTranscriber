"""The list of transcribed files kept between sessions (gigaam_app/history.py and the controller)."""

import json
from pathlib import Path
import queue
import sys

import pytest

from gigaam_app import catalog
from gigaam_app.controller import Controller
from gigaam_app.engine import Segment, Transcript, Word
from gigaam_app.history import Entry, History

sys.path.insert(0, str(Path(__file__).parent))  # the shared fakes live in test_controller.py
from test_controller import FakeDesktop, FakeWorker, finish, segment  # noqa: E402


def transcript(source, cancelled=False):
    return Transcript(source=str(source), model="RNNT", device="CPU", audio_seconds=61.0, speech_seconds=40.0,
                      segments=[Segment(1.0, 2.5, "Привет.", [Word(1.0, 2.5, "Привет.", 0.75)])], cancelled=cancelled)


def test_entries_round_trip_and_keep_their_order(tmp_path):
    history = History(tmp_path / "history")
    assert history.load() == []
    first = Entry("a", tmp_path / "one.mp3", "done", transcript(tmp_path / "one.mp3"),
                  {"txt": tmp_path / "one-transcript.txt"}, 61.0, 3.0, 40.0, saved_at=10.0)
    second = Entry("b", tmp_path / "two.mp3", "cancelled", transcript(tmp_path / "two.mp3", True), saved_at=5.0)
    history.save(first)
    history.save(second)
    loaded = history.load()
    assert [entry.key for entry in loaded] == ["b", "a"]
    assert loaded[1] == first
    assert loaded[1].transcript.segments[0].words[0] == Word(1.0, 2.5, "Привет.", 0.75)
    history.delete("b")
    assert [entry.key for entry in history.load()] == ["a"]


def test_damaged_entries_are_skipped(tmp_path):
    history = History(tmp_path)
    history.save(Entry("good", tmp_path / "a.mp3", "done", transcript(tmp_path / "a.mp3")))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "future.json").write_text(json.dumps({"version": 99}), encoding="utf-8")
    assert [entry.key for entry in history.load()] == ["good"]


def make_controller(tmp_path, monkeypatch, history):
    monkeypatch.setattr(catalog, "installed_folder", lambda info: tmp_path if info.bundled else None)
    sent = []
    control = Controller(FakeWorker(), queue.Queue(), send=sent.append, probe=lambda path: 61.0, sound_check=lambda path: True,
                         desktop=FakeDesktop(), settings_path=tmp_path / "settings.json", history=history)
    control.sent = sent
    control.ready()
    control.worker.take()
    return control


@pytest.fixture
def media(tmp_path):
    files = []
    for name in ("a.mp3", "b.wav"):
        path = tmp_path / name
        path.write_bytes(b"fake")
        files.append(path)
    return files


def test_finished_files_come_back_in_the_next_session(tmp_path, monkeypatch, media):
    history = History(tmp_path / "history")
    control = make_controller(tmp_path, monkeypatch, history)
    control.add_files([str(path) for path in media])
    finish(control, media[0], [segment(0.0, 2.0, "Первый."), segment(3.0, 4.0, "Второй.")])
    # The second file is cancelled before any text: nothing to keep.
    control.handle(("finished", Transcript(source=str(media[1]), model="RNNT", device="CPU", cancelled=True), []))

    later = make_controller(tmp_path, monkeypatch, History(tmp_path / "history"))
    files = later.ready()["files"]
    assert [(file["name"], file["state"]) for file in files] == [("a.mp3", "done")]
    restored = files[0]
    # The model that made the text comes back too (finish() reports RNNT).
    assert restored["model"] == "GigaAM v3 RNNT" and restored["detail"].endswith("готово, RNNT")
    assert [chip["path"] is not None for chip in restored["outputs"]] == [True, True, False, False, False]
    assert later.copy_text(restored["id"], False) == "Первый.\nВторой.\n"
    assert [line["text"] for line in later.segments(restored["id"])] == ["Первый.", "Второй."]
    assert later.worker.jobs.empty()  # nothing is recognised again

    # A format created after the restart is remembered too.
    assert later.create_output(restored["id"], "srt")
    third = make_controller(tmp_path, monkeypatch, History(tmp_path / "history"))
    assert third.ready()["files"][0]["outputs"][3]["path"].endswith("a-transcript.srt")

    # Removing it from the list forgets it but keeps the transcript files.
    assert third.remove(third.files[0].id)
    assert History(tmp_path / "history").load() == []
    assert (tmp_path / "a-transcript.txt").is_file()


def test_retry_replaces_the_remembered_result(tmp_path, monkeypatch, media):
    history = History(tmp_path / "history")
    control = make_controller(tmp_path, monkeypatch, history)
    control.add_files([str(media[0])])
    finish(control, media[0], [segment(0.0, 2.0, "Старый.")])
    item_id = control.files[0].id
    control.retry(item_id)
    finish(control, media[0], [segment(0.0, 2.0, "Новый.")])
    entries = history.load()
    assert len(entries) == 1 and entries[0].transcript.segments[0].text == "Новый."
    # A failed retry keeps the last good result for the next session.
    control.retry(item_id)
    control.handle(("error", "boom"))
    assert history.load()[0].transcript.segments[0].text == "Новый."


def test_without_history_nothing_is_written(tmp_path, monkeypatch, media):
    control = make_controller(tmp_path, monkeypatch, None)
    control.add_files([str(media[0])])
    finish(control, media[0], [segment(0.0, 2.0, "Текст.")])
    assert not (tmp_path / "history").exists()
