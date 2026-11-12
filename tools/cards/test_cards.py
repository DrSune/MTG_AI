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
    assert ("target slot (cast): 1..1 of [you_bear, you_giant, opp_flier, opp_tapped, opp_bear, "
            "opp_giant, you, opp]") in text
    assert "opp: life 20 -> 18" in text
    assert "opp_bear dies" in text
    assert rep.sha() == probe.Probe(sup, "M21", oid).report().sha()  # deterministic


def test_the_probe_plays_a_modal_spell_one_mode_at_a_time() -> None:
    # Return to Nature's three modes each get their own target slot and their own variants
    # (CR 601.2b: modes first, then only those modes' targets); the engine refuses every mode's
    # targets at once.
    sup = compile_supply("all", "M21", require_verified=False)
    oid = next(o for o, m in sup.metas.items() if m.name == "Return to Nature")
    rep = probe.Probe(sup, "M21", oid).report()
    text = rep.text()
    assert not rep.errors
    assert "target slot (cast modes=[0]): 1..1 of [you_relic, opp_relic]" in text
    assert "target slot (cast modes=[1]): 1..1 of [you_charm, opp_charm]" in text
    assert "[cast modes=[2] targets=['opp_fallen']]" in text
    assert "opp_relic moves battlefield -> graveyard (by card/DESTROY)" in text


def test_the_probe_never_targets_one_object_for_two_slots_of_another_target() -> None:
    # "Another target creature" (CR 115.3): Rookie Mistake's second target and Garruk, Savage
    # Herald's -2 never take the first slot's target, and a game never offers that pair
    # (stack.slot_options), so the probe does not try it either.
    sup = compile_supply("all", "M21", require_verified=False)
    for name in ("Rookie Mistake", "Garruk, Savage Herald"):
        oid = next(o for o, m in sup.metas.items() if m.name == name)
        rep = probe.Probe(sup, "M21", oid).report()
        assert not rep.errors, (name, rep.errors)
        assert "targets=['you_bear', 'you_bear']" not in rep.text()
        assert "targets=['you_bear', 'you_giant']" in rep.text()


def test_the_probe_shows_the_asks_a_combat_makes() -> None:
    # Feline Sovereign: "Whenever one or more Cats you control deal combat damage to a player,
    # destroy up to one target artifact or enchantment that player controls." The engine asks the
    # controller as the trigger goes on the stack (CR 603.3d, 601.2c). The scenario runner's combat
    # op used to answer that ask itself, unseen, with its first word, so the trace showed the Relic
    # destroyed and no choice (verification wave 1, packet A15).
    sup = compile_supply("all", "M21", require_verified=False)
    oid = next(o for o, m in sup.metas.items() if m.name == "Feline Sovereign")
    text = probe.Probe(sup, "M21", oid).report().text()
    attack = text.split("[stimulus: this creature attacks alone, unblocked")[1].split("\n[")[0]
    assert "ask target: [opp_relic, opp_charm, NONE] -> opp_relic" in attack
    assert "opp_relic moves battlefield -> graveyard (by card/DESTROY)" in attack


def test_a_card_on_the_probe_board_has_made_its_as_enters_choice() -> None:
    # Runed Halo: "As this enchantment enters, choose a card name" (CR 614.1c). A permanent is on
    # the battlefield only by having entered it, so the board's Halo has chosen a name, and the
    # opponent's attack checks its controller's protection against that name.
    sup = compile_supply("all", "M21", require_verified=False)
    oid = next(o for o, m in sup.metas.items() if m.name == "Runed Halo")
    rep = probe.Probe(sup, "M21", oid).report()
    assert not rep.errors, rep.errors


def test_the_probe_plays_an_emblem_without_putting_it_in_a_hand() -> None:
    # An emblem is never a card in a hand (CR 114.1), so it gets no "from your hand, the card
    # enters" stimulus. Basri Ket's emblem compiles in M21.
    sup = compile_supply("all", "M21", require_verified=False)
    oid = next(o for o, r in sup.pool.results.items() if r.card.name == "Basri Ket Emblem")
    rep = probe.Probe(sup, "M21", oid).report()
    assert not rep.errors
    assert "from your hand" not in rep.text()


def test_the_probe_plays_a_token_without_putting_it_in_a_hand() -> None:
    # A token put into a hand ceases to exist (CR 111.8), so it gets no from-hand stimulus.
    sup = compile_supply("all", "M21", require_verified=False)
    oid = next(o for o, r in sup.pool.results.items() if r.card.name == "Cat" and r.card.is_token)
    rep = probe.Probe(sup, "M21", oid).report()
    assert not rep.errors
    assert "from your hand" not in rep.text()


def test_g0_asks_no_cast_carrier_of_a_token() -> None:
    # A token is never cast (CR 111.8), so G0 asks no permanent's cast carrier of it.
    import corpus
    import gates

    sc = corpus.compile_set("M20")
    oid = next(o for o, r in sc.results.items() if r.card is not None and r.card.name == "Wolf"
               and r.card.is_token)
    card = sc.results[oid].card
    fails, _ = gates.g0(sc.raw[oid], card, card, clauses=None, known_signatures=None)
    assert not [f for f in fails if "SpellAbility" in f], fails


def test_a_reverification_adds_its_packs_beside_the_earlier_ones(tmp_path) -> None:
    """cardtool verify names a kept spec pack by the first free index, so re-verifying a card
    never overwrites the packs of its earlier verification (KNOWLEDGE 201)."""
    from cardtool import next_pack_path

    assert next_pack_path(tmp_path, "basri_ket").name == "basri_ket_1.json"
    (tmp_path / "basri_ket_1.json").write_text("{}")
    (tmp_path / "basri_ket_2.json").write_text("{}")
    assert next_pack_path(tmp_path, "basri_ket").name == "basri_ket_3.json"


def test_a_reverification_keeps_one_copy_of_a_pack_it_carries_again(tmp_path) -> None:
    """A verdict that lists a pack already kept for the card (the same text) reuses its file, so
    re-verifying never duplicates a spec pack in the suite; a new pack takes the next index."""
    from cardtool import kept_pack_path

    (tmp_path / "tales_end_1.json").write_text('{"a": 1}')
    (tmp_path / "tales_end_2.json").write_text('{"b": 2}')
    assert kept_pack_path(tmp_path, "tales_end", '{"b": 2}').name == "tales_end_2.json"
    assert kept_pack_path(tmp_path, "tales_end", '{"c": 3}').name == "tales_end_3.json"
