"""Build the Windows release: one folder with both EXEs, the models, ffmpeg.exe and licences.

Run from the repository root with a Python environment that has only the app
dependencies (requirements.txt) and PyInstaller (requirements-build.txt):

    python tools/build_windows.py

Steps:
1. check the environment, the exported models (SHA-256 against model.json) and ffmpeg;
2. PyInstaller onedir build from packaging/GigaAmTranscriber.spec;
3. copy models/, ffmpeg.exe, the example settings, README.txt and licences beside the EXEs;
4. smoke test the console EXE on a silent file with ffmpeg removed from PATH, and
   start the windowed EXE off screen (tools/gui_smoke_test.py);
5. pack the release assets into build/release/:
       GigaAmTranscriber-v<version>-windows-x64.zip   the app folder
       THIRD_PARTY_LICENSES.zip                      the licences folder alone, under windows/
                                                     (build_linux.py adds linux/ to it)
       FFmpeg-<version>-source.zip                   source of the bundled FFmpeg (GPL)
       SHA256SUMS.txt
"""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gigaam_app import __version__  # noqa: E402

APP_NAME = "GigaAmTranscriber"
BUNDLED_MODELS = ("v3_e2e_rnnt", "v3_e2e_ctc")
VAD_MODEL = "silero_vad_scan.onnx"
# The FFmpeg source archive in third_party/ matches exactly this build.
FFMPEG_BUILD = "8.0.1-full_build-www.gyan.dev"
FFMPEG_SOURCE = ROOT / "third_party" / "ffmpeg" / "FFmpeg-8.0.1-source.zip"
REPO_LICENCES = ROOT / "packaging" / "licenses"


def fail(message):
    raise SystemExit(f"build_windows: {message}")


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


# ------------------------------------------------------------------ checks


def check_environment():
    """The build must not pick up torch, and ONNX Runtime must be the DirectML package."""
    if sys.platform != "win32":
        fail("Windows builds only")
    for heavy in ("torch", "torchaudio"):
        if importlib.util.find_spec(heavy) is not None:
            fail(f"{heavy} is installed in this environment; build from a clean venv (see README)")
    if importlib.util.find_spec("PyInstaller") is None:
        fail("PyInstaller is missing: pip install -r requirements-build.txt")
    try:
        importlib.metadata.version("onnxruntime-directml")
    except importlib.metadata.PackageNotFoundError:
        fail("onnxruntime-directml is not installed (the plain onnxruntime package has no GPU support)")
    import onnxruntime
    if "DmlExecutionProvider" not in onnxruntime.get_available_providers():
        fail("ONNX Runtime has no DirectML provider")


def check_models(models_root):
    """Every bundled model file must exist and match the checksum written by the export tool."""
    for name in BUNDLED_MODELS:
        folder = models_root / name
        meta_path = folder / "model.json"
        if not meta_path.is_file():
            fail(f"model {name} not found in {models_root}; run tools/export_models.py first")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for entry in meta["files"].values():
            path = folder / entry["name"]
            if not path.is_file() or sha256(path) != entry["sha256"]:
                fail(f"{path} is missing or does not match model.json")
    if not (models_root / VAD_MODEL).is_file():
        fail(f"{VAD_MODEL} not found; run tools/make_silero_scan.py first")


def find_ffmpeg(explicit):
    """Return (ffmpeg.exe, folder holding its LICENSE and README.txt)."""
    path = Path(explicit) if explicit else Path(shutil.which("ffmpeg") or "")
    if not path.is_file():
        fail("ffmpeg.exe not found; pass --ffmpeg or put it on PATH")
    first_line = subprocess.run([str(path), "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    if FFMPEG_BUILD not in first_line:
        fail(f"expected FFmpeg {FFMPEG_BUILD} to match {FFMPEG_SOURCE.name}, found: {first_line}")
    notices = path.parent.parent
    for name in ("LICENSE", "README.txt"):
        if not (notices / name).is_file():
            fail(f"FFmpeg {name} not found in {notices}")
    if not FFMPEG_SOURCE.is_file():
        fail(f"{FFMPEG_SOURCE} not found")
    return path, notices


# ------------------------------------------------------------------ build


def python_dll_dirs():
    """Folders where the build Python keeps its own DLLs (conda puts Tcl/Tk, OpenSSL... in Library/bin)."""
    base = Path(sys.base_prefix)
    return [folder for folder in (base / "Library" / "bin", base / "DLLs", base) if folder.is_dir()]


def run_pyinstaller(work, dist):
    command = [sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / f"{APP_NAME}.spec"),
               "--noconfirm", "--clean", f"--workpath={work}", f"--distpath={dist}"]
    # PyInstaller resolves DLLs through PATH. Another Python or conda on PATH would
    # lend its own tcl86t.dll or libcrypto, which then mismatch this Python's files.
    system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    path = [str(folder) for folder in python_dll_dirs()] + [str(system / "System32"), str(system)]
    env = {**os.environ, "PATH": os.pathsep.join(path)}
    subprocess.run(command, check=True, cwd=ROOT, env=env)
    return dist / APP_NAME


def check_dlls(app):
    """A bundled DLL that the build Python also has must be one of its copies (some exist twice)."""
    own = {}
    for folder in python_dll_dirs():
        for path in folder.glob("*.dll"):
            own.setdefault(path.name.lower(), []).append(path)
    for bundled in (app / "_internal").glob("*.dll"):
        sources = own.get(bundled.name.lower())
        if sources and sha256(bundled) not in {sha256(source) for source in sources}:
            fail(f"{bundled.name} in the build is not the build Python's copy; another Python's DLL was picked up")


def copy_payload(app, models_root, ffmpeg):
    models = app / "models"
    for name in BUNDLED_MODELS:
        shutil.copytree(models_root / name, models / name)
    shutil.copy2(models_root / VAD_MODEL, models / VAD_MODEL)
    shutil.copy2(ffmpeg, app / "ffmpeg.exe")
    shutil.copy2(ROOT / "gigaam-config.example.json", app / "gigaam-config.example.json")
    readme = (ROOT / "packaging" / "README.txt").read_text(encoding="utf-8").replace("{version}", __version__)
    # Windows Notepad shows UTF-8 with a byte order mark reliably on every version.
    (app / "README.txt").write_text(readme, encoding="utf-8-sig", newline="\r\n")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", app / "THIRD_PARTY_NOTICES.md")


def distribution_licences(name):
    """License files declared in an installed package's metadata."""
    dist = importlib.metadata.distribution(name)
    found = []
    for item in dist.files or []:
        parts = [part.lower() for part in item.parts]
        if any(part.endswith(".dist-info") for part in parts) and \
                re.search(r"(licen[cs]e|copying|notice)", item.name, re.I):
            found.append((Path(item.locate()), Path(*item.parts[1:])))
    return found


def find_python_licence():
    base = Path(sys.base_prefix)
    for candidate in (base / "LICENSE.txt", base / "LICENSE_PYTHON.txt"):
        if candidate.is_file():
            return candidate
    fail("Python LICENSE.txt not found in the base Python")


def collect_licences(app, ffmpeg_notices):
    """Licence texts of everything inside the folder, one subfolder per component."""
    target = app / "licenses"

    def put(source, relative):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    put(ROOT / "LICENSE", "gigaam-transcriber/LICENSE.txt")  # app code and GigaAM models: MIT
    put(REPO_LICENCES / "silero-vad-LICENSE.txt", "silero-vad/LICENSE.txt")
    put(REPO_LICENCES / "DirectML-LICENSE.txt", "directml/LICENSE.txt")
    import onnxruntime
    ort_dir = Path(onnxruntime.__file__).parent
    for name in ("LICENSE", "ThirdPartyNotices.txt", "Privacy.md"):
        put(ort_dir / name, f"onnxruntime/{name}")
    # numpy, PyInstaller's bootloader, and the window: pywebview with pythonnet (.NET bridge)
    # and their own dependencies.
    for package in ("numpy", "pyinstaller", "pywebview", "pythonnet", "clr_loader", "cffi", "pycparser",
                    "bottle", "typing_extensions"):
        found = distribution_licences(package)
        if not found:
            fail(f"no licence file found in the metadata of {package}")
        for source, relative in found:
            put(source, Path(package) / relative)
    put(REPO_LICENCES / "proxy_tools-LICENSE.txt", "proxy_tools/LICENSE.txt")
    # Microsoft.Web.WebView2.Core/WinForms.dll and WebView2Loader.dll come with pywebview.
    put(REPO_LICENCES / "WebView2-SDK-LICENSE.txt", "webview2-sdk/LICENSE.txt")
    put(REPO_LICENCES / "WebView2-SDK-NOTICE.txt", "webview2-sdk/NOTICE.txt")
    put(find_python_licence(), "python/LICENSE.txt")
    put(ffmpeg_notices / "LICENSE", "ffmpeg/LICENSE.txt")
    put(ffmpeg_notices / "README.txt", "ffmpeg/README.txt")
    conda_licences(app, target)


def conda_licences(app, target):
    """A conda-based Python ships DLLs from other conda packages (zlib, OpenSSL, libffi, ...).

    For each DLL that ended up in the build, find the conda package that owns
    it and copy that package's licence files from its info/licenses folder.
    """
    base = Path(sys.base_prefix)
    meta_dir = base / "conda-meta"
    if not meta_dir.is_dir():
        return
    bundled = {path.name.lower() for path in (app / "_internal").rglob("*") if path.suffix.lower() in (".dll", ".pyd")}
    pkgs_dirs = [base.parent.parent / "pkgs", Path(os.environ.get("CONDA_PKGS_DIRS", "")),
                 Path.home() / ".conda" / "pkgs", Path(os.environ.get("ProgramData", "C:/ProgramData")) / "miniconda3" / "pkgs"]
    for record_path in meta_dir.glob("*.json"):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        owned = {Path(item).name.lower() for item in record.get("files", [])}
        if not owned & bundled or record["name"] == "python":
            continue
        package = f"{record['name']}-{record['version']}-{record['build']}"
        for pkgs in pkgs_dirs:
            licences = pkgs / package / "info" / "licenses"
            if licences.is_dir():
                for source in licences.rglob("*"):
                    if source.is_file():
                        destination = target / "conda" / record["name"] / source.relative_to(licences)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, destination)
                break
        else:
            fail(f"licence files of conda package {package} not found (it provides {sorted(owned & bundled)})")


def check_no_torch(app):
    leftovers = [path for path in (app / "_internal").rglob("*")
                 if re.match(r"(torch|c10|cudnn|cublas|libtorch)", path.name, re.I)]
    if leftovers:
        fail(f"torch files ended up in the build: {leftovers[:5]}")


def smoke_test(app):
    """Run the console EXE on 2 s of silence, with no ffmpeg on PATH and no Python around."""
    with tempfile.TemporaryDirectory() as temporary:
        audio = Path(temporary) / "silence.wav"
        subprocess.run([str(app / "ffmpeg.exe"), "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                        "-t", "2", str(audio)], check=True)
        env = {key: value for key, value in os.environ.items()
               if key.upper() not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "CONDA_PREFIX")}
        env["PATH"] = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        cli = str(app / "gigaam-cli.exe")
        version = subprocess.run([cli, "--version"], capture_output=True, text=True, env=env, cwd=temporary)
        if version.returncode != 0 or __version__ not in version.stdout:
            fail(f"gigaam-cli --version failed: {version.stdout} {version.stderr}")
        for device in ("cpu", "auto"):
            started = time.perf_counter()
            run = subprocess.run([cli, str(audio), "--device", device], capture_output=True, text=True,
                                 encoding="utf-8", env=env, cwd=temporary)
            if run.returncode != 0 or "no speech found" not in run.stdout:
                fail(f"smoke test on {device} failed:\n{run.stdout}\n{run.stderr}")
            print(f"smoke test {device}: {run.stdout.splitlines()[0]} ({time.perf_counter() - started:.1f} s)",
                  flush=True)
    # The windowed EXE: start it off screen, let the model load, close it.
    import gui_smoke_test  # tools/gui_smoke_test.py, beside this script
    timings = gui_smoke_test.run(app, log=lambda message: None)
    print(f"smoke test GUI: window after {timings['window_seconds']:.1f} s, closed cleanly", flush=True)


# ------------------------------------------------------------------ release assets


def zip_folder(folder, zip_path, prefix):
    """Zip a folder under the top-level name `prefix`, files in sorted order."""
    temporary = zip_path.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, f"{prefix}/{path.relative_to(folder).as_posix()}")
    os.replace(temporary, zip_path)


def folder_size(folder):
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def make_assets(app, release):
    release.mkdir(parents=True, exist_ok=True)
    zip_name = f"{APP_NAME}-v{__version__}-windows-x64.zip"
    zip_folder(app, release / zip_name, APP_NAME)
    zip_folder(app / "licenses", release / "THIRD_PARTY_LICENSES.zip", "windows")
    shutil.copy2(FFMPEG_SOURCE, release / FFMPEG_SOURCE.name)
    assets = [zip_name, "THIRD_PARTY_LICENSES.zip", FFMPEG_SOURCE.name]
    (release / "SHA256SUMS.txt").write_text("".join(f"{sha256(release / name)}  {name}\n" for name in assets),
                                            encoding="utf-8", newline="\n")
    for name in assets + ["SHA256SUMS.txt"]:
        size = (release / name).stat().st_size
        if size >= 2 * 1024 ** 3:
            fail(f"{name} is {size / 1024 ** 3:.2f} GiB; GitHub release assets must stay below 2 GiB")
        print(f"  {name}: {size / 1024 ** 2:.1f} MiB", flush=True)


def remove_old_build(dist):
    """Delete the previous app folder, but only when nothing in it is in use.

    Windows refuses to rename a folder while a program runs from it or holds one of its
    files. Renaming first turns that into a clean stop; deleting straight away would
    remove the models and licences before reaching the first locked DLL (it happened
    once to a copy the owner had open, 2026-11-06)."""
    if not dist.exists():
        return
    doomed = dist.with_name(dist.name + ".old")
    if doomed.exists():
        shutil.rmtree(doomed)
    try:
        dist.rename(doomed)
    except PermissionError:
        fail(f"{dist} is in use (is the app running from it?); close it or pass another --out")
    shutil.rmtree(doomed)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", type=Path, default=ROOT / "models", help="exported models (default: models/)")
    parser.add_argument("--ffmpeg", help=f"ffmpeg.exe {FFMPEG_BUILD} (default: the one on PATH)")
    parser.add_argument("--out", type=Path, default=ROOT / "build", help="build folder (default: build/)")
    parser.add_argument("--no-zip", action="store_true", help="stop after the app folder and the smoke test")
    args = parser.parse_args()

    check_environment()
    check_models(args.models)
    ffmpeg, ffmpeg_notices = find_ffmpeg(args.ffmpeg)
    out = args.out.resolve()
    dist = out / "app"
    remove_old_build(dist)
    started = time.perf_counter()
    app = run_pyinstaller(out / "pyinstaller", dist)
    check_no_torch(app)
    check_dlls(app)
    code_size = folder_size(app)
    copy_payload(app, args.models, ffmpeg)
    collect_licences(app, ffmpeg_notices)
    print(f"App folder {app}: {folder_size(app) / 1024 ** 2:.0f} MiB "
          f"(program {code_size / 1024 ** 2:.0f} MiB), built in {time.perf_counter() - started:.0f} s", flush=True)
    smoke_test(app)
    if not args.no_zip:
        print("Release assets:", flush=True)
        make_assets(app, out / "release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
