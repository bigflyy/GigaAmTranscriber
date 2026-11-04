"""Decode any audio or video file into mono 16 kHz float32 samples with ffmpeg."""

import os
import subprocess

import numpy as np

from .paths import ffmpeg_executable

SAMPLE_RATE = 16000


def decode_audio(path) -> np.ndarray:
    """Return the whole file as float32 samples in [-1, 1].

    The file is decoded once; every later stage slices this array.
    """
    command = [ffmpeg_executable(), "-nostdin", "-hide_banner", "-v", "error", "-threads", "0",
               "-i", str(path), "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
               "-f", "s16le", "-acodec", "pcm_s16le", "-"]
    # CREATE_NO_WINDOW keeps a console from flashing up when the GUI runs ffmpeg.
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(command, capture_output=True, creationflags=flags)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip().splitlines()
        detail = message[-1] if message else f"exit code {result.returncode}"
        raise RuntimeError(f"Could not read audio from {path}: {detail}")
    samples = np.frombuffer(result.stdout, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0
