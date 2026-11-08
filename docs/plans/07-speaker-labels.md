# Speaker labels

Owner's idea (docs/IDEAS.md, 2026-11-06, raised again 2026-11-08): speaker segments; "we are going to
want this really", for about v0.6.0. Moved here from plan 01 Stage E (E1-E4; E5, the voice library,
is Stage F below, for later).

Owner's answers (session 18, 2026-11-08):
- Test audio: a public labelled set (Russian if one exists) plus the owner's own files, which have no
  labels: `C:\Users\User\Music\Аудиозапись.m4a` (2 h 3 min; very complex: 3 speakers, sometimes at the
  same time, several languages with switching), `C:\Users\User\Music\20260401_110502.m4a` (1 h 23 min,
  several speakers, owner's guess 4), and `C:\Users\User\Downloads\2023 06 10 10 34 50.mp3` (23 min,
  many speakers, noisy, "it actually may as well be 19").
- When: a Settings checkbox (off by default) runs it after each file, plus a button
  "Определить говорящих" on any finished file, like "Найти варианты".
- Look: a new paragraph at each change of speaker, starting with a coloured "Говорящий 1:"; a click on
  the name renames the speaker, and the new name goes into all files.
- Voice library (named speakers from saved samples): later, not in v0.6.0.

Earlier findings (HANDOFF.md, "Diarization findings"): sherpa-onnx 2.0.1 with pyannote segmentation
3.0 + WeSpeaker ResNet34 on the CPU, about 10x realtime; the lecture gave 1 speaker (right); the
23 min file gave 19 speakers at threshold 0.5 and 4 at 0.8; 3D-Speaker ERes2Net gave 88.

### Stage A: Measure and decide

- [ ] **A1** A public labelled set with known turns (Russian if one exists, else VoxConverse / AMI), a few recordings of 2-6 speakers, and a scoring script (DER with a 0.25 s collar, speaker count error, time per audio minute)
- [ ] **A2** The owner's three files: run every candidate, compare speaker counts and turns against the transcript (who answers whom); the owner checks a few turns by ear
- [ ] **A3** Candidates: sherpa-onnx (pyannote segmentation 3.0 and newer, several embedding models, threshold sweep), a lighter own pipeline (embeddings per VAD region on the app's ORT provider, clustering), and newer models if they run on ONNX Runtime without torch (for example pyannote community-1, DiariZen, Sortformer); CPU and DirectML speed
- [ ] **A4** Choose the pipeline, the default threshold and the download size; write the results to HANDOFF.md and ask the owner

### Stage B: Engine

- [ ] **B1** Diarization module on ONNX Runtime (no torch), models as a catalog download
- [ ] **B2** Speaker count: automatic, or a fixed number when the user knows it
- [ ] **B3** Assign words to speakers by word timestamps (overlap: the speaker with the most time over the word); turns stored with the transcript and its history; renames kept
- [ ] **B4** Worker job "diarize" in the model process, with progress and cancel; controller runs it after a file (Settings checkbox) or on request

### Stage C: Window

- [ ] **C1** Settings checkbox (off by default) and the "Определить говорящих" button with a status line, like "Найти варианты"
- [ ] **C2** Paragraph per turn with a coloured "Говорящий N:"; a click on the name renames that speaker everywhere
- [ ] **C3** Number of speakers: automatic or a number the user gives
- [ ] **C4** window_check steps for speakers; screenshots

### Stage D: Files and CLI

- [ ] **D1** txt, srt, md, json and the text for an AI carry the speaker names
- [ ] **D2** CLI option for speakers and their count

### Stage E: Release v0.6.0

- [ ] **E1** Builds (Windows, Linux), smoke tests, release notes, README; publishing waits for the owner's go-ahead

### Stage F: Voice library (later, owner: not in v0.6.0)

- [ ] **F1** Named speakers: save a short sample of a voice once; later files match by embedding similarity and use the saved name
