# GigaAM Transcriber

Offline transcription of Russian speech from audio and video files, with the
[GigaAM v3](https://github.com/salute-developers/GigaAM) models. An app for
Windows and Linux (window and command line) and Linux Docker images.
[Whisper](https://github.com/openai/whisper) large-v3-turbo can be downloaded as a
second model for other languages and for English terms inside Russian speech.

Since v0.2.0 the app runs on [ONNX Runtime](https://onnxruntime.ai/) instead of
PyTorch: the download is a quarter of the old CUDA build, it starts in a few
seconds, and it uses any DirectX 12 GPU (NVIDIA, AMD, Intel) through DirectML,
with the CPU as fallback. A 7.5-minute lecture takes about 5 s on a laptop GPU
and about 25 s on the CPU; see [BENCHMARK.md](BENCHMARK.md).

## Downloads

- **Windows:** [`GigaAmTranscriber-v0.5.0-windows-x64.zip`](https://github.com/bigflyy/GigaAmTranscriber/releases/latest)
  (about 930 MB, 1.2 GB unpacked). Unzip it anywhere and run `GigaAmTranscriber.exe`.
  No Python, CUDA or FFmpeg is needed; both GigaAM models are inside (Whisper is a
  547 MB download the first time it is chosen).
- **Linux:** [`GigaAmTranscriber-v0.5.0-linux-x64.tar.gz`](https://github.com/bigflyy/GigaAmTranscriber/releases/latest)
  (about 840 MB, 1 GB unpacked). Unpack it and run `./GigaAmTranscriber/GigaAmTranscriber`.
  Recognition runs on the CPU. The system must have glibc 2.39 or newer (Ubuntu 24.04,
  Debian 13, Fedora 40 and later), FFmpeg and, for the window, WebKitGTK 4.1:
  `sudo apt install ffmpeg gir1.2-webkit2-4.1` (Fedora:
  `sudo dnf install ffmpeg-free webkit2gtk4.1 gobject-introspection`).
  Without WebKitGTK the app says what to install; `gigaam-cli` works without it.
- **Docker (Linux, command line):** CPU and NVIDIA CUDA images, see [DOCKER.md](DOCKER.md).

## Using the app

Add files with **+ Добавить** or drag them (or a folder) onto the window. They
are transcribed one at a time, in the order added: the list on the left shows
which are done, running and waiting, and the right side shows the selected
file's progress and its text as it is recognised. **Отмена** stops the running
file and keeps the finished part. Each file names the model that recognised it
in the line under its name (the list line says RNNT, CTC or Whisper), also after the
settings choose another. The model loads in the background as soon as
the window opens and stays loaded between files. Closing the window while a file
runs asks first; the part recognised so far is saved.

The list is kept between sessions: finished files come back with their text the
next time the window opens, and missing formats can still be written from it.
**...** -> **Убрать из списка** forgets a file; its saved transcripts stay where they are. The
list lives in `%LOCALAPPDATA%\GigaAmTranscriber\history` on Windows and
`~/.local/share/gigaam-transcriber/history` on Linux (`GIGAAM_HISTORY` overrides it).
Results are saved beside the source file:

| Format | File | Contents |
| --- | --- | --- |
| `txt` | `name-transcript.txt` | plain text, one line per speech fragment |
| `timestamps` | `name-transcript-timestamps.txt` | the same lines with `[start - end]` times |
| `md` | `name-transcript.md` | Markdown: file name, date, length and model, then the text in sections of about a minute under their start times |
| `srt` | `name-transcript.srt` | subtitles, short cues built from word times |
| `json` | `name-transcript.json` | segments and every word with its start and end time and the model's confidence (0 to 1) |
| `llm` | `name-transcript-llm.txt` | text to paste into a chat with an AI: a note on the marks, then the text with doubtful words marked as `word[?66%]` (below the dotted threshold), and both versions `{GigaAM v3 RNNT: ... \| Whisper ...: ...}` where another model heard otherwise |

TXT and timestamped TXT are on by default; **Файлы** above the text opens the saved
ones and writes the other formats from the text already recognised. **Настройки** (bottom left)
chooses the formats, the model (RNNT by default, CTC, or Whisper), the device (Авто,
Видеокарта, Процессор) and CPU threads; changes count from the next file.
Choosing Whisper the first time asks to download it (547 MB); with Whisper the
settings also show **Язык речи**: automatic detection or a chosen language.
Words the model was unsure of are underlined in the text (dotted: maybe wrong,
wavy: likely wrong; hover a word for the number); the **Сомнения** switch above
the text hides the marks, and **Настройки** can colour every word from green to
red by confidence instead. **Копировать** copies the text as shown; its arrow offers
**Копировать для ИИ**, the text in the `llm` format, ready to paste into a chat with an AI model.

The **Говорящие** switch above the text finds who speaks when (on a file without
speakers it asks how many people talk, if known) and then shows or hides the names; the
saved files always carry them. A new paragraph starts at each change of speaker with a
coloured name, and a line of chips under the switches shows each speaker's share of the
speech. A click on a name renames that speaker, gives the turn to another or a new
speaker, or merges two speakers; selected words get **Говорящий** for the same.
**Настройки** -> **Говорящие** runs the search after every file.

A bar under the text plays the whole file (play / pause, seeking, speed, volume;
Space plays and pauses) and highlights the word being spoken; a click on a line's
time plays from there, Alt+click from a word. Select words to get **▶ Слушать**,
**Распознать заново** (that part read again by RNNT, CTC and Whisper, shown side by
side; **Термины** gives Whisper names and terms as a hint) and **Исправить...** (type
the text by hand); the saved files are written again at once. After a file is
recognised on the GPU, each line with doubtful words is also read by another model
(Whisper checks GigaAM, RNNT checks Whisper): where it heard something else, the
underline turns blue and a click shows the offer with **Взять** and **Оставить как
есть**. **Настройки** -> **Варианты для сомнительных слов** chooses when to look
(after GPU files, always, or only with **...** -> **Найти варианты**). The models
run in a separate process, so the window stays responsive while they load.

Settings are saved at once to `gigaam-config.json` beside the app (the command
line reads the same file); **Сбросить настройки** goes back to the defaults. The window follows the system's light or dark theme.

The window is a web page shown by Microsoft Edge WebView2, which Windows 10 and
11 normally have; if it is missing, the app says so and links to Microsoft's
installer. On Linux it is shown by the system's WebKitGTK.

The command line uses the same models and settings file:

```powershell
gigaam-cli.exe recording.mp3
gigaam-cli.exe *.mp4 --formats txt,srt --out-dir C:\Transcripts
gigaam-cli.exe lecture.m4a --model CTC --device cpu --threads 8
gigaam-cli.exe --download Whisper
gigaam-cli.exe interview.mp3 --model Whisper --language en
gigaam-cli.exe --help
```

### Settings file

`gigaam-config.json` beside the app holds the defaults for both the window and
the command line. [`gigaam-config.example.json`](gigaam-config.example.json)
lists every key; `language` (`"auto"` or a code such as `"en"`) is used only by
Whisper. Files saved by v0.1 still load (`"CUDA"` now means GPU; the v0.1 multilingual
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

**Whisper** runs on [whisper.cpp](https://github.com/ggml-org/whisper.cpp) 1.9.5
through ctypes, on any Vulkan GPU (NVIDIA, AMD, Intel) or the CPU. It gets the same
Silero speech chunks, each recognised on its own with greedy decoding; whole-file
decoding and beam search invented text and repeated phrases on a long call. Word
times come from whisper.cpp's token times. The 7.5-minute lecture takes about 12 s
on a laptop RTX 4070 (GigaAM: about 6 s). On Russian GigaAM is usually more accurate;
Whisper writes English terms as written ("fine tuning", "prompt") and knows 99 languages.

## Building from source

Python 3.12 on Windows. The app needs only numpy and ONNX Runtime:

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-build.txt   # app + PyInstaller + pytest
.venv\Scripts\python -m gigaam_app                   # window
.venv\Scripts\python -m gigaam_app.cli file.mp3      # command line
```

FFmpeg must be on PATH (or `ffmpeg.exe` in the repository root) when running from source.
Whisper needs the whisper.cpp libraries, built once by `python tools/build_whisper_cpp.py`
into `third_party/whisper.cpp/` (the script lists what the build machine needs).

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
first). Whisper large-v3-turbo (q5_0) is the first: its file comes from the
`models-1` release of this repository, and from the whisper.cpp project's
Hugging Face files when the release cannot deliver it; the app writes its
`model.json` itself. To publish a GigaAM-type model, export it, run
`python tools/stage_model_assets.py assets export/<folder>`, upload `assets/*`
to the `models-1` release and paste the printed lines into the catalog.

**Tests.** `python -m pytest tests` runs the unit tests (VAD against the
silero-vad reference, decoders against a textbook RNNT decoder, outputs,
settings, CLI, the threaded pipeline with fakes, model downloads against a local
HTTP server) and, when `models/` exists,
tests on the real models. A full-file comparison with a v0.1 reference runs when
`GIGAAM_PARITY_AUDIO` and `GIGAAM_PARITY_REFERENCE` are set; see
[tests/test_models.py](tests/test_models.py). Whisper's tests use the built
whisper.cpp libraries; `GIGAAM_WHISPER_MODEL_ROOT` (a folder holding the model folder
and `silero_vad_scan.onnx`) with `GIGAAM_PARITY_AUDIO` adds a run on the real model.
`python tools/window_check.py LONG SHORT --out FOLDER` drives the real window off
screen (`--whisper FOLDER` adds a file transcribed with a downloaded Whisper model).

**Windows release.** In the build environment (no PyTorch in it):

```powershell
python tools/build_windows.py
```

It verifies the models, builds both EXEs into one folder with
[packaging/GigaAmTranscriber.spec](packaging/GigaAmTranscriber.spec), copies the
models, `ffmpeg.exe` (Gyan's 8.0.1 full build, matching the source archive in
`third_party/ffmpeg/`) and the licences, runs the console EXE, transcribes a
short Russian file with Whisper on the GPU and the CPU, and starts the
window off screen ([tools/gui_smoke_test.py](tools/gui_smoke_test.py)),
then writes the zip, `THIRD_PARTY_LICENSES.zip`, the FFmpeg source and
`SHA256SUMS.txt` to `build/release/`. The Whisper test does not download the model: it links in a
downloaded model folder, `--whisper-model FOLDER` (a `whisper_large_v3_turbo_q5_0`
folder, for example from `%LOCALAPPDATA%\GigaAmTranscriber\models`) with
`--whisper-audio FILE`; both default to the test area `build/whisper-test/`, and
`--no-whisper-test` skips it. The Linux build takes the same options.

**Linux release.** Built and tested on Ubuntu 24.04 (WSL works) with the system
Python 3.12, because the app carries the system's PyGObject, which fits only that
Python. The build machine needs `python3-venv python3-gi gir1.2-webkit2-4.1 ffmpeg xvfb x11-utils`:

```bash
python3 -m venv ~/.venvs/gigaam-build      # without --system-site-packages
~/.venvs/gigaam-build/bin/pip install -r requirements-build.txt
~/.venvs/gigaam-build/bin/python tools/build_linux.py --out ~/gigaam-build --speech sample.m4a
```

[packaging/GigaAmTranscriber-linux.spec](packaging/GigaAmTranscriber-linux.spec)
bundles Python, numpy, ONNX Runtime (CPU), pywebview and PyGObject; GTK,
WebKitGTK, GObject introspection and FFmpeg come from the system. The script
checks that every bundled library resolves, runs the command line on silence,
on the `--speech` file and with Whisper on the CPU, checks the missing-WebKitGTK message, opens the window on
a private Xvfb display and lets it transcribe the file, then writes the tar.gz and
`SHA256SUMS.txt`. For a release, build Windows first and pass
`--release /mnt/c/<repo>/build/release`: the Linux licences then go into the same
`THIRD_PARTY_LICENSES.zip` (folders `windows/` and `linux/`) and its line in `SHA256SUMS.txt`. When running from source on Linux, make the venv with
`--system-site-packages` so it sees the system's `gi`.

**Docker.** `docker build -t gigaam-transcriber:cpu .` exports the models in a
build stage and produces an image without PyTorch; see [DOCKER.md](DOCKER.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `gigaam_app/` | the app: audio, VAD, ASR, pipeline, outputs, settings, model catalog and downloads, CLI, window (`window.py`, `controller.py`, the page in `web/`) |
| `launchers/` | PyInstaller entry points |
| `packaging/` | PyInstaller specs (Windows, Linux), READMEs for the app folders, licences not shipped by packages |
| `tools/` | model export, Silero loop builder, download asset staging, Windows and Linux builds, off-screen window tests (`gui_smoke_test.py` for the EXE, `window_check.py` for the page) |
| `tests/` | pytest suite |
| `gigaam/` | upstream GigaAM PyTorch package (MIT), used only by the export tools |
| `experiments/` | prototypes and profiling scripts behind the v0.2 design |
| `docs/plans/` | work plans |

## Licences

MIT, like upstream GigaAM. Bundled components keep their licences; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The Windows app includes
FFmpeg (GPLv3) as a separate program; its source is a release download. The Linux
app uses the system's FFmpeg and does not include it.

GigaAM itself, its papers and model documentation:
[salute-developers/GigaAM](https://github.com/salute-developers/GigaAM).
