"""Reference runs with NVIDIA Nemotron-3-Diarization (NeMo, torch); at most 8 speakers.

Not app code: shows what the model reaches before deciding on an ONNX port.
Runs in the owner's conda env newrag (nemo_toolkit 2.7.2, CPU torch), with the
offline configuration from the model card (30.4 s input buffer).

Usage: python run_nemotron.py MODEL.nemo OUT_DIR AUDIO...
"""
import sys
import time
from pathlib import Path

import torch
from nemo.collections.asr.models import SortformerEncLabelModel

from common import SAMPLE_RATE, load_audio, write_rttm


def main():
    model_path, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SortformerEncLabelModel.restore_from(restore_path=model_path, map_location=device, strict=False)
    model.eval()
    modules = model.sortformer_modules
    modules.spkcache_len, modules.fifo_len, modules.chunk_len = 264, 40, 340
    modules.chunk_right_context, modules.spkcache_update_period = 40, 300
    model._check_streaming_parameters()
    for audio_path in map(Path, sys.argv[3:]):
        audio = load_audio(audio_path)
        started = time.perf_counter()
        with torch.inference_mode():
            result = model.diarize(audio=[audio], batch_size=1, sample_rate=SAMPLE_RATE)
        elapsed = time.perf_counter() - started
        segments = []
        for line in result[0]:
            start, end, speaker = str(line).split()
            segments.append((float(start), float(end), speaker))
        write_rttm(out_dir / f"{audio_path.stem}.rttm", audio_path.stem, segments)
        seconds = len(audio) / SAMPLE_RATE
        found = len({s for _, _, s in segments})
        with open(out_dir / "timing.tsv", "a", encoding="utf-8") as timing:
            timing.write(f"{audio_path.stem}\t{seconds:.1f}\t{elapsed:.2f}\t{found}\n")
        print(f"{audio_path.stem}: {seconds:.0f} s audio in {elapsed:.1f} s "
              f"({seconds / elapsed:.0f}x realtime), {found} speakers", flush=True)


if __name__ == "__main__":
    main()
