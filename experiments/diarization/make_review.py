"""Make a review page for the kremlin.ru labels: video, speaker names, transcript.

The page plays each event's video straight from kremlin.ru (nothing is
stored locally) and shows the labelled transcript beside it: one block per
turn with the speaker's name, the current word highlighted, a click on a
block jumps there. The big line under the video names who should be
speaking right now, so a wrong label is easy to see and hear. Words with an
unknown speaker ("?") are grey.

With a system result (HYP_DIR with <id>.rttm), every word whose system
speaker (mapped one to one to the true names, as in score_words.py) differs
from the label is underlined in red, so the places where a system fails can
be found by ear.

Usage: python make_review.py KREMLIN_DIR OUT.html [HYP_DIR]
       python make_review.py --system OUT.html HYP_DIR ASR_DIR AUDIO...
The second form is for recordings without true labels (the owner's files): the
names are the system's speakers (SPEAKER_00, ...), every word of the app's
transcript (ASR_DIR/<stem>-transcript.json) gets the speaker that covers it in
HYP_DIR/<stem>.rttm, and the local audio file plays in the page.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from common import read_rttm, speaker_at


def load_words(path):
    """Read <id>.words.tsv as [[start, end, text, speaker]]."""
    words = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        start, end, text, speaker = line.split("\t")
        words.append([round(float(start), 2), round(float(end), 2), text, speaker])
    return words


def mark_errors(words, rttm_path):
    """Add a 0/1 'wrong' flag to every word, from a system RTTM."""
    segments = read_rttm(rttm_path)
    systems = [speaker_at(segments, w[0], w[1]) or "none" for w in words]
    truths = sorted({w[3] for w in words if w[3] != "?"})
    names = sorted(set(systems))
    counts = np.zeros((len(truths), len(names)))
    for word, system in zip(words, systems):
        if word[3] != "?":
            counts[truths.index(word[3]), names.index(system)] += 1
    rows, cols = linear_sum_assignment(-counts)
    mapping = {names[c]: truths[r] for r, c in zip(rows, cols)}
    for word, system in zip(words, systems):
        word.append(int(word[3] != "?" and mapping.get(system) != word[3]))


PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Speaker labels check</title>
<style>
:root { --bg:#f7f7f5; --fg:#1d1d1f; --muted:#8a8a8e; --card:#fff; --line:#e3e3e0; --accent:#2f6fde; --bad:#d93025; }
@media (prefers-color-scheme: dark) { :root { --bg:#161618; --fg:#ececec; --muted:#8d8d92; --card:#202023; --line:#323236; --accent:#6ea0ff; --bad:#ff6b5e; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; }
header { padding:12px 16px; display:flex; gap:12px; align-items:center; flex-wrap:wrap; border-bottom:1px solid var(--line); }
select { font:inherit; padding:4px 8px; }
main { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:16px; padding:16px; height:calc(100vh - 58px); }
@media (max-width:900px) { main { grid-template-columns:1fr; height:auto; } }
.left video { width:100%; background:#000; border-radius:8px; }
#now { font-size:26px; font-weight:600; margin:10px 0 2px; }
#nowsub { color:var(--muted); min-height:3em; }
.hint { color:var(--muted); font-size:13px; margin-top:10px; }
#text { overflow:auto; background:var(--card); border:1px solid var(--line); border-radius:8px; padding:8px 14px; }
.turn { padding:6px 0; border-bottom:1px solid var(--line); cursor:pointer; }
.turn .who { font-weight:600; font-size:13px; }
.turn .t { color:var(--muted); font-size:12px; margin-left:6px; }
.w.unk { color:var(--muted); }
.w.bad { text-decoration:underline wavy var(--bad); }
.w.on { background:var(--accent); color:#fff; border-radius:3px; }
</style></head><body>
<header><b>Speaker labels check</b><select id="pick"></select><span id="info" class="hint"></span></header>
<main>
 <div class="left">
  <video id="v" controls preload="metadata"></video>
  <div id="now">-</div><div id="nowsub"></div>
  <div class="hint">The big line names who should be speaking now (from the kremlin.ru transcript, lined up with GigaAM's word times).
  Grey words: speaker unknown, not scored. Click a block to jump there.</div>
 </div>
 <div id="text"></div>
</main>
<script>
const EVENTS = __EVENTS__;
const COLORS = ["#2f6fde","#d9822b","#1e9e6a","#b84cc4","#c7344a","#0f8fa3","#7a6a1e","#5b5bd6","#a0522d","#3c8c3c","#c2185b","#00796b","#6d4c41","#455a64"];
const v = document.getElementById("v"), text = document.getElementById("text");
const pick = document.getElementById("pick");
let ev = null, spans = [], current = -1;
EVENTS.forEach((e, i) => { const o = document.createElement("option"); o.value = i; o.textContent = e.title; pick.appendChild(o); });
function show(i) {
  ev = EVENTS[i]; v.src = ev.video; text.innerHTML = ""; spans = []; current = -1;
  const names = [...new Set(ev.words.map(w => w[3]).filter(s => s !== "?"))];
  const color = s => s === "?" ? "var(--muted)" : COLORS[names.indexOf(s) % COLORS.length];
  let block = null, last = null;
  ev.words.forEach((w, k) => {
    if (w[3] !== last) {
      block = document.createElement("div"); block.className = "turn";
      const t0 = w[0];
      block.innerHTML = `<span class="who" style="color:${color(w[3])}">${w[3] === "?" ? "?" : w[3]}</span><span class="t">${clock(t0)}</span><br>`;
      block.onclick = () => { v.currentTime = t0; v.play(); };
      text.appendChild(block); last = w[3];
    }
    const s = document.createElement("span");
    s.className = "w" + (w[3] === "?" ? " unk" : "") + (w[4] ? " bad" : "");
    s.textContent = w[2] + " "; block.appendChild(s); spans.push(s);
  });
  document.getElementById("info").textContent = `${names.length} speakers, ${ev.words.length} words` + (ev.score ? `, system: ${ev.score}` : "");
}
function clock(t) { const m = Math.floor(t / 60), s = Math.floor(t % 60); return `${m}:${String(s).padStart(2, "0")}`; }
function find(t) { let lo = 0, hi = ev.words.length - 1, ans = -1; while (lo <= hi) { const mid = (lo + hi) >> 1; if (ev.words[mid][0] <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1; } return ans; }
v.addEventListener("timeupdate", () => {
  const k = find(v.currentTime); if (k === current || k < 0) return;
  if (current >= 0) spans[current].classList.remove("on");
  current = k; spans[k].classList.add("on");
  spans[k].scrollIntoView({ block: "center", behavior: "smooth" });
  const w = ev.words[k];
  document.getElementById("now").textContent = w[3] === "?" ? "? (unknown)" : w[3];
  document.getElementById("nowsub").textContent = ev.words.slice(Math.max(0, k - 6), k + 6).map(x => x[2]).join(" ");
});
pick.onchange = () => show(pick.value);
show(0);
</script></body></html>
"""


def system_events(hyp_dir, asr_dir, audio_paths):
    """Events for recordings without labels: words coloured by the system's speakers."""
    events = []
    for audio_path in audio_paths:
        data = json.loads((asr_dir / f"{audio_path.stem}-transcript.json").read_text(encoding="utf-8"))
        segments = read_rttm(hyp_dir / f"{audio_path.stem}.rttm")
        words = []
        for segment in data["segments"]:
            for word in segment["words"]:
                start, end = float(word["start"]), float(word["end"])
                words.append([round(start, 2), round(end, 2), word["text"], speaker_at(segments, start, end) or "?"])
        speakers = len({w[3] for w in words if w[3] != "?"})
        events.append({"title": f"{audio_path.name} ({speakers} speakers found)",
                       "video": audio_path.resolve().as_uri(), "words": words, "score": ""})
    return events


def main():
    if sys.argv[1] == "--system":
        out_path, hyp_dir, asr_dir = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
        events = system_events(hyp_dir, asr_dir, [Path(p) for p in sys.argv[5:]])
        page = PAGE.replace("__EVENTS__", json.dumps(events, ensure_ascii=False))
        page = page.replace("names who should be speaking now (from the kremlin.ru transcript, lined up with GigaAM's word times)",
                            "names the speaker the system found for the current word (names are the system's own numbers)")
        out_path.write_text(page, encoding="utf-8")
        print(out_path)
        return
    kremlin_dir, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    hyp_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    index = {e["id"]: e for e in json.loads((kremlin_dir / "index.json").read_text(encoding="utf-8"))}
    events = []
    for words_path in sorted((kremlin_dir / "labels").glob("*.words.tsv")):
        file_id = words_path.name[:-len(".words.tsv")]
        entry = index[file_id.lstrip("k")]
        words = load_words(words_path)
        score = ""
        if hyp_dir and (hyp_dir / f"{file_id}.rttm").exists():
            mark_errors(words, hyp_dir / f"{file_id}.rttm")
            known = [w for w in words if w[3] != "?"]
            score = f"{100 * sum(w[4] for w in known) / len(known):.1f}% words wrong"
        video = next(v for v in entry["videos"] if "video_low" in v)
        title = entry["title"].split(" • ")[0]
        events.append({"title": f"{title} ({file_id})", "video": video, "words": words, "score": score})
    out_path.write_text(PAGE.replace("__EVENTS__", json.dumps(events, ensure_ascii=False)), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
