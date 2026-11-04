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
- [ ] **B2** Try fp16 compute for DirectML (speed); keep only if text stays identical
- [x] **B3** Audio decode once (ffmpeg), streaming Silero VAD (`ChunkFinder`, exact vs batch port), chunk grouping
- [x] **B4** Encoder runner: provider choice (DirectML, CPU), batching on GPU, batch 1 on CPU
- [x] **B5** RNNT and CTC greedy decoders that also return token frame times (word timestamps)
- [ ] **B6** Model store: bundled models size-checked on load (done); downloads of extra models with SHA-256 (not done)
- [x] **B7** Automated tests: VAD, decoders, outputs, config, CLI, pipeline with fakes, real-model tests and an optional parity test
- [x] **B8** Overlap speech search with recognition (3-thread pipeline) and Silero in an ONNX Scan loop (`tools/make_silero_scan.py`)

### Stage C: Application

- [x] **C1** CLI on the engine; outputs TXT, timestamped TXT, SRT, JSON
- [x] **C2** GUI: start loading the model at launch in the background, keep it loaded between files
- [x] **C3** GUI settings cut to model, device, threads, output formats; VAD knobs in the config file only
- [x] **C4** Remove torch-era code paths, `giga.py`, debug files, the frozen `requirements.txt`

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

### Stage E: Speaker diarization

- [ ] **E1** Get a labelled multi-speaker recording (known speakers and turns) to score against
- [ ] **E2** Compare sherpa-onnx with a lighter own pipeline (embeddings per VAD region on the same ORT provider)
- [ ] **E3** Assign words to speakers by word timestamps; output "Speaker N:" turns
- [ ] **E4** Options: automatic speaker count or a fixed number
- [ ] **E5** Named speakers: voice library from short samples, matched by embedding similarity
