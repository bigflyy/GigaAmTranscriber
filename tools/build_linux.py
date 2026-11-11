"""Build the Linux release: one folder with both programs, the models and licences, packed as .tar.gz.

Run on Linux (built and tested on Ubuntu 24.04 in WSL) from the repository root with a
venv made from the system Python, because the bundled PyGObject is the system's copy
and fits only that Python:

    python3 -m venv ~/.venvs/gigaam-build
    ~/.venvs/gigaam-build/bin/pip install -r requirements-build.txt
    ~/.venvs/gigaam-build/bin/python tools/build_linux.py --out ~/gigaam-build

The build machine needs python3-gi, gir1.2-webkit2-4.1, ffmpeg and xvfb (for the window
smoke test). The built app needs from the target system: glibc 2.39 or newer (Ubuntu 24.04,
Debian 13, Fedora 40 and later), GTK 3, WebKitGTK 4.1 with its GObject introspection
files, and FFmpeg. Recognition runs on the CPU.

Steps:
1. check the environment, the exported models (SHA-256 against model.json), the whisper.cpp
   libraries from tools/build_whisper_cpp.py (SHA-256 against build-info.json) and PyGObject;
2. PyInstaller onedir build from packaging/GigaAmTranscriber-linux.spec;
3. copy models/, the example settings, README.txt and licences beside the programs and the
   whisper.cpp libraries into _internal/whisper_cpp/, then check that every bundled library resolves;
4. smoke test the CLI on a silent file (and on --speech FILE if given), check that it loads
   whisper.cpp (gigaam-cli --devices), transcribe a short speech file with Whisper on the CPU
   (a downloaded model folder linked in, see build_windows.py --whisper-model), read it with
   faster-whisper (--fast-whisper-model), and open the window
   under Xvfb (with --speech it must also write the transcript);
5. pack <release>/GigaAmTranscriber-v<version>-linux-x64.tar.gz and add it to SHA256SUMS.txt;
   put the licences under linux/ in <release>/THIRD_PARTY_LICENSES.zip, beside the windows/
   folder that a Windows build into the same release folder wrote (build Windows first).
"""

import argparse
import importlib.util
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from gigaam_app import __version__  # noqa: E402
from build_windows import (APP_NAME, BUNDLED_MODELS, REPO_LICENCES, VAD_MODEL,  # noqa: E402
                           add_whisper_arguments, check_faster_whisper_files, check_faster_whisper_packages,
                           check_models, check_no_torch, check_whisper_cpp, distribution_licences,
                           fast_whisper_test_files, folder_size, put_faster_whisper_licences, sha256,
                           speaker_smoke_test, speaker_test_files, whisper_smoke_test, whisper_test_files)

WHISPER_CPP = ROOT / "third_party" / "whisper.cpp" / "linux-x64"  # tools/build_whisper_cpp.py
# CTranslate2's wheel brings GCC's OpenMP runtime (libgomp, GPL-3 with the GCC runtime library
# exception); the build machine's own libgomp1 package holds the same licence texts.
GOMP_COPYRIGHT = Path("/usr/share/doc/libgomp1/copyright")
GPL3 = Path("/usr/share/common-licenses/GPL-3")

SYSTEM_GI = Path("/usr/lib/python3/dist-packages/gi")
TITLE_START = "GigaAM - "


def fail(message):
    raise SystemExit(f"build_linux: {message}")


# ------------------------------------------------------------------ checks


def check_environment(gi_dir):
    if not sys.platform.startswith("linux"):
        fail("Linux builds only")
    if sys.prefix == sys.base_prefix:
        fail("run from a venv (see the docstring)")
    for heavy in ("torch", "torchaudio"):
        if importlib.util.find_spec(heavy) is not None:
            fail(f"{heavy} is installed in this environment; build from a clean venv")
    if importlib.util.find_spec("PyInstaller") is None:
        fail("PyInstaller is missing: pip install -r requirements-build.txt")
    if importlib.util.find_spec("gi") is not None:
        fail("this venv can import gi; the spec copies PyGObject itself, so make the venv "
             "without --system-site-packages")
    # PyGObject's compiled part must fit this Python exactly.
    suffix = sysconfig.get_config_var("EXT_SUFFIX")
    if not (gi_dir / f"_gi{suffix}").is_file():
        fail(f"{gi_dir} has no _gi{suffix}: PyGObject was built for another Python than {sys.version.split()[0]}")
    for tool in ("ffmpeg", "ldd", "dpkg"):
        if not shutil.which(tool):
            fail(f"{tool} not found")
    check_faster_whisper_packages()
    for licence in (GOMP_COPYRIGHT, GPL3):
        if not licence.is_file():
            fail(f"{licence} not found (the licence of the libgomp that comes with CTranslate2)")


# ------------------------------------------------------------------ build


def run_pyinstaller(work, dist, gi_dir):
    command = [sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / f"{APP_NAME}-linux.spec"),
               "--noconfirm", "--clean", f"--workpath={work}", f"--distpath={dist}"]
    subprocess.run(command, check=True, cwd=ROOT, env={**os.environ, "GIGAAM_GI_DIR": str(gi_dir)})
    return dist / APP_NAME


def elf_files(folder):
    for path in sorted(folder.rglob("*")):
        if path.is_file() and not path.is_symlink():
            with open(path, "rb") as stream:
                if stream.read(4) == b"\x7fELF":
                    yield path


def check_libraries(app):
    """Every bundled program and library must find all its libraries (bundled or system)."""
    internal = app / "_internal"
    env = {**os.environ, "LD_LIBRARY_PATH": str(internal)}
    for path in elf_files(app):
        listing = subprocess.run(["ldd", str(path)], capture_output=True, text=True, env=env).stdout
        missing = re.findall(r"^\s*(\S+) => not found", listing, re.M)
        if missing:
            fail(f"{path.relative_to(app)} cannot find {missing}")


def copy_payload(app, models_root):
    models = app / "models"
    for name in BUNDLED_MODELS:
        shutil.copytree(models_root / name, models / name)
    shutil.copy2(models_root / VAD_MODEL, models / VAD_MODEL)
    shutil.copy2(ROOT / "gigaam-config.example.json", app / "gigaam-config.example.json")
    readme = (ROOT / "packaging" / "README-linux.txt").read_text(encoding="utf-8").replace("{version}", __version__)
    (app / "README.txt").write_text(readme, encoding="utf-8", newline="\n")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", app / "THIRD_PARTY_NOTICES.md")
    # whisper_cpp.library_dir() looks here; the libraries find each other through RPATH $ORIGIN.
    libraries = app / "_internal" / "whisper_cpp"
    libraries.mkdir()
    for path in sorted(WHISPER_CPP.glob("lib*.so*")):
        shutil.copy2(path, libraries / path.name)


def owning_packages(app):
    """Debian packages that provided the system libraries PyInstaller bundled (libpython, libssl...)."""
    packages = set()
    for path in (app / "_internal").glob("*.so*"):
        answer = subprocess.run(["dpkg", "-S", f"*/{path.name}"], capture_output=True, text=True).stdout
        for line in answer.splitlines():
            if line.startswith("diversion "):
                continue
            package, _, owned = line.partition(": ")
            if owned.endswith("/" + path.name) and owned.startswith(("/usr/lib", "/lib")):
                packages.add(package.split(":")[0])
    return sorted(packages)


def collect_licences(app, gi_dir):
    """Licence texts of everything inside the folder, one subfolder per component."""
    target = app / "licenses"

    def put(source, relative):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    put(ROOT / "LICENSE", "gigaam-transcriber/LICENSE.txt")  # app code and GigaAM models: MIT
    put(REPO_LICENCES / "silero-vad-LICENSE.txt", "silero-vad/LICENSE.txt")
    import onnxruntime
    ort_dir = Path(onnxruntime.__file__).parent
    for name in ("LICENSE", "ThirdPartyNotices.txt", "Privacy.md"):
        put(ort_dir / name, f"onnxruntime/{name}")
    for package in ("numpy", "pyinstaller", "pywebview", "bottle", "typing_extensions"):
        found = distribution_licences(package)
        if not found:
            fail(f"no licence file found in the metadata of {package}")
        for source, relative in found:
            put(source, Path(package) / relative)
    put(REPO_LICENCES / "proxy_tools-LICENSE.txt", "proxy_tools/LICENSE.txt")
    put(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", "python/LICENSE.txt")
    put(WHISPER_CPP / "LICENSE.txt", "whisper.cpp/LICENSE.txt")  # whisper.cpp and ggml: MIT
    put(REPO_LICENCES / "whisper-LICENSE.txt", "whisper-model/LICENSE.txt")  # Whisper weights (downloaded): MIT
    put(REPO_LICENCES / "speaker-models-LICENSE.txt", "speaker-models/LICENSE.txt")  # downloaded: MIT, CC BY 4.0
    put_faster_whisper_licences(put)
    put(GOMP_COPYRIGHT, "libgomp/copyright")  # GCC's copyright file, with the runtime library exception
    put(GPL3, "libgomp/GPL-3")
    # PyGObject (LGPL-2.1-or-later), copied from the system package with its copyright file.
    gi_copyright = Path("/usr/share/doc/python3-gi/copyright")
    if gi_dir.resolve() == SYSTEM_GI and not gi_copyright.is_file():
        fail(f"{gi_copyright} not found")
    if gi_copyright.is_file():
        put(gi_copyright, "pygobject/copyright")
    # System libraries that came along with the Python (libpython, libmpdec, libssl, ...).
    packages = owning_packages(app)
    if not packages:
        fail("no Debian package found for the bundled system libraries (libpython...)")
    for package in packages:
        copyright_file = Path("/usr/share/doc") / package / "copyright"
        if not copyright_file.is_file():
            fail(f"copyright file of {package} not found")
        put(copyright_file, f"debian/{package}/copyright")


# ------------------------------------------------------------------ smoke tests


def clean_env():
    """The environment a user's shell would give: no venv, no Python variables, system PATH."""
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "LD_LIBRARY_PATH")}
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    return env


def smoke_cli(app, speech, whisper=None, speakers=None, fast_whisper=None):
    """The CLI on silence, on SPEECH if given, with Whisper (model folder, audio) if given,
    finding speakers (model folder, audio) if given, and with faster-whisper (model folder,
    audio) if given."""
    with tempfile.TemporaryDirectory() as temporary:
        audio = Path(temporary) / "silence.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2",
                        str(audio)], check=True)
        cli = str(app / "gigaam-cli")
        version = subprocess.run([cli, "--version"], capture_output=True, text=True, env=clean_env(), cwd=temporary)
        if version.returncode != 0 or __version__ not in version.stdout:
            fail(f"gigaam-cli --version failed: {version.stdout} {version.stderr}")
        devices = subprocess.run([cli, "--devices"], capture_output=True, text=True, env=clean_env(), cwd=temporary)
        if devices.returncode != 0 or "backends" not in devices.stdout or "CPU" not in devices.stdout:
            fail(f"gigaam-cli --devices failed (whisper.cpp not loaded):\n{devices.stdout}\n{devices.stderr}")
        print("smoke test devices:\n  " + devices.stdout.strip().replace("\n", "\n  "), flush=True)
        started = time.perf_counter()
        run = subprocess.run([cli, str(audio), "--device", "cpu"], capture_output=True, text=True,
                             env=clean_env(), cwd=temporary)
        if run.returncode != 0 or "no speech found" not in run.stdout:
            fail(f"CLI smoke test failed:\n{run.stdout}\n{run.stderr}")
        print(f"smoke test CLI: {run.stdout.splitlines()[0]} ({time.perf_counter() - started:.1f} s)", flush=True)
        if speech:
            copy = Path(temporary) / speech.name
            shutil.copy2(speech, copy)
            started = time.perf_counter()
            run = subprocess.run([cli, str(copy), "--device", "cpu"], capture_output=True, text=True,
                                 env=clean_env(), cwd=temporary)
            text = copy.with_name(copy.stem + "-transcript.txt")
            if run.returncode != 0 or not text.is_file():
                fail(f"CLI on {speech.name} failed:\n{run.stdout}\n{run.stderr}")
            words = len(text.read_text(encoding="utf-8").split())
            print(f"smoke test CLI on {speech.name}: {words} words in {time.perf_counter() - started:.1f} s",
                  flush=True)
    if whisper:
        whisper_smoke_test(str(app / "gigaam-cli"), *whisper, clean_env(), "cpu")  # no Vulkan GPU in WSL
    if fast_whisper:
        whisper_smoke_test(str(app / "gigaam-cli"), *fast_whisper, clean_env(), "cpu", fast=True)
    if speakers:
        speaker_smoke_test(str(app / "gigaam-cli"), *speakers, clean_env(), "cpu")


def window_titles(env):
    listing = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True, text=True, env=env).stdout
    return re.findall(r'"([^"]*)"', listing)


def screenshot(path, env):
    """Grab the Xvfb screen with the system Python's GTK (no screenshot tool needed)."""
    grab = ("import sys, gi; gi.require_version('Gdk', '3.0'); from gi.repository import Gdk; "
            "r = Gdk.get_default_root_window(); "
            "Gdk.pixbuf_get_from_window(r, 0, 0, r.get_width(), r.get_height()).savev(sys.argv[1], 'png', [], [])")
    subprocess.run(["/usr/bin/python3", "-c", grab, str(path)], env=env, timeout=30)


def smoke_window(app, speech, shots):
    """Open the window on a private Xvfb screen (never on the user's display). With a speech
    file it must transcribe it: files given on the command line start at once."""
    if not shutil.which("Xvfb") or not shutil.which("xwininfo"):
        fail("Xvfb and xwininfo are needed for the window smoke test (apt install xvfb x11-utils)")
    display = ":97"
    xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = clean_env()
    env.pop("WAYLAND_DISPLAY", None)  # under WSLg it would show the window on the real screen
    env.update(DISPLAY=display, GDK_BACKEND="x11", GIGAAM_THEME="dark")
    window = None
    try:
        time.sleep(1.0)
        with tempfile.TemporaryDirectory() as temporary:
            arguments = []
            text = None
            if speech:
                copy = Path(temporary) / speech.name
                shutil.copy2(speech, copy)
                arguments = [str(copy)]
                text = copy.with_name(copy.stem + "-transcript.txt")
            env["GIGAAM_HISTORY"] = str(Path(temporary) / "history")  # not the user's own list
            log = open(Path(temporary) / "window.log", "w")
            started = time.perf_counter()
            window = subprocess.Popen([str(app / APP_NAME), *arguments], env=env, cwd=temporary,
                                      stdout=log, stderr=subprocess.STDOUT)
            shown = None
            while time.perf_counter() - started < 60 and window.poll() is None:
                if any(title.startswith(TITLE_START) for title in window_titles(env)):
                    shown = time.perf_counter() - started
                    break
                time.sleep(0.1)
            if shown is None:
                log.close()
                fail(f"the window did not appear:\n{(Path(temporary) / 'window.log').read_text()}")
            print(f"smoke test window: shown after {shown:.1f} s", flush=True)
            if text:
                while time.perf_counter() - started < 300 and window.poll() is None and not text.is_file():
                    time.sleep(0.2)
                if not text.is_file():
                    log.close()
                    fail(f"the window did not write {text.name}:\n{(Path(temporary) / 'window.log').read_text()}")
                print(f"smoke test window: {speech.name} written after {time.perf_counter() - started:.1f} s "
                      f"({len(text.read_text(encoding='utf-8').split())} words)", flush=True)
                time.sleep(1.0)
            if shots:
                shots.mkdir(parents=True, exist_ok=True)
                screenshot(shots / "linux-window.png", env)
            window.send_signal(signal.SIGTERM)
            window.wait(timeout=20)
            log.close()
            window = None
    finally:
        if window is not None and window.poll() is None:
            window.kill()
        xvfb.terminate()
        xvfb.wait(timeout=10)


def smoke_missing_webkit(app):
    """Without WebKitGTK the window program must say what to install and exit."""
    env = {**clean_env(), "GIGAAM_PRETEND_NO_WEBVIEW": "1"}
    env.pop("DISPLAY", None)  # no dialog program can open: the text goes to stderr only
    env.pop("WAYLAND_DISPLAY", None)
    run = subprocess.run([str(app / APP_NAME)], capture_output=True, text=True, env=env, timeout=60)
    if run.returncode != 1 or "gir1.2-webkit2-4.1" not in run.stderr or "python3-gi" in run.stderr:
        fail(f"missing WebKitGTK message is wrong (exit {run.returncode}):\n{run.stderr}")
    print("smoke test: missing WebKitGTK names gir1.2-webkit2-4.1", flush=True)


# ------------------------------------------------------------------ release asset


def update_sums(release, name):
    """Put one asset's line into SHA256SUMS.txt, keeping the other assets' lines."""
    sums = release / "SHA256SUMS.txt"
    lines = [line for line in (sums.read_text(encoding="utf-8").splitlines() if sums.is_file() else [])
             if not line.endswith("  " + name)]
    lines.append(f"{sha256(release / name)}  {name}")
    sums.write_text("".join(line + "\n" for line in lines), encoding="utf-8", newline="\n")


def merge_licences(app, release):
    """THIRD_PARTY_LICENSES.zip holds one folder per app: windows/ (from build_windows.py)
    and linux/ (this build's licences). The linux/ folder is replaced, the rest is kept."""
    name = "THIRD_PARTY_LICENSES.zip"
    target = release / name
    temporary = release / (name + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as merged:
        if target.is_file():
            with zipfile.ZipFile(target) as old:
                for info in old.infolist():
                    if not info.filename.startswith("linux/"):
                        merged.writestr(info, old.read(info))
        folder = app / "licenses"
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                merged.write(path, f"linux/{path.relative_to(folder).as_posix()}")
    os.replace(temporary, target)
    update_sums(release, name)
    print(f"  {name}: {target.stat().st_size / 1024:.0f} KiB", flush=True)


def make_tarball(app, release):
    release.mkdir(parents=True, exist_ok=True)
    name = f"{APP_NAME}-v{__version__}-linux-x64.tar.gz"
    temporary = release / (name + ".tmp")
    programs = {f"{APP_NAME}/{APP_NAME}", f"{APP_NAME}/gigaam-cli"}

    def normalise(info):
        # Files copied from a Windows drive in WSL come with every permission bit set;
        # only the two programs need to be executable. No owner names from the build machine.
        if info.isdir():
            info.mode = 0o755
        elif info.isfile():
            info.mode = 0o755 if info.name in programs else 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        return info

    with tarfile.open(temporary, "w:gz", compresslevel=6) as archive:
        archive.add(app, arcname=APP_NAME, filter=normalise)
    os.replace(temporary, release / name)
    update_sums(release, name)
    size = (release / name).stat().st_size
    if size >= 2 * 1024 ** 3:
        fail(f"{name} is {size / 1024 ** 3:.2f} GiB; GitHub release assets must stay below 2 GiB")
    print(f"  {name}: {size / 1024 ** 2:.1f} MiB", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", type=Path, default=ROOT / "models", help="exported models (default: models/)")
    parser.add_argument("--gi", type=Path, default=SYSTEM_GI, help=f"PyGObject package folder (default: {SYSTEM_GI})")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "linux", help="build folder")
    parser.add_argument("--release", type=Path, help="where the .tar.gz goes (default: <out>/release)")
    parser.add_argument("--speech", type=Path, help="a short speech file for the CLI and window smoke tests")
    parser.add_argument("--shots", type=Path, help="save a screenshot of the window here")
    parser.add_argument("--no-tar", action="store_true", help="stop after the app folder and the smoke tests")
    add_whisper_arguments(parser)
    args = parser.parse_args()

    check_environment(args.gi)
    check_models(args.models)
    check_whisper_cpp(WHISPER_CPP)
    whisper = whisper_test_files(args.whisper_model, args.whisper_audio, args.no_whisper_test)
    speakers = speaker_test_files(args.speaker_model, args.whisper_audio, args.no_speaker_test)
    fast_whisper = fast_whisper_test_files(args.fast_whisper_model, args.whisper_audio, args.no_fast_whisper_test)
    out = args.out.expanduser().resolve()
    dist = out / "app"
    if dist.exists():
        shutil.rmtree(dist)
    started = time.perf_counter()
    app = run_pyinstaller(out / "pyinstaller", dist, args.gi)
    check_no_torch(app)
    check_faster_whisper_files(app, [r"libctranslate2.*\.so[.\d]*", r"libgomp.*\.so[.\d]*", r"_ext\..*\.so",
                                     r"tokenizers.*\.so"])
    code_size = folder_size(app)
    copy_payload(app, args.models)
    check_libraries(app)  # after the copy, so the whisper.cpp libraries are checked too
    collect_licences(app, args.gi)
    print(f"App folder {app}: {folder_size(app) / 1024 ** 2:.0f} MiB "
          f"(program {code_size / 1024 ** 2:.0f} MiB), built in {time.perf_counter() - started:.0f} s", flush=True)
    speech = args.speech.resolve() if args.speech else None
    smoke_cli(app, speech, whisper, speakers, fast_whisper)
    smoke_missing_webkit(app)
    smoke_window(app, speech, args.shots)
    if not args.no_tar:
        print("Release asset:", flush=True)
        release = (args.release or out / "release").expanduser().resolve()
        make_tarball(app, release)
        merge_licences(app, release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
