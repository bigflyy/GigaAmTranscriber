# GigaAM Transcriber v0.7.0

Whisper is faster on the processor: whisper.cpp no longer reads every piece twice, the search for
other models' suggestions tells Whisper the language, and faster-whisper can read Whisper on the
processor instead of whisper.cpp. GigaAM's own recognition is the same as in v0.6.0.

## Whisper on the processor

- **Настройки** -> **Модель** -> **Whisper на процессоре** chooses what reads Whisper on the
  processor: **whisper.cpp** (inside the app, as before) or **faster-whisper (int8)**, a separate
  780 MB download, asked for the first time you choose it (**Не сейчас** keeps whisper.cpp).
- On the processor faster-whisper reads the text about 1.4 times faster than this version's
  whisper.cpp (the 7.5-minute test lecture: about 3.5 min against 5 min on 8 threads) and finds
  the other models' suggestions 1.6 to 2 times faster, reading up to 8 lines at once. Its word
  times are more exact. On the test recordings it heard as well as whisper.cpp; each was right
  about as often where they differed.
- The status line says **Whisper - процессор, faster-whisper** while it is in use, and a file it
  read names "Whisper large-v3-turbo (faster-whisper int8)" as its model, also in the saved
  Markdown and the text for an AI. On a video
  card Whisper always runs on whisper.cpp (with **Авто**, faster-whisper is used only when there
  is no card for whisper.cpp).
- A file read again gives the same text: faster-whisper's random choices on noisy places now
  start from a fixed seed.
- The command line follows the same setting (`"whisper_cpu"` in `gigaam-config.json`).

## Faster whisper.cpp

- With the language **Авто**, whisper.cpp used to encode each piece twice: once to find the
  language and once to transcribe it. It now finds the language from the same pass. Same text,
  word times and confidences; about 1.9 times faster on the processor and 1.2 to 1.3 times on a
  video card.
- The search for other models' suggestions tells Whisper the language of GigaAM's text when the
  language is **Авто** (Russian; Whisper still finds it itself on a line where more than 15% of
  the letters are Latin), so it
  no longer guesses it on every short line: about twice as fast per line on the processor. A
  language chosen in **Настройки** is used as before.

## Fixed

- Windows with a DirectX 12 video card: after the model, the device or the number of threads
  was changed, the recognition process could crash while it looked for speakers or for
  suggestions ("Процесс распознавания неожиданно завершился", since v0.6.0). The window
  started it again, but that file's search was lost. A model on the video card is now freed
  only together with the other models on the card; they load again when next needed.

## Windows

`GigaAmTranscriber-v0.7.0-windows-x64.zip` (about 960 MB): unzip it anywhere and
run `GigaAmTranscriber.exe`; `gigaam-cli.exe` beside it is the command line. Both
GigaAM models and FFmpeg are inside; GigaAM uses any DirectX 12 GPU through DirectML,
Whisper any Vulkan GPU, both with the CPU as fallback. The EXEs are not code-signed,
so Windows SmartScreen may ask once. Models downloaded by earlier versions (Whisper, the
speaker models) are found automatically.

## Linux

`GigaAmTranscriber-v0.7.0-linux-x64.tar.gz` (about 890 MB): the window and
`gigaam-cli`, both GigaAM models inside. GigaAM and Whisper run on the CPU (the Linux app
also carries whisper.cpp's Vulkan backend, not yet tried on a Linux GPU). Unpack it and run
`./GigaAmTranscriber/GigaAmTranscriber`.

The system must have glibc 2.39 or newer (Ubuntu 24.04, Debian 13, Fedora 40 and
later), FFmpeg and, for the window, WebKitGTK 4.1:

    sudo apt install ffmpeg gir1.2-webkit2-4.1
    sudo dnf install ffmpeg-free webkit2gtk4.1 gobject-introspection   # Fedora

## Downloads

- `GigaAmTranscriber-v0.7.0-windows-x64.zip` - Windows app.
- `GigaAmTranscriber-v0.7.0-linux-x64.tar.gz` - Linux app.
- `THIRD_PARTY_LICENSES.zip` - licences of the bundled components, one folder per app
  (`windows/`, `linux/`; also inside the app folders). New: faster-whisper, CTranslate2 (with
  the libraries built into it) and tokenizers.
- `FFmpeg-8.0.1-source.zip` - source of the FFmpeg build in the Windows app (GPLv3).
- `SHA256SUMS.txt` - checksums of the files above.

The Whisper models and the speaker models are assets of the separate `models-1` release or
come from Hugging Face; the app downloads them when they are first needed.

Notes of earlier versions: https://github.com/bigflyy/GigaAmTranscriber/releases
