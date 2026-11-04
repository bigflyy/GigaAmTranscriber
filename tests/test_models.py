"""Tests on the real exported models. Skipped when models/ has not been exported.

The parity test also needs a recording and a reference transcript made with
the v0.1 PyTorch pipeline (a JSON list of {"b": [start, end], "t": text}):

    set GIGAAM_PARITY_AUDIO=C:\\path\\recording.mp4
    set GIGAAM_PARITY_REFERENCE=C:\\path\\reference.json
    set GIGAAM_PARITY_DEVICE=cpu        (optional: auto, gpu or cpu)
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from gigaam_app.engine import BUNDLED_MODELS, Transcriber
from gigaam_app.paths import models_dir

ROOT = Path(__file__).resolve().parents[1]
HAVE_MODELS = all((models_dir() / folder / "model.json").is_file() for folder in BUNDLED_MODELS.values()) and \
    (models_dir() / "silero_vad_scan.onnx").is_file()
needs_models = pytest.mark.skipif(not HAVE_MODELS, reason="exported models not found in models/")
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


@pytest.fixture(scope="module", params=list(BUNDLED_MODELS))
def cpu_transcriber(request):
    return Transcriber(request.param, device="cpu", cpu_threads=2)


@needs_models
def test_encoder_shapes(cpu_transcriber):
    model = cpu_transcriber.asr
    pieces = [np.zeros(16000, np.float32), np.zeros(8000, np.float32)]
    encoded = model.encode(pieces)
    # 40 ms frames: one second gives 25 frames, half a second about 13.
    assert [len(item) for item in encoded] in ([25, 13], [26, 13], [25, 12])
    assert encoded[0].dtype == np.float32
    assert model.decode(encoded[0]) == []  # silence decodes to nothing


@needs_models
@needs_ffmpeg
def test_silent_file_has_no_speech(cpu_transcriber, tmp_path):
    path = tmp_path / "silence.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "4",
                    str(path)], check=True)
    result = cpu_transcriber.transcribe(path)
    assert result.segments == [] and abs(result.audio_seconds - 4.0) < 0.01


@needs_models
@pytest.mark.skipif(not (os.environ.get("GIGAAM_PARITY_AUDIO") and os.environ.get("GIGAAM_PARITY_REFERENCE")),
                    reason="set GIGAAM_PARITY_AUDIO and GIGAAM_PARITY_REFERENCE")
def test_parity_with_reference():
    reference = json.loads(Path(os.environ["GIGAAM_PARITY_REFERENCE"]).read_text(encoding="utf-8"))
    transcriber = Transcriber("RNNT", device=os.environ.get("GIGAAM_PARITY_DEVICE", "cpu"))
    result = transcriber.transcribe(os.environ["GIGAAM_PARITY_AUDIO"])
    assert len(result.segments) == len(reference)
    for segment, expected in zip(result.segments, reference):
        assert abs(segment.start - expected["b"][0]) <= 0.051 and abs(segment.end - expected["b"][1]) <= 0.051
    assert " ".join(s.text for s in result.segments).split() == " ".join(r["t"] for r in reference).split()


@needs_models
@needs_ffmpeg
def test_cli_end_to_end(tmp_path):
    audio = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2",
                    str(audio)], check=True)
    run = subprocess.run([sys.executable, "-m", "gigaam_app.cli", str(audio), "--device", "cpu",
                          "--formats", "txt,json", "-o", str(tmp_path / "out")],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert run.returncode == 0, run.stderr
    assert "no speech found" in run.stdout


@needs_models
@needs_ffmpeg
def test_cli_survives_unprintable_file_names(tmp_path):
    # With output redirected, Windows uses the ANSI code page, which has no check mark.
    audio = tmp_path / "запись ✓.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "1",
                    str(audio)], check=True)
    env = {**os.environ, "PYTHONIOENCODING": "cp1251"}
    run = subprocess.run([sys.executable, "-m", "gigaam_app.cli", str(audio), "--device", "cpu"],
                         cwd=ROOT, capture_output=True, env=env, timeout=120)
    assert run.returncode == 0, run.stderr.decode("cp1251", "replace")
