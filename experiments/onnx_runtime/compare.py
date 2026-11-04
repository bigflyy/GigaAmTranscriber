import json, sys, difflib
a = json.load(open(sys.argv[1], encoding="utf-8")); b = json.load(open(sys.argv[2], encoding="utf-8"))
print("chunks", len(a), len(b))
bd = [(x["b"], y["b"]) for x, y in zip(a, b) if any(abs(p - q) > 0.051 for p, q in zip(x["b"], y["b"]))]
print("boundary mismatches:", len(bd), bd[:3])
ta = " ".join(x["t"] for x in a).split(); tb = " ".join(x["t"] for x in b).split()
sm = difflib.SequenceMatcher(a=ta, b=tb, autojunk=False)
diff = [(ta[i1:i2], tb[j1:j2]) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]
print(f"words {len(ta)} vs {len(tb)}, word diff ops: {len(diff)}, similarity {sm.ratio():.4f}")
for d in diff[:8]: print("  ", d)
