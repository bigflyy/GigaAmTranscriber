# GigaAM Transcriber

This repo contains a snapshot of a modified GigaAM package using Silero VAD.
The original `giga.py` is kept as the baseline. `transcribe.py` is the
standalone launcher. Run without arguments (or double-click the EXE) to open
the minimal Russian GUI. Choose a file (**Выбрать файл…**) and click
**Распознать**. Two UTF-8 TXT files are saved beside the input:

- `name-transcript.txt`: plain text.
- `name-transcript-timestamps.txt`: the same text with chunk timestamps.

Recognized text appears after each completed speech chunk. Cancellation also
saves both versions of the partial result. Cancelling before any chunks have
been recognized leaves existing output files untouched.

**Включить таймкоды** is off by default (a saved config can override it).
It shows or hides timestamps immediately, including during
transcription. It changes only the preview; both file versions are always
saved. The original chunk boundaries remain in memory until the next file or
closing the app, so toggling timestamps back on restores them. The CLI also
saves both files. `-o report.txt` produces `report.txt` and
`report-timestamps.txt`. The old `--no-timestamps` flag is accepted for
compatibility; it no longer changes which versions are saved.

The v0.1.0 Windows release and current Docker images include this behavior.

**Настройки** is collapsed initially. It contains RNNT/CTC model
selection, device selection, Silero speech/silence/padding settings, and chunk
lengths. Technical labels inside the panel are in English; the main interface
is in Russian. **Reset defaults** restores the built-in model/VAD settings and
the current default of **4 GigaAM CPU threads**. Silero 6.2.1 fixes
the analysis window to 512 samples at 16 kHz; its old window-size argument
has no effect, so this value is shown read-only.

File transcription combines VAD regions while their total span fits
**Preferred max chunk**. The former **Preferred min chunk** early-stop rule
has been removed. For example, adjacent 16-second and 4-second regions now
form one 20-second chunk. Existing configs containing `min_duration` still
load; that key is ignored and omitted on the next save. The old CLI
`--min-duration` option is also accepted but ignored. **VAD max speech**,
**Preferred max chunk**, and **Hard chunk limit** now all default to **25 seconds**.
The tiny-chunk cutoff remains 0.2 seconds. An existing saved config still takes
precedence; **Reset defaults** applies these defaults in the GUI, and
**Save as default** persists them.

Hover over a setting label or input for detailed English help. Each hint
explains the purpose, units, default, examples and tradeoffs. Click a label
marked **(?)** to keep its description open in a scrollable window, or use
**Parameter help** to read the complete guide. The guide explains the VAD
stage, chunk grouping, soft versus hard limits, CPU threads and model/device
selection. Help is available while transcription is running.

**GigaAM CPU threads** controls PyTorch's intra-operation CPU thread count
for GigaAM recognition. The default is 4; 1 restores the original single-thread
behavior. Silero runs with one thread independently, then the selected count
is applied to GigaAM when using CPU. CUDA inference ignores this CPU setting.
The previous PyTorch thread count is restored after transcription, including
on errors. This changes a process-wide PyTorch setting; the desktop app runs
one transcription at a time. It does not reserve a fixed set of CPU cores.

On the local Ryzen 7 7840HS, 8 threads were faster than 4, while 16 were slower
than 8. More threads are not always faster; see [measurements](BENCHMARK.md).
The CLI and both Docker images accept, for example:

```powershell
conda run -n gigaam-cpu python transcribe.py recording.wav --device cpu --cpu-threads 8
```

Loading and speech detection use an activity indicator. Transcription reports
`100 × completed speech segments / total speech segments` after Silero has
found and grouped speech. This is a chunk count, not a time estimate: chunks
can take different amounts of time. The interface stays responsive while
the worker runs. The one-file EXE extracts before the window can appear;
the folder release starts faster.

After the first completed chunk, **Осталось примерно** shows a countdown.
At each completion the estimate is recalculated as the mean elapsed time per
completed chunk multiplied by the remaining chunk count. Timing starts after
model loading and VAD; those phases have no ETA. Unequal chunk lengths and
initial warm-up can change the estimate. If a chunk takes longer than expected,
the app displays **Уточняем оставшееся время…** until the next update.

## Saved GUI settings

The GUI loads **gigaam-config.json** next to the EXE on startup. With Python
source, it looks beside `gui.py`. The location is independent of the working
directory and of a one-file EXE's temporary extraction directory. Without a
config, the built-in defaults apply. Both Windows release formats support it.

Open **Настройки** to use:

- **Save as default**: save current settings next to the EXE for future launches.
- **Export config…**: save a named preset to any folder.
- **Import config…**: apply a preset now; use **Save as default** to keep it for
  future launches.

The file contains model, device, CPU threads, all editable VAD/chunk settings,
and the timestamp checkbox. It contains no audio paths or transcripts.
Changing fields or exiting does not overwrite a saved config. **Reset defaults**
resets the model/VAD/thread controls for this session; saving afterward replaces
the stored defaults. Importing the timestamp preference updates the current
preview only, just like toggling the checkbox.

Files are UTF-8 JSON. See [gigaam-config.example.json](gigaam-config.example.json).
Missing keys use built-in defaults; unknown keys, invalid values, and unsupported
versions are rejected without partially applying settings. A broken startup
config displays an error and leaves the app usable with built-in defaults.
If the EXE folder is read-only, export elsewhere and import that file, or move
the portable app to a writable folder. Config loading applies to the GUI;
CLI/Docker settings continue to use explicit command-line flags.

## Run from the existing CUDA environment

### Multilingual models (source testing)

The source app's **Model** selector offers four transcription models:

| GUI option | CLI name | Output / download |
| --- | --- | --- |
| RNNT | `v3_e2e_rnnt` | Russian E2E, with punctuation; existing default |
| CTC | `v3_e2e_ctc` | Russian E2E, with punctuation |
| Multilingual CTC (220M) | `multilingual_ctc` | Lowercase text; about 883 MB checkpoint |
| Multilingual CTC Large (600M) | `multilingual_large_ctc` | Lowercase text; about 2.34 GB checkpoint |

Both multilingual models support Russian, English, Kazakh, Kyrgyz and Uzbek
with a shared alphabet and no language selector. Mixed-language text is
possible within a chunk, but accuracy needs evaluation on your recordings.
They do not produce normal sentence punctuation, uppercase letters or digits.
The SSL models are training backbones without transcription decoders and
are not included in this selector. See the
[official model card](https://huggingface.co/ai-sage/GigaAM-Multilingual).

Open the current GUI from source:

```powershell
conda run --no-capture-output -n cuda-torch2 python transcribe.py
```

Or start with the smaller model on CPU:

```powershell
conda run --no-capture-output -n gigaam-cpu python transcribe.py recording.wav --model multilingual_ctc --device cpu
```

The first use downloads a missing model into `%USERPROFILE%\.cache\gigaam`;
later runs work offline. Large downloads only when selected. Loading/downloading
uses the activity indicator and cancellation takes effect after that stage.
Config import/export supports all four model choices. Silero, chunk limits,
streamed partial results, cancellation, and both TXT exports use the same pipeline.

This addition is available in source; the v0.1.0 EXEs and Docker images still
offer the two Russian models. No rebuild is required to test the source GUI.
For a later build, `build_release.py --models` accepts any of the four CLI
names. By default it still bundles the two Russian models; optional models
download when first selected. Multilingual checkpoints contain their alphabet
and require no separate tokenizer file.

### Launch with the existing setup

```powershell
conda run -n cuda-torch2 python transcribe.py "C:\path\to\audio.mp4"
```

`transcribe.py --help` shows normal use. `transcribe.py --advanced-help` shows
the optional model, device, CPU thread count, segmentation and Silero VAD
parameters. The three duration limits now default to 25 seconds, and GigaAM
CPU inference defaults to 4 threads. Other VAD defaults retain the original
modified package's values. For example:

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
conda run -n gigaam-cpu python -c "import gigaam; gigaam.load_model('v3_e2e_rnnt', device='cpu'); gigaam.load_model('v3_e2e_ctc', device='cpu')"
conda run -n gigaam-cpu python build_release.py cpu all
```

Build `onedir` alone during troubleshooting:

```powershell
conda run -n gigaam-cpu python build_release.py cpu onedir
```

The release directories are `dist/cpu/onedir/GigaAmTranscriber/` and
`dist/cpu/onefile/GigaAmTranscriber.exe`. The one-folder directory can be
zipped and unpacked on another Windows computer. The build recipe now includes
both `v3_e2e_rnnt` and `v3_e2e_ctc`, their tokenizers, Silero data, and
`ffmpeg.exe` in both formats. Both model choices will work offline. RNNT stays
the default. Cache both models before building (the command above downloads
only missing files). CTC adds approximately **422 MiB of uncompressed model
files**; the final single-EXE size increase depends on compression.

The v0.1.0 CPU and CUDA releases bundle both models. Older EXEs created before
this release may include RNNT only.

The older Russian GUI without the remaining-time estimate also exists at
`dist/cpu/onefile-ru/GigaAmTranscriber.exe`. Use the normal `onedir` / `onefile`
paths for the latest release. Close running copies before rebuilding, or
pass `--output-root dist/new-release` to write both formats to a new location.

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

`build_release.py` reads both `v3_e2e_rnnt` and `v3_e2e_ctc` checkpoints and
tokenizers from the user's `~/.cache/gigaam` and locates `ffmpeg.exe` on `PATH`.
Run the two-model caching command above if the files are missing. Models, temporary
transcripts, build directories, and release binaries are excluded from Git.

The imported `requirements.txt` and `setup.py` were retained from the source
snapshot; they include packages unrelated to this transcriber. Use
`requirements-cpu.txt` for the CPU build.

The current build script bundles a Gyan FFmpeg 8.0.1 full build, licensed as
GPLv3. See [third-party notices and source links](THIRD_PARTY_NOTICES.md).
Generated release files are kept out of Git.

## Docker: CPU command-line version

For published CPU/CUDA images and setup commands, see **[DOCKER.md](DOCKER.md)**.

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

After rebuilding from current source, results are `C:\Audio\recording-transcript.txt`
and `C:\Audio\recording-transcript-timestamps.txt`. Replace `C:\Audio` with your audio folder. The model folder
must contain `v3_e2e_rnnt.ckpt` and `v3_e2e_rnnt_tokenizer.model`; alternatively,
mount the `models` folder from the unpacked Windows CPU release there.
The image includes dependencies and FFmpeg; model weights are mounted
separately and are not downloaded when using this offline command.

## Docker: NVIDIA GPU command-line version

Docker Desktop must be running. The container processes one file and exits;
there is no background application server or web interface to start.
On Windows, GPU containers require Docker Desktop's WSL 2 backend and a
compatible NVIDIA driver; see the official
[Docker GPU setup instructions](https://docs.docker.com/desktop/features/gpu/).
On Linux, configure the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

Build from this repository:

```powershell
docker build --build-arg TORCH_VARIANT=cu124 -t gigaam-transcriber:cuda .
```

The same Dockerfile defaults to CPU; `TORCH_VARIANT=cu124` installs the
[official PyTorch 2.5.1 CUDA 12.4 wheels](https://docs.pytorch.org/get-started/previous-versions/).
CUDA dependencies are included in the image; the NVIDIA driver comes from
the host. GPU builds download considerably more than CPU builds.

Run in PowerShell:

```powershell
docker run --rm --gpus all --network none `
  --mount "type=bind,source=$env:USERPROFILE\.cache\gigaam,target=/app/models,readonly" `
  --mount "type=bind,source=C:\Audio,target=/data" `
  gigaam-transcriber:cuda /data/recording.wav --device cuda
```

Replace the audio folder and filename. After rebuilding from current source,
results are `C:\Audio\recording-transcript.txt` and
`C:\Audio\recording-transcript-timestamps.txt`.
As in the CPU example, the RNNT checkpoint and tokenizer must be present
in the mounted model folder. Networking is disabled in this example,
so downloading an uncached CTC model requires a different run command.

`--gpus all` exposes the GPU to the container. `--device cuda` makes the
application report an error if CUDA is unavailable instead of silently
using CPU. To use this larger image on CPU, omit `--gpus all` and pass
`--device cpu`. Image tags here are local build outputs, not published
Docker Hub images; build them on each machine or transfer them with
`docker save` / `docker load` along with the separate model files.
