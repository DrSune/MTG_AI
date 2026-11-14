"""Run tools/cards/lints.py over every card of the 19 sets (records applied). Verified-card hits
are false-positive candidates; the rest are leads. Run from the worktree root."""
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path.cwd()
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]
import corpus  # noqa: E402
import lints  # noqa: E402

from MTG_bot.core.compiler import card_records  # noqa: E402

sets = sys.argv[1].split(",") if len(sys.argv) > 1 else corpus.SETS
ver_hits = []
other = defaultdict(list)
n_ver = n_other = 0
for code in sets:
    sc = corpus.compile_set(code)
    for oid, raw in sc.raw.items():
        if raw.is_token or raw.is_emblem:
            continue
        res = sc.results.get(oid)
        if res is None:
            continue
        rec = sc.records.get(oid)
        ver = card_records.is_verified(res, rec)
        try:
            found = lints.lint(raw, res.card)
        except Exception as exc:  # noqa: BLE001
            found = [f"CRASH {type(exc).__name__}: {exc}"]
        if ver:
            n_ver += 1
            for f in found:
                ver_hits.append((code, raw.identity.name, f))
        else:
            n_other += 1
            for f in found:
                other[f.split(":")[0]].append((code, raw.identity.name, f, bool(res.unparsed)))
print("verified cards linted:", n_ver, "hits:", len(ver_hits))
for h in ver_hits:
    print("  VERIFIED HIT", h[0], "|", h[1], "|", h[2][:260])
print("unverified cards linted:", n_other)
for k, v in other.items():
    print(f"== {k}: {len(v)} findings on {len({(a, b) for a, b, *_ in v})} cards "
          f"({sum(1 for *_, u in v if not u)} on fully compiled)")
    for row in [r for r in v if not r[3]] + v[:int(sys.argv[2]) if len(sys.argv) > 2 else 12]:
        print("   ", row[0], "|", row[1], "|", "partial" if row[3] else "whole", "|", row[2][:230])
