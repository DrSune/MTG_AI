"""G3's mutants of every card that chooses as it enters or names a card (the family and Runed
Halo, Necromentia): how many are live, and which of them drop a chosen-quality read. Read-only.

    g3_choosers.py <root>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core.ability_tree import FAtom, FAtomPred, walk
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from tools.cards.gates import mutants

reg = build_full_registry()


def reads(card):
    return sorted(str(n.string_value) for n in walk(card)
                  if isinstance(n, FAtom) and n.pred is FAtomPred.NAME_CHOSEN)


CARDS = (("M21", "Runed Halo"), ("M21", "Necromentia"), ("M20", "Icon of Ancestry"),
         ("M20", "Diamond Knight"), ("FDN", "Diamond Mare"), ("M19", "Diamond Mare"),
         ("ORI", "Prism Ring"), ("KHM", "Rally the Ranks"), ("M15", "Obelisk of Urd"),
         ("ELD", "Heraldic Banner"), ("FDN", "Heraldic Banner"), ("M12", "Adaptive Automaton"),
         ("FDN", "Adaptive Automaton"))
for code, name in CARDS:
    raw = next(r for r in ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json").values()
               if r.identity.name == name)
    try:
        card = compile_card(raw, reg).card
    except Exception as e:  # noqa: BLE001
        print(f"{code} {name}: does not compile ({type(e).__name__})")
        continue
    ms = list(mutants(card))
    fewer = [(op, path, reads(m)) for op, path, m in ms if len(reads(m)) < len(reads(card))]
    print(f"{code} {name}: reads {reads(card)}; {len(ms)} live mutants; dropping a read: {fewer}")
