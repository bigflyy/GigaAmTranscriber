"""Run sherpa-onnx speaker diarization on audio files and write RTTM files.

Pipeline: pyannote-style segmentation ONNX model, a speaker embedding ONNX
model, then agglomerative clustering (cut at a cosine threshold, or at a
given number of speakers).

Usage:
    python run_sherpa.py OUT_DIR SEGMENTATION.onnx EMBEDDING.onnx THRESHOLD AUDIO...
THRESHOLD is a float (automatic speaker count) or "nN" for exactly N speakers,
or "oracle" to take the count from a reference RTTM next to the audio.
Writes OUT_DIR/<audio stem>.rttm and appends timings to OUT_DIR/timing.tsv.
"""
import sys
import time
from pathlib import Path

import sherpa_onnx

from common import SAMPLE_RATE, load_audio, read_rttm, write_rttm

THREADS = 8


def build(segmentation, embedding, threshold, speakers):
    """Create a sherpa-onnx diarization object for one setting."""
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=segmentation),
            num_threads=THREADS),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=embedding, num_threads=THREADS),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=speakers, threshold=threshold),
        min_duration_on=0.3, min_duration_off=0.5)
    if not config.validate():
        raise SystemExit("bad sherpa-onnx config")
    return sherpa_onnx.OfflineSpeakerDiarization(config)


def main():
    out_dir = Path(sys.argv[1])
    segmentation, embedding, setting = sys.argv[2], sys.argv[3], sys.argv[4]
    out_dir.mkdir(parents=True, exist_ok=True)
    for audio_path in map(Path, sys.argv[5:]):
        threshold, speakers = 0.5, -1
        if setting == "oracle":
            reference = audio_path.with_suffix(".rttm")
            speakers = len({speaker for _, _, speaker in read_rttm(reference)})
        elif setting.startswith("n"):
            speakers = int(setting[1:])
        else:
            threshold = float(setting)
        diarizer = build(segmentation, embedding, threshold, speakers)
        audio = load_audio(audio_path)
        started = time.perf_counter()
        result = diarizer.process(audio).sort_by_start_time()
        elapsed = time.perf_counter() - started
        segments = [(s.start, s.end, f"spk{s.speaker}") for s in result]
        write_rttm(out_dir / f"{audio_path.stem}.rttm", audio_path.stem, segments)
        found = len({speaker for _, _, speaker in segments})
        seconds = len(audio) / SAMPLE_RATE
        with open(out_dir / "timing.tsv", "a", encoding="utf-8") as timing:
            timing.write(f"{audio_path.stem}\t{seconds:.1f}\t{elapsed:.2f}\t{found}\n")
        print(f"{audio_path.stem}: {seconds:.0f} s audio in {elapsed:.1f} s "
              f"({seconds / elapsed:.0f}x realtime), {found} speakers", flush=True)


if __name__ == "__main__":
    main()
