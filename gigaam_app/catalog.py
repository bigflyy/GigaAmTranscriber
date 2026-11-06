"""Models the app knows: bundled with the app, or downloaded on request.

No model is downloadable at the moment; download.py and the GUI and CLI
download paths are ready for the first one (tests use a fake entry).

The size and SHA-256 of every downloadable file are written here, in the app
itself, so a download is accepted only if it is byte for byte the published
file. The checksums never come from the server that serves the files.

Downloadable files are assets of one GitHub release; an asset name is
"<model folder>.<file name>", because a release has one flat list of assets.
"""

from dataclasses import dataclass
from pathlib import Path

from .paths import downloads_dir, models_dir

DOWNLOAD_BASE_URL = "https://github.com/bigflyy/GigaAmTranscriber/releases/download/models-1"


@dataclass(frozen=True)
class RemoteFile:
    name: str    # file name inside the model folder
    size: int    # bytes
    sha256: str  # hex digest of the whole file


@dataclass(frozen=True)
class ModelInfo:
    key: str           # name in the settings file, in --model and in the window
    folder: str        # model folder produced by tools/export_models.py
    description: str
    files: tuple = ()  # RemoteFile entries; empty for models bundled with the app
    base_url: str = DOWNLOAD_BASE_URL
    title: str = ""   # full name for saved files (the Markdown info line); empty means the key

    @property
    def bundled(self):
        return not self.files

    @property
    def download_size(self):
        return sum(file.size for file in self.files)

    def url(self, file):
        return f"{self.base_url}/{self.folder}.{file.name}"


CATALOG = (
    ModelInfo("RNNT", "v3_e2e_rnnt", "Russian, punctuation and capitals (default)", title="GigaAM v3 RNNT"),
    ModelInfo("CTC", "v3_e2e_ctc", "Russian, punctuation and capitals, a little faster than RNNT",
              title="GigaAM v3 CTC"),
)
BY_KEY = {info.key: info for info in CATALOG}


def model_title(key):
    """Full model name for a settings key ("RNNT" -> "GigaAM v3 RNNT"); unknown keys stay as they are."""
    info = BY_KEY.get(key)
    return (info.title or info.key) if info else key

# Model names used by v0.1 settings files. The GigaAM multilingual CTC models
# were dropped in v0.2 (worse than RNNT on Russian, Cyrillic transliteration of
# English), so settings that chose them load with RNNT.
ALIASES = {
    "Multilingual CTC (220M)": "RNNT",
    "Multilingual CTC Large (600M)": "RNNT",
}


class ModelNotInstalled(RuntimeError):
    def __init__(self, info):
        super().__init__(f"Model {info.key} is not downloaded yet "
                         f"({info.download_size / 1024 ** 2:.0f} MB). "
                         f"Download it: gigaam-cli --download {info.key}")
        self.info = info


def find(key):
    """ModelInfo for a key or a v0.1 name; ValueError for unknown names."""
    info = BY_KEY.get(ALIASES.get(key, key))
    if info is None:
        raise ValueError(f"Unknown model {key!r}; expected one of {', '.join(BY_KEY)}")
    return info


def installed_folder(info):
    """Folder that holds the model, or None. Bundled models live beside the app;
    downloaded ones in the per-user folder, or beside the app if copied there."""
    roots = [models_dir()] if info.bundled else [models_dir(), downloads_dir()]
    for root in roots:
        folder = Path(root) / info.folder
        if (folder / "model.json").is_file():
            return folder
    return None
