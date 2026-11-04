"""Settings stored as gigaam-config.json beside the app.

Version 1 files from v0.1 still load: "CUDA" becomes "GPU", and retired keys
are ignored. Segmentation settings keep their v0.1 names.
"""

from dataclasses import asdict, dataclass, field, fields
import json
import math
import os
from pathlib import Path
import tempfile

from .engine import DEFAULT_MODEL, MODELS
from .outputs import DEFAULT_FORMATS, FORMATS
from .paths import app_dir
from .vad import VadOptions

CONFIG_NAME = "gigaam-config.json"
DEVICES = ("Auto", "GPU", "CPU")
RETIRED_KEYS = {"min_duration", "vad_window_samples"}


@dataclass
class Settings:
    model: str = DEFAULT_MODEL
    device: str = "Auto"
    cpu_threads: int = 0              # 0 = choose automatically
    include_timestamps: bool = False  # preview only; files are written as listed in outputs
    outputs: list = field(default_factory=lambda: list(DEFAULT_FORMATS))
    vad: VadOptions = field(default_factory=VadOptions)

    @property
    def engine_device(self):
        return self.device.lower()

    def to_json(self):
        data = {"version": 2, **{k: v for k, v in asdict(self).items() if k != "vad"}}
        data.update(asdict(self.vad))
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def default_path():
    return app_dir() / CONFIG_NAME


def parse(data):
    """Validate a decoded JSON object into Settings; raises ValueError with a readable message."""
    if not isinstance(data, dict):
        raise ValueError("Settings must be a JSON object.")
    version = data.get("version", 2)
    if version not in (1, 2):
        raise ValueError(f"Unsupported settings version: {version}")
    settings = Settings()
    vad_names = {f.name: f.type for f in fields(VadOptions)}
    for key, value in data.items():
        if key == "version" or key in RETIRED_KEYS:
            continue
        if key == "model":
            if value not in MODELS:
                raise ValueError(f"model: expected one of {', '.join(MODELS)}")
            settings.model = value
        elif key == "device":
            value = "GPU" if value == "CUDA" else value
            if value not in DEVICES:
                raise ValueError(f"device: expected one of {', '.join(DEVICES)}")
            settings.device = value
        elif key == "cpu_threads":
            if type(value) is not int or value < 0:
                raise ValueError("cpu_threads: expected a whole number, 0 for automatic")
            settings.cpu_threads = value
        elif key == "include_timestamps":
            if type(value) is not bool:
                raise ValueError("include_timestamps: expected true or false")
            settings.include_timestamps = value
        elif key == "outputs":
            if not isinstance(value, list) or not value or any(item not in FORMATS for item in value):
                raise ValueError(f"outputs: expected a list from {', '.join(FORMATS)}")
            settings.outputs = list(dict.fromkeys(value))
        elif key in vad_names:
            setattr(settings.vad, key, _number(key, value, vad_names[key]))
        # Unknown keys are ignored so newer files still open in older versions.
    if not 0 < settings.vad.vad_threshold <= 1:
        raise ValueError("vad_threshold: expected a value above 0 and at most 1")
    for key in ("max_duration", "strict_limit_duration", "vad_max_speech_s"):
        if getattr(settings.vad, key) <= 0:
            raise ValueError(f"{key}: expected a value above 0")
    return settings


def _number(key, value, kind):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{key}: expected a non-negative number")
    if kind in (int, "int"):
        if value != int(value):
            raise ValueError(f"{key}: expected a whole number")
        return int(value)
    return float(value)


def load(path=None):
    """Settings from the file, or defaults when it does not exist."""
    path = Path(path) if path else default_path()
    if not path.is_file():
        return Settings()
    return parse(json.loads(path.read_text(encoding="utf-8-sig")))


def save(settings, path=None):
    path = Path(path) if path else default_path()
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(settings.to_json())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
