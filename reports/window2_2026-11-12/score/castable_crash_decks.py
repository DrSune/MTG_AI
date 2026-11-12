"""Which castable-pool cards sat in the decks of window 2's four crashed H2 deals (run on the w2 tree)."""
from MTG_bot.core.executor.games import deal_decks, get_supply
from tools.selfplay.decks import DEAL_SEED

sup = get_supply("castable", "M21")
ver = get_supply("verified", "M21")
names = {c: sup.metas[c].name for c in sup.metas}
crashed = {900114: "NAME_CHOSEN", 900195: "NAME_CHOSEN", 900283: "NAME_CHOSEN", 900085: "TARGET_PLAYER"}
vset = set(ver.deckable)
for seed, why in crashed.items():
    d = deal_decks(seed, DEAL_SEED, sup, "coherent")
    unver = [sorted({names[c] for c in deck if c not in vset and not sup.metas[c].is_land}) for deck in d]
    halo = [sum(names[c] == "Runed Halo" for c in deck) for deck in d]
    print(seed, why, "Runed Halo copies per seat:", halo, "\n   unverified spells seat0:", unver[0], "\n   unverified spells seat1:", unver[1])
