"""ZND-5 tests: the b10 spell-kind bucket (spec KNOWLEDGE/2026-10-19/121).

Laws under test:

1. ONE-ROW-ONE-OUTCOME: each of the six live ZNR rows b10 claims is
   claimed by exactly one template; every named-defer row (ZND-5a..f,
   the Relic Amulet removal activation) matches NOTHING anywhere in the
   registry — no silent partials, no forced lanes.
2. VERBATIM + STRUCTURE: patterns own the exact corpus sentences; the
   conjunctive head is FOr(TYPE_EQ Instant, TYPE_EQ Sorcery,
   SUBTYPE_EQ Wizard) with actor CONTROLLER_IS YOU. ATOM-KIND is a
   STRUCTURAL pin (engine word-tests all three type predicates
   identically, quantity.py:726 — behaviorally neutral today; SUBTYPE_EQ
   is CR-correct IR per gate [G-A1] correction). THE P0 EXECUTOR AXIS:
   never-fire / always-fire — matching-kind positive AND non-matching
   negative per trigger board.
3. REGISTRY LAWS: bucket "B10", priority PINNED 118 (G-A7: strictly
   above b9=116 and every other bucket); regex-disjointness probe — the
   conjunctive head never co-claims b2b's Cat/Dog/noncreature/colored
   cast heads, and b5a/b9's counter lanes keep their sentences.
4. EXECUTOR-OBSERVED falsifiers (P0 for this round): every cast-trigger
   ships a MATCHING-kind positive (instant cast fires; Wizard creature
   cast fires — the SUBTYPE_EQ axis; sorcery cast fires) AND a
   NON-MATCHING negative (non-Wizard creature cast stays silent — an
   always-firing cast-trigger is the T6 class). Anticognition s1: the
   FOr menu covers creature AND planeswalker AND excludes an instant;
   the counter fires on PASS (zone + event) and the FLAT unless cost
   pays through the payer-seat kickback lane (verbs.py:1926).
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from typing import Any

from MTG_bot.core.ability_tree import (
    CastSpellEvent,
    ControllerRef,
    Cost,
    CostManaColor,
    CounterKind,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    OptionalEffect,
    PtDelta,
    QConst,
    SpellKind,
    TriggeredAbility,
    Verb,
    ZoneKind,
)
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.templates import AbilityOutcome, EffectOutcome
from MTG_bot.core.compiler.templates_b10 import TEMPLATES as TEMPLATES_B10
from MTG_bot.core.executor.query import legal_targets
from MTG_bot.core.executor.stack import cast, park
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
)
from MTG_bot.core.test_executor_binding import card_id
from MTG_bot.core.test_executor_layers import record_of as record_of_kw
from MTG_bot.core.test_executor_rung1 import Rung1Case
from MTG_bot.core.test_executor_stack import StackCase, spell_rec

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
    assert isinstance(out.ability, TriggeredAbility)
    return out.ability


def _effect(sentence: str) -> Any:
    out = _outcome(sentence)
    assert isinstance(out, EffectOutcome), sentence
    return out.effect


def _pairs(atom: Any) -> dict:
    return dict(atom.args.pairs)


def _pick(answer: Any):
    def prov(vocab, what):
        for v in vocab:
            if str(v) == str(answer):
                return v
        return vocab[0]

    return prov


def _prov_vocab(want: str):
    def prov(vocab, what):
        return want if want in vocab else vocab[0]

    return prov


# The six VERBATIM register sentences this bucket owns (spec /121).
S_FLYING = (
    "Whenever you cast an instant, sorcery, or Wizard spell, this "
    "creature gains flying until end of turn."
)
S_MAY_DRAW = (
    "Whenever you cast an instant, sorcery, or Wizard spell, you may draw a card."
)
S_CHARGE = (
    "Whenever you cast an instant, sorcery, or Wizard spell, put a "
    "charge counter on this artifact."
)
S_DAMAGE = (
    "Whenever you cast an instant, sorcery, or Wizard spell, this "
    "creature deals 1 damage to any target."
)
S_PT = (
    "Whenever you cast an instant, sorcery, or Wizard spell, this "
    "creature gets +2/+0 until end of turn."
)
S_COUNTER = (
    "Counter target creature or planeswalker spell unless its controller pays {2}."
)

OWNED: dict[str, str] = {
    "B10-cast-kw-eot-self": S_FLYING,
    "B10-cast-may-draw": S_MAY_DRAW,
    "B10-cast-charge-self": S_CHARGE,
    "B10-cast-self-damage-any": S_DAMAGE,
    "B10-cast-self-pt-eot": S_PT,
    "B10-counter-unless-cw-pw": S_COUNTER,
}

# Named-defer rows (spec /121 SPEC-GATE REVISIONS) — must match NOTHING.
DEFER_ROWS: dict[str, str] = {
    # ZND-5a: COPY has NO executor dispatch; never template a copy that
    # cannot copy (FM2 law).
    "ZND-5a lithoform": "{3}, {T}: Copy target instant or sorcery spell you control.",
    # ZND-5b: next-spell replacement windows (+ anaphora twin).
    "ZND-5b stormcaller": "When this creature enters, copy the next "
    "instant or sorcery spell with mana value 2 or less you cast this "
    "turn when you cast it.",
    "ZND-5b stormcaller-kicked": "If this creature was kicked, copy that "
    "spell twice instead.",
    "ZND-5b kaza": "{T}: The next instant or sorcery spell you cast this "
    "turn costs {X} less to cast, where X is the number of Wizards you "
    "control as this ability resolves.",
    # ZND-5c: mana-restriction lane absent.
    "ZND-5c base-camp": "Spend this mana only to cast a Cleric, Rogue, "
    "Warrior, or Wizard spell or to activate an ability of a Cleric, "
    "Rogue, Warrior, or Wizard.",
    # ZND-5d: targeted-BY event absent.
    "ZND-5d myriad": "When this creature becomes the target of a spell, "
    "sacrifice it and create a number of 1/1 colorless Construct "
    "artifact creature tokens equal to its power.",
    # ZND-5e: Anticognition s2 threshold/instead replacement window.
    "ZND-5e anticognition-s2": "If an opponent has eight or more cards "
    "in their graveyard, instead counter that spell, then scry 2.",
    # ZND-5f: Master of Winds PT-pair choice fork.
    "ZND-5f master-of-winds": "Whenever you cast an instant, sorcery, or "
    "Wizard spell, you may have this creature's base power and toughness "
    "become 4/1 or 1/4 until end of turn.",
    # Carried (ZND-3d family): Relic Amulet's removal activation —
    # quantity-of-removed-counters damage has no lane; the card stays a
    # 2-row residue feeding PC-2.
    "relic-removal": "{2}, {T}, Remove all charge counters from this "
    "artifact: It deals that much damage to target creature.",
}

# The neighbour heads b10 must stay regex-disjoint from (G-A7 probe).
NEIGHBOUR_HEADS: dict[str, str] = {
    "B2b-cast-cat-create-dog": "Whenever you cast a Cat spell, create a "
    "1/1 white Cat creature token.",
    "B2b-cast-dog-create-cat": "Whenever you cast a Dog spell, create a "
    "1/1 green Dog creature token.",
    "B2b-noncreature-counter": "Whenever you cast a noncreature spell, "
    "put a +1/+1 counter on this creature.",
    "B2b-colored-cast-counter": "Whenever you cast a spell that's white, "
    "blue, black, or red, put a +1/+1 counter on this creature.",
    "B5a-counter-unless-spell": "Counter target spell unless its controller pays {3}.",
    "B5a-counter-unless-sps": "Counter target instant or sorcery spell "
    "unless its controller pays {2}.",
    "B9-counter-noncreature-spell": "Counter target noncreature spell.",
}


class TestRegistryLaws(unittest.TestCase):
    def test_bucket_and_priority_pinned(self) -> None:
        self.assertTrue(TEMPLATES_B10)
        for t in TEMPLATES_B10:
            self.assertEqual(t.bucket, "B10")
            # G-A7: 118 strictly above the whole ladder (b9=116 tops the
            # 100/110/112/114 ladder). A tie would let the tid-asc
            # tiebreak starve b10 rows.
            self.assertEqual(t.priority, 118)
        others = [t.priority for t in REG.all() if t.bucket != "B10"]
        self.assertGreater(118, max(others))

    def test_six_rows_single_claim(self) -> None:
        for tid, sentence in OWNED.items():
            self.assertEqual(_tids(sentence), [tid], sentence)

    def test_defers_match_nothing(self) -> None:
        for label, row in DEFER_ROWS.items():
            self.assertEqual(_tids(row), [], label)

    def test_regex_disjointness_from_neighbour_heads(self) -> None:
        # G-A7 probe: the conjunctive head must not steal b2b's Cat/Dog/
        # noncreature/colored cast heads, nor b5a/b9's counter lanes;
        # each neighbour sentence keeps EXACTLY its historical owner.
        for tid, sentence in NEIGHBOUR_HEADS.items():
            self.assertEqual(_tids(sentence), [tid], sentence)

    def test_head_is_type_instant_type_sorcery_subtype_wizard(self) -> None:
        # [G-A1] STRUCTURAL pin (atom-kind is behaviorally neutral today —
        # the engine word-tests all three type predicates identically,
        # quantity.py:726): "Wizard" MUST be SUBTYPE_EQ because that is
        # the CR-correct IR; a TYPE_EQ encoding would work today and
        # break the day the predicates split.
        for sentence in (S_FLYING, S_MAY_DRAW, S_CHARGE, S_DAMAGE, S_PT):
            ev = _ability(sentence).event
            assert isinstance(ev, CastSpellEvent)
            assert isinstance(ev.filter, FOr)
            kids = ev.filter.children
            self.assertEqual(len(kids), 3)
            kinds = sorted(
                (k.pred.name, k.string_value)
                for k in kids
                if isinstance(k, FAtom)
                and k.pred in (FAtomPred.TYPE_EQ, FAtomPred.SUBTYPE_EQ)
            )
            self.assertEqual(
                kinds,
                sorted(
                    [
                        ("TYPE_EQ", "Instant"),
                        ("TYPE_EQ", "Sorcery"),
                        ("SUBTYPE_EQ", "Wizard"),
                    ]
                ),
                sentence,
            )
            assert isinstance(ev.actor, FAtom)
            self.assertIs(ev.actor.pred, FAtomPred.CONTROLLER_IS)
            self.assertIs(ev.actor.who, ControllerRef.YOU)

    def test_no_subtype_word_as_type_eq_anywhere(self) -> None:
        # Registry-wide guard for the B10 heads: no cast-filter may
        # encode a creature SUBTYPE as TYPE_EQ (the general never-fire
        # shape — Wizard/Cat/Dog).
        def walk(f: Any):
            yield f
            if isinstance(f, (FAnd, FOr)):
                for c in f.children:
                    yield from walk(c)
            elif isinstance(f, FNot):
                yield from walk(f.inner)

        for tid in (
            "B10-cast-kw-eot-self",
            "B10-cast-may-draw",
            "B10-cast-charge-self",
            "B10-cast-self-damage-any",
            "B10-cast-self-pt-eot",
        ):
            outcome = REG.match(OWNED[tid])[0].outcome
            assert isinstance(outcome, AbilityOutcome)
            assert isinstance(outcome.ability, TriggeredAbility)
            ev = outcome.ability.event
            assert isinstance(ev, CastSpellEvent)
            for node in walk(ev.filter):
                if isinstance(node, FAtom) and node.pred is FAtomPred.TYPE_EQ:
                    self.assertNotIn(node.string_value, {"Wizard", "Cat", "Dog"})

    def test_tail_shapes(self) -> None:
        # keyword-grant self + EOT (Umara Wizard front face)
        ab = _ability(S_FLYING)
        p = _pairs(ab.effect)
        self.assertIs(ab.effect.verb, Verb.GRANT_ABILITY)
        self.assertIs(p["ability"].keyword, Keyword.FLYING)
        self.assertIsInstance(p["duration"], DurationEot)
        self.assertIsInstance(p["target"], object)
        # may-draw: OptionalEffect over the b6 DRAW anchor
        ab = _ability(S_MAY_DRAW)
        self.assertIsInstance(ab.effect, OptionalEffect)
        self.assertIs(ab.effect.inner.verb, Verb.DRAW)
        # charge counter on the self artifact — CHARGE kind, executor
        # lane is kind-agnostic (verbs._v_put_counter)
        ab = _ability(S_CHARGE)
        p = _pairs(ab.effect)
        self.assertIs(ab.effect.verb, Verb.PUT_COUNTER)
        self.assertIs(p["counter_kind"], CounterKind.CHARGE)
        self.assertEqual(p["count"].value, 1)
        # 1 damage to the CR 109.5 any-target population
        ab = _ability(S_DAMAGE)
        p = _pairs(ab.effect)
        self.assertIs(ab.effect.verb, Verb.DEAL_DAMAGE)
        self.assertEqual(p["amount"].value, 1)
        # +2/+0 self UET
        ab = _ability(S_PT)
        p = _pairs(ab.effect)
        self.assertIs(ab.effect.verb, Verb.MODIFY_PT)
        self.assertIsInstance(p["power"], PtDelta)
        self.assertIsInstance(p["duration"], DurationEot)

    def test_counter_unless_shape_flat_payer_seat_safe(self) -> None:
        atom = _effect(S_COUNTER)
        self.assertIs(atom.verb, Verb.COUNTER_SPELL)
        p = _pairs(atom)
        sel = p["target"]
        self.assertIs(sel.zones[0].kind, ZoneKind.STACK)
        self.assertIsInstance(sel.filter, FOr)
        self.assertEqual(
            sorted(k.string_value for k in sel.filter.children),
            ["Creature", "Planeswalker"],
        )
        unless = p["unless"]
        self.assertIsInstance(unless, Cost)
        self.assertEqual(len(unless.parts), 1)  # FLAT {2}: payer-seat safe
        self.assertEqual(unless.parts[0].amount.value, 2)


# ---------------------------------------------------------------------------
# Executor-observed falsifiers (the P0 shape of this round)
# ---------------------------------------------------------------------------


class CastKindCase(StackCase):
    """Watcher creature carrying a COMPILED b10 trigger; the real stack
    cast feed (executor.stack.cast) drives every assertion."""

    def watcher(self, sentence: str, name: str = "Watcher"):
        ability = _ability(sentence)
        handle = self.world.add_card(card_id(name, "2", "2"), self.p0, "battlefield")
        self.ex.attach_card(
            handle,
            record_of_kw(
                [ability],
                name=name,
                oid=self.world.cards[handle].identity.oracle_id,
            ),
        )
        return handle

    def watcher_ir(self, ability, name: str):
        """Watcher carrying a RAW-IR ability (shared-branch pin below)."""
        handle = self.world.add_card(card_id(name, "2", "2"), self.p0, "battlefield")
        self.ex.attach_card(
            handle,
            record_of_kw(
                [ability],
                name=name,
                oid=self.world.cards[handle].identity.oracle_id,
            ),
        )
        return handle

    def free_spell(
        self,
        name: str,
        *,
        kind: SpellKind = SpellKind.INSTANT,
        subtypes: tuple[str, ...] = (),
    ):
        """Zero-cost castable card in p0's hand with its compiled record
        attached (instant/sorcery; or a creature, optionally WITH the
        Wizard subtype, with kind=CREATURE)."""
        creature = kind is SpellKind.CREATURE
        type_line = (
            "Creature"
            if creature
            else ("Instant" if kind is SpellKind.INSTANT else "Sorcery")
        )
        if subtypes:
            type_line += " — " + " ".join(subtypes)
        base = spell_rec(
            name,
            kind,
            type_line=type_line,
            types=("Creature",) if creature else (type_line,),
            power="2" if creature else None,
            toughness="2" if creature else None,
        )
        # spell_rec pins subtypes=(); the Wizard axis must be REAL card
        # data for _match_cast's SUBTYPE_EQ read.
        rec = replace(base, subtypes=subtypes)
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name=name,
                type_line=type_line,
                power="2" if creature else None,
                toughness="2" if creature else None,
                cmc=2,
                colors=(),
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def cast_free(self, handle, decisions: tuple[str, ...] = ()):
        cast(self.ex, self.p0, handle, decisions=decisions)

    def pt(self, handle):
        state = self.world.cards[handle]
        return self.ex.ledger.effective_pt(state.identity, handle, state.counters)

    def zone(self, seat, kind):
        return [
            h
            for h in self.world.cards
            if self.world.zone_of(h).kind == kind
            and self.world.controller_of(h) == seat
        ]

    def hand_n(self):
        return len(self.zone(self.p0, ZONE_HAND))


class TestCastKindFalsifiers(CastKindCase):
    """Matching-kind positives AND the non-matching negative per tail —
    the always-firing/never-firing falsifier (T6-class guard)."""

    def test_type_predicates_share_one_word_test_branch(self) -> None:
        """PIN of TODAY's engine semantics (diff gate, 2026-10-19):
        TYPE_EQ/SUBTYPE_EQ/SUPERTYPE_EQ evaluate as ONE type-line
        word-test (quantity.py:726) — a TYPE_EQ("Wizard") head FIRES on
        a Wizard-creature cast exactly like SUBTYPE_EQ does. The
        structural test pins the b10 encoding; this test pins the
        behavior so a future strict-predicate split (engine-lane,
        Type-1) MUST update it consciously instead of silently."""
        base = _ability(S_FLYING)
        assert isinstance(base.event, CastSpellEvent)
        w_type = self.watcher_ir(
            replace(
                base,
                event=replace(
                    base.event,
                    filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Wizard"),
                ),
            ),
            "TypeWatcher",
        )
        w_sub = self.watcher_ir(
            replace(
                base,
                event=replace(
                    base.event,
                    filter=FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Wizard"),
                ),
            ),
            "SubWatcher",
        )
        self.cast_free(
            self.free_spell("Twobird", kind=SpellKind.CREATURE, subtypes=("Wizard",))
        )
        self.assertTrue(self.ex.layers.keyword_of(w_type, Keyword.FLYING))
        self.assertTrue(self.ex.layers.keyword_of(w_sub, Keyword.FLYING))

    # ------------------------------------------------- keyword-grant UET
    def test_flying_fires_on_instant_and_expires(self):
        w = self.watcher(S_FLYING)
        self.assertFalse(self.ex.layers.keyword_of(w, Keyword.FLYING))
        self.cast_free(self.free_spell("Zap"))
        self.assertTrue(self.ex.layers.keyword_of(w, Keyword.FLYING))  # fire
        self.ex.end_turn()
        self.assertFalse(self.ex.layers.keyword_of(w, Keyword.FLYING))  # EOT

    def test_flying_silent_on_nonwizard_creature_cast(self):
        # THE NEGATIVE (P0): a creature spell that is neither instant,
        # sorcery, nor Wizard must NOT grant — always-fire falsified.
        w = self.watcher(S_FLYING)
        self.cast_free(self.free_spell("Goblin", kind=SpellKind.CREATURE))
        self.assertFalse(self.ex.layers.keyword_of(w, Keyword.FLYING))

    def test_flying_fires_on_wizard_subtypes_eq_axis(self):
        # SUBTYPE_EQ positive (branch reachability through the EXECUTOR);
        # the structural test owns the atom-kind pin — here we only pin
        # that a Wizard-creature cast FIRES the trigger.
        w = self.watcher(S_FLYING)
        self.cast_free(
            self.free_spell(
                "Hedge Wizard", kind=SpellKind.CREATURE, subtypes=("Wizard",)
            )
        )
        self.assertTrue(self.ex.layers.keyword_of(w, Keyword.FLYING))

    # -------------------------------------------------------- may-draw
    def test_may_draw_fires_and_skips(self):
        self.watcher(S_MAY_DRAW)
        # DRAW against an empty library is a silent no-op: seed the deck
        # so the fire/skip delta measures the MAY, not the zone math.
        for i in (1, 2):
            self.world.add_card(card_id(f"Lib{i}", type_line="Basic Land"), self.p0)
        n0 = self.hand_n()
        self.ex.decisions.provider = _prov_vocab("fire")
        try:
            self.cast_free(self.free_spell("Zap"))
        finally:
            self.ex.decisions.provider = None
        # +1 (spell dealt to hand) -1 (spell cast) +1 (the may drew).
        self.assertEqual(self.hand_n(), n0 + 1)
        n1 = self.hand_n()
        self.ex.decisions.provider = _prov_vocab("skip")
        try:
            self.cast_free(self.free_spell("Zap2"))
        finally:
            self.ex.decisions.provider = None
        # honest skip: +1 dealt -1 cast, no draw.
        self.assertEqual(self.hand_n(), n1)

    def test_may_draw_silent_on_nonwizard_creature_cast(self):
        self.watcher(S_MAY_DRAW)
        # a seeded library makes a WRONG fire observable (an empty deck
        # would no-op the draw and blind this falsifier).
        self.world.add_card(card_id("LibX", type_line="Basic Land"), self.p0)
        # fire-available provider: if the trigger WRONGLY fired on this
        # non-matching cast, a drawn card would remain in hand.
        self.ex.decisions.provider = _prov_vocab("fire")
        try:
            self.cast_free(self.free_spell("Goblin", kind=SpellKind.CREATURE))
        finally:
            self.ex.decisions.provider = None
        # the creature resolved to the battlefield; hand empty: no ask
        # answered, no draw — the negative falsifier.
        self.assertEqual(self.hand_n(), 0)

    # ---------------------------------------------------- charge counter
    def test_charge_counter_fires_and_counts(self):
        w = self.watcher(S_CHARGE, name="Amulet")
        self.cast_free(self.free_spell("Stomp", kind=SpellKind.SORCERY))
        self.assertEqual(self.world.cards[w].counters.get("CHARGE"), 1)
        self.cast_free(
            self.free_spell(
                "Hedge Wizard", kind=SpellKind.CREATURE, subtypes=("Wizard",)
            )
        )
        self.assertEqual(self.world.cards[w].counters.get("CHARGE"), 2)

    def test_charge_silent_on_nonwizard_creature_cast(self):
        w = self.watcher(S_CHARGE, name="Amulet")
        self.cast_free(self.free_spell("Goblin", kind=SpellKind.CREATURE))
        self.assertIsNone(self.world.cards[w].counters.get("CHARGE"))

    # ---------------------------------------------------- 1-damage lane
    def test_damage_fires_at_declared_player(self) -> None:
        self.watcher(S_DAMAGE)
        life0 = self.world.players[self.p1].life
        self.ex.decisions.provider = _pick(self.p1)
        try:
            self.cast_free(self.free_spell("Zap"))
        finally:
            self.ex.decisions.provider = None
        self.assertEqual(self.world.players[self.p1].life, life0 - 1)

    def test_damage_silent_on_nonwizard_creature_cast(self):
        self.watcher(S_DAMAGE)
        life0 = self.world.players[self.p1].life
        self.ex.decisions.provider = _pick(self.p1)
        try:
            self.cast_free(self.free_spell("Goblin", kind=SpellKind.CREATURE))
        finally:
            self.ex.decisions.provider = None
        self.assertEqual(self.world.players[self.p1].life, life0)

    # ------------------------------------------------------- +2/+0 UET
    def test_pt_fires_instant_sorcery_wizard_silent_creature(self):
        w = self.watcher(S_PT)
        self.assertEqual(self.pt(w), (2, 2))
        self.cast_free(self.free_spell("Zap"))
        self.assertEqual(self.pt(w), (4, 2))  # instant fires
        self.cast_free(self.free_spell("Stomp", kind=SpellKind.SORCERY))
        self.assertEqual(self.pt(w), (6, 2))  # sorcery fires
        self.cast_free(self.free_spell("Goblin", kind=SpellKind.CREATURE))
        self.assertEqual(self.pt(w), (6, 2))  # THE NEGATIVE: silent
        self.cast_free(
            self.free_spell(
                "Hedge Wizard", kind=SpellKind.CREATURE, subtypes=("Wizard",)
            )
        )
        self.assertEqual(self.pt(w), (8, 2))  # Wizard subtype fires


class TestAnticognitionCounter(StackCase):
    """B10-counter-unless-cw-pw: the FOr menu, the counter lane and the
    FLAT payer-seat kickback (verbs.py:1926) — executor-observed."""

    def _spell(self, name, type_line, seat=None):
        seat = seat if seat is not None else self.p1
        return self.world.add_card(
            card_id(name, cmc=2, type_line=type_line), seat, ZONE_HAND
        )

    def _anti(self):
        return self.world.add_card(
            card_id("Anticognition", cmc=2, type_line="Instant"),
            self.p0,
            ZONE_BATTLEFIELD,
        )

    def _atom(self):
        return _effect(S_COUNTER)

    def test_menu_covers_creature_and_pw_excludes_instant(self):
        cre = self._spell("Hound", "Creature — Hound")
        pw = self._spell("Jace", "Planeswalker — Jace")
        inst = self._spell("Zap", "Instant")
        park(self.ex, self.p1, cre)
        park(self.ex, self.p1, pw)
        park(self.ex, self.p1, inst)
        slot = legal_targets(
            self.world,
            self.ex,
            _pairs(self._atom())["target"],
            source=self._anti(),
            controller=self.p0,
        )
        self.assertEqual(
            sorted(str(h) for h in slot.candidates),
            sorted(str(h) for h in (cre, pw)),
        )  # both OR branches live, the instant excluded

    def test_counter_lane_needs_a_frame(self):
        # FALSIFIER for the lane itself: COUNTER_SPELL refuses a parked,
        # UNFRAMED card (verbs.py) — a real counter must run through the
        # response window, not a direct-execute shortcut.
        cre = self._spell("Hound", "Creature — Hound")
        park(self.ex, self.p1, cre)
        bind: dict[str, Any] = {"target": (cre,)}
        with self.assertRaises(ValueError):
            self.ex.execute(
                self._atom(),
                source=self._anti(),
                controller=self.p0,
                bindings=bind,
            )


class TestAnticognitionResponseWindow(Rung1Case):
    """The counter + FLAT {2} kickback through the REAL RUNG-1 window:
    PASS counters (COUNTER row, card to graveyard), PAY runs the plan
    through the PAYER seat's pool (verbs.py kickback lane) and the
    spell lives — the compiled b10 node drives both."""

    def _pup(self):
        pup = self.give(
            "Cliffhaven Sell-Sword",
            SpellKind.CREATURE,
            cost=Cost((CostManaColor("W", QConst(1)),)),
            types=("Creature",),
            type_line="Creature",
            power="3",
            toughness="1",
        )
        self.mana(self.p0, W=3)  # cast {W} + kickback {2} payer seat
        return pup

    def _anti(self):
        anti = self.give(
            "Anticognition",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(1)),)),
            effect=_effect(S_COUNTER),
            seat=self.p1,
        )
        self.mana(self.p1, U=1)
        return anti

    def _prov(self, counter, kick):
        def prov(vocab, what):
            # the kickback ask vocab is exactly ("PASS", "PAY"); the
            # window-offer vocab is ("PASS", <counter handle>) — the
            # handle presence is what tells the two apart.
            if "PAY" in vocab:
                return kick
            for v in vocab:
                if str(v) == str(counter):
                    return v
            return vocab[0]

        return prov

    def test_pass_counters_the_creature_spell(self):
        pup = self._pup()
        anti = self._anti()
        self.ex.decisions.provider = self._prov(anti, "PASS")
        try:
            self.ex_cast(self.p0, pup)
        finally:
            self.ex.decisions.provider = None
        self.assertEqual(self.zone_kind(pup), ZONE_GRAVEYARD)  # countered
        self.assertEqual(len(self.journal_rows("COUNTER")), 1)
        self.assertEqual(len(self.journal_rows("KICKBACK")), 1)

    def test_pay_lets_the_spell_live(self):
        pup = self._pup()
        anti = self._anti()
        self.ex.decisions.provider = self._prov(anti, "PAY")
        try:
            self.ex_cast(self.p0, pup)
        finally:
            self.ex.decisions.provider = None
        self.assertEqual(self.zone_kind(pup), ZONE_BATTLEFIELD)  # lived
        rows = self.journal_rows("KICKBACK")
        self.assertEqual(len(rows), 1)
        self.assertIn("PAY", repr(rows[0]))  # flat {2} paid via payer seat
        self.assertEqual(len(self.journal_rows("COUNTER")), 0)


if __name__ == "__main__":
    unittest.main()
