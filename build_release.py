"""Build a self-contained Windows release with PyInstaller.

Run with the Python interpreter from the CPU or CUDA build environment.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from model_catalog import MODEL_CHOICES, DEFAULT_BUNDLED_MODELS, model_files


ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edition", choices=("cpu", "cuda"))
    parser.add_argument("mode", choices=("onedir", "onefile", "all"))
    parser.add_argument("--models", nargs="+", choices=tuple(MODEL_CHOICES.values()),
                        default=DEFAULT_BUNDLED_MODELS,
                        help="Models to bundle; defaults to Russian RNNT and CTC. Others download on first use.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "dist",
                        help="Release root; use a new folder if older EXEs are running")
    args = parser.parse_args()

    if sys.platform != "win32":
        parser.error("This build script currently creates Windows releases only")

    import torch
    import PyInstaller  # noqa: F401 - fail early when the build tool is missing

    has_cuda = torch.version.cuda is not None
    if args.edition == "cpu" and has_cuda:
        parser.error("CPU release requires a CPU-only PyTorch installation")
    if args.edition == "cuda" and not has_cuda:
        parser.error("CUDA release requires a CUDA-enabled PyTorch installation")

    checkpoint_dir = Path.home() / ".cache" / "gigaam"
    bundle_files = [
        checkpoint_dir / filename
        for name in dict.fromkeys(args.models)
        for filename in model_files(name)
    ]
    missing = [str(path) for path in bundle_files if not path.is_file()]
    if missing:
        parser.error("Model files must be cached before building: " + ", ".join(missing))

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        parser.error("ffmpeg.exe must be available on PATH before building")

    modes = ("onedir", "onefile") if args.mode == "all" else (args.mode,)
    for mode in modes:
        base = ROOT / "build" / args.edition / mode
        base.mkdir(parents=True, exist_ok=True)
        release = args.output_root.resolve() / args.edition / mode
        release.mkdir(parents=True, exist_ok=True)
        options = [
            str(ROOT / "transcribe.py"),
            f"--{mode}",
            "--windowed",
            "--noconfirm",
            "--name=GigaAmTranscriber",
            f"--paths={ROOT}",
            f"--distpath={release}",
            # Both formats share analysis/PYZ caches; only the final archive differs.
            f"--workpath={ROOT / 'build' / args.edition / 'work'}",
            f"--specpath={base}",
            "--collect-data=silero_vad",
            "--hidden-import=gigaam.encoder",
            "--hidden-import=gigaam.decoder",
            "--hidden-import=gigaam.decoding",
            "--hidden-import=gigaam.vad_utils",
            f"--add-binary={ffmpeg}{os.pathsep}bin",
        ]
        options.extend(f"--add-data={path}{os.pathsep}models" for path in bundle_files)
        options.append(f"--add-data={ROOT / 'LICENSE'}{os.pathsep}licenses/gigaam")
        ffmpeg_dir = Path(ffmpeg).parent.parent
        for filename in ("LICENSE", "README.txt"):
            notice = ffmpeg_dir / filename
            if notice.is_file():
                options.append(f"--add-data={notice}{os.pathsep}licenses/ffmpeg")
        print(f"Building {args.edition} {mode} release from {sys.executable}", flush=True)
        subprocess.run([sys.executable, "-m", "PyInstaller", *options], check=True, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
