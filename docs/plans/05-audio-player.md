# Audio player for the whole file

Owner's idea (docs/IDEAS.md, 2026-11-08): "maybe there should be a play/pause button. and how
much time passed (the player of audio interface?)". Owner chose (2026-11-08, AskUserQuestion)
a whole-file player like Google Recorder or Otter over small controls for the piece being
played: a bar under the text with play/pause, time / total, a seek bar and speed; the word
being spoken is highlighted and the text follows it; a click on a timecode plays from there
and keeps going.

What exists (plan 03 A2): a timecode or the selection bar's "Слушать" plays only that piece,
cut by ffmpeg to a WAV and handed to the page as a data: URL; the button turns into "Стоп".
The page is loaded from a string (window.create_window(html=...)), so it cannot open local
files by path.

Findings (2026-11-08):
- A data: URL does not scale to a whole file (a 45 min call as 16 kHz WAV is 86 MB, more in
  base64). The page needs the audio from a small local HTTP server with Range requests, so it
  can seek without loading everything.
- Converting a 45 min WAV to Ogg Opus 32 kbps mono took 36 s (10 MB) with the bundled ffmpeg
  (gyan.dev full build: libopus, libmp3lame present; the Linux build uses the system ffmpeg).
  Too slow to wait for before playing, so the original file is served when the window's
  engine can play its format, and only other formats are converted, in the background.

### Stage A: Audio for the page

- [x] **A1** Local audio server: 127.0.0.1 on a free port, a random token in every path, Range requests, serves only files the controller registered; starts with the window and stops when it closes. Check first that the page (loaded from a string) may play http://127.0.0.1 media in WebView2
- [x] **A2** controller.audio(file_id) -> {url, duration}: the original file when its format plays in the window (mp3, m4a, aac, wav, ogg, opus, flac, webm, mp4 by extension), else a temporary Ogg Opus made in the background ("audio_ready" message); the page also asks for the converted copy when the original fails to play. Temporary copies are deleted when the window closes

### Stage B: The player bar

- [ ] **B1** Bar under the text of a finished or cancelled file: play/pause, time / total, a seek bar, speed (0.75x to 2x)
- [ ] **B2** A click on a timecode plays from that line and keeps going; the selection bar's "Слушать" plays the selection and stops at its end; the fix dialog keeps its own clip
- [ ] **B3** The word being spoken is highlighted; while playing, the text follows it unless the reader has scrolled away

### Stage C: Checks

- [ ] **C1** Tests: the server (Range, token, unknown paths refused), controller.audio (original or converted), clean-up at close
- [ ] **C2** window_check.py steps (muted): play, pause, seek, the highlighted word moves; screenshots
- [ ] **C3** Linux: the player under WebKitGTK at the next Linux build (formats it plays without extra GStreamer plugins)
