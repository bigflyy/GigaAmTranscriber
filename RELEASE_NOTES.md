# GigaAM Transcriber v0.4.0

Whisper as a second model, Markdown transcripts and an app icon. GigaAM recognition
and its text are the same as in v0.3.0.

## Whisper

- **Whisper large-v3-turbo** (OpenAI) can be chosen in **Настройки** beside RNNT and
  CTC. It is not inside the app: choosing it the first time asks to download it
  (547 MB, once; an interrupted download resumes). The file comes from this
  repository's `models-1` release, with the whisper.cpp project's copy on Hugging Face
  as the backup address; its SHA-256 is checked. Downloaded models live outside the
  app folder (`%LOCALAPPDATA%\GigaAmTranscriber\models` on Windows,
  `~/.local/share/gigaam-transcriber/models` on Linux), so a newer version finds them.
- With Whisper the settings show **Язык речи**: detect it automatically, or choose one
  of 20 languages (Russian, English, Ukrainian, German, Chinese and others).
- What it is for: speech in other languages, and Russian speech full of English
  terms, which Whisper writes as written ("fine tuning", "LLM", "Prompt Engineering").
  On plain Russian GigaAM is usually more accurate, so RNNT stays the default.
- Whisper runs on [whisper.cpp](https://github.com/ggml-org/whisper.cpp) 1.9.5 with
  Vulkan: on any Vulkan GPU (NVIDIA, AMD, Intel; a separate GPU before a built-in
  one), else on the CPU. A 7.5-minute lecture takes about 12 s on a laptop RTX 4070
  (GigaAM: about 6 s) and a few minutes on the CPU. The first Whisper run on a GPU
  (and the first after a driver update) spends about half a minute preparing it.
- Whisper gets the same speech fragments as GigaAM and reads each one on its own.
  Fed a whole 45-minute call at once, Whisper invented text and repeated one phrase
  many times; fragment by fragment it did not.
- Each file in the window names the model that made its text ("Модель: Whisper
  large-v3-turbo (q5_0)" under the status; RNNT, CTC or Whisper in the list), also
  for files from earlier sessions and after the settings choose another model.
- Command line: `gigaam-cli --download Whisper`, then
  `gigaam-cli talk.mp3 --model Whisper --language en`. `gigaam-cli --devices` lists
  the GPUs and the CPU each engine can use.

## Markdown transcripts

- New format `md` (`name-transcript.md`): the file name as the title, a line with the
  date, length and model, then the text in sections of about a minute under their
  start times. Off by default: tick it in **Настройки**, make it from a finished file
  with the **MD** button, or pass `--formats md`.

## App icon

- Both programs and the window now have an icon: a sound wave turning into lines of text.

## Windows

`GigaAmTranscriber-v0.4.0-windows-x64.zip` (about 930 MB): unzip it anywhere and
run `GigaAmTranscriber.exe`; `gigaam-cli.exe` beside it is the command line. Both
GigaAM models and FFmpeg are inside; GigaAM uses any DirectX 12 GPU through DirectML,
Whisper any Vulkan GPU, both with the CPU as fallback. The EXEs are not code-signed,
so Windows SmartScreen may ask once.

## Linux

`GigaAmTranscriber-v0.4.0-linux-x64.tar.gz` (about 840 MB): the window and
`gigaam-cli`, both GigaAM models inside. GigaAM runs on the CPU. Whisper runs on the
CPU too; the Linux app also carries whisper.cpp's Vulkan backend, but it has not been
tried on a Linux GPU yet. Unpack it and run `./GigaAmTranscriber/GigaAmTranscriber`.

The system must have glibc 2.39 or newer (Ubuntu 24.04, Debian 13, Fedora 40 and
later), FFmpeg and, for the window, WebKitGTK 4.1:

    sudo apt install ffmpeg gir1.2-webkit2-4.1
    sudo dnf install ffmpeg-free webkit2gtk4.1 gobject-introspection   # Fedora

## Downloads

- `GigaAmTranscriber-v0.4.0-windows-x64.zip` - Windows app.
- `GigaAmTranscriber-v0.4.0-linux-x64.tar.gz` - Linux app.
- `THIRD_PARTY_LICENSES.zip` - licences of the bundled components, one folder per app
  (`windows/`, `linux/`; also inside the app folders). Whisper's weights and whisper.cpp
  are MIT.
- `FFmpeg-8.0.1-source.zip` - source of the FFmpeg build in the Windows app (GPLv3).
- `SHA256SUMS.txt` - checksums of the files above.

The Whisper model file itself is an asset of the separate `models-1` release; the app
downloads it when Whisper is first chosen.

Notes of earlier versions: https://github.com/bigflyy/GigaAmTranscriber/releases
