"""Prepare GitHub assets, splitting only an oversized CUDA executable."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def prepare(cpu, cuda, destination, part_size=1900 * 1024**2):
    destination.mkdir(parents=True, exist_ok=True)
    cpu_name = "GigaAmTranscriber-CPU.exe"
    cuda_name = "GigaAmTranscriber-CUDA.exe"
    assets = []
    shutil.copy2(cpu, destination / cpu_name)
    assets.append(destination / cpu_name)
    if cuda.stat().st_size < 2 * 1024**3:
        shutil.copy2(cuda, destination / cuda_name)
        assets.append(destination / cuda_name)
    else:
        manifest = {"output": cuda_name, "size": cuda.stat().st_size, "sha256": sha256(cuda), "parts": []}
        with cuda.open("rb") as source:
            index = 1
            while source.tell() < manifest["size"]:
                part = destination / f"{cuda_name}.part{index:02d}"
                remaining = part_size
                digest = hashlib.sha256()
                with part.open("wb") as target:
                    while remaining:
                        block = source.read(min(4 * 1024**2, remaining))
                        if not block:
                            break
                        target.write(block)
                        digest.update(block)
                        remaining -= len(block)
                manifest["parts"].append(dict(name=part.name, size=part.stat().st_size, sha256=digest.hexdigest()))
                assets.append(part)
                print(f"Prepared {part.name}: {part.stat().st_size / 1024**2:.1f} MiB", flush=True)
                index += 1
        manifest_path = destination / "cuda-parts.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        assets.append(manifest_path)
        for name in ("Join-CUDA.ps1", "Join-CUDA.cmd"):
            shutil.copy2(ROOT / "release" / name, destination / name)
            assets.append(destination / name)
    shutil.copy2(ROOT / "gigaam-config.example.json", destination / "gigaam-config.example.json")
    assets.append(destination / "gigaam-config.example.json")
    checksums = destination / "SHA256SUMS.txt"
    checksums.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in assets), encoding="utf-8")
    print(f"Prepared {len(assets)} assets plus checksums in {destination}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=Path, required=True)
    parser.add_argument("--cuda", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.cpu, args.cuda, args.destination)
