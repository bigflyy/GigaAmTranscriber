# Handoff: state and findings

Last updated 2026-11-09 (session 21). Current plan: [docs/plans/07-speaker-labels.md](docs/plans/07-speaker-labels.md) (speakers; B-D and G done, owner liked G6 / G7; next: E1, the v0.6.0 release).
Plan 06 finished (suggested fixes, models in their own process, release v0.5.0 published as its
Stage D). Plan 03 (fix a part):
A and B2 done; B1 and C left. Plan 05 (player) done (C3 in v0.5.0).
Plan 04 (Whisper) done: v0.4.0. Plan 02 (window) has D for later; plan 01 still
holds B9, F (Parakeet, Qwen3-ASR, F5 for suggestions) (its E moved to plan 07).
Owner's ideas: [docs/IDEAS.md](docs/IDEAS.md).

## Session 21 (2026-11-09): plan 07 G6 (layout D) and G7 (play from here)

- G6 window (app.js): drawLines -> appendParagraphs. Each paragraph is a row div.para: a
  time (time.playable, data-seg / data-w of its first word; a click plays from that word) in
  a left column (CSS grid, --time-col 3.6em, 5.2em past an hour; only with Таймкоды) and a
  p with the text. Words sit in span.seg[data-seg] (one per line or line piece), so
  span.parentNode.dataset.seg still maps a word; every "p[data-seg]" selector became
  ".seg[data-seg]". With speakers the name is a div.turn-head line (no colon) above the turn,
  lined up with the text; a piece joins the paragraph before when that one does not end with
  . ? ! ... (endsSentence, closing quotes / brackets allowed); a turn starting inside a line
  shows its first word's time; empty lines are skipped. Without speakers: the same rows, a
  paragraph per line, no joining (my choice; asked the owner). turnRange finds the turn's
  first word in the row after the name. onSegment redraws when turns are shown.
- G6 files (outputs.py): ends_sentence, part_text, paragraphs(); turn_lines writes a line per
  paragraph, so txt and the AI text join; md starts no section in the middle of a sentence
  (unless the section reached 3 min). srt, timestamps, json unchanged. Without speakers no
  change. 7 new tests (541 pass, 2 skipped).
- G7: #sel-from "▶ Отсюда" on the selection bar plays from the selection's first word on
  (playFrom without stopAt). README updated (name line, joining, time column, Отсюда).
- window_check --whisper 122/122: names without colon, layout D checks (name rows, the turn
  inside a line has its word's time, page paragraphs = outputs.paragraphs, text and names in
  one column), the join rule run by the page on made-up lines (the clip has one line), Отсюда
  plays past the selection's end. The run started about when the empty-line skip was added,
  so it may not include that line (the clip has no empty lines). Screens in this session's
  scratchpad wcheck/shots1 (04a, 04k-two-speakers-times).
- Owner after G6 / G7 (2026-11-09): "yep i like it". Joining also without speakers (owner):
  outputs.paragraphs joins for every transcript (a new turn still starts a paragraph);
  app.js appendParagraphs joins always, appendLine joins live lines during recognition,
  redrawLine redraws an offer's line pieces in place (full redraw only when they do not
  match). Commit 4b6d7a2.
- Cancel for the suggestion search (owner: before v0.6.0), commit 0b31ff2:
  controller.cancel_suggestions (drops the lines not yet read; the line on the worker ends
  and its offers stay; suggestions_searched stays False; a queued file is taken out),
  _suggest_view can_cancel, "Останавливаю поиск вариантов..."; task line has #task-suggest and
  #task-speakers, each with its Отменить. window_check --whisper 124/124 (screen
  04g2-search-cancel in wcheck/shots2); 543 tests pass. The app.js part of the joining went
  into the cancel commit (same file).
- Whisper on the CPU (owner asked why so slow): the build is optimized (Release, CPU variants,
  as fast as a native build); the model is large and every read pads to a 30 s window.
  Padding measured on the owner's three files (scratchpad padding.py): 87-91% of lines have a
  doubtful word (below 0.97), 14-17 s on average; padding 43-53%; packing would need only
  1.2-1.5x fewer windows. audio_ctx research and the options are in IDEAS.md (Models). Owner
  asked about packing and context; answered: packed lines share decoder context (cannot be
  dropped inside one window), gain is small; better levers are fewer lines and a shorter window.
- Tooling: in this shell, heredocs fed to python turned "\\n" and "\\u2026" escapes into the
  characters; write patch scripts with the Write tool and run "python -I script.py".

## Session 20 (2026-11-09): plan 07 Stage G, the tidy window, speakers switch and fixes

- G1/G2: mock-ups at https://claude.ai/artifact/DeRDh7s7NayNWyu8M1K2PG (current screen, Recorder /
  Otter / MacWhisper, layouts A-C, round 2 A1-A3, the fix menus). Owner chose A, then A2 (answers in
  the plan's Stage G). Files always carry the names; all three fixes; session 19 choices kept; the
  model's own count as a hint. Hideable side panels went to IDEAS (Window).
- G4 (3221ad0): controller.set_words_speaker (None = new; a number left without words is used
  again), merge_speakers (the source number stays unused), speakers view "list" with share of
  speech time, "found" (Transcript.speakers_found: with a given count the VBx count from the
  worker's "diarize_found" event, else the speakers found; not in the JSON file), "error";
  Settings.show_speakers (also in set_settings / reset / view); copy_text(..., with_speakers).
- G3/G5 page: head = name + one meta line (status · model), buttons Копировать (+ arrow: для ИИ),
  Файлы (saved formats, + creates, Показать в папке), "..." (Найти варианты with its status as
  hint, Определить говорящих..., Распознать снова, Убрать из списка); "Распознать снова" stays in
  sight only for a file without text. Switches Таймкоды / Сомнения / Говорящие (on a file without
  speakers it opens the count dialog #speaker-search with "модель насчитала" hint). Speaker chips
  line (#speaker-line: name, share %, menu: rename, next turn, merge; "Заново..."; hint "модель
  насчитала N" when it differs). #task-line only while a search runs (with Отменить) or after a
  speaker search failed. One popup #menu (app.js openMenu: arrows, Esc, click outside). A name in
  the text opens: rename, "Эту реплику сказал" (whole turn) other / new, merge. Selection bar gets
  "Говорящий". No undo (text edits have none either). README updated for the new head.
- window_check: menu helpers open_menu / menu_texts / choose; speaker steps cover the switch,
  dialog, chips, give turn, merge, selected words, hide / show; screens 04i-04n and 04-files-menu.
  First run 116/118 (set_settings ignored show_speakers: fixed); second run --whisper 117/117;
  526 tests pass.
- Owner tried it: menu headings now "Эту реплику сказал(а)" / "Эти слова сказал(а)". Owner saw a line
  cut mid-sentence ("...действительно могут" / 00:55 "Решить большинство проблем.") stand as its own
  paragraph without a name and asked if it was a bug: no, the words are Anna's (session 19 kept each
  line of a turn as a paragraph). Owner chose B: plan 07 G6 (join a line to the paragraph before it
  when that one ends without . ? !, its time a small grey mark inside; a turn starting mid-line gets
  its first word's time). Mock-up: round 3 on the artifact page; owner asked for it before the build,
  so G6 waits for the owner's look at it. Round 4 (D and E, name first): owner chose D (name above,
  time column), then confirmed D after hearing how B joins. Lines are cut mid-sentence because the
  VAD caps a line at 25 s and cuts at the longest short pause (a breath) when no 2 s pause comes.
  Owner: saved txt, md and AI text join such lines too ("yes"); srt and timestamps keep their timing.
  G7: "▶ Отсюда" on the selection bar (owner: yes). Then E1.
- Bug (owner): the suggestion card closed whenever the search added an offer (with speakers every
  line event redraws the whole text, and drawLines closes the card). Fixed: onLine reopens the card
  on the same word (reopenCard); window_check step for it; window_check --whisper 118/118.

## Session 19 (2026-11-09): plan 07 B4, C, D done (speakers in the window, files, CLI)

- B4 controller (c0354ac): Settings.speakers (off) queues a search after each DONE file;
  find_speakers(file, count) for the button; the speaker models (catalog.SPEAKER_MODEL, 31 MiB)
  download by themselves the first time through the worker's "download" job (no question: the
  user asked for speakers). One search at a time; it holds the next file (a whole-file job on
  the worker; a waiting file says "...когда закончится определение говорящих") and goes before
  suggestion searches. diarize_result -> assign_speakers (turns come as tuples, made Turns
  again), history, files rewritten. cancel_speakers, rename_speaker (empty name = number back),
  close question names a running search. fix.replace_words: new words take the speaker of the
  first word they replace.
- C window (a9bf314): #file-speakers line (status, "Говорящих: авто / 1-20", button "Определить
  говорящих" / "Определить заново", "Отменить"); Settings fieldset "Говорящие". With speakers a
  change of speaker (also inside a line) starts a paragraph with a coloured name (--spk-0..7 per
  theme); the lines of one long turn stay their own paragraphs (my choice: a lecture would
  otherwise be one paragraph). A click on the name opens a rename dialog. Page words carry
  word[5] = speaker. window_check speaker_steps: --whisper 103/103 (screens 04i-04k in this
  session's scratchpad wcheck/shots; the lecture clip has one voice, so a second speaker is set
  by the check to see a split line).
- D files and CLI (748a27c): outputs.line_parts; txt and the AI text "Имя: " at each turn after
  a blank line (the AI note says speakers are automatic and may be wrong); timestamps name the
  speaker on every line; srt cues never mix speakers, the first cue of a turn has the name; md
  "**Имя:**" per turn; copying uses the same texts. CLI --speakers [auto|N|off] (default from
  the settings file), --download Speakers, --list-models lists them. 517 tests pass, 2 skipped.
- CPU speed of the port (PORT_DEVICE=cpu, 2 s step, run_port_sets.sh port-cpu, results in
  build/diar-data/out/port-cpu.txt): 14-18x realtime, about 17x overall (an hour in ~3.5 min;
  voice prints ~90% of the time). Same quality as the GPU at 2 s: AMI DER 20.9 (excl 26.8),
  kremlin 0.3% words wrong, all counts right except TS3003a (2 of 4, as always). Another
  session's light test jobs may have run alongside.
- Owner saw it (2026-11-09): "the gui is very cluttered now", no on / off switch for speakers, no way to fix speaker results, buttons styled inconsistently; asked whether to do it now or next session (next: design with mock-ups first). Added as plan 07 Stage G and to docs/IDEAS.md (Window).
  Plan 07 left: E1 (v0.6.0 builds, smoke tests, notes, README; publishing waits for the owner).

## Session 18 (2026-11-08): speaker labels, questions first

- Decision (owner, "leave them"): the 17 older commits on GitHub that carry a Claude co-author
  line stay as they are. No history rewrite, no force push; tags v0.3.0, v0.4.0, models-1 keep
  their ids. New commits carry no co-author or attribution lines.
- Speaker labels got their own plan, docs/plans/07-speaker-labels.md (plan 01 Stage E moved there).
  Owner's answers are at its top: public labelled set (Russian if any) plus three own unlabelled
  files; Settings checkbox (off) + "Определить говорящих" button; turns with a coloured, renamable
  "Говорящий N:"; voice library later. Owner then asked: "research the options for speaker
  labeling and segmentations. test them and check them out. including newer and better ones".
  Owner also: prefer test sets the models were unlikely to be trained on; the app takes the
  number of speakers when the user knows it (already B2 / C3); asked for GPU, not only CPU.
- Research (web, 2026-11-08). Shippable: pyannote community-1 = segmentation-3.0 (MIT, 6 MB ONNX
  from sherpa-onnx) + WeSpeaker ResNet34-LM (26.5 MB ONNX) + community-1 PLDA (CC-BY-4.0, mirrored
  ungated in FinDIT-Studio/dia-models) with VBx clustering; Rust ports `dia` and `speakrs` reach
  pyannote parity without torch. Nemotron-3-Diarization (NVIDIA, 2026-09, OpenMDW, max 8
  speakers, 199 MB .nemo; ONNX exports in onnx-community need own mel + speaker-cache code; NeMo
  2.7.2 in env newrag cannot load it: "TransformerEncoder" missing). Not shippable: DiariZen
  (weights CC BY-NC), Rev reverb v1/v2 (Non-Production licence). Sortformer v2/v2.1: 4 speakers.
  No free Russian labelled diarization set found.
- Test sets in build/diar-data (gitignored; scripts in experiments/diarization, README there):
  AMI test ES2004a, IS1009a, TS3003a, EN2002a (Mix-Headset, only_words RTTM + UEM; pyannote
  trains on other AMI meetings, so a setup check only). Unseen Russian set from kremlin.ru
  (CC BY 4.0): 5 events, 3.9 h, 2-16 speakers (81185 government meeting, 80874 party leaders,
  80929 teachers, 80788 gas ceremony with video links, 81071 interview); labels from the
  transcript's bold speaker names lined up (difflib) with GigaAM RNNT word times: 99.2-100% of
  words labelled, text match 92-95%. An official's first turn is a linked name with a photo
  tooltip; the first parser missed those (81185 had 10 speakers instead of 16, whole reports
  given to Putin, 63% "wrong" for every system); fixed in ae84be5. Audio kept as 16 kHz FLAC only (disk below 20 GB free);
  review page build/diar-data/kremlin/review.html plays the video from kremlin.ru.
- AMI results (DER %, collar 0, overlap scored; 4 meetings, 92 min):
  | system | DER | confusion part |
  | --- | --- | --- |
  | community-1 (torch, auto count) | 19.9 | 3-5 |
  | community-1, true count | 19.8 | |
  | pyannote 3.1, auto | 21.3 | (TS3003a: 2 speakers of 4) |
  | sherpa-onnx seg-3.0 + ResNet34, true count | 29.0 | 5-29 |
  | sherpa-onnx + CAM++ zh_en, true count | 32.4 | |
  | sherpa-onnx + ERes2NetV2, true count (2 files) | 46.8 | |
  Same segmentation, so the gap is the clustering: VBx + PLDA vs sherpa's complete-linkage AHC.
  Exclusive (one speaker at a time) versions score ~26 (overlap counted as missed) but have
  lower confusion: that is the one for labelling words. Speeds: pyannote torch GPU 20-35x
  realtime (batch 1); sherpa-onnx CPU 6-8x.
- ONNX speed probe (speed_probe.py, random input, batch 32), per hour of audio, 1 s step:
  DirectML: segmentation 10 s, ResNet34 embeddings once per window 21 s (x3 per local speaker
  62 s); CPU 8 threads: 36 s, 6 min (x3 18 min). Plan for B1: run the ResNet trunk once per
  window and pool per speaker (pyannote's forward_frames / forward_embedding split), on DirectML.
- Russian results on the fixed labels (build/diar-data/out/rescore.txt), words with the wrong
  speaker (all words, exclusive version) and DER (collar 0.25, from the labels' loose edges):
  | system | words wrong | DER | speakers found (true 14, 7, 7, 2, 16) |
  | --- | --- | --- | --- |
  | community-1, auto count | 0.3% | 10.5 | all exact |
  | community-1, 2 s step | 0.3% | 10.3 | all exact |
  | community-1, true count | 0.3% | 10.5 | |
  | pyannote 3.1, auto | 0.1% | 10.3 | all exact |
  | sherpa-onnx + CAM++ zh_en, true count | 17.7% | 24.6 | 11, 6, 5, 2, 14 |
  | sherpa-onnx + ResNet34, true count | 29.4% | 36.2 | 11, 6, 5, 2, 13 |
  Official events are easy (clean microphones, long turns); AMI and the owner's files are the hard
  cases. AMI with the 2 s step: DER 20.6 (1 s: 19.9; TS3003a 2 of 4 speakers). So 2 s is a fair
  CPU setting, 1 s stays for the GPU.
- int8 (dynamic, unsigned weights; signed fails: no ConvInteger on the CPU) ResNet34: 6.7 MB,
  cosine 0.99 to float, but 4.7x slower on the CPU (1496 s per hour vs 320 s). Dead end; the
  faster CPU path is OpenVINO (IDEAS) or less work (2 s step, skip silent windows).
- Owner's files (GigaAM transcripts in build/diar-data/owner/asr), speakers found: community-1
  auto 4 / 5 / 7 (Аудиозапись, 20260401_110502, 2023 06 10 10 34 50), pyannote 3.1 10 / 5 / 7,
  sherpa t0.5 37 / 17 / 17. Owner review page: build/diar-data/owner/review.html (local audio,
  words coloured by community-1 exclusive speakers). File ids with spaces broke the RTTM columns
  (09ae450).
- Owner checked the review pages ("seems fine i guess", "ok") and decided (A4): "ok lets try this
  approach in v1 and try others in future". So community-1 on ONNX Runtime for v0.6.0; other
  engines are an idea for later (IDEAS.md).
- Plan 07 Stage B, engine (commits 8451810, 797e65b, fa81053):
  - export_speaker_models.py (cuda-torch2) writes build/diar-data/export: segmentation.onnx
    (5.9 MB, seg-3.0, waveform (B,1,160000) -> powerset log-probs (B,589,7)), embedding.onnx
    (26.5 MB, ResNet34 trunk + pyannote's weighted StatsPool + seg_1 inside: centred fbank
    (B,998,80) + weights (B,3,125) -> (B,3,256)), speakers.npz (powerset table, PLDA with the
    eigh done offline, so no scipy), speakers.json (frame grid 0 / 0.0619375 / 0.016875,
    VBx 0.6 / 0.07 / 0.8). ONNX vs torch: 2e-5 and 1.4e-7.
  - gigaam_app/diarize.py: numpy port of every step (chunking, powerset, speaker count,
    Kaldi fbank once per batch span, centroid-linkage AHC with Lance-Williams (stops at the
    first pair above 0.6, same as fcluster), VBx, k-means for a fixed count, constrained
    assignment by trying every assignment, reconstruct, frame-middle turns). Speakers are
    numbered by first appearance. Step 1 s on a GPU, 2 s on the CPU. exclude_overlap off
    (as measured; community-1's own config may have it on, untested).
  - Check (run_port.py, run_port_sets.sh): segmentation 1e-6 of frames differ, count exact,
    fbank 5e-4; scores equal torch: AMI DER 19.9 (excl 26.0), kremlin 0.3% words wrong, all
    counts right. DirectML ~50x realtime (an hour in ~70 s: segmentation ~25 s, voice prints
    ~45 s; numpy pooling was 3x slower before it moved into the ONNX model). CPU speed not
    yet measured with the port.
  - Word.speaker, Transcript.speakers (names), diarize.assign_speakers; JSON output keeps
    them when known. Worker job "diarize" (events in worker.py's docstring). 486 tests pass.
  - catalog.SPEAKER_MODEL points at models-1 assets speakers_community1.<file>. Owner: "yes";
    uploaded 2026-11-08, GitHub digests equal the catalog; download.install from the release
    works. Licences: packaging/licenses/speaker-models-LICENSE.txt (bundled by both builds as
    licenses/speaker-models/LICENSE.txt) and THIRD_PARTY_NOTICES.md.
  - Next: B4 controller part, then Stage C (window), D (files, CLI).

## Session 17 (2026-11-08): plan 06 Stage C, models in their own process

- Owner chose option 1 (Worker in a separate process, before v0.5.0): "1 yes". Built (d892e59):
  worker.WorkerProcess runs the Worker in a spawned process (never fork) behind the same jobs /
  cancel / engine_key / start / stop, so the controller is unchanged. The process sends
  internal events "_job" (which job runs, or None between jobs), "_engine_key" (before
  "loaded") and "_exit"; a forwarder thread passes the rest on. A process that dies is
  reported (a reread / suggest gets *_failed + *_done; a load gets load_failed; then "error",
  which fails a running file) and a new process takes the waiting jobs. The process ends when
  the window's process is gone (parent_process().join()). A download job carries the
  ModelInfo, so window_check's test model (registered only in the window's process) still
  downloads. launchers/gui_main.py calls multiprocessing.freeze_support(); the frozen builds
  are not yet tried (D1 smoke tests). Tests 463 passed, 2 skipped; window_check --whisper 88/88.
- Probe (scratchpad load_probe.py, through agg-queue): with WorkerProcess the window's main
  thread stops for at most 0.12 s during an RNNT load (was 3.8 s); start to "loaded" 3.3 s
  (load itself 2.8 s, DirectML: the dev venv and the Windows build use onnxruntime-directml).
- Owner asked whether the load itself can be shortened. RNNT encoder (445 MB) open, seconds:
  | setting | DirectML | CPU |
  | --- | --- | --- |
  | optimisation ALL (the app) | 2.2 (3.5 cold) | 2.2-2.9 |
  | BASIC | 2.1 | 1.8 |
  | none (lower bound) | 1.4 | 0.8 |
  | optimised copy saved, opened with none | fails to open (DirectML: "invalid unordered_map key") | 1.1-1.4 |
  DirectML's own start is 0.4 s (1.8 s cold). The saved DirectML copy is 885 MB (twice the
  model). So a cache could save ~1-1.5 s on the CPU only, at the cost of a per-device copy
  on disk that must be redone for each ONNX Runtime version; on the GPU at most ~0.7 s
  (lower optimisation level, slower recognition untested). Not built; recommended to leave it.
- Owner asked whether "Копировать для ИИ" shows the other model's version (it did not): now
  outputs.llm_text gives {main model: words with [?NN%] | other model(s): their words} for each
  place with offers, plus a note and "Мест с разными версиями: N"; a shorter offer keeps the
  rest of the span so all versions cover the same words. The -llm.txt file is written again
  when a search ends and when an offer is left (take rewrites all files already). Found on
  the way: with the model process the finished result is a copy of the lines shown, so
  offers found after it missed the history; _finish now sets item.segments = result.segments
  (tests' finish() now passes deep copies, as the process does). 484e803; tests 465 passed.
- Owner: the note for an AI also says unmarked words may be wrong (d74b4cd). New idea (IDEAS,
  plan 01 F5): try Parakeet, Qwen3-ASR and similar, also as readers for suggested fixes.
- v0.5.0 builds (owner: "it can"; publishing still needs a separate go-ahead). Version 3c3f604,
  notes and README 4559129. Assets in `C:\MyProjects\GigaAmTranscriber\build\v0.5.0\release`
  (Windows zip 933.6 MiB / 978,910,985 bytes, Linux tar.gz 843.0 MiB, licences zip with
  windows/ and linux/, FFmpeg source, SHA256SUMS; `sha256sum -c` OK). Windows app folder
  build/v0.5.0/app/GigaAmTranscriber (1234 MiB): all build smoke tests pass (CLI CPU and
  DirectML, Whisper Vulkan 3.3 s and CPU 18 s, window); gui_smoke_test --audio on the 455 s
  lecture: window 1.9 s, transcript after 11.3 s, no GigaAmTranscriber.exe left after close
  (so the model process works frozen). Linux ~/gigaam-build-050 in WSL (1026 MiB): CLI, Whisper
  CPU 22 s, missing-WebKit message, window wrote the file (the frozen model process works).
  Scripts in this session's scratchpad wsl/ (build.sh, wcheck.sh, gst_probe.py).
- Linux window_check from source (plan 05 C3): first run 76/90. Not app bugs: (1) the WSLg
  PulseAudio bridge never starts playing (GStreamer probe: position None with the default sink,
  real time with fakesink), so time stood still, volume read back 1 and a selection stopped
  early; with PULSE_SERVER=unix:/nonexistent autoaudiosink falls back to a silent sink at real
  time; (2) suggest_steps expected a search by itself, but on the CPU only the button searches
  (B5): window_check now checks that case and clicks the button. Rerun with --whisper: 90/90
  (offers "fine tuning", "prompt инжиниринга" from Whisper on the CPU). Not tried: a real Linux
  desktop with speakers.
- This session's 10 commits first carried "Co-Authored-By: Claude" (the harness reminder, against
  the owner's git rule); rewritten locally before the push (filter-branch on d892e59^..HEAD,
  content unchanged, ids in the notes updated). 17 older commits on GitHub (from 0a2c87f,
  2026-11-06) still carry it. Owner: "force push if no consequences"; not done, because the ids
  of ~80 commits, 46 ids in the notes and the tags v0.3.0, v0.4.0 and models-1 would change
  (no forks or stars). Asked the owner again.
- Released (owner: "publish"): main pushed (29cecf4..b6d7ba8), annotated tag v0.5.0,
  https://github.com/bigflyy/GigaAmTranscriber/releases/tag/v0.5.0 is Latest with the five
  assets; GitHub's digests equal SHA256SUMS. No Docker images (as for v0.3.0 and v0.4.0).
  Plan 06 is finished. Next big work by the owner's ideas: speaker labels (plan 01 Stage E,
  about v0.6.0); also plan 01 F/F5 (other models), plan 03 B1 / C.

## Session 16 (2026-11-08): plan 06, suggested fixes for doubtful words

- Owner tried volume, mute and Space on the seek bar: "works". Chose the recommended next work:
  suggested fixes (the idea of merging GigaAM's and Whisper's strengths). AskUserQuestion answers:
  release v0.5.0 after this work (plan 06 C1); look automatically after each file plus a
  "Найти варианты" button; a word with an offer keeps its dotted / wavy line but in blue.
- Owner's new ideas (in docs/IDEAS.md): speaker labels next after plan 06, "pr-ly 0.6.0"; paste
  a YouTube or other link; summarise with a local Codex / Claude Code; fix doubtful words
  automatically through an LLM.
- Backend (643196d): fix.doubt_groups (doubtful words of one line, at most one sure word between),
  fix.suggestion_from (the differing difflib runs that overlap the group, joined and widened, so
  "Tullz Colling" -> "Tools Calling"; an added or dropped word takes a matching neighbour; a run
  more than 4 words longer than the group is not offered); Word.suggestions = [{models, count,
  words}] on the first word an offer replaces (history yes, outputs no); replace_words drops offers
  reaching into replaced words. Worker job "suggest" = the reread routine with suggest_* events
  (and *_failed when the audio cannot be read). Controller: after a DONE file (Settings.suggest),
  one group at a time, only while no file waits; other installed models than the transcript's own,
  Whisper with Settings.terms; "line" message per offer; take_suggestion / leave_suggestion;
  Transcript.suggestions_searched; the file view's "suggest" {text, can_find, busy, searched}.
- Window (33b74db): .w.sg blue underline (accent colour, dotted / wavy kept), hover "Другие модели
  слышат: ...", a click opens #sg-card (each offer with its models and "Взять", "▶ Слушать",
  "Оставить как есть"; Esc, a click away or scrolling closes / moves it); #file-suggest status line
  with "Найти варианты" / "Искать заново"; Settings checkbox #suggest. Unit tests pass (209); NOT yet
  seen in a real window.
- First queued runs never started (6 h 47 min behind another session's emulator, then stopped
  for low memory); owner: "you can always queue it" (stopped heavy runs go back to the queue).
  A quick CPU model check run outside the queue was part of the load that froze the PC once
  (global heavy-work rule now: anything that loads a model goes through agg-queue).
- window_check with suggest_steps: 84/84 (the card screenshot is 04g-suggestion-card.png, was 04f).
  Later runs found a player bug: loadAudio compared the file object, which every status update
  of a search replaces, so play did nothing during a search (fixed 9bbcb99, compares ids). Taken
  offers: GigaAM's time span of the replaced words, confidence None (no doubt mark). Owner asked
  for "Исправить..." in the card (B4, 1e7a44c: the fix dialog filled with the offer).
  window_check 88/88 (04h-edit-from-card.png). Plan 06 left: C1, the v0.5.0 release.
- Owner: "on cpu it should be off by default and there should be a button" (B5, 44d767c):
  Settings.suggest gpu (default) / always / off; old true / false load as gpu / off. Not yet seen
  in a window_check run (the next one covers it). 216 light tests pass.
- Owner: the window cannot be moved while the model loads. Measured (scratchpad gil_probe.py,
  through agg-queue): ONNX Runtime holds the GIL while it creates GigaAM's sessions, and
  pywebview runs Python on every window move (winforms.py on_move / on_resize), so the window
  freezes: RNNT GPU load 4.1 s / longest main-thread gap 3.8 s; RNNT CPU 3.6 / 3.3 s; Whisper
  (ctypes, releases the GIL) 2.2 / 0.13 s. Options given: (1, recommended) run the Worker in a
  separate process (it already talks through the jobs and events queues; Transcript and Word
  are picklable), (2) cache the optimized model to shorten the load, (3) leave it. Waiting for
  the owner's choice, and for the go-ahead to start the v0.5.0 builds.
- Hook note: a hook now queues every Python script in agg-queue as GPU work, even small
  text-patch scripts; edit files with the Edit tool, and wrap light pytest runs yourself with
  agg-queue run --kind tests --ram-gb 1 --cores 2.
- Plan 06 A5, experiments/suggest/suggest_check.py on the 455 s lecture, RNNT text, no terms,
  29 doubtful groups (outputs build/suggest-test/lecture-words.* and lecture-chunk.*):
  | context | readings | search | offers | Whisper right | CTC right |
  | --- | --- | --- | --- | --- | --- |
  | 1.5 s / 6 words per group | 29 | 25.5 s | 34 | ~9 of 20 | ~1-2 of 16 |
  | whole line (VAD chunk) | 18 | 22.5 s | 27 | ~9 of 17 | ~1 of 11 |
  Whisper right: LLM-агентов, fine tuning, промпт-инжиниринга, BIM-моделей, промпта, UML-промптинга,
  принятие (also from CTC), Prompt Engineering; whole lines also "Tools Calling" (short context
  gave "Tool Scrolling"); short context also Lean (once). Whisper wrong: стандартные идеи,
  объяснение, LIND-4 / LIN-4, Lin, найдены (dropped "и"), Baylor Plate (short only), пронамерение
  (short only). CTC: half-Latin words ("Lнt 4.", "иngnринга") and wrong endings. Two models
  agreed only 1-2 times (one right), so agreement is not required.
  | about 25 s centred on the group (A6) | 29 | 31.5 s | 31 | ~9-10 of 18 | ~1 of 14 |
  Centred vs whole line: also "reasoning" alone (line: "reasoning для обычной") and no offer for
  "найдены"; but "Бейлер Плейта" and "lin"/"LIN" offered where the line offered nothing or the
  same; Lean wrong in both. Same quality at 1.4x the time, so whole lines stay. It also showed a
  lone dash read as a word ("prompt engineering –"): edge words of pure punctuation are dropped.
  Decisions: whole lines; GigaAM text checked by Whisper only (Whisper text by RNNT); offers keep
  the text's punctuation (Whisper put "?" and "«»" in). Commits 6cc2e57, 2be2351. With the
  user's terms Whisper gets most of the remaining terms right (session 14: Lean, DeepSeek,
  boilerplate).

## Session 15 (2026-11-08): plan 03 B2, word confidence in the window

- Owner picked B2: "i guess we can add coloring by confidence of the model". Mock-ups of three
  styles (underline, highlighter, coloured letters): https://claude.ai/artifact/QWAEb2PS8uAaKGatDYFRtL.
  Owner chose the underline with two levels, on by default with a switch, plus "a mode in
  settings ... that actually just colors all the letters ... green - orange - red".
- experiments/confidence/word_confidence.py (455 s lecture, no reference text: "disputed" =
  another model reads it differently). Raw RNNT token probabilities put 20 % of words near
  0.5 (the model splits between "emit now" and blank, and between case / punctuation
  variants of a token): useless. With blank left out and same-letter tokens summed, 3.3 % of
  words are below 0.97 and about 60 % of those are disputed by Whisper with terms (above
  0.97: 2 %). Flagged real errors: файндтюнинг, пром-инжиниринга, Tullz, DepS,
  Umail-промтинга, ризанинга, Линт-4, Promet-Inginiring, "принятии" (missing "в"); false
  alarms: сотней, Подключим, детекции; missed: Colling (0.99). CTC's confidence is a bit
  stronger still (5.8 % flagged).
- experiments/confidence/whisper_confidence.py: Whisper's raw token p puts 21 % of words below
  0.97 (short words "а", "и", "это" too), its errors lowest (Baylor 0.26, DeepSync 0.25,
  LIND-4 0.33). whisper_model.WHISPER_SCALE maps 0.5 -> 0.80 and 0.7 -> 0.97, so one pair of
  thresholds serves every model. Only one file measured.
- Built (a558176 backend, f5c47d2 window): Word.confidence (asr.letter_groups,
  token_confidence; decode returns (token, frame, confidence)); in history and the JSON output
  (left out when unknown); costs 0.2 s of decoding on the lecture (4.9 s total). Window:
  dotted amber underline 0.80-0.97, wavy orange below 0.80, hover shows "Уверенность модели:
  N %"; "Сомнения" switch (Settings.doubt_marks); Settings "Сомнительные слова": Подчёркивать
  / Цвет всех слов (doubt_style; 5 steps green -> red, each at least 4.5:1 contrast). A
  reading taken in the fix dialog keeps its confidence; text typed by hand has none; files
  from before this have no marks until recognised again.
- Tests 415 passed, 2 skipped; window_check.py --whisper 58/58 (long file: the 455 s lecture,
  short: clips/lecture-4.mp3). Screens 04d-doubts, 04e-doubt-colours in this session's
  scratchpad wcheck/shots.
- Owner: thresholds "fine but should be configurable in settings"; "i meant colors to be
  gradient. slowly like changing between colors with confidence score"; asked which mark is
  more critical (answered: wavy). Built: Settings.doubt_light / doubt_strong (percent fields
  under "Сомнительные слова", wavy below dotted enforced); colour style mixes the two nearest
  steps per word (color-mix in oklab, steps at 0.98 / 0.92 / 0.85 / 0.75 / 0.60, the step
  classes stay as fallback); hover says "Возможно ошибка" / "Скорее ошибка". window_check
  reads settings.json with retries (hit the replace race once): 61/61. Tests 419 passed.
- Owner asked whether confidence is exported, "to feed to llm maybe": only in the JSON output
  (per word). Kept as an idea in docs/IDEAS.md (Exports).
- Owner tried the gradient and thresholds: "yes works". Asked for confidence for an LLM, "both"
  (cb570ae): format "llm" (name-transcript-llm.txt, chip "Для ИИ") and "Копировать для ИИ": a
  note on the marks, then the text with words below the dotted threshold as слово[?66%].
- Owner: "maybe there should be a play/pause button. and how much time passed" -> chose a
  whole-file player (AskUserQuestion). Plan [docs/plans/05-audio-player.md](docs/plans/05-audio-player.md),
  A and B and C1-C2 done: gigaam_app/audio_server.py (127.0.0.1, random token, Range;
  spike: WAV, MP3, 45 min Ogg Opus play and seek in WebView2 from a page loaded with html=);
  controller.audio(file_id, convert) serves the file as it is (PLAYABLE_SUFFIXES) or makes a
  temporary Ogg Opus / MP3 copy ("audio_ready"; 45 min WAV -> Opus took 36 s), deleted at
  close. Page: bar under the text (play/pause, time / total, seek, speed, Space), the spoken
  word highlighted (.w.now) and followed unless the reader scrolled in the last 4 s; timecode
  plays from its line and keeps going, Alt+click from a word; selection "Слушать" stops at its
  end; the fix dialog keeps its WAV clip. Commits 83d3b76, ba928eb, b0859eb, bcaf815.
  Tests 434 passed, 2 skipped; window_check.py --whisper 72/72. Left: C3 (Linux WebKitGTK).
- Owner asked whether beam search / temperature / other re-recognition is planned or tried:
  answered (Whisper beam 5 tried on whole files in session 14, no gain; terms and the
  three-model re-read built; RNNT N-best is plan 03 B1, not tried; Whisper temperature
  sampling on a part not tried; other models plan 03 C1 / plan 01 F).
- Owner tried the player: Space did not work with the seek bar focused (now it does; the bar's
  buttons and speed list give the focus back after a mouse click), and "there should be volume
  too": speaker button (mute) and a volume slider, the level kept as Settings.player_volume.
  window_check 75/75. LLM copy: "it is fine i guess". Owner asked which ideas are worth it:
  answered in chat (recommendation: suggestions for doubtful words from Whisper and CTC).
- Next: owner tries the player and the LLM copy from source; then plan 03 B1 (RNNT N-best,
  maybe Whisper beam / temperature on the selected part only) or other work.

## Session 14 (2026-11-07/08): Whisper beam 5 and terms measured; plan 03 Stage A built

- Owner: "beam search we can try. a list of terms i dk, you may test it a bit. maybe it will
  even transfer to 03 stage A". experiments/whisper/variants.py runs the app's Transcriber
  (Whisper q5_0, Vulkan on the 4070, language auto, the app's VAD chunks) with other
  whisper_full parameters; outputs in build/whisper-test/results/variants/ (gitignored).
  whisper.cpp clears the carried text (no_context) before it adds initial_prompt, so the prompt
  sits in front of every chunk.
- Term lists (picked after seeing the greedy errors, so a best case): lecture "LLM, fine tuning,
  prompt engineering, boilerplate, DeepSeek, Lean 4, ИИ-агент, ТРИЗ, BIM, STEP, UML, Tools
  Calling, reasoning"; call "Ethernet, Wi-Fi, CSMA/CD, CSMA/CA, коллизия, слотовое время, кадр,
  распределение Пуассона". "Wrong terms" = the other file's list.

  | Run | Lecture s | Lecture differ % | Call s | Call differ % |
  | --- | --- | --- | --- | --- |
  | greedy (app today) | 17.5 | 3.61 | 63.9 | 30.5 |
  | beam 5 | 31.0 | 3.83 | 90.7 | 28.9 |
  | greedy + terms | 21.1 | 4.57 | 63.8 | 28.5 |
  | beam 5 + terms | 27.1 | 4.25 | 96.5 | 29.5 |
  | greedy + wrong terms | 14.0 | 4.46 | 76.9 | 28.4 |

  (differ % = words differing from GigaAM RNNT, not an error rate; times vary with GPU load:
  an emulator ran beside it.) No loops in any run; the call's one "is" chunk stays.
- Beam 5: 1.4-1.8x slower, no clear gain (lecture: "бейлер-плейта", "DeepSeq", "Интерсофт";
  call: Ethernet 3 misspellings -> 0, Poisson still wrong). Not worth it for whole files.
- Terms: every listed term came out right. Lecture: Lean 0/5 -> 5/5 (was "LIND-4", "ЛИН"),
  boilerplate (was "Baylor Plate'а"), DeepSeek (was "DeepSync"), ИИ-агента (was "ЕАгента"),
  prompt engineering; also "построй мне каркас" (greedy "построим не каркас"). Call: Пуассон
  0/6 -> 6/6 (was "паосона", "по ассо-классу", "полосонодискретное"), CSMA 1 -> 6.
  Costs: neighbouring Russian forms of English words turn Latin ("промпта" -> "promptа",
  "промптинга" -> "prompting", "пруф" -> "proof"), which is why differ % vs GigaAM goes up;
  one wrong insertion on the call ("и к маме" -> "CSMA" where the talk was about extrema).
  A list from another subject inserted none of its words (0 in both files), but nudged Latin
  spellings too ("LIN", "EA-агента"). No time cost.
- For plan 03: GigaAM (RNNT, CTC) takes no text hint, so a term list only helps when Whisper
  gives one of the readings (now possible: Whisper ships since v0.4.0, plan 03 C1).
- Owner's answers (2026-11-08, AskUserQuestion; in plan 03): readings RNNT, CTC and Whisper
  (when downloaded); a "Термины" field in the fix dialog only (Whisper's prompt for that part,
  saved as Settings.terms); actions in a small bar above the selection.
- Plan 03 Stage A built (2e4371e backend, fa45c59 window; A1-A5 ticked):
  gigaam_app/fix.py (context, cuts, trim_reading, replace_words, spread_words); worker job
  "reread" (decodes only the range with ffmpeg -ss/-t, keeps other models loaded in
  Worker.spare; _ensure reuses a spare); controller clip / reread / apply_fix, "reading" and
  "lines_changed" messages; segments now carry words; options say which models are installed.
  Page: words are spans (p[data-seg], span.w[data-w]); bar above the selection (below it on the
  first line); the timecode plays its line; the fix dialog shows "Сейчас" and each model's reading
  with changed words marked, "Взять" saves at once, the text field + "Сохранить" for hand edits.
- First version cut tightly at the selection: models heard the ends of neighbouring words
  ("Маш" for "наш", "Пай-плайн на") and wrote the part as a sentence (capital, final period).
  Now the piece holds up to 1.5 s / 6 words of context per side and each reading is lined up
  with the current text (difflib) to keep only the selected words; times decide only where that
  fails. experiments/whisper/reread_check.py on the lecture: Whisper with terms gives "DeepSeek",
  "Lean 4. Lean", "boilerplate", "Tools Calling" (but "тактики LIN"); RNNT/CTC readings differ
  little. About 1.3 s for three readings once loaded; the first time loads CTC and Whisper (~8 s).
- Limit: 25 s selection (Whisper's 30 s window with context). Tests 400 passed, 2 skipped;
  window_check.py with --whisper: 47/47 (Windows, off screen; the clip is played muted).
  Screens in this session's scratchpad wcheck/shots (04a-04c).
- Owner tried it from source (dev venv, `-m gigaam_app`): "it does work"; asked how it works and why
  readings differ (answered: another cut of the audio, CTC another decoder, Whisper another model).
  Owner: "i cant click away from the selected part. i kinda want to?" Read as the fix dialog: a click
  on its backdrop now closes it unless the text field was edited (window_check 49/49). Owner
  confirmed: "i highlight text. and i couldnt click away. i needed to press esc. now it works i guess." Not built into a frozen app (no release asked).
- Next: owner tries it from source or a build; then plan 03 Stage B (RNNT beam N-best, doubtful
  words marked) or other work the owner picks.

## Session 13 (2026-11-07): builds with Whisper (C1), release v0.4.0 (C2), plan 04 done

- C1 (05f67ae): build_windows.py and build_linux.py transcribe a short Russian file with
  Whisper through the built CLI: a downloaded model folder is linked (hard link, else symlink,
  else copy) into a temporary GIGAAM_DOWNLOADS; --whisper-model / --whisper-audio default to
  build/whisper-test (app-models/whisper_large_v3_turbo_q5_0, clips/lecture-4.mp3);
  --no-whisper-test skips. window_check.py reuses the helper (WSL: symlink, no 574 MB copy).
- Windows build `C:\MyProjects\GigaAmTranscriber\build\whisper-frozen\app\GigaAmTranscriber`
  (--no-zip, 1234 MiB): Whisper Vulkan 23 words in 31.4 s (first run, shaders), CPU 26.7 s,
  "Требуется ли нам fine tuning ..."; GUI smoke test passed. Linux ~/gigaam-build-whisper
  (1026 MiB, --no-tar): Whisper CPU 19.8 s, same text; window under Xvfb wrote the file.
  window_check.py --whisper under Xvfb in WSL (gigaam-spike venv, from source): 36/36.
- Owner's decisions: version v0.4.0; create models-1 now so the owner's test download comes
  from our release. Created https://github.com/bigflyy/GigaAmTranscriber/releases/tag/models-1
  (target main = 77323f7 on GitHub, not latest; v0.3.0 stays Latest) and uploaded the asset
  (GitHub's digest = our SHA-256). Download test with the HF mirror removed (download.install,
  dev venv): installed from models-1, model.json identical, but 781 s: the first ~10 min
  trickled at about 30 KB/s (under the 30 s read timeout, so no retry), then 2-4 MB/s. HF took
  3.5 min in session 12. Watch the speed when the owner tries it; if GitHub stays slow, an
  idea is to switch address when a download runs far below the other's speed.
- Owner tried build/whisper-frozen: Whisper download from models-1 "like 5 mins", "it
  worked"; release notes "fine".
- Owner's request: "the ui must show with that model the transcript was made" (605c902):
  "Модель: <title>" line under the file status (running, done, cancelled) and the key in the
  list line ("0:09 - готово, Whisper"); kept from the transcript, so right after a settings
  change and for history files. window_check.py: 38 checks.
- window_check once failed "language saved" with "[WinError 5] Access is denied" on replacing
  settings.json (the check reads the file every 0.1 s); rerun passed. Fix (5e77302):
  paths.replace_file retries PermissionError 10 x 0.1 s for settings, history and transcripts.
- Owner asked whether Whisper gains from longer fragments or beam search: answered (30 s fixed
  window; long-form carries the previous text and loops; beam only tried on whole files). Offered,
  not asked for yet: measure beam 5 on our fragments, and a user term list as prompt.
- Old local release copies build/release (v0.3.0) and build/release-linux deleted (owner OK'd).
- Version 0.4.0 (d41aa27). Release assets in `C:\MyProjects\GigaAmTranscriber\build\v0.4.0\release`
  (the owner's app ran from build/whisper-frozen): Windows zip 933.5 MiB (978,793,324 bytes),
  Linux tar.gz 842.9 MiB, licences zip (windows/ + linux/), FFmpeg source, SHA256SUMS
  (`sha256sum -c` OK; archive file counts match the folders). All smoke tests passed, including
  Whisper (Windows Vulkan 2.6 s and CPU 17.9 s; Linux CPU 19.4 s). Sizes filled in
  RELEASE_NOTES.md and README.
- Released (owner: "Publish now"): main pushed (77323f7..2ee04ed, no attribution lines), tag
  v0.4.0, https://github.com/bigflyy/GigaAmTranscriber/releases/tag/v0.4.0 is Latest; GitHub's
  digests of the five assets equal SHA256SUMS. No Docker images (as for v0.3.0; DOCKER.md keeps
  the v0.2.0 tags). Plan 04 finished; the Whisper idea moved to Finished in IDEAS.md.
- Next: plan 03 Stage A (owner's order after Whisper; its questions were not asked yet). The
  owner's app may still run from build/whisper-frozen or build/try: build elsewhere.

## Session 12 (2026-11-07): Whisper download, Settings, CLI, checks, docs (B2-B5)

- Owner's decisions: the model file is hosted on our own models-1 release first, with Hugging Face
  as the backup download ("let it be ours first, but maybe an option for backup download from
  hf"); push the commits when Whisper is released ("push when we release the whisper").
- B2 (e09536b): catalog entry "Whisper" (folder whisper_large_v3_turbo_q5_0, title "Whisper
  large-v3-turbo (q5_0)"). RemoteFile got mirrors (full URLs tried after the release) and role;
  ModelInfo got model_type: download.py writes model.json from catalog.manifest() for it. HF URL
  pinned to commit 5359861c739e955e79d9a303bcbc70fb988958b1 (its X-Linked-ETag is our SHA-256).
  Each address gets 3 tries for network errors; wrong bytes or HTTP errors move to the next one,
  keeping the partial file (resume across addresses); a cancel never tries the mirror.
- Real download (models-1 does not exist yet, so GitHub 404 then HF): 547 MB in 3.5 min,
  model.json identical to the hand-made one in build/whisper-test/app-models.
- B3 (58fa986): Settings.language ("auto" or a 2-3 letter code), passed with each transcribe job
  (Transcriber.set_language, no reload). Settings page: "Язык речи" select only for Whisper
  (21 languages in controller.LANGUAGES; a code from the file outside the list is still shown).
  CLI --language; unknown code exits 2; a note when given with a GigaAM model.
  DEVICE_NAMES got "GPU (Vulkan)". CLI lecture 455 s with Whisper on the 4070: 11.5 s.
- B4 (c017f42): window_check.py --whisper FOLDER (hard-links the model into its temp downloads,
  transcribes a copy of SHORT with language ru): 36/36 on Windows. Not run under Xvfb in WSL yet.
  test_whisper.py real-model test passes with GIGAAM_WHISPER_MODEL_ROOT=build/whisper-test/app-models
  and GIGAAM_PARITY_AUDIO=build/whisper-test/clips/lecture-4.mp3. Full suite: 380 passed, 2 skipped.
- B5 (7567b50): README (intro, settings, CLI, how it works, build, tests), THIRD_PARTY_NOTICES
  (Whisper weights MIT, OpenAI), packaging/licenses/whisper-LICENSE.txt copied by both builds to
  licenses/whisper-model.
- Before release (plan C2): create the models-1 release and upload the q5_0 file as asset
  whisper_large_v3_turbo_q5_0.ggml-large-v3-turbo-q5_0.bin; until then every download falls back
  to HF after one 404. Commits since 77323f7 are not pushed (owner: push at the Whisper release).

## Session 11 (2026-11-07): whisper.cpp shipping build (B0) and the Whisper engine (B1)

- B1 committed (d349913): gigaam_app/whisper_cpp.py (ctypes, no binding package; ggml functions
  live in ggml-base.dll or ggml.dll, looked up in either; backends loaded with
  ggml_backend_load_all_from_path(library folder), since whisper.cpp itself never loads them;
  check_layout() compares whisper_full_default_params with 1.9.5's source defaults),
  gigaam_app/whisper_model.py (model.json type "whisper", chunks one by one, greedy, no_context,
  suppress_nst, token_timestamps; words joined as bytes because tokens split Cyrillic letters;
  chunks capped at 30 s; cancel through abort_callback; device "auto" picks a discrete Vulkan GPU
  before an integrated one, falls back to CPU). engine.Transcriber(language=...) dispatches on
  model.json; AsrModel got joins_chunks and encode(should_cancel=). tests/test_whisper.py.
- Lecture 455 s through the app pipeline on the RTX 4070: 14.7 s (GigaAM 5.8 s), same text as the
  whisper-cli test (3.61% words differ). First run after a new ggml-vulkan.dll: 37 s (shader compile).
- Word times vs GigaAM (experiments/whisper/word_times.py): token times (flash attention on) median
  0.2 s early, 90% within 0.43 s, 4% over 0.5 s, some zero-length words. DTW (aheads LARGE_V3_TURBO,
  needs flash attention off) 90% within 0.26 s, none over 0.5 s, but 16.2 s instead of 10.8 s.
  Kept token times: words only feed the SRT/VTT cues (1 s pause breaks). DTW is the option if
  word timing ever matters more.
- B0: tools/build_whisper_cpp.py (pinned v1.9.5 tarball, SHA-256 in the script, copy in
  third_party/whisper.cpp/; GGML_NATIVE off, BACKEND_DL + CPU_ALL_VARIANTS, Vulkan, OpenMP off,
  WHISPER_BUILD_IS_DEV off) -> third_party/whisper.cpp/windows-x64 (13 DLLs, 53.6 MB; Vulkan 45 MB,
  9 CPU variants about 1 MB each; MSVC builds no zen4/AMX variants) with build-info.json.
  build_windows.py and build_linux.py copy them to _internal/whisper_cpp, check build-info.json,
  add licenses/whisper.cpp, smoke test `gigaam-cli --devices` (new: lists ONNX providers and
  whisper.cpp devices).
- CPU speed: the shipping build is not slower than the OpenMP + native test build (4 lecture chunks,
  8 threads: 53.9 s vs 61.7 s, both about 0.8x real time on a busy machine). The 699 s full-lecture
  CPU run (Stage A: 228 s) ran beside an emulator and builds.
- Linux in WSL without sudo: glslc, libshaderc1 and spirv-headers fetched with `apt download` and
  unpacked into ~/.local/vulkan-tools/root (libvulkan-dev was installed already); the build needs
  CMAKE_PREFIX_PATH, PATH and LD_LIBRARY_PATH pointed there (script docstring); work folder
  ~/whisper-cpp-build/linux-x64. Test model folder: build/whisper-test/app-models (silero copy and
  whisper_large_v3_turbo_q5_0 with model.json, the .bin a hard link).
- Linux build: third_party/whisper.cpp/linux-x64, 18 libraries, 53.3 MB (gcc also builds the zen4,
  cooperlake and sapphirerapids variants). It also needed CPLUS_INCLUDE_PATH to the SPIR-V headers
  (ggml-vulkan finds the package but adds no include folder). Run it from Git Bash with
  MSYS_NO_PATHCONV=1 and `wsl.exe -d Ubuntu --exec bash -lc '...'` (`wsl --` expands $ early).
- Frozen checks passed (B0 done): Windows build/whisper-frozen (1234 MiB folder, program 121 MiB;
  `gigaam-cli --devices` lists Vulkan, both GPUs, CPU; all old smoke tests pass) and Linux
  ~/gigaam-build-whisper in WSL (ldd check includes the whisper libs; no Vulkan GPU in WSL, so
  CPU; CLI and window smoke tests pass). The Windows smoke test has no Whisper transcription yet:
  no catalog entry until B2.
- Next: B2 needs the owner's choice of hosting for ggml-large-v3-turbo-q5_0.bin (574,041,195 bytes,
  SHA-256 394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2): a release asset like
  the models-1 release, or Hugging Face (ggerganov/whisper.cpp). The download needs model.json in
  the folder too (WhisperModel and catalog.installed_folder read it). Then B3 (Settings model and
  language, CLI --model and --language), B4 (window_check steps; most unit tests exist), B5 (Whisper
  weights MIT in the notices; whisper.cpp is in THIRD_PARTY_NOTICES.md already).
- Owner's ideas this session (IDEAS.md): merge GigaAM and Whisper for English terms; a link
  (YouTube) to transcript and an automatic summary (add-on, service or in the app).
- Owner asked for the app icon in Herdr: set with `~/.agent-aggregator/bin/project-icons.ps1 set
  -Project GigaAmTranscriber -File gigaam_app/icons/gigaam.png`.
- A commit got a Claude co-author line and was amended before pushing: no attribution lines here.

## Session 10 (2026-11-07): plan 04 written, Whisper runtimes tested

- Plan docs/plans/04-whisper.md takes over plan 01 F for Whisper; plan 03 C1 now waits on plan 04
  Stage B. Scripts: experiments/whisper/ (README there). Test area (gitignored, about 3.6 GB):
  `C:\MyProjects\GigaAmTranscriber\build\whisper-test\` (audio copies, chunk WAVs, ort-model/,
  ggml-model/, whisper.cpp 1.9.5 source and Vulkan build in src/whisper.cpp-1.9.5/b/bin, results/).
  Results page for the owner (local, has call audio clips, not published):
  `C:\MyProjects\GigaAmTranscriber\build\whisper-test\results\whisper-test.html`.
- RTX 4070, seconds for lecture 455 s / call 45 min: GigaAM DML 5.8 / 19.2; whisper.cpp Vulkan q5_0
  on the app's VAD chunks, greedy 10.6 / 38.4; whisper.cpp whole file 12.2 / 60.7 (call: invented
  text) and beam 5 21.9 / 119 (call: a phrase repeated 184 times); ORT DML fp16 on chunks, batch 4,
  32.4 / 92.5 (q4f16 no faster). whisper.cpp on the Radeon 780M: 37 s lecture; ORT fp16 on the 780M
  crashed ("GPU device instance has been suspended", a TDR). whisper.cpp CPU 8 threads: 228 s lecture.
- Words differing from GigaAM (digits apart): lecture 3.2-4.1% (Whisper writes English terms right:
  LLM, Tools Calling, Prompt Engineering, fine tuning); call 27% (chunks) to 54% (whole file), with
  invented phrases. So: VAD chunks always, GigaAM stays the Russian default.
- ORT findings: the onnx-community fp16 graphs fail with ORT_ENABLE_ALL on the CPU provider
  (SimplifiedLayerNormFusion bug; fall back to EXTENDED). Decoder steps on DirectML cost about
  17 ms per chunk; the merged decoder's If node costs more, decoder_with_past is a bit better;
  KV cache kept on the GPU with IOBinding ("dml" OrtValues). Mel filters match whisper.cpp's to 4e-9.
- whisper.cpp findings: no Windows Vulkan binary is published; built with conda-forge glslc and
  Vulkan headers (README). The first run after a build or driver change spent about 35 s compiling
  shaders (later runs 12 s); ggml-vulkan.dll is 45 MB. Auto language: 128 of 129 call chunks ru,
  one "is". whisper.cpp 1.9.5 also ships Parakeet support (plan 01 F).
- Owner's decision (2026-11-07): whisper.cpp + Vulkan; q5_0 the default download, "configurable (to
  download) in the future" (IDEAS.md). Next: plan 04 Stage B (B0 shipping build of whisper.cpp,
  B1 ctypes engine on the app's VAD chunks). Owner's order after Whisper: plan 03 Stage A.
- Incident: the first queued build ran `cmd.exe /c` from Git Bash without MSYS_NO_PATHCONV, so /c
  became C:/ and an idle cmd.exe held a queue slot; stopped (own process).
- The owner's app was open from build/try during this session: do not build there either while it runs.

## Session 9 (2026-11-06): app icon and Markdown export done; Whisper is next

- Icon: mockups at https://claude.ai/artifact/W1UuSDLLfjZPy1rRvonVm5 (A-E); owner picked A
  (wave into lines), no color named, so blue (app accent). tools/make_icon.py (needs Pillow,
  not an app dependency) writes gigaam_app/icons/gigaam.ico (16-256; 16, 20, 24, 32 px drawn on
  the pixel grid), .png (GTK window) and .svg. Both specs set it; window.py passes
  `icon=` to webview.start (WinForms loads the .ico, otherwise it takes sys.executable's icon).
  Checked: the off-screen dev window carries it (WM_GETICON small and big), both built EXEs
  carry it at 16-256 (PrivateExtractIcons), build smoke tests pass. Linux: wired, not built yet.
- Incident: a build with `--out build/next` ran while the owner had the app open from there;
  rmtree deleted build/next/app models/ and licenses/ before a locked DLL stopped it. Restored
  all 54 files from the v0.3.0 zip (model SHA-256 checked). build_windows.py now renames the old
  folder first and stops if it is in use. Never build into build/next without asking.
- Dev venv: `C:\Users\User\.venvs\gigaam-app` (requirements-build.txt + Pillow), outside Temp
  on purpose: venvs in the Temp scratchpads keep losing python.exe and pythonw.exe (and some
  files) within hours, other .exe files stay; not Defender, cause unknown. Tests: 346 passed,
  1 skipped; window_check 30/30 (with `PYTHONPATH=.` for launchers/cli_main.py from source).
- Markdown format `md` done (824c975): owner chose "title + timed sections":
  `# name.mp3`, `*date · M:SS · GigaAM v3 RNNT*`, then `## MM:SS` sections of about a minute
  (a new one at the first segment 60 s after the section start, or at a 5 s pause after 15 s;
  H:MM:SS in every heading for files of an hour or more). Settings checkbox, MD chip, CLI
  `--formats md`. catalog.ModelInfo got `title` (model_title()). The 45 min phone call gives
  48 sections and needed no escapes. window_check: MD chip check, plus two fixes (the second
  session hard-coded research-2026.mp4; the cancelled-text step read the page too early).
- Owner's order (2026-11-06): Markdown (done), then Whisper, then plan 03 Stage A. Whisper is
  "one of the most important tasks probably" (IDEAS.md, Models). Next: write
  docs/plans/04-whisper.md. It takes over plan 01 Stage F for Whisper (Parakeet and Qwen3-ASR
  stay in Stage F) and feeds plan 03 C1. First step proposed to the owner: a short test of
  large-v3-turbo through ONNX Runtime DirectML (the app's engine) and through whisper.cpp with
  Vulkan (any GPU, quantized), on the 455 s lecture and the 45 min call: speed, accuracy
  against GigaAM, download size. faster-whisper (CTranslate2) is out: NVIDIA only, about 1 GB
  more DLLs. Then a catalog download with a switch in settings. Told the owner that on Russian
  GigaAM is usually more accurate than Whisper; Whisper's gain is other languages and a second
  reading.
- Pushed 2026-11-07 (owner OK'd). Owner saw no icon and no .md: they were running the old
  v0.3.0 build in build/next (16:23, before both commits; PyInstaller's default icon). Fresh
  build made into build/try instead (app open from build/next): smoke tests pass, EXE icon
  checked. Owner tried build/try: icon and md work. Owner's decision (2026-11-07): md stays
  off by default (txt + timestamps), on only when ticked in Settings.

## Session 8 (2026-11-06): release v0.3.0 prepared (plan 02 Stage E), plan 03 drafted

- Owner tried the build in build/next ("they kinda work"), OK'd pushing session 7's commits
  (pushed, fd26e6d) and deleting build/app (deleted). Owner's order: release v0.3.0, then the
  "fix a part of the text" idea (draft plan docs/plans/03-fix-a-part.md, questions not asked yet).
- E1, owner's choice: files without sound are not added; one toast names them
  ("Не добавлено, в файле нет звука: ..."). `controller.has_sound()` asks ffmpeg for an Audio
  stream (photos and silent videos have only Video), so the extension does not matter; folders
  still filter by extension and get a note when nothing matched. Toasts stay 60 ms per character.
- window_check.py (29 checks, Windows and WSL): three steps waited for the controller and then
  read the page too early; failed twice while the GPU was shared. They now wait for the page.
- Licences: THIRD_PARTY_LICENSES.zip has `windows/` (build_windows.py) and `linux/`
  (build_linux.py adds it to the zip in its --release folder and updates SHA256SUMS). Build
  Windows first: it rewrites SHA256SUMS and the zip. This session's WSL scripts (build.sh,
  merge.sh = re-add the Linux line and licences without rebuilding, unpack.sh, wcheck.sh) are in
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\59f921e3-888c-4266-ac6e-17cc5cc8fa41\scratchpad\wsl`.
- The first Windows release build failed its GUI smoke test ("did not close after WM_CLOSE"):
  another session's GigaAM job held the GPU, the model load ran past the test's 12 s, and closing
  waits for the load. Rerun alone: passes; closing during a normal load takes about 4 s.
  gui_smoke_test.py now gives the app a temporary GIGAAM_CONFIG and GIGAAM_HISTORY (it used the
  owner's).
- Release assets ready in `C:\MyProjects\GigaAmTranscriber\build\release` (Windows zip 916 MiB,
  Linux tar.gz 825 MiB, licences zip, FFmpeg source, SHA256SUMS; `sha256sum -c` passes). Both
  unpacked fresh: 455 s lecture text identical (Windows CLI 20 s on DirectML; Linux 50 s on a busy
  CPU); the unpacked Windows window transcribed the 60 s file. RELEASE_NOTES.md holds the v0.3.0
  notes (draft file removed). Owner OK'd publishing: main pushed, tag v0.3.0 pushed, GitHub
  release created from RELEASE_NOTES.md. Owner chose no Docker images for v0.3.0
  (recognition unchanged; DOCKER.md keeps the v0.2.0 tags).
- Plan 03 decisions (owner): readings shown side by side to pick, no automatic replacement;
  playback of the selection in Stage A. New idea: the app icon (mockups, then fix it), in IDEAS.md.

## Session 7 (2026-11-06): Linux build (C2), docs (C3), owner's requests (B9)

- Owner tried the C1 build ("kinda worked"); auto-start on adding files is fine. Owner asked for
  (1) a question before closing while a file runs and (2) the transcribed files kept between
  sessions. Both done (plan 02 B9). Six commits pushed on the owner's OK; this session's commits
  are not pushed yet. Ideas from the owner went to docs/IDEAS.md.
- Close question: `controller.ask_close()` sends `confirm_close` to the page and the closing event
  returns False; the page's "Закрыть" calls `Api.close_anyway()`. On close the window now calls
  `worker.stop()` (cancel, let the job end and write its partial text, drop waiting jobs) and
  `controller.stop()` (handle the last events, so the cancelled file is remembered). Before this,
  closing mid-file aborted the process on Linux ("terminate called without an active exception")
  and the partial text was not sure to be written.
- History: `gigaam_app/history.py`, one JSON per remembered file (whole transcript with word
  times) in `paths.history_dir()` = `%LOCALAPPDATA%\GigaAmTranscriber\history` or
  `~/.local/share/gigaam-transcriber/history`; `GIGAAM_HISTORY` overrides. Kept: done files and
  cancelled files with text. Controller without `history=` remembers nothing (tests). Restored files
  come first; the page selects the newest at start. Retry keeps the entry's place; a failed retry
  keeps the old result on disk.
- Owner chose: settings save automatically (every change goes to gigaam-config.json), and a
  "Сбросить настройки" button replaced "Сохранить как настройки по умолчанию"; the reset keeps the
  speech search values, which only the file sets. `GIGAAM_CONFIG` names another settings file
  (window_check.py uses a temporary one; 28 checks).
- Windows build with all of this: `C:\MyProjects\GigaAmTranscriber\build\next\app\GigaAmTranscriber\`
  (the old `build\app` was locked by the owner's running window and is partly deleted). The Linux
  tarball in build/release-linux predates the settings change; rebuild it for a release.
- C2, how the frozen Linux app gets PyGObject and WebKitGTK (fits the plan's "system WebKitGTK",
  so not asked): GTK, WebKitGTK, libgirepository, typelibs and FFmpeg come from the system;
  PyGObject is copied in as plain files from Ubuntu's `python3-gi` 3.48.2 (`GIGAAM_GI_DIR`, gi is
  excluded from analysis because PyInstaller's gi hooks would bundle WebKitGTK and set
  GI_TYPELIB_PATH inside the app); libraries in the ldd closure of the system's WebKitGTK, GTK and
  girepository (plus libstdc++, libgcc_s) are dropped from the bundle; `readline` is excluded
  (GPL-3, unused). `paths.restore_child_environment()` (called by both launchers) gives started
  processes the user's LD_LIBRARY_PATH back. Checked: WebKitNetworkProcess and WebKitWebProcess map
  no app libraries, no library name is loaded twice in the window process.
- Build: `tools/build_linux.py` with WSL venv `~/.venvs/gigaam-build` (system Python 3.12.3, no
  system site packages, requirements-build.txt). Run through agg-queue, for example
  `agg-queue.exe run --kind build --what "..." -- wsl.exe -d Ubuntu -- bash <script>` (Git Bash needs
  `MSYS_NO_PATHCONV=1`). Wrapper scripts of this session: scratchpad `wsl/` (build.sh, verify.sh,
  wcheck.sh, unpack.sh) under
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\5297a77e-1f2f-44cc-b6de-976f4752fc6a\scratchpad`.
  Output: `~/gigaam-build/app/GigaAmTranscriber` (973 MiB, program 115 MiB) and
  `C:\MyProjects\GigaAmTranscriber\build\release-linux\GigaAmTranscriber-v0.2.0-linux-x64.tar.gz`
  (825 MiB, version not bumped yet). Smoke tests pass: CLI 60 s file in 4-9 s, missing WebKitGTK
  message (names only gir1.2-webkit2-4.1), window under a private Xvfb `:97` in 0.7-1.3 s and
  transcribing. Unpacked tarball: permissions 0755 only for the two programs; 455 s lecture on the
  CPU in 34 s, 1.5 GB RAM, text byte-identical to the Windows build.
- Tests: 325 passed, 1 skipped on Windows (dev venv: this session's scratchpad `venv-app`); WSL
  from source with `~/.venvs/gigaam-spike`. New `pytest.ini` (testpaths = tests: on Linux pytest
  collected tools/gui_smoke_test.py). `tools/window_check.py`: 26 checks, both answers of the close
  question, a second window session that must show the remembered files; passes on Windows and
  in WSL under Xvfb; it uses a temporary history folder.
- C3: README (Linux download and build, the list and its folder, close question), THIRD_PARTY_NOTICES
  (PyGObject LGPL with source link, Debian copyrights, no FFmpeg on Linux), draft release notes in
  `docs/RELEASE_NOTES_NEXT.md` (v0.3.0 proposed).
- Open before a release: the Windows build is from C1 (no close question, no history): rebuild;
  `THIRD_PARTY_LICENSES.zip` is built from the Windows licences only, so merge in the Linux ones
  (pygobject, debian); bump the version. Not checked: a real Linux desktop (only WSL + Xvfb), and on
  Linux by hand the file dialog, drop, copy and opening files. ONNX Runtime prints a "GPU device
  discovery failed ... /sys/class/drm/card0" warning in WSL (no DRM device there); harmless.

## Session 6 (2026-11-06): the new window built, Stage B done

- Code: `gigaam_app/web/` (index.html, app.css, app.js; inlined by window.py, no server, no CDN),
  `gigaam_app/controller.py` (queue, settings, status texts; no GUI toolkit), `gigaam_app/window.py`
  (theme, WebView2/WebKitGTK check, `Api` bridge, `Sender`, `main`), `gigaam_app/worker.py` (the
  old Tk `Worker`, moved; now emits `loading` / `load_failed`). `gigaam_app/gui.py` (Tk) is deleted;
  `python -m gigaam_app` and `launchers/gui_main.py` open the new window.
- Behaviour choices made without asking (owner may change them): files start as soon as they are
  added (no "Распознать" button; the mockup had none); settings apply at once, to the next file;
  closing the window while a file runs cancels it (no confirm); a dropped folder adds the media
  files directly inside it; saved-file chips also offer to create a missing format from the text.
- **pywebview bug on GTK:** `evaluate_js` passes the script length in characters where WebKit
  wants bytes, so any script with Cyrillic is cut short ("Unexpected end of script"). The sender
  uses `json.dumps(ensure_ascii=True)`; scripts in tools stay ASCII.
- The model load holds the GIL for about 2 s; the worker sleeps 0.1 s after `loading` so the page
  can show it first. Bridge calls wait during the load.
- Tests: `tests/test_controller.py` (fake worker), `tests/test_window.py`; 313 passed, 1 skipped.
  `tools/window_check.py LONG SHORT --out DIR` drives the real window (19 checks: queue, cancel
  midway, timecodes, create SRT, retry, remove, device change, download dialog against a local
  test model, load error banner): passes on Windows in both themes and in WSL Ubuntu under Xvfb
  (WSL venv `~/.venvs/gigaam-spike` now has requirements.txt installed). Not testable without a
  real mouse: the file dialog, drop, copy to clipboard, opening files and the folder.
- Missing engine: `GIGAAM_PRETEND_NO_WEBVIEW=1` shows the message (MessageBox checked on a hidden
  desktop; on Linux stderr plus zenity/kdialog/xmessage). `GIGAAM_THEME=light|dark` forces a theme.
- `tools/gui_smoke_test.py` now runs the EXE off screen (`GIGAAM_WINDOW_OFFSCREEN=1`) on the
  normal desktop, because WebView2 does not run on a hidden desktop.
- C1 build (`python tools/build_windows.py --no-zip`, through agg-queue): spec drops Tk, adds
  `gigaam_app/web` as data, excludes other pywebview backends and cffi's compiler modules (they
  import distutils, which broke the analysis). Licences added: pywebview, pythonnet, clr_loader,
  cffi, pycparser, bottle, typing_extensions from their metadata; `packaging/licenses/`
  WebView2-SDK-LICENSE/NOTICE (from the 1.0.3856.49 NuGet package) and proxy_tools-LICENSE (MIT
  text; the package has no licence file). Results: program 121 MiB, folder 1180 MiB; CLI smoke
  CPU and DirectML pass; GUI window after 1.8-2.0 s; the 455 s lecture written after 10.5 s
  (`build/app/GigaAmTranscriber/`). No release zip was made.
- Next: C2 (Linux build). Open question there: a frozen app cannot import the system's PyGObject
  (gi is ABI-tied to the system Python); options are PyInstaller's gi hooks (bundle GTK/WebKit,
  large) or building with the system Python 3.12 and adding the system dist-packages path
  (works only on matching distros). Linux FFmpeg: planned to use the system package (the app
  already finds ffmpeg on PATH). Then C3 (README parts done this session; Linux and release notes left).
- Sample audio copies for checks: scratchpad of this session, `audio/` (research-2026.mp4 and a
  60 s cut). Screenshots: its `shots/` folder.

## Session 5 (2026-11-06): new window on pywebview, Stage A done

- C5 (sv-ttk restyle) was built but the owner found it too close to the old window.
  Not committed; the whole diff is kept outside the repo at
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\3f818aad-2f5d-47ea-8f62-788af417f8b8\scratchpad\c5-backup\c5-sv-ttk.patch`.
  Two side fixes from it were committed: the smoke test reads the title with
  GetWindowTextW (11edf89), and the first model load waits for the window to draw (101b70c).
- Mockups: https://claude.ai/artifact/32pVRs6kmWRDDUiss5sYby. **Owner chose design B**
  (file list on the left: done, running, waiting; selected file's progress and live text on the right).
- **Owner decisions:** build it in HTML/CSS with pywebview; Linux too, using the system
  WebKitGTK (the app names the package if it is missing); Linux recognition on the CPU
  first, NVIDIA later; ONNX Runtime WebGPU (Vulkan) as a later experiment for a light
  Linux GPU option. Owner accepted the webview start time (dark frame about 1.2 s, content
  about 1.75 s, against 0.85 s for Tk) on 2026-11-06; no PyInstaller splash.
- Spike results (`experiments/webview_spike/`, pywebview 6.2.1): bridge both ways, pushed
  lines and theme detection work on Windows (WebView2 156) and WSL Ubuntu 24.04 (WebKitGTK 2.52).
  Frozen on Windows: +2 MB; window frame at 1.3-1.6 s, page at 2.5-2.7 s (Tk: 0.85 s).
  Rechecked warm (5 runs each, from process start, frozen): frame 1.2 s, page 1.75 s.
  Where it goes: Python + pywebview import 0.45 s, pythonnet/.NET + WinForms 0.7 s,
  WebView2 start and page 0.5 s. A kept profile (`private_mode=False`) does not help;
  `background_color` does not change timing but removes the white flash (frame shows
  in the app's dark colour). Bench (bench.py, bench_frozen.py, a frozen build):
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\6a3c0658-6d34-4248-a107-e790afcad1b6\scratchpad\speed`.
  Without WebView2 pywebview falls back to the IE engine silently, so the app must check (B6).
  Drop and the file dialog were not tested (need a real mouse).
- Testing: WebView2 does not paint on a hidden desktop; use an off-screen window
  (x, y = -6000, `focus=False`) and PrintWindow. In WSL, unset `WAYLAND_DISPLAY` and set
  `GDK_BACKEND=x11` under Xvfb; once this session forgot it and a spike window showed on
  the owner's screen through WSLg for a few seconds.
- Dev venv for this session: `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\3f818aad-2f5d-47ea-8f62-788af417f8b8\scratchpad\venv-app`
  (requirements-build.txt + pywebview); the session 3 venv lost its python.exe.
  Tests: 280 passed, 1 skipped. WSL venv: `~/.venvs/gigaam-spike` (system site packages for gi).

## Decisions (approved by the owner on 2026-11-04)

- Drop PyTorch from the shipped app. Run GigaAM on ONNX Runtime with the
  DirectML provider (any DX12 GPU) and CPU fallback, in one onedir build.
  PyTorch stays only as a developer tool for exporting checkpoints to ONNX.
- Release v0.2.0: one Windows zip (GUI + console CLI, RNNT and CTC bundled),
  updated Docker images. Speaker diarization is NOT part of it (owner: not now).
- Old builds in `dist/` may be deleted once the new build is verified.
- Commit and publish the release only after the owner has seen the new build work
  (owner confirmed in session 3).

## Session 4 (2026-11-05): B2 done (not adopted), B6 built, multilingual dropped

Commits from 0d7dd4a on main, pushed. Tests: 280 passed, 1 skipped
(parity), with the session 3 venv
`C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\740fa774-5b91-4234-b11a-c5b322975530\scratchpad\venv-app`.

**B2, fp16 compute on DirectML: not adopted.** `experiments/onnx_runtime/fp16_encoder.py`
converts the encoder explicitly: fp16 everywhere except the mel front-end (log of
1e-9 powers) and the frame-length arithmetic (fp16 is exact only to 2048). The
onnxconverter-common converter failed (left the graph's Cast(to=float) nodes,
type errors, then all-NaN output). RNNT, 7 files / 2 h of audio, encoder time:

| GPU | fp32 | fp16 | Text vs fp32 |
| --- | ---: | ---: | --- |
| RTX 4070 Laptop (DML device 0) | 42.6 s | 40.8 s | lecture identical; `2023 06 10 12 08 59.mp3` loses 10 of 2863 words ("Так, вторая группа.", dialogue dashes) |
| Radeon 780M iGPU (DML device 1) | 175 s | 107 s | same kind of differences |

Keeping Softmax and LayerNorm in fp32 did not help (still differs, and adds a diff
on the lecture). Only the iGPU would gain, and the text changes, so the app stays
fp32. Side finding: DML device 0 is the RTX on this laptop; the app does not pick
an adapter (DirectML's default).

**B6, downloads of extra models (code done; no model uses it yet).**
- Models: `multilingual_ctc` (220M, 845 MB) and `multilingual_large_ctc` (600M,
  2.2 GB), the two v0.1 offered. Char-level CTC (Latin, Cyrillic, Kazakh letters),
  lowercase, no punctuation. Checkpoints are float32 and NOT fp16-exact; lossy fp16
  storage changed 8 tokens on a Russian file, so they ship fp32. The 600M weights
  exceed the 2 GB protobuf and 2 GiB GitHub asset limits: `export_models.py` now puts
  weights above 1.8 GiB into `encoder.data1` / `encoder.data2` (external data, at most
  1.5 GiB each). v3_e2e_ctc re-exports byte for byte. Max |onnx - torch|: 2.5e-4 and 8.8e-4.
- Speed on DML (RTX): 220M like v3 (lecture 4.6 s); 600M 1.7x slower, load 9 s cold.
  On English audio both write Cyrillic transliteration (that file is out of domain).
- App: `gigaam_app/catalog.py` (keys RNNT, CTC; Multilingual entries were removed, see below;
  sizes and SHA-256 of each file in code; v0.1 names as aliases),
  `gigaam_app/download.py` (staging `<folder>.partial`, SHA-256 per file, HTTP Range
  resume, 3 attempts, cancel, disk space check, rename when all pass),
  `paths.downloads_dir()` (`%LOCALAPPDATA%\GigaAmTranscriber\models`, `GIGAAM_DOWNLOADS`).
  CLI `--list-models`, `--download MODEL`; GUI asks before downloading, progress and
  cancel. Bug fixed on the way: v0.2.0 rejected v0.1 settings naming a multilingual model.
- Tested: `tests/test_download.py` (17 tests, local HTTP server: damaged, cut,
  resumed, cancelled, Range ignored, 404, too long, no space). GUI end to end in
  process with the Tk root withdrawn (never shown): large model cancelled at 312 MB,
  resumed with `Range: bytes=327155712-`, loaded; small model downloaded from
  "Распознать", transcribed a file. Docker `--download` is documented but not run.
- **Owner decision: multilingual GigaAM dropped.** Ignoring case and punctuation,
  its Russian text differs from RNNT by 5% (lecture), 10% (phone call) and 26%
  (multi-speaker class), and English comes out transliterated. Removed from the
  catalog, GUI and docs; v0.1 settings that chose it load with RNNT. The downloader,
  the external-data export and `tools/stage_model_assets.py` stay for future models
  (Stage F, B9, diarization models). Release tag `models-1` is not created.
- Owner: for English and other languages only Whisper-class models make sense.
  Plan Stage F (before E) compares Parakeet TDT 0.6B v3, Whisper large-v3-turbo and
  Qwen3-ASR on labelled Russian and English audio. B9: int8 encoder for CPU-only
  machines as an optional download (owner suggested q8/q4).
- Owner tried the app from source: it works. Owner wants a nicer window design: plan C5.
- No release date. v0.2.1/v0.3.0 has little visible change so far (v0.1 settings fix);
  a release makes sense with B9 or Stage F.

## Release v0.2.0 (session 3, 2026-11-04): published

- Dev venv recreated (scratchpad `venv-app` of session 3); 261 passed, 1 skipped
  (the parity test, which needs `GIGAAM_PARITY_AUDIO` / `GIGAAM_PARITY_REFERENCE`).
- Rewrite committed in 9 commits (8c4135e..eba7650) and pushed to main.
- GitHub release v0.2.0 at eba7650, marked Latest:
  https://github.com/bigflyy/GigaAmTranscriber/releases/tag/v0.2.0
  Four assets uploaded; GitHub's SHA-256 digests match SHA256SUMS.txt, and a fresh
  download of all assets passed `sha256sum -c` (the first `gh release download` of the
  zip broke off with an HTTP/2 stream error; `curl -C -` resumed it).
- Workflow "Publish CPU and CUDA containers" run 41867784548 with v0.2.0: both jobs
  passed. Pushed `ghcr.io/bigflyy/gigaamtranscriber:v0.2.0-cpu` / `:cpu`
  (sha256:73cf43eb...) and `:v0.2.0-cuda` / `:cuda` (sha256:c615b94f...).
  The workflow smoke test runs `--version` and transcribes a 2 s silent file offline
  with RNNT and CTC: it proves the image starts and loads both models without network,
  but the encoder does not run on speech there. Real speech was checked only on the
  locally built CPU image (session 2). The CUDA image is still not GPU-tested.
- Remaining work: plan items B2 (fp16 on DirectML), B6 (downloads of extra models),
  and Stage E (speaker diarization, owner: not now).

## State of the rewrite (session 2, 2026-11-04)

Done and verified in session 2:

- Tests: `tests/test_decoders.py`, `test_outputs.py`, `test_config.py`, `test_cli.py`,
  `test_engine.py` (pipeline with fakes), `test_models.py` (real models, optional parity
  via `GIGAAM_PARITY_AUDIO` / `GIGAAM_PARITY_REFERENCE`). 261 passed; parity passes on
  DirectML and CPU.
- Windows build: `packaging/GigaAmTranscriber.spec` (two EXEs, one `_internal`),
  `packaging/README.txt`, `packaging/licenses/` (Silero, DirectML texts),
  `tools/build_windows.py` (checks, build, payload, licences, smoke tests, zip, SHA256SUMS),
  `tools/gui_smoke_test.py` (GUI EXE on a hidden desktop, PrintWindow capture, WM_CLOSE).
  Output: `build/app/GigaAmTranscriber/` and `build/release/`.
- Fixes found by testing the frozen build: PyInstaller took `tcl86t.dll` from
  `C:\ProgramData\miniconda3\Library\bin` on PATH (window crashed); the build now runs
  PyInstaller with a clean PATH and checks every DLL. The CLI failed on file names outside
  the console code page when output was redirected; fixed (`safe_console`). The first
  model load delayed the window to 3-5 s; now it starts 150 ms after the window (about 1 s).
- CLI expands wildcards itself (cmd.exe does not).
- `asr.py` calls `onnxruntime.preload_dlls()` before CUDA sessions (Docker CUDA image).
- Removed torch-era files: transcribe.py, gui.py, gui_help.py, app_config.py, model_catalog.py,
  build_release.py, prepare_release.py, benchmark.py, giga.py, release/, tests/test_desktop.py,
  requirements-cpu.txt, setup.py (upstream packaging that read requirements.txt),
  README_TRANSCRIBER.md (folded into README.md), debug files. `gigaam/` stays: the export
  tools and experiments use it.
- New requirements: `requirements.txt` (app), `requirements-build.txt`, `requirements-export.txt`.
- Docs rewritten: README.md, DOCKER.md, RELEASE_NOTES.md, BENCHMARK.md, RELEASE_TESTS.md,
  THIRD_PARTY_NOTICES.md, gigaam-config.example.json (version 2).
- Dockerfile: two stages, export with CPU torch in stage 1, final image has no torch;
  `ORT_VARIANT=cpu|cuda`. Workflow builds both and smoke-tests offline.
- `third_party/` (gitignored) holds `ffmpeg/FFmpeg-8.0.1-source.zip` and
  `v0.1.0/THIRD_PARTY_LICENSES.zip`, copied out of `dist/` with matching checksums.

- Final build verified (end of session 2): `build/release/` holds
  `GigaAmTranscriber-v0.2.0-windows-x64.zip` (917 MiB, SHA-256 b790348e...),
  `THIRD_PARTY_LICENSES.zip`, `FFmpeg-8.0.1-source.zip`, `SHA256SUMS.txt`. The zip was
  unpacked to a fresh folder and tested there: GUI on a hidden desktop transcribed the
  455 s lecture (window 1.6 s, text identical to v0.1), CLI on CPU and DirectML.
- Docker CPU image built locally (`gigaam-transcriber:cpu`, 2.81 GB): offline RNNT and CTC
  work, RNNT text identical to v0.1. The CUDA image is not built or GPU-tested locally.
  Docker Desktop pulled from PyPI at ~60 kB/s while the host got 1.9 MB/s; its only proxy
  is the built-in `http.docker.internal:3128` in "system" mode (Windows proxy is off). The
  owner chose to leave Docker Desktop settings as they are.
- `dist/` deleted (owner approved; v0.1.0 assets are all on the GitHub release).
Dev venv: scratchpad `venv-app` of session 3 (may be gone); recreate with
`uv venv venv-app --python C:\Users\User\.conda\envs\cuda-torch2\python.exe` and
`uv pip install -r requirements-build.txt`. Run the build with that venv's python.


## Measurements (2026-11-04, Ryzen 7 7840HS, RTX 4070 Laptop 8 GB)

Sample: `C:\Users\User\Downloads\research-2026.mp4`, 455 s, one speaker, 26 chunks.
"First file" = first transcription in a fresh process, including CUDA warm-up.

| Pipeline | Startup to ready | First file | Second file | Text vs reference |
| --- | ---: | ---: | ---: | --- |
| Old, torch CUDA (source, warm disk) | 14.5 s | 37.7 s | 21.6 s | reference uses CPU fp32 |
| Old, torch CPU 8 threads | 10.8 s | 40.4 s | - | reference |
| Old, onefile EXE CUDA / CPU (BENCHMARK.md) | 129 s / 26 s before the window appears | | | |
| ORT CUDA EP fp32 | 3.1 s | 4.0 s | 3.8 s | identical (932/932 words) |
| ORT DirectML fp32 | 2.0 s | 6.9 s | 5.0 s | identical |
| ORT CPU fp32, 8 threads | 2.0 s | 25 s | 25 s | identical |
| ORT CPU int8 (MatMul only), 8 threads | 1.1 s | 14.4 s | 17.4 s | 9 small diffs in 932 words (punctuation, hyphens) |

Where the old pipeline loses time, for the same file on CUDA:

- `import torch` 4-9 s; torch CUDA libraries are 3.9 GB, which forces the 3.7 GB EXE.
- Onefile EXE unpacks everything to %TEMP% on every launch: the 129 s / 26 s above.
- MD5 of the 449 MB checkpoint on every load (~1 s), then a pickle `torch.load`
  with `weights_only=False` (runs arbitrary code from a downloaded file).
- The GUI loads the model again for every file.
- Audio is decoded by ffmpeg twice (`vad_utils.segment_audio_file`).
- Silero VAD in torch, one thread, about 14,000 sequential calls: 8-10 s.
  ORT with the audio cut into parallel rows: 1.3 s, same boundaries except one 0.1 s shift.
- RNNT greedy decoding: 13.5 s on GPU, slower than the encoder. It runs the
  prediction LSTM on every frame although its output only changes after an
  emitted token, recomputes the encoder projection per frame, and syncs the GPU
  with `.item()` per step. A numpy version with both fixes: 0.9 s.
- No batching; the first CUDA run spends ~11 s warming kernels for new shapes.

## Diarization findings (sherpa-onnx 2.0.1, CPU, 8 threads)

- Pipeline: pyannote segmentation-3.0 ONNX (6 MB) + speaker embedding ONNX + clustering.
- Speed about 10x realtime on CPU (23 min file in ~145 s). This is slower than ASR on GPU.
- Single-speaker lecture: 1 speaker found (correct).
- 23 min multi-speaker file `2023 06 10 10 34 50.mp3`, WeSpeaker ResNet34:
  threshold 0.5 gives 19 speakers, 0.8 gives 4. True count unknown.
- 3D-Speaker ERes2Net base: 88 speakers at 0.8, unusable as configured.
- Conclusion: works, but the clustering threshold needs tuning on a labelled
  recording, and a "number of speakers" option is needed for when the user knows it.

## Files and storage

- Prototype code: `experiments/onnx_runtime/` (see its README).
- Session 1 scratchpad (reference JSON `ref_torch_cpu.json`, `short.m4a`):
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\1b972041-92b6-47ff-9690-27ace02d4adf\scratchpad`.
  Session 2 copies are in its scratchpad `ref/`.
- Storage rule from the owner: up to ~3 GB of new files without asking. `dist/` is deleted;
  the FFmpeg source and the old licence zip are in `third_party/` (gitignored).
