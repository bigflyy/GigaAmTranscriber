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

- [x] **A1** A public labelled set with known turns (Russian if one exists, else VoxConverse / AMI), a few recordings of 2-6 speakers, and a scoring script (DER with a 0.25 s collar, speaker count error, time per audio minute)
- [x] **A2** The owner's three files: run every candidate, compare speaker counts and turns against the transcript (who answers whom); the owner checks a few turns by ear. Owner 2026-11-08 on build/diar-data/owner/review.html (community-1: 4, 5, 7 speakers): "seems fine i guess"
- [x] **A3** Candidates: sherpa-onnx (pyannote segmentation 3.0 and newer, several embedding models, threshold sweep), a lighter own pipeline (embeddings per VAD region on the app's ORT provider, clustering), and newer models if they run on ONNX Runtime without torch (for example pyannote community-1, DiariZen, Sortformer); CPU and DirectML speed. Done 2026-11-08: community-1 and pyannote 3.1 (torch references), sherpa-onnx with 3 embeddings, ONNX speed on DirectML and CPU, int8, 2 s step; DiariZen and Rev not shippable, Sortformer 4 speakers, Nemotron needs a newer NeMo (results in HANDOFF.md, session 18). The lighter own pipeline was dropped: sherpa's simple clustering already loses 17-29% of words on the Russian set, VBx + PLDA is what wins
- [x] **A4** Choose the pipeline, the default threshold and the download size; write the results to HANDOFF.md and ask the owner. Owner 2026-11-08: "ok lets try this approach in v1 and try others in future": community-1 (segmentation-3.0 + WeSpeaker ResNet34-LM + PLDA, VBx clustering with pyannote's defaults: threshold 0.6, Fa 0.07, Fb 0.8) rebuilt on ONNX Runtime, DirectML with a CPU fallback (2 s step on the CPU), about 33 MB download

### Stage B: Engine

- [x] **B1** Diarization module on ONNX Runtime (no torch), models as a catalog download. Done 2026-11-08: gigaam_app/diarize.py (797e65b), models from experiments/diarization/export_speaker_models.py in build/diar-data/export (33 MB), catalog.SPEAKER_MODEL (folder speakers_community1, release models-1). Owner: "yes" to the upload; uploaded 2026-11-08 (GitHub digests equal the catalog's SHA-256; download.install tested), licences in packaging/licenses/speaker-models-LICENSE.txt and THIRD_PARTY_NOTICES.md
- [x] **B2** Speaker count: automatic, or a fixed number when the user knows it (SpeakerModel.diarize num_speakers; the window part is C3)
- [x] **B3** Assign words to speakers by word timestamps (overlap: the speaker with the most time over the word); turns stored with the transcript and its history; renames kept. Done: Word.speaker, Transcript.speakers (names), diarize.assign_speakers (numbers by first word, takes earlier names); history keeps them through asdict; JSON output carries them
- [x] **B4** Worker job "diarize" in the model process, with progress and cancel; controller runs it after a file (Settings checkbox) or on request. Worker side done (fa81053: events diarize_loading / diarize_progress / diarize_result, cancel through Worker.cancel, a lost process gives diarize_result with the error). Controller done (session 19): the speaker models download by themselves the first time (33 MB, no question: the user asked for speakers), Settings.speakers (off), after DONE or find_speakers(file, count); a search holds the next file (one whole-file job on the worker), goes before suggestion searches; assign_speakers, history, files rewritten; cancel_speakers, rename_speaker; a fixed word takes the speaker of the word it replaces (fix.replace_words)

### Stage C: Window

- [x] **C1** Settings checkbox (off by default) and the "Определить говорящих" button with a status line, like "Найти варианты". Done (session 19): #file-speakers under the file name (status, "Говорящих: авто / 1-20", button, "Отменить"), Settings fieldset "Говорящие"
- [x] **C2** Paragraph per turn with a coloured "Говорящий N:"; a click on the name renames that speaker everywhere. Done: a change of speaker (also inside a line) starts a new paragraph with the name in its colour (8 colours per theme, --spk-0..7); lines of one long turn stay paragraphs of their own (a lecture would otherwise be one paragraph); the name opens a dialog; an empty name gives the number back
- [x] **C3** Number of speakers: automatic or a number the user gives (per file, next to the button; the after-file run is automatic)
- [x] **C4** window_check steps for speakers; screenshots. Done (session 19): speaker_steps (models downloaded from the release into the temporary folder, search with count 2: 1 speaker with words on the one-voice clip, ~20 s with download and load; labels, colour, rename, a line split between two speakers, the checkbox); window_check --whisper 103/103; screens 04i-04k

### Stage D: Files and CLI

- [x] **D1** txt, srt, md, json and the text for an AI carry the speaker names. Done (session 19, outputs.line_parts): txt and the AI text "Имя: " at each turn after a blank line (the AI text's note says speakers are automatic and may be wrong); timestamps name the speaker on every line; srt cues never mix speakers, the first cue of a turn starts with the name; md a paragraph per turn with "**Имя:**"; json as before. "Копировать" uses the same texts
- [x] **D2** CLI option for speakers and their count: --speakers [auto|N|off] (alone = auto; default from Settings.speakers), --download Speakers, --list-models shows the speaker models; models download by themselves the first time

### Stage G: Tidy the window, speakers on / off, fixing speakers (owner 2026-11-09, before E)

Owner after trying session 19's window: "very cluttered now", "no switch on / off when we
segmented", "no way to fix segmentation results", "some buttons are showed one way and some are
the other way". Design first, the owner chooses, then build.

Owner's answers (session 20, 2026-11-09, on https://claude.ai/artifact/DeRDh7s7NayNWyu8M1K2PG):
- Layout: A (toolbar + menus: name and one fact line; Копировать ▾, Файлы ▾, ⋯; switches Таймкоды /
  Сомнения / Говорящие; a status line only while a search runs). But: "i do like B tho, and we
  could make both panels hideable, to fix the small monitor problem ... the percentage of text by
  speaker is useful i guess. and like being able to assing them a name. the rest is cluttering
  maybe ... round 2?" So a second round of mock-ups: A with B's speaker list (share of talk, name).
- Говорящие switch: saved files always carry the names when speakers are known; Копировать
  copies what is on screen.
- Fixes: all of them: a paragraph to another or a new speaker, merge two speakers, selected words
  to another or a new speaker. Owner: when selected words go to the speaker of the next (or
  previous) paragraph, they join that paragraph ("it should merge them right? into one
  paragraph?": yes, neighbouring turns of one speaker always join).
- Session 19's choices kept: lines of a long turn stay paragraphs, a speaker search holds the next
  file, the after-file run counts by itself. Owner added: when the user picks their own number,
  show the model's own count as a hint ("the model counted N speakers").
- Round 2 (same page, top): owner chose A2: A plus one thin line of speaker chips under the
  switches (colour, name, share of the talk; a chip's menu renames, merges, jumps to the next
  turn; "Заново..." at the end), hidden with the Говорящие switch. Not A1 (hideable side panels)
  nor A3 (a Говорящие menu in the toolbar).

- [x] **G1** Inventory of everything under the file name and above the text (status, model, "Найти варианты", speaker line, count, saved-file chips, switches, copy buttons) and how each control looks now (link-style vs button vs chip); screenshot of the current state. Done (session 20): 11 controls in 5 looks (blue links, big buttons, small buttons, chips, a dropdown); up to 6 lines under the name; head + tools take 40% of a 680 px window; empty status leaves "Искать заново" / "Определить заново" alone on an indented line. Page with the screenshot (window_check 103/103, screen 04k): https://claude.ai/artifact/DeRDh7s7NayNWyu8M1K2PG
- [x] **G2** Two or three layout mock-ups side by side (for example a compact toolbar over the text with the switches Таймкоды / Сомнения / Говорящие, one "more" menu for rarer actions, status lines folded into one line; one consistent style for actions), compared with how similar apps do it (Google Recorder, Otter, MacWhisper, Telegram voice transcripts); ask the owner to choose
- [x] **G3** A "Говорящие" switch over the text (like Таймкоды / Сомнения): shows or hides the names and paragraphs; saved files follow the shown choice or always carry names (ask the owner). Done (session 20): Settings.show_speakers; files always carry names (owner); copying follows the screen; on a file without speakers the switch opens the count dialog
- [x] **G4** Fixing speakers: options to show the owner (click a name -> menu: rename, change this paragraph's speaker to another or a new one, merge with another speaker; select words -> "Другой говорящий"); controller methods that change Word.speaker and Transcript.speakers, history and files follow; tests. Done (session 20): set_words_speaker(file, first, last, speaker or None = new; a number left without words is used again), merge_speakers(file, source, target); the view lists speakers with words and their share of speech time; Transcript.speakers_found (the model's own count, from the worker's new "diarize_found" event; not in the JSON file) for the hint; Settings.show_speakers; copy_text(..., with_speakers). 525 tests pass
- [ ] **G6** Lines inside a turn (owner 2026-11-09, after trying it: "weird layout ... last words are not of Anna?"): a line cut mid-sentence by a pause stood as its own paragraph without a name. Owner chose B: a line joins the paragraph before it when that one ended without . ? !, its time a small grey mark inside the paragraph (Таймкоды on); a turn that starts mid-line gets the time of its first word. Mock-up asked first (artifact, round 3). Also: menu headings "сказал(а)" (owner). Round 4 (same page, top): owner then chose D: "it seems best looking for me": the name on its own line above the turn, each paragraph's time in a left column (shown with Таймкоды), the text in one aligned column; lines cut mid-sentence join the paragraph before (no inner time mark in D); a turn starting mid-line gets its first word's time. Owner asked how B joins (answered: same joining, B only adds the joined line's time as a grey mark inside the text); if the owner switches back to B after that, build B
- [ ] **G7** "▶ Отсюда" on the selection bar (owner 2026-11-09: "yes"): plays from the selection's start and keeps going; "▶ Слушать" still plays only the selection; Alt+click stays
- [x] **G5** Build the chosen layout; window_check updated; screenshots for the owner. Done (session 20): layout A2 built (HANDOFF.md session 20); window_check --whisper 117/117; screens 04-files-menu, 04i-04n in session 20's scratchpad wcheck/shots3

### Stage E: Release v0.6.0

- [ ] **E1** Builds (Windows, Linux), smoke tests, release notes, README; publishing waits for the owner's go-ahead

### Stage F: Voice library (later, owner: not in v0.6.0)

- [ ] **F1** Named speakers: save a short sample of a voice once; later files match by embedding similarity and use the saved name
