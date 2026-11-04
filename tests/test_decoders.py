"""Greedy CTC and RNNT decoders and the token-to-word step, on small synthetic models."""

import numpy as np
import pytest

from gigaam_app.asr import AsrModel, RnntHead, Word, ctc_decode

# ---------------------------------------------------------------- CTC


def one_hot_log_probs(classes, n_classes):
    """Log-probabilities where frame i is certain of class classes[i]."""
    log_probs = np.full((len(classes), n_classes), -20.0, dtype=np.float32)
    log_probs[np.arange(len(classes)), classes] = 0.0
    return log_probs


def test_ctc_merges_repeats_and_drops_blanks():
    blank = 4
    frames = [blank, 1, 1, blank, 1, 2, 2, 2, blank, blank, 3]
    tokens = ctc_decode(one_hot_log_probs(frames, 5), blank)
    # A blank between two equal classes keeps both; the frame is where each token starts.
    assert tokens == [(1, 1), (1, 4), (2, 5), (3, 10)]


def test_ctc_all_blank_gives_nothing():
    assert ctc_decode(one_hot_log_probs([3, 3, 3], 4), blank_id=3) == []


def test_ctc_first_frame_counts():
    assert ctc_decode(one_hot_log_probs([0, 0, 2], 3), blank_id=2) == [(0, 0)]


# ---------------------------------------------------------------- RNNT

HIDDEN, ENC_DIM, JOINT, VOCAB = 6, 5, 7, 4  # VOCAB tokens plus one blank


def write_head(path, seed, blank_bias=0.0):
    """A random prediction + joint network in the layout of tools/export_models.py (torch shapes)."""
    rng = np.random.default_rng(seed)

    def r(*shape):
        return rng.normal(0, 0.8, shape).astype(np.float32)

    out_b = r(VOCAB + 1)
    out_b[VOCAB] += blank_bias
    np.savez(path, embed=r(VOCAB + 1, HIDDEN), w_ih=r(4 * HIDDEN, HIDDEN), w_hh=r(4 * HIDDEN, HIDDEN),
             bias=r(4 * HIDDEN), enc_w=r(JOINT, ENC_DIM), enc_b=r(JOINT), pred_w=r(JOINT, HIDDEN),
             pred_b=r(JOINT), out_w=r(VOCAB + 1, JOINT), out_b=out_b)
    return path


def naive_rnnt_greedy(weights, encoded, blank, max_symbols):
    """Textbook greedy RNNT as GigaAM runs it: full joint with log-softmax at every step,
    and the prediction network re-run for the current label on every step."""
    w = {key: weights[key].astype(np.float64) for key in weights.files}

    def sigmoid(x):
        return 1 / (1 + np.exp(-x))

    def predict(label, state):
        x = np.zeros(HIDDEN) if label is None else w["embed"][label]
        h, c = state
        z = w["w_ih"] @ x + w["w_hh"] @ h + w["bias"]
        i, f, g, o = np.split(z, 4)
        c = sigmoid(f) * c + sigmoid(i) * np.tanh(g)
        h = sigmoid(o) * np.tanh(c)
        return h, (h, c)

    zero_state = (np.zeros(HIDDEN), np.zeros(HIDDEN))
    state, label, tokens = zero_state, None, []
    for frame in range(encoded.shape[0]):
        for _ in range(max_symbols):
            out, new_state = predict(label, state)
            joint = np.maximum(w["enc_w"] @ encoded[frame] + w["enc_b"] + w["pred_w"] @ out + w["pred_b"], 0)
            logits = w["out_w"] @ joint + w["out_b"]
            log_probs = logits - np.log(np.exp(logits - logits.max()).sum()) - logits.max()
            token = int(log_probs.argmax())
            if token == blank:
                break
            tokens.append((token, frame))
            state, label = new_state, token
    return tokens


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize("blank_bias", [-2.0, 0.0, 2.0])
def test_rnnt_fast_decoder_equals_naive(tmp_path, seed, blank_bias):
    path = write_head(tmp_path / "head.npz", seed, blank_bias)
    encoded = np.random.default_rng(100 + seed).normal(0, 1, (40, ENC_DIM)).astype(np.float32)
    fast = RnntHead(path, blank_id=VOCAB, max_symbols_per_frame=3).decode(encoded)
    assert fast == naive_rnnt_greedy(np.load(path), encoded, VOCAB, max_symbols=3)


def test_rnnt_max_symbols_per_frame_caps_emissions(tmp_path):
    # A strongly negative blank bias makes every step emit a token.
    path = write_head(tmp_path / "head.npz", seed=1, blank_bias=-50.0)
    encoded = np.zeros((4, ENC_DIM), dtype=np.float32)
    tokens = RnntHead(path, blank_id=VOCAB, max_symbols_per_frame=2).decode(encoded)
    assert [frame for _, frame in tokens] == [0, 0, 1, 1, 2, 2, 3, 3]


def test_rnnt_all_blank(tmp_path):
    path = write_head(tmp_path / "head.npz", seed=2, blank_bias=50.0)
    assert RnntHead(path, blank_id=VOCAB).decode(np.ones((10, ENC_DIM), np.float32)) == []


# ---------------------------------------------------------------- words


def bare_model(vocab, frame_seconds=0.04):
    """An AsrModel with only what words() needs, without loading any ONNX file."""
    model = object.__new__(AsrModel)
    model.vocab = vocab
    model.frame_seconds = frame_seconds
    return model


def test_words_from_sentencepiece_pieces():
    model = bare_model(["▁при", "вет", "▁мир", ",", "▁", "!"])
    tokens = [(0, 2), (1, 3), (2, 10), (3, 11), (4, 20), (5, 21)]
    words = model.words(tokens, offset_seconds=1.0)
    # A lone marker piece starts a word; the "!" after it becomes that word.
    assert words == [Word(1.08, 1.16, "привет"), Word(1.4, 1.48, "мир,"), Word(1.84, 1.88, "!")]


def test_words_from_character_vocabulary():
    model = bare_model([" ", "д", "а", "н", "е", "т"])
    tokens = [(0, 0), (1, 1), (2, 2), (0, 3), (3, 5), (4, 6), (5, 9), (0, 10)]
    words = model.words(tokens, offset_seconds=0.0)
    assert [w.text for w in words] == ["да", "нет"]
    # Leading and trailing spaces do not stretch the word times.
    assert (words[0].start, words[0].end) == (0.04, 0.12)
    assert (words[1].start, words[1].end) == (0.2, 0.4)


def test_words_empty():
    assert bare_model(["▁a"]).words([], 3.0) == []
