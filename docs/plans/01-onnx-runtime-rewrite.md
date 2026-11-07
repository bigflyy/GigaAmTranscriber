# Rewrite on ONNX Runtime, then speaker diarization

Findings and measurements behind this plan are in [HANDOFF.md](../../HANDOFF.md).

### Stage A: Measure and decide

- [x] **A1** Profile the old pipeline stage by stage (startup, VAD, encoder, decoder)
- [x] **A2** Export GigaAM v3 RNNT to ONNX with the mel front-end inside the graph
- [x] **A3** Torch-free prototype: ORT encoder, numpy RNNT decoder, batched Silero ORT VAD
- [x] **A4** Benchmark CPU, CUDA and DirectML providers; check text parity with torch
- [x] **A5** Try sherpa-onnx diarization on a single-speaker and a multi-speaker file
- [x] **A6** Owner approves the direction (ORT + DirectML, no torch at run time)

### Stage B: Engine (new package, no torch import)

- [x] **B1** Export tool `tools/export_models.py`: RNNT and CTC, weights stored fp16 losslessly, vocab, head, model.json with SHA-256
- [x] **B2** Try fp16 compute for DirectML (speed); keep only if text stays identical (tried: text changed, app stays fp32)
- [x] **B3** Audio decode once (ffmpeg), streaming Silero VAD (`ChunkFinder`, exact vs batch port), chunk grouping
- [x] **B4** Encoder runner: provider choice (DirectML, CPU), batching on GPU, batch 1 on CPU
- [x] **B5** RNNT and CTC greedy decoders that also return token frame times (word timestamps)
- [x] **B6** Model store: bundled models size-checked on load; downloads of extra models with SHA-256 (ready, no model uses it yet)
  - [x] **B6.1** Export multilingual CTC 220M and 600M (fp32; the 600M weights split into data parts under 2 GiB); check text (5-26% of words differ from RNNT on Russian)
  - [x] **B6.2** Catalog in the app code (files, sizes, SHA-256) and a verified, resumable, cancellable downloader into a per-user folder
  - [x] **B6.3** Engine, settings (v0.1 model labels accepted), CLI `--list-models` / `--download`, GUI download prompt with progress
  - [x] **B6.4** Tests with a local HTTP server: good, damaged, truncated, resumed, cancelled downloads
  - [x] **B6.5** Hosting decision: the owner dropped the GigaAM multilingual models (worse than RNNT, English comes out transliterated); nothing hosted, v0.1 settings that chose them load with RNNT
  - [x] **B6.6** Docs: README, DOCKER.md (release notes are written with the next release)
- [x] **B7** Automated tests: VAD, decoders, outputs, config, CLI, pipeline with fakes, real-model tests and an optional parity test
- [x] **B8** Overlap speech search with recognition (3-thread pipeline) and Silero in an ONNX Scan loop (`tools/make_silero_scan.py`)
- [ ] **B9** int8 encoder for CPU-only machines as an optional download (session 1: 25 s -> 14 s on the lecture, 9 small diffs in 932 words); measure the text on more files first, offer it only on CPU

### Stage C: Application

- [x] **C1** CLI on the engine; outputs TXT, timestamped TXT, SRT, JSON
- [x] **C2** GUI: start loading the model at launch in the background, keep it loaded between files
- [x] **C3** GUI settings cut to model, device, threads, output formats; VAD knobs in the config file only
- [x] **C4** Remove torch-era code paths, `giga.py`, debug files, the frozen `requirements.txt`
- [x] **C5** Nicer window design (owner asked): first try a modern ttk theme such as sv-ttk (Windows 11 look, light and dark), spacing and a clearer layout; a different toolkit only if that is not enough. Check the result with screenshots from a hidden desktop (sv-ttk tried; the owner found it too close to the old window; continues in [02-webview-window.md](02-webview-window.md))

### Stage D: Packaging

- [x] **D1** PyInstaller onedir build, models as separate files beside the app; measure size and startup
- [x] **D2** Release as one zip; drop the split CUDA parts and join scripts
- [x] **D3** Docker image on ORT CPU (optional onnxruntime-gpu image for Linux; CPU image verified, CUDA image GPU use not verified)
- [x] **D4** After the new build is verified, delete `dist/` (9.2 GB; owner approved, FFmpeg source and licence zip kept in `third_party/`)

### Stage R: Release v0.2.0

- [x] **R1** Owner confirms the new build works; recreate the dev venv and run the test suite
- [x] **R2** Commit the rewrite in small steps (export tools, engine, CLI and GUI, requirements, build, removal, Docker, docs, plan)
- [x] **R3** Push to main
- [x] **R4** Publish the v0.2.0 GitHub release with the four assets; check the uploaded checksums
- [x] **R5** Run "Publish CPU and CUDA containers" with v0.2.0; check both images pass

### Stage F: English and other languages (before Stage E)

Whisper moved to its own plan, [04-whisper.md](04-whisper.md) (2026-11-07); Parakeet and Qwen3-ASR stay here.

- [ ] **F1** Get labelled test audio: Russian and English, with reference text (public sets such as FLEURS or LibriSpeech, plus own files)
- [ ] **F2** Compare candidates on WER and speed: NVIDIA Parakeet TDT 0.6B v3 (25 European languages incl. Russian, a transducer like RNNT), Whisper large-v3-turbo (99 languages, slower), Qwen3-ASR (top of the Open ASR leaderboard, 1.7B, LLM decoder)
- [ ] **F3** Export the chosen model to ONNX with a numpy decoder; check DirectML and CPU
- [ ] **F4** Offer it as a download through the catalog; language or model choice in the window and the CLI

### Stage E: Speaker diarization

- [ ] **E1** Get a labelled multi-speaker recording (known speakers and turns) to score against
- [ ] **E2** Compare sherpa-onnx with a lighter own pipeline (embeddings per VAD region on the same ORT provider)
- [ ] **E3** Assign words to speakers by word timestamps; output "Speaker N:" turns
- [ ] **E4** Options: automatic speaker count or a fixed number
- [ ] **E5** Named speakers: voice library from short samples, matched by embedding similarity
