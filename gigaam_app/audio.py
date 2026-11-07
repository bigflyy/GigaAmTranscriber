"""Decode any audio or video file into mono 16 kHz float32 samples with ffmpeg."""

import io
import os
import subprocess
import wave

import numpy as np

from .paths import ffmpeg_executable

SAMPLE_RATE = 16000
# Formats the window's page plays as they are (WebView2; WebKitGTK with the usual GStreamer
# plugins), told by the file name. Others get a playable copy first (start_playable_copy).
PLAYABLE_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".oga", ".opus", ".flac", ".webm", ".mp4"}


def _run_ffmpeg(path, arguments):
    """Run ffmpeg on one input file and return its stdout bytes; RuntimeError on failure."""
    command = [ffmpeg_executable(), "-nostdin", "-hide_banner", "-v", "error", "-threads", "0", *arguments]
    # CREATE_NO_WINDOW keeps a console from flashing up when the GUI runs ffmpeg.
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(command, capture_output=True, creationflags=flags)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = message[-1] if message else f"exit code {result.returncode}"
        raise RuntimeError(f"Could not read audio from {path}: {detail}")
    return result.stdout


def _range_arguments(path, start, duration):
    """Input seeking (-ss before -i): fast, and exact because the audio is decoded."""
    return ["-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.0, duration):.3f}", "-i", str(path)]


def decode_audio(path) -> np.ndarray:
    """Return the whole file as float32 samples in [-1, 1].

    The file is decoded once; every later stage slices this array.
    """
    data = _run_ffmpeg(path, ["-i", str(path), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
                              "-f", "s16le", "-acodec", "pcm_s16le", "-"])
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def decode_range(path, start, duration) -> np.ndarray:
    """Samples of `duration` seconds from `start` (a selected part of the text)."""
    data = _run_ffmpeg(path, [*_range_arguments(path, start, duration), "-vn", "-ac", "1",
                              "-ar", str(SAMPLE_RATE), "-f", "s16le", "-acodec", "pcm_s16le", "-"])
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def start_playable_copy(path, target, codec="libopus"):
    """Start ffmpeg writing a copy of the file's sound that the window can play; returns the
    process (the caller waits for it, or stops it when the window closes).

    codec "libopus" writes Ogg Opus, 32 kbps mono: small and clear for speech (a 45 min
    call: 10 MB in about 36 s). "libmp3lame" writes MP3 64 kbps mono, the fallback for an
    ffmpeg without Opus.
    """
    rate = "32k" if codec == "libopus" else "64k"
    command = [ffmpeg_executable(), "-nostdin", "-hide_banner", "-v", "error", "-y", "-i", str(path),
               "-vn", "-ac", "1", "-c:a", codec, "-b:a", rate, str(target)]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, creationflags=flags)


def wav_clip(path, start, duration) -> bytes:
    """A WAV file (16 kHz mono, about 32 KB per second) of a part, for the window to play.

    The header is written here: ffmpeg writing WAV to a pipe cannot go back to fill in
    the length, and some players stop at such a file.
    """
    data = _run_ffmpeg(path, [*_range_arguments(path, start, duration), "-vn", "-ac", "1",
                              "-ar", str(SAMPLE_RATE), "-f", "s16le", "-acodec", "pcm_s16le", "-"])
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(data)
    return buffer.getvalue()
