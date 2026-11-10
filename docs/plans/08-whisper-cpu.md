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
- [x] **A2** Baseline: the app's whisper.cpp q5_0 on the CPU, 8 threads, language auto (as now) and language "ru" (one encoder pass); time per piece and the offers
- [x] **A3** faster-whisper large-v3-turbo int8 on the CPU (own venv): one piece at a time and batched (8 per batch); greedy, no previous text, word times; time, RAM, offers
- [x] **A4** Parakeet TDT 0.6B v3 on sherpa-onnx: the usual int8 build and the selective int8 build (LingoFlip); time, RAM, offers
- [x] **A5** compare.py: offers of each runtime against the baseline, lecture terms checked by hand (the A5 list of plan 06: LLM-агентов, fine tuning, Tools Calling, Prompt Engineering ...); results page for the owner
- [x] **A6** Owner chooses what goes on (a runtime, language once per file, or nothing)

Owner's decision (2026-11-11, after the results page build/cpu-asr-test/results.html): the language
from GigaAM's text ("it is weird but ok lets do that. unless configured otherwise in settings"):
only when Settings.language is auto; a language set in Settings is used as now. faster-whisper:
"i guess it should be an option if it is that faster" (its 1.6 GB file is turbo in fp16; an int8
file is about 0.8 GB). Results in HANDOFF.md, session 24. Asked again with the gain on top of C1
(1.6x one piece at a time, 2.0x batched, a second runtime in the app, an optional 814 MB download):
owner 2026-11-11 "yes", C2 goes ahead.

Owner's choices for C2 (2026-11-11, mock-up https://claude.ai/artifact/BWNUwoCShj5L21Gmpqe2Zv, A was my
recommendation): layout B, two cards "Whisper на процессоре": whisper.cpp / faster-whisper (int8), in
the "Варианты для сомнительных слов" block; choosing faster-whisper when it is not downloaded asks the
usual download question, "Не сейчас" moves the choice back to whisper.cpp. On a video card Whisper stays
on whisper.cpp (Vulkan). Scope: "search and main text but check first the quality and etc": the search
first (C2), the main text (Whisper as the chosen model on the CPU) only after C4 shows it is as good.

### Stage B: Less work per file

- [ ] **B1** Measure reading fewer lines (only words below doubt_strong) and Whisper only on long doubtful runs, on top of the A6 choice
- [ ] **B2** Shorter window: audio_ctx with an ACFT fine-tune (MahmoudAshraf/acft-whisper-large-v3-turbo; Russian untested, licence to check)

### Stage C: In the app

- [x] **C1** Language from GigaAM's text for the search's Whisper readings when Settings.language is auto (fix.py, controller); tests
- [x] **C2** faster-whisper int8 as a CPU option: a ready-made int8 upload (owner 2026-11-11: "i d use a ready made upload if possible. users dont have to download all the models all at once", so it is downloaded only when chosen); candidate Zoont/faster-whisper-large-v3-turbo-int8-ct2 (MIT, model.bin 814 MB, sha256 starts 7482f978f9493b93; voxta/faster-whisper-large-v3-turbo-int8 has the same file); split into C2a-C2e:
- [x] **C2a** The upload gives the A3 offers (read_fw.py on the 138 pieces, one piece at a time and batched, against fw-one-hint and fw-batch-hint). Result 2026-11-11 (readings fwq-one-hint, fwq-batch-hint; compare-fwq.json): same speed (one 6.1-9.4 s per piece, batch 4.9-5.3 s), RAM one at a time 1185 MB (A3 1879: no conversion at load), batch 2857 MB; offers equal A3's in 283 of 347 groups one at a time and 297 of 347 batched (int8 made at conversion, not at load); where they differ, whisper.cpp agrees with the upload in 18 and A3 in 13 (batch 11 and 20), all in noisy places; lecture 28 of 29 equal, the one difference "промпт-инжиниринга" (= whisper.cpp) instead of "prompt-инжиниринга". As good as A3.
- [x] **C2b** faster-whisper 1.2.1 in the app without its av, huggingface_hub and onnxruntime requirements (vendored, MIT, small marked patches), ctranslate2 and tokenizers in requirements; catalog entry (Hugging Face address pinned to a commit) and download
- [x] **C2c** Engine gigaam_app/faster_whisper_model.py with WhisperModel's methods plus a batched read; tests
- [x] **C2d** Search: Settings.whisper_cpu ("whisper.cpp" / "faster-whisper"), the worker picks the engine on the CPU, the controller sends up to 8 pieces of the same language at once; tests
- [x] **C2e** Настройки: the two cards (layout B), download question, "Не сейчас" goes back to whisper.cpp; window_check steps
- [ ] **C4** Measure faster-whisper as the main model on the CPU against whisper.cpp: whole transcripts of the four files (words wrong against each other and by hand on the lecture terms, loops or invented text, word times, the confidence scale WHISPER_SCALE, time and RAM); owner decides from the results
- [ ] **C5** If C4 is good: the main text uses faster-whisper when it is chosen and Whisper runs on the CPU (transcribe and "Распознать снова"); tests
- [ ] **C3** Packaging of C2 (and C5) (CTranslate2 in the Windows and Linux builds), window_check, builds, release notes
