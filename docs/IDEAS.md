# Ideas

Owner's ideas for later. Ideas only: work that has started lives in docs/plans.
Older future items already sit in plans: plan 01 (B9 int8 encoder for CPU, Stage F other
models, Stage E speaker diarization) and plan 02 (D1-D3).

## Models

- 2026-11-06: an optimized Whisper variant for inference that I can turn on in the app;
  "one of the most important tasks probably". It may also help fix selected parts, "but
  just the model itself is already more important". Close to plan 01 Stage F (F2 compares
  Whisper large-v3-turbo with Parakeet and Qwen3-ASR) and plan 03 C1.

## Languages and speakers

- 2026-11-06: detect the language (there, in the selected part or the file).
- 2026-11-06: speaker segments somehow, somewhere ("idea for now").

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
