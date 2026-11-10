"""Plan 08 A4: Parakeet TDT 0.6B v3 (sherpa-onnx, int8) reading every dumped piece on the CPU.

    python -I experiments/cpu_asr/read_parakeet.py MODEL_DIR DATA_DIR NAME [NAME ...] --label LABEL
        [--threads 8] [--batch 1] [--most N]

MODEL_DIR holds encoder*.onnx, decoder*.onnx, joiner*.onnx and tokens.txt of a sherpa-onnx NeMo
transducer export. Greedy search. --batch 1 decodes one piece at a time (as the search does now);
a larger --batch hands that many pieces to one decode_streams call. Words are joined from the
tokens: a token starting with a space (or the SentencePiece mark U+2581) starts a word; a word ends where the
next one starts (or 0.3 s after its last token at the end). Parakeet gives no confidence, so it is
left empty. Writes DATA_DIR/readings/LABEL/NAME.json. Run with the cpu-asr-exp venv.
"""

import argparse
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import load_pieces, peak_ram_mb, piece_path, save_readings  # noqa: E402

SAMPLE_RATE = 16000
WORD_MARK = "▁"


def one_file(folder, pattern):
    found = sorted(folder.glob(pattern))
    if not found:
        raise SystemExit(f"no {pattern} in {folder}")
    return str(found[0])


def words_from(tokens, times, shift, piece_end):
    """Tokens and their start times -> [start, end, text, None] with times from the file start."""
    words = []
    for token, start in zip(tokens, times):
        # sherpa-onnx gives NeMo tokens with a plain space where SentencePiece has its mark.
        if token.startswith((WORD_MARK, " ")) or not words:
            words.append([start, None, token.replace(WORD_MARK, " ")])
        else:
            words[-1][2] += token
    rows = []
    for index, (start, _, text) in enumerate(words):
        end = words[index + 1][0] if index + 1 < len(words) else min(start + 0.3, piece_end)
        if text.strip():
            rows.append([round(start + shift, 3), round(max(end, start) + shift, 3), text.strip(), None])
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir")
    parser.add_argument("data_dir")
    parser.add_argument("names", nargs="+")
    parser.add_argument("--label", required=True)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--most", type=int)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    import sherpa_onnx

    folder = Path(args.model_dir)
    started = time.perf_counter()
    recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=one_file(folder, "encoder*.onnx"), decoder=one_file(folder, "decoder*.onnx"),
        joiner=one_file(folder, "joiner*.onnx"), tokens=one_file(folder, "tokens.txt"),
        num_threads=args.threads, sample_rate=SAMPLE_RATE, feature_dim=128,
        decoding_method="greedy_search", model_type="nemo_transducer")
    print(f"{args.label}: loaded in {time.perf_counter() - started:.1f} s")

    for name in args.names:
        info = load_pieces(args.data_dir, name, args.most)
        pieces = info["pieces"]
        results, total = [], 0.0
        for first in range(0, len(pieces), args.batch):
            group = pieces[first:first + args.batch]
            began = time.perf_counter()
            streams = []
            for piece in group:
                stream = recognizer.create_stream()
                stream.accept_waveform(SAMPLE_RATE, np.load(piece_path(args.data_dir, name, piece)))
                streams.append(stream)
            recognizer.decode_streams(streams)
            spent = time.perf_counter() - began
            total += spent
            for piece, stream in zip(group, streams):
                result = stream.result
                results.append({"number": piece["number"], "spent": round(spent / len(group), 3),
                                "language": getattr(result, "lang", None) or None,
                                "words": words_from(list(result.tokens), list(result.timestamps),
                                                    piece["start"], piece["seconds"])})
        audio_seconds = sum(p["seconds"] for p in pieces)
        save_readings(args.data_dir, args.label, name, total, results, {"peak_ram_mb": peak_ram_mb()})
        print(f"{args.label} {name}: {len(pieces)} pieces, {audio_seconds:.0f} s of audio, {total:.1f} s "
              f"({total / max(1, len(pieces)):.2f} s per piece), peak RAM {peak_ram_mb()} MB")


if __name__ == "__main__":
    main()
