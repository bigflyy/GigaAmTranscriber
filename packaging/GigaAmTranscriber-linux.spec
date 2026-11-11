# PyInstaller spec for Linux: one onedir folder with two programs sharing one _internal folder.
#
#   GigaAmTranscriber   the window: the page in gigaam_app/web shown by pywebview (system WebKitGTK)
#   gigaam-cli          command line
#
# Build with tools/build_linux.py on Linux with the system Python (see its docstring).
#
# What comes from the system and what is bundled:
# - GTK 3, WebKitGTK 4.1 and GObject introspection (libgirepository and the .typelib files)
#   come from the system: WebKitGTK starts helper programs from its own install folder and
#   cannot be moved into the app. The app names the missing package if they are absent.
# - PyGObject (the Python package "gi") is bundled: it is tied to the bundled Python, so the
#   system's copy cannot be used. It is copied as plain files, not analysed, because
#   PyInstaller's gi hooks would bundle GTK and WebKitGTK and point GI_TYPELIB_PATH inside
#   the app. The build passes its folder in GIGAAM_GI_DIR.
# - Libraries that the system's GTK and WebKitGTK load too (libz, libffi, libstdc++, ...) are
#   not bundled: two copies of one library in one process can clash, and the system's copy is
#   always present where WebKitGTK is.
# - FFmpeg comes from the system (found on PATH).

import ast
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(SPECPATH).resolve().parent
GI_DIR = Path(os.environ.get("GIGAAM_GI_DIR", "/usr/lib/python3/dist-packages/gi"))

# Nothing here is used at run time (same list as the Windows spec).
EXCLUDES = [
    "torch", "torchaudio", "torchvision", "gigaam", "silero_vad", "onnx", "hydra", "omegaconf",
    "sentencepiece", "scipy", "pandas", "matplotlib", "PIL", "IPython", "jupyter", "notebook",
    "pytest", "_pytest", "sympy", "mpmath", "coloredlogs", "humanfriendly", "flatbuffers",
    "google.protobuf", "psutil", "setuptools", "pkg_resources", "distutils", "lib2to3",
    "pydoc_data", "xmlrpc", "tkinter", "_tkinter",
    # faster-whisper (plan 08): CTranslate2's model converters and huggingface_hub (see the Windows spec).
    "ctranslate2.converters", "huggingface_hub",
    # Python's readline module links GNU readline (GPL-3); only an interactive prompt uses it.
    "readline",
    "onnxruntime.quantization", "onnxruntime.transformers", "onnxruntime.tools",
    "onnxruntime.datasets", "onnxruntime.backend",
    # pywebview backends other than GTK; gi and cairo are handled by hand (see above).
    "webview.platforms.winforms", "webview.platforms.edgechromium", "webview.platforms.mshtml",
    "webview.platforms.qt", "webview.platforms.cocoa", "webview.platforms.android",
    "webview.platforms.cef", "clr", "clr_loader", "pythonnet", "qtpy", "PyQt5", "PyQt6", "PySide2",
    "PySide6", "cefpython3", "gi", "cairo",
]

# Libraries the system's GTK and WebKitGTK stack loads; never bundle these.
SYSTEM_STACK = ["libwebkit2gtk-4.1.so.0", "libjavascriptcoregtk-4.1.so.0", "libgtk-3.so.0",
                "libgirepository-1.0.so.1"]
ALWAYS_SYSTEM = {"libstdc++.so.6", "libgcc_s.so.1"}


def find_library(name):
    for folder in ("/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib"):
        if Path(folder, name).exists():
            return Path(folder, name)
    sys.exit(f"{name} not found: install WebKitGTK 4.1 to build (sudo apt install gir1.2-webkit2-4.1)")


def system_stack_names():
    """File names of every library the GTK and WebKitGTK libraries pull in."""
    names = set(ALWAYS_SYSTEM)
    for library in SYSTEM_STACK:
        path = find_library(library)
        names.add(path.name)
        listing = subprocess.run(["ldd", str(path)], capture_output=True, text=True, check=True).stdout
        names.update(re.findall(r"^\s*(\S+\.so[.\d]*)\s", listing, re.M))
    return names


def gi_files():
    """(source, destination folder) for PyGObject's files, without caches and the cairo part
    (it needs pycairo, which the window does not use)."""
    if not (GI_DIR / "__init__.py").is_file():
        sys.exit(f"PyGObject not found in {GI_DIR}; set GIGAAM_GI_DIR")
    files = []
    for path in sorted(GI_DIR.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts or path.name.startswith("_gi_cairo"):
            continue
        files.append((str(path), str(Path("gi") / path.parent.relative_to(GI_DIR))))
    return files


def gi_stdlib_imports():
    """Standard library modules PyGObject imports: it is not analysed, so name them here."""
    found = set()
    for path in GI_DIR.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module)
    return sorted(name for name in found if name.split(".")[0] in sys.stdlib_module_names)


def analysis(script, datas=(), hiddenimports=()):
    return Analysis([str(ROOT / "launchers" / script)], pathex=[str(ROOT)], datas=list(datas),
                    hiddenimports=list(hiddenimports), excludes=EXCLUDES, noarchive=False, optimize=1)


def without_system_stack(binaries, names):
    """Drop top-level libraries that come from the system; package libraries
    (numpy.libs/, onnxruntime/capi/) stay."""
    return [entry for entry in binaries if "/" in entry[0] or Path(entry[0]).name not in names]


SYSTEM_NAMES = system_stack_names()
# pywebview picks its backend at run time, so the GTK one is named here.
gui = analysis("gui_main.py",
               datas=[(str(ROOT / "gigaam_app" / "web"), "gigaam_app/web"),
                      (str(ROOT / "gigaam_app" / "icons" / "gigaam.png"), "gigaam_app/icons")] + gi_files(),
               hiddenimports=["webview.platforms.gtk"] + gi_stdlib_imports())
cli = analysis("cli_main.py")
gui.binaries = without_system_stack(gui.binaries, SYSTEM_NAMES)
cli.binaries = without_system_stack(cli.binaries, SYSTEM_NAMES)

gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="GigaAmTranscriber",
              console=True, strip=False, upx=False)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="gigaam-cli",
              console=True, strip=False, upx=False)

COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas,
        name="GigaAmTranscriber", strip=False, upx=False)
