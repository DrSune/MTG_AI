"""Exile and remove-counter costs (2026-11-14, ontology round R11, DESIGN_ATOM_ONTOLOGY §15; ledger
F3 ruled: a cost part stays its own closed union, never the verb atom it mirrors).

- ``CostExile(target)``: "Exile this creature" (M20 Hanged Executioner), "Exile this card from your
  graveyard" (FDN Suspicious Shambler: the ability then works only in the graveyard, CR 113.6m),
  "Exile a creature card from your graveyard" (DOM Fungal Plots).
- ``CostRemoveCounter(counter_kind, target, count)``: "Remove a +1/+1 counter from this creature"
  (M20 Barkhide Troll), CostPutCounter's twin.
- A cost is paid while the ability is activated (CR 601.2h by 602.2b), before anyone can respond
  (117.3c), all of it or the ability is not activated (118.3, 601.2h), and it stays paid when the
  ability does not resolve (608.2b). The payer chooses which objects (the ``exile`` and
  ``remove_counter`` asks) when a cost offers more than it needs.

Every test here fails on the base, 1d5e4164, except the controls named in
``reports/cost_twins_2026-11-14/base_runs.txt``.
"""

from __future__ import annotations

from functools import cache

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    ControllerRef,
    Cost,
    CostManaGeneric,
    CostSacrifice,
    CostTap,
    CounterKind,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    QConst,
    QUnbounded,
    QX,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import compile_supply
from MTG_bot.core.executor.legality import (
    activation_zone,
    build_payment_plan,
    ctx_for,
    pay_costs,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD, GameWorld
from MTG_bot.core.test_executor_binding import BF_ANY, CREATURE, IS_SOURCE, UNIV, atom, card_id, reset_oracle_ids
from tools.run_scenarios import ScenarioRunner

GY_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
THIS = Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=(BF_ANY,))
THIS_IN_GRAVEYARD = Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=(GY_YOU,))
P1P1 = CounterKind.PLUS_1_PLUS_1


def _exile(sel: Selector):
    return at.CostExile(target=sel)


def _remove(kind: CounterKind = P1P1, sel: Selector = THIS, n: int = 1):
    return at.CostRemoveCounter(counter_kind=kind, target=sel, count=QConst(n))


# ------------------------------------------------------------------------------------- the IR


def test_the_two_cost_parts_round_trip_in_a_cost() -> None:
    cost = Cost(parts=(CostManaGeneric(QConst(1)), _remove(), _exile(THIS)))
    assert at.from_dict("Cost", at.to_dict(cost)) == cost
    assert {type(p).__name__ for p in cost.parts} >= {"CostExile", "CostRemoveCounter"}


@pytest.mark.parametrize("make", [_exile, lambda s: _remove(sel=s)])
@pytest.mark.parametrize("sel", [
    Selector(QConst(1), SelectorMode.TARGET, CREATURE, zones=(BF_ANY,)),  # costs never target
    Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
             referent="target"),  # nor name "it"
    Selector(QConst(1), SelectorMode.ALL, CREATURE, zones=(BF_ANY,)),
    Selector(QUnbounded(), SelectorMode.CHOOSE, CREATURE, zones=(BF_ANY,)),  # "any number"
    Selector(QX(), SelectorMode.CHOOSE, CREATURE, zones=(BF_ANY,)),
    Selector(QConst(0), SelectorMode.CHOOSE, CREATURE, zones=(BF_ANY,)),
], ids=["target", "referent", "all", "any-number", "x", "zero"])
def test_the_payer_chooses_a_literal_number_of_objects(make, sel) -> None:
    """CR 601.2h: the payer chooses a cost's objects as they pay it; they are never targets (CR
    601.2c chooses targets first) and never "it"."""
    with pytest.raises(ValueError):
        make(sel)


@pytest.mark.parametrize("kind", [ZoneKind.LIBRARY, ZoneKind.STACK, ZoneKind.EXILE, ZoneKind.ANY])
def test_an_exile_cost_takes_a_permanent_or_a_card_from_a_graveyard_or_hand(kind) -> None:
    with pytest.raises(ValueError, match="zones must be among"):
        _exile(Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(Zone(kind, ControllerRef.YOU),)))
    for ok in (ZoneKind.BATTLEFIELD, ZoneKind.GRAVEYARD, ZoneKind.HAND):
        _exile(Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(Zone(ok, ControllerRef.YOU),)))


def test_a_remove_counter_cost_is_one_kind_a_literal_amount_on_a_permanent() -> None:
    with pytest.raises(ValueError, match="CostLoyalty"):
        _remove(CounterKind.LOYALTY)  # a loyalty ability's cost is CostLoyalty (CR 606.4)
    for count in (QX(), QUnbounded(), QConst(0)):  # Cruel Sadist, Relic Amulet: no lane pays them
        with pytest.raises(ValueError, match="count is a literal"):
            at.CostRemoveCounter(counter_kind=P1P1, target=THIS, count=count)
    with pytest.raises(ValueError, match="zones must be among"):
        _remove(sel=THIS_IN_GRAVEYARD)
    with pytest.raises(ValueError, match="CounterKind"):
        at.CostRemoveCounter(counter_kind="PLUS_1_PLUS_1", target=THIS)


def test_an_exile_from_the_graveyard_keeps_a_mana_ability() -> None:
    """CR 605.1a: IKO Titans' Nest's "Exile a card from your graveyard: Add {C}." and ZNR Throne of
    Makindi's "{T}, Remove a charge counter from this land: Add two mana of any one color." move no
    card to or from a library, target nothing and add mana: mana abilities."""
    add_c = atom(Verb.ADD_MANA, amount=QConst(1), color="C", controller=ControllerRef.YOU)
    nest = ActivatedAbility(cost=Cost(parts=(_exile(Selector(QConst(1), SelectorMode.CHOOSE, UNIV,
                                                             zones=(GY_YOU,))),)), effect=add_c)
    throne = ActivatedAbility(cost=Cost(parts=(CostTap(), _remove(CounterKind.CHARGE))), effect=add_c)
    assert at.is_mana_ability(nest) and at.is_mana_ability(throne)


def test_an_ability_that_exiles_its_card_from_the_graveyard_works_there() -> None:
    """CR 113.6m: its cost moves its own card out of the graveyard, so it works only there; "Exile
    two other creature cards" names other cards and leaves the battlefield the zone."""
    tokens = atom(Verb.DRAW, amount=QConst(1), controller=ControllerRef.YOU)
    own = ActivatedAbility(cost=Cost(parts=(_exile(THIS_IN_GRAVEYARD),)), effect=tokens)
    others = ActivatedAbility(cost=Cost(parts=(_exile(Selector(
        QConst(2), SelectorMode.CHOOSE, FAnd((FNot(IS_SOURCE), CREATURE)), zones=(GY_YOU,))),)),
        effect=tokens)
    assert activation_zone(own) == ZONE_GRAVEYARD
    assert activation_zone(others) == ZONE_BATTLEFIELD
    assert activation_zone(ActivatedAbility(cost=Cost(parts=(_exile(THIS),)), effect=tokens)) == ZONE_BATTLEFIELD


# ------------------------------------------------------------------------------- the compiler


def _ability(sentence: str):
    from MTG_bot.core.compiler.coverage import build_full_registry
    from MTG_bot.core.compiler.frames import compose

    matches = compose(sentence, build_full_registry())
    assert matches, f"no parse: {sentence}"
    assert matches[0].template.tid.startswith("B13-activated-cost-item+")
    return matches[0].outcome.ability


def test_the_frame_reads_an_exile_of_the_source() -> None:
    ab = _ability("{3}{W}, Exile this creature: Exile target creature.")  # Hanged Executioner
    exile = [p for p in ab.cost.parts if isinstance(p, at.CostExile)]
    assert exile == [_exile(THIS)]
    assert sorted(type(p).__name__ for p in ab.cost.parts) == [
        "CostExile", "CostManaColor", "CostManaGeneric"]
    assert ab.effect.verb is Verb.MOVE_ZONE and ab.effect.args.get("target").mode is SelectorMode.TARGET
    inquisitive = _ability("Exile this creature: Create a 1/1 white Human creature token.")
    assert inquisitive.cost.parts == (_exile(THIS),)


def test_the_frame_reads_an_exile_of_this_card_from_your_graveyard() -> None:
    ab = _ability("{4}{B}{B}, Exile this card from your graveyard: Create two 2/2 black Zombie "
                  "creature tokens.")  # Suspicious Shambler
    assert _exile(THIS_IN_GRAVEYARD) in ab.cost.parts
    assert activation_zone(ab) == ZONE_GRAVEYARD


def test_the_frame_reads_an_exile_of_cards_from_your_graveyard() -> None:
    plots = _ability("{1}{G}, Exile a creature card from your graveyard: Create a 1/1 green "
                     "Saproling creature token.")  # DOM Fungal Plots
    assert _exile(Selector(QConst(1), SelectorMode.CHOOSE, CREATURE, zones=(GY_YOU,))) in plots.cost.parts
    others = _ability("Exile two other cards from your graveyard: Draw a card.")
    assert others.cost.parts == (_exile(Selector(QConst(2), SelectorMode.CHOOSE, FNot(IS_SOURCE),
                                                 zones=(GY_YOU,))),)


def test_the_frame_reads_a_removed_counter() -> None:
    hydra = _ability("{2}{G}, Remove a +1/+1 counter from this creature: Destroy target artifact or "
                     "enchantment.")  # ELD Steelbane Hydra
    assert _remove() in hydra.cost.parts
    tome = _ability("{1}, {T}, Remove a page counter from this artifact: Draw a card.")  # ELD Tome
    assert _remove(CounterKind.PAGE) in tome.cost.parts and CostTap() in tome.cost.parts


@pytest.mark.parametrize("sentence", [
    "{5}, {T}, Remove a wish counter from this artifact: Draw a card.",  # no WISH kind
    "Remove a +1/+1 counter from this creature: It deals 1 damage to any target.",  # a pronoun
    "Remove X +1/+1 counters from this creature: Draw a card.",  # X has no lane
    "{T}, Remove all charge counters from this artifact: Draw a card.",
])
def test_the_frame_leaves_what_it_cannot_read_unparsed(sentence) -> None:
    from MTG_bot.core.compiler.coverage import build_full_registry
    from MTG_bot.core.compiler.frames import compose

    assert not compose(sentence, build_full_registry())


# -------------------------------------------------------------------------------- the payment


class _World:
    """p0's Alpha (the source) and Gamma, Delta on the battlefield, two creature cards and a land
    card in p0's graveyard; p1's Beta."""

    def __init__(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=17)
        self.p0, self.p1 = self.world.player_order
        add = self.world.add_card
        self.alpha = add(card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.gamma = add(card_id("Gamma", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.delta = add(card_id("Delta", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.beta = add(card_id("Beta", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.dead = [add(card_id(f"Dead{i}", "1", "1"), self.p0, ZONE_GRAVEYARD) for i in (1, 2)]
        self.land = add(card_id("Old Land", type_line="Land"), self.p0, ZONE_GRAVEYARD)
        self.ex = Executor(self.world)
        self.asks: list[tuple[str, tuple[str, ...]]] = []

    def plan(self, *parts):
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        return build_payment_plan(self.world, ctx, Cost(parts=parts))

    def pay(self, plan, answer=None):
        def prov(vocab, what):
            self.asks.append((what, tuple(vocab)))
            return str(answer) if answer is not None and str(answer) in vocab else vocab[0]

        self.ex.decisions.provider = prov
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)


def test_a_remove_counter_cost_without_the_counter_cannot_be_paid() -> None:
    """CR 118.3: with no +1/+1 counter on it, "Remove a +1/+1 counter from this creature" can't be
    paid; with one, the plan removes it from the source and nothing is asked."""
    w = _World()
    plan, why = w.plan(_remove())
    assert plan is None and why == "cost:remove_counter:PLUS_1_PLUS_1:insufficient_candidates:0<1"
    w.world.cards[w.alpha].counters["PLUS_1_PLUS_1"] = 1
    plan, why = w.plan(_remove())
    assert why is None and plan.remove_counters == (((w.alpha,), 1, "PLUS_1_PLUS_1", 1),)
    w.pay(plan)
    assert "PLUS_1_PLUS_1" not in w.world.cards[w.alpha].counters and w.asks == []
    assert w.plan(_remove())[0] is None  # the counter is gone: a second activation can't pay


def test_one_cost_never_spends_a_counter_or_a_card_twice() -> None:
    """Two parts of one cost compete for one counter or one card: the second finds it taken."""
    w = _World()
    w.world.cards[w.alpha].counters["PLUS_1_PLUS_1"] = 1
    assert w.plan(_remove(), _remove())[1] == "cost:remove_counter:PLUS_1_PLUS_1:insufficient_candidates:0<1"
    w.world.cards[w.alpha].counters["PLUS_1_PLUS_1"] = 2
    assert w.plan(_remove(), _remove())[1] is None
    creature_card = Selector(QConst(1), SelectorMode.CHOOSE, CREATURE, zones=(GY_YOU,))
    two = Selector(QConst(2), SelectorMode.CHOOSE, CREATURE, zones=(GY_YOU,))
    # Cost sorts its parts (canonical bytes): the one-card exile plans first and takes a card
    assert w.plan(_exile(two), _exile(creature_card))[1] == "cost:exile:insufficient_candidates:1<2"
    plan, why = w.plan(_exile(creature_card), _exile(creature_card))
    assert why is None and plan.exile == tuple(sorted(w.dead))


def test_the_payer_chooses_which_cards_a_cost_exiles() -> None:
    """CR 601.2h: "Exile a creature card from your graveyard" with two there asks the payer (the
    ``exile`` ask, the sacrifice lane's shape), and the land card is no creature card."""
    w = _World()
    plan, why = w.plan(_exile(Selector(QConst(1), SelectorMode.CHOOSE, CREATURE, zones=(GY_YOU,))))
    assert why is None and plan.exile_options == ((tuple(sorted(w.dead)), 1),)
    w.pay(plan, answer=w.dead[1])
    (site, vocab), = w.asks
    assert site.startswith(f"exile:{w.p0}:{w.alpha}:") and vocab == tuple(str(h) for h in sorted(w.dead))
    assert w.world.zone_of(w.dead[1]).kind == ZONE_EXILE
    assert w.world.zone_of(w.dead[0]).kind == ZONE_GRAVEYARD
    assert w.world.zone_of(w.land).kind == ZONE_GRAVEYARD


def test_the_source_pays_an_exile_cost_only_when_the_cost_names_it() -> None:
    """A spell is on the stack while its costs are paid (CR 601.2a, 601.2h), but the cast fold
    plans with it still where it was cast from: "exile a creature card from your graveyard" never
    takes the spell itself (a creature card cast from the graveyard), as CostDiscard never
    discards it; "Exile this card from your graveyard" takes exactly the source."""
    w = _World()
    w.world.move_to_zone(w.alpha, w.p0, ZONE_GRAVEYARD)
    creature_card = Selector(QConst(1), SelectorMode.CHOOSE, CREATURE, zones=(GY_YOU,))
    plan, why = w.plan(_exile(creature_card))
    assert why is None and plan.exile_options == ((tuple(sorted(w.dead)), 1),)
    plan, why = w.plan(_exile(THIS_IN_GRAVEYARD))
    assert why is None and plan.exile == (w.alpha,)


def test_the_payer_chooses_the_permanent_a_cost_removes_counters_from() -> None:
    """A cost removing a counter from "a creature you control" (no such printed cost of the 19
    sets has a kind; WAR Soul Diviner's "a counter" is refused) asks which creature, among those
    holding one."""
    w = _World()
    mine = Selector(QConst(1), SelectorMode.CHOOSE,
                    FAnd((CREATURE, FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU))), zones=(BF_ANY,))
    for h in (w.gamma, w.delta, w.beta):
        w.world.cards[h].counters["PLUS_1_PLUS_1"] = 1
    plan, why = w.plan(_remove(sel=mine))
    assert why is None and plan.remove_counters == ((tuple(sorted((w.gamma, w.delta))), 1, "PLUS_1_PLUS_1", 1),)
    w.pay(plan, answer=w.delta)
    (site, vocab), = w.asks
    assert site.startswith(f"remove_counter:{w.p0}:{w.alpha}:")
    assert "PLUS_1_PLUS_1" not in w.world.cards[w.delta].counters
    assert w.world.cards[w.gamma].counters == {"PLUS_1_PLUS_1": 1}


def test_a_plan_keeps_the_repr_the_stack_fingerprint_folds() -> None:
    """The stack's fingerprint row folds repr(PaymentPlan) (stack.SpellStack.dump): the three new
    fields stay out of it, so every state holding a stack object keeps its fingerprint bytes
    (reports/cost_twins_2026-11-14/fingerprint_check.py, base and branch)."""
    from MTG_bot.core.executor.legality import PaymentPlan
    from MTG_bot.core.identity import Handle

    assert repr(PaymentPlan(mana=(("R", 1),), exile=(Handle("card", 9),))) == (
        "PaymentPlan(mana=(('R', 1),), tap=(), sacrifice=(), discard=(), counters=(), loyalty=0, "
        "life=0, sacrifice_options=(), tap_options=(), discard_options=())")


def test_the_counters_come_off_before_their_permanent_is_sacrificed() -> None:
    """M13 Hellion Crucible's "Remove two pressure counters from this land and sacrifice it": the
    payer pays in any order (CR 601.2h), and only removing first pays it all."""
    w = _World()
    w.world.cards[w.alpha].counters["CHARGE"] = 2
    plan, why = w.plan(_remove(CounterKind.CHARGE, n=2), CostSacrifice(THIS))
    assert why is None
    w.pay(plan)
    assert w.world.zone_of(w.alpha).kind == ZONE_GRAVEYARD
    rows = [e[1:] for e in w.ex.events]
    assert rows == [("REMOVE_COUNTER", str(w.alpha), "CHARGE", 2),
                    ("MOVE", str(w.alpha), "battlefield->graveyard")], rows


# ------------------------------------------------------------------------------ the cards


@cache
def _supply(code: str):
    return compile_supply("all", code, require_verified=False)  # the records, unverified


def _runner(code: str, cards: list[dict], mana: dict | None = None) -> ScenarioRunner:
    pack = {"set": code, "world": {"life": 20, "seed": 7}, "cards": cards, "steps": []}
    if mana:
        pack["mana"] = mana
    return ScenarioRunner(pack, _supply(code))


def _real(key, name, seat=0, zone="battlefield", **extra) -> dict:
    return {"key": key, "real": name, "zone": zone, "controller": seat, **extra}


def _bear(key, seat=1, zone="battlefield") -> dict:
    return {"key": key, "name": key.title(), "type": "Creature — Bear", "power": "2",
            "toughness": "2", "zone": zone, "controller": seat}


def _zone(r: ScenarioRunner, key: str) -> str:
    return r.world.zone_of(r.handles[key]).kind


EXECUTIONER = 1  # its abilities: [0] the Spirit token as it enters, [1] the exile, [2] the cast


def test_hanged_executioner_is_exiled_as_its_ability_is_activated() -> None:
    """M20 Hanged Executioner, "{3}{W}, Exile this creature: Exile target creature.": the cost is
    paid as the ability is activated (CR 602.2b, 601.2h), so it is in exile while the ability
    waits on the stack, before anyone can respond; then the ability exiles its target."""
    r = _runner("M20", [_real("hang", "Hanged Executioner"), _bear("bear")], {"0": {"W": 1, "C": 3}})
    r.run_step({"op": "activate", "key": "hang", "idx": EXECUTIONER, "seat": 0, "targets": ["bear"],
                "hold": True})
    assert _zone(r, "hang") == ZONE_EXILE and _zone(r, "bear") == ZONE_BATTLEFIELD
    assert len(r.ex.stack.frames) == 1
    r.run_step({"op": "pass"})
    assert _zone(r, "bear") == ZONE_EXILE and not r.world.players[r.p0].mana_pool


def test_removal_in_response_cannot_reach_hanged_executioner() -> None:
    """The opponent answers the ability with a removal spell aimed at the Executioner: it is
    already in exile, paid as the ability was activated, so the spell has no such target and the
    ability exiles its target."""
    r = _runner("M20", [_real("hang", "Hanged Executioner"), _bear("bear"),
                        _real("dis", "Disfigure", seat=1, zone="hand")],
                {"0": {"W": 1, "C": 3}, "1": {"B": 1}})
    r.run_step({"op": "activate", "key": "hang", "idx": EXECUTIONER, "seat": 0, "targets": ["bear"],
                "hold": True})
    with pytest.raises(ValueError, match="illegal target selection: selection:off_population"):
        r.run_step({"op": "cast", "key": "dis", "real": "Disfigure", "controller": 1,
                    "targets": ["hang"], "hold": True})
    r.run_step({"op": "pass"})
    assert _zone(r, "hang") == ZONE_EXILE and _zone(r, "bear") == ZONE_EXILE


def test_hanged_executioner_stays_exiled_when_its_target_is_gone() -> None:
    """Removal in response does not undo the cost: the target bounced, the ability does not
    resolve (CR 608.2b), and the Executioner stays exiled. Were the exile an effect of the ability
    (the F3 fold), it would never have happened, and the Executioner would be back for more."""
    r = _runner("M20", [_real("hang", "Hanged Executioner"), _bear("bear")], {"0": {"W": 1, "C": 3}})
    r.run_step({"op": "activate", "key": "hang", "idx": EXECUTIONER, "seat": 0, "targets": ["bear"],
                "hold": True})
    r.run_step({"op": "move", "key": "bear", "to": "hand"})
    r.run_step({"op": "pass"})
    assert _zone(r, "hang") == ZONE_EXILE and _zone(r, "bear") == "hand"


def test_hanged_executioner_cannot_pay_once_it_is_gone() -> None:
    """The creature already gone: a second activation held behind the first finds nothing to
    exile (CR 113.6, 118.3), and in the graveyard the ability does not exist to be activated."""
    r = _runner("M20", [_real("hang", "Hanged Executioner"), _bear("bear"), _bear("ox")],
                {"0": {"W": 2, "C": 6}})
    r.run_step({"op": "activate", "key": "hang", "idx": EXECUTIONER, "seat": 0, "targets": ["bear"],
                "hold": True})
    with pytest.raises(ValueError, match="window:not_in_battlefield"):
        r.run_step({"op": "activate", "key": "hang", "idx": EXECUTIONER, "seat": 0,
                    "targets": ["ox"]})
    g = _runner("M20", [_real("hang", "Hanged Executioner", zone="graveyard"), _bear("bear")],
                {"0": {"W": 1, "C": 3}})
    with pytest.raises(ValueError, match="window:not_in_battlefield"):
        g.run_step({"op": "activate", "key": "hang", "idx": EXECUTIONER, "seat": 0, "targets": ["bear"]})
    assert g.world.players[g.p0].mana_pool == {"W": 1, "C": 3}  # nothing paid


TROLL = 1  # its abilities: [0] the counter it enters with, [1] the hexproof, [2] the cast


def test_barkhide_troll_enters_with_a_counter_and_spends_it_on_hexproof() -> None:
    """M20 Barkhide Troll: "This creature enters with a +1/+1 counter on it. {1}, Remove a +1/+1
    counter from this creature: This creature gains hexproof until end of turn." The counter comes
    off as the ability is activated; the hexproof comes when it resolves, until end of turn."""
    r = _runner("M20", [_real("troll", "Barkhide Troll", zone="hand")], {"0": {"G": 3}})
    r.run_step({"op": "cast", "key": "troll", "real": "Barkhide Troll"})
    troll = r.handles["troll"]
    assert r.world.cards[troll].counters == {"PLUS_1_PLUS_1": 1}
    r.run_step({"op": "activate", "key": "troll", "idx": TROLL, "seat": 0, "hold": True})
    assert r.world.cards[troll].counters == {} and not r.ex.layers.keyword_of(troll, at.Keyword.HEXPROOF)
    r.run_step({"op": "pass"})
    assert r.ex.layers.keyword_of(troll, at.Keyword.HEXPROOF)
    r.run_step({"op": "end_turn"})
    assert not r.ex.layers.keyword_of(troll, at.Keyword.HEXPROOF)


@pytest.mark.parametrize("respond", [True, False])
def test_barkhide_troll_answers_a_bounce_with_hexproof(respond) -> None:
    """The opponent casts Unsummon at the Troll; activated in response, the Troll's ability resolves
    first (CR 608.1), and Unsummon's only target is then illegal (hexproof, CR 702.11b, 608.2b):
    the Troll stays, one counter lighter. Unanswered, Unsummon returns it to its owner's hand."""
    r = _runner("M20", [_real("troll", "Barkhide Troll", counters={"PLUS_1_PLUS_1": 1}),
                        _real("uns", "Unsummon", seat=1, zone="hand")],
                {"0": {"G": 1}, "1": {"U": 1}})
    r.run_step({"op": "cast", "key": "uns", "real": "Unsummon", "controller": 1,
                "targets": ["troll"], "hold": True})
    if respond:
        r.run_step({"op": "activate", "key": "troll", "idx": TROLL, "seat": 0, "hold": True})
    r.run_step({"op": "pass"})
    assert _zone(r, "uns") == ZONE_GRAVEYARD
    if respond:
        assert _zone(r, "troll") == ZONE_BATTLEFIELD
        assert r.world.cards[r.handles["troll"]].counters == {}
    else:
        assert _zone(r, "troll") == "hand"


def test_barkhide_troll_without_a_counter_cannot_activate() -> None:
    r = _runner("M20", [_real("troll", "Barkhide Troll")], {"0": {"G": 1}})
    with pytest.raises(ValueError, match="cost:remove_counter:PLUS_1_PLUS_1:insufficient_candidates:0<1"):
        r.run_step({"op": "activate", "key": "troll", "idx": TROLL, "seat": 0})
    assert r.world.players[r.p0].mana_pool == {"G": 1}


@pytest.mark.parametrize("counters", [1, 2])
def test_two_activations_compete_for_the_trolls_counters(counters) -> None:
    """Holding priority, a second activation needs a second counter: with one, it can't be paid
    (CR 118.3); with two, both are activated and both counters come off."""
    r = _runner("M20", [_real("troll", "Barkhide Troll", counters={"PLUS_1_PLUS_1": counters})],
                {"0": {"G": 2}})
    r.run_step({"op": "activate", "key": "troll", "idx": TROLL, "seat": 0, "hold": True})
    second = {"op": "activate", "key": "troll", "idx": TROLL, "seat": 0, "hold": True}
    if counters == 1:
        with pytest.raises(ValueError, match="cost:remove_counter"):
            r.run_step(second)
        assert r.world.players[r.p0].mana_pool == {"G": 1} and len(r.ex.stack.frames) == 1
    else:
        r.run_step(second)
        assert len(r.ex.stack.frames) == 2 and not r.world.players[r.p0].mana_pool
    assert r.world.cards[r.handles["troll"]].counters == {}


def test_suspicious_shambler_works_from_the_graveyard_as_a_sorcery() -> None:
    """FDN Suspicious Shambler: "{4}{B}{B}, Exile this card from your graveyard: Create two 2/2
    black Zombie creature tokens. Activate only as a sorcery." It works only in the graveyard (CR
    113.6m) and only at sorcery speed; it exiles itself as the cost."""
    mana = {"0": {"B": 2, "C": 4}}
    r = _runner("FDN", [_real("sham", "Suspicious Shambler", zone="graveyard")], mana)
    r.run_step({"op": "activate", "key": "sham", "idx": 0, "seat": 0})
    assert _zone(r, "sham") == ZONE_EXILE
    zombies = [c for c in r.world.cards.values() if c.identity.name == "Zombie" and c.identity.is_token]
    assert len(zombies) == 2
    b = _runner("FDN", [_real("sham", "Suspicious Shambler")], mana)
    with pytest.raises(ValueError, match="window:not_in_graveyard"):
        b.run_step({"op": "activate", "key": "sham", "idx": 0, "seat": 0})
    t = _runner("FDN", [_real("sham", "Suspicious Shambler", zone="graveyard")], mana)
    t.run_step({"op": "advance_turn"})
    with pytest.raises(ValueError, match="window:sorcery"):
        t.run_step({"op": "activate", "key": "sham", "idx": 0, "seat": 0})
