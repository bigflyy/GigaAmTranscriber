# GigaAM Transcriber

This repo contains a snapshot of a modified GigaAM package using Silero VAD.
The original `giga.py` is kept as the baseline. `transcribe.py` is the
standalone launcher; it accepts a file or opens a file picker when run without
arguments. The output is a UTF-8 `*.transcript.txt` file beside the input.

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

## Build inputs and Git

`build_release.py` reads `v3_e2e_rnnt.ckpt` and its tokenizer from the user's
`~/.cache/gigaam` and locates `ffmpeg.exe` on `PATH`. Run the original script
once to populate the GigaAM cache if the files are missing. Models, temporary
transcripts, build directories, and release binaries are excluded from Git.

The imported `requirements.txt` and `setup.py` were retained from the source
snapshot; they include packages unrelated to this transcriber. Use
`requirements-cpu.txt` for the CPU build.
