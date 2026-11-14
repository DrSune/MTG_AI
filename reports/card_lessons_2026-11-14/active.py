"""Per card agent: active minutes (gaps between its messages of at most 15 min; longer gaps are
the waits between follow-ups), API turns and output tokens; grouped by phase."""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

root = Path(sys.argv[1])


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


PHASES = [
    ("map", ("Map M20",)),
    ("remap", ("Re-map", "Remap")),
    ("verify_opus", ("Verify M20", "Verify FDN")),
    ("verify_sonnet", ("Blind G2",)),
    ("g3_packs", ("Kill 12", "G3 kill packs")),
    ("g3_rules", ("G3 dead-role", "Classify")),
    ("gate", ("Gate round",)),
    ("fix", ("Fix per-object", "Fix castable", "Fix defender", "Fix two faults", "Wave 2", "Wave 3:",
             "Engine wave", "Scenario runner reach", "Add turn-history", "Add the next missing",
             "Fix wave 2")),
    ("census", ("census",)),
    ("redteam", ("Red-team wave-2",)),
]
agg = defaultdict(lambda: [0, 0.0, 0, 0])
for meta in sorted(root.glob("*.meta.json")):
    desc = json.loads(meta.read_text()).get("description") or ""
    phase = next((p for p, keys in PHASES if any(k in desc for k in keys)), None)
    if phase is None:
        continue
    prev = None
    active = 0.0
    seen = set()
    out_tok = 0
    with open(meta.with_name(meta.name.replace(".meta.json", ".jsonl")), encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("timestamp")
            if t:
                if prev is not None:
                    gap = (ts(t) - ts(prev)).total_seconds() / 60
                    if 0 < gap <= 15:
                        active += gap
                prev = t
            if d.get("type") == "assistant":
                m = d.get("message") or {}
                if m.get("id") not in seen:
                    seen.add(m.get("id"))
                    out_tok += (m.get("usage") or {}).get("output_tokens", 0) or 0
    a = agg[phase]
    a[0] += 1
    a[1] += active
    a[3] += out_tok
    print(f"{phase:14} {desc[:50]:50} active {active:6.1f} min  out {out_tok:7}")
print()
for p, (n, act, _t, out) in agg.items():
    print(f"{p:14} agents {n:3}  active {act:7.1f} min  output tokens {out:9}")
