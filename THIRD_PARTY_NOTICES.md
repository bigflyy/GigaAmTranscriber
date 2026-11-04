# Third-party components

GigaAM Transcriber source is distributed under the repository's MIT license.
Bundled components keep their own licenses. Their texts are in the `licenses`
folder of the Windows app, in the `THIRD_PARTY_LICENSES.zip` release download,
and at the sources below.

- **GigaAM v3 models (RNNT, CTC):** [upstream repository](https://github.com/salute-developers/GigaAM), MIT.
  The app ships them converted to ONNX by `tools/export_models.py`; the weights are unchanged
  (stored as float16, which is lossless for these checkpoints).
- **Silero VAD 6.2.1:** [upstream repository](https://github.com/snakers4/silero-vad), MIT.
  The unchanged model runs inside an ONNX loop made by `tools/make_silero_scan.py`.
  The speech-region logic in `gigaam_app/vad.py` is ported from silero-vad.
- **ONNX Runtime 1.23.0:** [Microsoft](https://github.com/microsoft/onnxruntime), MIT,
  with the third-party notices in `licenses/onnxruntime/ThirdPartyNotices.txt`.
- **DirectML 1.15.4 (`DirectML.dll`):** Microsoft DirectML redistributable, shipped inside the
  `onnxruntime-directml` package, under the
  [Microsoft Software License Terms](https://www.nuget.org/packages/Microsoft.AI.DirectML/1.15.4/License)
  (`licenses/directml/LICENSE.txt`). Windows only.
- **NumPy:** [numpy.org](https://numpy.org/), BSD-3-Clause, with the licenses of the libraries it bundles.
- **Python and Tcl/Tk:** [Python licensing](https://docs.python.org/3/license.html),
  [Tcl/Tk licensing](https://www.tcl.tk/software/tcltk/license.html). Libraries that Python
  loads (zlib, OpenSSL, libffi, xz, bzip2 and others) are listed with their licenses under
  `licenses/conda`.
- **PyInstaller bootloader:** [PyInstaller](https://pyinstaller.org/), GPL 2.0 with the
  bootloader exception, which allows distributing the EXEs under any license.
- **FFmpeg:** unmodified `8.0.1-full_build-www.gyan.dev`, a separate executable
  (`ffmpeg.exe`) run for media decoding. This build is GPLv3. Its license and Gyan's
  build README, which lists the enabled external libraries and the build configuration,
  are in `licenses/ffmpeg`. [Binary supplier](https://www.gyan.dev/ffmpeg/builds/),
  [exact FFmpeg source revision](https://github.com/FFmpeg/FFmpeg/commit/894da5ca7d).
  The release also supplies `FFmpeg-8.0.1-source.zip` with this source revision.
  The external libraries keep their own licenses.

The Docker images contain Debian's `ffmpeg` package (with its copyright files in
`/usr/share/doc`), Python, NumPy and ONNX Runtime (CPU image) or ONNX Runtime GPU
with NVIDIA CUDA and cuDNN libraries from PyPI under NVIDIA's license terms (CUDA image).

No third-party binary is presented as authored by this project.
