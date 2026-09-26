# v0.1.0 release verification

Tested on 2026-09-26 on Windows with an AMD Ryzen 7 7840HS, an NVIDIA
GeForce RTX 4070 Laptop GPU (8 GiB), and NVIDIA driver 581.29. This verifies
the listed cases on this machine; other hardware/driver combinations were
not tested.

## Windows artifacts

Both editions bundle the RNNT and CTC models, tokenizers, Silero VAD,
Python, and FFmpeg.

| Edition | Portable folder | Single EXE |
| --- | ---: | ---: |
| CPU | 1,542,334,592 bytes (1.44 GiB) | 1,066,341,669 bytes (0.99 GiB) |
| CUDA with CPU fallback | 5,796,165,660 bytes (5.40 GiB) | 3,771,192,580 bytes (3.51 GiB) |

GitHub downloads supply the CPU EXE directly and CUDA in two parts of
1,900 MiB and approximately 1,696.5 MiB. The join script validates each part
and the completed EXE. The full-size join was tested and its SHA-256 matched
the built EXE. Small fixtures additionally verified corrupted-part rejection
and handling of an already assembled matching file.

The folder builds are available locally under `dist/<edition>/onedir/`.
The published release distributes the single-file builds. Single-file apps
extract their contents to a temporary directory on each launch; this is
especially noticeable with CUDA. Allow space for that extraction as well as
the EXE (and the parts while assembling CUDA).

Observed GUI startup (one run each, including the test harness's one-second
screenshot delay): CPU folder 2.05 s, CPU single EXE 27.22 s, CUDA folder
2.06 s, CUDA single EXE 106.12 s. Builds/transfers were active during some
checks, so these are approximate startup observations, not controlled speed
comparisons.

## Tests

- 14 automated regression tests: settings defaults and validation, atomic
  config writes, legacy config compatibility, chunk grouping and duration
  limits, exclusion of leading silence, audio statistics, GUI defaults/help,
  scroll/selection preservation, cancellation with both partial exports,
  restart clearing, completion time, and both final TXT exports.
- Actual RNNT and CTC inference from source on CPU and CUDA, including
  streamed chunks, progress/statistics callbacks, thread settings/restoration,
  and cancellation of a longer recording after the first result.
- Packaged apps: real transcription with both models, no Conda or FFmpeg on
  PATH, an empty user model cache, and model downloads blocked. Text compared
  with the corresponding source run; both output files checked. CUDA also
  exercised explicit CPU mode. Both folder and single-file formats checked.
- Packaged GUI startup and clean shutdown, with screenshots inspected.
- CPU and CUDA Docker images: both models with `--network none`, mounted
  model cache, actual GPU use for CUDA, and both TXT outputs.
- Public registry access: anonymous manifest requests and full image pulls
  without registry credentials for both editions. Both RNNT and CTC ran
  offline from each downloaded image, with GPU inference for CUDA and text
  matching the local Docker builds. The CUDA pull needed retries after a
  slow transfer, then completed successfully.
- GitHub release uploads: server-reported SHA-256 checked against each
  local asset. `SHA256SUMS.txt` and `cuda-parts.json` accompany the release.

The transcription samples exercise packaging and functionality; they are
not an accuracy benchmark. Existing CPU/GPU and CPU thread measurements
are in [BENCHMARK.md](BENCHMARK.md); its older build-size table predates CTC
bundling.

## Build environments

- Windows CPU: Python 3.12, PyTorch 2.5.1+cpu, torchaudio 2.5.1+cpu.
- Windows CUDA: existing `cuda-torch2` environment, PyTorch 2.12.1+cu126
  and torchaudio 2.11.0+cpu. This existing environment carries optional
  dependencies and produces a larger executable.
- Both Windows builds: PyInstaller 6.22.3, Silero VAD 6.2.1.
- Docker: Python 3.11, PyTorch/torchaudio 2.5.1 (CPU or cu124), Linux amd64.

Container publication workflow:
[v0.1.0 run](https://github.com/bigflyy/GigaAmTranscriber/actions/runs/36231676622).
Runtime source is shared by both Docker and Windows builds.
