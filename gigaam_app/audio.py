"""Decode any audio or video file into mono 16 kHz float32 samples with ffmpeg."""

import io
import os
import subprocess
import wave

import numpy as np

from .paths import ffmpeg_executable

SAMPLE_RATE = 16000


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
