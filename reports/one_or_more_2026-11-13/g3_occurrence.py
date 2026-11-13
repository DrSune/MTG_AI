"""Per checkout: the G3 "occurrence" mutants (gates.mutants: "trigger count: once per event ->
each occurrence" and "each occurrence -> once per event", both critical) of every verified tree of
the 19 sets, card records applied. Diff two outputs to see which verified cards a re-verification
must now kill a new critical mutant on.

    g3_occurrence.py <checkout> <out.json>
    g3_occurrence.py --diff <base.json> <branch.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.argv[1] == "--diff":
    base = json.loads(Path(sys.argv[2]).read_text())
    new = json.loads(Path(sys.argv[3]).read_text())
    for key in sorted(set(base) | set(new)):
        if base.get(key) != new.get(key):
            print(f"{key}: {base.get(key)} -> {new.get(key)}")
    print(f"verified trees with an occurrence mutant: {len(base)} (base) -> {len(new)} (branch)")
    sys.exit(0)

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards"):
    sys.path.insert(0, str(p))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

import gates

from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()
out = {}
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except (StateCorruptionError, ValueError):
            continue
        if not card_records.is_verified(res, records.get(oid)):
            continue
        ops = sorted(f"{op} @ {where}" for op, where, _m in gates.mutants(res.card) if "occurrence" in op)
        if ops:
            out[f"{code} {rc.identity.name}"] = ops
Path(sys.argv[2]).write_text(json.dumps(out, indent=1, sort_keys=True))
print(len(out), "verified trees with an occurrence mutant", file=sys.stderr)
