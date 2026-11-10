# faster-whisper 1.2.1 (vendored)

A copy of the Python package faster-whisper 1.2.1 (https://github.com/SYSTRAN/faster-whisper,
MIT licence, see LICENSE), used by gigaam_app/faster_whisper_model.py (plan 08 C2).

Why a copy and not `pip install faster-whisper`: the package requires onnxruntime, PyAV and
huggingface_hub. Its onnxruntime would be installed beside the app's onnxruntime-directml, and
both provide the same `onnxruntime` module, so DirectML would break. PyAV would bring a second
FFmpeg build, and huggingface_hub a model downloader the app does not use. The app only needs
`ctranslate2` and `tokenizers` (in requirements.txt).

Changes from the released files, each marked "GigaAM patch" in the code:

- Imports of the package's own modules are relative (`from .audio import ...`), so it lives
  inside gigaam_app.
- audio.py: `import av` moved into the three functions that use it (decode_audio and its
  helpers); the app hands numpy arrays over and never calls them.
- utils.py: `import huggingface_hub` moved into download_model; tqdm is optional (QuietBar
  stands in for it).
- transcribe.py: tqdm is optional, as in utils.py.
- The assets folder (silero_vad_v6.onnx, for vad_filter) is left out; the app finds speech
  with its own Silero model and never sets vad_filter.

To update: copy the new release's faster_whisper/*.py over these files and apply the same
changes again.
