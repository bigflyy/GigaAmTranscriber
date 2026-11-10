"""Shared by the plan 08 reading scripts (no imports beyond the standard library, so every venv can use it)."""

import json
from pathlib import Path
import re


def load_pieces(data_dir, name, most=None):
    """pieces.json of one file, with at most `most` pieces picked evenly over the file
    (the same pieces for every runtime)."""
    info = json.loads((Path(data_dir) / name / "pieces.json").read_text(encoding="utf-8"))
    pieces = info["pieces"]
    if most and len(pieces) > most:
        pieces = [pieces[round(i * (len(pieces) - 1) / (most - 1))] for i in range(most)]
    info["pieces"] = pieces
    return info


LATIN = re.compile("[A-Za-z]")
CYRILLIC = re.compile("[Ѐ-ӿ]")
# Below this share of Latin letters in GigaAM's text the piece is read as Russian.
HINT_LATIN_BELOW = 0.15


def hint_language(piece):
    """Language for Whisper from GigaAM's own text of the piece (plan 08): "ru" when it is
    almost all Cyrillic, None (let Whisper detect it) otherwise. GigaAM writes English
    speech in Latin letters, so this costs nothing and spares the detection pass."""
    text = " ".join(row[2] for row in piece["words"])
    latin, cyrillic = len(LATIN.findall(text)), len(CYRILLIC.findall(text))
    return "ru" if latin / max(1, latin + cyrillic) < HINT_LATIN_BELOW else None


def piece_path(data_dir, name, piece):
    return Path(data_dir) / name / f"{piece['number']:04d}.npy"


def save_readings(data_dir, label, name, total, results, extra=None):
    out_dir = Path(data_dir) / "readings" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"label": label, "total": total, "pieces": results, **(extra or {})}
    (out_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def peak_ram_mb():
    """Peak working set of this process in MB (psutil on Windows), None when unknown."""
    try:
        import psutil
        info = psutil.Process().memory_info()
        return round(getattr(info, "peak_wset", info.rss) / 2**20)
    except Exception:
        return None
