"""Build whisper.cpp for shipping with the app: shared libraries with the Vulkan backend.

Run from the repository root (any Python 3.10+; the check step imports gigaam_app):

    python tools/build_whisper_cpp.py                 Windows: MSVC 2022, Ninja, Vulkan SDK
    python3 tools/build_whisper_cpp.py                Linux: gcc, Ninja, Vulkan headers and glslc

Output, used by gigaam_app/whisper_cpp.py from a source checkout and copied into the
app by the build scripts:

    third_party/whisper.cpp/windows-x64/   whisper.dll, ggml.dll, ggml-base.dll,
                                           ggml-vulkan.dll, ggml-cpu-<variant>.dll ...
    third_party/whisper.cpp/linux-x64/     libwhisper.so.1, libggml.so.0, ... (same set)
    each with LICENSE.txt and build-info.json (version, options, SHA-256 of every file)

Build options, chosen for an app that runs on other people's computers:
- GGML_NATIVE=OFF: nothing is tuned for the build machine's CPU;
- GGML_BACKEND_DL=ON with GGML_CPU_ALL_VARIANTS=ON: one CPU backend per CPU generation
  (SSE4.2 up to AVX-512), and ggml loads the best one the user's CPU supports;
- GGML_VULKAN=ON: one GPU backend for NVIDIA, AMD and Intel GPUs. The Vulkan loader
  (vulkan-1.dll, libvulkan.so.1) comes with the GPU driver and is not shipped; without it
  the Vulkan backend does not load and whisper.cpp runs on the CPU;
- GGML_OPENMP=OFF: ggml's own thread pool, so no OpenMP runtime (vcomp140.dll, libgomp)
  has to be shipped;
- no examples, tests or server.

What the build machine needs:
- Windows: Visual Studio 2022 with the C++ workload (found with vswhere), CMake and Ninja
  on PATH, and a Vulkan SDK: the LunarG SDK, or a conda env with
  `conda create -p <env> -c conda-forge shaderc libvulkan-loader libvulkan-headers spirv-headers`
  passed as --vulkan-sdk <env>/Library (glslc.exe, include/vulkan, lib/vulkan-1.lib).
- Linux: cmake, ninja-build, g++, libvulkan-dev, spirv-headers and glslc (Ubuntu: sudo apt
  install cmake ninja-build g++ libvulkan-dev spirv-headers glslc), or --vulkan-sdk <folder>
  with include/, lib/, bin/glslc. Without root, `apt download glslc libshaderc1 spirv-headers`
  and `dpkg-deb -x` into a folder work too: put its usr on CMAKE_PREFIX_PATH, its usr/bin on
  PATH, its usr/lib/x86_64-linux-gnu on LD_LIBRARY_PATH for the whole build (CMake then
  calls that glslc directly, and it needs libshaderc.so.1 from there) and its usr/include on
  CPLUS_INCLUDE_PATH (ggml-vulkan finds the SPIR-V headers package but does not add its
  include folder to the compile command).

The Vulkan shaders make this a heavy build (several minutes, all cores): run it through
the work queue on a shared machine.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.9.5"
SOURCE_URL = f"https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v{VERSION}.tar.gz"
SOURCE_SHA256 = "ff1a9053feb509ff9d7729703355541ae9690073a6b1c40eb692c962e0dc1720"
SOURCE_ARCHIVE = ROOT / "third_party" / "whisper.cpp" / f"whisper.cpp-{VERSION}.tar.gz"
PLATFORM = "windows-x64" if sys.platform == "win32" else "linux-x64"
OUT_DEFAULT = ROOT / "third_party" / "whisper.cpp" / PLATFORM
WORK_DEFAULT = ROOT / "build" / "whisper-cpp" / PLATFORM

CMAKE_OPTIONS = {
    "CMAKE_BUILD_TYPE": "Release",
    "BUILD_SHARED_LIBS": "ON",
    "GGML_NATIVE": "OFF",
    "GGML_BACKEND_DL": "ON",
    "GGML_CPU_ALL_VARIANTS": "ON",
    "GGML_VULKAN": "ON",
    "GGML_OPENMP": "OFF",
    "GGML_CCACHE": "OFF",
    "WHISPER_BUILD_EXAMPLES": "OFF",
    "WHISPER_BUILD_TESTS": "OFF",
    "WHISPER_BUILD_SERVER": "OFF",
    "WHISPER_BUILD_IS_DEV": "OFF",  # a release tag: version "1.9.5", not "1.9.5-dev"
}
LINUX_OPTIONS = {
    # Every library finds the others in its own folder.
    "CMAKE_BUILD_WITH_INSTALL_RPATH": "ON",
    "CMAKE_INSTALL_RPATH": "$ORIGIN",
}


def fail(message):
    raise SystemExit(f"build_whisper_cpp: {message}")


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch_source(archive):
    """The pinned source archive, downloaded once and checked by SHA-256."""
    if not archive.is_file():
        archive.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {SOURCE_URL}")
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(SOURCE_URL) as response, open(partial, "wb") as stream:
            shutil.copyfileobj(response, stream)
        partial.replace(archive)
    digest = sha256(archive)
    if digest != SOURCE_SHA256:
        fail(f"{archive} has SHA-256 {digest}, expected {SOURCE_SHA256}")
    return archive


def unpack(archive, work):
    """Fresh source tree in <work>/src (the build folder inside it is short: 'b',
    because MSVC tools still trip over paths longer than 260 characters)."""
    source = work / "src"
    if source.exists():
        shutil.rmtree(source)
    work.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    (work / f"whisper.cpp-{VERSION}").rename(source)
    return source


def msvc_environment():
    """Environment of the x64 developer prompt of the newest Visual Studio with C++ tools."""
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / \
        "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        fail("vswhere.exe not found: install Visual Studio 2022 with the C++ workload")
    install = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                              "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                              "-property", "installationPath"],
                             capture_output=True, text=True, check=True).stdout.strip()
    vcvars = Path(install) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.is_file():
        fail(f"{vcvars} not found")
    # shell=True runs: cmd.exe /c ""...\vcvars64.bat" >nul && set"
    output = subprocess.run(f'"{vcvars}" >nul && set', capture_output=True, text=True,
                            check=True, shell=True).stdout
    environment = {}
    for line in output.splitlines():
        name, sep, value = line.partition("=")
        if sep:
            environment[name] = value
    return environment


def build_environment(vulkan_sdk):
    environment = msvc_environment() if sys.platform == "win32" else dict(os.environ)
    if vulkan_sdk:
        sdk = Path(vulkan_sdk).resolve()
        environment["VULKAN_SDK"] = str(sdk)
        environment["PATH"] = str(sdk / "bin") + os.pathsep + environment.get("PATH", "")
    for tool in ("cmake", "ninja"):
        if shutil.which(tool, path=environment.get("PATH")) is None:
            fail(f"{tool} not found on PATH")
    if shutil.which("glslc", path=environment.get("PATH")) is None:
        fail("glslc not found: pass --vulkan-sdk or install the Vulkan SDK (see the docstring)")
    return environment


def configure_and_build(source, environment, jobs):
    build = source / "b"
    options = dict(CMAKE_OPTIONS)
    if sys.platform != "win32":
        options.update(LINUX_OPTIONS)
    else:
        options["CMAKE_C_COMPILER"] = "cl"
        options["CMAKE_CXX_COMPILER"] = "cl"
    command = ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja"]
    command += [f"-D{name}={value}" for name, value in options.items()]
    subprocess.run(command, env=environment, check=True)
    command = ["cmake", "--build", str(build), "--config", "Release"]
    if jobs:
        command += ["--parallel", str(jobs)]
    subprocess.run(command, env=environment, check=True)
    return build, options


def soname(path):
    """SONAME of a Linux shared library (None for a backend module without one)."""
    output = subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True, check=True).stdout
    for line in output.splitlines():
        if "(SONAME)" in line:
            return line.split("[", 1)[1].split("]", 1)[0]
    return None


def shipped_libraries(build):
    """{file name in the app: built file} for whisper, ggml and every backend."""
    found = {}
    if sys.platform == "win32":
        for path in sorted((build / "bin").glob("*.dll")):
            if path.name.startswith(("ggml", "whisper")):
                found[path.name] = path
    else:
        for path in sorted(build.rglob("*.so*")):
            if path.is_symlink() or not path.is_file():
                continue
            if not path.name.startswith(("libggml", "libwhisper")):
                continue
            # Saved under the name other libraries ask for (libwhisper.so.1, not .so.1.9.5).
            found[soname(path) or path.name] = path
    for required in (["whisper.dll", "ggml.dll", "ggml-base.dll", "ggml-vulkan.dll"] if sys.platform == "win32"
                     else ["libggml-vulkan.so"]):
        if required not in found:
            fail(f"{required} was not built")
    if not any(name.startswith(("ggml-cpu-", "libggml-cpu-")) for name in found):
        fail("no CPU backend variants were built")
    return found


def collect(build, source, out, options):
    """Copy the libraries, the licence and a build record into a fresh output folder."""
    libraries = shipped_libraries(build)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name, path in libraries.items():
        shutil.copy2(path, out / name)
    shutil.copy2(source / "LICENSE", out / "LICENSE.txt")
    info = {
        "version": VERSION,
        "source": SOURCE_URL,
        "source_sha256": SOURCE_SHA256,
        "platform": PLATFORM,
        "cmake_options": options,
        "files": {path.name: {"size": path.stat().st_size, "sha256": sha256(path)}
                  for path in sorted(out.iterdir())},
    }
    (out / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    total = sum(entry["size"] for entry in info["files"].values())
    print(f"{len(libraries)} libraries, {total / 1024 ** 2:.1f} MB in {out}")
    return out


def check(out):
    """Load the output in a fresh Python, the way the app does, and list what it found."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]);"
            "from gigaam_app import whisper_cpp as w;"
            "lib = w.Library.get(sys.argv[2]);"
            "print('whisper.cpp', lib.version, '| backends:', ', '.join(lib.backends()));"
            "print('CPU:', lib.system_info.strip());"
            "[print('device:', d[1], '-', d[2], f'({d[3] / 1024 ** 3:.1f} GB)') for d in lib.devices()]")
    environment = dict(os.environ)
    environment.pop("GIGAAM_WHISPER_LIB", None)
    subprocess.run([sys.executable, "-c", code, str(ROOT), str(out)], check=True, env=environment)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--vulkan-sdk", default=os.environ.get("VULKAN_SDK"),
                        help="Vulkan SDK folder with bin/glslc, include/vulkan and the import library "
                             "(default: VULKAN_SDK; on Linux the system packages are used without it)")
    parser.add_argument("--work", type=Path, default=WORK_DEFAULT, help=f"build folder (default {WORK_DEFAULT})")
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT, help=f"output folder (default {OUT_DEFAULT})")
    parser.add_argument("--jobs", type=int, help="parallel compile jobs (default: Ninja's choice)")
    parser.add_argument("--check-only", action="store_true", help="only load the existing output and list devices")
    args = parser.parse_args()
    if not args.check_only:
        if sys.platform == "win32" and not args.vulkan_sdk:
            fail("pass --vulkan-sdk or set VULKAN_SDK (see the docstring)")
        environment = build_environment(args.vulkan_sdk)
        source = unpack(fetch_source(SOURCE_ARCHIVE), args.work.resolve())
        build, options = configure_and_build(source, environment, args.jobs)
        collect(build, source, args.out.resolve(), options)
    check(args.out.resolve())


if __name__ == "__main__":
    main()
