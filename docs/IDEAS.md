# Ideas

Owner's ideas for later. Ideas only: work that has started lives in docs/plans.
Older future items already sit in plans: plan 01 (B9 int8 encoder for CPU, Stage F other
models, Stage E speaker diarization) and plan 02 (D1-D3).

## Models

- 2026-11-07: Whisper model size: q5_0 is the default, but make it "configurable (to download) in the future" (q8_0 874 MB, f16 1.6 GB).
- 2026-11-07: a user's list of terms (for example "LLM, fine tuning") given to Whisper as a hint (initial prompt), and beam search on our fragments. Owner: "beam search we can try. a list of terms i dk, you may test it a bit. maybe it will even transfer to 03 stage A" (the hint when a selected part is recognised again). Measured in session 14 (experiments/whisper/variants.py; results in HANDOFF.md). Owner 2026-11-08: terms in the re-recognise box of plan 03 A3 (Whisper reading of that part only), not a Settings field for whole files yet. Beam 5 gave little at 1.4-1.8x the time, so it is not proposed for now.
- 2026-11-08: research more models and try them: "parakeet qwen3 asr and similiar. maybe for fixes too (finding variants of doubtful words)". Both as models for whole files (plan 01 Stage F already lists Parakeet TDT 0.6B v3 and Qwen3-ASR) and as extra readers for the suggested fixes of plan 06 (today only Whisper checks GigaAM's text; CTC's offers were nearly all wrong). Measure them with experiments/suggest/suggest_check.py like A5.

## Languages and speakers

- 2026-11-06: detect the language (there, in the selected part or the file).

## Links and summaries

- 2026-11-07: send a video by link (YouTube for example) and get it transcribed, then summarised automatically: "an addon to firefox / chrome / just some kind of service, maybe even in our app idk". Summary with Claude / Codex / an API; a local model as experimental, for the future ("i dont have a good one").
  2026-11-08 (repeated): paste a YouTube link, "or possible in the future other types of link", and get a transcript; summarise it later with a local Codex or Claude Code, or a local model ("i dont have good ones, so i barely think last one is usable").
- 2026-11-08: fix the doubtful words automatically through an LLM (a local Codex or Claude Code): "summarize and maybe fix it (the unsure words) auto via llm (codex / claude code)". Builds on the "Для ИИ" text, which marks doubtful words as слово[?66%], and on the suggested fixes of plan 06 (the LLM could pick between the models' readings).

## Started

- 2026-11-06: speaker segments somehow, somewhere ("idea for now").
  2026-11-08: owner: speaker labels are the next big task after suggested fixes (plan 06): "we are going to want this really", probably for v0.6.0, "unless something you or i think of something cool and better". Plan 01 Stage E holds the earlier diarization work. Started 2026-11-08 (session 18): docs/plans/07-speaker-labels.md.
- 2026-11-07: merge the two models' strengths: "gigaam does bad with english namings and whisper is good with english namings. idk if we can merge these capabilities, but if we could it d be nice. somehow. in the future." (On the lecture GigaAM wrote "tullz colling", "deps", "umail" where Whisper wrote "tools calling", "deepsync", "uml".) For now only Whisper as a model you can choose and run (plan 04). Started 2026-11-08 as suggested fixes for doubtful words: docs/plans/06-suggested-fixes.md.
- 2026-11-08: an audio player: "maybe there should be a play/pause button. and how much time passed (the player of audio interface?)". Owner chose a whole-file player. Plan: docs/plans/05-audio-player.md.
- 2026-11-06: select a part of the text and try to fix it somehow: decode again with
  another temperature or other heuristics, something smart, auto fixing; maybe run another
  model on that part (Whisper or similar). Plan: docs/plans/03-fix-a-part.md (owner chose it
  after the v0.3.0 release, 2026-11-06).

## Finished

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
