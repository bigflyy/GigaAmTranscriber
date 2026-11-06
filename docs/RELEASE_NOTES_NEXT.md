# GigaAM Transcriber v0.3.0 (draft, not released)

Draft notes for the next release. The version number is a proposal; when the release
is made, this text replaces RELEASE_NOTES.md (the v0.2.0 notes) and the timings and
sizes below are measured again on the final build.

A new window, and the app now runs on Linux too. Recognition and the text are the
same as in v0.2.0.

## New window

- Files in a list on the left (done, running, waiting); the selected file's
  progress and its text as it is recognised on the right. Several files can be
  added at once, by **+ Добавить** or by dragging files or a folder onto the window;
  they start at once and run one at a time.
- **The list is kept between sessions.** Finished files come back with their text
  when the window opens again; SRT or JSON can still be made from them later.
  **Убрать из списка** forgets a file but keeps its saved transcripts.
- Saved files are shown as buttons that open them; **Показать в папке** opens the
  folder. A format that was not chosen can be written from the text already recognised.
- Closing the window while a file is recognised or a model downloads asks first.
  The text recognised so far is saved.
- Settings (model, device, CPU threads, formats) apply to the next file at once
  and are saved by themselves; **Сбросить настройки** goes back to the defaults.
- Light and dark theme, following the system.
- The window is drawn by Microsoft Edge WebView2 on Windows (part of Windows 10
  and 11; if it is missing, the app links to Microsoft's installer) and by the
  system's WebKitGTK on Linux. It opens in about 2 s.

## Linux

`GigaAmTranscriber-v0.3.0-linux-x64.tar.gz` (about 830 MB): the window and
`gigaam-cli`, both models inside, recognition on the CPU (a 7.5-minute lecture
in about 35 s). Unpack it and run `./GigaAmTranscriber/GigaAmTranscriber`.

The system must have glibc 2.39 or newer (Ubuntu 24.04, Debian 13, Fedora 40 and
later), FFmpeg and, for the window, WebKitGTK 4.1:

    sudo apt install ffmpeg gir1.2-webkit2-4.1
    sudo dnf install ffmpeg-free webkit2gtk4.1 gobject-introspection   # Fedora

NVIDIA GPUs on Linux: use the CUDA Docker image for now.

## Fixes

- Settings files from v0.1 that chose a multilingual model load again (with RNNT).

## Downloads

- `GigaAmTranscriber-v0.3.0-windows-x64.zip` - Windows app.
- `GigaAmTranscriber-v0.3.0-linux-x64.tar.gz` - Linux app.
- `THIRD_PARTY_LICENSES.zip` - licences of the bundled components (also inside the app folders).
- `FFmpeg-8.0.1-source.zip` - source of the FFmpeg build in the Windows app (GPLv3).
- `SHA256SUMS.txt` - checksums of the files above.
