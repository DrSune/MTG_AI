"""193 §2's G3: 1,000 decks per K from the critic, no games. Each deck is seat 0's dealt coherent
deck of an M21 deal (seeds 900,000-900,999, the G2 deals) after K swaps (decks.drafted_decks,
versus mode). Per K: distinct decks, spells in at least 1% of decks, decks outside the critic's
band (and how many of those started outside it), the mean predicted gain in logits.
    PYTHONPATH=. .venv/bin/python <this> CRITIC.json"""
import json
import sys
from collections import Counter
from pathlib import Path

from MTG_bot.core.executor.games import deal_decks, get_supply
from tools.selfplay import decks as DK

critic = json.loads(Path(sys.argv[1]).read_text())
sha, value = critic["sha256"][:8], critic["value"]
sup = get_supply("verified", "M21")
bd = critic["band"]["M21"]


def meta(c):
    m = sup.metas[c]
    return m.mana_value, "Creature" in m.type_line, m.is_land, m.is_basic


def inside(deck):
    mv, cr, cp = DK.deck_stats(Counter(deck), meta)
    return bd["mv"][0] <= mv <= bd["mv"][1] and bd["creatures"][0] <= cr <= bd["creatures"][1] \
        and cp <= bd["copies"]


seeds = range(900_000, 901_000)
start = {s: deal_decks(s, DK.DEAL_SEED, sup, "coherent")[0] for s in seeds}
for k in (0, 4, 8, 16):
    decks = {s: DK.drafted_decks(s, f"versus:{k}:{sha}", 0, sup, critic, "M21")[0] for s in seeds}
    used = Counter(c for d in decks.values() for c in set(d) if not sup.metas[c].is_land)
    out = [s for s, d in decks.items() if not inside(d)]
    gain = sum(sum(value.get(c, 0.0) for c in decks[s]) - sum(value.get(c, 0.0) for c in start[s])
               for s in seeds) / len(seeds)
    print(json.dumps({"k": k, "decks": len(decks), "distinct": len(set(decks.values())),
                      "spells_1pct": sum(n >= 10 for n in used.values()),
                      "outside_band": len(out),
                      "outside_and_started_outside": sum(not inside(start[s]) for s in out),
                      "gain_logits": round(gain, 3)}))
