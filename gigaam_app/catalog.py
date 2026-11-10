"""Models the app knows: bundled with the app, or downloaded on request.

The size and SHA-256 of every downloadable file are written here, in the app
itself, so a download is accepted only if it is byte for byte the published
file. The checksums never come from the server that serves the files.

Downloadable files are assets of one GitHub release; an asset name is
"<model folder>.<file name>", because a release has one flat list of assets.
A file may also list mirrors: other addresses of the same bytes, tried in order
when the release cannot deliver it (owner's choice, 2026-11-07: our release first,
Hugging Face as the backup for Whisper).

A model whose files come from elsewhere (Whisper's ggml file is published by the
whisper.cpp project) has no model.json among its files; it names its model_type
instead, and download.py writes model.json from manifest() after the download.
"""

from dataclasses import dataclass
from pathlib import Path

from .paths import downloads_dir, models_dir

DOWNLOAD_BASE_URL = "https://github.com/bigflyy/GigaAmTranscriber/releases/download/models-1"
# The whisper.cpp project's model files, pinned to one commit so the address never
# points at changed bytes (the SHA-256 check would refuse them anyway).
WHISPER_CPP_HF = "https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1"


@dataclass(frozen=True)
class RemoteFile:
    name: str    # file name inside the model folder
    size: int    # bytes
    sha256: str  # hex digest of the whole file
    role: str = "model"  # its key under "files" in a model.json written by manifest()
    mirrors: tuple = ()  # full URLs of the same file elsewhere, tried after the release


@dataclass(frozen=True)
class ModelInfo:
    key: str           # name in the settings file, in --model and in the window
    folder: str        # model folder produced by tools/export_models.py
    description: str
    files: tuple = ()  # RemoteFile entries; empty for models bundled with the app
    base_url: str = DOWNLOAD_BASE_URL
    title: str = ""   # full name for saved files (the Markdown info line); empty means the key
    model_type: str = ""  # set when the app writes model.json itself (see manifest())

    @property
    def bundled(self):
        return not self.files

    @property
    def download_size(self):
        return sum(file.size for file in self.files)

    def url(self, file):
        return f"{self.base_url}/{self.folder}.{file.name}"

    def urls(self, file):
        """Every address of a file, in the order to try them: the release, then the mirrors."""
        return (self.url(file),) + tuple(file.mirrors)


def manifest(info):
    """model.json for a model that does not download one: the same format as
    tools/export_models.py writes, with the catalog's sizes and checksums."""
    return {
        "format": 1,
        "name": info.folder,
        "type": info.model_type,
        "sample_rate": 16000,
        "files": {file.role: {"name": file.name, "sha256": file.sha256, "size": file.size} for file in info.files},
    }


CATALOG = (
    ModelInfo("RNNT", "v3_e2e_rnnt", "Russian, punctuation and capitals (default)", title="GigaAM v3 RNNT"),
    ModelInfo("CTC", "v3_e2e_ctc", "Russian, punctuation and capitals, a little faster than RNNT",
              title="GigaAM v3 CTC"),
    # Whisper large-v3-turbo, q5_0 (plan 04): 99 languages, writes English terms in
    # Latin letters; about 2.5x slower than GigaAM on a GPU (HANDOFF.md, session 10).
    ModelInfo("Whisper", "whisper_large_v3_turbo_q5_0",
              "Whisper large-v3-turbo: 99 languages, English terms as written; slower than GigaAM",
              files=(RemoteFile("ggml-large-v3-turbo-q5_0.bin", 574_041_195,
                                "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
                                mirrors=(f"{WHISPER_CPP_HF}/ggml-large-v3-turbo-q5_0.bin",)),),
              title="Whisper large-v3-turbo (q5_0)", model_type="whisper"),
)
BY_KEY = {info.key: info for info in CATALOG}

# Speaker labels (plan 07, gigaam_app/diarize.py): pyannote community-1 on ONNX, made by
# experiments/diarization/export_speaker_models.py. Not a speech model, so not in CATALOG
# (the window's model list); downloaded the first time speakers are looked for.
# Licences: segmentation-3.0 MIT, WeSpeaker ResNet34-LM and the PLDA CC BY 4.0.
SPEAKER_MODEL = ModelInfo(
    "Speakers", "speakers_community1", "Speaker labels: pyannote community-1 (segmentation-3.0, WeSpeaker ResNet34-LM, PLDA)",
    files=(RemoteFile("segmentation.onnx", 5_916_314,
                      "3550ea68ca1ef51073036f4934513c03c4776065d009fa850d8e671e89ff0c91", role="segmentation"),
           RemoteFile("embedding.onnx", 26_540_186,
                      "140b763b61363bd37ef524546eeb5168a821b9cdf80d5772068f983c0093a179", role="embedding"),
           RemoteFile("speakers.npz", 268_598,
                      "3290ecac3ca358ea4c1ada30056da4dbe9fecd3f2d89043a7b6ae78b9f70c064", role="arrays"),
           RemoteFile("speakers.json", 386,
                      "e195b1d67fdf4bbd9ffe8ca5b7b4d65baed14d79d7d79a0b7a4ae42c912379d2", role="config")),
    title="pyannote community-1 (ONNX)", model_type="speakers")


# Whisper large-v3-turbo for faster-whisper (CTranslate2), quantised to int8 (plan 08 C2):
# about 1.6x faster than whisper.cpp q5_0 on the CPU one piece at a time, 2x in batches of
# 8 (HANDOFF.md, session 24). Used only when Настройки choose it for Whisper on the
# processor; downloaded only then (owner 2026-11-11: "users dont have to download all the
# models all at once"). The files are Zoont's ready-made conversion (MIT, made with
# ct2-transformers-converter --quantization int8 from openai/whisper-large-v3-turbo),
# pinned to one commit; our release is tried first, as for Whisper.
FAST_WHISPER_HF = "https://huggingface.co/Zoont/faster-whisper-large-v3-turbo-int8-ct2/resolve/846f74797293e5f605d509a6ab5395a1f2f2874e"
FAST_WHISPER_MODEL = ModelInfo(
    "faster-whisper", "faster_whisper_large_v3_turbo_int8",
    "Whisper large-v3-turbo for faster-whisper (CTranslate2 int8): faster on the CPU",
    files=tuple(RemoteFile(name, size, sha256, role=role, mirrors=(f"{FAST_WHISPER_HF}/{name}",))
                for name, size, sha256, role in (
                    ("model.bin", 814_054_531, "7482f978f9493b93b3d0bf68a148a1a62ca02547e8ee981358ff8ef2de8a9418", "model"),
                    ("config.json", 2_487, "27ec8ecb8ba05f3ac81522a7a035bd5ab19a5b567640bf68ccec90ded4fc1726", "config"),
                    ("preprocessor_config.json", 340,
                     "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711", "preprocessor"),
                    ("tokenizer.json", 2_710_337,
                     "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd", "tokenizer"),
                    ("vocabulary.json", 1_119_981,
                     "697ee5a65726e46b4d294d1a243d98e1878f5d81caba17891b1c5ebab7a912a9", "vocabulary"))),
    title="Whisper large-v3-turbo (faster-whisper int8)", model_type="faster-whisper")


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
    """ModelInfo for a key or a v0.1 name, or FAST_WHISPER_MODEL (not in the window's model
    list, but downloaded and loaded by its key); ValueError for unknown names."""
    if key == FAST_WHISPER_MODEL.key:
        return FAST_WHISPER_MODEL
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
