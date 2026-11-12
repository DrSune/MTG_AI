"""Compiler pins: Liliana, Waker of the Dead's +1, Transmogrify, Peer into the Abyss.

1. Liliana's +1 "Each opponent who can't loses 3 life." is a mandatory
   EachPlayer(ALL_OPPONENTS, Conditional(FNot(hand ZONE_COUNT_GE 1), LOSE_LIFE 3))
   inside the loyalty-+1 ActivatedAbility, placed before the discard it reads
   (docs/ATOM_DIVERGENCES.md D17).
2. Transmogrify reveals until a creature card (REVEAL ``until``) as the exiled
   creature's controller, and that player puts the card onto the battlefield and
   shuffles (EachPlayer over the same referent); the three effects fold into one Seq.
3. Peer into the Abyss: the target player loses exactly half their life,
   rounded up, after the draw.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    Conditional,
    ControllerRef,
    CostLoyalty,
    EachPlayer,
    FAtom,
    FAtomPred,
    FNot,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    Rounding,
    Seq,
    Selector,
    SpellAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

_M21_PATH = Path(__file__).resolve().parents[2] / "data" / "M21.json"

_WAKER = "e0df8e2a-96d2-4e4d-b065-aa2e162abbfe"
_TRANSMOG = "4c1c3a0a-5782-4b7d-8b9c-61eea913166d"
_PEER = "21fa2442-6eac-4dce-a9cc-76f0053fdb8f"


class TestC3CompilerPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21_PATH)
        cls.reg = build_full_registry()

    def _compile(self, oid: str):
        res = compile_card(self.pool[oid], self.reg)
        self.assertEqual(res.unparsed, ())
        return res

    # ---- waker: loyalty-+1 tail "Each opponent who can't loses 3 life." ----

    def test_waker_tail_merges_into_plus_one_ability(self) -> None:
        """The can't-clause merges into the +1 ability as its first step,
        before the discard it is about (docs/ATOM_DIVERGENCES.md D17), so an
        opponent who discards their last card does not lose life."""
        res = self._compile(_WAKER)
        gated = [
            ab
            for ab in res.card.abilities
            if isinstance(ab, ActivatedAbility)
            and any(isinstance(p, CostLoyalty) and p.delta == 1 for p in ab.cost.parts)
        ]
        self.assertEqual(len(gated), 1, "expected exactly one loyalty-+1 ability")
        ability = gated[0]
        assert isinstance(ability.effect, Seq)
        self.assertEqual(len(ability.effect.steps), 2)
        self.assertIsInstance(ability.effect.steps[0], EachPlayer)

    def test_waker_each_player_gate_shape(self) -> None:
        """EachPlayer(ALL_OPPONENTS, Conditional(pred=FNot(
        ZONE_COUNT_GE(HAND, YOU, 1)), then=LOSE_LIFE(controller=YOU,
        amount=QConst(3)))): YOU-relative both sides, and the EachPlayer
        rotation rebinds YOU per opponent."""
        res = self._compile(_WAKER)
        gate = next(
            step
            for ab in res.card.abilities
            if isinstance(ab, ActivatedAbility)
            for step in (
                ab.effect.steps if isinstance(ab.effect, Seq) else (ab.effect,)
            )
            if isinstance(step, EachPlayer)
        )
        self.assertIs(gate.ref, ControllerRef.ALL_OPPONENTS)
        cond = gate.effect
        assert isinstance(cond, Conditional)
        self.assertIsNone(cond.else_effect)
        assert isinstance(cond.pred, FNot)
        pred = cond.pred.inner
        assert isinstance(pred, FAtom)
        self.assertIs(pred.pred, FAtomPred.ZONE_COUNT_GE)
        self.assertIs(pred.who, ControllerRef.YOU)
        self.assertEqual(
            pred.zone, Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)
        )
        self.assertEqual(pred.count, QConst(1))
        lose = cond.then_effect
        assert isinstance(lose, Atom)
        self.assertIs(lose.verb, Verb.LOSE_LIFE)
        self.assertIs(lose.args.get("controller"), ControllerRef.YOU)
        self.assertEqual(lose.args.get("amount"), QConst(3))

    def test_waker_discard_head_preserved(self) -> None:
        """The "discard a card" step of the +1 ability is kept, as the last
        step (the who-can't gate precedes it, D17)."""
        res = self._compile(_WAKER)
        ability = next(
            ab
            for ab in res.card.abilities
            if isinstance(ab, ActivatedAbility)
            and any(isinstance(p, CostLoyalty) and p.delta == 1 for p in ab.cost.parts)
        )
        assert isinstance(ability.effect, Seq)
        head = ability.effect.steps[-1]
        assert isinstance(head, Atom)
        # A discard is a MOVE_ZONE to the graveyard.
        self.assertIs(head.verb, Verb.MOVE_ZONE)
        self.assertEqual(
            head.args.get("destination"),
            Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.ANY),
        )

    # ---- transmogrify: REVEAL until a creature, then that player puts it ----

    def test_transmog_spell_folds_to_three_step_seq(self) -> None:
        """MOVE_ZONE (exile), REVEAL (until a creature card), EachPlayer (that
        player puts that card onto the battlefield, then shuffles): the three
        sentence effects fold into the SpellAbility's single Seq."""
        res = self._compile(_TRANSMOG)
        (spell,) = res.card.abilities
        assert isinstance(spell, SpellAbility)
        assert isinstance(spell.effect, Seq)
        head, reveal, tail = spell.effect.steps
        assert isinstance(head, Atom) and isinstance(reveal, Atom)
        self.assertIs(head.verb, Verb.MOVE_ZONE)  # "Exile target creature."
        self.assertIs(reveal.verb, Verb.REVEAL)
        assert isinstance(tail, EachPlayer)

    def test_transmog_reveals_until_a_creature_as_its_controller(self) -> None:
        """REVEAL(controller="that creature's controller", count 1, until TYPE_EQ
        Creature): the controller is the referent-"target" selector (the exiled
        creature's controller, CR 608.2h), never TARGET_PLAYER, so the spell has
        one target (KNOWLEDGE/2026-11-05/184: it used to designate a player too)."""
        res = self._compile(_TRANSMOG)
        (spell,) = res.card.abilities
        assert isinstance(spell, SpellAbility) and isinstance(spell.effect, Seq)
        reveal = spell.effect.steps[1]
        assert isinstance(reveal, Atom)
        controller = reveal.args.get("controller")
        assert isinstance(controller, Selector)
        self.assertEqual(controller.referent, "target")
        self.assertEqual(reveal.args.get("count"), QConst(1))
        self.assertEqual(
            reveal.args.get("until"), FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
        )
        self.assertNotIn("TARGET_PLAYER", repr(spell))

    def test_transmog_that_player_puts_it_and_shuffles(self) -> None:
        """EachPlayer(ref=that creature's controller): MOVE_ZONE of "that card"
        (the REVEAL's result) to the battlefield under that player (YOU inside
        the rotation, CR 110.2a), then SHUFFLE of their library."""
        res = self._compile(_TRANSMOG)
        (spell,) = res.card.abilities
        assert isinstance(spell, SpellAbility) and isinstance(spell.effect, Seq)
        tail = spell.effect.steps[2]
        assert isinstance(tail, EachPlayer)
        assert isinstance(tail.ref, Selector)
        self.assertEqual(tail.ref.referent, "target")
        assert isinstance(tail.effect, Seq)
        put, shuffle = tail.effect.steps
        assert isinstance(put, Atom) and isinstance(shuffle, Atom)
        self.assertIs(put.verb, Verb.MOVE_ZONE)
        cards = put.args.get("cards")
        assert isinstance(cards, Selector)
        self.assertEqual(cards.referent, "result")
        self.assertEqual(
            put.args.get("destination"),
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        )
        self.assertIs(shuffle.verb, Verb.SHUFFLE)
        self.assertEqual(
            shuffle.args.get("zone"), Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU)
        )

    # ---- Peer into the Abyss: half the target player's life ----

    def test_peer_golden_unchanged_no_half_life_approximation(self) -> None:
        """The LOSE_LIFE is exact: the target player's own life (EachPlayer
        rotation, never the caster's), halved and rounded up (CR 107.1a),
        after the draw (printed order)."""
        res = self._compile(_PEER)
        (spell,) = res.card.abilities
        assert isinstance(spell, SpellAbility)
        effect = spell.effect
        assert isinstance(effect, Seq)
        draw, lose = effect.steps
        assert isinstance(draw, Atom)
        self.assertIs(draw.verb, Verb.DRAW)
        self.assertIs(draw.args.get("controller"), ControllerRef.TARGET_PLAYER)
        self.assertNotIn("LOSE_LIFE", repr(draw))
        assert isinstance(lose, EachPlayer)
        self.assertIs(lose.ref, ControllerRef.TARGET_PLAYER)
        assert isinstance(lose.effect, Atom)
        self.assertIs(lose.effect.verb, Verb.LOSE_LIFE)
        self.assertIs(lose.effect.args.get("controller"), ControllerRef.YOU)
        self.assertEqual(
            lose.effect.args.get("amount"),
            QBin(
                op=QBinOp.DIV,
                left=QProp(referent="controller", field=QPropField.LIFE),
                right=QConst(2),
                rounding=Rounding.CEIL,
            ),
        )


if __name__ == "__main__":
    unittest.main()
