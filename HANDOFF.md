# Handoff: state and findings

Last updated 2026-11-05 (session 4). The plan is in [docs/plans/01-onnx-runtime-rewrite.md](docs/plans/01-onnx-runtime-rewrite.md).

## Decisions (approved by the owner on 2026-11-04)

- Drop PyTorch from the shipped app. Run GigaAM on ONNX Runtime with the
  DirectML provider (any DX12 GPU) and CPU fallback, in one onedir build.
  PyTorch stays only as a developer tool for exporting checkpoints to ONNX.
- Release v0.2.0: one Windows zip (GUI + console CLI, RNNT and CTC bundled),
  updated Docker images. Speaker diarization is NOT part of it (owner: not now).
- Old builds in `dist/` may be deleted once the new build is verified.
- Commit and publish the release only after the owner has seen the new build work
  (owner confirmed in session 3).

## Session 4 (2026-11-05): B2 done (not adopted), B6 built, upload pending

Commits 0d7dd4a..2990463 on main, not pushed. Tests: 281 passed, 1 skipped
(parity), with the session 3 venv
`C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\740fa774-5b91-4234-b11a-c5b322975530\scratchpad\venv-app`.

**B2, fp16 compute on DirectML: not adopted.** `experiments/onnx_runtime/fp16_encoder.py`
converts the encoder explicitly: fp16 everywhere except the mel front-end (log of
1e-9 powers) and the frame-length arithmetic (fp16 is exact only to 2048). The
onnxconverter-common converter failed (left the graph's Cast(to=float) nodes,
type errors, then all-NaN output). RNNT, 7 files / 2 h of audio, encoder time:

| GPU | fp32 | fp16 | Text vs fp32 |
| --- | ---: | ---: | --- |
| RTX 4070 Laptop (DML device 0) | 42.6 s | 40.8 s | lecture identical; `2023 06 10 12 08 59.mp3` loses 10 of 2863 words ("Так, вторая группа.", dialogue dashes) |
| Radeon 780M iGPU (DML device 1) | 175 s | 107 s | same kind of differences |

Keeping Softmax and LayerNorm in fp32 did not help (still differs, and adds a diff
on the lecture). Only the iGPU would gain, and the text changes, so the app stays
fp32. Side finding: DML device 0 is the RTX on this laptop; the app does not pick
an adapter (DirectML's default).

**B6, downloads of extra models (code done, hosting not done).**
- Models: `multilingual_ctc` (220M, 845 MB) and `multilingual_large_ctc` (600M,
  2.2 GB), the two v0.1 offered. Char-level CTC (Latin, Cyrillic, Kazakh letters),
  lowercase, no punctuation. Checkpoints are float32 and NOT fp16-exact; lossy fp16
  storage changed 8 tokens on a Russian file, so they ship fp32. The 600M weights
  exceed the 2 GB protobuf and 2 GiB GitHub asset limits: `export_models.py` now puts
  weights above 1.8 GiB into `encoder.data1` / `encoder.data2` (external data, at most
  1.5 GiB each). v3_e2e_ctc re-exports byte for byte. Max |onnx - torch|: 2.5e-4 and 8.8e-4.
- Speed on DML (RTX): 220M like v3 (lecture 4.6 s); 600M 1.7x slower, load 9 s cold.
  On English audio both write Cyrillic transliteration (that file is out of domain).
- App: `gigaam_app/catalog.py` (keys RNNT, CTC, Multilingual, Multilingual-Large;
  sizes and SHA-256 of each file in code; v0.1 names as aliases),
  `gigaam_app/download.py` (staging `<folder>.partial`, SHA-256 per file, HTTP Range
  resume, 3 attempts, cancel, disk space check, rename when all pass),
  `paths.downloads_dir()` (`%LOCALAPPDATA%\GigaAmTranscriber\models`, `GIGAAM_DOWNLOADS`).
  CLI `--list-models`, `--download MODEL`; GUI asks before downloading, progress and
  cancel. Bug fixed on the way: v0.2.0 rejected v0.1 settings naming a multilingual model.
- Tested: `tests/test_download.py` (17 tests, local HTTP server: damaged, cut,
  resumed, cancelled, Range ignored, 404, too long, no space). GUI end to end in
  process with the Tk root withdrawn (never shown): large model cancelled at 312 MB,
  resumed with `Range: bytes=327155712-`, loaded; small model downloaded from
  "Распознать", transcribed a file. Docker `--download` is documented but not run.
- Hosting: catalog URLs point to release tag `models-1`
  (`https://github.com/bigflyy/GigaAmTranscriber/releases/download/models-1/<folder>.<file>`),
  which does not exist yet. The exported folders are in this session's scratchpad
  `export/` (3.1 GB):
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\28d81582-1145-4ab9-a6b4-42d9490289a5\scratchpad\export`.
  Upload: `tools/stage_model_assets.py OUT export/multilingual_ctc export/multilingual_large_ctc`
  then `gh release upload models-1 OUT/*`; its printed hashes match catalog.py.
  If the scratchpad is gone, re-export with the cuda-torch2 env (2 min); check the
  hashes still match catalog.py (export looked deterministic for v3, not checked for these).
- Open: B6.5 (owner approves hosting, upload, test real downloads), then a release
  (version bump, release notes, Windows build, Docker images).

## Release v0.2.0 (session 3, 2026-11-04): published

- Dev venv recreated (scratchpad `venv-app` of session 3); 261 passed, 1 skipped
  (the parity test, which needs `GIGAAM_PARITY_AUDIO` / `GIGAAM_PARITY_REFERENCE`).
- Rewrite committed in 9 commits (8c4135e..eba7650) and pushed to main.
- GitHub release v0.2.0 at eba7650, marked Latest:
  https://github.com/bigflyy/GigaAmTranscriber/releases/tag/v0.2.0
  Four assets uploaded; GitHub's SHA-256 digests match SHA256SUMS.txt, and a fresh
  download of all assets passed `sha256sum -c` (the first `gh release download` of the
  zip broke off with an HTTP/2 stream error; `curl -C -` resumed it).
- Workflow "Publish CPU and CUDA containers" run 41867784548 with v0.2.0: both jobs
  passed. Pushed `ghcr.io/bigflyy/gigaamtranscriber:v0.2.0-cpu` / `:cpu`
  (sha256:73cf43eb...) and `:v0.2.0-cuda` / `:cuda` (sha256:c615b94f...).
  The workflow smoke test runs `--version` and transcribes a 2 s silent file offline
  with RNNT and CTC: it proves the image starts and loads both models without network,
  but the encoder does not run on speech there. Real speech was checked only on the
  locally built CPU image (session 2). The CUDA image is still not GPU-tested.
- Remaining work: plan items B2 (fp16 on DirectML), B6 (downloads of extra models),
  and Stage E (speaker diarization, owner: not now).

## State of the rewrite (session 2, 2026-11-04)

Done and verified in session 2:

- Tests: `tests/test_decoders.py`, `test_outputs.py`, `test_config.py`, `test_cli.py`,
  `test_engine.py` (pipeline with fakes), `test_models.py` (real models, optional parity
  via `GIGAAM_PARITY_AUDIO` / `GIGAAM_PARITY_REFERENCE`). 261 passed; parity passes on
  DirectML and CPU.
- Windows build: `packaging/GigaAmTranscriber.spec` (two EXEs, one `_internal`),
  `packaging/README.txt`, `packaging/licenses/` (Silero, DirectML texts),
  `tools/build_windows.py` (checks, build, payload, licences, smoke tests, zip, SHA256SUMS),
  `tools/gui_smoke_test.py` (GUI EXE on a hidden desktop, PrintWindow capture, WM_CLOSE).
  Output: `build/app/GigaAmTranscriber/` and `build/release/`.
- Fixes found by testing the frozen build: PyInstaller took `tcl86t.dll` from
  `C:\ProgramData\miniconda3\Library\bin` on PATH (window crashed); the build now runs
  PyInstaller with a clean PATH and checks every DLL. The CLI failed on file names outside
  the console code page when output was redirected; fixed (`safe_console`). The first
  model load delayed the window to 3-5 s; now it starts 150 ms after the window (about 1 s).
- CLI expands wildcards itself (cmd.exe does not).
- `asr.py` calls `onnxruntime.preload_dlls()` before CUDA sessions (Docker CUDA image).
- Removed torch-era files: transcribe.py, gui.py, gui_help.py, app_config.py, model_catalog.py,
  build_release.py, prepare_release.py, benchmark.py, giga.py, release/, tests/test_desktop.py,
  requirements-cpu.txt, setup.py (upstream packaging that read requirements.txt),
  README_TRANSCRIBER.md (folded into README.md), debug files. `gigaam/` stays: the export
  tools and experiments use it.
- New requirements: `requirements.txt` (app), `requirements-build.txt`, `requirements-export.txt`.
- Docs rewritten: README.md, DOCKER.md, RELEASE_NOTES.md, BENCHMARK.md, RELEASE_TESTS.md,
  THIRD_PARTY_NOTICES.md, gigaam-config.example.json (version 2).
- Dockerfile: two stages, export with CPU torch in stage 1, final image has no torch;
  `ORT_VARIANT=cpu|cuda`. Workflow builds both and smoke-tests offline.
- `third_party/` (gitignored) holds `ffmpeg/FFmpeg-8.0.1-source.zip` and
  `v0.1.0/THIRD_PARTY_LICENSES.zip`, copied out of `dist/` with matching checksums.

- Final build verified (end of session 2): `build/release/` holds
  `GigaAmTranscriber-v0.2.0-windows-x64.zip` (917 MiB, SHA-256 b790348e...),
  `THIRD_PARTY_LICENSES.zip`, `FFmpeg-8.0.1-source.zip`, `SHA256SUMS.txt`. The zip was
  unpacked to a fresh folder and tested there: GUI on a hidden desktop transcribed the
  455 s lecture (window 1.6 s, text identical to v0.1), CLI on CPU and DirectML.
- Docker CPU image built locally (`gigaam-transcriber:cpu`, 2.81 GB): offline RNNT and CTC
  work, RNNT text identical to v0.1. The CUDA image is not built or GPU-tested locally.
  Docker Desktop pulled from PyPI at ~60 kB/s while the host got 1.9 MB/s; its only proxy
  is the built-in `http.docker.internal:3128` in "system" mode (Windows proxy is off). The
  owner chose to leave Docker Desktop settings as they are.
- `dist/` deleted (owner approved; v0.1.0 assets are all on the GitHub release).
Dev venv: scratchpad `venv-app` of session 3 (may be gone); recreate with
`uv venv venv-app --python C:\Users\User\.conda\envs\cuda-torch2\python.exe` and
`uv pip install -r requirements-build.txt`. Run the build with that venv's python.


## Measurements (2026-11-04, Ryzen 7 7840HS, RTX 4070 Laptop 8 GB)

Sample: `C:\Users\User\Downloads\research-2026.mp4`, 455 s, one speaker, 26 chunks.
"First file" = first transcription in a fresh process, including CUDA warm-up.

| Pipeline | Startup to ready | First file | Second file | Text vs reference |
| --- | ---: | ---: | ---: | --- |
| Old, torch CUDA (source, warm disk) | 14.5 s | 37.7 s | 21.6 s | reference uses CPU fp32 |
| Old, torch CPU 8 threads | 10.8 s | 40.4 s | - | reference |
| Old, onefile EXE CUDA / CPU (BENCHMARK.md) | 129 s / 26 s before the window appears | | | |
| ORT CUDA EP fp32 | 3.1 s | 4.0 s | 3.8 s | identical (932/932 words) |
| ORT DirectML fp32 | 2.0 s | 6.9 s | 5.0 s | identical |
| ORT CPU fp32, 8 threads | 2.0 s | 25 s | 25 s | identical |
| ORT CPU int8 (MatMul only), 8 threads | 1.1 s | 14.4 s | 17.4 s | 9 small diffs in 932 words (punctuation, hyphens) |

Where the old pipeline loses time, for the same file on CUDA:

- `import torch` 4-9 s; torch CUDA libraries are 3.9 GB, which forces the 3.7 GB EXE.
- Onefile EXE unpacks everything to %TEMP% on every launch: the 129 s / 26 s above.
- MD5 of the 449 MB checkpoint on every load (~1 s), then a pickle `torch.load`
  with `weights_only=False` (runs arbitrary code from a downloaded file).
- The GUI loads the model again for every file.
- Audio is decoded by ffmpeg twice (`vad_utils.segment_audio_file`).
- Silero VAD in torch, one thread, about 14,000 sequential calls: 8-10 s.
  ORT with the audio cut into parallel rows: 1.3 s, same boundaries except one 0.1 s shift.
- RNNT greedy decoding: 13.5 s on GPU, slower than the encoder. It runs the
  prediction LSTM on every frame although its output only changes after an
  emitted token, recomputes the encoder projection per frame, and syncs the GPU
  with `.item()` per step. A numpy version with both fixes: 0.9 s.
- No batching; the first CUDA run spends ~11 s warming kernels for new shapes.

## Diarization findings (sherpa-onnx 2.0.1, CPU, 8 threads)

- Pipeline: pyannote segmentation-3.0 ONNX (6 MB) + speaker embedding ONNX + clustering.
- Speed about 10x realtime on CPU (23 min file in ~145 s). This is slower than ASR on GPU.
- Single-speaker lecture: 1 speaker found (correct).
- 23 min multi-speaker file `2023 06 10 10 34 50.mp3`, WeSpeaker ResNet34:
  threshold 0.5 gives 19 speakers, 0.8 gives 4. True count unknown.
- 3D-Speaker ERes2Net base: 88 speakers at 0.8, unusable as configured.
- Conclusion: works, but the clustering threshold needs tuning on a labelled
  recording, and a "number of speakers" option is needed for when the user knows it.

## Files and storage

- Prototype code: `experiments/onnx_runtime/` (see its README).
- Session 1 scratchpad (reference JSON `ref_torch_cpu.json`, `short.m4a`):
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\1b972041-92b6-47ff-9690-27ace02d4adf\scratchpad`.
  Session 2 copies are in its scratchpad `ref/`.
- Storage rule from the owner: up to ~3 GB of new files without asking. `dist/` is deleted;
  the FFmpeg source and the old licence zip are in `third_party/` (gitignored).
