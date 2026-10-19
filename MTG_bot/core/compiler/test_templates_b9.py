"""ZND-4 tests: the b9 flip-sweep bucket (spec KNOWLEDGE/2026-10-19/115).

Laws under test:

1. ONE-ROW-ONE-OUTCOME: every live ZNR row a b9 template claims is
   claimed by exactly that template (single fullmatch, no co-claim); the
   deferred/one-away probes match NOTHING anywhere in the registry (no
   silent partials, no forced lanes — ZND-4a/b/c gap ledger).
2. VERBATIM: each pattern is pinned to the exact corpus sentence it owns.
3. Batch-A carrier widens are ADDITIVE: the coloured Equip backref and
   the "target card" return branch only ADD to the old language; the
   bare-symbol "Equip {B}." (would miscompile the colour) still misses.
4. G-FM2 self-as-legal-target: the cant-be-blocked encoding carries NO
   ``FNot(IS_SOURCE)`` in its blocked-side filter, while the
   while-condition shapes keep theirs.
5. Bucket "B9", priority PINNED 116 (G-FM3).
6. EXECUTOR-OBSERVED falsifiers for every new shape: ETB firing and
   silence, +1/+1 counters through TARGET designation, EOT keyword
   expiry, the life-trigger feed, static while-gates that lose AND
   re-acquire their subject, the attachment-gated keyword grant, the
   QCount census, the scry-then-draw reorder, the filter menus
   (or-flying, noncreature-on-stack), the anthem direction, and the
   runtime blocker-veto whose protection covers the record's OWN source.
"""

from __future__ import annotations

import unittest
from typing import Any

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    CostManaColor,
    CostManaGeneric,
    CostTap,
    CounterKind,
    DeclareBlockersEvent,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    PtDelta,
    PtDirection,
    QConst,
    QCount,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.templates import AbilityOutcome, EffectOutcome
from MTG_bot.core.compiler.templates_b9 import TEMPLATES as TEMPLATES_B9
from MTG_bot.core.compiler.test_templates_b5a import _raw
from MTG_bot.core.compiler.test_templates_b7 import _EQUIP_ETB_SENTENCE, _card_id
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.query import legal_targets
from MTG_bot.core.executor.stack import park
from MTG_bot.core.state import ZONE_GRAVEYARD, GameWorld
from MTG_bot.core.test_executor_binding import BindingCase, atom, card_id, gain
from MTG_bot.core.test_executor_blockers import BlockerCase
from MTG_bot.core.test_executor_layers import LayerCase
from MTG_bot.core.test_executor_layers import record_of as record_of_kw

REG = build_full_registry()


def _tids(sentence: str) -> list[str]:
    return [m.template.tid for m in REG.match(sentence)]


def _outcome(sentence: str) -> Any:
    matches = REG.match(sentence)
    assert len(matches) == 1, (sentence, [m.template.tid for m in matches])
    return matches[0].outcome


def _ability(sentence: str) -> Any:
    out = _outcome(sentence)
    assert isinstance(out, AbilityOutcome), sentence
    return out.ability


def _effect(sentence: str) -> Any:
    out = _outcome(sentence)
    assert isinstance(out, EffectOutcome), sentence
    return out.effect


def _pairs(atom: Any) -> dict:
    return dict(atom.args.pairs)


def _atom(effect: Any) -> Any:
    """Narrow an effect to Atom for BOTH runtime and the checker."""
    assert isinstance(effect, Atom), type(effect).__name__
    return effect


# The fifteen VERBATIM register sentences this bucket owns.
S_ETB_GAIN = "When this creature enters, you gain 3 life."
S_PT_WHILE = "This creature gets +2/+0 as long as you control another Warrior."
S_KW_WHILE = "This creature has deathtouch as long as you control another Cleric."
S_DESTROY_AEF = "Destroy target artifact, enchantment, or creature with flying."
S_ETB_COUNTER = "When this creature enters, put a +1/+1 counter on target creature."
S_ETB_GRANT = (
    "When this creature enters, target creature you control gains "
    "indestructible until end of turn."
)
S_EQUIPPED = "Equipped creature has indestructible."
S_LIFE_OPP = "Whenever you gain life, each opponent loses 1 life."
S_LIFE_SELF = "Whenever you gain life, put a +1/+1 counter on this creature."
S_KABIRA = (
    "Kabira Takedown deals damage equal to the number of creatures you "
    "control to target creature or planeswalker."
)
S_SCRY = "Scry 1, then draw a card."
S_ANTHEM = "Creatures your opponents control get -2/-0 until end of turn."
S_WIZARD = "If you control a Wizard, draw a card."
S_COUNTER = "Counter target noncreature spell."
S_CANT_BLOCK = (
    "{2}, {T}: Target creature with power 2 or less can't be blocked this turn."
)

_VERBATIM = {
    "B9-etb-gain-life": S_ETB_GAIN,
    "B9-pt-while-another-class": S_PT_WHILE,
    "B9-kw-while-another-class": S_KW_WHILE,
    "B9-destroy-artifact-enchantment-flying": S_DESTROY_AEF,
    "B9-etb-put-counter-target": S_ETB_COUNTER,
    "B9-etb-target-gains-indestructible-eot": S_ETB_GRANT,
    "B9-equipped-keyword": S_EQUIPPED,
    "B9-gain-life-each-opponent-loses": S_LIFE_OPP,
    "B9-gain-life-counter-self": S_LIFE_SELF,
    "B9-census-damage-kabira": S_KABIRA,
    "B9-scry-then-draw": S_SCRY,
    "B9-opponents-get-pm-eot": S_ANTHEM,
    "B9-if-wizard-draw": S_WIZARD,
    "B9-counter-noncreature-spell": S_COUNTER,
    "B9-target-cant-be-blocked-self-ok": S_CANT_BLOCK,
}

_EQUIP_OLD = (
    "Equip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)"
)
_EQUIP_NEW = (
    "Equip {2}{G} ({2}{G}: Attach to target creature you control. "
    "Equip only as a sorcery.)"
)


# ---------------------------------------------------------------------------
# section 1 — registry shape, VERBATIM law, one-row-one-outcome, defers
# ---------------------------------------------------------------------------


class TestRegistryShape(unittest.TestCase):
    def test_bucket_and_pinned_priority(self):
        self.assertEqual(len(TEMPLATES_B9), 15)
        self.assertEqual(len({t.tid for t in TEMPLATES_B9}), 15)
        for t in TEMPLATES_B9:
            self.assertIn(t.tid, REG)
            [m] = REG.match(_VERBATIM[t.tid])
            self.assertEqual(m.template.bucket, "B9", t.tid)
            self.assertEqual(m.template.priority, 116, t.tid)  # G-FM3

    def test_verbatim_patterns(self):
        for t in TEMPLATES_B9:
            self.assertIsNotNone(t.pattern.fullmatch(_VERBATIM[t.tid]), t.tid)

    def test_every_b9_row_single_claim(self):
        for sentence in _VERBATIM.values():
            self.assertEqual(len(_tids(sentence)), 1, sentence)

    def test_live_znr_pool_rows_claim_exactly_their_template(self):
        import json
        from pathlib import Path

        from MTG_bot.core.compiler.ingest import split_sentences

        data = json.loads(
            (Path(__file__).resolve().parents[2] / "data" / "ZNR.json").read_text(
                encoding="utf-8"
            )
        )
        sentences = {
            s
            for card in data["data"]["cards"]
            for s in split_sentences(card.get("text") or "")
        }
        seen: dict[str, int] = {t.tid: 0 for t in TEMPLATES_B9}
        for s in sentences:
            tids = _tids(s)
            b9 = [tid for tid in tids if tid.startswith("B9-")]
            if not b9:
                continue
            self.assertEqual(len(tids), 1, (s, tids))  # one row, one outcome
            seen[b9[0]] += 1
        self.assertEqual([tid for tid, n in seen.items() if n == 0], [])

    def test_m21_sentences_never_touch_b9(self):
        import json
        from pathlib import Path

        from MTG_bot.core.compiler.ingest import split_sentences

        path = Path(__file__).resolve().parents[2] / "data" / "M21.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for card in data["data"]["cards"]:
            for s in split_sentences(card.get("text") or ""):
                for t in TEMPLATES_B9:
                    self.assertIsNone(t.pattern.fullmatch(s), (card, s))

    def test_deferred_and_one_away_rows_match_nothing(self):
        # ZND-4a (multi-keyword merge = Type-1 schema decision), ZND-4b
        # (MANDATE_BLOCK has no dispatched run_atom verb — a triggered
        # mandate would raise at resolve), ZND-4c (the all-permanent
        # destroy scope has no executed selector family), plus every
        # one-away probe: NO silent partial anywhere in the registry.
        probes = [
            "Flying, vigilance.",  # ZND-4a
            "Defender, reach.",  # ZND-4a
            "Flying, lifelink.",  # ZND-4a
            (
                "When this creature enters, if it was kicked, all "  # ZND-4b
                "creatures able to block target creature this turn do so."
            ),
            "Destroy all nonland permanents.",  # ZND-4c
            "As long as this creature is on the battlefield, it has +1/+1.",
            "As long as you control a Warrior, this creature gets +2/+2.",
            # FINDING (register, not a regression): Blood Beckoning's
            # singular "Return target creature card from your graveyard to
            # your hand." is one alternation away from the widened B5b
            # carrier and was NEVER covered pre-ZND-4 (old shape =
            # "target permanent card" | "up to two target creature cards").
            # Out of the named union => stays unparsed, no silent partial.
            "Return target creature card from your graveyard to your hand.",
            (
                "Whenever this creature deals combat damage to a player, you "
                "gain 1 life for each Warrior you control."
            ),
            "Equipped creature has first strike.",
            "Return target permanent card from your graveyard to the battlefield.",
            "Whenever you gain life, target opponent loses 1 life.",  # anaphora
            "Equip {B}.",
            "Equip {2}{W}{W} (Attach to target creature you control.)",
        ]
        for s in probes:
            self.assertEqual(_tids(s), [], s)

    def test_counter_spell_stays_b5as_lane(self):
        # The counter LANE belongs to the prior bucket; b9's delta is only
        # the noncreature STACK filter. One row, one outcome.
        self.assertEqual(_tids("Counter target spell."), ["B5a-counter-spell"])


# ---------------------------------------------------------------------------
# section 2 — Batch-A carrier widens are additive
# ---------------------------------------------------------------------------


class TestCarrierWidens(unittest.TestCase):
    def test_equip_old_shape_still_single(self):
        self.assertEqual(_tids(_EQUIP_OLD), ["B5a-equip"])

    def test_equip_coloured_backref_lands_with_a_real_cost(self):
        self.assertEqual(_tids(_EQUIP_NEW), ["B5a-equip"])
        ab = _ability(_EQUIP_NEW)
        assert isinstance(ab, ActivatedAbility)
        self.assertEqual(
            ab.cost.parts,
            (CostManaGeneric(QConst(2)), CostManaColor("G", QConst(1))),
        )

    def test_equip_bare_colour_still_misses(self):
        # no parenthetical backref: the row stays unparsed, never miscompiled
        self.assertEqual(_tids("Equip {B}."), [])

    def test_return_old_shape_same_tid(self):
        # The pre-ZND-4 shapes must keep landing on the same tid — the
        # widen is additive, not a rewrite. (The singular "target creature
        # card" row was never in this carrier; see the FINDING probe in
        # TestRegistryShape.)
        self.assertEqual(
            _tids("Return target permanent card from your graveyard to your hand."),
            ["B5b-return-cards-hand"],
        )
        self.assertEqual(
            _tids(
                "Return up to two target creature cards from your graveyard "
                "to your hand."
            ),
            ["B5b-return-cards-hand"],
        )

    def test_return_target_card_branch(self):
        self.assertEqual(
            _tids("Return target card from your graveyard to your hand."),
            ["B5b-return-cards-hand"],
        )


# ---------------------------------------------------------------------------
# section 3 — per-template IR-tree pins
# ---------------------------------------------------------------------------


class TestB9Trees(unittest.TestCase):
    def test_etb_gain_life(self):
        ab = _ability(S_ETB_GAIN)
        assert isinstance(ab, TriggeredAbility)
        self.assertIsInstance(ab.event, ZoneChangeEvent)
        self.assertIsNone(ab.condition)
        pairs = _pairs(ab.effect)
        self.assertIs(_atom(ab.effect).verb, Verb.GAIN_LIFE)
        self.assertIs(pairs["controller"], ControllerRef.YOU)
        self.assertEqual(pairs["amount"], QConst(3))

    def _while_atom(self, sentence: str, cls: str) -> tuple[Any, dict]:
        ab = _ability(sentence)
        assert isinstance(ab, StaticAbility)
        pairs = _pairs(ab.effect)
        # The gate lives on StaticAbility.condition: the ONLY filter the
        # attached-static registration path reads (the atom duration-role
        # while is silently dropped by the engine — ever-live — FINDING
        # in templates_b9._you_control_a_class).
        self.assertNotIn("duration", pairs)
        cond = ab.condition
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(cond.count, QConst(1))
        inner = cond.inner_filter
        assert isinstance(inner, FAnd)
        # G-FM2 law: the "another" class-gate KEEPS its self-exclusion,
        # INSIDE the per-candidate inner filter (ctx.source = the anchor).
        self.assertIsInstance(inner.children[-1], FNot)
        last: Any = inner.children[-1]
        self.assertIs(last.inner.pred, FAtomPred.IS_SOURCE)
        subs = [n for n in inner.children if isinstance(n, FAtom)]
        self.assertIn(FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value=cls), subs)
        return ab, pairs

    def test_pt_while_another_class(self):
        ab, pairs = self._while_atom(S_PT_WHILE, "Warrior")
        self.assertIs(_atom(ab.effect).verb, Verb.MODIFY_PT)
        self.assertEqual(pairs["power"], PtDelta(PtDirection.INCREASE, QConst(2)))
        self.assertEqual(pairs["toughness"], PtDelta(PtDirection.INCREASE, QConst(0)))
        self.assertEqual(pairs["target"].filter, FAtom(pred=FAtomPred.IS_SOURCE))

    def test_kw_while_another_class(self):
        ab, pairs = self._while_atom(S_KW_WHILE, "Cleric")
        self.assertIs(_atom(ab.effect).verb, Verb.GRANT_ABILITY)
        ability = pairs["ability"]
        assert isinstance(ability, KeywordAbility)
        self.assertIs(ability.keyword, Keyword.DEATHTOUCH)

    def test_destroy_or_flying_selector(self):
        atom_ = _effect(S_DESTROY_AEF)
        self.assertIs(atom_.verb, Verb.DESTROY)
        selector = _pairs(atom_)["target"]
        self.assertIs(selector.mode, SelectorMode.TARGET)
        menu = selector.filter
        assert isinstance(menu, FOr)
        types = [n.string_value for n in menu.children if isinstance(n, FAtom)]
        self.assertEqual(types, ["Artifact", "Enchantment"])
        flyer = menu.children[2]
        assert isinstance(flyer, FAnd)
        kw: Any = flyer.children[1]
        self.assertIs(kw.pred, FAtomPred.KEYWORD_HAS)
        self.assertIs(kw.keyword, Keyword.FLYING)

    def test_etb_counter_target(self):
        ab = _ability(S_ETB_COUNTER)
        assert isinstance(ab, TriggeredAbility)
        pairs = _pairs(ab.effect)
        self.assertIs(_atom(ab.effect).verb, Verb.PUT_COUNTER)
        self.assertIs(pairs["counter_kind"], CounterKind.PLUS_1_PLUS_1)
        self.assertEqual(pairs["count"], QConst(1))
        selector = pairs["target"]
        self.assertIs(selector.mode, SelectorMode.TARGET)  # DESIGNATED
        self.assertEqual(len(selector.filter.children), 1)  # EVERY creature

    def test_etb_grant_indestructible_eot(self):
        ab = _ability(S_ETB_GRANT)
        assert isinstance(ab, TriggeredAbility)
        pairs = _pairs(ab.effect)
        self.assertIs(_atom(ab.effect).verb, Verb.GRANT_ABILITY)
        self.assertIs(pairs["ability"].keyword, Keyword.INDESTRUCTIBLE)
        self.assertIsInstance(pairs["duration"], DurationEot)
        # "target creature YOU CONTROL": the controller conjunct is present
        self.assertEqual(len(pairs["target"].filter.children), 2)

    def test_equipped_keyword(self):
        ab = _ability(S_EQUIPPED)
        assert isinstance(ab, StaticAbility)
        pairs = _pairs(ab.effect)
        self.assertIs(_atom(ab.effect).verb, Verb.GRANT_ABILITY)
        preds = [n.pred for n in pairs["target"].filter.children]
        self.assertIn(FAtomPred.IS_ATTACHED_TO_SOURCE, preds)

    def test_gain_life_heads(self):
        opp_ab = _ability(S_LIFE_OPP)
        self_abil = _ability(S_LIFE_SELF)
        for ab in (opp_ab, self_abil):
            assert isinstance(ab, TriggeredAbility)
            self.assertIsInstance(ab.event, LifeGainedEvent)
            ev: Any = ab.event
            self.assertIs(ev.actor.who, ControllerRef.YOU)
        assert isinstance(opp_ab.effect, Atom)
        opp = _pairs(opp_ab.effect)
        self.assertIs(opp_ab.effect.verb, Verb.LOSE_LIFE)
        self.assertIs(opp["controller"], ControllerRef.ALL_OPPONENTS)
        self.assertEqual(opp["amount"], QConst(1))
        assert isinstance(self_abil.effect, Atom)
        self_ = _pairs(self_abil.effect)
        self.assertEqual(self_["target"].filter, FAtom(pred=FAtomPred.IS_SOURCE))

    def test_census_damage(self):
        atom_ = _effect(S_KABIRA)
        self.assertIs(atom_.verb, Verb.DEAL_DAMAGE)
        pairs = _pairs(atom_)
        self.assertIsInstance(pairs["amount"], QCount)
        census = pairs["amount"].selector
        self.assertIs(census.mode, SelectorMode.ALL)
        self.assertIsInstance(census.count, QUnbounded)
        self.assertIsInstance(pairs["target"].filter, FOr)  # creature OR pw

    def test_scry_then_draw_seq(self):
        seq = _effect(S_SCRY)
        self.assertIsInstance(seq, Seq)
        scry, draw = seq.steps
        self.assertIs(scry.verb, Verb.SCRY)
        self.assertEqual(_pairs(scry)["count"], QConst(1))
        self.assertIs(draw.verb, Verb.DRAW)

    def test_opponents_anthem_direction(self):
        atom_ = _effect(S_ANTHEM)
        self.assertIs(atom_.verb, Verb.MODIFY_PT)
        pairs = _pairs(atom_)
        self.assertEqual(pairs["power"], PtDelta(PtDirection.DECREASE, QConst(2)))
        self.assertEqual(pairs["toughness"], PtDelta(PtDirection.DECREASE, QConst(0)))
        self.assertIsInstance(pairs["duration"], DurationEot)
        # the DIRECTION lane: opponent-owned population, never you
        who = next(
            n
            for n in pairs["target"].filter.children
            if n.pred is FAtomPred.CONTROLLER_IS
        )
        self.assertIs(who.who, ControllerRef.OPPONENT)

    def test_if_wizard_conditional(self):
        cond = _effect(S_WIZARD)
        self.assertIsInstance(cond, Conditional)
        self.assertIs(cond.pred.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(cond.pred.count, QConst(1))
        self.assertIn(
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Wizard"),
            cond.pred.inner_filter.children,
        )
        self.assertIs(cond.else_effect, None)
        self.assertIs(cond.then_effect.verb, Verb.DRAW)

    def test_counter_noncreature_negation(self):
        atom_ = _effect(S_COUNTER)
        self.assertIs(atom_.verb, Verb.COUNTER_SPELL)
        selector = _pairs(atom_)["target"]
        self.assertIs(selector.zone.kind, ZoneKind.STACK)
        neg = selector.filter.children[0]
        self.assertIsInstance(neg, FNot)
        self.assertIs(neg.inner.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(neg.inner.string_value, "Creature")

    def test_cant_blocked_self_ok_has_no_self_exclusion(self):
        # G-FM2: this is NOT the b3 carrier's ability — "Target creature"
        # with no "another": the blocked-side filter keeps the printed
        # POWER_LE bound but DROPS the IS_SOURCE negation.
        ab = _ability(S_CANT_BLOCK)
        assert isinstance(ab, ActivatedAbility)
        self.assertEqual(ab.cost.parts, (CostManaGeneric(QConst(2)), CostTap()))
        pairs = _pairs(ab.effect)
        self.assertIs(_atom(ab.effect).verb, Verb.PREVENT_EFFECT)
        event = pairs["event"]
        assert isinstance(event, DeclareBlockersEvent)
        blocked: Any = event.blocked
        preds = [n.pred for n in blocked.children if isinstance(n, FAtom)]
        self.assertIn(FAtomPred.IS_ANY_TARGET, preds)
        self.assertNotIn(FAtomPred.IS_SOURCE, preds)  # SELF-OK (G-FM2)
        power = next(
            n
            for n in blocked.children
            if isinstance(n, FAtom) and n.pred is FAtomPred.POWER_LE
        )
        self.assertEqual(power.count, QConst(2))
        self.assertIsInstance(pairs["duration"], DurationEot)


# ---------------------------------------------------------------------------
# section 4 — end-to-end compile_card (rows land as CARD abilities)
# ---------------------------------------------------------------------------


class TestCompileEndToEnd(unittest.TestCase):
    def test_instant_counter_row(self):
        raw = _raw("Disenchant the Wrong Thing", (S_COUNTER,), types=("Instant",))
        res = compile_card(raw, REG)
        self.assertEqual([s for s, _ in res.unparsed], [])
        self.assertEqual(len(res.card.abilities), 1)
        spell: Any = res.card.abilities[0]
        effect = spell.effect
        assert isinstance(effect, Atom)
        self.assertIs(effect.verb, Verb.COUNTER_SPELL)

    def test_creature_trigger_row(self):
        raw = _raw(
            "Sage Adept",
            (S_ETB_GAIN,),
            types=("Creature",),
            subtypes=("Human", "Wizard"),
            power_raw="1",
            toughness_raw="3",
        )
        res = compile_card(raw, REG)
        self.assertEqual([s for s, _ in res.unparsed], [])
        # A permanent carries a SpellAbility shell (effect=None) alongside
        # its compiled abilities; the trigger is the TriggeredAbility.
        trigs = [ab for ab in res.card.abilities if isinstance(ab, TriggeredAbility)]
        self.assertEqual(len(trigs), 1)
        [ab] = trigs
        self.assertIs(_atom(ab.effect).verb, Verb.GAIN_LIFE)

    def test_anthem_spell_row(self):
        raw = _raw("War Crier's Chant", (S_ANTHEM,), types=("Sorcery",))
        res = compile_card(raw, REG)
        self.assertEqual([s for s, _ in res.unparsed], [])
        spell: Any = res.card.abilities[-1]
        effect = spell.effect
        assert isinstance(effect, Atom)
        self.assertIs(effect.verb, Verb.MODIFY_PT)


# ---------------------------------------------------------------------------
# section 5 — executor-observed falsifiers
# ---------------------------------------------------------------------------


def _enter_atom() -> Atom:
    """A hand→battlefield MOVE_ZONE op (the proven landfall-enter idiom):
    the trigger is fired by the ENGINE's zone journal, not a fixture."""
    return Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAnd(children=()),
                        Zone(ZoneKind.HAND, ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
            )
        ),
    )


class EtbCase(BindingCase):
    """BindingCase + the self-enters harness: attach the compiled trigger
    to a card IN HAND, then walk it onto the battlefield through the
    executor; TARGET designation answers come from a provider."""

    def sage(self, sentence: str, target_answer=None):
        ability = _ability(sentence)
        handle = self.world.add_card(card_id("Sage", "1", "3"), self.p0, "hand")
        self.ex.attach_card(handle, self.record_for(handle, [ability]))
        if target_answer is not None:
            self.ex.decisions.provider = lambda vocab, what: (
                str(target_answer)
                if str(target_answer) in [str(v) for v in vocab]
                else vocab[0]
            )
        return handle

    def walk_in(self, handle):
        self.ex.execute(
            _enter_atom(),
            source=handle,
            controller=self.p0,
            bindings={"cards": handle},
        )


class TestExecutorEtbGainLife(EtbCase):
    def test_self_enters_gains_life_once(self):
        sage = self.sage(S_ETB_GAIN)
        before = self.life(self.p0)
        self.walk_in(sage)
        self.assertEqual(self.life(self.p0), before + 3)
        self.assertEqual(self.world.zone_of(sage).kind, "battlefield")
        # a turn boundary does NOT re-fire the enters trigger
        self.ex.end_turn()
        self.assertEqual(self.life(self.p0), before + 3)

    def test_exit_is_silent(self):
        sage = self.sage(S_ETB_GAIN)
        self.walk_in(sage)
        after = self.life(self.p0)
        self.world.move_to_zone(sage, self.p0, ZONE_GRAVEYARD)
        self.assertEqual(self.life(self.p0), after)

    def test_opponent_entrance_never_pays_you(self):
        sage = self.sage(S_ETB_GAIN)
        theirs = self.world.add_card(card_id("Rival", "1", "1"), self.p1, "hand")
        before = self.life(self.p0)
        self.ex.execute(
            _enter_atom(),
            source=theirs,
            controller=self.p1,
            bindings={"cards": theirs},
        )
        self.assertEqual(self.life(self.p0), before)  # to BF_YOU: not theirs
        self.walk_in(sage)  # own enters still works
        self.assertEqual(self.life(self.p0), before + 3)


class TestExecutorEtbTargetDesignation(EtbCase):
    def test_etb_counter_moves_counters_and_power(self):
        mate = self.world.add_card(card_id("Mate", "2", "2"), self.p0, "battlefield")
        sage = self.sage(S_ETB_COUNTER, target_answer=mate)
        self.walk_in(sage)
        state = self.world.cards[mate]
        self.assertEqual(state.counters.get(CounterKind.PLUS_1_PLUS_1.name), 1)
        # r19a: the counter layer folds only when the live counter map is
        # passed (CR 613.3b — counters sit above the timestamp layer).
        self.assertEqual(
            self.ex.ledger.effective_pt(
                state.identity, mate, self.world.cards[mate].counters
            ),
            (3, 3),
        )

    def test_etb_grant_wears_off_at_end_of_turn(self):
        mate = self.world.add_card(card_id("Mate", "2", "2"), self.p0, "battlefield")
        sage = self.sage(S_ETB_GRANT, target_answer=mate)
        self.walk_in(sage)
        self.assertTrue(self.ex.layers.keyword_of(mate, Keyword.INDESTRUCTIBLE))
        self.ex.end_turn()
        self.assertFalse(self.ex.layers.keyword_of(mate, Keyword.INDESTRUCTIBLE))


class TestExecutorLifeTriggers(EtbCase):
    def test_gain_life_drains_each_opponent(self):
        watch = self.watch
        self.ex.attach_card(watch, self.record_for(watch, [_ability(S_LIFE_OPP)]))
        self.ex.execute(gain(3), source=watch, controller=self.p0)
        self.assertEqual(self.life(self.p0), 23)
        self.assertEqual(self.life(self.p1), 19)
        # LOSING life is not gaining it: the LifeGained feed is one-way
        self.ex.execute(
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=QConst(2)),
            source=watch,
            controller=self.p0,
        )
        self.assertEqual(self.life(self.p0), 21)
        self.assertEqual(self.life(self.p1), 19)  # no second drain

    def test_gain_life_counters_the_source(self):
        watch = self.watch
        self.ex.attach_card(watch, self.record_for(watch, [_ability(S_LIFE_SELF)]))
        self.ex.execute(gain(1), source=watch, controller=self.p0)
        self.assertEqual(
            self.world.cards[watch].counters.get(CounterKind.PLUS_1_PLUS_1.name), 1
        )
        self.ex.execute(gain(1), source=watch, controller=self.p0)
        self.assertEqual(
            self.world.cards[watch].counters.get(CounterKind.PLUS_1_PLUS_1.name), 2
        )
        self.assertEqual(
            self.ex.ledger.effective_pt(
                self.world.cards[watch].identity,
                watch,
                self.world.cards[watch].counters,
            ),
            (4, 4),  # the 2/2 watch, twice countered
        )


class TestExecutorStaticWhileGates(LayerCase):
    def test_pt_gate_loses_and_regains_its_subject(self):
        carrier = self.world.add_card(
            card_id("Dragonmaster", "2", "2", type_line="Creature — Warrior"),
            self.p0,
        )
        self.world.move_to_zone(carrier, self.p0, "battlefield")
        self.attach(carrier, [_ability(S_PT_WHILE)])
        # alone, the carrier is NOT "another Warrior" for itself (G-FM2)
        self.assertEqual(self.pt(carrier), (2, 2))
        warrior = self.world.add_card(
            card_id("Rouseabout", "1", "1", type_line="Creature — Warrior"),
            self.p0,
        )
        self.world.move_to_zone(warrior, self.p0, "battlefield")
        self.settle()
        self.assertEqual(self.pt(carrier), (4, 2))
        # the gate DIES with its subject...
        self.world.move_to_zone(warrior, self.p0, ZONE_GRAVEYARD)
        self.settle()
        self.assertEqual(self.pt(carrier), (2, 2))
        # ...and RE-ACQUIRES it on reanimation (layers re-judge, not freeze)
        self.world.move_to_zone(warrior, self.p0, "battlefield")
        self.settle()
        self.assertEqual(self.pt(carrier), (4, 2))

    def test_keyword_gate_follows_the_same_lane(self):
        carrier = self.world.add_card(
            card_id("Cleric-Anchor", "2", "2", type_line="Creature — Cleric"),
            self.p0,
        )
        self.world.move_to_zone(carrier, self.p0, "battlefield")
        self.attach(carrier, [_ability(S_KW_WHILE)])
        self.assertFalse(self.ex.layers.keyword_of(carrier, Keyword.DEATHTOUCH))
        cleric = self.world.add_card(
            card_id("Acolyte", "1", "1", type_line="Creature — Cleric"), self.p0
        )
        self.world.move_to_zone(cleric, self.p0, "battlefield")
        self.settle()
        self.assertTrue(self.ex.layers.keyword_of(carrier, Keyword.DEATHTOUCH))
        self.world.move_to_zone(cleric, self.p0, ZONE_GRAVEYARD)
        self.settle()
        self.assertFalse(self.ex.layers.keyword_of(carrier, Keyword.DEATHTOUCH))

    def test_opponent_class_never_opens_the_gate(self):
        carrier = self.world.add_card(
            card_id("Anchor", "2", "2", type_line="Creature — Warrior"), self.p0
        )
        self.world.move_to_zone(carrier, self.p0, "battlefield")
        self.attach(carrier, [_ability(S_PT_WHILE)])
        rival = self.world.add_card(
            card_id("Rival Warrior", "1", "1", type_line="Creature — Warrior"),
            self.p1,
        )
        self.world.move_to_zone(rival, self.p1, "battlefield")
        self.settle()
        self.assertEqual(self.pt(carrier), (2, 2))  # not "you control"


class TestExecutorAttachmentGate(LayerCase):
    def test_equipped_creature_gains_and_loses_the_keyword(self):
        gear = self.world.add_card(
            _card_id("Test Knife", "Artifact — Equipment"), self.p0, "battlefield"
        )
        host = self.world.add_card(card_id("Host", "2", "2"), self.p0, "battlefield")
        self.attach(gear, [_ability(S_EQUIPPED)])
        self.assertFalse(self.ex.layers.keyword_of(host, Keyword.INDESTRUCTIBLE))
        # attach through the EXECUTED b7-equip-etb ATTACH atom (carrier)
        attach_atom = _ability(_EQUIP_ETB_SENTENCE).effect
        self.ex.execute(
            attach_atom,
            source=gear,
            controller=self.p0,
            bindings={"equipment": gear, "target": host},
        )
        self.assertEqual(self.ex.attachments.get(gear), host)
        self.settle()
        self.assertTrue(self.ex.layers.keyword_of(host, Keyword.INDESTRUCTIBLE))
        # unattached again: gear leaves the battlefield THROUGH THE EXECUTOR
        # (the journal lane pops the attachment edge; a raw world.move
        # bypasses it — that is NOT the engine lane and must not be used).
        self.ex.execute(
            Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAnd(children=()),
                                Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                            ),
                        ),
                        ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                    )
                ),
            ),
            source=gear,
            controller=self.p0,
            bindings={"cards": gear},
        )
        self.assertIsNone(self.ex.attachments.get(gear))
        self.settle()
        self.assertFalse(self.ex.layers.keyword_of(host, Keyword.INDESTRUCTIBLE))


class TestExecutorEffectShapes(BindingCase):
    def test_census_damage_counts_yours_alone(self):
        # Kabira shape: 3 friendly creatures deal 3 — lethal to a 2/2 ...
        beta = self.world.add_card(card_id("Beta", "2", "2"), self.p1, "battlefield")
        for i in (1, 2):
            self.world.add_card(card_id(f"Help{i}", "1", "1"), self.p0, "battlefield")
        self.ex.execute(
            _effect(S_KABIRA),
            source=self.watch,
            controller=self.p0,
            bindings={"target": beta},
        )
        self.assertEqual(self.world.zone_of(beta).kind, "graveyard")
        # ... while ONE friendly creature deals 1 — the same 2/2 survives.
        # The census counts creatures you control, and the ability SOURCE
        # rides that census when it is a creature: here the source is an
        # ARTIFACT, so exactly one creature (Lone) contributes.
        world = GameWorld(num_players=2, start_life=20, master_seed=99)
        p0, p1 = world.player_order
        watcher = world.add_card(
            card_id("Observer", type_line="Artifact"), p0, "battlefield"
        )
        world.add_card(card_id("Lone", "1", "1"), p0, "battlefield")
        target = world.add_card(card_id("Target", "2", "2"), p1, "battlefield")
        ex = Executor(world)
        ex.execute(
            _effect(S_KABIRA),
            source=watcher,
            controller=p0,
            bindings={"target": target},
        )
        self.assertEqual(world.zone_of(target).kind, "battlefield")

    def test_anthem_hits_only_the_opponents_and_expires(self):
        theirs = self.world.add_card(card_id("Enemy", "3", "3"), self.p1, "battlefield")
        mine = self.world.add_card(card_id("Ally", "3", "3"), self.p0, "battlefield")
        self.ex.execute(_effect(S_ANTHEM), source=self.watch, controller=self.p0)
        self.assertEqual(
            self.ex.ledger.effective_pt(self.world.cards[theirs].identity, theirs),
            (1, 3),
        )
        self.assertEqual(
            self.ex.ledger.effective_pt(self.world.cards[mine].identity, mine),
            (3, 3),
        )
        self.ex.end_turn()
        self.assertEqual(
            self.ex.ledger.effective_pt(self.world.cards[theirs].identity, theirs),
            (3, 3),
        )

    def test_conditional_gate_live_and_dead(self):
        # The compiled effect is a Conditional TREE, not a bare Atom: it
        # rides apply_effect (the executor's Effect-tree lane).
        hand_before = len(self.zone(self.p0, "hand"))
        self.ex.apply_effect(_effect(S_WIZARD), source=self.watch, controller=self.p0)
        self.assertEqual(len(self.zone(self.p0, "hand")), hand_before)  # dead gate
        wiz = self.world.add_card(
            card_id("Warden", "1", "1", type_line="Creature — Wizard"),
            self.p0,
            "battlefield",
        )
        self.ex.apply_effect(_effect(S_WIZARD), source=self.watch, controller=self.p0)
        self.assertEqual(len(self.zone(self.p0, "hand")), hand_before + 1)  # live
        self.world.move_to_zone(wiz, self.p0, ZONE_GRAVEYARD)
        self.ex.apply_effect(_effect(S_WIZARD), source=self.watch, controller=self.p0)
        self.assertEqual(len(self.zone(self.p0, "hand")), hand_before + 1)

    def test_destroy_menu_and_execution(self):
        selector = _pairs(_effect(S_DESTROY_AEF))["target"]
        art = self.world.add_card(_card_id("Hoard", "Artifact"), self.p1, "battlefield")
        ench = self.world.add_card(
            _card_id("Binding", "Enchantment"), self.p1, "battlefield"
        )
        flyer = self.world.add_card(
            card_id("Flea", "1", "1", type_line="Creature — Insect"),
            self.p1,
            "battlefield",
        )
        self.ex.attach_card(
            flyer,
            record_of_kw(
                [],
                "Flea",
                self.world.cards[flyer].identity.oracle_id,
                keywords=(KeywordAbility(keyword=Keyword.FLYING),),
            ),
        )
        # the live-keyword oracle (KEYWORD_HAS, 14f) answers from the
        # layer registry's derived maps: attach_card alone does not
        # refresh them — one recompute pass is needed (every public
        # executor op ends with one; this query-only test has no op).
        self.ex.layers.recompute()
        ground = self.world.add_card(
            card_id("Groundling", "1", "1"), self.p1, "battlefield"
        )
        slot = legal_targets(
            self.world, self.ex, selector, source=self.watch, controller=self.p0
        )
        self.assertEqual(sorted(slot.candidates), sorted([art, ench, flyer]))
        self.assertNotIn(ground, slot.candidates)
        # and the DESTROY really removes the designated enchantment
        self.ex.execute(
            _effect(S_DESTROY_AEF),
            source=self.watch,
            controller=self.p0,
            bindings={"target": ench},
        )
        self.assertEqual(self.world.zone_of(ench).kind, "graveyard")

    def test_counter_noncreature_menu_on_the_stack(self):
        selector = _pairs(_effect(S_COUNTER))["target"]
        # The stack is not a player zone: spells get there through the
        # ENGINE's own park lane (the CR 601.2h hand->stack move that the
        # real cast fold uses), never through add_card.
        inst = self.world.add_card(
            card_id("Zap", cmc=1, type_line="Instant"), self.p1, "hand"
        )
        sorc = self.world.add_card(
            card_id("Stomp", cmc=2, type_line="Sorcery"), self.p1, "hand"
        )
        cre = self.world.add_card(
            card_id("Goblin", "1", "1", type_line="Creature — Goblin"),
            self.p1,
            "hand",
        )
        park(self.ex, self.p1, inst)
        park(self.ex, self.p1, sorc)
        park(self.ex, self.p1, cre)
        slot = legal_targets(
            self.world, self.ex, selector, source=self.watch, controller=self.p0
        )
        self.assertEqual(sorted(slot.candidates), sorted([inst, sorc]))
        self.assertNotIn(cre, slot.candidates)  # the FNot(TYPE_EQ) lane is live

    def test_scry_then_draw_reorders_then_draws(self):
        # "Scry N, then draw a card." compiles to a Seq tree — the
        # executor lane for trees is apply_effect (execute takes one Atom).
        lib_before = list(self.zone(self.p0, "library"))
        self.ex.apply_effect(
            _effect(S_SCRY),
            source=self.watch,
            controller=self.p0,
            decisions=("bottom",),
        )
        # Observed lane (CR 701.1, entries top-LAST): the viewed top card
        # sinks under the whole library; the DRAW then takes the NEW top —
        # the OLD second card. The scry changed WHAT was drawn.
        self.assertEqual(self.zone(self.p0, "hand"), [lib_before[-2]])
        self.assertEqual(
            self.zone(self.p0, "library"),
            [lib_before[-1]] + lib_before[:-2],
        )

    def test_scry_top_keeps_the_order(self):
        lib_before = list(self.zone(self.p0, "library"))
        self.ex.apply_effect(
            _effect(S_SCRY),
            source=self.watch,
            controller=self.p0,
            decisions=("top",),
        )
        self.assertEqual(self.zone(self.p0, "hand"), [lib_before[-1]])
        self.assertEqual(self.zone(self.p0, "library"), lib_before[:-1])


class TestExecutorBlockerVetoSelfOk(BlockerCase):
    """The G-FM2 scenario, observed at DECLARE_BLOCKERS: the protection's
    designated target MAY BE the record's own source (no IS_SOURCE veto),
    and only power-2-or-less attackers are inside the printed bound."""

    def test_protection_covers_the_source_and_excludes_its_attacker(self):
        guide = self.synth("Guide", 2, 2, self.p0)  # attacker AND own target
        buddy = self.synth("Buddy", 2, 2, self.p0)
        blocky = self.synth("Blocky", 2, 2, self.p1)
        self.begin()
        self.ex.execute(
            _ability(S_CANT_BLOCK).effect,
            source=guide,
            controller=self.p0,
            bindings={"target": guide},
        )
        self.answers[f"block:{blocky}"] = str(buddy)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # the protected 2/2 is OFF the blocker's menu even though it is the
        # record's own source (Sneaking-Guide diagnosis, pinned):
        vocab = self.vocab_for(blocky)
        self.assertNotIn(str(guide), vocab)
        self.assertIn(str(buddy), vocab)
        self.assertEqual(self.blocked_map(), {str(buddy): [str(blocky)]})
        # Buddy dies to Blocky; the protected Guide walks in for 2.
        self.assertEqual(self.world.players[self.p1].life, 18)

    def test_power_bound_excludes_a_big_attacker(self):
        tiny = self.synth("Tiny", 1, 1, self.p0)
        big = self.synth("Big", 4, 4, self.p0)
        blocky = self.synth("Blocky", 2, 2, self.p1)
        self.begin()
        self.ex.execute(
            _ability(S_CANT_BLOCK).effect,
            source=tiny,
            controller=self.p0,
            bindings={"target": tiny},
        )
        self.answers[f"block:{blocky}"] = str(big)
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        # Big (power 4 > 2) is OUTSIDE the printed bound: still blockable.
        self.assertIn(str(big), self.vocab_for(blocky))
        self.assertNotIn(str(tiny), self.vocab_for(blocky))
        self.assertEqual(self.blocked_map(), {str(big): [str(blocky)]})
        self.assertEqual(self.world.players[self.p1].life, 19)  # Tiny's 1 gets in


if __name__ == "__main__":
    unittest.main()
