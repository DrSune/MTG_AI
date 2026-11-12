"""The G1 probe trace (tools/cards/probe.py) of every verified card of M21, M20 and FDN, and of the
three cards the fixes are for, under the code at ROOT: one line per card with the trace's sha and
engine-error count. Two runs, base and fixed engine, are compared line by line.

    .venv/bin/python reports/engine_faults_2026-11-12/probe_traces.py ROOT OUT.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
sys.path.insert(1, str(root / "tools" / "cards"))

from probe import Probe

from MTG_bot.core.executor.games import compile_supply

assert Path(sys.modules["MTG_bot"].__file__).resolve().is_relative_to(root), "wrong engine on the path"
EXTRA = {"M20": ("Blightbeetle", "Cavalier of Gales", "Sanitarium Skeleton")}
with Path(sys.argv[2]).open("w") as fh:
    for code in ("M21", "M20", "FDN"):
        supply = compile_supply("all", code, require_verified=False)
        names = {oid: meta.name for oid, meta in supply.metas.items()}
        oids = sorted(supply.verified_ids | {o for o, n in names.items() if n in EXTRA.get(code, ())})
        for oid in oids:
            try:
                rep = Probe(supply, code, oid).report()
                row = {"set": code, "name": names[oid], "sha": rep.sha(), "errors": len(rep.errors),
                       "text": rep.text()}
            except Exception as error:  # noqa: BLE001 - a probe crash is a finding, recorded
                row = {"set": code, "name": names[oid], "sha": None, "errors": None,
                       "text": f"{type(error).__name__}: {error}"}
            fh.write(json.dumps(row) + "\n")
            fh.flush()
