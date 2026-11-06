# New window on pywebview (design B), Windows and Linux

The owner found the sv-ttk restyle (C5 in plan 01) too close to the old window and chose
design B from the mockups: a file list on the left (done, running, waiting), the selected
file's progress and live text on the right, settings behind a link. The window is HTML/CSS
inside pywebview: Edge WebView2 on Windows, the system WebKitGTK on Linux (owner's choice;
the app names the missing package if WebKitGTK is absent). Linux recognition runs on the
CPU first; NVIDIA comes later. The engine and the CLI stay as they are.

Mockups: https://claude.ai/artifact/32pVRs6kmWRDDUiss5sYby (artboard "B - file list, running").
The sv-ttk attempt is kept as a patch outside the repo, not committed.

### Stage A: Prove pywebview

- [ ] **A1** Spike: a pywebview window with a JS-to-Python bridge, a file dialog, drag and drop with real file paths, and Python pushing events to the page; run it on Windows and in WSL Ubuntu (off screen)
- [ ] **A2** Freeze the spike with PyInstaller on Windows; measure start-up time and added size; check the WebView2-missing path shows a clear message

### Stage B: The window

- [ ] **B1** Page in `gigaam_app/web/` (HTML, CSS, JS, no CDN): design B, light and dark following the system
- [ ] **B2** Python side: an API object over the existing `Worker`; replaces the Tk `App`
- [ ] **B3** File list: add by dialog or drop, several files, queue runs one at a time, cancel, remove
- [ ] **B4** Live text for the selected file, timecodes switch, copy, open the saved files and the folder
- [ ] **B5** Settings view: model, device, CPU threads, formats, save as default; model download prompt with progress
- [ ] **B6** Status: model and device, errors, first-run model load
- [ ] **B7** Tests: the API logic with a fake worker; the page driven in a headless browser where it helps
- [ ] **B8** Remove the Tk window and its smoke test, or keep the smoke test working on the new window

### Stage C: Packaging and docs

- [ ] **C1** Windows build: pywebview and pythonnet in the build, their licences collected, smoke test on a hidden desktop, real transcription in the built EXE
- [ ] **C2** Linux build (WSL Ubuntu): PyInstaller onedir, CPU ONNX Runtime, FFmpeg choice (system or bundled), a tar.gz; run it in WSL
- [ ] **C3** README, THIRD_PARTY_NOTICES, HANDOFF; release notes for the next version

### Stage D: Later

- [ ] **D1** NVIDIA on Linux (onnxruntime-gpu with CUDA and cuDNN, like the Docker CUDA image)
- [ ] **D2** Experiment: ONNX Runtime WebGPU provider (Vulkan, any GPU make) as a light GPU option on Linux; check it is packaged and gives the same text
- [ ] **D3** Optional ideas from the mockups: audio playback from a text line, search in the text, recent files
