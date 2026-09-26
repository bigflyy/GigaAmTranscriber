# GigaAM Transcriber

This repo contains a snapshot of a modified GigaAM package using Silero VAD.
The original `giga.py` is kept as the baseline. `transcribe.py` is the
standalone launcher. Run without arguments (or double-click the EXE) to open
the minimal Russian GUI. Choose a file (**Выбрать файл…**) and click
**Распознать**. The output is a normal UTF-8 `name-transcript.txt` file beside
the input. Recognized text appears after each completed speech chunk.

**Включить таймкоды** shows or hides timestamps immediately, including during
transcription. After completion it also updates the saved text file. The
original chunk boundaries remain in memory until the next file or closing
the app, so toggling timestamps back on restores them. No regex or destructive
editing of recognition results is used. The CLI supports `--no-timestamps`.

**Настройки** is collapsed initially. It contains RNNT/CTC model
selection, device selection, Silero speech/silence/padding settings, and chunk
lengths. **Сбросить настройки** restores the original settings. Silero 6.2.1 fixes
the analysis window to 512 samples at 16 kHz; its old window-size argument
has no effect, so this value is shown read-only.

Loading and speech detection use an activity indicator. Transcription reports
`100 × completed speech segments / total speech segments` after Silero has
found and grouped speech. This is a chunk count, not a time estimate: chunks
can take different amounts of time. The interface stays responsive while
the worker runs. The one-file EXE extracts before the window can appear;
the folder release starts faster.

## Run from the existing CUDA environment

```powershell
conda run -n cuda-torch2 python transcribe.py "C:\path\to\audio.mp4"
```

`transcribe.py --help` shows normal use. `transcribe.py --advanced-help` shows
the optional model, device, segmentation and Silero VAD parameters. Omitted
parameters retain the values from the original modified package. For example:

```powershell
conda run -n cuda-torch2 python transcribe.py "C:\path\to\audio.wav" --device cpu --vad-threshold 0.6
```

## Build a smaller CPU-only Windows release

Build with a fresh environment so the CUDA libraries and unrelated packages
from `cuda-torch2` are not included. These commands leave that environment
untouched.

```powershell
conda create -n gigaam-cpu python=3.12 pip -y
conda run -n gigaam-cpu python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchaudio==2.5.1
conda run -n gigaam-cpu python -m pip install -r requirements-cpu.txt
conda run -n gigaam-cpu python build_release.py cpu all
```

Build `onedir` alone during troubleshooting:

```powershell
conda run -n gigaam-cpu python build_release.py cpu onedir
```

The release directories are `dist/cpu/onedir/GigaAmTranscriber/` and
`dist/cpu/onefile/GigaAmTranscriber.exe`. The one-folder directory can be
zipped and unpacked on another Windows computer. Both builds include the
default RNNT model, its tokenizer, Silero data, and `ffmpeg.exe`, so the
default transcription path works offline. The advanced CTC choice downloads
its model on first use unless you package that model separately.

For the current local Russian GUI release, the single EXE is at
`dist/cpu/onefile-ru/GigaAmTranscriber.exe`: the older EXE was running and
Windows prevented replacing it. Close running copies before rebuilding
into the normal `onefile` location.

See [local release measurements](BENCHMARK.md) for package sizes, startup
checks, and CPU versus GPU transcription speed. The single EXE extracts its
contents on every launch.

## Build from the existing CUDA environment

The same launcher chooses CUDA when available, otherwise CPU. A CUDA release
includes GPU libraries even for CPU-only users, so it will be much larger.

```powershell
conda run -n cuda-torch2 python -m pip install pyinstaller
conda run -n cuda-torch2 python build_release.py cuda all
```

Both builds require a compatible Windows computer. The CUDA path additionally
requires a suitable NVIDIA GPU and driver. Always test the release outside the
development environment; changing the developer's `PATH` or installed Python
packages can mask missing bundled files.

Size and startup time will change with the installed PyTorch and FFmpeg versions.

## Build inputs and Git

`build_release.py` reads `v3_e2e_rnnt.ckpt` and its tokenizer from the user's
`~/.cache/gigaam` and locates `ffmpeg.exe` on `PATH`. Run the original script
once to populate the GigaAM cache if the files are missing. Models, temporary
transcripts, build directories, and release binaries are excluded from Git.

The imported `requirements.txt` and `setup.py` were retained from the source
snapshot; they include packages unrelated to this transcriber. Use
`requirements-cpu.txt` for the CPU build.

The current build script bundles a Gyan FFmpeg 8.0.1 full build, which is
GPLv3. Before publicly distributing binary releases, review the FFmpeg
[license and source requirements](https://www.ffmpeg.org/legal.html) for that
binary. Generated release files are kept out of Git.

## Docker: CPU command-line version

The Docker image is a headless Linux CPU runner, without the Windows GUI.
It was built and tested locally in about four minutes, including a real
transcription with networking disabled. Building elsewhere can take longer
depending on downloads. Docker must be installed and running.

Build:

```powershell
docker build -t gigaam-transcriber:cpu .
```

Run in PowerShell, using the existing model cache and a folder containing audio:

```powershell
docker run --rm --network none `
  --mount "type=bind,source=$env:USERPROFILE\.cache\gigaam,target=/app/models,readonly" `
  --mount "type=bind,source=C:\Audio,target=/data" `
  gigaam-transcriber:cpu /data/recording.wav --device cpu
```

The result is `C:\Audio\recording-transcript.txt`. Add `--no-timestamps`
for plain text. Replace `C:\Audio` with your audio folder. The model folder
must contain `v3_e2e_rnnt.ckpt` and `v3_e2e_rnnt_tokenizer.model`; alternatively,
mount the `models` folder from the unpacked Windows CPU release there.
The image includes dependencies and FFmpeg; model weights are mounted
separately and are not downloaded when using this offline command.
