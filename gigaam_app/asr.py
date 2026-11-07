"""GigaAM speech recognition on ONNX Runtime: encoder sessions and greedy decoders.

A model folder is produced by tools/export_models.py. The encoder graph takes
raw 16 kHz audio and contains the log-mel front-end. RNNT models also need the
small prediction and joint networks, which run in numpy: they are tiny, and a
per-step call into ONNX Runtime or a GPU would cost more than the arithmetic.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path

import numpy as np

import onnxruntime as ort

WORD_START = "▁"  # SentencePiece marks the first piece of every word with this character
GPU_PROVIDERS = ("CUDAExecutionProvider", "DmlExecutionProvider")
PROVIDER_NAMES = {"CUDAExecutionProvider": "GPU (CUDA)", "DmlExecutionProvider": "GPU (DirectML)",
                  "CPUExecutionProvider": "CPU"}


@dataclass
class Word:
    start: float  # seconds from the start of the file
    end: float
    text: str
    # How sure the model was of the word, 0..1: the lowest probability among its tokens
    # (letter_groups explains how it is counted). None when unknown: text typed by hand,
    # a word of punctuation only, a transcript saved before word confidence existed.
    confidence: float = None
    # Other readings offered for this word and the words after it (plan 06, fix.py): a list
    # of {"models": [model keys], "count": current words replaced, starting with this one,
    # "words": [[start, end, text, confidence], ...]}. None when there are none. Kept in the
    # history, not written to the transcript files.
    suggestions: list = None


def letter_key(piece):
    """A vocabulary piece without punctuation and letter case; the word-start mark stays.
    WORD_START + "Вы" and WORD_START + "вы," give the same key; "." and "," an empty one."""
    letters = "".join(ch for ch in piece.lower().replace("ё", "е") if ch.isalnum())
    return (WORD_START if piece.startswith(WORD_START) else "") + letters


def letter_groups(vocab, blank_id):
    """For every token id: the ids of the tokens that spell the same letters (an int array),
    or None for a token without letters (punctuation, the bare word-start mark).

    Used for word confidence. GigaAM v3 writes case and punctuation itself, so the raw
    probability of a token is shared between "вы" and "Вы", or "идею" and "идею."; it
    often sits near 0.5 on a word that is right. Counting such tokens together measures
    how sure the model is of the letters (measured on a 455 s lecture, plan 03 B2).
    """
    by_key = {}
    for token, piece in enumerate(vocab):
        if token != blank_id:
            by_key.setdefault(letter_key(piece), []).append(token)
    groups = []
    for token, piece in enumerate(vocab):
        key = letter_key(piece)
        groups.append(None if token == blank_id or key in ("", WORD_START) else np.array(by_key[key]))
    return groups


def token_confidence(probabilities, token, groups, blank_id):
    """Probability of the emitted token's letters, with blank left out: in RNNT the blank
    also stands for "say it one frame later", which says nothing about the word.
    probabilities: a distribution over the vocabulary, blank included.
    None for a token without letters."""
    group = groups[token]
    if group is None:
        return None
    rest = 1.0 - float(probabilities[blank_id])
    if rest <= 0.0:
        return None
    return min(1.0, float(probabilities[group].sum()) / rest)


def default_cpu_threads():
    """Physical cores are what matter for the encoder; logical count / 2 approximates them."""
    return max(1, min(8, (os.cpu_count() or 2) // 2))


_cuda_libraries_loaded = False


def _load_cuda_libraries():
    """onnxruntime-gpu installed with its [cuda,cudnn] extras finds the NVIDIA
    libraries from PyPI only after preload_dlls(); a system CUDA works without it."""
    global _cuda_libraries_loaded
    if not _cuda_libraries_loaded and hasattr(ort, "preload_dlls"):
        _cuda_libraries_loaded = True
        try:
            ort.preload_dlls()
        except Exception:  # missing libraries show up as a CPU fallback below
            pass


def create_session(path, device="auto", cpu_threads=None):
    """Open an ONNX model on the requested device.

    device: "auto" (GPU when one works, else CPU), "gpu" or "cpu".
    Returns (session, provider name). On "auto" a failing GPU falls back to CPU.
    """
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.intra_op_num_threads = cpu_threads or default_cpu_threads()
    options.log_severity_level = 3  # hide the harmless "Memcpy nodes added" warnings
    available = ort.get_available_providers()
    gpu = [name for name in GPU_PROVIDERS if name in available]
    if device == "gpu" and not gpu:
        raise RuntimeError("No GPU provider in this build of ONNX Runtime. Choose CPU.")
    attempts = gpu if device in ("auto", "gpu") else []
    if "CUDAExecutionProvider" in attempts:
        _load_cuda_libraries()
    for provider in attempts:
        try:
            session = ort.InferenceSession(str(path), _gpu_options(options, provider),
                                           providers=[_provider_entry(provider), "CPUExecutionProvider"])
        except Exception:
            if device == "gpu":
                raise
            continue
        if session.get_providers()[0] == provider:
            return session, provider
    session = ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])
    return session, "CPUExecutionProvider"


def _provider_entry(provider):
    if provider == "CUDAExecutionProvider":
        # The default EXHAUSTIVE search benchmarks every convolution again for
        # each new input length: seconds of warm-up per chunk length.
        return (provider, {"cudnn_conv_algo_search": "HEURISTIC"})
    return provider


def _gpu_options(options, provider):
    if provider == "DmlExecutionProvider":
        # Required by the DirectML provider.
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return options


class RnntHead:
    """Prediction network (one LSTM layer) and joint network for greedy RNNT decoding."""

    def __init__(self, path, blank_id, max_symbols_per_frame=10):
        weights = np.load(path)
        self.embed = weights["embed"]
        self.w_ih = np.ascontiguousarray(weights["w_ih"].T)
        self.w_hh = np.ascontiguousarray(weights["w_hh"].T)
        self.bias = weights["bias"]
        self.enc_w = np.ascontiguousarray(weights["enc_w"].T)
        self.enc_b = weights["enc_b"]
        self.pred_w = np.ascontiguousarray(weights["pred_w"].T)
        self.pred_b = weights["pred_b"]
        self.out_w = np.ascontiguousarray(weights["out_w"].T)
        self.out_b = weights["out_b"]
        self.hidden = self.w_hh.shape[0]
        self.blank_id = blank_id
        self.max_symbols = max_symbols_per_frame

    def _lstm_step(self, x, h, c):
        """One LSTM step. PyTorch packs the gates as input, forget, cell, output."""
        z = x @ self.w_ih + h @ self.w_hh + self.bias
        n = self.hidden
        input_gate = 1.0 / (1.0 + np.exp(-z[:n]))
        forget_gate = 1.0 / (1.0 + np.exp(-z[n:2 * n]))
        cell_input = np.tanh(z[2 * n:3 * n])
        output_gate = 1.0 / (1.0 + np.exp(-z[3 * n:]))
        c = forget_gate * c + input_gate * cell_input
        return output_gate * np.tanh(c), c

    def decode(self, encoded, groups=None):
        """encoded: (frames, dim) for one chunk. Returns [(token id, frame index)], or with
        groups (letter_groups of the vocabulary) [(token id, frame index, confidence)].

        Two things keep this fast. The encoder half of the joint network is
        computed for all frames in one matrix product. The prediction network
        only runs after a token is emitted, because its output does not change
        on blank steps; most frames are blank.
        """
        encoder_part = encoded @ self.enc_w + self.enc_b
        h = np.zeros(self.hidden, np.float32)
        c = np.zeros(self.hidden, np.float32)
        # The first prediction step sees an all-zero input, as in GigaAM.
        h, c = self._lstm_step(np.zeros(self.hidden, np.float32), h, c)
        prediction_part = h @ self.pred_w + self.pred_b
        tokens = []
        for frame in range(encoder_part.shape[0]):
            for _ in range(self.max_symbols):
                logits = np.maximum(encoder_part[frame] + prediction_part, 0.0) @ self.out_w + self.out_b
                token = int(logits.argmax())  # argmax of logits equals argmax of log-softmax
                if token == self.blank_id:
                    break
                if groups is None:
                    tokens.append((token, frame))
                else:
                    # Softmax only for emitted tokens: a few per second of audio, cheap.
                    probabilities = np.exp(logits - logits[token])
                    probabilities /= probabilities.sum()
                    tokens.append((token, frame, token_confidence(probabilities, token, groups, self.blank_id)))
                h, c = self._lstm_step(self.embed[token], h, c)
                prediction_part = h @ self.pred_w + self.pred_b
        return tokens


def ctc_decode(log_probs, blank_id, groups=None):
    """Greedy CTC: best class per frame, merge repeats, drop blanks -> [(token, frame)].
    With groups (letter_groups): [(token, frame, confidence)], the confidence taken at
    the token's first frame."""
    best = log_probs.argmax(axis=-1)
    keep = best != blank_id
    keep[1:] &= best[1:] != best[:-1]
    frames = np.nonzero(keep)[0]
    if groups is None:
        return [(int(best[frame]), int(frame)) for frame in frames]
    return [(int(best[frame]), int(frame),
             token_confidence(np.exp(log_probs[frame]), int(best[frame]), groups, blank_id))
            for frame in frames]


class AsrModel:
    """One exported GigaAM model folder, ready to transcribe chunks of audio."""

    def __init__(self, folder, device="auto", cpu_threads=None):
        folder = Path(folder)
        meta_path = folder / "model.json"
        if not meta_path.is_file():
            raise FileNotFoundError(f"Model not found: {folder}")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.name = self.meta["name"]
        self.kind = self.meta["type"]
        self.frame_seconds = float(self.meta["frame_seconds"])
        self.blank_id = int(self.meta["blank_id"])
        for entry in self.meta["files"].values():
            # A cheap size check catches truncated copies. SHA-256 is checked when the
            # release is built (bundled models) or downloaded (download.py).
            path = folder / entry["name"]
            if not path.is_file() or path.stat().st_size != entry["size"]:
                raise RuntimeError(f"Model file is missing or damaged: {path}")
        self.vocab = json.loads((folder / "vocab.json").read_text(encoding="utf-8"))
        self.session, self.provider = create_session(folder / "encoder.onnx", device, cpu_threads)
        self.head = RnntHead(folder / "head.npz", self.blank_id) if self.kind == "rnnt" else None
        self.groups = letter_groups(self.vocab, self.blank_id)

    @property
    def on_gpu(self):
        return self.provider in GPU_PROVIDERS

    @property
    def device_label(self):
        return PROVIDER_NAMES.get(self.provider, self.provider)

    @property
    def joins_chunks(self):
        """True if the Transcriber should send waiting chunks to encode() together."""
        return self.on_gpu

    def encode(self, pieces, should_cancel=None):
        """Run the encoder on a list of 1-D sample arrays as one zero-padded batch.

        Returns one (frames, dim) array per piece (CTC: log-probabilities).
        should_cancel is not used: one encoder call takes well under a second.
        """
        longest = max(len(piece) for piece in pieces)
        batch = np.zeros((len(pieces), longest), dtype=np.float32)
        lengths = np.zeros(len(pieces), dtype=np.int64)
        for row, piece in enumerate(pieces):
            batch[row, :len(piece)] = piece
            lengths[row] = len(piece)
        output, output_lengths = self.session.run(None, {"wav": batch, "wav_len": lengths})
        return [np.ascontiguousarray(output[row, :output_lengths[row]], dtype=np.float32)
                for row in range(len(pieces))]

    def decode(self, encoded):
        """Greedy decoding of one encoded chunk -> [(token id, frame index, confidence)]."""
        if self.kind == "rnnt":
            return self.head.decode(encoded, self.groups)
        return ctc_decode(encoded, self.blank_id, self.groups)

    def words(self, tokens, offset_seconds):
        """Turn decoded tokens into words with times.

        A word starts at a piece that begins with the SentencePiece marker, or
        after a space token in character vocabularies. Its time runs from its
        first token's frame to one frame past its last token. tokens are
        (token, frame) or (token, frame, confidence); a word's confidence is the
        lowest among its tokens (None when none has one).
        """
        words, pieces, first, last, lowest = [], [], None, None, None

        def flush():
            text = "".join(pieces).strip()
            if text:
                words.append(Word(round(offset_seconds + first * self.frame_seconds, 3),
                                  round(offset_seconds + (last + 1) * self.frame_seconds, 3), text,
                                  None if lowest is None else round(lowest, 3)))

        for token, frame, *rest in tokens:
            confidence = rest[0] if rest else None
            piece = self.vocab[token]
            starts_word = piece.startswith(WORD_START) or piece == " "
            if starts_word and pieces:
                flush()
                pieces, lowest = [], None
            piece = piece.replace(WORD_START, " ")
            if not pieces:
                first = frame
            if piece.strip():
                pieces.append(piece)
                last = frame
                if confidence is not None:
                    lowest = confidence if lowest is None else min(lowest, confidence)
            elif not pieces:
                first = None
        if pieces:
            flush()
        return words
