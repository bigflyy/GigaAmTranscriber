"""Whisper on faster-whisper (CTranslate2, int8) on the CPU, behind the same model interface
as whisper_model.WhisperModel (plan 08 C2).

Used by the suggestion search when Настройки choose faster-whisper for Whisper on the
processor. Settings as in the measurement of plan 08 A3 (experiments/cpu_asr/read_fw.py):
greedy decoding (beam 1), nothing carried over from the piece before, word times, no VAD
(the app has already cut the audio). On the owner's files this was 1.6x faster than
whisper.cpp q5_0 one piece at a time and 2x when 8 pieces are read at once (read_many).

A model folder holds model.json (type "faster-whisper", written by download.py from the
catalog) and the CTranslate2 files: model.bin, config.json, preprocessor_config.json,
tokenizer.json, vocabulary.json.
"""

import json
from pathlib import Path

import numpy as np

from .asr import Word, default_cpu_threads
from .audio import SAMPLE_RATE
from .whisper_model import AUTO_LANGUAGE, whisper_confidence

MODEL_TYPE = "faster-whisper"
# Pieces per encoder call in read_many: the batch size measured in plan 08 A3 (2754 MB peak
# on the lecture, against 1879 MB for one piece at a time).
BATCH_SIZE = 8


def is_fast_whisper_folder(folder):
    """True if the model folder holds a faster-whisper model (model.json type 'faster-whisper')."""
    try:
        meta = json.loads((Path(folder) / "model.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return meta.get("type") == MODEL_TYPE


def words_from_fw(fw_words, offset_seconds, duration=None):
    """faster-whisper's words -> app Words with times from the start of the file.

    faster-whisper splits a word at a hyphen ("LLM-агентов" comes as " LLM" and "-агентов"):
    a piece without a leading space belongs to the word before, as whisper_model's
    words_from_tokens joins tokens. Times are kept inside the piece (0..duration) and in
    order. The confidence is the word's probability on the GigaAM scale (whisper_confidence);
    for a joined word the lowest of its pieces."""
    words = []
    for fw_word in fw_words:
        text = fw_word.word.strip()
        if not text:
            continue
        start, end = max(0.0, fw_word.start), max(0.0, fw_word.end)
        if duration is not None:
            start, end = min(start, duration), min(end, duration)
        end = max(end, start)
        probability = whisper_confidence(fw_word.probability)
        if words and not fw_word.word.startswith(" "):
            last = words[-1]
            words[-1] = Word(last.start, round(max(offset_seconds + end, last.end), 3), last.text + text,
                             round(min(last.confidence, probability), 3))
            continue
        if words:
            start = max(start, words[-1].start - offset_seconds)
            end = max(end, start)
        words.append(Word(round(offset_seconds + start, 3), round(offset_seconds + end, 3), text,
                          round(probability, 3)))
    return words


class FasterWhisperModel:
    """A faster-whisper model folder loaded on the CPU.

    The methods match WhisperModel's as engine.Transcriber and fix.reread_piece call them:
    encode() takes a list of chunks and returns the finished recognition, decode() passes
    it on, words() turns it into Words. read_many() reads several pieces in one batch.
    """

    joins_chunks = False
    max_chunk_seconds = 30.0
    gpu_name = None
    on_gpu = False
    device_label = "CPU"

    def __init__(self, folder, device="cpu", cpu_threads=None, language=None):
        """device: only the CPU is supported (faster-whisper's GPU path needs CUDA, which
        the app does not ship); 'gpu' raises, 'auto' and 'cpu' load on the CPU."""
        folder = Path(folder)
        meta_path = folder / "model.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"Model not found: {folder}")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if self.meta.get("type") != MODEL_TYPE:
            raise ValueError(f"{folder} is not a faster-whisper model")
        if device == "gpu":
            raise RuntimeError("faster-whisper runs only on the processor here. Choose CPU.")
        self.name = self.meta["name"]
        # A cheap size check catches truncated copies; download.py checks SHA-256.
        for entry in self.meta["files"].values():
            path = folder / entry["name"]
            if not path.is_file() or path.stat().st_size != entry["size"]:
                raise RuntimeError(f"Model file is missing or damaged: {path}")
        # Imported here: loading CTranslate2 takes a moment and only this engine needs it.
        from .faster_whisper import BatchedInferencePipeline, WhisperModel as _FwModel
        from .faster_whisper.tokenizer import _LANGUAGE_CODES

        self.cpu_threads = cpu_threads or default_cpu_threads()
        self.known_languages = set(_LANGUAGE_CODES)
        self.model = _FwModel(str(folder), device="cpu", compute_type="int8", cpu_threads=self.cpu_threads)
        self.pipeline = BatchedInferencePipeline(self.model)
        self.language = None
        self.last_language = ""
        self.set_language(language)

    def set_language(self, language):
        """A code such as 'ru', or None / 'auto' to detect the language of every chunk."""
        if language and language != AUTO_LANGUAGE and language not in self.known_languages:
            raise ValueError(f"Whisper does not know the language {language!r}")
        self.language = language

    def _language(self):
        return None if self.language in (None, "", AUTO_LANGUAGE) else self.language

    def encode(self, pieces, should_cancel=None, prompt=None):
        """Recognise each chunk on its own -> [(language, words, seconds)]. A cancel is
        checked between Whisper's segments; after one the list is shorter than the input.
        prompt: text put before every chunk (the user's terms)."""
        language = self._language()
        results = []
        for piece in pieces:
            if should_cancel is not None and should_cancel():
                break
            segments, info = self.model.transcribe(
                np.asarray(piece, dtype=np.float32), language=language, beam_size=1,
                condition_on_previous_text=False, word_timestamps=True, vad_filter=False,
                initial_prompt=prompt or None)
            found, cancelled = [], False
            for segment in segments:  # a generator: the work happens while it is read
                found.extend(segment.words or [])
                if should_cancel is not None and should_cancel():
                    cancelled = True
                    break
            if cancelled:
                break
            self.last_language = info.language
            results.append((info.language, found, len(piece) / SAMPLE_RATE))
        return results

    def decode(self, encoded):
        return encoded

    def words(self, decoded, offset_seconds):
        _, fw_words, duration = decoded
        return words_from_fw(fw_words, offset_seconds, duration)

    def read_many(self, pieces, offsets, prompt=None, batch_size=BATCH_SIZE):
        """Read several pieces in batches of batch_size -> one list of Words per piece, with
        times from the start of the file (offsets: each piece's start in the file).

        The pieces are put end to end and each one is its own clip (clip_timestamps), so
        BatchedInferencePipeline never reads across two pieces; each word goes back to the
        piece that holds its middle. All pieces get the language set with set_language;
        with none set, Whisper detects one for the whole call (the controller sends only
        pieces it knows the language of). As in plan 08 A3 (read_fw.py --mode batch)."""
        if not pieces:
            return []
        samples = [np.asarray(piece, dtype=np.float32) for piece in pieces]
        bounds, position = [], 0
        for piece in samples:
            bounds.append((position, position + len(piece)))
            position += len(piece)
        clips = [{"start": first / SAMPLE_RATE, "end": last / SAMPLE_RATE} for first, last in bounds]
        segments, info = self.pipeline.transcribe(
            np.concatenate(samples), language=self._language(), beam_size=1, word_timestamps=True,
            clip_timestamps=clips, batch_size=batch_size, initial_prompt=prompt or None)
        per_piece = [[] for _ in samples]
        for segment in segments:
            for fw_word in segment.words or []:
                middle = (fw_word.start + fw_word.end) / 2 * SAMPLE_RATE
                slot = next((index for index, (first, last) in enumerate(bounds) if first <= middle < last),
                            len(bounds) - 1)
                per_piece[slot].append(fw_word)
        self.last_language = info.language
        results = []
        for slot, fw_words in enumerate(per_piece):
            begin = bounds[slot][0] / SAMPLE_RATE
            shifted = [_Shifted(word, -begin) for word in fw_words]
            results.append(words_from_fw(shifted, offsets[slot], len(samples[slot]) / SAMPLE_RATE))
        return results

    def close(self):
        self.model = self.pipeline = None


class _Shifted:
    """A faster-whisper word with its times moved by shift seconds (read_many's pieces are
    end to end in one array; words_from_fw wants times inside their own piece)."""

    __slots__ = ("word", "start", "end", "probability")

    def __init__(self, fw_word, shift):
        self.word = fw_word.word
        self.start = fw_word.start + shift
        self.end = fw_word.end + shift
        self.probability = fw_word.probability
