"""gigaam_app/paths.py: the ffmpeg message and the frozen Linux child environment."""

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
