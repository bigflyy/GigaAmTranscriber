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
the "Варианты для сомнительных слов" block (moved to the "Модель" block after C5, owner 2026-11-11: "i guess
it makes sense at model block", since the choice now also decides what reads Whisper's main text); choosing
faster-whisper when it is not downloaded asks the
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
- [x] **C4** Measure faster-whisper as the main model on the CPU against whisper.cpp: whole transcripts of the four files (words wrong against each other and by hand on the lecture terms, loops or invented text, word times, the confidence scale WHISPER_SCALE, time and RAM); owner decides from the results. Measured 2026-11-11 (session 26; experiments/cpu_asr/main_text.py, main_compare.py; page build/cpu-asr-test/main-results.html): with language "auto" both engines encode every chunk twice; faster-whisper's multilingual=True detects from the transcription's own pass, same text, 2.8x faster than whisper.cpp (lecture 180 s against 500 s, call 556 against 1569 s; 2.5-2.6x real time on all four files). RAM +150 MB loaded, +300 MB peak. Quality a draw (lecture 7 places, the owner's files 9-16% of words differ, nearly all in noisy places, each wins about as often); word times clearly better (median 0.08-0.14 s from GigaAM's against 0.20-0.26 s, far fewer zero-length words); WHISPER_SCALE fits as it is (marks fewer words, closer to GigaAM's share). Needs a fixed CTranslate2 seed (temperature fallback samples).
  Owner's decision (2026-11-11): C5 "yes"; the one-pass detection also for the search's "auto" pieces "yes"; a
  whisper.cpp patch for the same as its own task "ok" (C6); faster-whisper on the GPU measured "not yet" (it
  would need NVIDIA's cuBLAS 527 MB and cuDNN 664 MB on top of the 818 MB model, NVIDIA cards only;
  published numbers: about as fast as whisper.cpp one piece at a time, about 4x batched; docs/IDEAS.md).
- [x] **C5** The main text uses faster-whisper when it is chosen and Whisper runs on the CPU (transcribe and "Распознать снова"); language "auto" detected from the transcription's own encoder pass (multilingual=True), also for the search's "auto" pieces; a fixed CTranslate2 seed; tests. Done 2026-11-11 (session 27): the controller sends the key "faster-whisper" for Whisper when it is chosen, downloaded and the device is not "Видеокарта"; engine.Transcriber reads that key as Whisper (model_label "Whisper", so the search asks RNNT) and with "Авто" still loads whisper.cpp on a Vulkan card (engine.whisper_cpp_on_gpu). "Распознать снова" sends faster-whisper to the model process and shows its reading as "Whisper". Status line "Whisper - процессор, faster-whisper". "auto": placeholder "en" with multilingual=True, the vendored Segment got a language field (GigaAM patch). Seed: ctranslate2.set_random_seed alone is not enough (measured: CTranslate2 seeds its generator once per worker thread at its first use; seeding again, or unload_model/load_model, changes nothing), so the seed is set before loading and a new CTranslate2 model is loaded (about 1 s) before the chunk after any chunk that sampled. Lecture through the app's Transcriber: 173 s, 935 words the same as C4's fwm. 586 tests (582 passed, 4 skipped); both real-model tests pass with GIGAAM_FW_MODEL (the repeat test uses noise as loud as the speech and a control run without the reload, which gave three different texts).
- [x] **C6** whisper.cpp patch: detect the language "auto" from the transcription's own encoder pass instead of a second encoder run (whisper.cpp:4177 / 7215), on the CPU and the GPU; measure the gain (estimated 1.7x) and that the text stays the same
  Result 2026-11-11 (session 28): tools/build_whisper_cpp.py now applies PATCHES (exact text replacements, each must match the pristine 1.9.5 source once) and records their names in build-info.json; patch "one-encoder-pass-auto-language": whisper_full skips the main loop's encoder call for the window at offset 0 when the language detection has just encoded it with the same audio context (the decoder reads only the cross-attention cache, which the detection's one decoder step leaves as it is). build_windows.py (and so build_linux.py) refuses a whisper.cpp build without the patches. Measured with main_text.py, language auto, base = the old libraries, patched = the new (build/cpu-asr-test/c6/): output identical in every run (text, word times, confidences, chunk languages). CPU, 8 threads, lecture: 619 -> 318 s and 618 -> 327 s (1.9x; C4's base was 500 s on a quieter PC). Vulkan GPU (RTX 4070): lecture 15.0 -> 12.6 s (1.19x), call 38.5 -> 29.6 s (1.30x). The search's "auto" pieces go through the same whisper_full call, so they gain the same; pieces with the language from GigaAM's text (C1) never encoded twice. faster-whisper against the patched whisper.cpp, lecture, back to back on the same busy PC: 209.7 s against 299.6 s, so 1.4x for the main text (C4's 2.8x was against the unpatched whisper.cpp); the card note and the download question now say 1,4.
- [x] **C3** Packaging of C2 (and C5) (CTranslate2 in the Windows and Linux builds), window_check (also a step for C5: Whisper as the model, device "Процессор", faster-whisper reads the main text and the status line says so), builds, release notes. Owner 2026-11-12: the card stays "в 1,4 раза" (the 1.4x was not the PC's load: both engines ran back to back; quiet-PC estimate 1.5x). Split:
- [x] **C3a** gigaam-cli follows Settings.whisper_cpu like the window (Whisper read by faster-whisper on the CPU when chosen and downloaded); tests
- [x] **C3b** Windows build: CTranslate2 without its unused cuDNN file (the wheel is built WITH_CUDNN=OFF), huggingface_hub kept out, licences (packaging/licenses/ctranslate2: CTranslate2, Intel MKL and OpenMP, oneDNN, spdlog and fmt, cpu_features, Thrust, CUTLASS; tokenizers; faster-whisper), THIRD_PARTY_NOTICES.md, a faster-whisper smoke test of the frozen CLI on the CPU
- [x] **C3c** Linux build: the same, plus libgomp's licence (GCC runtime library exception)
- [x] **C3d** window_check: the C5 step (Whisper as the model, device "Процессор", faster-whisper reads the main text and the status line says so); run it
- [x] **C3e** Version, RELEASE_NOTES.md, README; full Windows and Linux builds for the owner to try. Done 2026-11-12: v0.7.0 assets in build/v0.7.0/release (Windows zip 956.2 MiB, Linux tar.gz 888.2 MiB, licences zip with windows/ and linux/, FFmpeg source, SHA256SUMS checked); every smoke test passed. C3 is ticked once the owner has tried the builds; publishing (tag, GitHub release) waits for the owner's go-ahead.
- [x] **C3f** Owner's trial 2026-11-12: the suggestion search crashed the model process (0xC0000005, audio_2026-11-10_19-20-22.ogg; dump: Dml::BucketizedBufferAllocator::Alloc on a null allocator in a convolution). ONNX Runtime 1.23 DirectML: after the newest DirectML session is freed, running any other DirectML session crashes until a new one is opened (reproduced with the speaker models alone; freeing an older one is safe); present since v0.6.0. Fix in the model process: freeing a model that uses DirectML frees every DirectML model; test; rebuild Windows and Linux; owner's choice: move the v0.7.0 tag to the fix and publish v0.7.0. Done 2026-11-12 (session 30): fix b174d42, tag v0.7.0 at dff9dca, release https://github.com/bigflyy/GigaAmTranscriber/releases/tag/v0.7.0 (Latest, five assets from build/v0.7.0-c3f/release, GitHub digests equal SHA256SUMS.txt)
