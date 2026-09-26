# Third-party components

GigaAM Transcriber source is distributed under the repository's MIT license.
Bundled components retain their own licenses; see the companion
`THIRD_PARTY_LICENSES.zip`, the notices inside the packaged app, and the sources below.

- **GigaAM / model weights:** [upstream repository](https://github.com/salute-developers/GigaAM), MIT.
- **Silero VAD:** [upstream repository](https://github.com/snakers4/silero-vad), MIT.
- **PyTorch / torchaudio:** [PyTorch](https://github.com/pytorch/pytorch),
  [torchaudio](https://github.com/pytorch/audio); their bundled third-party licenses also apply.
- **Python / Tcl / Tk:** [Python licensing](https://docs.python.org/3/license.html),
  [Tcl/Tk licensing](https://www.tcl.tk/software/tcltk/license.html).
- **CUDA runtime libraries:** NVIDIA components bundled by the CUDA PyTorch distribution;
  their NVIDIA license terms apply. The CPU executable contains no CUDA runtime.
- **FFmpeg:** unmodified `8.0.1-full_build-www.gyan.dev`, a separate executable
  invoked for media decoding. This build is GPLv3. Its GPL license and Gyan's
  build README are included under `licenses/ffmpeg` in the app and in the
  release's license archive. [Binary supplier](https://www.gyan.dev/ffmpeg/builds/),
  [exact FFmpeg source revision](https://github.com/FFmpeg/FFmpeg/commit/894da5ca7d).
  The release also supplies an archive of this FFmpeg source revision.
  Gyan's build README identifies enabled external libraries and the build configuration;
  those external libraries retain their respective licenses.

No third-party binary is presented as authored by this project.
