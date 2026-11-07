"""Whisper (a ggml model file on whisper.cpp) behind the model interface engine.Transcriber uses.

The Transcriber cuts the file into speech chunks with Silero VAD (up to about 25 s,
inside Whisper's 30 s window) and hands them over one by one. Each chunk is
recognised on its own by whisper_full: greedy decoding, nothing carried over from the
chunk before. Measured on 2026-11-07 (HANDOFF.md, session 10): whole-file decoding
and beam search invented text and loops on a 45 min call; the chunks did not.

A model folder holds model.json and the ggml file:

    {"format": 1, "name": "...", "type": "whisper", "sample_rate": 16000,
     "files": {"model": {"name": "ggml-large-v3-turbo-q5_0.bin", "size": ..., "sha256": "..."}}}
"""

import json
from pathlib import Path

from .asr import Word, default_cpu_threads
from .audio import SAMPLE_RATE
from . import whisper_cpp

AUTO_LANGUAGE = "auto"


def is_whisper_folder(folder):
    """True if the model folder holds a Whisper model (model.json type 'whisper')."""
    try:
        meta = json.loads((Path(folder) / "model.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return meta.get("type") == "whisper"


def words_from_tokens(tokens, offset_seconds, duration=None):
    """Join Whisper's text tokens into words with times from the start of the file.

    A token that begins with a space starts a new word; punctuation and word pieces
    without one stick to the word before. Tokens are joined as bytes and decoded once
    per word, because a token may end in the middle of a UTF-8 character (common for
    Cyrillic). A word runs from its first token's start to its last token's end.
    Times are kept inside the chunk (0..duration) and in order: whisper.cpp's token
    times come from a heuristic and can step back a little or run past the end.
    """
    words = []
    state = {"data": b"", "start": None, "end": None}

    def flush():
        text = state["data"].decode("utf-8", "replace").strip()
        if text and state["start"] is not None:
            start, end = state["start"], max(state["end"], state["start"])
            if duration is not None:
                start, end = min(start, duration), min(end, duration)
            if words:
                start = max(start, words[-1].start - offset_seconds)
                end = max(end, start)
            words.append(Word(round(offset_seconds + start, 3), round(offset_seconds + end, 3), text))
        state.update(data=b"", start=None, end=None)

    for token in tokens:
        if token.data.startswith(b" ") and state["data"].strip():
            flush()
        if token.data.strip():
            if state["start"] is None:
                state["start"] = max(0.0, token.start)
            state["end"] = max(0.0, token.end)
        state["data"] += token.data
    flush()
    return words


class WhisperModel:
    """A Whisper model folder loaded on whisper.cpp, on a Vulkan GPU or the CPU.

    The methods match asr.AsrModel's as engine.Transcriber calls them: encode() takes
    a list of chunks (here always one: joins_chunks is False) and already returns the
    finished recognition, decode() passes it on, words() turns it into Words.
    """

    joins_chunks = False
    max_chunk_seconds = 30.0  # Whisper's window; engine.Transcriber keeps chunks inside it

    def __init__(self, folder, device="auto", cpu_threads=None, language=None, library=None):
        folder = Path(folder)
        meta_path = folder / "model.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"Model not found: {folder}")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if self.meta.get("type") != "whisper":
            raise ValueError(f"{folder} is not a Whisper model")
        self.name = self.meta["name"]
        entry = self.meta["files"]["model"]
        path = folder / entry["name"]
        # A cheap size check catches truncated copies; download.py checks SHA-256.
        if not path.is_file() or path.stat().st_size != entry["size"]:
            raise RuntimeError(f"Model file is missing or damaged: {path}")
        self.cpu_threads = cpu_threads or default_cpu_threads()
        self.language = language
        self.last_language = ""
        self.lib = library or whisper_cpp.Library.get()
        self.context, self.gpu_name = self._open(path, device)

    def _open(self, path, device):
        """Load on the preferred GPU, or on the CPU. 'auto' falls back to the CPU when
        no Vulkan GPU is found or loading on it fails; 'gpu' raises instead."""
        gpus = self.lib.gpus() if device in ("auto", "gpu") else []
        if device == "gpu" and not gpus:
            raise RuntimeError("No Vulkan GPU found (is the GPU driver installed?). Choose CPU.")
        index = whisper_cpp.preferred_gpu(gpus)
        if index is not None:
            try:
                return whisper_cpp.Context(path, use_gpu=True, gpu_device=index, library=self.lib), gpus[index][2]
            except RuntimeError:
                if device == "gpu":
                    raise
        return whisper_cpp.Context(path, use_gpu=False, library=self.lib), None

    @property
    def on_gpu(self):
        return self.gpu_name is not None

    @property
    def device_label(self):
        return "GPU (Vulkan)" if self.on_gpu else "CPU"

    def set_language(self, language):
        """A code such as 'ru', or None / 'auto' to detect the language of every chunk."""
        if language and language != AUTO_LANGUAGE and not self.context.is_language(language):
            raise ValueError(f"Whisper does not know the language {language!r}")
        self.language = language

    def encode(self, pieces, should_cancel=None):
        """Recognise each chunk -> [(language, tokens)]. After a cancel the list is
        shorter than the input: the Transcriber keeps what is finished and stops."""
        language = None if self.language in (None, "", AUTO_LANGUAGE) else self.language
        results = []
        for piece in pieces:
            try:
                found, tokens = self.context.transcribe(piece, language=language, n_threads=self.cpu_threads,
                                                        should_cancel=should_cancel)
            except whisper_cpp.Cancelled:
                break
            self.last_language = found
            results.append((found, tokens, len(piece) / SAMPLE_RATE))
        return results

    def decode(self, encoded):
        return encoded

    def words(self, decoded, offset_seconds):
        _, tokens, duration = decoded
        return words_from_tokens(tokens, offset_seconds, duration)

    def close(self):
        self.context.close()
