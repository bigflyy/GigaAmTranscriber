# GigaAM Transcriber v0.1.0

Portable Windows x64 transcription app with a Russian interface and English
advanced settings/help. Both RNNT and CTC models are bundled for offline use.

## Windows downloads

- **CPU:** download `GigaAmTranscriber-CPU.exe` and run it. No Python, Conda,
  FFmpeg installation, or model download is needed.
- **CUDA:** download **all** `GigaAmTranscriber-CUDA.exe.partXX` files, plus
  `cuda-parts.json`, `Join-CUDA.ps1`, and `Join-CUDA.cmd` into the same directory.
  Double-click **Join-CUDA.cmd**. It verifies SHA-256 checksums and reconstructs
  `GigaAmTranscriber-CUDA.exe`. Run that EXE normally afterward; the parts can
  be deleted. An NVIDIA GPU and compatible driver are needed for CUDA mode.
  The CUDA app also supports CPU mode.

GitHub limits each asset to under 2 GiB, so CUDA is distributed in parts.
Allow free disk space for the downloaded parts, the assembled EXE, and the
temporary extraction performed by a single-file PyInstaller executable.
First launch can take tens of seconds. These EXEs are not code-signed.

## Features

- File selection, streaming partial results, progress and estimated remaining time.
- Cancellation retains and saves partial text. Total elapsed time appears afterward.
- Plain `name-transcript.txt` and timestamped `name-transcript-timestamps.txt`.
- Timestamp checkbox affects only the preview; it is off by default.
- No forced auto-scroll when new text arrives.
- Total duration, speech/non-speech duration, and actual skipped audio.
- RNNT/CTC, CPU/CUDA selection, four CPU threads by default, single-thread Silero VAD.
- VAD max speech, preferred max chunk, and hard limit default to 25 seconds.
- Removed the preferred-min early-cut rule; corrected leading-silence retention.
- Import/export settings and `gigaam-config.json` beside the EXE for startup defaults.

Existing saved configs override defaults. Use **Reset defaults → Save as default**
to adopt the current defaults. Rename the supplied example config to
`gigaam-config.json` only if you want to use its values as your startup preset.

## Docker

CPU: `ghcr.io/bigflyy/gigaamtranscriber:cpu`

CUDA: `ghcr.io/bigflyy/gigaamtranscriber:cuda`

Versioned tags: `v0.1.0-cpu` and `v0.1.0-cuda`.

**[Docker setup, model download, and copy-and-paste commands](https://github.com/bigflyy/GigaAmTranscriber/blob/main/DOCKER.md)**

Docker images are headless Linux amd64 runners. Model weights use a mounted
cache, rather than being embedded in the image.

## Verification

Regression checks cover configuration, chunking, leading silence, GUI controls,
scroll preservation, cancellation, elapsed time and both TXT exports. Both
models are tested on CPU and CUDA. Packaged apps are tested without Conda or
FFmpeg on PATH, with an empty user model cache and downloads blocked. CPU and
CUDA Docker images are tested with `--network none` and mounted models.

`SHA256SUMS.txt` contains release asset checksums. The CUDA manifest also contains
the expected hash of the reconstructed executable.

[Verification details](https://github.com/bigflyy/GigaAmTranscriber/blob/main/RELEASE_TESTS.md)
and [third-party notices](https://github.com/bigflyy/GigaAmTranscriber/blob/main/THIRD_PARTY_NOTICES.md)
are available in the repository. License notices and the bundled FFmpeg source
revision are supplied as companion release downloads.
