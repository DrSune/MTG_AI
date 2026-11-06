"""Casting an MDFC whose compiled record carries only a ``BackFace`` (no SpellAbility: the front
text never compiled) is refused loudly, never faked as a face cast.

``cast_card`` raises ``FaceCastAbsentError`` (a ValueError) with a fixed site message, and only
``face_cast_absent`` recognises that pair. The guarded effect lane (a CAST verb, as in Coveted
Prize's free cast) skips exactly that refusal and records it on ``unresolved_effects`` once per
distinct card. A look-alike ValueError is not matched, and the plain land refusal keeps its own
message and is not skippable.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    BackFace,
    ControllerRef,
    Cost,
    QConst,
    Selector,
    SelectorMode,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.stack import (
    FaceCastAbsentError,
    cast,
    cast_card,
    face_cast_absent,
)
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
)
from MTG_bot.core.test_executor_binding import UNIV, record_of
from MTG_bot.core.test_executor_stack import StackCase

DFC_NAME = "Beyeen Veil // Beyeen Coast"
FACE_MSG = (
    f"executor: CAST {DFC_NAME}: no SpellAbility on the card — the "
    "compiled record carries only a BackFace (the front text never "
    "reached the spell grammar)"
)
EXILE_YOU = Zone(ZoneKind.EXILE, ControllerRef.YOU)


class DFCCastCase(StackCase):
    """StackCase plus the two compiled DFC record shapes."""

    def back_face_only(self, name=DFC_NAME, zone=ZONE_HAND):
        """The ZNR shape: a card whose ONLY compiled ability is a BackFace
        (the front text never became a SpellAbility)."""
        rec = record_of([BackFace(face_name="Beyeen Coast", abilities=())], name=name)
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name=name,
                type_line="Creature // Land",
                power=None,
                toughness=None,
                cmc=2,
                colors=(),
            ),
            self.p0,
            zone,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def compiled_front(self, name="Glasspool Mimic // Glasspool Shore"):
        """The control: a record carrying both a SpellAbility and the BackFace behind it
        (Glasspool Mimic's shape); its front casts normally."""
        return self.give(
            name,
            SpellKind.CREATURE,
            type_line="Creature",
            types=("Creature",),
            power=1,
            toughness=2,
            extra_abilities=(BackFace(face_name="Glasspool Shore", abilities=()),),
        )

    def waiver(self, tag):
        """A PrizeClone: an instant whose whole effect is the corpus'
        cost-waiver CAST of the (single) exiled card."""
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(EXILE_YOU,))
        return self.give(
            f"PrizeClone{tag}",
            SpellKind.INSTANT,
            cost=Cost(()),
            effect=Atom(
                verb=Verb.CAST,
                args=AtomArgs(pairs=(("source", sel), ("cost", Cost(())))),
            ),
        )


class TestFaceCastRefusal(DFCCastCase):
    def test_compiled_front_face_casts(self):
        handle = self.compiled_front()
        cast(self.ex, self.p0, handle)
        self.assertEqual(self.world.zone_of(handle).kind, ZONE_BATTLEFIELD)
        rec = self.ex.binder.handle_record[handle]
        self.assertTrue(any(isinstance(a, BackFace) for a in rec.abilities))
        self.assertEqual(self.ex.unresolved_effects, [])

    def test_back_face_only_raises_the_typed_refusal(self):
        handle = self.back_face_only()
        with self.assertRaises(FaceCastAbsentError) as caught:
            cast_card(self.ex, self.p0, handle, cost_override=Cost(()))
        exc = caught.exception
        # the dedicated type and the exact site message
        self.assertEqual(str(exc), FACE_MSG)
        self.assertTrue(face_cast_absent(exc))
        # nothing was fabricated: the card never moved, no frame, no event
        self.assertEqual(self.world.zone_of(handle).kind, ZONE_HAND)
        self.assertEqual(self.ex.stack.frames, [])
        self.assertEqual(self.ex.unresolved_effects, [])

    def test_plain_land_refusal_is_not_the_face_cast(self):
        # the land refusal keeps its own message and is not the face cast: type and
        # predicate both say no (the guard skips only the dedicated pair).
        from MTG_bot.core.test_executor_binding import card_id

        land_id = card_id("Plains")
        rec = record_of([], name="Plains", oid=land_id.oracle_id)
        handle = self.world.add_card(land_id, self.p0, ZONE_HAND)
        self.ex.attach_card(handle, rec)
        with self.assertRaises(ValueError) as caught:
            cast_card(self.ex, self.p0, handle, cost_override=Cost(()))
        exc = caught.exception
        self.assertNotIsInstance(exc, FaceCastAbsentError)
        self.assertFalse(face_cast_absent(exc))
        self.assertEqual(str(exc), "executor: CAST Plains: no SpellAbility on the card")

    def test_lookalike_message_never_matches_the_predicate(self):
        # a bare ValueError wearing the face-cast's words is NOT skipped.
        lookalike = ValueError(FACE_MSG)
        self.assertFalse(face_cast_absent(lookalike))
        # the predicate rebuilds from the STORED name: a tampered type
        # pairing does not match either.
        honest = FaceCastAbsentError(DFC_NAME)
        honest.face_name = "Someone Else"
        self.assertFalse(face_cast_absent(honest))


class TestGuardedLane(DFCCastCase):
    """Coveted Prize's full-party free cast designating an uncompiled-front MDFC: the live lane
    skips the CAST step, records it once per distinct card, and the game plays on."""

    def test_guarded_cast_skips_and_ledgers(self):
        dfc = self.back_face_only(zone=ZONE_EXILE)
        prize = self.waiver("")
        cast(self.ex, self.p0, prize)  # must NOT raise
        self.assertEqual(self.world.zone_of(prize).kind, ZONE_GRAVEYARD)
        # nothing was fabricated: the DFC sits untouched in exile
        self.assertEqual(self.world.zone_of(dfc).kind, ZONE_EXILE)
        # LOUD, once, naming the producer card and the site refusal
        self.assertEqual(len(self.ex.unresolved_effects), 1)
        self.assertIn("PrizeClone", self.ex.unresolved_effects[0])
        self.assertIn(DFC_NAME, self.ex.unresolved_effects[0])
        self.assertIn("no SpellAbility", self.ex.unresolved_effects[0])

    def test_second_occurrence_dedupes_the_count(self):
        # two attempts, one distinct flag with a count of 2 (the ledger keys on the
        # waiver's own name).
        for _ in ("A", "B"):
            self.back_face_only(zone=ZONE_EXILE)
            prize = self.give(
                "PrizeClone",
                SpellKind.INSTANT,
                cost=Cost(()),
                effect=Atom(
                    verb=Verb.CAST,
                    args=AtomArgs(
                        pairs=(
                            (
                                "source",
                                Selector(
                                    QConst(1),
                                    SelectorMode.CHOOSE,
                                    UNIV,
                                    zones=(EXILE_YOU,),
                                ),
                            ),
                            ("cost", Cost(())),
                        )
                    ),
                ),
            )
            cast(self.ex, self.p0, prize)
        self.assertEqual(len(self.ex.unresolved_effects), 1)
        self.assertEqual(
            self.ex.unresolved_effect_counts[self.ex.unresolved_effects[0]], 2
        )


if __name__ == "__main__":
    unittest.main()
