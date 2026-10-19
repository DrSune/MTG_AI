"""R1a construction-normalization law — docs/DESIGN_ATOM_ONTOLOGY.md §3
(SET-R1a rows), §3 O3 (sort AT CONSTRUCTION, ``AtomArgs.pairs`` :2541
precedent), §6 identity law.

Every SET-R1a field is sorted at construction (frozen ``__post_init__`` +
``object.__setattr__``); ``FAnd``/``FOr`` additionally splice same-class
children. A single-child filter node is KEPT by the node (it cannot replace
itself in its parent) — the unwrap lives at the compiler emission site and
checker V2′ forbids new emission, so these tests pin BOTH halves of that
division of labour.

The final section is the R1a diff-gate B3 EXECUTION PIN: the two
behaviour-changed cards (Negate, Dauntless Survivor) run through the REAL
executor — compiled from the pool with the CURRENT compiler, cast on the
real stack, effect outcomes OBSERVED (never shape-only assertions).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import MTG_bot.core.ability_tree as at
from MTG_bot.core.ability_tree import canonical_json
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_binding import atom, card_id
from MTG_bot.core.test_executor_rung1 import Rung1Case
from MTG_bot.core.test_executor_stack import any_target

_OID_A = "01020304-0506-4708-890a-0b0c0d0e0f10"


def _fa(subtype: str) -> at.FAtom:
    return at.FAtom(pred=at.FAtomPred.TYPE_EQ, string_value=subtype)


def _tap(subtype: str) -> at.Atom:
    """A legal TAP atom (the verb requires a target role — grammar law stays
    in force inside these fixtures)."""
    target = at.Selector(
        at.QConst(1),
        at.SelectorMode.TARGET,
        _fa(subtype),
        zones=(at.Zone(kind=at.ZoneKind.BATTLEFIELD, controller=at.ControllerRef.YOU),),
    )
    return at.Atom(verb=at.Verb.TAP, args=at.AtomArgs(pairs=(("target", target),)))


def _untap(subtype: str) -> at.Atom:
    target = at.Selector(
        at.QConst(1),
        at.SelectorMode.TARGET,
        _fa(subtype),
        zones=(at.Zone(kind=at.ZoneKind.BATTLEFIELD, controller=at.ControllerRef.YOU),),
    )
    return at.Atom(verb=at.Verb.UNTAP, args=at.AtomArgs(pairs=(("target", target),)))


def _card(**over) -> at.CardRecord:
    base = dict(
        oracle_id=_OID_A,
        name="R1a Probe",
        type_line="Creature — Cat",
        types=("Creature",),
        subtypes=("Cat",),
        supertypes=(),
        colors=("W",),
        color_identity=frozenset({"W"}),
        mana_cost=None,
        mana_value=1,
        power=at.QConst(1),
        toughness=at.QConst(1),
        loyalty=None,
        keywords=(),
        abilities=(),
        is_token=False,
    )
    base.update(over)
    return at.CardRecord(**base)


# --------------------------------------------------------------------------
# FAnd / FOr: sort, flatten, single-child policy
# --------------------------------------------------------------------------
def test_fand_children_sorted_by_canonical_json():
    a, b = _fa("Cat"), _fa("Bird")
    assert canonical_json(at.FAnd((a, b))) == canonical_json(at.FAnd((b, a)))
    assert at.FAnd((a, b)) == at.FAnd((b, a))  # value equality (dedup/goldens)
    assert hash(at.FAnd((a, b))) == hash(at.FAnd((b, a)))
    lo, hi = sorted((canonical_json(a), canonical_json(b)))
    got = [canonical_json(c) for c in at.FAnd((b, a)).children]
    assert got == [lo, hi]


def test_for_children_sorted_too():
    a, b = _fa("Cat"), _fa("Bird")
    want = [canonical_json(c) for c in sorted((a, b), key=canonical_json)]
    assert [canonical_json(c) for c in at.FOr((b, a)).children] == want


def test_same_class_child_is_spliced():
    a, b, c = _fa("Cat"), _fa("Bird"), _fa("Wall")
    inner = at.FAnd((a, b))
    outer = at.FAnd((inner, c))
    assert [type(k).__name__ for k in outer.children] == ["FAtom", "FAtom", "FAtom"]
    # order-free after splicing, and idempotent (no re-fire on rebuild)
    again = at.FAnd(outer.children)
    assert canonical_json(again) == canonical_json(outer)


def test_cross_class_child_is_NEVER_spliced():
    """De Morgan shapes are real structure, not a duplicate layer (§3)."""
    a, b = _fa("Cat"), _fa("Bird")
    inner = at.FOr((a, b))
    outer = at.FAnd((inner,))
    assert [type(k).__name__ for k in outer.children] == ["FOr"]
    mixed = at.FAnd((inner, a))  # sorted by canonical_json, not by class name
    assert sorted(type(k).__name__ for k in mixed.children) == ["FAtom", "FOr"]
    assert any(type(k) is at.FOr for k in mixed.children)


def test_single_child_node_is_kept_by_the_node():
    """A node cannot replace itself in its parent: the KEEP-half of the R1a
    law. Emission-side unwrap is the compiler's job (V2′ polices it)."""
    a = _fa("Cat")
    one = at.FAnd((a,))
    assert len(one.children) == 1 and one.children[0] == a
    assert '"tag":"FOr"' in canonical_json(at.FOr((a,)))


def test_empty_wrappers_stay_meaningful():
    """FAnd(()) = universal filter, FOr(()) = matches nothing: both are
    semantics, not phantoms (V2′ only forbids the ONE-child shape)."""
    assert at.FAnd(()).children == ()
    assert at.FOr(()).children == ()


def test_normalization_is_idempotent_under_roundtrip_and_replace():
    a, b, c = _fa("Cat"), _fa("Bird"), _fa("Wall")
    node = at.FAnd((at.FOr((c, a)), b, at.FAnd((b, c))))
    once = canonical_json(node)
    back = at.from_dict("FAnd", at.to_dict(node))
    assert canonical_json(back) == once
    assert canonical_json(dataclasses.replace(node, children=node.children)) == once
    # splicing already happened: no nested FAnd survives
    assert not any(type(k) is at.FAnd for k in node.children)


def test_frozen_law_still_holds():
    node = at.FAnd((_fa("Cat"), _fa("Bird")))
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.children = ()  # the only rewrite channel is __post_init__


# --------------------------------------------------------------------------
# FAtom.colors / EtBState.initial_counters
# --------------------------------------------------------------------------
def test_fatom_colors_membership_set_is_sorted():
    assert at.FAtom(pred=at.FAtomPred.COLOR_IN, colors=("G", "U", "W")).colors == (
        "G",
        "U",
        "W",
    )
    assert at.FAtom(pred=at.FAtomPred.COLOR_IN, colors=("W", "G")).colors == (
        at.FAtom(pred=at.FAtomPred.COLOR_IN, colors=("G", "W")).colors
    )


def test_fatom_color_validation_still_raises():
    for bad in (("W", "W"), ("K",), ("W", "X")):
        with pytest.raises(ValueError):
            at.FAtom(pred=at.FAtomPred.COLOR_IN, colors=bad)
    with pytest.raises(ValueError):  # COLOR_IN needs a non-empty set
        at.FAtom(pred=at.FAtomPred.COLOR_IN, colors=())


def test_etbstate_initial_counters_sorted_by_canonical_json():
    e = at.EtBState(
        initial_counters=(
            (at.CounterKind.PLUS_1_PLUS_1, at.QConst(2)),
            (at.CounterKind.MINUS_1_MINUS_1, at.QConst(1)),
        )
    )
    assert [k.name for k, _ in e.initial_counters] == [
        "MINUS_1_MINUS_1",
        "PLUS_1_PLUS_1",
    ]
    other = at.EtBState(
        initial_counters=(
            (at.CounterKind.MINUS_1_MINUS_1, at.QConst(1)),
            (at.CounterKind.PLUS_1_PLUS_1, at.QConst(2)),
        )
    )
    assert canonical_json(e) == canonical_json(other)
    with pytest.raises(ValueError):  # the no-op rejection is untouched
        at.EtBState(tapped=False, initial_counters=())


# --------------------------------------------------------------------------
# CardRecord.keywords / TokenSpec containers
# --------------------------------------------------------------------------
def test_cardrecord_keywords_sorted_and_order_free():
    kw_vigilance = at.KeywordAbility(keyword=at.Keyword.VIGILANCE)
    kw_trample = at.KeywordAbility(keyword=at.Keyword.TRAMPLE)
    one = _card(keywords=(kw_trample, kw_vigilance))
    two = _card(keywords=(kw_vigilance, kw_trample))
    assert canonical_json(one) == canonical_json(two)
    assert [k.keyword.name for k in one.keywords] == ["TRAMPLE", "VIGILANCE"]


def test_cardrecord_printed_identity_fields_keep_printed_order():
    """§3 IDENTITY rows: oracle-printed fidelity is NOT normalized (§11)."""
    card = _card(
        types=("Creature", "Legend"),
        subtypes=("Cat", "Tiger"),
        supertypes=("Legendary",),
        colors=("U", "W"),
    )
    assert card.types == ("Creature", "Legend")
    assert card.subtypes == ("Cat", "Tiger")
    assert card.colors == ("U", "W")
    assert card.supertypes == ("Legendary",)


def test_cardrecord_abilities_keep_printed_order():
    a = at.StaticAbility(effect=_tap("Cat"))
    b = at.StaticAbility(effect=_untap("Bird"))
    assert _card(abilities=(a, b)).abilities == (a, b)
    assert canonical_json(_card(abilities=(a, b))) != canonical_json(
        _card(abilities=(b, a))
    )


def test_tokenspec_compiler_emitted_containers_are_sorted():
    spec = at.TokenSpec(
        name="Cat",
        type_line="Creature Token — Cat",
        types=("Token", "Creature"),
        subtypes=("Cat", "Kitten"),
        power=at.QConst(1),
        toughness=at.QConst(1),
        keywords=(at.Keyword.TRAMPLE, at.Keyword.HASTE),
        abilities=(),
    )
    assert spec.types == ("Creature", "Token")
    assert spec.subtypes == ("Cat", "Kitten")
    assert spec.keywords == (at.Keyword.HASTE, at.Keyword.TRAMPLE)
    swapped = at.TokenSpec(
        name="Cat",
        type_line="Creature Token — Cat",
        types=("Creature", "Token"),
        subtypes=("Kitten", "Cat"),
        power=at.QConst(1),
        toughness=at.QConst(1),
        keywords=(at.Keyword.HASTE, at.Keyword.TRAMPLE),
        abilities=(),
    )
    assert canonical_json(spec) == canonical_json(swapped)
    with pytest.raises(ValueError):  # validation survives normalization
        at.TokenSpec(
            name="Cat",
            type_line="Creature Token — Cat",
            types=(),
            subtypes=(),
            power=None,
            toughness=None,
            keywords=(),
            abilities=(),
        )


# --------------------------------------------------------------------------
# Fields R1a must NOT touch (TIME / MENU / OPERATOR / SET-R1b)
# --------------------------------------------------------------------------
def test_seq_steps_and_choose_options_keep_their_order():
    a, b = _tap("Cat"), _untap("Bird")
    assert at.Seq((a, b)).steps == (a, b)
    assert canonical_json(at.Seq((a, b))) != canonical_json(at.Seq((b, a)))
    ch = at.Choose(count=at.QConst(1), options=(a, b))
    assert ch.options == (a, b)
    assert canonical_json(at.Choose(at.QConst(1), (a, b))) != canonical_json(
        at.Choose(at.QConst(1), (b, a))
    )


def test_r1b_and_operator_fields_are_untouched():
    """Sorting Cost.parts / additional_costs / hybrid colors is R1b (the same
    order-keyed planner, legality.py:1272) — R1a must not preempt it."""
    generic = at.CostManaGeneric(amount=at.QConst(2))
    tap = at.CostTap()
    assert at.Cost((tap, generic)).parts == (tap, generic)
    hybrid = at.CostManaHybrid(colors=("U", "R"), amount=at.QConst(1))
    assert hybrid.colors == ("U", "R")
    spell = at.SpellAbility(
        kind=at.SpellKind.CREATURE,
        effect=None,
        additional_costs=(at.Cost((tap,)), at.Cost((generic,))),
    )
    assert spell.additional_costs == (at.Cost((tap,)), at.Cost((generic,)))
    params = at.KeywordAbility(keyword=at.Keyword.SCRY, params=(at.QConst(1),))
    assert params.params == (at.QConst(1),)


# --------------------------------------------------------------------------
# The owner's example: functionally-identical wording ⇒ identical bytes
# --------------------------------------------------------------------------
def test_wording_permutations_land_on_one_encoding():
    """ "vigilance and trample" vs "trample and vigilance"; "green or white"
    vs "white or green"; two grant-orderings of the same conjunctive gate."""
    kw_a = at.KeywordAbility(keyword=at.Keyword.VIGILANCE)
    kw_b = at.KeywordAbility(keyword=at.Keyword.TRAMPLE)
    assert canonical_json(_card(keywords=(kw_a, kw_b))) == canonical_json(
        _card(keywords=(kw_b, kw_a))
    )
    c1 = at.FAtom(pred=at.FAtomPred.COLOR_IN, colors=("W", "G"))
    c2 = at.FAtom(pred=at.FAtomPred.COLOR_IN, colors=("G", "W"))
    assert canonical_json(c1) == canonical_json(c2)
    gate1 = at.FAnd(
        (
            _fa("Cat"),
            at.FAnd(
                (
                    at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
                    _fa("Bird"),
                )
            ),
        )
    )
    gate2 = at.FAnd(
        (
            _fa("Bird"),
            at.FAnd(
                (
                    at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
                    _fa("Cat"),
                )
            ),
        )
    )
    assert canonical_json(gate1) == canonical_json(gate2)
    # ... and the spliced single layer is the SAME shape as the flat one
    flat = at.FAnd(
        (
            _fa("Cat"),
            _fa("Bird"),
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
        )
    )
    assert canonical_json(gate1) == canonical_json(flat)


def test_fand_validation_order_of_checks_unchanged():
    """A non-Filter child still raises — normalization never swallows the
    grammar's own type law."""
    with pytest.raises(ValueError):
        at.FAnd(((_fa("Cat"), "not a filter")))
    with pytest.raises(ValueError):
        at.FOr((1,))


# ===========================================================================
# B3 EXECUTION PINS (R1a diff gate): the two behaviour-changed cards, REAL
# compiled records, REAL stack, OBSERVED outcomes. The unwrap (FAnd[FNot] ->
# FNot, FAnd[FAtom] -> FAtom) must be EXECUTION-IDENTICAL, not shape-only.
# ===========================================================================
_ZNR_PATH = Path(__file__).resolve().parents[1] / "data" / "ZNR.json"
_POOL_CACHE: dict = {}


def _compiled_znr(name: str):
    """The card as the CURRENT compiler emits it (real record, not fixture)."""
    if "pool" not in _POOL_CACHE:
        _POOL_CACHE["pool"] = ingest_pool(_ZNR_PATH)
        _POOL_CACHE["registry"] = build_full_registry()
    pool, registry = _POOL_CACHE["pool"], _POOL_CACHE["registry"]
    for raw in pool.values():
        if raw.identity.name == name:
            return compile_card(raw, registry).card
    raise AssertionError(f"{name!r} not in the ZNR pool")


def _target_selector(rec):
    """The target Selector inside the first Atom effect (SpellAbility or
    TriggeredAbility) — the node the emission-site unwrap touches."""
    for ab in rec.abilities:
        effect = getattr(ab, "effect", None)
        if effect is None or not isinstance(effect, at.Atom):
            continue
        for _role, value in effect.args.pairs:
            if isinstance(value, at.Selector):
                return value
    raise AssertionError("no target Selector in the compiled record")


class TestUnwrapExecution(Rung1Case):
    """Gate B3: Negate and Dauntless Survivor run on the real executor."""

    def _give_real(self, rec, seat):
        """World card + the REAL compiled record attached (oracle bridge)."""
        handle = self.world.add_card(
            card_id(
                rec.name,
                power=str(rec.power.value) if rec.power else None,
                toughness=str(rec.toughness.value) if rec.toughness else None,
                type_line=rec.type_line,
                cmc=rec.mana_value,
                oid=rec.oracle_id,
                colors=rec.colors,
            ),
            seat,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle

    # ------------------------------------------------- static halves of the pin
    def test_negate_filter_is_the_bare_unwrapped_fnot(self):
        sel = _target_selector(_compiled_znr("Negate"))
        self.assertIsInstance(sel.filter, at.FNot)  # NOT FAnd[FNot]
        self.assertEqual(sel.filter.inner.pred, at.FAtomPred.TYPE_EQ)

    def test_dauntless_filter_is_the_bare_unwrapped_fatom(self):
        sel = _target_selector(_compiled_znr("Dauntless Survivor"))
        self.assertIsInstance(sel.filter, at.FAtom)  # NOT FAnd[FAtom]
        self.assertEqual(sel.filter.pred, at.FAtomPred.TYPE_EQ)

    # ------------------------------------------------------- Negate, executed
    def test_negate_counters_a_noncreature_spell(self):
        rec_neg = _compiled_znr("Negate")
        zap = self.give(
            "Shock",
            at.SpellKind.INSTANT,
            cost=at.Cost((at.CostManaColor("R", at.QConst(1)),)),
            effect=atom(at.Verb.DEAL_DAMAGE, target=any_target(), amount=at.QConst(2)),
        )
        neg = self._give_real(rec_neg, self.p1)
        self.mana(self.p0, R=1)
        self.mana(self.p1, U=2)
        # the ONE ask is the RUNG-1 counter offer (Negate's stack target is
        # a single candidate and auto-resolves); answer it with the real card
        self.script(str(neg))
        try:
            self.ex_cast(self.p0, zap, targets=(self.p1,))
        finally:
            self.ex.decisions.provider = None
        self.assertEqual(self.zone_kind(zap), ZONE_GRAVEYARD)  # countered
        self.assertEqual(self.zone_kind(neg), ZONE_GRAVEYARD)  # resolved
        self.assertGreaterEqual(len(self.journal_rows("COUNTER")), 1)
        self.assertEqual(self.world.players[self.p1].life, 20)  # damage NEVER ran

    def test_negate_cannot_counter_a_creature_spell_falsifier(self):
        """The FNot[TYPE_EQ Creature] filter, EXECUTED: a creature spell on
        the stack is NOT a legal target, so Negate is never even OFFERED
        (the script is empty — any ask fails loudly), the creature resolves,
        and its ETB trigger still runs the FAtom creature menu."""
        rec_neg = _compiled_znr("Negate")
        rec_ds = _compiled_znr("Dauntless Survivor")
        ds = self._give_real(rec_ds, self.p0)
        neg = self._give_real(rec_neg, self.p1)
        self.mana(self.p0, G=2)
        self.mana(self.p1, U=2)
        self.script()  # zero permitted asks: any ask raises unexpected-ask
        try:
            self.ex_cast(self.p0, ds)
        finally:
            self.ex.decisions.provider = None
        self.assertEqual(self.zone_kind(ds), ZONE_BATTLEFIELD)  # NOT countered
        self.assertEqual(self.journal_rows("COUNTER"), [])
        # the ETB trigger ran anyway (FAtom filter executed; the single
        # candidate — Dauntless herself — auto-resolved):
        self.assertEqual(
            self.world.cards[ds].counters.get(at.CounterKind.PLUS_1_PLUS_1.name, 0),
            1,
        )

    # ------------------------------------------------- Dauntless Survivor, run
    def test_dauntless_etb_target_executes_creature_menu_only(self):
        """Cast the REAL card; the ETB TARGET ask must offer EXACTLY the
        creatures (the bare FAtom[TYPE_EQ Creature] executed in the legality
        lane) and the +1/+1 counter must LAND on the chosen creature."""
        rec_ds = _compiled_znr("Dauntless Survivor")
        other = self.give(
            "Second Creature",
            at.SpellKind.CREATURE,
            cost=at.Cost((at.CostManaColor("G", at.QConst(1)),)),
            type_line="Creature",
            types=("Creature",),
            power="2",
            toughness="2",
            zone=ZONE_BATTLEFIELD,
        )
        enc = self.give(
            "Frozen Enchantment",
            at.SpellKind.ENCHANTMENT,
            type_line="Enchantment",
            types=("Enchantment",),
            zone=ZONE_BATTLEFIELD,
        )
        ds = self._give_real(rec_ds, self.p0)
        self.mana(self.p0, G=2)
        self.script(str(other))  # the ETB target ask picks the other creature
        try:
            self.ex_cast(self.p0, ds)
        finally:
            self.ex.decisions.provider = None
        self.assertEqual(self.zone_kind(ds), ZONE_BATTLEFIELD)
        # the ask really fired and its menu was EXACTLY the two creatures:
        target_asks = [
            vocab
            for vocab, _what in self.asks
            if str(other) in vocab and str(ds) in vocab
        ]
        self.assertTrue(target_asks, f"no creature-target ask in {self.asks}")
        self.assertEqual(set(target_asks[0]), {str(ds), str(other)})
        self.assertNotIn(str(enc), target_asks[0])  # enchantment NOT offered
        # OBSERVED outcome: the counter is on the chosen creature; nothing
        # leaked to Dauntless herself or to the enchantment:
        self.assertEqual(
            self.world.cards[other].counters.get(at.CounterKind.PLUS_1_PLUS_1.name, 0),
            1,
        )
        self.assertEqual(
            self.world.cards[ds].counters.get(at.CounterKind.PLUS_1_PLUS_1.name, 0),
            0,
        )
        self.assertEqual(dict(self.world.cards[enc].counters), {})
