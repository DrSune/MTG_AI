"""Every card's tree in the 19 sets, two ways: the game's (verified records applied, mode "all")
and the mapper's (every record applied); with whether it is in the verified deal pool. Run on
each checkout; compare the JSON outputs with tree_compare.py.

    tree_dump.py <checkout> <out.json>
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__
from MTG_bot.core.ability_tree import to_dict  # noqa: E402
from MTG_bot.core.executor.games import compile_supply, get_supply  # noqa: E402

SETS = ("10E", "DOM", "ELD", "FDN", "IKO", "KHM", "M10", "M11", "M12", "M13", "M14", "M15", "M19",
        "M20", "M21", "ORI", "THB", "WAR", "ZNR")


def sha(card) -> str | None:
    if card is None:
        return None
    return hashlib.sha256(json.dumps(to_dict(card), sort_keys=True).encode()).hexdigest()[:16]


out = {}
for code in SETS:
    game = get_supply("all", code)
    mapped = compile_supply("all", code, require_verified=False)
    dealt = set(get_supply("verified", code).deckable)
    rows = {}
    for oid in sorted(set(game.pool.results) | set(mapped.pool.results)):
        g, m = game.pool.results.get(oid), mapped.pool.results.get(oid)
        rows[oid] = {"game": sha(g.card if g else None), "mapped": sha(m.card if m else None),
                     "dealt": oid in dealt}
    out[code] = rows
Path(sys.argv[2]).write_text(json.dumps(out, indent=0, sort_keys=True))
print("dumped", sum(len(v) for v in out.values()), "cards")
