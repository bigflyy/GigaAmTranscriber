"""Run the app's speaker labelling (gigaam_app.diarize, ONNX + numpy) like run_pyannote.py.

Writes OUT_DIR/<stem>.rttm (overlap kept) and OUT_DIR-excl/<stem>.rttm (one
speaker at a time), plus timing.tsv, so score_der.py / score_words.py compare
it with the torch community-1 runs.

Usage: python run_port.py MODEL_DIR OUT_DIR SPEAKERS AUDIO...
SPEAKERS: "auto", "oracle" (count from the RTTM next to the audio) or a number.
Environment: PORT_DEVICE (auto / cpu, default auto), PORT_STEP (seconds; default:
1 on a GPU, 2 on the CPU), PORT_EXCLUDE_OVERLAP=1, PORT_CHECK=reference.npz
(compare the first file's steps with export_speaker_models.py's torch reference).
"""
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from gigaam_app import diarize  # noqa: E402
from common import SAMPLE_RATE, load_audio, read_rttm, write_rttm  # noqa: E402


def check(model, audio, reference_path):
    """Compare segmentation, count and the voice-print filterbank with the torch reference."""
    ref = np.load(reference_path)
    starts = model._chunk_starts(len(audio), SAMPLE_RATE)
    padded = np.zeros(int(starts[-1]) + diarize.WINDOW_SAMPLES, dtype=np.float32)
    padded[:len(audio)] = audio
    progress = diarize._Progress(None, None)
    seg = model._segment(padded, starts, progress)
    print("segmentation", seg.shape, "vs", ref["segmentation"].shape,
          "frames differing:", float(np.mean(seg != ref["segmentation"][:len(seg)])))
    count = model._speaker_count(seg, 1.0)
    ref_count = ref["speaker_counting"][:, 0]
    print("count", count.shape, "vs", ref_count.shape, "frames differing:",
          float(np.mean(count[:len(ref_count)] != ref_count[:len(count)])))
    fb = np.load(Path(reference_path).with_name("fbank_check.npz"))
    mine = np.stack([model._fbank(w) for w in fb["wave"]])
    mine -= mine.mean(axis=1, keepdims=True)
    print("fbank max diff vs torchaudio:", float(np.abs(mine - fb["fbank"]).max()))


def main():
    model_dir, out_dir, speakers_arg = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    device = os.environ.get("PORT_DEVICE", "auto")
    step = float(os.environ["PORT_STEP"]) if os.environ.get("PORT_STEP") else None
    exclude = os.environ.get("PORT_EXCLUDE_OVERLAP") == "1"
    model = diarize.SpeakerModel(model_dir, device=device)
    print("provider:", model.provider, flush=True)
    excl_dir = Path(str(out_dir) + "-excl")
    out_dir.mkdir(parents=True, exist_ok=True)
    excl_dir.mkdir(parents=True, exist_ok=True)
    for index, audio_path in enumerate(map(Path, sys.argv[4:])):
        audio = load_audio(audio_path)
        if index == 0 and os.environ.get("PORT_CHECK"):
            check(model, audio, os.environ["PORT_CHECK"])
        number = None
        if speakers_arg == "oracle":
            number = len({s for _, _, s in read_rttm(audio_path.with_suffix(".rttm"))})
        elif speakers_arg != "auto":
            number = int(speakers_arg)
        started = time.perf_counter()
        result = model.diarize(audio, num_speakers=number, step=step, exclude_overlap=exclude)
        elapsed = time.perf_counter() - started
        stem = audio_path.stem
        write_rttm(out_dir / f"{stem}.rttm", stem, [(t.start, t.end, f"S{t.speaker:02d}") for t in result.turns])
        write_rttm(excl_dir / f"{stem}.rttm", stem, [(t.start, t.end, f"S{t.speaker:02d}") for t in result.exclusive_turns])
        seconds = len(audio) / SAMPLE_RATE
        with open(out_dir / "timing.tsv", "a", encoding="utf-8") as timing:
            timing.write(f"{stem}\t{seconds:.1f}\t{elapsed:.2f}\t{result.speakers}\n")
        print(f"{stem}: {seconds:.0f} s audio in {elapsed:.1f} s ({seconds / elapsed:.0f}x realtime), "
              f"{result.speakers} speakers, {model.timings}", flush=True)


if __name__ == "__main__":
    main()
