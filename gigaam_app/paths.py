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


def ffmpeg_executable() -> str:
    """Bundled ffmpeg.exe beside the app first, then whatever is on PATH."""
    for candidate in (app_dir() / "ffmpeg.exe", app_dir() / "bin" / "ffmpeg.exe"):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg not found. Put ffmpeg.exe beside the app or add it to PATH.")
    return found
