# Whisper as a second model

Owner's idea (docs/IDEAS.md, Models, 2026-11-06): an optimized Whisper variant that can be turned
on in the app, "one of the most important tasks probably". Owner's order (2026-11-06): Markdown
export (done), then this plan, then plan 03 Stage A.

This plan takes over plan 01 Stage F for Whisper; Parakeet TDT and Qwen3-ASR stay in plan 01
Stage F. Plan 03 C1 (another model's reading of a selected part) waits for Stage B here.

What is known before testing (HANDOFF.md, session 9): on Russian GigaAM v3 is usually more
accurate than Whisper; Whisper's gain is other languages (99) and a second, independent reading.
The app runs GigaAM on ONNX Runtime with DirectML (any DX12 GPU) and the CPU, cuts audio with
Silero VAD into chunks of up to about 25 s (Whisper's window is 30 s), and downloads extra models
through gigaam_app/catalog.py and download.py (SHA-256 per file, resumable). faster-whisper
(CTranslate2) is out: NVIDIA only and about 1 GB more DLLs.

### Stage A: Test runtimes and choose

- [ ] **A1** Test files and GigaAM reference: the 455 s lecture (research-2026.mp4) and the 45 min call (2023 06 10 12 08 59.mp3, copied out of Downloads); GigaAM RNNT text and the VAD chunks of both
- [ ] **A2** large-v3-turbo on ONNX Runtime DirectML: onnx-community export (fp16, and q4f16 if DirectML runs it), numpy mel front-end, greedy decoding with the KV cache, fed the app's VAD chunks; speed on the RTX 4070 and the Radeon 780M, and on the CPU
- [ ] **A3** large-v3-turbo on whisper.cpp with Vulkan: build whisper.cpp with the Vulkan backend (no Windows Vulkan binary is published), ggml q5_0 model; speed on both GPUs and the CPU
- [ ] **A4** Compare: words that differ from GigaAM (case and punctuation ignored), samples of the differences, repeated or invented text, speed, download size, size added to the app, word timestamps
- [ ] **A5** Results page for the owner; the owner chooses the runtime and the model size

### Stage B: Whisper in the app

- [ ] **B1** Engine: Whisper model behind the same Transcriber interface (VAD chunks in, segments with word times out); language: automatic or chosen
- [ ] **B2** Catalog entry and download (files, sizes, SHA-256 in code; a release asset or the model's own hosting, owner decides)
- [ ] **B3** Model switch in Settings and `--model` in the CLI; the download prompt as for any extra model; language choice in Settings and `--language`
- [ ] **B4** Tests (decoder with a fake model, real model on a short file) and window_check.py steps
- [ ] **B5** Docs and licences (Whisper weights MIT; whisper.cpp MIT if chosen)

### Stage C: Build and release

- [ ] **C1** Windows and Linux builds with Whisper; smoke tests transcribe a short file with it
- [ ] **C2** Release notes, the owner tries the build, release
