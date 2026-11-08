"""Reference runs with pyannote.audio 4 (torch) on cached models: 3.1 and community-1.

Not app code: these show what the torch pipelines reach, so an ONNX port can be
checked against them. Runs in the owner's conda env cuda-torch2 (pyannote.audio
4.0.5, CUDA), offline from the Hugging Face cache.

community-1 is gated on Hugging Face, but it is segmentation-3.0 + WeSpeaker
ResNet34-LM + the community-1 PLDA with VBx clustering (pyannote's own defaults:
threshold 0.6, Fa 0.07, Fb 0.8, segmentation min_duration_off 0). The first two
are cached, and the PLDA files (plda.npz, xvec_transform.npz) are cached too.

Usage: python run_pyannote.py MODE OUT_DIR SPEAKERS AUDIO...
MODE: "p31" (speaker-diarization-3.1) or "c1" (community-1).
SPEAKERS: "auto", "oracle" (count from the reference RTTM next to the audio) or a number.
Environment: PYANNOTE_STEP, the window step as a share of the 10 s window (default 0.1 = 1 s;
0.2 = 2 s halves the work), to measure what a faster CPU setting costs in quality.
Writes OUT_DIR/<stem>.rttm; for c1 also OUT_DIR-excl/<stem>.rttm (the exclusive
version, one speaker at a time, meant for labelling words).
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch  # noqa: E402
from pyannote.audio import Pipeline  # noqa: E402
from pyannote.audio.pipelines import SpeakerDiarization  # noqa: E402

from common import SAMPLE_RATE, load_audio, read_rttm  # noqa: E402

PLDA_DIR = next((Path.home() / ".cache/huggingface/hub/models--pyannote--speaker-diarization-community-1/snapshots").glob("*/plda"))


def build(mode):
    """Create the pipeline for MODE on the GPU when there is one."""
    if mode == "p31":
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
    else:
        pipeline = SpeakerDiarization(
            segmentation="pyannote/segmentation-3.0",
            embedding="pyannote/wespeaker-voxceleb-resnet34-LM",
            plda=str(PLDA_DIR), clustering="VBxClustering",
            segmentation_step=float(os.environ.get("PYANNOTE_STEP", "0.1")))
        pipeline.instantiate(pipeline.default_parameters())
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipeline.to(device)
    return pipeline


def write(annotation, path, file_id):
    """Write a pyannote Annotation as RTTM."""
    lines = [f"SPEAKER {file_id.replace(' ', '_')} 1 {seg.start:.3f} {seg.duration:.3f} <NA> <NA> {label} <NA> <NA>"
             for seg, _, label in annotation.itertracks(yield_label=True)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    mode, out_dir, speakers_arg = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    pipeline = build(mode)
    for audio_path in map(Path, sys.argv[4:]):
        options = {}
        if speakers_arg == "oracle":
            options["num_speakers"] = len({s for _, _, s in read_rttm(audio_path.with_suffix(".rttm"))})
        elif speakers_arg != "auto":
            options["num_speakers"] = int(speakers_arg)
        waveform = torch.from_numpy(load_audio(audio_path)).unsqueeze(0)
        started = time.perf_counter()
        output = pipeline({"waveform": waveform, "sample_rate": SAMPLE_RATE}, **options)
        elapsed = time.perf_counter() - started
        annotation = getattr(output, "speaker_diarization", output)
        write(annotation, out_dir / f"{audio_path.stem}.rttm", audio_path.stem)
        exclusive = getattr(output, "exclusive_speaker_diarization", None)
        if exclusive is not None:
            write(exclusive, Path(str(out_dir) + "-excl") / f"{audio_path.stem}.rttm", audio_path.stem)
        seconds = waveform.shape[1] / SAMPLE_RATE
        found = len(annotation.labels())
        with open(out_dir / "timing.tsv", "a", encoding="utf-8") as timing:
            timing.write(f"{audio_path.stem}\t{seconds:.1f}\t{elapsed:.2f}\t{found}\n")
        print(f"{audio_path.stem}: {seconds:.0f} s audio in {elapsed:.1f} s "
              f"({seconds / elapsed:.0f}x realtime), {found} speakers", flush=True)


if __name__ == "__main__":
    main()
