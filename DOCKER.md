# Docker: CPU and NVIDIA CUDA

Images: **`ghcr.io/bigflyy/gigaamtranscriber:cpu`** and
**`ghcr.io/bigflyy/gigaamtranscriber:cuda`**.
Versioned tags are `v0.2.0-cpu` and `v0.2.0-cuda`.

[Package and available tags](https://github.com/bigflyy/GigaAmTranscriber/pkgs/container/gigaamtranscriber)
· [Publishing workflow](https://github.com/bigflyy/GigaAmTranscriber/actions/workflows/publish-containers.yml)

These are Linux amd64 command-line images on ONNX Runtime, without PyTorch.
For the Windows app with a window, use the
[Windows release](https://github.com/bigflyy/GigaAmTranscriber/releases/latest).
On Windows, use Docker Desktop with Linux containers. CUDA needs an NVIDIA GPU
and a GPU-enabled Docker setup (WSL2 on Windows).

Since v0.2.0 the RNNT and CTC models are inside the image, so there is no
separate model download step and no model volume. Transcription works offline.

## Transcribe with the CPU

Replace `C:\Audio` and `recording.mp3` with your folder and file. The folder is
mounted as `/data`, the image's working folder:

```powershell
docker run --rm --network none -v "C:\Audio:/data" ghcr.io/bigflyy/gigaamtranscriber:cpu recording.mp3
```

## Or with an NVIDIA GPU

```powershell
docker run --rm --network none --gpus all -v "C:\Audio:/data" ghcr.io/bigflyy/gigaamtranscriber:cuda recording.mp3
```

The CUDA image uses the GPU when `--gpus all` is given and one is available,
and the CPU otherwise; the first output line says which. `--device gpu` makes a
missing GPU an error instead.

On Linux, replace `C:\Audio` with an absolute folder such as `/home/you/audio`.

ONNX Runtime may print a warning that starts with `GPU device discovery failed`
when the container has no GPU; it is harmless.

## Options

Both commands save `recording-transcript.txt` and
`recording-transcript-timestamps.txt` in the audio folder. Common options:

```powershell
... recording.mp3 --model CTC                 # CTC instead of RNNT
... recording.mp3 --formats txt,srt,json      # also subtitles and word times
... "*.mp3" --out-dir out                     # every MP3 in the folder, results in out/
... recording.mp3 --threads 8                 # CPU threads (default: half the logical CPUs, at most 8)
... --help                                    # all options, including speech search settings
```

Settings can also come from a file: put a `gigaam-config.json` (see
[gigaam-config.example.json](gigaam-config.example.json)) in the audio folder
and add `--config gigaam-config.json`.

Changes from v0.1: the images no longer need the model volume, `--device cuda`
is now `--device gpu`, `--cpu-threads` is now `--threads`, and `--model` takes
`RNNT` or `CTC`.

## Publish a new version

Maintainers can run **Publish CPU and CUDA containers** from the repository's
Actions tab and enter a version such as `v0.2.0`. It builds both images, checks
that they transcribe offline with both models, and publishes them with the
repository's `GITHUB_TOKEN`; no registry password is committed.

## Local builds

```powershell
docker build -t gigaam-transcriber:cpu .
docker build --build-arg ORT_VARIANT=cuda -t gigaam-transcriber:cuda .
```

The first build stage downloads the GigaAM checkpoints and CPU PyTorch and
exports the models to ONNX with `tools/export_models.py`, which takes a few
minutes. Use the local tag in place of the `ghcr.io/...` name in the commands above.
