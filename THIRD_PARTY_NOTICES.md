# Third-party components

GigaAM Transcriber source is distributed under the repository's MIT license.
Bundled components keep their own licenses. Their texts are in the `licenses`
folder of the Windows and Linux apps, in the `THIRD_PARTY_LICENSES.zip` release
download (one folder per app, `windows/` and `linux/`), and at the sources below.

- **GigaAM v3 models (RNNT, CTC):** [upstream repository](https://github.com/salute-developers/GigaAM), MIT.
  The app ships them converted to ONNX by `tools/export_models.py`; the weights are unchanged
  (stored as float16, which is lossless for these checkpoints).
- **Whisper large-v3-turbo model (downloaded on request, not bundled):**
  [OpenAI Whisper](https://github.com/openai/whisper), MIT (`licenses/whisper-model/LICENSE.txt`).
  The app downloads the q5_0 ggml conversion published by the whisper.cpp project
  ([ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp), file
  `ggml-large-v3-turbo-q5_0.bin`), unchanged, from this repository's `models-1` release or from
  Hugging Face.
- **Speaker label models (downloaded on request, not bundled):** pyannote
  [segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) (MIT),
  [WeSpeaker ResNet34-LM](https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM)
  ([WeSpeaker](https://github.com/wenet-e2e/wespeaker), CC BY 4.0) and the PLDA of
  [speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
  (CC BY 4.0) (`licenses/speaker-models/LICENSE.txt`). Converted to ONNX by
  `experiments/diarization/export_speaker_models.py` (weights unchanged) and downloaded from this
  repository's `models-1` release. `gigaam_app/diarize.py` ports the clustering of
  [pyannote.audio](https://github.com/pyannote/pyannote-audio) 4 (MIT).
- **Silero VAD 6.2.1:** [upstream repository](https://github.com/snakers4/silero-vad), MIT.
  The unchanged model runs inside an ONNX loop made by `tools/make_silero_scan.py`.
  The speech-region logic in `gigaam_app/vad.py` is ported from silero-vad.
- **ONNX Runtime 1.23.0:** [Microsoft](https://github.com/microsoft/onnxruntime), MIT,
  with the third-party notices in `licenses/onnxruntime/ThirdPartyNotices.txt`.
- **DirectML 1.15.4 (`DirectML.dll`):** Microsoft DirectML redistributable, shipped inside the
  `onnxruntime-directml` package, under the
  [Microsoft Software License Terms](https://www.nuget.org/packages/Microsoft.AI.DirectML/1.15.4/License)
  (`licenses/directml/LICENSE.txt`). Windows only.
- **whisper.cpp 1.9.5 with ggml:** [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp), MIT
  (`licenses/whisper.cpp/LICENSE.txt`); runs the Whisper model. The app ships libraries built from
  the unmodified [v1.9.5 source](https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v1.9.5.tar.gz)
  by `tools/build_whisper_cpp.py` (in `_internal/whisper_cpp`). The Vulkan loader comes with the
  GPU driver and is not bundled.
- **NumPy:** [numpy.org](https://numpy.org/), BSD-3-Clause, with the licenses of the libraries it bundles.
- **Python:** [Python licensing](https://docs.python.org/3/license.html). Windows: libraries that
  Python loads (zlib, OpenSSL, libffi, xz, bzip2 and others) are listed with their licenses under
  `licenses/conda`. Linux: Ubuntu's Python 3.12; the system libraries that came with it
  (libpython, OpenSSL) have their Debian copyright files under `licenses/debian`.
- **pywebview 6.2.1:** [pywebview](https://github.com/r0x0r/pywebview), BSD-3-Clause; the window.
  Its dependencies: [pythonnet](https://github.com/pythonnet/pythonnet) (MIT) with
  [clr_loader](https://github.com/pythonnet/clr-loader) (MIT), [cffi](https://github.com/python-cffi/cffi)
  (MIT-0), [pycparser](https://github.com/eliben/pycparser) (BSD-3-Clause),
  [bottle](https://bottlepy.org/) (MIT), [proxy_tools](https://github.com/jtushman/proxy_tools)
  (MIT, declared in its metadata; it ships no license file) and
  [typing_extensions](https://github.com/python/typing_extensions) (PSF-2.0).
  pythonnet, clr_loader, cffi and pycparser are in the Windows app only.
- **PyGObject 3.48.2 (Linux only):** [PyGObject](https://gitlab.gnome.org/GNOME/pygobject),
  LGPL-2.1-or-later, the Python binding pywebview uses for GTK. The Linux app carries the
  unmodified files of Ubuntu 24.04's `python3-gi` 3.48.2-1 as a separate folder
  (`_internal/gi`), which can be replaced by another build of the same version; its copyright
  file is in `licenses/pygobject`. Source:
  [pygobject-3.48.2.tar.xz](https://download.gnome.org/sources/pygobject/3.48/pygobject-3.48.2.tar.xz)
  and Ubuntu's source package `pygobject` 3.48.2-1. GTK 3, WebKitGTK 4.1 and GObject
  introspection come from the user's system and are not included.
- **Microsoft WebView2 SDK 1.0.3856.49:** `Microsoft.Web.WebView2.Core.dll`,
  `Microsoft.Web.WebView2.WinForms.dll` and `WebView2Loader.dll`, shipped inside pywebview,
  under Microsoft's BSD-style SDK license with its notices (`licenses/webview2-sdk`). The
  WebView2 Runtime itself is part of Windows and is not bundled. Windows only.
- **PyInstaller bootloader:** [PyInstaller](https://pyinstaller.org/), GPL 2.0 with the
  bootloader exception, which allows distributing the EXEs under any license.
- **FFmpeg:** unmodified `8.0.1-full_build-www.gyan.dev`, a separate executable
  (`ffmpeg.exe`) run for media decoding. This build is GPLv3. Its license and Gyan's
  build README, which lists the enabled external libraries and the build configuration,
  are in `licenses/ffmpeg`. [Binary supplier](https://www.gyan.dev/ffmpeg/builds/),
  [exact FFmpeg source revision](https://github.com/FFmpeg/FFmpeg/commit/894da5ca7d).
  The release also supplies `FFmpeg-8.0.1-source.zip` with this source revision.
  The external libraries keep their own licenses.

The Linux app does not include FFmpeg: it runs the system's `ffmpeg`.

The Docker images contain Debian's `ffmpeg` package (with its copyright files in
`/usr/share/doc`), Python, NumPy and ONNX Runtime (CPU image) or ONNX Runtime GPU
with NVIDIA CUDA and cuDNN libraries from PyPI under NVIDIA's license terms (CUDA image).

No third-party binary is presented as authored by this project.
