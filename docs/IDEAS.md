# Ideas

Owner's ideas for later. Ideas only: work that has started lives in docs/plans.
Older future items already sit in plans: plan 01 (B9 int8 encoder for CPU, Stage F other
models, Stage E speaker diarization) and plan 02 (D1-D3).

## Models

- 2026-11-07: Whisper model size: q5_0 is the default, but make it "configurable (to download) in the future" (q8_0 874 MB, f16 1.6 GB).
- 2026-11-07: merge the two models' strengths: "gigaam does bad with english namings and whisper is good with english namings. idk if we can merge these capabilities, but if we could it d be nice. somehow. in the future." (On the lecture GigaAM wrote "tullz colling", "deps", "umail" where Whisper wrote "tools calling", "deepsync", "uml".) For now only Whisper as a model you can choose and run (plan 04).

## Languages and speakers

- 2026-11-06: detect the language (there, in the selected part or the file).
- 2026-11-06: speaker segments somehow, somewhere ("idea for now").

## Links and summaries

- 2026-11-07: send a video by link (YouTube for example) and get it transcribed, then summarised automatically: "an addon to firefox / chrome / just some kind of service, maybe even in our app idk". Summary with Claude / Codex / an API; a local model as experimental, for the future ("i dont have a good one").

## Started

- 2026-11-06: select a part of the text and try to fix it somehow: decode again with
  another temperature or other heuristics, something smart, auto fixing; maybe run another
  model on that part (Whisper or similar). Plan: docs/plans/03-fix-a-part.md (owner chose it
  after the v0.3.0 release, 2026-11-06).

## Finished

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
