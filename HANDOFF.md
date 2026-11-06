# Handoff: state and findings

Last updated 2026-11-06 (session 9). Current plan: [docs/plans/02-webview-window.md](docs/plans/02-webview-window.md)
(new window; Stages A-C done, D is later); the rewrite plan [docs/plans/01-onnx-runtime-rewrite.md](docs/plans/01-onnx-runtime-rewrite.md)
still holds B9, F and E. Owner's ideas: [docs/IDEAS.md](docs/IDEAS.md).

## Session 9 (2026-11-06): app icon and Markdown export done; Whisper is next

- Icon: mockups at https://claude.ai/artifact/W1UuSDLLfjZPy1rRvonVm5 (A-E); owner picked A
  (wave into lines), no color named, so blue (app accent). tools/make_icon.py (needs Pillow,
  not an app dependency) writes gigaam_app/icons/gigaam.ico (16-256; 16, 20, 24, 32 px drawn on
  the pixel grid), .png (GTK window) and .svg. Both specs set it; window.py passes
  `icon=` to webview.start (WinForms loads the .ico, otherwise it takes sys.executable's icon).
  Checked: the off-screen dev window carries it (WM_GETICON small and big), both built EXEs
  carry it at 16-256 (PrivateExtractIcons), build smoke tests pass. Linux: wired, not built yet.
- Incident: a build with `--out build/next` ran while the owner had the app open from there;
  rmtree deleted build/next/app models/ and licenses/ before a locked DLL stopped it. Restored
  all 54 files from the v0.3.0 zip (model SHA-256 checked). build_windows.py now renames the old
  folder first and stops if it is in use. Never build into build/next without asking.
- Dev venv: `C:\Users\User\.venvs\gigaam-app` (requirements-build.txt + Pillow), outside Temp
  on purpose: venvs in the Temp scratchpads keep losing python.exe and pythonw.exe (and some
  files) within hours, other .exe files stay; not Defender, cause unknown. Tests: 346 passed,
  1 skipped; window_check 30/30 (with `PYTHONPATH=.` for launchers/cli_main.py from source).
- Markdown format `md` done (824c975): owner chose "title + timed sections":
  `# name.mp3`, `*date · M:SS · GigaAM v3 RNNT*`, then `## MM:SS` sections of about a minute
  (a new one at the first segment 60 s after the section start, or at a 5 s pause after 15 s;
  H:MM:SS in every heading for files of an hour or more). Settings checkbox, MD chip, CLI
  `--formats md`. catalog.ModelInfo got `title` (model_title()). The 45 min phone call gives
  48 sections and needed no escapes. window_check: MD chip check, plus two fixes (the second
  session hard-coded research-2026.mp4; the cancelled-text step read the page too early).
- Owner's order (2026-11-06): Markdown (done), then Whisper, then plan 03 Stage A. Whisper is
  "one of the most important tasks probably" (IDEAS.md, Models). Next: write
  docs/plans/04-whisper.md. It takes over plan 01 Stage F for Whisper (Parakeet and Qwen3-ASR
  stay in Stage F) and feeds plan 03 C1. First step proposed to the owner: a short test of
  large-v3-turbo through ONNX Runtime DirectML (the app's engine) and through whisper.cpp with
  Vulkan (any GPU, quantized), on the 455 s lecture and the 45 min call: speed, accuracy
  against GigaAM, download size. faster-whisper (CTranslate2) is out: NVIDIA only, about 1 GB
  more DLLs. Then a catalog download with a switch in settings. Told the owner that on Russian
  GigaAM is usually more accurate than Whisper; Whisper's gain is other languages and a second
  reading.
- Pushed 2026-11-07 (owner OK'd). Owner saw no icon and no .md: they were running the old
  v0.3.0 build in build/next (16:23, before both commits; PyInstaller's default icon). Fresh
  build made into build/try instead (app open from build/next): smoke tests pass, EXE icon
  checked. md is off by default (txt + timestamps); asked the owner whether to turn it on.

## Session 8 (2026-11-06): release v0.3.0 prepared (plan 02 Stage E), plan 03 drafted

- Owner tried the build in build/next ("they kinda work"), OK'd pushing session 7's commits
  (pushed, fd26e6d) and deleting build/app (deleted). Owner's order: release v0.3.0, then the
  "fix a part of the text" idea (draft plan docs/plans/03-fix-a-part.md, questions not asked yet).
- E1, owner's choice: files without sound are not added; one toast names them
  ("Не добавлено, в файле нет звука: ..."). `controller.has_sound()` asks ffmpeg for an Audio
  stream (photos and silent videos have only Video), so the extension does not matter; folders
  still filter by extension and get a note when nothing matched. Toasts stay 60 ms per character.
- window_check.py (29 checks, Windows and WSL): three steps waited for the controller and then
  read the page too early; failed twice while the GPU was shared. They now wait for the page.
- Licences: THIRD_PARTY_LICENSES.zip has `windows/` (build_windows.py) and `linux/`
  (build_linux.py adds it to the zip in its --release folder and updates SHA256SUMS). Build
  Windows first: it rewrites SHA256SUMS and the zip. This session's WSL scripts (build.sh,
  merge.sh = re-add the Linux line and licences without rebuilding, unpack.sh, wcheck.sh) are in
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\59f921e3-888c-4266-ac6e-17cc5cc8fa41\scratchpad\wsl`.
- The first Windows release build failed its GUI smoke test ("did not close after WM_CLOSE"):
  another session's GigaAM job held the GPU, the model load ran past the test's 12 s, and closing
  waits for the load. Rerun alone: passes; closing during a normal load takes about 4 s.
  gui_smoke_test.py now gives the app a temporary GIGAAM_CONFIG and GIGAAM_HISTORY (it used the
  owner's).
- Release assets ready in `C:\MyProjects\GigaAmTranscriber\build\release` (Windows zip 916 MiB,
  Linux tar.gz 825 MiB, licences zip, FFmpeg source, SHA256SUMS; `sha256sum -c` passes). Both
  unpacked fresh: 455 s lecture text identical (Windows CLI 20 s on DirectML; Linux 50 s on a busy
  CPU); the unpacked Windows window transcribed the 60 s file. RELEASE_NOTES.md holds the v0.3.0
  notes (draft file removed). Owner OK'd publishing: main pushed, tag v0.3.0 pushed, GitHub
  release created from RELEASE_NOTES.md. Owner chose no Docker images for v0.3.0
  (recognition unchanged; DOCKER.md keeps the v0.2.0 tags).
- Plan 03 decisions (owner): readings shown side by side to pick, no automatic replacement;
  playback of the selection in Stage A. New idea: the app icon (mockups, then fix it), in IDEAS.md.

## Session 7 (2026-11-06): Linux build (C2), docs (C3), owner's requests (B9)

- Owner tried the C1 build ("kinda worked"); auto-start on adding files is fine. Owner asked for
  (1) a question before closing while a file runs and (2) the transcribed files kept between
  sessions. Both done (plan 02 B9). Six commits pushed on the owner's OK; this session's commits
  are not pushed yet. Ideas from the owner went to docs/IDEAS.md.
- Close question: `controller.ask_close()` sends `confirm_close` to the page and the closing event
  returns False; the page's "Закрыть" calls `Api.close_anyway()`. On close the window now calls
  `worker.stop()` (cancel, let the job end and write its partial text, drop waiting jobs) and
  `controller.stop()` (handle the last events, so the cancelled file is remembered). Before this,
  closing mid-file aborted the process on Linux ("terminate called without an active exception")
  and the partial text was not sure to be written.
- History: `gigaam_app/history.py`, one JSON per remembered file (whole transcript with word
  times) in `paths.history_dir()` = `%LOCALAPPDATA%\GigaAmTranscriber\history` or
  `~/.local/share/gigaam-transcriber/history`; `GIGAAM_HISTORY` overrides. Kept: done files and
  cancelled files with text. Controller without `history=` remembers nothing (tests). Restored files
  come first; the page selects the newest at start. Retry keeps the entry's place; a failed retry
  keeps the old result on disk.
- Owner chose: settings save automatically (every change goes to gigaam-config.json), and a
  "Сбросить настройки" button replaced "Сохранить как настройки по умолчанию"; the reset keeps the
  speech search values, which only the file sets. `GIGAAM_CONFIG` names another settings file
  (window_check.py uses a temporary one; 28 checks).
- Windows build with all of this: `C:\MyProjects\GigaAmTranscriber\build\next\app\GigaAmTranscriber\`
  (the old `build\app` was locked by the owner's running window and is partly deleted). The Linux
  tarball in build/release-linux predates the settings change; rebuild it for a release.
- C2, how the frozen Linux app gets PyGObject and WebKitGTK (fits the plan's "system WebKitGTK",
  so not asked): GTK, WebKitGTK, libgirepository, typelibs and FFmpeg come from the system;
  PyGObject is copied in as plain files from Ubuntu's `python3-gi` 3.48.2 (`GIGAAM_GI_DIR`, gi is
  excluded from analysis because PyInstaller's gi hooks would bundle WebKitGTK and set
  GI_TYPELIB_PATH inside the app); libraries in the ldd closure of the system's WebKitGTK, GTK and
  girepository (plus libstdc++, libgcc_s) are dropped from the bundle; `readline` is excluded
  (GPL-3, unused). `paths.restore_child_environment()` (called by both launchers) gives started
  processes the user's LD_LIBRARY_PATH back. Checked: WebKitNetworkProcess and WebKitWebProcess map
  no app libraries, no library name is loaded twice in the window process.
- Build: `tools/build_linux.py` with WSL venv `~/.venvs/gigaam-build` (system Python 3.12.3, no
  system site packages, requirements-build.txt). Run through agg-queue, for example
  `agg-queue.exe run --kind build --what "..." -- wsl.exe -d Ubuntu -- bash <script>` (Git Bash needs
  `MSYS_NO_PATHCONV=1`). Wrapper scripts of this session: scratchpad `wsl/` (build.sh, verify.sh,
  wcheck.sh, unpack.sh) under
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\5297a77e-1f2f-44cc-b6de-976f4752fc6a\scratchpad`.
  Output: `~/gigaam-build/app/GigaAmTranscriber` (973 MiB, program 115 MiB) and
  `C:\MyProjects\GigaAmTranscriber\build\release-linux\GigaAmTranscriber-v0.2.0-linux-x64.tar.gz`
  (825 MiB, version not bumped yet). Smoke tests pass: CLI 60 s file in 4-9 s, missing WebKitGTK
  message (names only gir1.2-webkit2-4.1), window under a private Xvfb `:97` in 0.7-1.3 s and
  transcribing. Unpacked tarball: permissions 0755 only for the two programs; 455 s lecture on the
  CPU in 34 s, 1.5 GB RAM, text byte-identical to the Windows build.
- Tests: 325 passed, 1 skipped on Windows (dev venv: this session's scratchpad `venv-app`); WSL
  from source with `~/.venvs/gigaam-spike`. New `pytest.ini` (testpaths = tests: on Linux pytest
  collected tools/gui_smoke_test.py). `tools/window_check.py`: 26 checks, both answers of the close
  question, a second window session that must show the remembered files; passes on Windows and
  in WSL under Xvfb; it uses a temporary history folder.
- C3: README (Linux download and build, the list and its folder, close question), THIRD_PARTY_NOTICES
  (PyGObject LGPL with source link, Debian copyrights, no FFmpeg on Linux), draft release notes in
  `docs/RELEASE_NOTES_NEXT.md` (v0.3.0 proposed).
- Open before a release: the Windows build is from C1 (no close question, no history): rebuild;
  `THIRD_PARTY_LICENSES.zip` is built from the Windows licences only, so merge in the Linux ones
  (pygobject, debian); bump the version. Not checked: a real Linux desktop (only WSL + Xvfb), and on
  Linux by hand the file dialog, drop, copy and opening files. ONNX Runtime prints a "GPU device
  discovery failed ... /sys/class/drm/card0" warning in WSL (no DRM device there); harmless.

## Session 6 (2026-11-06): the new window built, Stage B done

- Code: `gigaam_app/web/` (index.html, app.css, app.js; inlined by window.py, no server, no CDN),
  `gigaam_app/controller.py` (queue, settings, status texts; no GUI toolkit), `gigaam_app/window.py`
  (theme, WebView2/WebKitGTK check, `Api` bridge, `Sender`, `main`), `gigaam_app/worker.py` (the
  old Tk `Worker`, moved; now emits `loading` / `load_failed`). `gigaam_app/gui.py` (Tk) is deleted;
  `python -m gigaam_app` and `launchers/gui_main.py` open the new window.
- Behaviour choices made without asking (owner may change them): files start as soon as they are
  added (no "Распознать" button; the mockup had none); settings apply at once, to the next file;
  closing the window while a file runs cancels it (no confirm); a dropped folder adds the media
  files directly inside it; saved-file chips also offer to create a missing format from the text.
- **pywebview bug on GTK:** `evaluate_js` passes the script length in characters where WebKit
  wants bytes, so any script with Cyrillic is cut short ("Unexpected end of script"). The sender
  uses `json.dumps(ensure_ascii=True)`; scripts in tools stay ASCII.
- The model load holds the GIL for about 2 s; the worker sleeps 0.1 s after `loading` so the page
  can show it first. Bridge calls wait during the load.
- Tests: `tests/test_controller.py` (fake worker), `tests/test_window.py`; 313 passed, 1 skipped.
  `tools/window_check.py LONG SHORT --out DIR` drives the real window (19 checks: queue, cancel
  midway, timecodes, create SRT, retry, remove, device change, download dialog against a local
  test model, load error banner): passes on Windows in both themes and in WSL Ubuntu under Xvfb
  (WSL venv `~/.venvs/gigaam-spike` now has requirements.txt installed). Not testable without a
  real mouse: the file dialog, drop, copy to clipboard, opening files and the folder.
- Missing engine: `GIGAAM_PRETEND_NO_WEBVIEW=1` shows the message (MessageBox checked on a hidden
  desktop; on Linux stderr plus zenity/kdialog/xmessage). `GIGAAM_THEME=light|dark` forces a theme.
- `tools/gui_smoke_test.py` now runs the EXE off screen (`GIGAAM_WINDOW_OFFSCREEN=1`) on the
  normal desktop, because WebView2 does not run on a hidden desktop.
- C1 build (`python tools/build_windows.py --no-zip`, through agg-queue): spec drops Tk, adds
  `gigaam_app/web` as data, excludes other pywebview backends and cffi's compiler modules (they
  import distutils, which broke the analysis). Licences added: pywebview, pythonnet, clr_loader,
  cffi, pycparser, bottle, typing_extensions from their metadata; `packaging/licenses/`
  WebView2-SDK-LICENSE/NOTICE (from the 1.0.3856.49 NuGet package) and proxy_tools-LICENSE (MIT
  text; the package has no licence file). Results: program 121 MiB, folder 1180 MiB; CLI smoke
  CPU and DirectML pass; GUI window after 1.8-2.0 s; the 455 s lecture written after 10.5 s
  (`build/app/GigaAmTranscriber/`). No release zip was made.
- Next: C2 (Linux build). Open question there: a frozen app cannot import the system's PyGObject
  (gi is ABI-tied to the system Python); options are PyInstaller's gi hooks (bundle GTK/WebKit,
  large) or building with the system Python 3.12 and adding the system dist-packages path
  (works only on matching distros). Linux FFmpeg: planned to use the system package (the app
  already finds ffmpeg on PATH). Then C3 (README parts done this session; Linux and release notes left).
- Sample audio copies for checks: scratchpad of this session, `audio/` (research-2026.mp4 and a
  60 s cut). Screenshots: its `shots/` folder.

## Session 5 (2026-11-06): new window on pywebview, Stage A done

- C5 (sv-ttk restyle) was built but the owner found it too close to the old window.
  Not committed; the whole diff is kept outside the repo at
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\3f818aad-2f5d-47ea-8f62-788af417f8b8\scratchpad\c5-backup\c5-sv-ttk.patch`.
  Two side fixes from it were committed: the smoke test reads the title with
  GetWindowTextW (11edf89), and the first model load waits for the window to draw (101b70c).
- Mockups: https://claude.ai/artifact/32pVRs6kmWRDDUiss5sYby. **Owner chose design B**
  (file list on the left: done, running, waiting; selected file's progress and live text on the right).
- **Owner decisions:** build it in HTML/CSS with pywebview; Linux too, using the system
  WebKitGTK (the app names the package if it is missing); Linux recognition on the CPU
  first, NVIDIA later; ONNX Runtime WebGPU (Vulkan) as a later experiment for a light
  Linux GPU option. Owner accepted the webview start time (dark frame about 1.2 s, content
  about 1.75 s, against 0.85 s for Tk) on 2026-11-06; no PyInstaller splash.
- Spike results (`experiments/webview_spike/`, pywebview 6.2.1): bridge both ways, pushed
  lines and theme detection work on Windows (WebView2 156) and WSL Ubuntu 24.04 (WebKitGTK 2.52).
  Frozen on Windows: +2 MB; window frame at 1.3-1.6 s, page at 2.5-2.7 s (Tk: 0.85 s).
  Rechecked warm (5 runs each, from process start, frozen): frame 1.2 s, page 1.75 s.
  Where it goes: Python + pywebview import 0.45 s, pythonnet/.NET + WinForms 0.7 s,
  WebView2 start and page 0.5 s. A kept profile (`private_mode=False`) does not help;
  `background_color` does not change timing but removes the white flash (frame shows
  in the app's dark colour). Bench (bench.py, bench_frozen.py, a frozen build):
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\6a3c0658-6d34-4248-a107-e790afcad1b6\scratchpad\speed`.
  Without WebView2 pywebview falls back to the IE engine silently, so the app must check (B6).
  Drop and the file dialog were not tested (need a real mouse).
- Testing: WebView2 does not paint on a hidden desktop; use an off-screen window
  (x, y = -6000, `focus=False`) and PrintWindow. In WSL, unset `WAYLAND_DISPLAY` and set
  `GDK_BACKEND=x11` under Xvfb; once this session forgot it and a spike window showed on
  the owner's screen through WSLg for a few seconds.
- Dev venv for this session: `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\3f818aad-2f5d-47ea-8f62-788af417f8b8\scratchpad\venv-app`
  (requirements-build.txt + pywebview); the session 3 venv lost its python.exe.
  Tests: 280 passed, 1 skipped. WSL venv: `~/.venvs/gigaam-spike` (system site packages for gi).

## Decisions (approved by the owner on 2026-11-04)

- Drop PyTorch from the shipped app. Run GigaAM on ONNX Runtime with the
  DirectML provider (any DX12 GPU) and CPU fallback, in one onedir build.
  PyTorch stays only as a developer tool for exporting checkpoints to ONNX.
- Release v0.2.0: one Windows zip (GUI + console CLI, RNNT and CTC bundled),
  updated Docker images. Speaker diarization is NOT part of it (owner: not now).
- Old builds in `dist/` may be deleted once the new build is verified.
- Commit and publish the release only after the owner has seen the new build work
  (owner confirmed in session 3).

## Session 4 (2026-11-05): B2 done (not adopted), B6 built, multilingual dropped

Commits from 0d7dd4a on main, pushed. Tests: 280 passed, 1 skipped
(parity), with the session 3 venv
`C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\740fa774-5b91-4234-b11a-c5b322975530\scratchpad\venv-app`.

**B2, fp16 compute on DirectML: not adopted.** `experiments/onnx_runtime/fp16_encoder.py`
converts the encoder explicitly: fp16 everywhere except the mel front-end (log of
1e-9 powers) and the frame-length arithmetic (fp16 is exact only to 2048). The
onnxconverter-common converter failed (left the graph's Cast(to=float) nodes,
type errors, then all-NaN output). RNNT, 7 files / 2 h of audio, encoder time:

| GPU | fp32 | fp16 | Text vs fp32 |
| --- | ---: | ---: | --- |
| RTX 4070 Laptop (DML device 0) | 42.6 s | 40.8 s | lecture identical; `2023 06 10 12 08 59.mp3` loses 10 of 2863 words ("Так, вторая группа.", dialogue dashes) |
| Radeon 780M iGPU (DML device 1) | 175 s | 107 s | same kind of differences |

Keeping Softmax and LayerNorm in fp32 did not help (still differs, and adds a diff
on the lecture). Only the iGPU would gain, and the text changes, so the app stays
fp32. Side finding: DML device 0 is the RTX on this laptop; the app does not pick
an adapter (DirectML's default).

**B6, downloads of extra models (code done; no model uses it yet).**
- Models: `multilingual_ctc` (220M, 845 MB) and `multilingual_large_ctc` (600M,
  2.2 GB), the two v0.1 offered. Char-level CTC (Latin, Cyrillic, Kazakh letters),
  lowercase, no punctuation. Checkpoints are float32 and NOT fp16-exact; lossy fp16
  storage changed 8 tokens on a Russian file, so they ship fp32. The 600M weights
  exceed the 2 GB protobuf and 2 GiB GitHub asset limits: `export_models.py` now puts
  weights above 1.8 GiB into `encoder.data1` / `encoder.data2` (external data, at most
  1.5 GiB each). v3_e2e_ctc re-exports byte for byte. Max |onnx - torch|: 2.5e-4 and 8.8e-4.
- Speed on DML (RTX): 220M like v3 (lecture 4.6 s); 600M 1.7x slower, load 9 s cold.
  On English audio both write Cyrillic transliteration (that file is out of domain).
- App: `gigaam_app/catalog.py` (keys RNNT, CTC; Multilingual entries were removed, see below;
  sizes and SHA-256 of each file in code; v0.1 names as aliases),
  `gigaam_app/download.py` (staging `<folder>.partial`, SHA-256 per file, HTTP Range
  resume, 3 attempts, cancel, disk space check, rename when all pass),
  `paths.downloads_dir()` (`%LOCALAPPDATA%\GigaAmTranscriber\models`, `GIGAAM_DOWNLOADS`).
  CLI `--list-models`, `--download MODEL`; GUI asks before downloading, progress and
  cancel. Bug fixed on the way: v0.2.0 rejected v0.1 settings naming a multilingual model.
- Tested: `tests/test_download.py` (17 tests, local HTTP server: damaged, cut,
  resumed, cancelled, Range ignored, 404, too long, no space). GUI end to end in
  process with the Tk root withdrawn (never shown): large model cancelled at 312 MB,
  resumed with `Range: bytes=327155712-`, loaded; small model downloaded from
  "Распознать", transcribed a file. Docker `--download` is documented but not run.
- **Owner decision: multilingual GigaAM dropped.** Ignoring case and punctuation,
  its Russian text differs from RNNT by 5% (lecture), 10% (phone call) and 26%
  (multi-speaker class), and English comes out transliterated. Removed from the
  catalog, GUI and docs; v0.1 settings that chose it load with RNNT. The downloader,
  the external-data export and `tools/stage_model_assets.py` stay for future models
  (Stage F, B9, diarization models). Release tag `models-1` is not created.
- Owner: for English and other languages only Whisper-class models make sense.
  Plan Stage F (before E) compares Parakeet TDT 0.6B v3, Whisper large-v3-turbo and
  Qwen3-ASR on labelled Russian and English audio. B9: int8 encoder for CPU-only
  machines as an optional download (owner suggested q8/q4).
- Owner tried the app from source: it works. Owner wants a nicer window design: plan C5.
- No release date. v0.2.1/v0.3.0 has little visible change so far (v0.1 settings fix);
  a release makes sense with B9 or Stage F.

## Release v0.2.0 (session 3, 2026-11-04): published

- Dev venv recreated (scratchpad `venv-app` of session 3); 261 passed, 1 skipped
  (the parity test, which needs `GIGAAM_PARITY_AUDIO` / `GIGAAM_PARITY_REFERENCE`).
- Rewrite committed in 9 commits (8c4135e..eba7650) and pushed to main.
- GitHub release v0.2.0 at eba7650, marked Latest:
  https://github.com/bigflyy/GigaAmTranscriber/releases/tag/v0.2.0
  Four assets uploaded; GitHub's SHA-256 digests match SHA256SUMS.txt, and a fresh
  download of all assets passed `sha256sum -c` (the first `gh release download` of the
  zip broke off with an HTTP/2 stream error; `curl -C -` resumed it).
- Workflow "Publish CPU and CUDA containers" run 41867784548 with v0.2.0: both jobs
  passed. Pushed `ghcr.io/bigflyy/gigaamtranscriber:v0.2.0-cpu` / `:cpu`
  (sha256:73cf43eb...) and `:v0.2.0-cuda` / `:cuda` (sha256:c615b94f...).
  The workflow smoke test runs `--version` and transcribes a 2 s silent file offline
  with RNNT and CTC: it proves the image starts and loads both models without network,
  but the encoder does not run on speech there. Real speech was checked only on the
  locally built CPU image (session 2). The CUDA image is still not GPU-tested.
- Remaining work: plan items B2 (fp16 on DirectML), B6 (downloads of extra models),
  and Stage E (speaker diarization, owner: not now).

## State of the rewrite (session 2, 2026-11-04)

Done and verified in session 2:

- Tests: `tests/test_decoders.py`, `test_outputs.py`, `test_config.py`, `test_cli.py`,
  `test_engine.py` (pipeline with fakes), `test_models.py` (real models, optional parity
  via `GIGAAM_PARITY_AUDIO` / `GIGAAM_PARITY_REFERENCE`). 261 passed; parity passes on
  DirectML and CPU.
- Windows build: `packaging/GigaAmTranscriber.spec` (two EXEs, one `_internal`),
  `packaging/README.txt`, `packaging/licenses/` (Silero, DirectML texts),
  `tools/build_windows.py` (checks, build, payload, licences, smoke tests, zip, SHA256SUMS),
  `tools/gui_smoke_test.py` (GUI EXE on a hidden desktop, PrintWindow capture, WM_CLOSE).
  Output: `build/app/GigaAmTranscriber/` and `build/release/`.
- Fixes found by testing the frozen build: PyInstaller took `tcl86t.dll` from
  `C:\ProgramData\miniconda3\Library\bin` on PATH (window crashed); the build now runs
  PyInstaller with a clean PATH and checks every DLL. The CLI failed on file names outside
  the console code page when output was redirected; fixed (`safe_console`). The first
  model load delayed the window to 3-5 s; now it starts 150 ms after the window (about 1 s).
- CLI expands wildcards itself (cmd.exe does not).
- `asr.py` calls `onnxruntime.preload_dlls()` before CUDA sessions (Docker CUDA image).
- Removed torch-era files: transcribe.py, gui.py, gui_help.py, app_config.py, model_catalog.py,
  build_release.py, prepare_release.py, benchmark.py, giga.py, release/, tests/test_desktop.py,
  requirements-cpu.txt, setup.py (upstream packaging that read requirements.txt),
  README_TRANSCRIBER.md (folded into README.md), debug files. `gigaam/` stays: the export
  tools and experiments use it.
- New requirements: `requirements.txt` (app), `requirements-build.txt`, `requirements-export.txt`.
- Docs rewritten: README.md, DOCKER.md, RELEASE_NOTES.md, BENCHMARK.md, RELEASE_TESTS.md,
  THIRD_PARTY_NOTICES.md, gigaam-config.example.json (version 2).
- Dockerfile: two stages, export with CPU torch in stage 1, final image has no torch;
  `ORT_VARIANT=cpu|cuda`. Workflow builds both and smoke-tests offline.
- `third_party/` (gitignored) holds `ffmpeg/FFmpeg-8.0.1-source.zip` and
  `v0.1.0/THIRD_PARTY_LICENSES.zip`, copied out of `dist/` with matching checksums.

- Final build verified (end of session 2): `build/release/` holds
  `GigaAmTranscriber-v0.2.0-windows-x64.zip` (917 MiB, SHA-256 b790348e...),
  `THIRD_PARTY_LICENSES.zip`, `FFmpeg-8.0.1-source.zip`, `SHA256SUMS.txt`. The zip was
  unpacked to a fresh folder and tested there: GUI on a hidden desktop transcribed the
  455 s lecture (window 1.6 s, text identical to v0.1), CLI on CPU and DirectML.
- Docker CPU image built locally (`gigaam-transcriber:cpu`, 2.81 GB): offline RNNT and CTC
  work, RNNT text identical to v0.1. The CUDA image is not built or GPU-tested locally.
  Docker Desktop pulled from PyPI at ~60 kB/s while the host got 1.9 MB/s; its only proxy
  is the built-in `http.docker.internal:3128` in "system" mode (Windows proxy is off). The
  owner chose to leave Docker Desktop settings as they are.
- `dist/` deleted (owner approved; v0.1.0 assets are all on the GitHub release).
Dev venv: scratchpad `venv-app` of session 3 (may be gone); recreate with
`uv venv venv-app --python C:\Users\User\.conda\envs\cuda-torch2\python.exe` and
`uv pip install -r requirements-build.txt`. Run the build with that venv's python.


## Measurements (2026-11-04, Ryzen 7 7840HS, RTX 4070 Laptop 8 GB)

Sample: `C:\Users\User\Downloads\research-2026.mp4`, 455 s, one speaker, 26 chunks.
"First file" = first transcription in a fresh process, including CUDA warm-up.

| Pipeline | Startup to ready | First file | Second file | Text vs reference |
| --- | ---: | ---: | ---: | --- |
| Old, torch CUDA (source, warm disk) | 14.5 s | 37.7 s | 21.6 s | reference uses CPU fp32 |
| Old, torch CPU 8 threads | 10.8 s | 40.4 s | - | reference |
| Old, onefile EXE CUDA / CPU (BENCHMARK.md) | 129 s / 26 s before the window appears | | | |
| ORT CUDA EP fp32 | 3.1 s | 4.0 s | 3.8 s | identical (932/932 words) |
| ORT DirectML fp32 | 2.0 s | 6.9 s | 5.0 s | identical |
| ORT CPU fp32, 8 threads | 2.0 s | 25 s | 25 s | identical |
| ORT CPU int8 (MatMul only), 8 threads | 1.1 s | 14.4 s | 17.4 s | 9 small diffs in 932 words (punctuation, hyphens) |

Where the old pipeline loses time, for the same file on CUDA:

- `import torch` 4-9 s; torch CUDA libraries are 3.9 GB, which forces the 3.7 GB EXE.
- Onefile EXE unpacks everything to %TEMP% on every launch: the 129 s / 26 s above.
- MD5 of the 449 MB checkpoint on every load (~1 s), then a pickle `torch.load`
  with `weights_only=False` (runs arbitrary code from a downloaded file).
- The GUI loads the model again for every file.
- Audio is decoded by ffmpeg twice (`vad_utils.segment_audio_file`).
- Silero VAD in torch, one thread, about 14,000 sequential calls: 8-10 s.
  ORT with the audio cut into parallel rows: 1.3 s, same boundaries except one 0.1 s shift.
- RNNT greedy decoding: 13.5 s on GPU, slower than the encoder. It runs the
  prediction LSTM on every frame although its output only changes after an
  emitted token, recomputes the encoder projection per frame, and syncs the GPU
  with `.item()` per step. A numpy version with both fixes: 0.9 s.
- No batching; the first CUDA run spends ~11 s warming kernels for new shapes.

## Diarization findings (sherpa-onnx 2.0.1, CPU, 8 threads)

- Pipeline: pyannote segmentation-3.0 ONNX (6 MB) + speaker embedding ONNX + clustering.
- Speed about 10x realtime on CPU (23 min file in ~145 s). This is slower than ASR on GPU.
- Single-speaker lecture: 1 speaker found (correct).
- 23 min multi-speaker file `2023 06 10 10 34 50.mp3`, WeSpeaker ResNet34:
  threshold 0.5 gives 19 speakers, 0.8 gives 4. True count unknown.
- 3D-Speaker ERes2Net base: 88 speakers at 0.8, unusable as configured.
- Conclusion: works, but the clustering threshold needs tuning on a labelled
  recording, and a "number of speakers" option is needed for when the user knows it.

## Files and storage

- Prototype code: `experiments/onnx_runtime/` (see its README).
- Session 1 scratchpad (reference JSON `ref_torch_cpu.json`, `short.m4a`):
  `C:\Users\User\AppData\Local\Temp\claude\b3b5ded84d394c69\1b972041-92b6-47ff-9690-27ace02d4adf\scratchpad`.
  Session 2 copies are in its scratchpad `ref/`.
- Storage rule from the owner: up to ~3 GB of new files without asking. `dist/` is deleted;
  the FFmpeg source and the old licence zip are in `third_party/` (gitignored).
