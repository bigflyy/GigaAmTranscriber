# GigaAM Transcriber v0.2.0

The app is rewritten on ONNX Runtime. PyTorch is gone from the app: one
Windows download for every GPU and the CPU, a few seconds to start, and
transcription several times faster. The recognised text is the same as in v0.1.

## Windows download

Download **`GigaAmTranscriber-v0.2.0-windows-x64.zip`** (about 920 MB), unzip
it anywhere and run **`GigaAmTranscriber.exe`**. `gigaam-cli.exe` in the same
folder is the command line. No Python, CUDA, FFmpeg or model download is needed.

- One build for all computers: **Авто** uses any DirectX 12 GPU (NVIDIA, AMD,
  Intel) through DirectML and falls back to the CPU. No CUDA install, no split
  download, no join script.
- A folder instead of a single EXE: nothing is unpacked to a temporary folder at
  every launch. The window opens in about 1 s and the model is ready 2-3 s
  later (v0.1: 27 s for the CPU EXE and over 100 s for the CUDA EXE before the
  window appeared).
- These EXEs are not code-signed; Windows SmartScreen may ask for confirmation.

## Faster

On a 7.5-minute lecture (Ryzen 7 7840HS, RTX 4070 Laptop):

| | v0.1 (PyTorch) | v0.2 (ONNX Runtime) |
| --- | ---: | ---: |
| GPU, first file after start | 38 s (CUDA) | 5-7 s (DirectML) |
| CPU, 8 threads | 40 s | 25 s |
| Model ready after start | 11-15 s | 2-3 s |

The model now starts loading when the window opens and stays loaded between
files. The speech search overlaps with recognition, the audio is decoded once,
and the RNNT decoder no longer runs its network on every frame.
Details: [BENCHMARK.md](https://github.com/bigflyy/GigaAmTranscriber/blob/main/BENCHMARK.md).

## New

- **SRT subtitles** and **JSON with word times** in addition to TXT and timestamped TXT.
- **Word timestamps** from the decoders (40 ms steps), used by SRT and JSON.
- The command line takes several files and wildcards (`gigaam-cli.exe *.mp3`),
  `--formats`, `--out-dir`, and the speech search settings as flags.
- Simpler settings window: model, device, CPU threads and output formats.
  The speech search settings are in `gigaam-config.json` (see
  `gigaam-config.example.json`); v0.1 settings files still load.

## Same results

The speech search and chunking are ported exactly from v0.1 (Silero VAD 6.2.1
and the same grouping). On the 7.5-minute test file all 932 words and all 26
chunk boundaries are identical to v0.1, on the GPU and on the CPU.

## Docker

CPU: `ghcr.io/bigflyy/gigaamtranscriber:cpu` · CUDA: `ghcr.io/bigflyy/gigaamtranscriber:cuda`
(versioned: `v0.2.0-cpu`, `v0.2.0-cuda`).

The models are now inside the images: no model volume or download step.
Some flags changed (`--device gpu`, `--threads`, `--model RNNT|CTC`).
[Docker commands](https://github.com/bigflyy/GigaAmTranscriber/blob/main/DOCKER.md).

## Not in this release

- Only the Russian v3 RNNT and CTC models are included. The multilingual
  models need a model download step in the app, which is planned.
- Speaker diarization (who speaks when) is planned for a later release.

## Downloads

- `GigaAmTranscriber-v0.2.0-windows-x64.zip` - the app.
- `THIRD_PARTY_LICENSES.zip` - licences of the bundled components (also inside the app folder).
- `FFmpeg-8.0.1-source.zip` - source of the bundled FFmpeg build (GPLv3).
- `SHA256SUMS.txt` - checksums of the files above.

[Verification](https://github.com/bigflyy/GigaAmTranscriber/blob/main/RELEASE_TESTS.md)
· [Third-party notices](https://github.com/bigflyy/GigaAmTranscriber/blob/main/THIRD_PARTY_NOTICES.md)
