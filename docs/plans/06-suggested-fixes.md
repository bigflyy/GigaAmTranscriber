# Suggested fixes for doubtful words

Owner's idea (docs/IDEAS.md, 2026-11-07): merge the two models' strengths, "gigaam does bad with
english namings and whisper is good with english namings". Recommended in session 15 as the next
work and accepted by the owner (2026-11-08, session 16).

How it works: after a file is recognised, every group of doubtful words (below the dotted
threshold, Settings.doubt_light; neighbours in one line grouped) is recognised again in the
background with the other installed models, the same way as "Распознать заново" (plan 03 A3: the
group plus up to 1.5 s / 6 words of context, cut at the quietest point). Whisper gets the user's
terms (Settings.terms). Each reading is lined up with the current text (difflib on word keys); a
run of words that differs and touches the doubtful group becomes a suggestion, widened to the whole
run ("Tullz Colling" -> "Tools Calling"). The user clicks the word, sees each model's reading in a
small card and takes one with one click, or leaves the text as it is.

Owner's decisions (2026-11-08, AskUserQuestion):
- Release v0.5.0 after this work, with everything since v0.4.0 in one release.
- Suggestions are looked for automatically after every file (a Settings switch turns it off), and a
  "Найти варианты" button does it for older files from the history.
- A doubtful word with a suggestion keeps its dotted / wavy underline, but in blue (like Google
  Docs' suggestions); in the all-colours mode a blue underline is added. A click opens the card.

Changed after the A5 measurement (2026-11-08): each line with doubtful words (one VAD chunk, at
most 25 s) is read once as a whole instead of each group with 1.5 s of context, and only Whisper
checks GigaAM's text (RNNT checks Whisper's); CTC's offers were nearly all wrong. An offer keeps
the punctuation of the words it replaces. Numbers in HANDOFF.md, session 16.

### Stage A: Suggestions in the backend

- [x] **A1** fix.py: group the doubtful words of a transcript into ranges (one line each, neighbours joined, at most MAX_SECONDS); turn a reading of the piece into suggestions (the differing runs that touch the group, as words with times)
- [x] **A2** Word.suggestions kept in the transcript and the history (not in the outputs); replace_words drops a suggestion whose words were changed
- [x] **A3** Worker job "suggest": one range at a time, each other installed model (not the transcript's own), Whisper with the terms; controller queues it after a finished file and on the button, a newly added file goes first; progress and results go to the page
- [x] **A4** Controller: take a suggestion (words keep their times, files written again, like apply_fix), leave it (the suggestion is dropped); Settings.suggest switch
- [x] **A5** Measure on the 455 s lecture: how many suggestions, how many right, how long; decide whether a suggestion needs two models to agree. Compare the 1.5 s / 6 words of context with reading each whole line (VAD chunk, at most 25 s) once (owner 2026-11-08: "yes"); switch the app to whole lines if they win

- [x] **A6** Measure about 25 s centred on each group (half before, half after, across line ends) against whole lines (owner 2026-11-08: "measure it, test it"); switch if it wins. Result: same quality (Whisper ~9-10 of 18 right against ~9 of 17), 29 readings and 31.5 s against 18 and 22.5 s; whole lines stay

### Stage B: Window

- [x] **B1** Blue underline for words with a suggestion; hover text names the suggestion; a click opens the card under the word (each model's reading, "Взять", "Оставить"), Esc and a click away close it
- [x] **B2** File status shows the search ("Ищу варианты: 5 / 35"); "Найти варианты" for files without suggestions; Settings switch "Предлагать исправления"
- [x] **B3** Tests (fix.py, controller with a fake model) and window_check.py steps

- [x] **B4** "Исправить..." in the offer card (owner 2026-11-08: "yes"): opens the fix dialog for the words the offer covers, the box filled with the offer's text, so a nearly right offer can be corrected by hand

- [x] **B5** On the CPU only the button searches (owner 2026-11-08: "on cpu it should be off by default and there should be a button"; Whisper on the CPU is slower than the recording): Settings "Варианты для сомнительных слов" gpu (default) / always / off

### Stage C: Models in their own process

The window froze for about 4 s while GigaAM loaded: ONNX Runtime holds Python's interpreter lock
while it opens the model, and pywebview runs Python on every move of the window (measured in
session 16). Owner 2026-11-08: run the models in a separate process, before v0.5.0 ("1 yes").

- [x] **C1** worker.WorkerProcess: the Worker in a spawned process, the same jobs / cancel / engine_key / start / stop for the controller; a crashed process is reported (the running file fails, a search gets its _failed event) and replaced; the process ends when the window's process is gone; launchers/gui_main.py calls freeze_support(); tests/test_worker_process.py
- [x] **C2** Check: window_check with Whisper passes; the window's main thread no longer stops during a load (probe); the frozen Windows and Linux builds start the process (in the release smoke tests, D1)
- [x] **C3** Owner's question 2026-11-08: can the load itself be shortened? Measure where the time goes (CUDA start-up, graph optimisation, an optimised copy kept on disk) and answer. Result (HANDOFF session 17): a saved optimised copy does not open on DirectML; on the CPU it would save ~1-1.5 s of ~2.5 s; not built

### Stage D: Release v0.5.0

- [x] **D1** Release v0.5.0 (fix a part, doubt marks, AI export, player, suggested fixes): Windows and Linux builds with smoke tests, plan 05 C3 (player on Linux), notes, owner's go-ahead before publishing. Published 2026-11-08: https://github.com/bigflyy/GigaAmTranscriber/releases/tag/v0.5.0
