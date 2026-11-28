# GigaAM Transcriber v0.8.1

A fix for the Windows app: v0.8.0 did not start when the downloaded zip had been unpacked with
Windows' own "Extract all". The window failed with "Unhandled exception in script ...
Failed to resolve Python.Runtime.Loader.Initialize". Windows marks every file unpacked from a
downloaded zip as "from the internet", and .NET Framework refuses to load such libraries. The
app now removes that mark from the libraries its window needs before loading them; if the folder
is read-only and it cannot, it says how to unblock the folder. Nothing else changed: the notes
of v0.8.0 follow.

If you keep v0.8.0, unblock it once instead: in PowerShell run
`Get-ChildItem -Recurse "<the unpacked folder>" | Unblock-File`, or open the zip's
**Properties**, tick **Unblock** and unpack it again.

## New in v0.8.0

Running subtitles for video editors, a download window that can be hidden, and a suggestion
search that reads the most doubtful lines first. Recognition itself is the same as in v0.7.0.

### Running subtitles

- A new file format, **Бегущие субтитры** (`name-transcript-words.srt`): one word at a time,
  for Adobe Premiere Pro and other video editors. Choose it in **Настройки** -> **Сохранять рядом с файлом**
  ("SRT по одному слову") or write it for one finished file from its **Файлы** menu.
- Each word stays on screen until the next one starts; before a pause of 1 s or longer it stays
  at least 0.3 s. A word shorter than two frames (80 ms) is shown together with the next one.
  No speaker names.
- The file is UTF-8 with a byte order mark and Windows line endings: without the mark Premiere
  garbles Russian letters. Imported into Premiere Pro 2024 (24.3): Russian text and timing
  correct. The usual **Субтитры** file (`name-transcript.srt`) is unchanged.
- Command line: `--formats srt_words`.

### Window

- The window that downloads a model can be hidden with **Скрыть** (or Esc) while it downloads.
  The status line then shows "Скачивание модели X: N%"; a click on it shows the window again.
- The search for other models' suggestions reads the lines with a wavy-underlined word first,
  then the other doubtful lines, each part in text order, so the most likely mistakes get their
  suggestions sooner. It still reads every doubtful line.

## Windows

`GigaAmTranscriber-v0.8.1-windows-x64.zip` (about 960 MB): unzip it anywhere and
run `GigaAmTranscriber.exe`; `gigaam-cli.exe` beside it is the command line. Both
GigaAM models and FFmpeg are inside; GigaAM uses any DirectX 12 GPU through DirectML,
Whisper any Vulkan GPU, both with the CPU as fallback. The EXEs are not code-signed,
so Windows SmartScreen may ask once. Models downloaded by earlier versions (Whisper, the
speaker models) are found automatically.

## Linux

`GigaAmTranscriber-v0.8.1-linux-x64.tar.gz` (about 890 MB): the window and
`gigaam-cli`, both GigaAM models inside. GigaAM and Whisper run on the CPU (the Linux app
also carries whisper.cpp's Vulkan backend, not yet tried on a Linux GPU). Unpack it and run
`./GigaAmTranscriber/GigaAmTranscriber`.

The system must have glibc 2.39 or newer (Ubuntu 24.04, Debian 13, Fedora 40 and
later), FFmpeg and, for the window, WebKitGTK 4.1:

    sudo apt install ffmpeg gir1.2-webkit2-4.1
    sudo dnf install ffmpeg-free webkit2gtk4.1 gobject-introspection   # Fedora

## Downloads

- `GigaAmTranscriber-v0.8.1-windows-x64.zip` - Windows app.
- `GigaAmTranscriber-v0.8.1-linux-x64.tar.gz` - Linux app.
- `THIRD_PARTY_LICENSES.zip` - licences of the bundled components, one folder per app
  (`windows/`, `linux/`; also inside the app folders).
- `FFmpeg-8.0.1-source.zip` - source of the FFmpeg build in the Windows app (GPLv3).
- `SHA256SUMS.txt` - checksums of the files above.

The Whisper models and the speaker models are assets of the separate `models-1` release or
come from Hugging Face; the app downloads them when they are first needed.

Notes of earlier versions: https://github.com/bigflyy/GigaAmTranscriber/releases
