# Speaker diarization experiments (plan 07 Stage A)

Measurement code, not the app. Data and results live in `build/diar-data` (gitignored).
Environments on the owner's machine: `~/.venvs/diar-exp` (sherpa-onnx 2.0.1,
onnxruntime-directml 1.23.0, scipy), conda `cuda-torch2` (pyannote.audio 4.0.5, pyannote.metrics),
conda `newrag` (NeMo 2.7.2). Every model run goes through agg-queue.

| Script | Purpose |
| --- | --- |
| `common.py` | ffmpeg audio loading, RTTM read / write, the speaker of a word span |
| `kremlin_index.py` | index kremlin.ru transcripts: speakers per event, video links (`OUT_DIR PAGES`) |
| `kremlin_labels.py` | speaker per recognised word from a transcript + the app's JSON: words.tsv, RTTM, UEM, SRT |
| `make_review.py` | review page: kremlin.ru video + labelled transcript (+ a system's wrong words in red) |
| `run_sherpa.py` | sherpa-onnx diarization (segmentation + embedding ONNX, AHC; threshold, `nN` or `oracle`) |
| `run_pyannote.py` | pyannote 3.1 and community-1 (torch, cached models), also the exclusive version |
| `run_nemotron.py` | NVIDIA Nemotron-3-Diarization through NeMo (needs a newer NeMo than 2.7.2) |
| `score_der.py` | DER with pyannote.metrics (collar, overlap options, UEM) |
| `score_words.py` | word speaker error: share of recognised words with the wrong speaker |
| `speed_probe.py` | DirectML vs CPU time of the segmentation and embedding ONNX models |
| `export_speaker_models.py` | community-1 for the app: segmentation and voice print ONNX (pooling inside), PLDA npz, torch reference (cuda-torch2) |
| `run_port.py` | the app's gigaam_app/diarize.py on files, RTTMs like run_pyannote.py, optional step check against the reference |
| `quantize_probe.py` | int8 (dynamic) copy of an embedding model: CPU time and closeness to float |

Shell drivers used in session 18: `build/diar-data/run_refs.sh`, `run_set.sh`, `run_ami_oracle.sh`, `relabel_rescore.sh`, `run_port_sets.sh` (the port on AMI and kremlin, scored).
