"""Card tooling: the Python rendering round-trips every compiled tree, and the probe plays a card
through the engine's own legality surface."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import irpy
import probe

from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor.games import compile_supply

DATA = HERE.parents[1] / "MTG_bot" / "data"


def test_every_m21_tree_renders_to_python_that_rebuilds_it() -> None:
    pool = compile_pool(ingest_pool(DATA / "M21.json"), build_full_registry())
    ns = irpy.namespace()
    for card in pool.cards.values():
        assert eval(irpy.render(card), ns) == card, card.name


def test_a_draft_keeps_the_compiled_tree_and_may_add_to_it() -> None:
    pool = compile_pool(ingest_pool(DATA / "M21.json"), build_full_registry())
    card = next(c for c in pool.cards.values() if c.name == "Shock")
    kws, abilities = irpy.run_draft("abilities = compiled", card.abilities, card.keywords)
    assert abilities == card.abilities and kws == card.keywords


def test_the_probe_offers_only_legal_targets_and_shows_the_damage() -> None:
    sup = compile_supply("all", "M21", require_verified=False)
    oid = next(o for o, m in sup.metas.items() if m.name == "Shock")
    rep = probe.Probe(sup, "M21", oid).report()
    text = rep.text()
    assert not rep.errors
    assert "target slot (cast): 1..1 of [you_bear, you_giant, opp_bear, opp_giant, you, opp]" in text
    assert "opp: life 20 -> 18" in text
    assert "opp_bear dies" in text
    assert rep.sha() == probe.Probe(sup, "M21", oid).report().sha()  # deterministic
