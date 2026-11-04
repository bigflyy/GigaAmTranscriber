# Speed measurements

Machine: AMD Ryzen 7 7840HS (8 cores, 16 logical processors), 64 GB RAM,
NVIDIA GeForce RTX 4070 Laptop GPU (8 GB), Windows 11. These numbers describe
this machine and these samples, not a guarantee. Other programs were running;
repeated runs vary by about 20 %.

Sample: a 455 s (7.5 min) lecture, one speaker, MP4; Silero finds 26 chunks.
"First file" is the first transcription in a fresh process, including GPU warm-up.

## v0.2 against v0.1, 2026-11-04 (from source)

| Pipeline | Model ready after start | First file | Second file | Text against the v0.1 CPU reference |
| --- | ---: | ---: | ---: | --- |
| v0.1, PyTorch CUDA | 14.5 s | 37.7 s | 21.6 s | (CUDA fp16) |
| v0.1, PyTorch CPU, 8 threads | 10.8 s | 40.4 s | - | reference |
| v0.2, ONNX Runtime DirectML | 2.0 s | 6.9 s | 5.0 s | identical, 932 of 932 words |
| v0.2, ONNX Runtime CPU, 8 threads | 2.0 s | 25 s | 25 s | identical |
| ONNX Runtime CUDA (not shipped on Windows) | 3.1 s | 4.0 s | 3.8 s | identical |
| ONNX Runtime CPU int8 (not shipped) | 1.1 s | 14.4 s | 17.4 s | 9 small differences in 932 words |

v0.1 as released was a single-file EXE that unpacked itself on every start:
27 s (CPU) and 106-129 s (CUDA) before the window appeared.

## Where v0.1 lost time

For the same file on CUDA:

- `import torch` took 4-9 s, and the CUDA libraries (3.9 GB) made the 3.7 GB EXE.
- The single-file EXE unpacked everything to `%TEMP%` on every launch.
- Each load computed the MD5 of the 449 MB checkpoint (about 1 s) and unpickled it.
- The window loaded the model again for every file.
- ffmpeg decoded the audio twice.
- Silero VAD made about 14,000 single-thread PyTorch calls: 8-10 s. In v0.2 it is
  one ONNX loop over blocks of 1024 windows (about 3.4 times faster) and runs while
  recognition proceeds.
- Greedy RNNT decoding took 13.5 s on the GPU, more than the encoder: it ran the
  prediction LSTM on every frame, although its output only changes after a token,
  and waited for the GPU after every step. The numpy decoder in v0.2 takes 0.9 s.

## Choices measured along the way

- Silero has to run in order over the whole file. Cutting the file into rows that
  run in parallel was 6 times faster but moved up to 60 % of the speech regions
  on noisy audio.
- Chunk times are rounded to 0.1 s as silero-vad reports them; without the
  rounding about 1 % of the words change.
- Weights are stored as float16 in the ONNX files (lossless for these
  checkpoints, half the download); ONNX Runtime then needs about 1 s more to
  open the model.
- Batching chunks helps on the GPU (up to 8 chunks, 200 s of audio per call)
  and not on the CPU, where chunks run one by one.

## Windows build v0.2.0

Measured 2026-11-04 with the release folder (`gigaam-cli.exe`, PATH without
Python or FFmpeg), same 455 s sample given twice in one run, 8 CPU threads:

| Model and device | Model load | First file | Second file |
| --- | ---: | ---: | ---: |
| RNNT, DirectML | 3.3 s | 6.0 s (76x realtime) | 4.8 s (95x) |
| RNNT, CPU | 2.8 s | 23.4 s (19x) | 23.9 s (19x) |
| CTC, DirectML | 4.7 s | 5.2 s (87x) | 4.4 s (103x) |
| CTC, CPU | 2.5 s | 24.1 s (19x) | 23.5 s (19x) |

The whole GPU run, from starting the process to exit after both files, took 15.5 s.
`GigaAmTranscriber.exe` shows its window after about 1 s (three runs: 0.85-1.07 s,
measured on a hidden desktop by `tools/gui_smoke_test.py`) and loads the model
after that.

| Size | |
| --- | ---: |
| Release zip | 917 MiB |
| Unpacked folder | 1184 MiB |
| of which models (RNNT, CTC, Silero) | 857 MiB |
| of which `ffmpeg.exe` | 201 MiB |
| of which program (`_internal` and both EXEs) | 125 MiB |

v0.1 for comparison: CPU EXE 0.99 GiB, CUDA EXE 3.51 GiB (two download parts).

## Reproduce

```powershell
gigaam-cli.exe lecture.mp4 lecture.mp4 --device gpu    # first and second file, one process
gigaam-cli.exe lecture.mp4 --device cpu --threads 8
```

The first output line gives the model load time, each file line the
transcription time and speed.
