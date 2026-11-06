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


def history_dir() -> Path:
    """The window's list of transcribed files: GIGAAM_HISTORY if set, else a per-user folder
    beside the downloaded models."""
    override = os.environ.get("GIGAAM_HISTORY")
    if override:
        return Path(override)
    return downloads_dir().parent / "history"


def ffmpeg_executable() -> str:
    """Bundled ffmpeg.exe beside the app first, then whatever is on PATH."""
    for candidate in (app_dir() / "ffmpeg.exe", app_dir() / "bin" / "ffmpeg.exe"):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg")
    if not found:
        if sys.platform == "win32":
            raise RuntimeError("ffmpeg not found. Put ffmpeg.exe beside the app or add it to PATH.")
        # The Linux build uses the system FFmpeg.
        raise RuntimeError("ffmpeg not found. Install it: sudo apt install ffmpeg (Ubuntu, Debian) "
                           "or sudo dnf install ffmpeg-free (Fedora).")
    return found


def restore_child_environment():
    """Frozen Linux build: give programs the app starts the user's library path back.

    PyInstaller's bootloader puts the app's _internal folder first on
    LD_LIBRARY_PATH (the old value is kept in LD_LIBRARY_PATH_ORIG). Programs the
    app starts would inherit it: ffmpeg, xdg-open, and WebKitGTK's own helper
    processes, which must load the system libraries, not the bundled ones. The
    app itself is not affected: the loader read the variable when it started.
    """
    if not getattr(sys, "frozen", False) or sys.platform == "win32":
        return
    original = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
    if original is not None:
        os.environ["LD_LIBRARY_PATH"] = original
        return
    bundle = getattr(sys, "_MEIPASS", "")
    kept = [part for part in os.environ.get("LD_LIBRARY_PATH", "").split(":") if part and part != bundle]
    if kept:
        os.environ["LD_LIBRARY_PATH"] = ":".join(kept)
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)
