"""Plan 08 A5: the offers each runtime's readings give, side by side, with times.

    python experiments/cpu_asr/compare.py DATA_DIR --base wcpp-auto [--out FILE.json]

For every label in DATA_DIR/readings and every file it read, turns each piece's reading into
offers for the piece's doubtful groups with the app's own fix.suggestion_from (what the window
would show), and prints per label: seconds per piece, total, peak RAM, groups with an offer,
and how many offers equal the --base label's offer for the same group (word keys compared).
--out keeps every group's offers per label for the results page and for judging by hand.
Run from the repository root with the dev venv.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import hint_language, load_pieces  # noqa: E402
from gigaam_app import fix  # noqa: E402
from gigaam_app.asr import Word  # noqa: E402


def joined_rows(rows):
    """Readings saved before read_fw.py joined word pieces: a row starting with a hyphen
    and a letter ("-агентов") belongs to the word before."""
    out = []
    for row in rows:
        if out and len(row[2]) > 1 and row[2][0] == "-" and row[2][1].isalpha():
            out[-1] = [out[-1][0], row[1], out[-1][2] + row[2], out[-1][3]]
        else:
            out.append(list(row))
    return out


def offers_of(piece, reading_rows):
    """[(group text, offer key or None, offer text, replaced text)] for each group of a piece."""
    context = [Word(*row) for row in piece["words"]]
    reading = [Word(*row) for row in joined_rows(reading_rows)]
    found = []
    for first, last in piece["selected"]:
        group = " ".join(word.text for word in context[first:last + 1])
        offer = fix.suggestion_from(reading, context, first, last)
        if offer is None:
            found.append((group, None, "", ""))
            continue
        index, count, words = offer
        key = (index, count, tuple(fix.word_key(word.text) for word in words))
        found.append((group, key, " ".join(word.text for word in words),
                      " ".join(word.text for word in context[index:index + count])))
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir")
    parser.add_argument("--base", default="wcpp-auto")
    parser.add_argument("--out")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    readings_dir = Path(args.data_dir) / "readings"
    loaded = {}
    for folder in sorted(path for path in readings_dir.iterdir() if path.is_dir()):
        if not folder.name.startswith("smoke"):
            loaded[folder.name] = {path.stem: json.loads(path.read_text(encoding="utf-8"))
                                   for path in sorted(folder.glob("*.json"))}
    # whisper.cpp with the language from GigaAM's text (common.hint_language), put together
    # from the two real runs: the "ru" reading where the hint is ru, the "auto" one elsewhere.
    if "wcpp-auto" in loaded and "wcpp-ru" in loaded:
        loaded["wcpp-hint"] = {}
        for name, auto in loaded["wcpp-auto"].items():
            russian = {p["number"]: p for p in loaded["wcpp-ru"].get(name, {}).get("pieces", [])}
            pieces = {piece["number"]: piece for piece in load_pieces(args.data_dir, name)["pieces"]}
            chosen = [russian[p["number"]] if hint_language(pieces[p["number"]]) == "ru" else p
                      for p in auto["pieces"]]
            loaded["wcpp-hint"][name] = {"total": sum(p["spent"] for p in chosen), "pieces": chosen}
    table, kept = [], {}
    base_offers = {}
    for label in [args.base] + [label for label in loaded if label != args.base]:
        for name, data in loaded[label].items():
            pieces = {piece["number"]: piece for piece in load_pieces(args.data_dir, name)["pieces"]}
            groups = with_offer = same = 0
            for reading in data["pieces"]:
                piece = pieces[reading["number"]]
                for slot, (group, key, text, replaced) in enumerate(offers_of(piece, reading["words"])):
                    where = (name, reading["number"], slot)
                    groups += 1
                    with_offer += key is not None
                    if label == args.base:
                        base_offers[where] = key
                    same += key == base_offers.get(where, "missing")
                    entry = kept.setdefault(f"{name}/{reading['number']}/{slot}", {
                        "file": name, "piece": reading["number"], "group": group,
                        "line": " ".join(row[2] for row in piece["words"]), "offers": {}})
                    entry["offers"][label] = {"offer": text, "replaces": replaced} if key else None
            count = len(data["pieces"])
            languages = {}
            for reading in data["pieces"]:
                languages[reading.get("language")] = languages.get(reading.get("language"), 0) + 1
            table.append((label, name, count, data["total"], data["total"] / max(1, count),
                          data.get("peak_ram_mb"), groups, with_offer, same, languages))
    print(f"{'label':22s} {'file':11s} {'pieces':>6s} {'total s':>8s} {'s/piece':>7s} {'RAM MB':>7s} "
          f"{'groups':>6s} {'offers':>6s} {'=base':>6s}  languages")
    for label, name, count, total, each, ram, groups, with_offer, same, languages in table:
        print(f"{label:22s} {name:11s} {count:6d} {total:8.1f} {each:7.2f} {ram or 0:7d} "
              f"{groups:6d} {with_offer:6d} {same:6d}  {languages}")
    if args.out:
        Path(args.out).write_text(json.dumps({"table": table, "groups": list(kept.values())},
                                             ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
