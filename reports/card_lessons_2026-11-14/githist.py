"""History of every card record in git: re-maps (ir changed), re-stamps, stamps dropped, first
stamp per day. Uses `git -C <worktree>` only."""
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict

WT = sys.argv[1]


def git(*a):
    return subprocess.run(["git", "-C", WT, *a], capture_output=True, text=True, check=True).stdout


log = git("log", "--reverse", "--format=@@%H %ad %s", "--date=format:%Y-%m-%d %H:%M", "--name-status",
          "--", "MTG_bot/data/cards")
commits = []
cur = None
for line in log.splitlines():
    if line.startswith("@@"):
        h, d, t, *s = line[2:].split(" ")
        cur = {"h": h, "date": d, "time": t, "subj": " ".join(s), "files": []}
        commits.append(cur)
    elif line.strip() and cur is not None:
        parts = line.split("\t")
        cur["files"].append((parts[0], parts[-1]))


def h(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12] if obj is not None else None


state = {}  # path -> (ir hash, verified tree_sha, verified date)
ev = Counter()
remaps = []
restamp_same_tree = []
dropped = []
first_stamp_day = Counter()
stamps_per_commit = []
for c in commits:
    n_new_stamps = 0
    for status, path in c["files"]:
        if not path.endswith(".json"):
            continue
        if status.startswith("D"):
            ev["deleted"] += 1
            state.pop(path, None)
            continue
        try:
            rec = json.loads(git("show", f"{c['h']}:{path}"))
        except Exception:  # noqa: BLE001
            continue
        irh = h(rec.get("ir"))
        ver = rec.get("verified") or {}
        vt = ver.get("tree_sha")
        prev = state.get(path)
        if prev is None:
            ev["created"] += 1
            if vt:
                first_stamp_day[c["date"]] += 1
                n_new_stamps += 1
        else:
            pir, pvt, pdate, pna = prev
            if pir is not None and irh != pir:
                ev["ir_changed"] += 1
                remaps.append((c["date"], c["h"][:8], rec.get("set"), rec.get("name"), c["subj"][:90]))
            if pir is None and irh is not None and pna:
                ev["needs_atom_to_ir"] += 1
            if vt and not pvt:
                ev["stamped"] += 1
                first_stamp_day[c["date"]] += 1
                n_new_stamps += 1
            elif vt and pvt and vt != pvt:
                ev["restamped_new_tree"] += 1
            elif vt and pvt and vt == pvt and ver.get("date") != pdate:
                ev["restamped_same_tree"] += 1
                restamp_same_tree.append((c["date"], rec.get("set"), rec.get("name")))
            elif pvt and not vt:
                ev["stamp_dropped"] += 1
                dropped.append((c["date"], rec.get("set"), rec.get("name"), c["subj"][:80]))
        state[path] = (irh, vt, ver.get("date"), "needs_atom" in rec)
    stamps_per_commit.append((c["date"], c["time"], c["h"][:8], n_new_stamps, c["subj"][:70]))

print("events:", dict(ev))
print("first stamps per day:", dict(sorted(first_stamp_day.items())))
print("re-maps (ir changed):", len(remaps))
for r in remaps:
    print("  ", r)
print("stamps dropped:", len(dropped))
for r in dropped:
    print("  ", r)
print("re-stamped, same tree:", len(restamp_same_tree), Counter(d for d, *_ in restamp_same_tree))
per_set = Counter()
na = Counter()
for path, (irh, vt, d, isna) in state.items():
    s = path.split("/")[-2]
    per_set[(s, "verified" if vt else ("needs-atom" if isna else ("mapped" if irh else "other")))] += 1
print("current records:", dict(sorted(per_set.items())))
