"""Tests for templates_b10: each owned row single-claims its template and the deferred rows
match nothing; the cast head's structure (SUBTYPE_EQ for Wizard); the priority and the
neighbouring heads it must not claim; and, through the executor, every cast trigger fires on a
matching cast and stays silent on a non-matching one, and the counterspell's menu, PASS and PAY.
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


# The printed sentences this bucket owns.
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

# Rows left unparsed on purpose (the templates_b10 docstring says why): they match nothing.
DEFER_ROWS: dict[str, str] = {
    "ZND-5a lithoform": "{3}, {T}: Copy target instant or sorcery spell you control.",
    "ZND-5b stormcaller": "When this creature enters, copy the next "
    "instant or sorcery spell with mana value 2 or less you cast this "
    "turn when you cast it.",
    "ZND-5b stormcaller-kicked": "If this creature was kicked, copy that "
    "spell twice instead.",
    "ZND-5b kaza": "{T}: The next instant or sorcery spell you cast this "
    "turn costs {X} less to cast, where X is the number of Wizards you "
    "control as this ability resolves.",
    "ZND-5c base-camp": "Spend this mana only to cast a Cleric, Rogue, "
    "Warrior, or Wizard spell or to activate an ability of a Cleric, "
    "Rogue, Warrior, or Wizard.",
    "ZND-5d myriad": "When this creature becomes the target of a spell, "
    "sacrifice it and create a number of 1/1 colorless Construct "
    "artifact creature tokens equal to its power.",
    "ZND-5e anticognition-s2": "If an opponent has eight or more cards "
    "in their graveyard, instead counter that spell, then scry 2.",
    "ZND-5f master-of-winds": "Whenever you cast an instant, sorcery, or "
    "Wizard spell, you may have this creature's base power and toughness "
    "become 4/1 or 1/4 until end of turn.",
    "relic-removal": "{2}, {T}, Remove all charge counters from this "
    "artifact: It deals that much damage to target creature.",
}

# Neighbouring heads that b10 must not claim.
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
        # The cast head must not claim b2b's Cat/Dog/noncreature/colored cast heads, nor the
        # b5a/b9 counterspells: each neighbour keeps its own template.
        for tid, sentence in NEIGHBOUR_HEADS.items():
            self.assertEqual(_tids(sentence), [tid], sentence)

    def test_head_is_type_instant_type_sorcery_subtype_wizard(self) -> None:
        # "Wizard" is SUBTYPE_EQ: TYPE_EQ would work today (the engine tests the three type
        # predicates alike) and break the day the predicates split.
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
        # No B10 cast filter encodes a creature subtype (Wizard, Cat, Dog) as TYPE_EQ.
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
        # charge counter on the self artifact
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
        # target_spell ANDs STACK_KIND_EQ SPELL into the filter
        self.assertIsInstance(sel.filter, FAnd)
        kind, types = sorted(sel.filter.children, key=lambda c: isinstance(c, FOr))
        self.assertEqual(kind, FAtom(pred=FAtomPred.STACK_KIND_EQ, string_value="SPELL"))
        self.assertIsInstance(types, FOr)
        self.assertEqual(
            sorted(k.string_value for k in types.children),
            ["Creature", "Planeswalker"],
        )
        unless = p["unless"]
        self.assertIsInstance(unless, Cost)
        self.assertEqual(len(unless.parts), 1)  # a flat {2}
        self.assertEqual(unless.parts[0].amount.value, 2)


# ---------------------------------------------------------------------------
# Through the executor
# ---------------------------------------------------------------------------


class CastKindCase(StackCase):
    """A watcher creature carrying a compiled b10 trigger; the real stack cast
    (executor.stack.cast) drives every assertion."""

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
        # spell_rec sets subtypes=(); _match_cast's SUBTYPE_EQ reads the real card data.
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
    """Each tail fires on a matching cast and stays silent on a non-matching one."""

    def test_type_predicates_share_one_word_test_branch(self) -> None:
        """Today TYPE_EQ, SUBTYPE_EQ and SUPERTYPE_EQ are one type-line word test: a
        TYPE_EQ("Wizard") head fires on a Wizard creature cast like SUBTYPE_EQ does. A split of
        the predicates must update this test."""
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
        # A creature spell that is not an instant, sorcery or Wizard does not grant.
        w = self.watcher(S_FLYING)
        self.cast_free(self.free_spell("Goblin", kind=SpellKind.CREATURE))
        self.assertFalse(self.ex.layers.keyword_of(w, Keyword.FLYING))

    def test_flying_fires_on_wizard_subtypes_eq_axis(self):
        # A Wizard creature cast fires the trigger.
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
        self.assertEqual(self.pt(w), (6, 2))  # non-Wizard creature: silent
        self.cast_free(
            self.free_spell(
                "Hedge Wizard", kind=SpellKind.CREATURE, subtypes=("Wizard",)
            )
        )
        self.assertEqual(self.pt(w), (8, 2))  # Wizard subtype fires


class TestAnticognitionCounter(StackCase):
    """B10-counter-unless-cw-pw through the executor: the target menu and the counter."""

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
        # COUNTER_SPELL refuses a parked card without a stack frame: a real counter runs
        # through the response window.
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


class TestAnticognitionInResponse(Rung1Case):
    """The compiled counter and its flat {2} unless cost, cast at a creature spell waiting on
    the stack: PASS counters the spell (COUNTER row, card to graveyard); PAY pays from the
    spell controller's pool and the spell lives."""

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

    def test_pass_counters_the_creature_spell(self):
        pup = self._pup()
        self.countered_by(self._anti(), self.p0, pup, answers=("PASS",))
        self.assertEqual(self.zone_kind(pup), ZONE_GRAVEYARD)  # countered
        self.assertEqual(len(self.journal_rows("COUNTER")), 1)
        self.assertEqual(len(self.journal_rows("KICKBACK")), 1)

    def test_pay_lets_the_spell_live(self):
        pup = self._pup()
        self.countered_by(self._anti(), self.p0, pup, answers=("PAY",))
        self.assertEqual(self.zone_kind(pup), ZONE_BATTLEFIELD)  # lived
        rows = self.journal_rows("KICKBACK")
        self.assertEqual(len(rows), 1)
        self.assertIn("PAY", repr(rows[0]))  # the controller paid the {2}
        self.assertEqual(len(self.journal_rows("COUNTER")), 0)


if __name__ == "__main__":
    unittest.main()
