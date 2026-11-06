# PyInstaller spec: one onedir folder with two launchers that share one _internal folder.
#
#   GigaAmTranscriber.exe  windowed app: the page in gigaam_app/web shown by pywebview (Edge WebView2)
#   gigaam-cli.exe         console app
#
# Build with tools/build_windows.py, which also copies the models, ffmpeg.exe and
# licences beside the EXEs. Models are not packed into the EXEs: they are plain
# files in models/, so the EXEs start without unpacking anything.

from pathlib import Path
import re

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

ROOT = Path(SPECPATH).resolve().parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "gigaam_app" / "__init__.py").read_text()).group(1)

# Nothing here is used at run time. torch and friends must never end up in the
# build even when PyInstaller runs in an environment that has them.
EXCLUDES = [
    "torch", "torchaudio", "torchvision", "gigaam", "silero_vad", "onnx", "hydra", "omegaconf",
    "sentencepiece", "scipy", "pandas", "matplotlib", "PIL", "IPython", "jupyter", "notebook",
    "pytest", "_pytest", "sympy", "mpmath", "coloredlogs", "humanfriendly", "flatbuffers",
    "google.protobuf", "psutil", "setuptools", "pkg_resources", "distutils", "lib2to3",
    "pydoc_data", "xmlrpc",
    "onnxruntime.quantization", "onnxruntime.transformers", "onnxruntime.tools",
    "onnxruntime.datasets", "onnxruntime.backend",
]


# pywebview backends other than WebView2 (WinForms) never run on Windows.
WEBVIEW_OTHER = ["webview.platforms.gtk", "webview.platforms.qt", "webview.platforms.cocoa",
                 "webview.platforms.android", "webview.platforms.cef", "gi", "qtpy", "PyQt5", "PyQt6",
                 "PySide2", "PySide6", "cefpython3",
                 # cffi's compiler side (pythonnet's clr_loader only calls cffi at run time);
                 # it imports distutils, which PyInstaller cannot alias once excluded.
                 "cffi.recompiler", "cffi.setuptools_ext", "cffi.vengine_cpy", "cffi.vengine_gen",
                 "cffi.verifier", "cffi._shimmed_dist_utils", "cffi.ffiplatform"]


def analysis(script, datas=()):
    return Analysis([str(ROOT / "launchers" / script)], pathex=[str(ROOT)], datas=list(datas),
                    excludes=EXCLUDES + ["tkinter", "_tkinter"] + WEBVIEW_OTHER, noarchive=False, optimize=1)


def version_info(name, description):
    """Windows file properties (Details tab) for one EXE."""
    numbers = tuple(int(part) for part in VERSION.split(".")) + (0,) * (4 - len(VERSION.split(".")))
    strings = [StringStruct("ProductName", "GigaAM Transcriber"), StringStruct("FileDescription", description),
               StringStruct("FileVersion", VERSION), StringStruct("ProductVersion", VERSION),
               StringStruct("OriginalFilename", name + ".exe"), StringStruct("InternalName", name),
               StringStruct("LegalCopyright", "MIT License")]
    return VSVersionInfo(ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
                         kids=[StringFileInfo([StringTable("040904B0", strings)]),
                               VarFileInfo([VarStruct("Translation", [0x0409, 1200])])])


# The page files and the window icon sit beside gigaam_app/window.py, where it looks for them.
ICON = str(ROOT / "gigaam_app" / "icons" / "gigaam.ico")
gui = analysis("gui_main.py", datas=[(str(ROOT / "gigaam_app" / "web"), "gigaam_app/web"),
                                     (ICON, "gigaam_app/icons")])
cli = analysis("cli_main.py")

gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="GigaAmTranscriber",
              console=False, upx=False, icon=ICON, version=version_info("GigaAmTranscriber", "GigaAM Transcriber"))
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name="gigaam-cli",
              console=True, upx=False, icon=ICON, version=version_info("gigaam-cli", "GigaAM Transcriber command line"))

COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas,
        name="GigaAmTranscriber", upx=False)
