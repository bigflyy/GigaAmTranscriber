"""Prepare exported model folders for download hosting and print their catalog entries.

    python tools/stage_model_assets.py OUT_DIR MODEL_FOLDER [MODEL_FOLDER ...]

Every file of a folder (model.json first) is copied to OUT_DIR as
"<folder>.<file>", the asset names gigaam_app/catalog.py expects on the
models release. The printed RemoteFile lines go into catalog.py; the sizes
and SHA-256 are computed from the copies, so they match what gets uploaded.
Then upload, for example:

    gh release upload models-1 OUT_DIR/*
"""

import hashlib
import json
from pathlib import Path
import shutil
import sys


def sha256(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage(folder, out_dir):
    folder = Path(folder)
    meta = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    names = ["model.json"] + [entry["name"] for entry in meta["files"].values()]
    print(f"# {meta['name']}")
    for name in names:
        target = out_dir / f"{folder.name}.{name}"
        shutil.copyfile(folder / name, target)
        size = target.stat().st_size
        if name != "model.json" and size != meta["files"][_role(meta, name)]["size"]:
            raise SystemExit(f"{folder / name} does not match its model.json")
        print(f'RemoteFile("{name}", {size}, "{sha256(target)}"),')


def _role(meta, name):
    return next(role for role, entry in meta["files"].items() if entry["name"] == name)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    for folder in sys.argv[2:]:
        stage(folder, out_dir)


if __name__ == "__main__":
    main()
