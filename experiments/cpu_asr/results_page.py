"""Plan 08 A5: a local results page from compare.py's JSON and the clean timing readings.

    python experiments/cpu_asr/results_page.py DATA_DIR OUT.html

Reads DATA_DIR/compare.json (compare.py --out) and DATA_DIR/readings/clean-*/lecture.json.
The page quotes the owner's own recordings, so it stays a local file (not published).
"""

import html
import json
from pathlib import Path
import sys

LABELS = [
    ("wcpp-auto", "whisper.cpp q5_0, auto (today)"),
    ("wcpp-hint", "whisper.cpp q5_0, language from GigaAM's text"),
    ("fw-one-hint", "faster-whisper int8, one"),
    ("fw-batch-hint", "faster-whisper int8, batch 8"),
    ("pk-int8", "Parakeet int8"),
    ("pk-lingoflip", "Parakeet LingoFlip int8"),
]
CLEAN = [
    ("clean-wcpp-auto", "whisper.cpp q5_0, language auto (today)", "-", "nothing new"),
    ("clean-wcpp-ru", "whisper.cpp q5_0, language ru", "-", "nothing new: the language picked from GigaAM's text"),
    ("clean-fw-one-ru", "faster-whisper int8, one piece at a time", "1879", "CTranslate2 (19.5 MiB wheel on Windows) and a second Whisper model (1.6 GB fp16 file)"),
    ("clean-fw-batch-ru", "faster-whisper int8, 8 pieces per call", "2754", "the same, and the search reads 8 lines at once"),
    ("clean-pk-int8", "Parakeet TDT 0.6B v3 int8 (sherpa-onnx)", "1195", "sherpa-onnx and a 640 MB model; weaker offers (below)"),
]


def esc(text):
    return html.escape(text or "")


def offer_cell(offer):
    if not offer:
        return '<td class="none">-</td>'
    return f"<td><s>{esc(offer['replaces'])}</s> {esc(offer['offer'])}</td>"


def main():
    data_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    compare = json.loads((data_dir / "compare.json").read_text(encoding="utf-8"))
    rows = []
    base = None
    for label, title, ram, cost in CLEAN:
        path = data_dir / "readings" / label / "lecture.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        each = data["total"] / len(data["pieces"])
        base = base or each
        rows.append(f"<tr><td>{esc(title)}</td><td class=num>{each:.1f}</td><td class=num>{base / each:.1f}x</td>"
                    f"<td class=num>{ram}</td><td>{esc(cost)}</td></tr>")
    table = [row for row in compare["table"]]
    per_file = []
    for label, title in LABELS:
        cells = []
        for name in ("lecture", "call2023", "interview", "audiozapis"):
            found = [row for row in table if row[0] == label and row[1] == name]
            if found:
                _, _, count, total, each, _, groups, offers, same, _ = found[0]
                cells.append(f"<td class=num>{each:.1f} s<br><small>{offers}/{groups} offers, {same} = today</small></td>")
            else:
                cells.append("<td>-</td>")
        per_file.append(f"<tr><td>{esc(title)}</td>{''.join(cells)}</tr>")
    lecture = []
    for group in compare["groups"]:
        if group["file"] != "lecture":
            continue
        cells = "".join(offer_cell(group["offers"].get(label)) for label, _ in LABELS)
        lecture.append(f"<tr><td><b>{esc(group['group'])}</b></td>{cells}</tr>")
    differ = []
    for group in compare["groups"]:
        if group["file"] in ("lecture",):
            continue
        a, b = group["offers"].get("wcpp-hint"), group["offers"].get("fw-one-hint")
        if (a and a["offer"].lower()) != (b and b["offer"].lower()) and len(differ) < 60:
            differ.append(f"<tr><td>{esc(group['file'])}</td><td>{esc(group['line'][:140])}</td><td><b>{esc(group['group'])}</b></td>"
                          f"{offer_cell(a)}{offer_cell(b)}</tr>")
    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CPU runtimes test</title><style>
:root {{ --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a65; --line:#e2dfd7; --accent:#2f5d8a; --none:#b0ada5; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1b1b1a; --fg:#ecebe6; --muted:#a3a19a; --line:#3a3936; --accent:#8fb6dd; --none:#6d6b66; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:0 auto; max-width:1180px; padding:24px 16px; }}
h1 {{ font-size:24px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:32px 0 8px; }}
p, li {{ max-width:860px; }} .muted, small {{ color:var(--muted); }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }} th, td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; vertical-align:top; }}
th {{ color:var(--muted); font-weight:600; }} .num {{ text-align:right; white-space:nowrap; }} td.none {{ color:var(--none); }}
s {{ color:var(--muted); }} .wrap {{ overflow-x:auto; }} .key {{ border-left:3px solid var(--accent); padding:8px 14px; margin:16px 0; }}
</style></head><body>
<h1>Suggestion search on the CPU: runtimes compared</h1>
<p class="muted">Plan 08 Stage A, 2026-11-10. The same pieces the app's suggestion search reads (doubtful lines of GigaAM RNNT,
cut as the app cuts them): the 455 s lecture (all 18) and 40 evenly spread pieces from each of your three files (2023 06 10 call,
20260401 interview, Аудиозапись). 8 CPU threads.</p>
<div class="key"><b>In short.</b> Today every piece pays for two Whisper encoder passes, one only to detect the language
(whisper.cpp does this with language "auto"). Taking the language from GigaAM's own text halves the time with the same offers.
faster-whisper is 1.6-2x faster again with offers of the same quality. Parakeet is far faster but its offers are worse:
it writes English terms in Cyrillic and offers wrong word endings.</div>
<h2>Speed (lecture, whole machine free)</h2>
<div class="wrap"><table><tr><th>Runtime</th><th class=num>s per piece</th><th class=num>faster</th><th class=num>peak RAM MB</th><th>What it adds to the app</th></tr>
{''.join(rows)}</table></div>
<p class="muted">Language from GigaAM's text: "ru" when the piece's text is under 15% Latin letters, otherwise Whisper detects it.
122 of the 138 pieces got "ru", and Whisper's own detection said ru on 121 of those; the other 16 are left to Whisper's
detection (they pay for it). Аудиозапись has real English speech (16 of 40 pieces), where a fixed
"ru" makes Whisper translate the English into Russian.</p>
<h2>All four files (other jobs were running on the PC)</h2>
<div class="wrap"><table><tr><th>Runtime</th><th>lecture</th><th>2023 call</th><th>interview</th><th>Аудиозапись</th></tr>
{''.join(per_file)}</table></div>
<p class="muted">"= today" counts the doubtful groups where the offer (or no offer) equals whisper.cpp with language auto.
The faster-whisper rows use the language from GigaAM's text.</p>
<h2>Lecture: every offer side by side</h2>
<p>The terms plan 06 counted as right: LLM-агентов, fine-tuning, промпт-инжиниринга, BIM-моделей, промпта, UML-промптинга,
принятие, Prompt Engineering, Tools Calling. Both Whisper runtimes give all nine.</p>
<div class="wrap"><table><tr><th>Doubtful</th>{''.join(f'<th>{esc(t)}</th>' for _, t in LABELS)}</tr>{''.join(lecture)}</table></div>
<h2>Your files: where faster-whisper and whisper.cpp differ (first 60)</h2>
<p class="muted">Neither is clearly better: each gets some right that the other misses (ARP, задержек vs ARPA, sociable); both are noisy on these recordings.</p>
<div class="wrap"><table><tr><th>File</th><th>Line (GigaAM)</th><th>Doubtful</th><th>whisper.cpp</th><th>faster-whisper</th></tr>{''.join(differ)}</table></div>
</body></html>"""
    out.write_text(page, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
