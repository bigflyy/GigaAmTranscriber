"""Settings stored as gigaam-config.json beside the app.

Version 1 files from v0.1 still load: "CUDA" becomes "GPU", the old names of
the dropped multilingual models become RNNT, and retired keys are ignored. Segmentation settings keep their v0.1 names.
"""

from dataclasses import asdict, dataclass, field, fields
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .catalog import ALIASES
from .engine import DEFAULT_MODEL, MODELS
from .outputs import DEFAULT_FORMATS, FORMATS
from .paths import app_dir, replace_file
from .vad import VadOptions

CONFIG_NAME = "gigaam-config.json"
DEVICES = ("Auto", "GPU", "CPU")
RETIRED_KEYS = {"min_duration", "vad_window_samples"}
# A Whisper language code ("en", "haw", "yue"); whisper.cpp checks it is one it knows.
LANGUAGE_PATTERN = re.compile(r"auto|[a-z]{2,3}")
# Whisper reads at most about 220 prompt tokens; a longer list is cut from the front.
MAX_TERMS_LENGTH = 500
# How the window shows the model's confidence (plan 03 B2): "underline" marks only the
# doubtful words, "colors" colours every word from green (sure) to red.
DOUBT_STYLES = ("underline", "colors")
# When suggestions for doubtful words are looked for by themselves after a file (plan 06):
# "gpu" when the file was recognised on a video card (on the CPU Whisper is slower than the
# recording: 699 s for the 455 s lecture, against 15 s on the GPU), "always", or "off" (only
# the "Найти варианты" button).
SUGGEST_MODES = ("gpu", "always", "off")


@dataclass
class Settings:
    model: str = DEFAULT_MODEL
    device: str = "Auto"
    cpu_threads: int = 0              # 0 = choose automatically
    language: str = "auto"            # Whisper only: a code such as "en", or "auto" to detect it
    terms: str = ""                   # the last terms typed when a part is recognised again (Whisper's prompt)
    include_timestamps: bool = False  # preview only; files are written as listed in outputs
    doubt_marks: bool = True          # the window marks words by the model's confidence
    doubt_style: str = "underline"    # one of DOUBT_STYLES
    doubt_light: float = 0.97         # underline style: below this a word is doubtful (dotted)
    doubt_strong: float = 0.80        # and below this likely wrong (wavy); 0 < strong < light <= 1
    player_volume: float = 1.0        # the window's player, 0..1
    suggest: str = "gpu"              # one of SUGGEST_MODES: look for other readings after each file
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
    """gigaam-config.json beside the app; GIGAAM_CONFIG names another file (tests)."""
    override = os.environ.get("GIGAAM_CONFIG")
    return Path(override) if override else app_dir() / CONFIG_NAME


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
            value = ALIASES.get(value, value) if isinstance(value, str) else value
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
        elif key == "language":
            if not isinstance(value, str) or not LANGUAGE_PATTERN.fullmatch(value):
                raise ValueError('language: expected "auto" or a language code such as "en"')
            settings.language = value
        elif key == "terms":
            if not isinstance(value, str) or len(value) > MAX_TERMS_LENGTH:
                raise ValueError(f"terms: expected text of at most {MAX_TERMS_LENGTH} characters")
            settings.terms = value
        elif key == "include_timestamps":
            if type(value) is not bool:
                raise ValueError("include_timestamps: expected true or false")
            settings.include_timestamps = value
        elif key == "doubt_marks":
            if type(value) is not bool:
                raise ValueError("doubt_marks: expected true or false")
            settings.doubt_marks = value
        elif key == "suggest":
            if type(value) is bool:  # before 2026-11-08 an on / off switch
                value = "gpu" if value else "off"
            if value not in SUGGEST_MODES:
                raise ValueError(f"suggest: expected one of {', '.join(SUGGEST_MODES)}")
            settings.suggest = value
        elif key == "doubt_style":
            if value not in DOUBT_STYLES:
                raise ValueError(f"doubt_style: expected one of {', '.join(DOUBT_STYLES)}")
            settings.doubt_style = value
        elif key == "player_volume":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ValueError("player_volume: expected a number from 0 to 1")
            settings.player_volume = float(value)
        elif key in ("doubt_light", "doubt_strong"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise ValueError(f"{key}: expected a number above 0 and at most 1")
            setattr(settings, key, float(value))
        elif key == "outputs":
            if not isinstance(value, list) or not value or any(item not in FORMATS for item in value):
                raise ValueError(f"outputs: expected a list from {', '.join(FORMATS)}")
            settings.outputs = list(dict.fromkeys(value))
        elif key in vad_names:
            setattr(settings.vad, key, _number(key, value, vad_names[key]))
        # Unknown keys are ignored so newer files still open in older versions.
    if not settings.doubt_strong < settings.doubt_light:
        raise ValueError("doubt_strong: expected a value below doubt_light")
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
        replace_file(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
