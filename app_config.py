"""Portable GUI settings stored beside the executable (or source launcher)."""

import json
import math
import os
from pathlib import Path
import sys
import tempfile


SETTINGS = (
    ("vad_threshold", "VAD threshold", float, 0.5),
    ("vad_min_speech_ms", "VAD min speech (ms)", int, 300),
    ("vad_max_speech_s", "VAD max speech (s)", float, 25),
    ("vad_min_silence_ms", "VAD min silence (ms)", int, 2000),
    ("vad_speech_pad_ms", "VAD speech padding (ms)", int, 250),
    ("new_chunk_threshold", "Min chunk duration (s)", float, 0.2),
    ("max_duration", "Preferred max chunk (s)", float, 25),
    ("strict_limit_duration", "Hard chunk limit (s)", float, 25),
)


def default_config_path():
    # onefile's __file__ points into its temporary extraction directory.
    launcher = Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__)
    return launcher.resolve().parent / "gigaam-config.json"


def defaults():
    return {"version": 1, "model": "RNNT", "device": "Auto", "cpu_threads": 4,
            "include_timestamps": False,
            **{name: default for name, _, _, default in SETTINGS}}


def validate_config(data):
    """Validate the entire document before applying anything; missing keys use defaults."""
    if not isinstance(data, dict):
        raise ValueError("Конфигурация должна быть объектом JSON.")
    # Earlier presets contained this retired grouping target. Accept and discard it.
    data = {key: value for key, value in data.items() if key != "min_duration"}
    config = defaults()
    unknown = data.keys() - config.keys()
    if unknown:
        raise ValueError("Неизвестные параметры: " + ", ".join(sorted(unknown)))
    config.update(data)
    if type(config["version"]) is not int or config["version"] != 1:
        raise ValueError("Неподдерживаемая версия конфигурации (ожидается version: 1).")
    if config["model"] not in ("RNNT", "CTC"):
        raise ValueError("Model: допустимы RNNT или CTC.")
    if config["device"] not in ("Auto", "CPU", "CUDA"):
        raise ValueError("Device: допустимы Auto, CPU или CUDA.")
    if type(config["cpu_threads"]) is not int or config["cpu_threads"] < 1:
        raise ValueError("CPU threads: требуется целое число не меньше 1.")
    if type(config["include_timestamps"]) is not bool:
        raise ValueError("include_timestamps: требуется true или false.")
    positive = {"max_duration", "strict_limit_duration", "vad_max_speech_s"}
    for name, label, kind, _ in SETTINGS:
        value = config[name]
        if type(value) not in (int, float) or (kind is int and type(value) is not int):
            raise ValueError(f"{label}: неверный тип числа.")
        try:
            valid = math.isfinite(value) and value >= 0
        except OverflowError:
            valid = False
        if not valid or (name in positive and value == 0):
            raise ValueError(f"{label}: недопустимое значение.")
        if name == "vad_threshold" and not 0 < value <= 1:
            raise ValueError("VAD threshold должен быть больше 0 и не больше 1.")
    return config


def read_config(path):
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def write_config(path, config):
    config = validate_config(config)
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
