"""Trace a pack's steps against one checkout: zones of every pack card and the stack after each step.

    tracepack.py <checkout> <pack.json>
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import run_scenarios as rs  # noqa: E402
from MTG_bot.core.executor.games import get_supply  # noqa: E402

path = Path(sys.argv[2])
pack = json.loads(path.read_text())
sup = get_supply("all", pack.get("set", "M21"))
orig = rs.ScenarioRunner._dispatch if hasattr(rs, "ScenarioRunner") else None
cls = next(v for v in vars(rs).values() if isinstance(v, type) and hasattr(v, "_dispatch"))
real = cls._dispatch


def traced(self, step):
    real(self, step)
    zones = {k: self.world.zone_of(h).kind for k, h in self.handles.items() if h in self.world.cards}
    stack = [(str(f.handle), f.spell_kind) for f in self.ex.stack.frames]
    rows = [(e.clock, e.kind, str(e.subject), str(e.cause), e.cause_verb, e.data[:2], e.origin if hasattr(e, "origin") else "-")
            for e in self.ex.journal.events[-6:] if e.kind == "ZONE_CHANGE"]
    print(step.get("op"), zones, "stack", stack, "\n    ", rows)


cls._dispatch = traced
print(rs.run_pack(path, sup))
