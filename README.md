# GigaAM Transcriber

Offline transcription of Russian speech from audio and video files, with the
[GigaAM v3](https://github.com/salute-developers/GigaAM) models. A Windows app
(window and command line) and Linux Docker images.

Since v0.2.0 the app runs on [ONNX Runtime](https://onnxruntime.ai/) instead of
PyTorch: the download is a quarter of the old CUDA build, it starts in a few
seconds, and it uses any DirectX 12 GPU (NVIDIA, AMD, Intel) through DirectML,
with the CPU as fallback. A 7.5-minute lecture takes about 5 s on a laptop GPU
and about 25 s on the CPU; see [BENCHMARK.md](BENCHMARK.md).

## Downloads

- **Windows:** [`GigaAmTranscriber-v0.2.0-windows-x64.zip`](https://github.com/bigflyy/GigaAmTranscriber/releases/latest)
  (about 920 MB, 1.2 GB unpacked). Unzip it anywhere and run `GigaAmTranscriber.exe`.
  No Python, CUDA, FFmpeg or model download is needed; both models are inside.
- **Docker (Linux, command line):** CPU and NVIDIA CUDA images, see [DOCKER.md](DOCKER.md).

## Using the app

Choose a file and press **Распознать**. The model loads in the background as
soon as the window opens and stays loaded between files. Text appears while the
file is processed; **Отмена** stops and keeps the finished part. Results are
saved beside the source file:

| Format | File | Contents |
| --- | --- | --- |
| `txt` | `name-transcript.txt` | plain text, one line per speech fragment |
| `timestamps` | `name-transcript-timestamps.txt` | the same lines with `[start - end]` times |
| `srt` | `name-transcript.srt` | subtitles, short cues built from word times |
| `json` | `name-transcript.json` | segments and every word with its start and end time |

TXT and timestamped TXT are on by default; **Настройки** chooses the formats,
the model (RNNT by default, or CTC), the device
(Авто, GPU, CPU) and CPU threads. **Сохранить как настройки по умолчанию** writes
them to `gigaam-config.json` beside the app.

The command line uses the same models and settings file:

```powershell
gigaam-cli.exe recording.mp3
gigaam-cli.exe *.mp4 --formats txt,srt --out-dir C:\Transcripts
gigaam-cli.exe lecture.m4a --model CTC --device cpu --threads 8
gigaam-cli.exe --help
```

### Settings file

`gigaam-config.json` beside the app holds the defaults for both the window and
the command line. [`gigaam-config.example.json`](gigaam-config.example.json)
lists every key. Files saved by v0.1 still load (`"CUDA"` now means GPU; the v0.1 multilingual
models are gone, and settings that chose one get RNNT).
Speech search and chunking settings are only in this file and in command-line
flags such as `--vad-threshold`:

| Key | Default | Meaning |
| --- | ---: | --- |
| `vad_threshold` | 0.5 | Silero speech probability at or above which audio counts as speech |
| `vad_min_speech_ms` | 300 | shorter speech is ignored |
| `vad_min_silence_ms` | 2000 | a pause must be this long to end a speech region |
| `vad_speech_pad_ms` | 250 | padding added around each speech region |
| `vad_max_speech_s` | 25 | longer regions are split at their longest pause |
| `max_duration` | 25 | regions are joined into chunks of up to this many seconds |
| `strict_limit_duration` | 25 | longer chunks are cut into equal parts (GigaAM takes about 25 s at most) |
| `new_chunk_threshold` | 0.2 | chunks this short or shorter are dropped |

## How it works

```
ffmpeg decode -> Silero VAD (ONNX loop, CPU) -> GigaAM encoder (ONNX, GPU or CPU) -> greedy decoder (numpy)
```

The three stages run on their own threads, so recognition starts a few
seconds into a long file. The audio is decoded once. Silero runs as one ONNX
loop over blocks of 32 ms windows, which gives exactly the speech regions of
silero-vad. The encoder graph contains the log-mel front-end, so it takes raw
audio. The small RNNT prediction and joint networks run in numpy and only
step after an emitted token; this turned a 13 s decoder into a 1 s one.
Tokens keep their 40 ms frame positions, which gives word timestamps.

The text is identical to v0.1 (PyTorch): on a 7.5-minute test file all 932
words and all 26 chunk boundaries match, on DirectML and on the CPU.

## Building from source

Python 3.12 on Windows. The app needs only numpy and ONNX Runtime:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-build.txt   # app + PyInstaller + pytest
.venv\Scripts\python -m gigaam_app                   # window
.venv\Scripts\python -m gigaam_app.cli file.mp3      # command line
```

FFmpeg must be on PATH (or `ffmpeg.exe` in the repository root) when running from source.

**Models.** `models/` is not in git. The export tools turn the upstream PyTorch
checkpoints into ONNX; they need a separate environment with PyTorch
([requirements-export.txt](requirements-export.txt)) and use the upstream
`gigaam` package kept in [`gigaam/`](gigaam):

```powershell
python tools/export_models.py v3_e2e_rnnt v3_e2e_ctc --out models
python tools/make_silero_scan.py --out models/silero_vad_scan.onnx
```

Each export checks ONNX Runtime against PyTorch and writes `model.json` with
SHA-256 checksums. The v3 weights are stored as float16, which is lossless for
these checkpoints. Weights above 1.8 GiB go into `encoder.data1`, `encoder.data2`,
... beside `encoder.onnx`, because a protobuf file and a GitHub release asset are
limited to 2 GB.

**Downloadable models.** The app can download extra models into
`%LOCALAPPDATA%\GigaAmTranscriber\models` (`GIGAAM_DOWNLOADS` overrides it), each
file checked against the size and SHA-256 in
[`gigaam_app/catalog.py`](gigaam_app/catalog.py), with resume after an
interruption (`gigaam-cli --list-models`, `--download MODEL`; the window asks
first). No model uses this yet. To publish one, export it, run
`python tools/stage_model_assets.py assets export/<folder>`, upload `assets/*`
to the `models-1` release and paste the printed lines into the catalog.

**Tests.** `python -m pytest tests` runs the unit tests (VAD against the
silero-vad reference, decoders against a textbook RNNT decoder, outputs,
settings, CLI, the threaded pipeline with fakes, model downloads against a local
HTTP server) and, when `models/` exists,
tests on the real models. A full-file comparison with a v0.1 reference runs when
`GIGAAM_PARITY_AUDIO` and `GIGAAM_PARITY_REFERENCE` are set; see
[tests/test_models.py](tests/test_models.py).

**Windows release.** In the build environment (no PyTorch in it):

```powershell
python tools/build_windows.py
```

It verifies the models, builds both EXEs into one folder with
[packaging/GigaAmTranscriber.spec](packaging/GigaAmTranscriber.spec), copies the
models, `ffmpeg.exe` (Gyan's 8.0.1 full build, matching the source archive in
`third_party/ffmpeg/`) and the licences, runs the console EXE and starts the
window on a hidden desktop ([tools/gui_smoke_test.py](tools/gui_smoke_test.py)),
then writes the zip, `THIRD_PARTY_LICENSES.zip`, the FFmpeg source and
`SHA256SUMS.txt` to `build/release/`.

**Docker.** `docker build -t gigaam-transcriber:cpu .` exports the models in a
build stage and produces an image without PyTorch; see [DOCKER.md](DOCKER.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `gigaam_app/` | the app: audio, VAD, ASR, pipeline, outputs, settings, model catalog and downloads, CLI, GUI |
| `launchers/` | PyInstaller entry points |
| `packaging/` | PyInstaller spec, README for the app folder, licences not shipped by packages |
| `tools/` | model export, Silero loop builder, download asset staging, Windows build, hidden GUI test |
| `tests/` | pytest suite |
| `gigaam/` | upstream GigaAM PyTorch package (MIT), used only by the export tools |
| `experiments/` | prototypes and profiling scripts behind the v0.2 design |
| `docs/plans/` | work plans |

## Licences

MIT, like upstream GigaAM. Bundled components keep their licences; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The Windows app includes
FFmpeg (GPLv3) as a separate program; its source is a release download.

GigaAM itself, its papers and model documentation:
[salute-developers/GigaAM](https://github.com/salute-developers/GigaAM).
