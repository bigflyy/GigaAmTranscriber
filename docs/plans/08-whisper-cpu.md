# Faster suggestion search on the CPU

Owner's idea (docs/IDEAS.md, Models, 2026-11-09): the suggestion search is slow when Whisper runs on
the CPU. Owner 2026-11-10: "you didnt check the faster whisper variant? and maybe others?", then
"maybe you research and not guess?", and after the published numbers: compare the runtimes on the
owner's files ("1. yes").

What is known (IDEAS.md, HANDOFF.md sessions 10 and 21): whisper.cpp 1.9.5 q5_0 on 8 CPU threads
took 228 s for the 455 s lecture; every doubtful line (87-91% of lines, 14-17 s on average) is padded
to Whisper's 30 s window. Published numbers (small model, i7-12700K, 8 threads, beam 5): whisper.cpp
fp32 2m05s, whisper.cpp OpenVINO 1m45s, faster-whisper int8 1m42s, faster-whisper int8 batch 8 51s.
Parakeet TDT 0.6B v3 int8 on sherpa-onnx: RTF 0.18-0.20 on 4 threads, Russian FLEURS 5.5% (NVIDIA,
float) and 8.1% / 5.4% (usual / selective int8, 300 clips); mixed Russian and English untested.
Found in the source (session 24): with language "auto" (the app's default) whisper.cpp runs the
encoder twice per piece, once to detect the language (whisper.cpp:4177) and again to transcribe
(whisper.cpp:7215).

Test set: the owner's three files of plan 07 A2 (C:\Users\User\Downloads\2023 06 10 10 34 50.mp3,
C:\Users\User\Music\20260401_110502.m4a, C:\Users\User\Music\Аудиозапись.m4a) and the 455 s lecture
(build/whisper-test/audio/lecture-455s.mp4, the one with English terms). Pieces are cut exactly as the
app's search cuts them (controller._suggest_pieces, fix.search_windows, worker._reread). Scripts:
experiments/cpu_asr/. Data and models: build/cpu-asr-test/ (gitignored).

### Stage A: Compare CPU runtimes on the same pieces

- [x] **A1** dump_pieces.py (dev venv): RNNT text of each file, its doubtful lines cut as the app cuts them, saved as audio and JSON (context words, groups)
- [ ] **A2** Baseline: the app's whisper.cpp q5_0 on the CPU, 8 threads, language auto (as now) and language "ru" (one encoder pass); time per piece and the offers
- [ ] **A3** faster-whisper large-v3-turbo int8 on the CPU (own venv): one piece at a time and batched (8 per batch); greedy, no previous text, word times; time, RAM, offers
- [ ] **A4** Parakeet TDT 0.6B v3 on sherpa-onnx: the usual int8 build and the selective int8 build (LingoFlip); time, RAM, offers
- [ ] **A5** compare.py: offers of each runtime against the baseline, lecture terms checked by hand (the A5 list of plan 06: LLM-агентов, fine tuning, Tools Calling, Prompt Engineering ...); results page for the owner
- [ ] **A6** Owner chooses what goes on (a runtime, language once per file, or nothing)

### Stage B: Less work per file

- [ ] **B1** Measure reading fewer lines (only words below doubt_strong) and Whisper only on long doubtful runs, on top of the A6 choice
- [ ] **B2** Shorter window: audio_ctx with an ACFT fine-tune (MahmoudAshraf/acft-whisper-large-v3-turbo; Russian untested, licence to check)

### Stage C: In the app

- [ ] **C1** Build what the owner chose in A6 and B; tests; window_check; Windows and Linux builds
