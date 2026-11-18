"""Play each named pack with a checkout's runner and print a sha of its journal dump, its final
life totals and zones, and whether run_pack passes: run once on the base export with its packs,
once on the branch with its packs, and diff the two outputs (the edits must play the same game).

    pack_journals.py <checkout> <list.txt> > out.txt
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core.executor import GameOver  # noqa: E402
from MTG_bot.core.executor.games import compile_supply, get_supply  # noqa: E402
from tools import run_scenarios as rs  # noqa: E402

D = ROOT / "tools" / "scenarios"
sups: dict = {}
for rel in Path(sys.argv[2]).read_text().split():
    rel = rel.removeprefix("tools/scenarios/")
    pack = json.loads((D / rel).read_text())
    code = str(pack.get("set", "M21"))
    key = (rel.split("/")[0] == "mapped", code)
    if key not in sups:
        sups[key] = compile_supply("all", code, require_verified=False) if key[0] else get_supply("all", code)
    try:
        r = rs.ScenarioRunner(pack, sups[key])
        for step in pack["steps"]:
            try:
                r.run_step(step)
            except GameOver:
                break
            except Exception as e:  # noqa: BLE001
                if not (step.get("expect_raise") and step["expect_raise"] in f"{type(e).__name__}: {e}"):
                    raise
        dump = repr(r.ex.journal.dump())
        state = sorted((str(h), r.world.zone_of(h).kind) for h in r.world.cards)
        life = [r.world.players[p].life for p in r.world.player_order]
        sha = hashlib.sha256((dump + repr(state) + repr(life)).encode()).hexdigest()[:16]
    except Exception as e:  # noqa: BLE001
        sha = f"ERROR {type(e).__name__}: {str(e)[:80]}"
    print(rel, sha)
