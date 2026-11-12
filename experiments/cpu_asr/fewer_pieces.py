"""Plan 08 B1: how much reading fewer pieces would save, and which offers it would lose.

    python experiments/cpu_asr/fewer_pieces.py DATA_DIR [--out FILE.json]

The search reads every line that holds a word below Settings.doubt_light (0.97). B1 asks
whether a stricter choice of lines is worth it:

- "strong": read a line only when one of its doubtful words is below doubt_strong (0.80),
  the words the window marks with a wavy line;
- "run N": read a line only when it holds a doubtful group of at least N words;
- "strong or run N": either of the two.

A kept line is read whole, as today, so every doubtful group on it still gets its offer;
only the groups on dropped lines lose theirs. The readings already saved by Stage A are
reused (a kept piece's reading does not change), so no model runs here.

For every file and choice it prints: pieces kept (of all the file's pieces, and of the read
sample), the reading time kept (sum of the saved per-piece times of the sample, faster-whisper
int8 one piece at a time and whisper.cpp with the language hint), doubtful groups covered,
offers kept and lost, lost offers on which both Whisper runtimes agree (a sign the offer is
likely right), and on the lecture which of plan 06's nine right terms stay.
Run from the repository root with the dev venv.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import hint_language, load_pieces  # noqa: E402
from compare import offers_of  # noqa: E402
from gigaam_app import fix  # noqa: E402
from gigaam_app.config import Settings  # noqa: E402

FILES = ("lecture", "call2023", "interview", "audiozapis")
# The lecture terms plan 06 A5 counted as right offers (checked by hand then).
LECTURE_TERMS = ("LLM-агентов", "fine-tuning", "промпт-инжиниринга", "BIM-моделей", "промпта",
                 "UML-промптинга", "принятие", "Prompt Engineering", "Tools Calling")
# The runtime the app uses on the CPU after A6 / C2, and the one it replaced (for agreement).
MAIN_LABEL = "fwq-one-hint"
OTHER_LABEL = "wcpp-hint"


def group_facts(piece, strong):
    """For each doubtful group of a piece: (word count, lowest confidence)."""
    facts = []
    for first, last in piece["selected"]:
        rows = piece["words"][first:last + 1]
        known = [row[3] for row in rows if row[3] is not None]
        facts.append((last - first + 1, min(known) if known else 1.0))
    return facts


def choices(strong):
    """name -> test(piece facts) that says whether the piece is still read."""
    def has_strong(facts):
        return any(lowest < strong for _, lowest in facts)

    def run(size):
        return lambda facts: any(count >= size for count, _ in facts)

    found = {"today": lambda facts: True, "strong": has_strong}
    for size in (2, 3, 4):
        found[f"run {size}"] = run(size)
        found[f"strong or run {size}"] = (lambda test: lambda facts: has_strong(facts) or test(facts))(run(size))
    return found


def wcpp_hint(data_dir, name):
    """whisper.cpp readings with the language from GigaAM's text, as compare.py makes them:
    the "ru" reading where the hint is ru, the "auto" one elsewhere. None when not saved."""
    readings = Path(data_dir) / "readings"
    try:
        auto = json.loads((readings / "wcpp-auto" / f"{name}.json").read_text(encoding="utf-8"))
        russian = json.loads((readings / "wcpp-ru" / f"{name}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    pieces = {piece["number"]: piece for piece in load_pieces(data_dir, name)["pieces"]}
    by_number = {p["number"]: p for p in russian["pieces"]}
    return {p["number"]: (by_number[p["number"]] if hint_language(pieces[p["number"]]) == "ru" else p)
            for p in auto["pieces"]}


def key_of(text):
    return fix.word_key(text.replace(" ", ""))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir")
    parser.add_argument("--out")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    strong = Settings().doubt_strong
    tests = choices(strong)

    report = {"doubt_strong": strong, "files": {}}
    for name in FILES:
        info = load_pieces(args.data_dir, name)
        everything = {piece["number"]: piece for piece in info["pieces"]}
        main_readings = json.loads((Path(args.data_dir) / "readings" / MAIN_LABEL / f"{name}.json")
                                   .read_text(encoding="utf-8"))
        main_by_number = {p["number"]: p for p in main_readings["pieces"]}
        other_by_number = wcpp_hint(args.data_dir, name) or {}
        rows = []
        for choice, test in tests.items():
            kept_all = sum(test(group_facts(piece, strong)) for piece in everything.values())
            row = {"choice": choice, "pieces_all": len(everything), "kept_all": kept_all,
                   "sample": len(main_by_number), "kept_sample": 0, "fw_seconds": 0.0, "fw_total": 0.0,
                   "wcpp_seconds": 0.0, "wcpp_total": 0.0, "groups": 0, "groups_kept": 0,
                   "offers": 0, "offers_kept": 0, "lost_agreed": 0, "lost": [], "terms_kept": []}
            terms_found = []
            for number, reading in main_by_number.items():
                piece = everything[number]
                keep = test(group_facts(piece, strong))
                row["fw_total"] += reading["spent"]
                other = other_by_number.get(number)
                if other is not None:
                    row["wcpp_total"] += other["spent"]
                offers = offers_of(piece, reading["words"])
                other_offers = offers_of(piece, other["words"]) if other is not None else [None] * len(offers)
                row["groups"] += len(offers)
                if keep:
                    row["kept_sample"] += 1
                    row["fw_seconds"] += reading["spent"]
                    row["wcpp_seconds"] += other["spent"] if other is not None else 0.0
                    row["groups_kept"] += len(offers)
                for (group, key, text, replaced), theirs in zip(offers, other_offers):
                    if key is None:
                        continue
                    row["offers"] += 1
                    if name == "lecture":
                        for term in LECTURE_TERMS:
                            if key_of(term) in key_of(text) and term not in terms_found:
                                terms_found.append(term)
                                if keep:
                                    row["terms_kept"].append(term)
                    if keep:
                        row["offers_kept"] += 1
                        continue
                    agreed = theirs is not None and theirs[1] == key
                    row["lost_agreed"] += agreed
                    row["lost"].append({"piece": number, "group": group, "replaces": replaced,
                                        "offer": text, "both_agree": agreed})
            row["terms_all"] = terms_found
            rows.append(row)
        report["files"][name] = rows

    print(f"doubt_strong {strong}; time = saved per-piece times of the read sample "
          f"({MAIN_LABEL} / {OTHER_LABEL})")
    print(f"{'file':11s} {'choice':16s} {'pieces':>11s} {'sample':>7s} {'fw s':>13s} {'wcpp s':>13s} "
          f"{'groups':>9s} {'offers':>9s} {'lost':>5s} {'agreed':>6s}  terms")
    for name, rows in report["files"].items():
        for row in rows:
            share = row["fw_seconds"] / max(1e-9, row["fw_total"])
            terms = f"{len(row['terms_kept'])}/{len(row['terms_all'])}" if name == "lecture" else ""
            print(f"{name:11s} {row['choice']:16s} {row['kept_all']:4d}/{row['pieces_all']:<4d}"
                  f"{100 * row['kept_all'] / row['pieces_all']:3.0f}% {row['kept_sample']:3d}/{row['sample']:<3d} "
                  f"{row['fw_seconds']:6.0f} {100 * share:4.0f}% {row['wcpp_seconds']:6.0f}/{row['wcpp_total']:<6.0f}"
                  f"{row['groups_kept']:4d}/{row['groups']:<4d} {row['offers_kept']:4d}/{row['offers']:<4d} "
                  f"{len(row['lost']):5d} {row['lost_agreed']:6d}  {terms}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
