"""Mine every blind verification round whose files survive: key (real vs planted, the plant's
operator), verdicts (OK/WRONG per clause), apply logs (VERIFIED / NOT VERIFIED and why).
Writes rows to argv[1] (JSON) and prints a summary."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

S = Path("/tmp/claude-1000/-home-sune/2e18468a-eed7-47b5-a69b-d15b1f5fd0e8/scratchpad")
RUNS = Path("/home/sune/Desktop/MTG_AI/runs")


def load_index_round(keydir: Path) -> dict:
    idx = json.loads((keydir / "index.json").read_text())
    out = {}
    for pid, v in idx.items():
        op = None
        if v.get("planted"):
            f = keydir / f"{pid}.json"
            if f.exists():
                k = json.loads(f.read_text())
                op = f"{k.get('planted')} @ {k.get('where')}"
            else:
                op = "?"
        out[pid] = {"set": v["set"], "card": v["card"], "planted": op}
    return out


def load_wave_key(kd: Path) -> dict:
    key = json.loads((kd / "key.json").read_text())
    out = {}
    for pid, v in key.items():
        op = None
        if v.get("planted"):
            f = kd / "plants" / f"{pid}.json"
            if f.exists():
                k = json.loads(f.read_text())
                op = f"{k.get('planted')} @ {k.get('where')}"
            else:
                op = "?"
        out[pid] = {"set": v["set"], "card": v["card"], "planted": op, "made": v.get("made", True)}
    return out


def parse_apply(log: Path) -> dict:
    res = {}
    cur = None
    if not log.exists():
        return res
    for line in log.read_text(errors="replace").splitlines():
        if "shape-gap" in line:
            continue
        m = re.match(r"== (.*) \((P[0-9a-f]+)\)", line) or re.match(r"== ([A-Z]\d\d) \S+ (.*)", line)
        if m:
            if line.startswith("== ") and re.match(r"== [A-Z]\d\d ", line):
                pid, card = m.group(1), m.group(2)
            else:
                card, pid = m.group(1), m.group(2)
            cur = pid
            res[cur] = {"card": card, "lines": []}
            continue
        if cur:
            res[cur]["lines"].append(line.strip())
    return res


rounds = []
# 2026-11-05/06 rounds: hashed packet ids
for name, keydir, verd, logs in [
    ("m20_mapped_r1", S / "round_m20_verify/private/key", S / "round_m20_verify/verdicts", [S / "round_m20_verify/apply.log"]),
    ("m20_compiled_r2", S / "round_m20_verify2/private/key", S / "round_m20_verify2/verdicts", [S / "round_m20_verify2/apply.log"]),
    ("fdn_compiled_r1", S / "round_fdn_verify1/private/key", S / "round_fdn_verify1/verdicts", [S / "round_fdn_verify1/apply.log"]),
    ("m20_r3", S / "round_r3/private/key_m20", S / "round_r3/verdicts", [S / "round_r3/apply_m20.log"]),
    ("fdn_r2", S / "round_r3/private/key_fdn", S / "round_r3/verdicts", [S / "round_r3/apply_fdn.log"]),
]:
    rounds.append((name, load_index_round(keydir), lambda pid, verd=verd: verd / f"{pid}.json", logs))
# 2026-11-12/13 waves: batch ids
for name, kd, wave in [("wave1", "verify_keys", "verify_wave1"), ("wave1b", "verify_keys_1b", "verify_wave1b"),
                       ("wave1c", "verify_keys_1c", "verify_wave1c"), ("wave1d", "verify_keys_1d", "verify_wave1d"),
                       ("wave1e", "verify_keys_1e", "verify_wave1e")]:
    rounds.append((name, load_wave_key(S / kd),
                   lambda pid, wave=wave: RUNS / wave / "verdicts" / pid[0] / f"{pid}.json",
                   [S / kd / "verify_A.log"]))

rows = []
for name, key, vpath, logs in rounds:
    applied = {}
    for log in logs:
        applied.update(parse_apply(log))
    for pid, k in key.items():
        vp = vpath(pid)
        if not vp.exists():
            rows.append({"round": name, "pid": pid, **k, "verdict": None, "wrong": [], "status": {}, "apply": None})
            continue
        v = json.loads(vp.read_text())
        st = Counter(c.get("status") for c in v.get("clauses", []))
        wrong = [{"clause": c.get("clause", ""), "issue": c.get("issue", "")} for c in v.get("clauses", [])
                 if c.get("status") == "WRONG"]
        ap = applied.get(pid)
        rows.append({"round": name, "pid": pid, **k, "verdict": v.get("verdict"), "wrong": wrong,
                     "status": dict(st), "packs": len(v.get("packs", [])),
                     "apply": ap["lines"] if ap else None})
json.dump(rows, open(sys.argv[1], "w"), indent=1)

by = defaultdict(Counter)
for r in rows:
    kind = "plant" if r["planted"] else "real"
    by[r["round"]][f"{kind}:{r['verdict']}"] += 1
    if r["apply"] is not None and not r["planted"]:
        ok = any(l.startswith("VERIFIED") for l in r["apply"])
        by[r["round"]]["applied_verified" if ok else "applied_not_verified"] += 1
        for l in r["apply"]:
            m = re.match(r"(G\d(?:/G\d)?): (.*)", l)
            if m:
                g = m.group(1)
                if g == "G3":
                    op = re.search(r"check: (.*?) at ", l)
                    by[r["round"]][f"G3 survivor: {op.group(1) if op else l}"] += 1
                else:
                    by[r["round"]][f"{g} fail"] += 1
for name, c in by.items():
    print(name, dict(sorted(c.items())))
missed = [r for r in rows if r["planted"] and r["verdict"] != "WRONG"]
print("plants missed:", len(missed), [(r["round"], r["card"], r["verdict"]) for r in missed])
print("plant ops:", Counter(r["planted"].split(" @ ")[0] for r in rows if r["planted"]))
