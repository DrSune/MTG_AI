"""C3 compiler campaign — dropped-clause restoration pins (2026-10-02).

Batch C3 restores three clause emissions that the goldens never carried:

1. Liliana Waker +1 tail — "Each opponent who can't loses 3 life." is a
   mandatory EachPlayer(ALL_OPPONENTS, Conditional(FNot(hand ZONE_COUNT_GE
   1), LOSE_LIFE 3)) appended to the loyalty-+1 ActivatedAbility through
   the R11-1 loyalty-trailing path (post-discard hand-count reading, the
   roadmap-sanctioned r21b deviation).
2. Transmogrify s2/s3 — the reveal-until pair emits a top-of-library
   creature SEARCH (ZonePosition.TOP, TARGET_PLAYER — CHOOSE can never
   reach past the library top) whose destination carries the "puts that
   card onto the battlefield" half, followed by the remainder SHUFFLE;
   the instant's three plain effects fold into one Seq at card assembly.
3. Peer into the Abyss — STOP verdict: the missing half-life clause has
   no quantity lane (no LIFE-total quantity field; R9 grammar roadmap), so
   the golden stays byte-identical and the pin below only falsifies that
   no half-LOSE_LIFE approximation was smuggled in.

Goldens moved for the two promoted cards under the C1-form set-evidence
audit (pre-snapshot /tmp/golden_pre_c3, 303 others byte-identical; moved
keys subset-of {abilities}).
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
    QConst,
    QUnbounded,
    Seq,
    Selector,
    SelectorMode,
    SpellAbility,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
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
        """The can't-clause is APPENDED (R11-1 loyalty-trailing path), not
        dropped and not a standalone sentence-outcome: the +1 ability's
        effect is a Seq whose LAST step is the EachPlayer gate."""
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
        self.assertIsInstance(ability.effect.steps[-1], EachPlayer)

    def test_waker_each_player_gate_shape(self) -> None:
        """EachPlayer(ALL_OPPONENTS, Conditional(pred=FNot(
        ZONE_COUNT_GE(HAND, YOU, 1)), then=LOSE_LIFE(controller=YOU,
        amount=QConst(3)))) — YOU-relative both sides; EachPlayer rotation
        rebinds per opponent (b2a/b2b convention)."""
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
        """The pre-existing "discard a card" step of the +1 ability is
        untouched — the tail is an append, the head is not rewritten."""
        res = self._compile(_WAKER)
        ability = next(
            ab
            for ab in res.card.abilities
            if isinstance(ab, ActivatedAbility)
            and any(isinstance(p, CostLoyalty) and p.delta == 1 for p in ab.cost.parts)
        )
        assert isinstance(ability.effect, Seq)
        head = ability.effect.steps[0]
        assert isinstance(head, Atom)
        # T4 P1a: the discard shape is the merged MOVE_ZONE atom.
        self.assertIs(head.verb, Verb.MOVE_ZONE)
        self.assertEqual(
            head.args.get("destination"),
            Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.ANY),
        )

    # ---- transmogrify: top-of-library SEARCH + TARGET_PLAYER SHUFFLE ----

    def test_transmog_spell_folds_to_three_step_seq(self) -> None:
        """MOVE_ZONE (exile shape), Seq(SEARCH, REVEAL), SHUFFLE — the
        three plain sentence effects fold into the SpellAbility's single
        Seq at card assembly (no continuation prefixes involved).
        T5-E: s2 contributes the nested Seq — the dig plus the traceable
        disclosure REVEAL (the sibling one-sentence-Seq precedent, e.g.
        the Cultivate-family builder); the executor walks nested Seqs
        and the transmogrify scenario pack is byte-green."""
        res = self._compile(_TRANSMOG)
        (spell,) = res.card.abilities
        assert isinstance(spell, SpellAbility)
        assert isinstance(spell.effect, Seq)
        steps = spell.effect.steps
        self.assertEqual(len(steps), 3)
        # T4 P1a: the old EXILE row is the merged MOVE_ZONE atom.
        head, mid, tail = steps
        assert isinstance(head, Atom) and isinstance(tail, Atom)
        self.assertIs(head.verb, Verb.MOVE_ZONE)
        assert isinstance(mid, Seq)
        self.assertEqual(
            [s.verb for s in mid.steps if isinstance(s, Atom)],
            [Verb.SEARCH, Verb.REVEAL],
        )
        self.assertIs(tail.verb, Verb.SHUFFLE)

    def test_transmog_search_is_top_scoped_target_player(self) -> None:
        """SEARCH cards = Selector(QConst(1), CHOOSE, TYPE_EQ Creature,
        Zone(LIBRARY, TARGET_PLAYER, TOP)) — TOP means CHOOSE can only
        ever take the library top (never a bottom-of-library draw); the
        destination Zone(BATTLEFIELD, TARGET_PLAYER) carries s3's
        "puts that card onto the battlefield" half."""
        res = self._compile(_TRANSMOG)
        (spell,) = res.card.abilities
        assert isinstance(spell, SpellAbility) and isinstance(spell.effect, Seq)
        mid = spell.effect.steps[1]
        # T5-E: s2 is the Seq(SEARCH, REVEAL) — the dig leads so its
        # ONE_OF menu never sees the disclosure's look window.
        assert isinstance(mid, Seq)
        search, disclosure = mid.steps
        assert isinstance(search, Atom) and isinstance(disclosure, Atom)
        self.assertIs(disclosure.verb, Verb.REVEAL)
        self.assertIs(disclosure.args.get("controller"), ControllerRef.TARGET_PLAYER)
        self.assertIsInstance(disclosure.args.get("count"), QUnbounded)
        cards = search.args.get("cards")
        assert isinstance(cards, Selector)
        self.assertEqual(cards.count, QConst(1))
        # Doc 29 ②: the up-to-one search pick asks the ONE_OF channel.
        self.assertIs(cards.mode, SelectorMode.ONE_OF)
        flt = cards.filter
        assert isinstance(flt, FAtom)
        self.assertIs(flt.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(flt.string_value, "Creature")
        self.assertEqual(
            cards.zones[0],
            Zone(
                kind=ZoneKind.LIBRARY,
                controller=ControllerRef.TARGET_PLAYER,
                position=ZonePosition.TOP,
            ),
        )
        self.assertEqual(
            search.args.get("destination"),
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.TARGET_PLAYER),
        )
        self.assertIs(search.args.get("controller"), ControllerRef.TARGET_PLAYER)

    def test_transmog_shuffle_rest_is_target_player_owned(self) -> None:
        """SHUFFLE zone = Zone(LIBRARY, TARGET_PLAYER) with NO position —
        the anaphoric "their library" rides the s1-exile target binding."""
        res = self._compile(_TRANSMOG)
        (spell,) = res.card.abilities
        assert isinstance(spell, SpellAbility) and isinstance(spell.effect, Seq)
        shuffle = spell.effect.steps[2]
        assert isinstance(shuffle, Atom)
        self.assertIs(shuffle.verb, Verb.SHUFFLE)
        zone = shuffle.args.get("zone")
        assert isinstance(zone, Zone)
        self.assertEqual(
            zone, Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.TARGET_PLAYER)
        )
        self.assertIsNone(zone.position)

    # ---- peer: STOP verdict falsification ----

    def test_peer_golden_unchanged_no_half_life_approximation(self) -> None:
        """Peer's DRAW half-library clause stays the ONLY emitted effect
        (QCount-shape intact); the missing "loses half their life" has no
        quantity lane (no LIFE-total Quantity in the grammar — R9 roadmap),
        so no approximation is emitted and the golden stays byte-identical."""
        res = self._compile(_PEER)
        (spell,) = res.card.abilities
        assert isinstance(spell, SpellAbility)
        effect = spell.effect
        assert isinstance(effect, Atom)
        self.assertIs(effect.verb, Verb.DRAW)
        self.assertNotIn("LOSE_LIFE", repr(effect))


if __name__ == "__main__":
    unittest.main()
