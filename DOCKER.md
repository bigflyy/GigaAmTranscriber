# Docker: CPU and NVIDIA CUDA

Images: **`ghcr.io/bigflyy/gigaamtranscriber:cpu`** and
**`ghcr.io/bigflyy/gigaamtranscriber:cuda`**.
Versioned tags are `v0.1.0-cpu` and `v0.1.0-cuda`.

[Package and available tags](https://github.com/bigflyy/GigaAmTranscriber/pkgs/container/gigaamtranscriber)
· [Publishing workflow](https://github.com/bigflyy/GigaAmTranscriber/actions/workflows/publish-containers.yml)

These are Linux amd64 command-line images. For the graphical Windows app,
use the [EXE release](https://github.com/bigflyy/GigaAmTranscriber/releases/latest).
On Windows, use Docker Desktop with Linux containers. CUDA needs an NVIDIA
GPU and a working GPU-enabled Docker setup (WSL2 on Windows).

## 1. Download models once

Model weights are stored in a reusable Docker volume, separately from the
image. This downloads RNNT and CTC (about 850 MiB combined). Internet is
needed for this initial step. Python and FFmpeg are inside the image.

```powershell
docker run --rm --entrypoint python --mount "type=volume,source=gigaam-models,target=/app/models" ghcr.io/bigflyy/gigaamtranscriber:cpu -c "import gigaam; [gigaam.load_model(m, device='cpu', download_root='/app/models') for m in ('v3_e2e_rnnt','v3_e2e_ctc')]"
```

If you only want the CUDA image, replace `:cpu` with `:cuda` in this command.
The download step itself uses the CPU and does not need `--gpus all`.

## 2. Transcribe with CPU

Replace `C:\Audio` and `recording.mp3` with your folder and file:

```powershell
docker run --rm --network none --mount "type=volume,source=gigaam-models,target=/app/models,readonly" --mount "type=bind,source=C:\Audio,target=/data" ghcr.io/bigflyy/gigaamtranscriber:cpu /data/recording.mp3 --device cpu
```

## 3. Or transcribe with CUDA

```powershell
docker run --rm --network none --gpus all --mount "type=volume,source=gigaam-models,target=/app/models,readonly" --mount "type=bind,source=C:\Audio,target=/data" ghcr.io/bigflyy/gigaamtranscriber:cuda /data/recording.mp3 --device cuda
```

On Linux, replace `C:\Audio` with an absolute Linux directory such as
`/home/you/audio`. To use CTC, add `--model v3_e2e_ctc`. RNNT is the default.
For CPU thread control, add `--cpu-threads 8` (default 4).

Both commands save **recording-transcript.txt** and
**recording-transcript-timestamps.txt** in your audio folder. After downloading
the image and models, transcription works offline, as shown by `--network none`.
The GUI's JSON configuration is not used by the CLI; pass settings as flags.

## Publish a new version

Maintainers can run **Publish CPU and CUDA containers** from the repository's
Actions tab and enter a version such as `v0.1.0`. It builds and publishes both
images using the repository's `GITHUB_TOKEN`; no registry password is committed.
On the first publication, GitHub defaults the package to private. In the package
settings, set visibility to **Public** to allow pulls without authentication.

## Local builds

```powershell
docker build -t gigaam-transcriber:cpu .
docker build --build-arg TORCH_VARIANT=cu124 -t gigaam-transcriber:cuda .
```

Use the local tag in place of the `ghcr.io/...` image name in the commands above.
