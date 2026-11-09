# Ideas

Owner's ideas for later. Ideas only: work that has started lives in docs/plans.
Older future items already sit in plans: plan 01 (B9 int8 encoder for CPU, Stage F other
models, Stage E speaker diarization) and plan 02 (D1-D3).

## Models

- 2026-11-07: Whisper model size: q5_0 is the default, but make it "configurable (to download) in the future" (q8_0 874 MB, f16 1.6 GB).
- 2026-11-07: a user's list of terms (for example "LLM, fine tuning") given to Whisper as a hint (initial prompt), and beam search on our fragments. Owner: "beam search we can try. a list of terms i dk, you may test it a bit. maybe it will even transfer to 03 stage A" (the hint when a selected part is recognised again). Measured in session 14 (experiments/whisper/variants.py; results in HANDOFF.md). Owner 2026-11-08: terms in the re-recognise box of plan 03 A3 (Whisper reading of that part only), not a Settings field for whole files yet. Beam 5 gave little at 1.4-1.8x the time, so it is not proposed for now.
- 2026-11-08: research more models and try them: "parakeet qwen3 asr and similiar. maybe for fixes too (finding variants of doubtful words)". Both as models for whole files (plan 01 Stage F already lists Parakeet TDT 0.6B v3 and Qwen3-ASR) and as extra readers for the suggested fixes of plan 06 (today only Whisper checks GigaAM's text; CTC's offers were nearly all wrong). Measure them with experiments/suggest/suggest_check.py like A5.

- 2026-11-08: fine-tune GigaAM itself on videos that come with transcripts (kremlin.ru and similar): "would giga am transcription become better? ... i am just asking as an idea right now". Needs filtering, since the transcripts are edited (keep only stretches where GigaAM and the text agree closely); the gain may be small outside official speech, and the weak spot users hit (English terms in Russian lectures) needs lecture-style data instead. The fine-tuned model goes through experiments/onnx_runtime/export_onnx.py again; measure WER on held-out events.

- 2026-11-09: Whisper on the CPU is slow in the suggestion search (owner: "why is whispercpp so slow on the CPU?"). The build is optimized (Release, CPU variants up to AVX-512, as fast as a native build in session 11); the cost is the model's size and Whisper's fixed 30 s window, so every short doubtful line costs a full 30 s encoder pass. Ways to try: pack several short lines into one 30 s window with silence between them and split the words back by time; a smaller audio_ctx (quality to measure); on the CPU let RNNT check only, or Whisper only on long doubtful runs. Owner: "well yes why not pack lines together? although the context would suffer?" Measured (session 21, doubt below 0.97, owner's three files): 87-91% of lines have a doubtful word, 14-17 s on average, so padding is 43-53% of the work and packing needs only 1.2-1.5x fewer windows. The bigger levers: read fewer lines (only strongly doubtful words, below 0.80) and a shorter encoder window. audio_ctx: whisper.cpp says about 3x faster for 10 s, but quality drops; FUTO's tests: stock model with a length-scaled audio_ctx WER 226 (loops) vs 4.7, so stock large-v3-turbo needs an ACFT fine-tune (FUTO whisper-acft method; MahmoudAshraf/acft-whisper-large-v3-turbo exists, Russian untested, licence to check). Measure with experiments/suggest/suggest_check.py.

- 2026-11-08: OpenVINO as a faster CPU engine (an ONNX Runtime execution provider for Intel CPUs and Intel GPUs): owner: "we need to remember the openvino idea". For the speaker models' CPU fallback (plan 07) and maybe GigaAM's CPU mode too; weigh the extra download size, and check AMD CPUs.

## Languages and speakers

- 2026-11-06: detect the language (there, in the selected part or the file).

- 2026-11-08: train or fine-tune the speaker models on Russian data with known speakers, "in some wild future dreams? there is so much annotated data, no?" (kremlin.ru transcripts name every speaker, CC BY 4.0; also government.ru and similar). Cheapest first: refit community-1's PLDA on Russian voice prints; then fine-tune the voice-print model (the same named people appear in many events); the segmentation model last (the labels have no overlaps and loose turn edges). Keep the session 18 test events out of any training data.

- 2026-11-08: other speaker-labelling engines after v0.6.0: "lets try this approach in v1 and try others in future". Candidates from session 18 (HANDOFF.md): Nemotron-3-Diarization (needs a newer NeMo or own ONNX code), newer pyannote releases, DiariZen if its licence changes; measure them with experiments/diarization on the kremlin.ru set and AMI.

## Window

- 2026-11-09: side panels that can be hidden, for small screens: "we could make both panels hideable, to fix the small monitor problem". Said about the file list and a speakers panel (mock-up A1); the owner chose a speaker line instead (A2), so for now this is about hiding the file list.

## Links and summaries

- 2026-11-07: send a video by link (YouTube for example) and get it transcribed, then summarised automatically: "an addon to firefox / chrome / just some kind of service, maybe even in our app idk". Summary with Claude / Codex / an API; a local model as experimental, for the future ("i dont have a good one").
  2026-11-08 (repeated): paste a YouTube link, "or possible in the future other types of link", and get a transcript; summarise it later with a local Codex or Claude Code, or a local model ("i dont have good ones, so i barely think last one is usable").
- 2026-11-08: fix the doubtful words automatically through an LLM (a local Codex or Claude Code): "summarize and maybe fix it (the unsure words) auto via llm (codex / claude code)". Builds on the "Для ИИ" text, which marks doubtful words as слово[?66%], and on the suggested fixes of plan 06 (the LLM could pick between the models' readings).

## Started

- 2026-11-09: the window is cluttered and inconsistent after speakers: "i feel like the gui is very cluttered now ... you need to organize it somehow and declutter i guess. some buttons are showed one way and some are the other way". Started 2026-11-09 (session 20): docs/plans/07-speaker-labels.md Stage G (owner chose layout A2).
- 2026-11-09: a switch to show or hide the speakers once a file has them: "there is no switch on / off when we segmented". Started 2026-11-09 (session 20): docs/plans/07-speaker-labels.md Stage G (owner chose layout A2).
- 2026-11-09: a way to fix wrong speaker results: "no way to fix segmentation results" (for example give a paragraph or selected words to another speaker, merge two speakers, split one). Started 2026-11-09 (session 20): docs/plans/07-speaker-labels.md Stage G (owner chose layout A2).
- 2026-11-06: speaker segments somehow, somewhere ("idea for now").
  2026-11-08: owner: speaker labels are the next big task after suggested fixes (plan 06): "we are going to want this really", probably for v0.6.0, "unless something you or i think of something cool and better". Plan 01 Stage E holds the earlier diarization work. Started 2026-11-08 (session 18): docs/plans/07-speaker-labels.md.
- 2026-11-07: merge the two models' strengths: "gigaam does bad with english namings and whisper is good with english namings. idk if we can merge these capabilities, but if we could it d be nice. somehow. in the future." (On the lecture GigaAM wrote "tullz colling", "deps", "umail" where Whisper wrote "tools calling", "deepsync", "uml".) For now only Whisper as a model you can choose and run (plan 04). Started 2026-11-08 as suggested fixes for doubtful words: docs/plans/06-suggested-fixes.md.
- 2026-11-08: an audio player: "maybe there should be a play/pause button. and how much time passed (the player of audio interface?)". Owner chose a whole-file player. Plan: docs/plans/05-audio-player.md.
- 2026-11-06: select a part of the text and try to fix it somehow: decode again with
  another temperature or other heuristics, something smart, auto fixing; maybe run another
  model on that part (Whisper or similar). Plan: docs/plans/03-fix-a-part.md (owner chose it
  after the v0.3.0 release, 2026-11-06).

## Finished

- 2026-11-09: cancel running jobs: "maybe we should be able to cancel jobs? like this long one looking for variants". Today only the speaker search has Отменить in the task line; the suggestion search (Найти варианты) has none, and a whole-file job can be cancelled only from the file itself. Owner: before v0.6.0. Finished 2026-11-09: Отменить for the suggestion search in the status line (offers found so far stay; the file does not count as searched); commit 0b31ff2.
- 2026-11-08: the text for an AI should show the suggested fixes: "make Копировать для ИИ makes it clear for AI that there are two versions of some words (whsiper vs giga am)". Finished 2026-11-08: "Копировать для ИИ" and the -llm.txt file give {GigaAM v3 RNNT: Tullz[?50%] Colling | Whisper large-v3-turbo (q5_0): Tools Calling} with a note on the format; commit 484e803.
- 2026-11-08: the note for an AI should say that everything is speech to text, "so even unmarked as doubtful words may be wrong". Finished 2026-11-08: a sentence added to the note's first line.
- 2026-11-08: export the word confidence, "to feed to llm maybe" ("does it export confidence in json txt or smh?"). Owner chose both a file and a button. Finished 2026-11-08: format "llm" (name-transcript-llm.txt) and "Копировать для ИИ", doubtful words as слово[?66%]; commit cb570ae.
- 2026-11-06: the app icon: "we need to do mockups and fix it". Finished 2026-11-06: owner
  picked idea A (wave into lines, blue) from the mockups at
  https://claude.ai/artifact/W1UuSDLLfjZPy1rRvonVm5; commit 86f4f68. The Linux window icon is
  wired but first seen at the next Linux build.
- 2026-11-06: "add export / save as markdown from the transcript", as a feature. Finished
  2026-11-06: the md format (owner chose title, info line and timed sections); commit 824c975.
- 2026-11-06: an optimized Whisper variant for inference that I can turn on in the app;
  "one of the most important tasks probably". It may also help fix selected parts, "but
  just the model itself is already more important". Close to plan 01 Stage F (F2 compares
  Whisper large-v3-turbo with Parakeet and Qwen3-ASR) and plan 03 C1. Plan: docs/plans/04-whisper.md (started 2026-11-07).
  Finished 2026-11-07: released in v0.4.0 (whisper.cpp + Vulkan, large-v3-turbo q5_0 from the
  models-1 release); https://github.com/bigflyy/GigaAmTranscriber/releases/tag/v0.4.0
