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

- [x] **A1** Spike: a pywebview window with a JS-to-Python bridge, a file dialog, drag and drop with real file paths, and Python pushing events to the page; run it on Windows and in WSL Ubuntu (off screen) (works on both; WebView2 does not paint on a hidden desktop, so Windows tests use an off-screen, non-focusable window; under WSL unset WAYLAND_DISPLAY and use GDK_BACKEND=x11 with Xvfb; drop and the file dialog need a check by hand)
- [x] **A2** Freeze the spike with PyInstaller on Windows; measure start-up time and added size; check the WebView2-missing path shows a clear message (pywebview and pythonnet add about 2 MB; frozen: window frame at 1.3-1.6 s, page at 2.5-2.7 s on the first runs, warm medians 1.2 s and 1.75 s, against 0.85 s for the Tk window; without WebView2 pywebview silently falls back to the IE engine, so the app must check and explain, see B6)

### Stage B: The window

- [x] **B1** Page in `gigaam_app/web/` (HTML, CSS, JS, no CDN): design B, light and dark following the system; create the window with `background_color` set to the theme's background, so the frame is never white before the page paints
- [x] **B2** Python side: an API object over the existing `Worker`; replaces the Tk `App`
- [x] **B3** File list: add by dialog or drop, several files, queue runs one at a time, cancel, remove (checked off screen by tools/window_check.py; the file dialog and drop need a check by hand)
- [x] **B4** Live text for the selected file, timecodes switch, copy, open the saved files and the folder (also: create a missing format from the text; copy and opening files need a check by hand)
- [x] **B5** Settings view: model, device, CPU threads, formats, save as default; model download prompt with progress
- [x] **B6** Status: model and device, errors, first-run model load; before opening the window, check for WebView2 (Windows) or WebKitGTK (Linux) and otherwise show a native message with the install link or package name; window background set to the theme colour so the frame is not white while the page loads (message checked with GIGAAM_PRETEND_NO_WEBVIEW=1: MessageBox on a hidden desktop, stderr and xmessage under Xvfb)
- [x] **B7** Tests: the API logic with a fake worker; the page driven in a headless browser where it helps (tests/test_controller.py, tests/test_window.py; instead of a headless browser, tools/window_check.py drives the real window: 19 checks pass on Windows, dark and light, and in WSL Ubuntu under Xvfb)
- [x] **B8** Remove the Tk window and its smoke test, or keep the smoke test working on the new window (Tk window removed; tools/gui_smoke_test.py runs the EXE off screen, since WebView2 does not run on a hidden desktop)

- [x] **B9** Owner's requests after trying C1 (2026-11-06): ask before closing while a file or a download runs; keep the transcribed files in the list between sessions (gigaam_app/history.py: one JSON per file in the per-user folder, with word times; "Убрать из списка" forgets it, the saved files stay; window_check.py checks a second session); settings save by themselves, with a reset button instead of "save as default" (owner's choice; 28 checks)

### Stage C: Packaging and docs

- [x] **C1** Windows build: pywebview and pythonnet in the build, their licences collected, smoke test on a hidden desktop, real transcription in the built EXE (smoke test off screen instead; program part 121 MiB; window after 1.8-2.0 s; lecture written after 10.5 s; release zip not made)
- [x] **C2** Linux build (WSL Ubuntu): PyInstaller onedir, CPU ONNX Runtime, FFmpeg choice (system or bundled), a tar.gz; run it in WSL (tools/build_linux.py; system GTK, WebKitGTK and FFmpeg, PyGObject copied in; tar.gz 825 MiB; window under Xvfb in 0.7-1.3 s; lecture text identical to Windows; needs glibc 2.39+)
- [x] **C3** README, THIRD_PARTY_NOTICES, HANDOFF; release notes for the next version (draft in docs/RELEASE_NOTES_NEXT.md; before a release: rebuild Windows, merge the Linux licences into THIRD_PARTY_LICENSES.zip, bump the version)

### Stage E: Release v0.3.0 (owner's go, 2026-11-06)

- [x] **E1** Owner tried the build ("they kinda work"): refuse files without sound (txt and others) with a note instead of adding them and failing; ffmpeg decides, not the extension (owner chose this) (controller.has_sound; window_check.py 29 checks on Windows and WSL; three waits there now wait for the page, not only the controller)
- [x] **E2** Bump the version to 0.3.0; move docs/RELEASE_NOTES_NEXT.md into RELEASE_NOTES.md
- [x] **E3** Rebuild Windows (release zip, smoke tests) and Linux (tar.gz, smoke tests in WSL) (zip 916 MiB, tar.gz 825 MiB; both unpacked fresh: lecture text identical, Windows window transcribed the 60 s file)
- [x] **E4** THIRD_PARTY_LICENSES.zip with the Linux licences (pygobject, debian) merged in; SHA256SUMS (folders windows/ and linux/; sha256sum -c passes)
- [ ] **E5** Ask the owner, then tag, push and publish the GitHub release

### Stage D: Later

- [ ] **D1** NVIDIA on Linux (onnxruntime-gpu with CUDA and cuDNN, like the Docker CUDA image)
- [ ] **D2** Experiment: ONNX Runtime WebGPU provider (Vulkan, any GPU make) as a light GPU option on Linux; check it is packaged and gives the same text
- [ ] **D3** Optional ideas from the mockups: audio playback from a text line, search in the text (recent files: done in B9)
