"""Compare whole transcripts of faster-whisper and whisper.cpp on the CPU (plan 08 C4).

    python -I experiments/cpu_asr/main_compare.py build/cpu-asr-test [--notes NOTES.html]

Reads DATA/main/{wcpp,fw,rnnt}/NAME.json (written by main_text.py) and writes
DATA/main-compare.json and the results page DATA/main-results.html (local: it quotes the
owner's recordings). There is no reference text, so GigaAM RNNT stands in as a third
reading: "differ" counts words, not errors. Measured per file and Whisper engine:

- time, load time, RAM after loading and the peak;
- words differing from RNNT and between the two Whispers (digits apart: "2023" against
  "две тысячи двадцать третьем" is not a reading difference);
- the lecture's English terms, counted in each transcript;
- loops (an n-gram repeated in a row), lines with too many words per second, phrases Whisper
  is known to invent ("Субтитры ...", "Продолжение следует");
- text where RNNT heard nothing near (invented?) and RNNT text Whisper left out (skipped?);
- word times against RNNT's for the words both have;
- the confidence scale WHISPER_SCALE: per band, how many words and how many of them RNNT
  does not have at that place, and the share of words the window would mark.
"""

import argparse
import bisect
import difflib
import html
import json
from pathlib import Path
import re
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gigaam_app.whisper_model import WHISPER_SCALE  # noqa: E402

FILES = (("lecture", "Lecture, 455 s (English terms)"), ("call2023", "2023 call, 23 min"),
         ("interview", "Interview, 83 min"), ("audiozapis", "Аудиозапись, 123 min (some English)"))
ENGINES = (("wcpp", "whisper.cpp q5_0"), ("wcppg", "whisper.cpp q5_0 on the GPU"),
           ("fwm", "faster-whisper int8, one pass"), ("fw", "faster-whisper int8, two passes"))
LABELS = dict(ENGINES)
# Readings compared word by word: (base, other). wcpp-fwm is what C5 would change; on the long
# files whisper.cpp ran on the GPU only (wcppg-fwm), wcpp-wcppg shows what that changes.
PAIRS = (("wcpp", "fwm"), ("wcppg", "fwm"), ("wcpp", "fw"), ("fw", "fwm"), ("wcpp", "wcppg"))
BANDS = (0.0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.97, 1.01)
# The window's two marks (Settings.doubt_strong / doubt_light).
MARK_STRONG, MARK_LIGHT = 0.80, 0.97
# English terms of the lecture (plan 06 A5 and the session 14 term list), as plain text keys.
TERMS = ("llm", "fine tuning", "finetuning", "prompt engineering", "tools calling", "tool calling",
         "deepseek", "lean", "boilerplate", "bim", "uml", "step", "reasoning", "триз", "промпт")
# Text Whisper is known to invent on silence or noise.
INVENTED_PHRASES = ("субтитр", "продолжение следует", "спасибо за просмотр", "подписывайтесь",
                    "dimatorzok", "редактор", "корректор", "thank you for watching", "amara")
WORDS_PER_SECOND_MAX = 6.0
NEAR_SECONDS = 1.5  # a word counts as heard by the other reading when it has a word this near


def key(text):
    """A word without case, punctuation and ё (as experiments/confidence/word_confidence.key)."""
    return re.sub(r"[^\w]", "", text.lower().replace("ё", "е"))


def split_keys(words):
    """[(key, word index)] with a hyphenated word split in its parts ("LLM-агентов" -> llm,
    агентов), so the readings line up word by word; empty keys are left out."""
    keys = []
    for index, word in enumerate(words):
        for part in re.split("[-\u2010\u2013\u2014/]", word[2]):
            part_key = key(part)
            if part_key:
                keys.append((part_key, index))
    return keys


def load(data_dir, engine, name):
    path = Path(data_dir) / "main" / engine / f"{name}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    data["words"] = [word for segment in data["segments"] for word in segment["words"]]
    return data


def differences(mine, theirs):
    """Word differences between two readings: (changed words, compared words, [(opcode, my
    key range, their key range)]). A change where either side holds a digit is not counted."""
    a, b = [k for k, _ in mine], [k for k, _ in theirs]
    changed, groups = 0, []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if any(ch.isdigit() for word in a[i1:i2] + b[j1:j2] for ch in word):
            continue
        changed += max(i2 - i1, j2 - j1)
        groups.append((tag, i1, i2, j1, j2))
    return changed, max(len(a), len(b)), groups


def matched_pairs(mine, theirs):
    """Pairs of word indexes that difflib lines up as equal."""
    a, b = [k for k, _ in mine], [k for k, _ in theirs]
    pairs = set()
    for block in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for offset in range(block.size):
            pairs.add((mine[block.a + offset][1], theirs[block.b + offset][1]))
    return pairs


def loops(data):
    """Lines with an n-gram (1-4 words) repeated in a row (3 times for n >= 2, 4 for single
    words), with too many words per second, or with a phrase Whisper is known to invent."""
    found = []
    for segment in data["segments"]:
        keys = [key(w[2]) for w in segment["words"] if key(w[2])]
        reasons = []
        for n in range(1, 5):
            need = 4 if n == 1 else 3
            for start in range(0, max(0, len(keys) - n * need + 1)):
                gram = keys[start:start + n]
                repeats = 1
                while keys[start + repeats * n:start + (repeats + 1) * n] == gram:
                    repeats += 1
                if repeats >= need:
                    reasons.append(f'"{" ".join(gram)}" x{repeats}')
                    break
            if reasons:
                break
        seconds = max(0.5, segment["end"] - segment["start"])
        if len(keys) / seconds > WORDS_PER_SECOND_MAX and len(keys) >= 8:
            reasons.append(f"{len(keys) / seconds:.1f} words/s")
        low = segment["text"].lower()
        reasons += [f'"{phrase}"' for phrase in INVENTED_PHRASES if phrase in low]
        if reasons:
            found.append({"start": segment["start"], "text": segment["text"], "why": ", ".join(reasons)})
    return found


def lonely_runs(words, other_words, least=3):
    """Runs of at least `least` words with no word of the other reading within NEAR_SECONDS:
    [(start, end, text)]."""
    starts = sorted(w[0] for w in other_words)
    ends = sorted(w[1] for w in other_words)

    def heard(word):
        index = bisect.bisect_left(starts, word[0] - NEAR_SECONDS)
        if index < len(starts) and starts[index] <= word[1] + NEAR_SECONDS:
            return True
        index = bisect.bisect_left(ends, word[0] - NEAR_SECONDS)
        return index < len(ends) and ends[index] <= word[1] + NEAR_SECONDS

    runs, current = [], []
    for word in words:
        if not key(word[2]):
            continue
        if heard(word):
            if len(current) >= least:
                runs.append(current)
            current = []
        else:
            current.append(word)
    if len(current) >= least:
        runs.append(current)
    return [(run[0][0], run[-1][1], " ".join(w[2] for w in run)) for run in runs]


def time_gaps(data, rnnt, pairs):
    """Start-time differences (s) against RNNT for the words both have, plus odd durations."""
    gaps = [abs(data["words"][i][0] - rnnt["words"][j][0]) for i, j in pairs]
    durations = [w[1] - w[0] for w in data["words"]]
    if not gaps:
        return {}
    gaps.sort()
    return {"words": len(gaps), "median": round(statistics.median(gaps), 3),
            "p90": round(gaps[int(0.9 * (len(gaps) - 1))], 3),
            "over_half_second": round(100 * sum(g > 0.5 for g in gaps) / len(gaps), 1),
            "zero_length": sum(d <= 0.0 for d in durations), "over_3s": sum(d > 3.0 for d in durations)}


def raw_of(confidence):
    """The raw Whisper probability that WHISPER_SCALE maps to `confidence` (its inverse)."""
    for (low, low_value), (high, high_value) in zip(WHISPER_SCALE, WHISPER_SCALE[1:]):
        if confidence <= high_value:
            return low + (confidence - low_value) * (high - low) / max(1e-9, high_value - low_value)
    return 1.0


def scale_table(data, rnnt_pairs):
    """Per confidence band: words, share, share RNNT does not have at that place."""
    heard = {i for i, _ in rnnt_pairs}
    confidences = [1.0 if w[3] is None else w[3] for w in data["words"]]
    rows = []
    for low, high in zip(BANDS, BANDS[1:]):
        inside = [i for i, c in enumerate(confidences) if low <= c < high]
        disputed = sum(1 for i in inside if i not in heard)
        rows.append({"band": f"{low:.2f}-{min(high, 1.0):.2f}", "words": len(inside),
                     "share": round(100 * len(inside) / max(1, len(confidences)), 1),
                     "disputed": round(100 * disputed / max(1, len(inside)), 1)})
    marked = {"strong": round(100 * sum(c < MARK_STRONG for c in confidences) / max(1, len(confidences)), 1),
              "light": round(100 * sum(c < MARK_LIGHT for c in confidences) / max(1, len(confidences)), 1)}
    return rows, marked, confidences


def raw_threshold_for_share(confidences, share):
    """The raw probability below which `share` percent of the words fall (to match another
    reading's share of marked words)."""
    raws = sorted(raw_of(c) for c in confidences)
    if not raws:
        return None
    return round(raws[min(len(raws) - 1, int(share / 100 * len(raws)))], 3)


def term_counts(data):
    text = " ".join(key(w[2]) if "-" not in w[2] else " ".join(key(p) for p in w[2].split("-"))
                    for w in data["words"])
    text = f" {text} "
    return {term: len(re.findall(rf"(?<=\s){re.escape(term)}", text)) for term in TERMS}


def context_text(words, index_from, index_to, around=4):
    before = " ".join(w[2] for w in words[max(0, index_from - around):index_from])
    inside = " ".join(w[2] for w in words[index_from:index_to])
    after = " ".join(w[2] for w in words[index_to:index_to + around])
    return before, inside, after


def compare_file(data_dir, name):
    readings = {engine: load(data_dir, engine, name) for engine in ("wcpp", "wcppg", "fw", "fwm", "rnnt")}
    rnnt = readings["rnnt"]
    result = {"name": name, "engines": {}}
    if rnnt is None:
        return result
    rnnt_keys = split_keys(rnnt["words"])
    result["rnnt"] = {"words": len(rnnt["words"]), "seconds": rnnt["seconds"],
                      "marked": scale_table(rnnt, set())[1]}
    for engine, _ in ENGINES:
        data = readings[engine]
        if data is None:
            continue
        keys = split_keys(data["words"])
        changed, compared, _ = differences(keys, rnnt_keys)
        pairs = matched_pairs(keys, rnnt_keys)
        rows, marked, confidences = scale_table(data, pairs)
        languages = {}
        for language in data["chunk_languages"]:
            languages[language] = languages.get(language, 0) + 1
        result["engines"][engine] = {
            "seconds": data["seconds"], "load_seconds": data["load_seconds"], "audio_seconds": data["audio_seconds"],
            "speed": round(data["audio_seconds"] / max(1e-9, data["seconds"]), 2),
            "ram_loaded_mb": data["ram_loaded_mb"], "ram_peak_mb": data["ram_peak_mb"],
            "words": len(data["words"]), "lines": len(data["segments"]), "languages": languages,
            "differ_rnnt": round(100 * changed / max(1, compared), 2),
            "loops": loops(data), "invented": lonely_runs(data["words"], rnnt["words"]),
            "skipped": lonely_runs(rnnt["words"], data["words"]),
            "times": time_gaps(data, rnnt, pairs), "scale": rows, "marked": marked,
            "raw_for_rnnt_light": raw_threshold_for_share(confidences, result["rnnt"]["marked"]["light"]),
            "raw_for_rnnt_strong": raw_threshold_for_share(confidences, result["rnnt"]["marked"]["strong"]),
            "terms": term_counts(data) if name == "lecture" else None,
        }
    result["between"] = {}
    for first, second in PAIRS:
        if readings[first] and readings[second]:
            result["between"][f"{first}-{second}"] = between(readings[first]["words"], readings[second]["words"])
    return result


def between(base_words, other_words):
    """Where two Whisper readings differ: share of words, places, and each place with the
    base reading's words around it."""
    base_keys, other_keys = split_keys(base_words), split_keys(other_words)
    changed, compared, groups = differences(other_keys, base_keys)
    listed = []
    for tag, i1, i2, j1, j2 in groups:
        other_from = other_keys[i1][1] if i1 < len(other_keys) else len(other_words)
        other_to = other_keys[i2 - 1][1] + 1 if i2 > i1 else other_from
        base_from = base_keys[j1][1] if j1 < len(base_keys) else len(base_words)
        base_to = base_keys[j2 - 1][1] + 1 if j2 > j1 else base_from
        at = base_words[min(base_from, len(base_words) - 1)][0] if base_words else 0.0
        before, base_text, after = context_text(base_words, base_from, base_to)
        listed.append({"at": at, "before": before, "base": base_text,
                       "other": " ".join(w[2] for w in other_words[other_from:other_to]),
                       "after": after, "size": max(i2 - i1, j2 - j1)})
    return {"differ": round(100 * changed / max(1, compared), 2), "groups": len(groups),
            "changed_words": changed, "list": listed}


def esc(text):
    return html.escape(str(text))


def clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02d}"


def page(results, notes):
    def cell(value, cls="num"):
        return f"<td class={cls}>{esc(value)}</td>"

    summary = []
    for name, title in FILES:
        file_result = results.get(name, {})
        for engine, label in ENGINES:
            e = file_result.get("engines", {}).get(engine)
            if not e:
                continue
            times = e["times"]
            summary.append(
                "<tr>" + cell(title, "") + cell(label, "") +
                cell(f"{e['seconds']:.0f} s") + cell(f"{e['speed']:.2f}x") + cell(e["ram_loaded_mb"]) + cell(e["ram_peak_mb"]) +
                cell(f"{e['differ_rnnt']:.1f}%") + cell(len(e["loops"])) + cell(len(e["invented"])) + cell(len(e["skipped"])) +
                cell(times.get("median", "")) + cell(f"{e['marked']['light']}% / {e['marked']['strong']}%") + "</tr>")
    between_rows = []
    for name, title in FILES:
        for pair, b in results.get(name, {}).get("between", {}).items():
            first, second = pair.split("-")
            between_rows.append("<tr>" + cell(title, "") + cell(f"{LABELS[first]} / {LABELS[second]}", "") +
                                cell(f"{b['differ']:.1f}%") + cell(b["groups"]) + "</tr>")
    terms = []
    lecture = results.get("lecture", {}).get("engines", {})
    present = [(engine, label) for engine, label in ENGINES if lecture.get(engine)]
    term_heads = "".join(f"<th class=num>{esc(label)}</th>" for _, label in present)
    for term in TERMS:
        terms.append("<tr>" + cell(term, "") + "".join(cell(lecture[engine]["terms"][term]) for engine, _ in present) + "</tr>")
    scale = []
    for name, title in FILES:
        for engine, label in ENGINES:
            e = results.get(name, {}).get("engines", {}).get(engine)
            if not e:
                continue
            bands = "".join(f"<td class=num>{r['share']}% <span class=muted>({r['disputed']}%)</span></td>" for r in e["scale"])
            scale.append("<tr>" + cell(title, "") + cell(label, "") + bands +
                         cell(f"{e['raw_for_rnnt_light']} / {e['raw_for_rnnt_strong']}") + "</tr>")
    problems = []
    for name, title in FILES:
        for engine, label in ENGINES:
            e = results.get(name, {}).get("engines", {}).get(engine)
            if not e:
                continue
            for item in e["loops"]:
                problems.append(f"<tr><td>{esc(title)}</td><td>{esc(label)}</td><td>loop / odd</td><td class=num>{clock(item['start'])}</td>"
                                f"<td>{esc(item['why'])}: {esc(item['text'][:300])}</td></tr>")
            for start, _, text in e["invented"][:25]:
                problems.append(f"<tr><td>{esc(title)}</td><td>{esc(label)}</td><td>RNNT heard nothing</td><td class=num>{clock(start)}</td>"
                                f"<td>{esc(text[:300])}</td></tr>")
            for start, _, text in e["skipped"][:25]:
                problems.append(f"<tr><td>{esc(title)}</td><td>{esc(label)}</td><td>left out (RNNT has it)</td><td class=num>{clock(start)}</td>"
                                f"<td>{esc(text[:300])}</td></tr>")
    diffs = []
    for name, title in FILES:
        pairs = results.get(name, {}).get("between", {})
        pair = next((p for p in ("wcpp-fwm", "wcppg-fwm", "wcpp-fw") if p in pairs), None)
        if pair is None:
            continue
        b, (first, second) = pairs[pair], pair.split("-")
        shown = b["list"] if name == "lecture" else b["list"][:40]
        diffs.append(f"<h3>{esc(title)}: {b['groups']} places{'' if name == 'lecture' else ', the first 40'}</h3>"
                     f"<div class=wrap><table><tr><th>Time</th><th>Before</th><th>{esc(LABELS[first])}</th>"
                     f"<th>{esc(LABELS[second])}</th><th>After</th></tr>")
        for item in shown:
            diffs.append(f"<tr><td class=num>{clock(item['at'])}</td><td class=muted>{esc(item['before'])}</td>"
                         f"<td><b>{esc(item['base']) or '<i>-</i>'}</b></td><td><b>{esc(item['other']) or '<i>-</i>'}</b></td>"
                         f"<td class=muted>{esc(item['after'])}</td></tr>")
        diffs.append("</table></div>")
    band_heads = "".join(f"<th class=num>{low:.2f}-{min(high, 1.0):.2f}</th>" for low, high in zip(BANDS, BANDS[1:]))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Whisper Main Text CPU</title><style>
:root {{ --bg:#fff; --fg:#1d1d1f; --muted:#6b6b70; --line:#e2e2e6; --head:#f4f4f6; --accent:#2b59c3; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#161618; --fg:#ececf0; --muted:#9a9aa2; --line:#33333a; --head:#222227; --accent:#8fb0ff; }} }}
:root[data-theme="dark"] {{ --bg:#161618; --fg:#ececf0; --muted:#9a9aa2; --line:#33333a; --head:#222227; --accent:#8fb0ff; }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:0 auto; max-width:1100px; padding:16px; }}
h1 {{ font-size:22px; }} h2 {{ font-size:18px; margin-top:32px; }} h3 {{ font-size:15px; }}
.wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
th, td {{ border-bottom:1px solid var(--line); padding:5px 8px; text-align:left; vertical-align:top; }}
th {{ background:var(--head); font-weight:600; }} .num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
.muted {{ color:var(--muted); }} .notes {{ border-left:3px solid var(--accent); padding:4px 14px; }}
</style></head><body>
<h1>faster-whisper as the main model on the CPU (plan 08 C4)</h1>
<p class=muted>Whole transcripts of the four test files, made as the app makes the main text: the same VAD chunks, greedy,
language detected per chunk (Settings "auto"), 8 threads, one job at a time on the PC. No reference text exists, so GigaAM RNNT
is the third reading: "differ" counts words, not errors.</p>
<div class=notes>{notes}</div>
<h2>Per file</h2>
<div class=wrap><table><tr><th>File</th><th>Engine</th><th class=num>Time</th><th class=num>Speed (audio / time)</th>
<th class=num>RAM loaded MB</th><th class=num>RAM peak MB</th><th class=num>Differ from RNNT</th><th class=num>Loops / odd lines</th>
<th class=num>Runs RNNT did not hear</th><th class=num>Runs left out</th><th class=num>Word start vs RNNT (median s)</th>
<th class=num>Marked light / strong</th></tr>{''.join(summary)}</table></div>
<p class=muted>RAM is the whole process, the decoded audio included (about 28 MB per minute of audio). "Runs": three or more
words in a row with no word of the other reading within {NEAR_SECONDS} s. Marked: words below {MARK_LIGHT} / {MARK_STRONG}
after WHISPER_SCALE.</p>
<h2>The Whisper readings against each other</h2>
<div class=wrap><table><tr><th>File</th><th>Readings</th><th class=num>Words that differ</th><th class=num>Places</th></tr>{''.join(between_rows)}</table></div>
<h2>Lecture terms (times each appears)</h2>
<div class=wrap><table><tr><th>Term</th>{term_heads}</tr>{''.join(terms)}</table></div>
<h2>Confidence scale WHISPER_SCALE</h2>
<p class=muted>Share of words in each band after the scale, and in brackets how many of them RNNT does not have at that place.
Last column: the raw probability below which the same share of words would fall as RNNT marks (light / strong); today's scale
puts 0.70 and 0.50 there.</p>
<div class=wrap><table><tr><th>File</th><th>Engine</th>{band_heads}<th class=num>Raw for RNNT's share</th></tr>{''.join(scale)}</table></div>
<h2>Loops, invented and left-out text</h2>
<div class=wrap><table><tr><th>File</th><th>Engine</th><th>What</th><th class=num>Time</th><th>Text</th></tr>{''.join(problems)}</table></div>
<h2>Where the two Whispers differ</h2>
{''.join(diffs)}
</body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir")
    parser.add_argument("--notes", help="an HTML snippet with the conclusions, put at the top of the page")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = {name: compare_file(args.data_dir, name) for name, _ in FILES}
    data_dir = Path(args.data_dir)
    (data_dir / "main-compare.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    notes = Path(args.notes).read_text(encoding="utf-8") if args.notes else "<p>Conclusions not written yet.</p>"
    (data_dir / "main-results.html").write_text(page(results, notes), encoding="utf-8")
    for name, _ in FILES:
        for engine, label in ENGINES:
            e = results[name].get("engines", {}).get(engine)
            if e:
                print(f"{name} {label}: {e['seconds']:.0f} s ({e['speed']}x), RAM {e['ram_loaded_mb']}/{e['ram_peak_mb']} MB, "
                      f"differ RNNT {e['differ_rnnt']}%, loops {len(e['loops'])}, invented {len(e['invented'])}, "
                      f"skipped {len(e['skipped'])}, times {e['times']}, marked {e['marked']}, "
                      f"raw for RNNT share {e['raw_for_rnnt_light']}/{e['raw_for_rnnt_strong']}, languages {e['languages']}")
        for pair, b in results[name].get("between", {}).items():
            print(f"{name} {pair}: {b['differ']}% words, {b['groups']} places")
    print(data_dir / "main-results.html")


if __name__ == "__main__":
    main()
