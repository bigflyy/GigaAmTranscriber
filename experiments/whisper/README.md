# Whisper runtime test (plan 04 Stage A, measurement code, not the app)

Scripts used on 2026-11-07 to choose how the app runs Whisper large-v3-turbo. Results and
the decision are in HANDOFF.md (session 10). Run from the repository root with the dev venv
(numpy, onnxruntime-directml); test files and models lived in `build/whisper-test/` (gitignored).

| Script | Purpose |
| --- | --- |
| `gigaam_ref.py` | GigaAM RNNT through the app's pipeline: VAD chunk boundaries, text, timings (`AUDIO OUT.json gpu|cpu`) |
| `ort_whisper.py` | Whisper on ONNX Runtime (onnx-community export): numpy mel, encoder, greedy decoding with the KV cache on the GPU, fed the chunks of a GigaAM JSON |
| `wcpp_chunks.py` | Joins whisper-cli's per-chunk JSON outputs (one WAV per VAD chunk) into one chunk JSON |
| `compare.py` | Words that differ from GigaAM (case, punctuation and digit differences set apart), loops, samples |
| `app_engine.py` | The app's own Transcriber (GigaAM or Whisper on whisper.cpp, plan 04 B1) on one file: chunks with word times |
| `word_times.py` | Word times of two app_engine.py runs compared on the words both agree on |

whisper.cpp 1.9.5 was built with Vulkan from source (no Windows Vulkan binary is published):
glslc and the Vulkan headers and import library came from a conda-forge env
(`shaderc libvulkan-loader libvulkan-headers spirv-headers`, VULKAN_SDK pointed at its
`Library` folder), MSVC 2022, `cmake -G Ninja -DGGML_VULKAN=ON` in a short build folder
(the Visual Studio generator hit the 260-character path limit in the shader generator).
`GGML_NATIVE=ON` was used for the test; a shipped build needs it off.
