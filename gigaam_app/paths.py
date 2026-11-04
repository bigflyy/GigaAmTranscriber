"""Where the app finds its own files, in source checkouts and in frozen builds."""

import os
from pathlib import Path
import shutil
import sys


def app_dir() -> Path:
    """Folder that holds the launcher: the EXE folder when frozen, the repository otherwise."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def models_dir() -> Path:
    """Model folder: GIGAAM_MODELS if set, else 'models' beside the app."""
    override = os.environ.get("GIGAAM_MODELS")
    return Path(override) if override else app_dir() / "models"


def downloads_dir() -> Path:
    """Downloaded models: GIGAAM_DOWNLOADS if set, else a per-user folder.

    It is outside the app folder, so a new app version unpacked elsewhere
    finds the models already downloaded by the old one.
    """
    override = os.environ.get("GIGAAM_DOWNLOADS")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "GigaAmTranscriber" / "models"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "gigaam-transcriber" / "models"


def ffmpeg_executable() -> str:
    """Bundled ffmpeg.exe beside the app first, then whatever is on PATH."""
    for candidate in (app_dir() / "ffmpeg.exe", app_dir() / "bin" / "ffmpeg.exe"):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg not found. Put ffmpeg.exe beside the app or add it to PATH.")
    return found
