# GigaAM Transcriber v0.6.0

Who speaks when, a tidier window, paragraphs that no longer break in the middle of a sentence,
playing from any selected word, and three speech search settings in the window. Recognition
itself is the same as in v0.5.0.

## Speakers

- The **Говорящие** switch above the text finds who speaks when. On a file without speakers it
  first asks how many people talk (**авто** if you do not know); after a search it shows or
  hides the names. **Настройки** -> **Говорящие** runs the search after every file by itself.
- Each turn starts with the speaker's coloured name on its own line. A line of chips under the
  switches shows every speaker with their share of the speech time.
- Fixing the result: a click on a name renames that speaker everywhere ("Говорящий 1" ->
  "Анна"), gives the turn to another or a new speaker, or merges two speakers into one; a
  chip's menu also jumps to the speaker's next turn. Selected words get **Говорящий** to give
  just those words to someone else. Neighbouring turns of one speaker join.
- When you give the number yourself, the window still shows how many speakers the model
  counted on its own.
- The saved files carry the names: the text and the text for an AI start each turn with
  "Анна: ", Markdown has a paragraph per turn, subtitles never mix two speakers in one cue,
  the timestamped text names the speaker on every line, and JSON gives each word its speaker.
  **Копировать** copies what is on screen, with or without names.
- Command line: `gigaam-cli recording.mp3 --speakers` (or `--speakers 3` when the number is
  known).
- The speaker models (pyannote community-1: segmentation 3.0, WeSpeaker ResNet34 and VBx
  clustering, rebuilt to run without PyTorch) are downloaded the first time, 33 MB. An hour
  of audio takes about 70 s on a GPU (DirectML) and about 3.5 min on the CPU. On public
  meeting recordings it gets about 20% of the speech time wrong (AMI, 4 meetings); on five
  Russian recordings of official events (2 to 16 speakers) it found the right number of
  speakers every time and gave 0.3% of the words to the wrong one. Two people talking at
  once, noisy rooms and many short replies are harder.

## A tidier window

- Above the text: the file name and one line of facts, then **Копировать** (its arrow:
  **Копировать для ИИ**), **Файлы** (the saved formats, creating the missing ones, **Показать
  в папке**) and **...** (**Найти варианты**, **Определить говорящих...**, **Распознать
  снова**, **Убрать из списка**). One look for all of them.
- The switches **Таймкоды**, **Сомнения** and **Говорящие** sit together over the text. A
  status line shows only while a search runs, with its **Отменить**.
- Paragraphs: a line the recogniser cut in the middle of a sentence (it cuts a line at about
  25 s even without a pause) now joins the paragraph before it, with or without speakers. The
  saved text, Markdown and the text for an AI join it the same way; subtitles and the
  timestamped text keep their timing.
- **Таймкоды** shows each paragraph's time in a column on the left, so the text stays in one
  straight column. A click on a time plays from there.

## Smaller changes

- **▶ Отсюда** on the bar over selected words plays from the first selected word and keeps
  going (**▶ Слушать** still plays only the selection).
- **Отменить** for the search for other models' suggestions; the offers found so far stay.
- The text no longer jumps down while a file is recognised. When new lines arrive below, a
  **Новый текст** button takes you there; at the end of the text it keeps following the new
  lines, and scrolling up stops that.
- Adding files shows the first of them at once, also when it has to wait. The window no longer
  switches to another file while you read: it moves to the next file only if you have not
  scrolled, clicked or played anything in the one on screen.
- **Настройки** -> **Дополнительно** (folded) has three speech search settings, each with its
  default a click away: the pause a line may end on (2 s), the speech threshold (50 %; lower
  finds quiet voices, higher suits noisy recordings) and the longest line (25 s, also the
  most). The other speech search settings stay in `gigaam-config.json`.

## Windows

`GigaAmTranscriber-v0.6.0-windows-x64.zip` (about 930 MB): unzip it anywhere and
run `GigaAmTranscriber.exe`; `gigaam-cli.exe` beside it is the command line. Both
GigaAM models and FFmpeg are inside; GigaAM uses any DirectX 12 GPU through DirectML,
Whisper any Vulkan GPU, both with the CPU as fallback. The EXEs are not code-signed,
so Windows SmartScreen may ask once. Models downloaded by earlier versions (Whisper) are found
automatically.

## Linux

`GigaAmTranscriber-v0.6.0-linux-x64.tar.gz` (about 840 MB): the window and
`gigaam-cli`, both GigaAM models inside. GigaAM and Whisper run on the CPU (the Linux app
also carries whisper.cpp's Vulkan backend, not yet tried on a Linux GPU). Unpack it and run
`./GigaAmTranscriber/GigaAmTranscriber`.

The system must have glibc 2.39 or newer (Ubuntu 24.04, Debian 13, Fedora 40 and
later), FFmpeg and, for the window, WebKitGTK 4.1:

    sudo apt install ffmpeg gir1.2-webkit2-4.1
    sudo dnf install ffmpeg-free webkit2gtk4.1 gobject-introspection   # Fedora

## Downloads

- `GigaAmTranscriber-v0.6.0-windows-x64.zip` - Windows app.
- `GigaAmTranscriber-v0.6.0-linux-x64.tar.gz` - Linux app.
- `THIRD_PARTY_LICENSES.zip` - licences of the bundled components, one folder per app
  (`windows/`, `linux/`; also inside the app folders).
- `FFmpeg-8.0.1-source.zip` - source of the FFmpeg build in the Windows app (GPLv3).
- `SHA256SUMS.txt` - checksums of the files above.

The Whisper model and the speaker models are assets of the separate `models-1` release; the
app downloads them when they are first needed.

Notes of earlier versions: https://github.com/bigflyy/GigaAmTranscriber/releases
