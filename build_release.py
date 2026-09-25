"""Build a self-contained Windows release with PyInstaller.

Run with the Python interpreter from the CPU or CUDA build environment.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
MODEL_NAME = "v3_e2e_rnnt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edition", choices=("cpu", "cuda"))
    parser.add_argument("mode", choices=("onedir", "onefile", "all"))
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
    model_files = [
        checkpoint_dir / f"{MODEL_NAME}.ckpt",
        checkpoint_dir / f"{MODEL_NAME}_tokenizer.model",
    ]
    missing = [str(path) for path in model_files if not path.is_file()]
    if missing:
        parser.error("Model files must be cached before building: " + ", ".join(missing))

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        parser.error("ffmpeg.exe must be available on PATH before building")

    modes = ("onedir", "onefile") if args.mode == "all" else (args.mode,)
    for mode in modes:
        base = ROOT / "build" / args.edition / mode
        base.mkdir(parents=True, exist_ok=True)
        release = ROOT / "dist" / args.edition / mode
        release.mkdir(parents=True, exist_ok=True)
        options = [
            str(ROOT / "transcribe.py"),
            f"--{mode}",
            "--noconfirm",
            "--name=GigaAmTranscriber",
            f"--paths={ROOT}",
            f"--distpath={release}",
            f"--workpath={base / 'work'}",
            f"--specpath={base}",
            "--collect-data=silero_vad",
            "--hidden-import=gigaam.encoder",
            "--hidden-import=gigaam.decoder",
            "--hidden-import=gigaam.decoding",
            "--hidden-import=gigaam.vad_utils",
            f"--add-binary={ffmpeg}{os.pathsep}bin",
        ]
        options.extend(f"--add-data={path}{os.pathsep}models" for path in model_files)
        print(f"Building {args.edition} {mode} release from {sys.executable}", flush=True)
        subprocess.run([sys.executable, "-m", "PyInstaller", *options], check=True, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
