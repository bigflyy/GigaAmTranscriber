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

### Stage A: Suggestions in the backend

- [x] **A1** fix.py: group the doubtful words of a transcript into ranges (one line each, neighbours joined, at most MAX_SECONDS); turn a reading of the piece into suggestions (the differing runs that touch the group, as words with times)
- [x] **A2** Word.suggestions kept in the transcript and the history (not in the outputs); replace_words drops a suggestion whose words were changed
- [x] **A3** Worker job "suggest": one range at a time, each other installed model (not the transcript's own), Whisper with the terms; controller queues it after a finished file and on the button, a newly added file goes first; progress and results go to the page
- [x] **A4** Controller: take a suggestion (words keep their times, files written again, like apply_fix), leave it (the suggestion is dropped); Settings.suggest switch
- [ ] **A5** Measure on the 455 s lecture: how many suggestions, how many right, how long; decide whether a suggestion needs two models to agree

### Stage B: Window

- [ ] **B1** Blue underline for words with a suggestion; hover text names the suggestion; a click opens the card under the word (each model's reading, "Взять", "Оставить"), Esc and a click away close it
- [ ] **B2** File status shows the search ("Ищу варианты: 5 / 35"); "Найти варианты" for files without suggestions; Settings switch "Предлагать исправления"
- [ ] **B3** Tests (fix.py, controller with a fake model) and window_check.py steps

### Stage C: Release v0.5.0

- [ ] **C1** Release v0.5.0 (fix a part, doubt marks, AI export, player, suggested fixes): Windows and Linux builds with smoke tests, plan 05 C3 (player on Linux), notes, owner's go-ahead before publishing
