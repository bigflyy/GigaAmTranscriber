# CPU runtimes for the suggestion search (plan 08 Stage A, measurement code, not the app)

Scripts used on 2026-11-10 to compare how fast, and how well, other CPU runtimes read the pieces
the app's suggestion search reads. Results: HANDOFF.md (session 24) and docs/plans/08-whisper-cpu.md.
Data and models lived in `build/cpu-asr-test/` (gitignored): one folder per file with the pieces,
`models/` (mobiuslabsgmbh/faster-whisper-large-v3-turbo, csukuangfj sherpa-onnx Parakeet TDT 0.6B v3
int8, timurlexx LingoFlip int8w) and `readings/LABEL/FILE.json`.

| Script | Venv | Purpose |
| --- | --- | --- |
| `dump_pieces.py` | dev (gigaam-app) | RNNT text of a file, its doubtful lines cut as the app cuts them (.npy + pieces.json) |
| `read_wcpp.py` | dev | The app's whisper.cpp q5_0 on the pieces (`--language auto`, `ru`) |
| `read_fw.py` | cpu-asr-exp | faster-whisper int8, `--mode one` or `batch`, `--language auto`, `ru` or `hint` |
| `read_parakeet.py` | cpu-asr-exp | Parakeet TDT on sherpa-onnx |
| `compare.py` | dev | Offers per runtime through fix.suggestion_from, times, agreement with a base label; also builds `wcpp-hint` from the auto and ru runs |
| `common.py` | both | Even piece sample (`--most`), the language hint from GigaAM's script, saving readings |

The cpu-asr-exp venv (`~/.venvs/cpu-asr-exp`, Python 3.13): `pip install faster-whisper sherpa-onnx numpy psutil`
(faster-whisper 1.2.1, ctranslate2 4.8.5, sherpa-onnx 2.0.1). Run the scripts there with `python -I`.
