"""HAS_KICKER on the 12c query surface (ZND-2 T4 first consumer, /98).

The ZNR fuzz ledger (reports/znr_engine_smoke_2026-10-19.md, seed 10) crashed
``HAS_KICKER not implemented (12c query surface)`` when Murasa Sproutling's
kicked ETB asked "return card with a kicker ability from your graveyard":
the TARGET selector's enumerate_candidates judged the filter against EVERY
graveyard card and the bare raise fired on the first candidate.

The landing is the PRINTED-property reading: the ground truth is the card's
COMPILED record — a card HAS a kicker iff its FRONT-FACE ability tuple
carries a KickerAbility node (the same top-level scan legality.kicker_of and
the cast fold use, §9 one encoding). Records resolve through
legality.spell_record (handle bridge, else oracle-id registry — the r20c
hand-window pattern for cards off the battlefield).

Face law (/106): BackFace abilities live in the face's OWN tuple, which the
scan never descends — a back-face-only kicker does NOT satisfy HAS_KICKER
for a front-face decision. Tokens: no compiled record (or is_token) ->
False, never a raise. The honest 12c raise REMAINS for every other unknown
pred (pinned here by a vocab scan).
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from MTG_bot.core.ability_tree import (
    BackFace,
    ControllerRef,
    Cost,
    CostManaGeneric,
    FAtom,
    FAtomPred,
    KickerAbility,
    QConst,
    Selector,
    SelectorMode,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.legality import ctx_for, enumerate_candidates
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld
from MTG_bot.core.test_executor_binding import record_of, reset_oracle_ids


def _cost() -> Cost:
    return Cost(parts=(CostManaGeneric(amount=QConst(1)),))


def _kicker_selector() -> Selector:
    """The EXACT compiled Murasa Sproutling filter shape (TARGET, count 1,
    your graveyard, HAS_KICKER) — read off the compiled tree."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAtom(pred=FAtomPred.HAS_KICKER),
        zone=Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
    )


class HasKickerFilterTest(unittest.TestCase):
    """The filter pred over graveyard candidates — the crash surface."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.supply = get_supply("engine", "ZNR")
        cls.records = {
            res.card.name: res.card for res in cls.supply.pool.results.values()
        }

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=5)
        self.executor = Executor(self.world)
        self.executor.attach_pool(self.supply.pool)
        self.p0, _p1 = self.world.player_order
        self.world.active_player = self.p0
        # The Murasa on the battlefield is the effect SOURCE for the ctx.
        murasa = self.records["Murasa Sproutling"]
        self.source = self.world.add_card(
            identity_of(murasa), self.p0, ZONE_BATTLEFIELD
        )

    def ctx(self) -> ExecCtx:
        return ctx_for(self.executor, source=self.source, controller=self.p0)

    def _in_graveyard(self, name: str):
        return self.world.add_card(
            identity_of(self.records[name]), self.p0, ZONE_GRAVEYARD
        )

    def test_real_kicker_card_satisfies_filter(self) -> None:
        # Positive: Kitesail Cleric's compiled record carries a top-level
        # KickerAbility -> the Murasa filter returns it.
        kc = self._in_graveyard("Kitesail Cleric")
        self.assertTrue(eval_filter(FAtom(pred=FAtomPred.HAS_KICKER), kc, self.ctx()))

    def test_plain_card_fails_filter(self) -> None:
        # Negative: Ruin Crab compiles with no KickerAbility anywhere.
        crab = self._in_graveyard("Ruin Crab")
        self.assertFalse(
            eval_filter(FAtom(pred=FAtomPred.HAS_KICKER), crab, self.ctx())
        )

    def test_enumerate_candidates_only_returns_kickers(self) -> None:
        # The crash lane itself: legality.enumerate_candidates over the real
        # compiled Murasa filter shape, mixed graveyard.
        kc = self._in_graveyard("Kitesail Cleric")
        crab = self._in_graveyard("Ruin Crab")
        cands = enumerate_candidates(_kicker_selector(), self.ctx())
        self.assertEqual(cands, [kc], "the kicker card alone (Handle-sorted)")
        self.assertNotIn(crab, cands)

    def test_back_face_only_kicker_does_not_satisfy(self) -> None:
        # /106 face law: a KickerAbility INSIDE a BackFace subtree is a face
        # component — encoded, not playable, and NOT a front-face printed
        # kicker. Synthesized record (the live ZNR pool has zero back-face
        # kickers, census-verified this wave: 38 front, 0 back-only).
        rec = record_of(
            [BackFace(face_name="Kick Face", abilities=(KickerAbility(cost=_cost()),))],
            name="Face Kicker Only",
        )
        self.executor.binder.records[rec.oracle_id] = rec
        handle = self.world.add_card(identity_of(rec), self.p0, ZONE_GRAVEYARD)
        self.assertFalse(
            eval_filter(FAtom(pred=FAtomPred.HAS_KICKER), handle, self.ctx()),
            "back-face kicker must not satisfy a front-face HAS_KICKER",
        )

    def test_token_is_false_not_raise(self) -> None:
        # Tokens never have a printed kicker: an UNREGISTERED token (no
        # compiled record at all) and a REGISTERED token record carrying a
        # nonsense KickerAbility both read False.
        token_ident = CardIdentity(
            oracle_id="00000000-1111-2222-3333-444444444444",
            name="Token",
            type_line="Creature Token",
            is_token=True,
        )
        handle = self.world.add_card(token_ident, self.p0, ZONE_GRAVEYARD)
        self.assertFalse(
            eval_filter(FAtom(pred=FAtomPred.HAS_KICKER), handle, self.ctx())
        )
        tok_rec = replace(
            record_of([KickerAbility(cost=_cost())], name="Token"),
            is_token=True,
        )
        self.executor.binder.records[tok_rec.oracle_id] = tok_rec
        tok_handle = self.world.add_card(identity_of(tok_rec), self.p0, ZONE_GRAVEYARD)
        self.assertFalse(
            eval_filter(FAtom(pred=FAtomPred.HAS_KICKER), tok_handle, self.ctx()),
            "is_token pins False even against a nonsense kicker-carrying token record",
        )

    def test_bare_ctx_flags_never_guesses(self) -> None:
        # flag-not-degrade: a bare ExecCtx (no executor -> no record
        # registry) raises naming HAS_KICKER, not the generic 12c raise.
        handle = self._in_graveyard("Ruin Crab")
        bare = ExecCtx(
            world=self.world,
            ledger=self.executor.ledger,
            controller=self.p0,
            source=self.source,
            bindings={},
            decisions=(),
        )
        with self.assertRaises(NotImplementedError) as cm:
            eval_filter(FAtom(pred=FAtomPred.HAS_KICKER), handle, bare)
        self.assertIn("HAS_KICKER", str(cm.exception))

    def test_unknown_pred_still_raises_12c(self) -> None:
        # The honest raise REMAINS for genuinely unimplementable preds: only
        # HAS_KICKER landed. Scanning the closed pred vocab (no shadow
        # list), at least one other member still meets the generic 12c
        # message.
        handle = self._in_graveyard("Ruin Crab")
        ctx = self.ctx()
        generic = []
        for pred in FAtomPred:
            if pred is FAtomPred.HAS_KICKER:
                continue
            try:
                atom = FAtom(pred=pred)
            except ValueError:
                continue  # slot-required preds: the bare atom is illegal IR
            try:
                eval_filter(atom, handle, ctx)
            except NotImplementedError as exc:
                if "not implemented (12c query surface)" in str(exc):
                    generic.append(pred)
            except Exception:  # noqa: BLE001,S112 - non-12c shapes skipped
                continue
        self.assertTrue(generic, "the 12c honest raise vanished from the whole vocab")


if __name__ == "__main__":
    unittest.main()
