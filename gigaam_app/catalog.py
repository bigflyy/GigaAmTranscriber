"""Models the app knows: bundled with the app, or downloaded on request.

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

    @property
    def bundled(self):
        return not self.files

    @property
    def download_size(self):
        return sum(file.size for file in self.files)

    def url(self, file):
        return f"{self.base_url}/{self.folder}.{file.name}"


CATALOG = (
    ModelInfo("RNNT", "v3_e2e_rnnt", "Russian, punctuation and capitals (default)"),
    ModelInfo("CTC", "v3_e2e_ctc", "Russian, punctuation and capitals, a little faster than RNNT"),
    ModelInfo("Multilingual", "multilingual_ctc",
              "Russian, English, Kazakh and other languages; lowercase, no punctuation (220M)", files=(
                  RemoteFile("model.json", 483, "46bf56233501dca6fd4d1e3b708b15a5dbb2ae9341bf9502a0394b40d54bb192"),
                  RemoteFile("vocab.json", 392, "b4bb373f5d37285d5993071d351aaa5d2f77b4988991484a589c88e30b756de2"),
                  RemoteFile("encoder.onnx", 885861138,
                             "bb433f2caf41d3687bc7dff9131532f78bb67487e6797948534e2162282d352a"),
              )),
    ModelInfo("Multilingual-Large", "multilingual_large_ctc",
              "Like Multilingual, larger and slower (600M)", files=(
                  RemoteFile("model.json", 836, "6e64ef7a1b7edcc568c7eea65d0b8b8b03ceb5c499b7af872009e8e8083b7752"),
                  RemoteFile("vocab.json", 392, "b4bb373f5d37285d5993071d351aaa5d2f77b4988991484a589c88e30b756de2"),
                  RemoteFile("encoder.onnx", 3486444,
                             "edbebce8351785dd10a7370d7a680e472b5377886a38881c5048fea7b3d8db1a"),
                  RemoteFile("encoder.data1", 1603538944,
                             "7687afc48cd0b3ef4967aec681899136d253fe65cdf6ee2998cf7c41c7ed4947"),
                  RemoteFile("encoder.data2", 738197504,
                             "d01248c14065795490c154303c01039b826a8e5b524f4789be3c1d22b1209ba3"),
              )),
)
BY_KEY = {info.key: info for info in CATALOG}

# Model names used by v0.1 settings files.
ALIASES = {
    "Multilingual CTC (220M)": "Multilingual",
    "Multilingual CTC Large (600M)": "Multilingual-Large",
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
