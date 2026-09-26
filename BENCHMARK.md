# Local build and speed measurements

Measured on 2026-09-26, Windows, AMD Ryzen 7 7840HS (8 cores / 16 logical
processors), NVIDIA GeForce RTX 4070 Laptop GPU (8 GiB), driver 581.29.
These measurements describe this machine and sample, not a performance guarantee.

## Release sizes and startup

| Release | Folder size | Single EXE size | Folder GUI startup | Single EXE GUI startup |
| --- | ---: | ---: | ---: | ---: |
| CPU (Russian GUI with ETA) | 1.02 GiB | 626.43 MiB | 2.45 s | 26.11 s |
| CUDA with CPU fallback | 4.99 GiB | 3.13 GiB | 2.09 s | 129.39 s |

Sizes include the RNNT checkpoint, tokenizer, Silero data, FFmpeg, Python,
and bundled dependencies. Startup checks were single local runs with a
minimal Windows PATH. The harness waits one extra second after detecting
the window to capture it, so the figures include that second. Model loading
starts when **Transcribe** is clicked and is excluded from GUI startup.
The single EXE extracts on every launch and needs temporary disk space.
Use the folder version for regular use; copy the entire folder, including
`_internal`. Python and Conda are not needed by the recipient.

## CPU versus GPU

`x realtime = audio duration / transcription time`: higher is faster.
All runs used the same 60-second, mono 16 kHz WAV, RNNT model, and unchanged
Silero/chunk settings. Silero produced five transcription chunks.

| Environment / device | Model load | First run | Second run |
| --- | ---: | ---: | ---: |
| cuda-torch2 / CPU, PyTorch 2.12.1+cu126 | 1.611 s | 8.823 s / 6.80x | 8.690 s / 6.90x |
| cuda-torch2 / GPU, PyTorch 2.12.1+cu126 | 1.879 s | 3.247 s / 18.48x | 1.704 s / 35.20x |
| gigaam-cpu / CPU, PyTorch 2.5.1+cpu | 1.597 s | 9.531 s / 6.30x | 9.452 s / 6.35x |

In the same environment, the GPU was about **5.1 times faster** on the
second run and **2.7 times faster** on the first. CPU inference uses FP32;
the GPU encoder uses FP16, matching the existing loader defaults.

Transcription timing includes audio decoding, Silero VAD, and GigaAM
inference. It excludes Python imports, model loading, EXE extraction,
GUI work, and transcript file writing. The same model instance is reused
for both runs; the second run benefits from initialization and caches.
The GUI currently loads GigaAM for each file, so allow model loading time
in addition to these inference figures. CUDA was synchronized around timing.

Silero 6.2.1 calls `torch.set_num_threads(1)` on import in both environments.
That existing behavior was preserved. These results therefore do not
represent tuned multicore CPU performance. Builds and smoke tests had
finished before the benchmark; each device benchmark ran sequentially.

Reproduce with your own PCM WAV:

```powershell
conda run -n cuda-torch2 python benchmark.py recording.wav --device cpu --runs 2
conda run -n cuda-torch2 python benchmark.py recording.wav --device cuda --runs 2
conda run -n gigaam-cpu python benchmark.py recording.wav --device cpu --runs 2
```

The private audio is excluded from Git. Sample SHA-256:
`13c3a08f25177f9999a5af90df31a2a73fa0641b79f34a3a2b97723d4f99d80f`.

## Verification scope

- Source GUI: file input, initially hidden settings, original defaults,
  actual CPU transcription, completion status, saved transcript, and 100% progress.
- All four packaged variants: window opens and closes with a minimal Windows PATH.
- CPU single EXE: actual transcription using bundled assets.
- CUDA folder: actual GPU transcription and forced CPU fallback.
- These transcription checks matched the source test transcript byte for byte.
- Default and expanded settings layouts were visually inspected.
- Russian GUI update: actual 60-second CPU transcription showed partial results
  before completion; toggling timestamps changed the view and exported text,
  and toggling back restored the original boundaries without loss.
- Updated CPU folder EXE: default `-transcript.txt` naming and plain-text
  export matched the reference. Both updated CPU packages passed GUI startup.
- Remaining-time update: real CPU transcription displayed an ETA after the
  first chunk and cleared it on completion. The layout was visually checked;
  both CPU package formats were rebuilt and passed GUI startup again.

CUDA artifacts refer to the earlier English GUI build. Further CUDA rebuilds
were deferred at the user's request; the Russian interface and incremental
text display are released for CPU first. The latest CPU single EXE, including
the remaining-time estimate, is in `dist/cpu/onefile/`. The `onefile-ru`
directory contains the earlier build without ETA.

The Linux CPU Docker image was also built and tested with a mounted model
cache and networking disabled. Its plain-text output matched the source
sample. This Docker check was functional, not a speed benchmark.

The CUDA Docker image (`gigaam-transcriber:cuda`, PyTorch 2.5.1+cu124) was
built and tested with `--gpus all --device cuda` on the RTX 4070 Laptop GPU.
It transcribed the sample offline using the mounted RNNT model cache;
its plain-text output matched the CPU reference. The same image also
passed with `--device cpu` and no GPU exposed. Docker reported image sizes
of 9.46 GB for CUDA and 2.05 GB for CPU; the separately mounted model weights
are excluded. These are functional checks, not Docker throughput benchmarks.

Testing was performed on the build computer, not a separate clean Windows
installation. CTC selection is implemented but its model was not downloaded
or benchmarked; RNNT is bundled and works offline. CUDA single-EXE testing
covered extraction and GUI startup; inference was checked in its folder build.
