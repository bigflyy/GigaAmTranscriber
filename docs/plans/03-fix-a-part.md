# Fix a part of the text

Owner's idea (docs/IDEAS.md, 2026-11-06): select a part of the text and try to fix it somehow:
decode again with another temperature or other heuristics, something smart, auto fixing; maybe
run another model on that part (Whisper or similar). Owner picked it as the next work after the
v0.3.0 release (2026-11-06).

What the app has to build on: every word has its start and end time (Transcript -> Segment ->
Word), the whole transcript is kept per file (gigaam_app/history.py), both models (RNNT, CTC)
are bundled, decoding is greedy (asr.RnntHead.decode, asr.ctc_decode), and the audio was cut into
chunks of up to about 25 s by Silero VAD. Greedy decoding has no "temperature": the usual sources
of other readings are a different cut of the audio, the other model, beam search (N best), or a
different model family.

Owner's decisions (2026-11-06):
- "Распознать заново" shows the readings that differ side by side; the user picks one
  ("Взять"), edits by hand or cancels. Nothing is replaced automatically.
- Listening to the selection is part of Stage A.

### Stage A: Select, listen, re-recognise

- [ ] **A1** Select words in the text (mouse drag over the live text of a finished file); the selection maps to a time range from the word times
- [ ] **A2** Play the selection (and a click-to-play on any line, plan 02 D3): audio cut by ffmpeg to a temporary WAV, played by the page's audio element
- [ ] **A3** "Распознать заново" on the selection: decode the time range again, with 1-2 s of context on each side and the cut at the VAD's quietest point, with RNNT and with CTC; show the readings that differ from the current text side by side
- [ ] **A4** Pick a reading or edit the text by hand; the change goes into the transcript (words keep times), the saved files are written again, the history entry is updated
- [ ] **A5** Tests (controller with a fake model; real models on a known hard sample) and window_check.py steps

### Stage B: More readings

- [ ] **B1** RNNT beam search (width 4-8) giving the N best readings of the range; measure speed and whether the second-best readings are useful on the sample files
- [ ] **B2** Mark doubtful words (low token probability) in the text, so the user knows where to look

### Stage C: Another model for the part

- [ ] **C1** Depends on plan 01 Stage F (Whisper large-v3-turbo, Parakeet, Qwen3-ASR compared on Russian): offer the winner as an optional download and as one more reading in A3
