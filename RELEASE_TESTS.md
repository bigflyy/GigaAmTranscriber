# v0.2.0 release verification

Tested on 2026-11-04 on Windows 11 with an AMD Ryzen 7 7840HS and an NVIDIA
GeForce RTX 4070 Laptop GPU (8 GB). Other hardware was not tested; DirectML on
AMD and Intel GPUs is expected to work but was not tried.

## Automated tests

`python -m pytest tests`: 261 passed, 1 skipped (the parity test, which needs
two environment variables), in about 20 s.

- **VAD:** the streaming `ChunkFinder` gives exactly the regions and chunks of
  the batch port of silero-vad 6.2.1 plus the v0.1 grouping, for 160 random
  probability sequences under four option sets, and nothing for silence.
- **Decoders:** the fast numpy RNNT decoder equals a textbook greedy RNNT
  (full joint with log-softmax, prediction network re-run every step) on 36
  random small models; the per-frame symbol limit and all-blank cases; CTC
  repeat merging and blanks; words and word times from SentencePiece and
  character vocabularies.
- **Pipeline:** with a fake model and fake VAD, segments come out in time order
  and equal the chunks of the VAD; GPU batches keep to 8 chunks and 200 s;
  cancelling keeps finished segments; errors in the encoder or in a callback are
  raised and stop the worker threads; silence gives an empty transcript.
- **Outputs:** clock format, TXT, timestamped TXT, SRT cue splitting (pauses,
  sentence ends, 6 s and 84 characters), JSON, file names, atomic writes.
- **Settings:** defaults, a v0.1 file (byte order mark, `"CUDA"`, retired keys),
  round trip, the shipped example file, 18 kinds of invalid values.
- **CLI:** typed VAD flags, wildcard expansion, exit code 2 for bad formats,
  missing files and bad settings, `--version`, file names that the console code
  page cannot show.
- **Real models** (when `models/` exists): encoder output lengths, silence gives
  no text, CLI end to end.
- **Parity:** `GIGAAM_PARITY_AUDIO` + `GIGAAM_PARITY_REFERENCE` with the 455 s
  lecture and a v0.1 PyTorch CPU reference: the same 26 chunk boundaries
  (within 0.05 s) and the same 932 words, on DirectML (8 s) and on the CPU (28 s).

## Windows build

`python tools/build_windows.py` from a venv with only `requirements-build.txt`
(Python 3.12, numpy 2.5.4, onnxruntime-directml 1.23.0, PyInstaller 6.22.3).
The script itself checks:

- model files against the SHA-256 in each `model.json`, and the FFmpeg build
  (`8.0.1-full_build-www.gyan.dev`) against the source archive;
- no torch files in the build, and every bundled DLL is the build Python's own
  copy (a Tcl DLL from another conda on PATH once broke the window; PyInstaller
  now runs with a clean PATH);
- `gigaam-cli.exe --version` and transcription of a silent file on CPU and on
  Auto (DirectML), with PATH reduced to `System32`, so neither Python nor FFmpeg
  can come from the system;
- `GigaAmTranscriber.exe` starts on a hidden desktop, loads the model, shows no
  error and closes on `WM_CLOSE` with exit code 0;
- every release asset is below 2 GiB.

Manual checks of the built folder:

- **Window, full file:** `tools/gui_smoke_test.py --audio` on the 455 s lecture,
  on a hidden desktop: window after 3.2 s (before the startup fix below), transcript
  written after 8.0 s, RNNT on DirectML, 26 fragments; the saved text equals the
  v0.1 reference word for word (932 words). A PrintWindow capture showed the
  finished state: progress bar full, "Готово за 00:00:05 (94x быстрее реального
  времени), фрагментов: 26", audio and speech statistics, the text, the saved files.
- **Startup:** the first model load used to run before the window was drawn and
  delayed it to 2.7-5.3 s; it now starts 150 ms after the window, which appears
  after 0.85-1.07 s.
- **CLI:** both models on DirectML and CPU, two files in one run (see
  [BENCHMARK.md](BENCHMARK.md)); a Cyrillic file name with a character outside
  the console code page and output redirected to a file (failed before the fix,
  now passes and is covered by a test); TXT, SRT and JSON written.

## Docker

CPU image, built locally with `docker build -t gigaam-transcriber:cpu .`
(Docker Desktop 28.3.2, WSL2), 2.81 GB uncompressed:

- The export stage downloaded the checkpoints and exported both models with
  CPU torch 2.8.0: max |onnx - torch| 5.8e-06 (RNNT) and 2.0e-05 (CTC); the
  Silero loop equals per-window Silero exactly. The ONNX files differ in bytes
  from the Windows export (torch 2.12), the vocabularies are identical.
- With `--network none`: `--version`; the 455 s lecture with RNNT in 22.7 s and
  with CTC in 22.1 s on the CPU (8 threads). The RNNT text equals the v0.1
  reference word for word (932 words).

The CUDA image (`ORT_VARIANT=cuda`) was not built locally; the publishing
workflow builds it and checks offline CPU transcription with both models, which
the CPU image passed too. GPU use in that image is not yet verified.
