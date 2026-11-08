# GigaAM Transcriber v0.5.0

Fix a part of the text, doubtful words marked, other models' suggestions for them, a text for an
AI chat, and a player for the whole file. GigaAM recognition of a whole file is the same as in
v0.4.0.

## Fix a part of the text

- Select words in a finished text: a small bar above the selection offers **▶ Слушать** (plays
  that part), **Распознать заново** and **Исправить...**.
- **Распознать заново** reads only that part again with RNNT, CTC and Whisper (when downloaded)
  and shows each reading beside the current text, with the changed words marked. **Взять**
  puts a reading in, or type the text by hand and **Сохранить**. The saved files are written
  again at once.
- **Термины** in that dialog: a list of names and terms ("LLM, fine tuning, DeepSeek") given
  to Whisper as a hint. On a recorded lecture every listed term came out right. GigaAM models
  take no such hint.
- A selection can be up to 25 seconds long.

## Doubtful words

- Every word now has the model's confidence. Words the model was not sure of are underlined:
  dotted for "возможно ошибка", wavy for "скорее ошибка"; hovering shows the percentage.
- **Сомнения** switches the marks on and off. In **Настройки**, under **Сомнительные слова**:
  underline only the doubtful words, or colour every word from green to red; both thresholds
  can be changed.
- Files recognised by earlier versions have no marks until they are recognised again.

## Suggestions from another model

- After a file is recognised, each line with doubtful words is read again by another installed
  model: Whisper checks GigaAM's text, RNNT checks Whisper's. Where it heard something else, the
  doubtful word's underline turns blue; hovering shows the other reading ("Другие модели
  слышат: Tools Calling").
- A click on such a word opens a card with each offer: **Взять**, **▶ Слушать**,
  **Исправить...** (the fix dialog with the offer filled in) and **Оставить как есть**.
- Whisper is good with English names and terms in Russian speech, GigaAM with Russian, so the
  offers are mostly for terms: on a recorded lecture about half of Whisper's offers were right
  ("Tullz Colling" -> "Tools Calling", "файндтюнинг" -> "fine tuning").
- When to look, in **Настройки** -> **Варианты для сомнительных слов**: right after a file
  recognised on the GPU (the default), always, or only with the **Найти варианты** button
  (also for files from earlier sessions). On the CPU Whisper can be slower than the recording,
  so there the default is the button.

## Text for an AI chat

- **Копировать для ИИ** and the new format **Для ИИ** (`name-transcript-llm.txt`): the text with
  a short note for the AI. Doubtful words are marked as `слово[?66%]`, and where another model
  heard something else both versions are given:
  `{GigaAM v3 RNNT: Tullz[?50%] Colling | Whisper large-v3-turbo (q5_0): Tools Calling}`.
  Paste it into a chat and ask the AI to check or correct the text.

## Player

- A bar under the text plays the whole file: play / pause, the time, seeking, speed, volume
  and mute; Space plays and pauses. The word being spoken is highlighted and followed unless
  you have just scrolled.
- A click on a line's time plays from that line; Alt+click on a word plays from that word.
- Formats the window cannot play itself (for example some video files) get a temporary copy
  of their sound first; it is deleted when the window closes.

## Window

- Models now run in a separate process. Before, the window could not be moved or resized
  for about 4 seconds while a GigaAM model loaded; now it stays responsive. If a model library
  ever crashes, the window shows an error and goes on instead of closing.

## Windows

`GigaAmTranscriber-v0.5.0-windows-x64.zip` (about 930 MB): unzip it anywhere and
run `GigaAmTranscriber.exe`; `gigaam-cli.exe` beside it is the command line. Both
GigaAM models and FFmpeg are inside; GigaAM uses any DirectX 12 GPU through DirectML,
Whisper any Vulkan GPU, both with the CPU as fallback. The EXEs are not code-signed,
so Windows SmartScreen may ask once. Downloaded Whisper models from v0.4.0 are found
automatically.

## Linux

`GigaAmTranscriber-v0.5.0-linux-x64.tar.gz` (about 840 MB): the window and
`gigaam-cli`, both GigaAM models inside. GigaAM and Whisper run on the CPU (the Linux app
also carries whisper.cpp's Vulkan backend, not yet tried on a Linux GPU). Unpack it and run
`./GigaAmTranscriber/GigaAmTranscriber`.

The system must have glibc 2.39 or newer (Ubuntu 24.04, Debian 13, Fedora 40 and
later), FFmpeg and, for the window, WebKitGTK 4.1:

    sudo apt install ffmpeg gir1.2-webkit2-4.1
    sudo dnf install ffmpeg-free webkit2gtk4.1 gobject-introspection   # Fedora

## Downloads

- `GigaAmTranscriber-v0.5.0-windows-x64.zip` - Windows app.
- `GigaAmTranscriber-v0.5.0-linux-x64.tar.gz` - Linux app.
- `THIRD_PARTY_LICENSES.zip` - licences of the bundled components, one folder per app
  (`windows/`, `linux/`; also inside the app folders).
- `FFmpeg-8.0.1-source.zip` - source of the FFmpeg build in the Windows app (GPLv3).
- `SHA256SUMS.txt` - checksums of the files above.

The Whisper model file is an asset of the separate `models-1` release; the app downloads it
when Whisper is first chosen.

Notes of earlier versions: https://github.com/bigflyy/GigaAmTranscriber/releases
