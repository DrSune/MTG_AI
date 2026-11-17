"""Trace every read of a token that ceased to exist (CR 704.5d): which engine sites look it up
after the state-based check removed it from world.cards. Runs the scenario packs (all dirs) and
seeded heuristic games on the verified pools.

    trace_ceased.py <checkout> <games per set> [<pack glob filter>]
"""
from __future__ import annotations

import collections
import json
import sys
import traceback
from functools import cache
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core import state as state_mod  # noqa: E402
from MTG_bot.core.executor import Executor  # noqa: E402
from MTG_bot.core.executor.games import compile_supply, get_supply  # noqa: E402

SITES: collections.Counter = collections.Counter()
EXAMPLES: dict = {}
CONTEXT = ["?"]


def _site() -> tuple[str, ...]:
    frames = [f for f in traceback.extract_stack()[:-2] if "/MTG_bot/" in f.filename or "/tools/" in f.filename]
    frames = [f for f in frames if not f.filename.endswith("trace_ceased.py")]
    return tuple(f"{Path(f.filename).name}:{f.name}:{f.lineno}" for f in frames[-9:])


class TrackDict(dict):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.ceased: set = set()

    def _hit(self, key, how):
        site = (how,) + _site()
        SITES[site] += 1
        EXAMPLES.setdefault(site, CONTEXT[0])

    def __getitem__(self, key):
        if key in self.ceased and not dict.__contains__(self, key):
            self._hit(key, "getitem")
        return dict.__getitem__(self, key)

    def __contains__(self, key):
        if key in self.ceased and not dict.__contains__(self, key):
            self._hit(key, "contains")
        return dict.__contains__(self, key)

    def get(self, key, default=None):
        if key in self.ceased and not dict.__contains__(self, key):
            self._hit(key, "get")
        return dict.get(self, key, default)


_init = state_mod.GameWorld.__init__


def init(self, *a, **k):
    _init(self, *a, **k)
    self.cards = TrackDict(self.cards)


state_mod.GameWorld.__init__ = init
_cease = Executor._cease_tokens


def cease(self):
    gone = _cease(self)
    cards = self.world.cards
    if isinstance(cards, TrackDict):
        cards.ceased.update(gone)
    return gone


Executor._cease_tokens = cease

sys.path.insert(0, str(ROOT / "tools"))
from run_scenarios import run_pack  # noqa: E402


@cache
def mapped(code):
    return compile_supply("all", code, require_verified=False)


def set_of(path):
    try:
        return str(json.loads(path.read_text()).get("set", "M21"))
    except (OSError, ValueError):
        return "M21"


flt = sys.argv[3] if len(sys.argv) > 3 else ""
packs = sorted((ROOT / "tools" / "scenarios").glob("*.json"))
packs += sorted((ROOT / "tools" / "scenarios").glob("cards/*/*.json"))
mapped_packs = sorted((ROOT / "tools" / "scenarios").glob("mapped/*/*.json"))
failed = []
for path in packs + mapped_packs:
    if flt and flt not in str(path):
        continue
    CONTEXT[0] = f"pack {path.relative_to(ROOT)}"
    sup = mapped(set_of(path)) if path in mapped_packs else get_supply("all", set_of(path))
    fails = run_pack(path, sup)
    if fails:
        failed.append((str(path.relative_to(ROOT)), fails[:3]))
print(f"packs failed: {len(failed)}")
for name, fails in failed:
    print("  FAIL", name, fails)

n = int(sys.argv[2])
crashes = []
if n:
    from tools.selfplay import rig
    from tools.selfplay.heuristic import HeuristicAgent

    import os

    only = {tuple(x.split(":")) for x in os.environ.get("GAMES", "").split(",") if x}
    for code in ("M21", "M20", "FDN"):
        for i in range(n):
            if only and (code, str(920000 + i)) not in only:
                continue
            CONTEXT[0] = f"game {code} {920000 + i}"
            res = rig.play_game(920000 + i, [HeuristicAgent(), HeuristicAgent()],
                                deck_mode="stress" if i % 3 else "coherent", pool_mode="verified",
                                set_code=code)
            if res["crash"]:
                crashes.append((code, 920000 + i, res["crash"][:300]))
print(f"game crashes: {len(crashes)}")
for row in crashes:
    print("  CRASH", row)
print(f"ceased-token read sites: {len(SITES)}")
for site, count in SITES.most_common():
    print(f"{count:6d}  {site}  e.g. {EXAMPLES[site]}")
