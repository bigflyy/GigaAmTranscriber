"""gigaam_app/paths.py: the ffmpeg message, the frozen Linux child environment, replace_file."""

import os
import sys

import pytest

from gigaam_app import paths


def test_missing_ffmpeg_names_the_package_on_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(paths.shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="sudo apt install ffmpeg"):
        paths.ffmpeg_executable()


@pytest.fixture
def frozen_linux(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/opt/app/_internal", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")


def test_child_environment_gets_the_original_library_path(frozen_linux, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/app/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")
    paths.restore_child_environment()
    assert os.environ["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in os.environ


def test_child_environment_drops_only_the_app_folder(frozen_linux, monkeypatch):
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/app/_internal:/usr/local/lib")
    paths.restore_child_environment()
    assert os.environ["LD_LIBRARY_PATH"] == "/usr/local/lib"
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/app/_internal")
    paths.restore_child_environment()
    assert "LD_LIBRARY_PATH" not in os.environ


def test_child_environment_is_left_alone_from_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/somewhere")
    paths.restore_child_environment()
    assert os.environ["LD_LIBRARY_PATH"] == "/somewhere"


def test_replace_file_waits_for_a_short_lock(tmp_path, monkeypatch):
    """Windows refuses a replace while another program holds the old file for a moment
    (an antivirus, a reader); replace_file tries again instead of failing the save."""
    source, target = tmp_path / "new.tmp", tmp_path / "settings.json"
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")
    real_replace, calls = os.replace, []

    def busy_twice(a, b):
        calls.append(a)
        if len(calls) <= 2:
            raise PermissionError(5, "Access is denied")
        real_replace(a, b)

    monkeypatch.setattr(paths.os, "replace", busy_twice)
    monkeypatch.setattr(paths, "REPLACE_PAUSE", 0)
    paths.replace_file(source, target)
    assert len(calls) == 3 and target.read_text(encoding="utf-8") == "new"


def test_replace_file_gives_up_on_a_lasting_lock(tmp_path, monkeypatch):
    def always_busy(a, b):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(paths.os, "replace", always_busy)
    monkeypatch.setattr(paths, "REPLACE_PAUSE", 0)
    with pytest.raises(PermissionError):
        paths.replace_file(tmp_path / "a", tmp_path / "b")
