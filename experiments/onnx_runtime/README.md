# ONNX Runtime prototype (measurement code, not the app)

Scripts used on 2026-11-04 to decide whether to leave PyTorch. Paths to
conda environments and sample audio are hard-coded for the owner's machine.

| Script | Purpose |
| --- | --- |
| `profile_old.py` | Stage timings of the old torch pipeline (`python profile_old.py AUDIO cuda`) |
| `profile_split.py` | VAD vs encoder vs RNNT decode split for the old pipeline |
| `export_onnx.py` | Export a GigaAM ASR model: `MODEL_encoder.onnx` (wav in, mel inside) and `MODEL_head.npz` |
| `ortasr.py` | Torch-free pipeline: `python ortasr.py AUDIO cpu|cuda|dml MODEL_DIR [ENCODER_FILE]` |
| `compare.py` | Word-level diff of two transcript JSON files |
| `diar.py` | sherpa-onnx speaker diarization timing: `python diar.py AUDIO MODEL_DIR EMBEDDING.onnx THRESHOLD` |

Export (needs the torch environment, run from the repository root):

    conda run -n cuda-torch2 python experiments/onnx_runtime/export_onnx.py v3_e2e_rnnt OUT_DIR

Run-time environments only need `numpy`, `sentencepiece` and one of
`onnxruntime`, `onnxruntime-gpu` or `onnxruntime-directml`, plus `ffmpeg` on PATH.
For CUDA the prototype reuses the CUDA and cuDNN DLLs from the torch environment
through `onnxruntime.preload_dlls`.

Environment variables for `ortasr.py`: `THREADS` (default 8), `MAX_BATCH` (16),
`BATCH_SECONDS` (200), `OUT_JSON` (write chunks and text for `compare.py`).
