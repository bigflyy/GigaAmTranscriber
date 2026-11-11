CTranslate2 4.8.5 (the engine of faster-whisper), as published on PyPI by OpenNMT
https://github.com/OpenNMT/CTranslate2 - MIT licence (CTranslate2-LICENSE.txt).

The app runs it on the processor only. Its library (ctranslate2.dll on Windows,
libctranslate2.so on Linux) is built by the CTranslate2 project from these parts
(python/tools/prepare_build_environment_windows.sh and _linux.sh at the tag v4.8.5):

- Intel oneAPI Math Kernel Library (oneMKL) 2025.3, linked in, and on Windows the Intel
  OpenMP runtime libiomp5md.dll beside it: Intel Simplified Software License
  (Intel-Simplified-Software-License.txt). They are redistributed unmodified.
- oneDNN 3.1.1, linked in: Apache License 2.0 (oneDNN-LICENSE.txt), its own third-party
  notices in oneDNN-THIRD-PARTY-PROGRAMS.txt.
- spdlog (header-only, with its bundled fmt): MIT (spdlog-LICENSE.txt, fmt-LICENSE.txt).
- cpu_features (Google): Apache License 2.0 (cpu_features-LICENSE.txt).
- Thrust, CUB and libcu++ (NVIDIA CCCL): Apache License 2.0, with the LLVM exception for
  libcu++ (thrust-cccl-LICENSE.txt).
- CUTLASS (NVIDIA): BSD 3-Clause (cutlass-LICENSE.txt).
- The NVIDIA CUDA 12.8 runtime, linked in by the CTranslate2 build, under the NVIDIA CUDA
  Toolkit End User License Agreement (https://docs.nvidia.com/cuda/eula/). It is used only
  on NVIDIA video cards, which this app does not use for CTranslate2. NVIDIA's cuBLAS and
  cuDNN are not included: the wheel's cuDNN loader (cudnn64_9.dll) is left out of the
  Windows app, because the wheel is built without cuDNN.
- Linux only: the GNU OpenMP runtime libgomp, see the libgomp folder.

Commit of each part: spdlog 76fb40d9, cpu_features 8a494eb1, CCCL b5fe509f,
CUTLASS bbe579a9 (CTranslate2's third_party submodules at v4.8.5).
