"""T4 P1a LOCK: mill / discard / exile trigger MATCHING.

HONEST PROVENANCE (corrected per owner evidence law after fresh-eyes review):
these locks are POST-LOCK — they use the new journal_kind/pop_order/from slots,
which HEAD's AtomArgs cannot construct, so they could NOT have been written
against the old handlers. Behavioral equivalence was established by
byte-comparing the merged lanes' code paths against `git show HEAD` handler
bodies (reviewer-verified), and these tests now lock the merged behavior going
forward. The merged MOVE_ZONE atom — same zone endpoints, journal kind carried
as a slot (A2 ii), mill pop-order kept as an explicit slot (A2 iii),
discard's ``result`` register kept as the moved set (A2 i), exile's
designation role kept as ``target`` (A2 iv) — reproduces them byte-identically.

Why the journal is the right lock: trigger/replacement matching walks the
zone-diff ENDPOINTS (binding.py ``_match_zone_change`` / ``_zone_matches``
vs events.py ``record_atom``), never the verb name.  The only cause_verb
string consumers are the ``TARGET`` designation feed (binding.py:870) and
the ``SACRIFICE`` dies-exclusion (binding.py:1010) — neither touches
MILL/DISCARD/EXILE.  If a merged atom emits the same endpoint rows and the
raw MILL row, no trigger can silently move.

Run names (task mandate): mill_trigger_matching, discard_trigger_matching,
exile_trigger_matching.
"""

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    FAnd,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_CREATURE_DIES, KIND_ZONE_CHANGE
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    GameWorld,
)

_ORACLE_SEQ = itertools.count(900)


def card_id(name, power=None, toughness=None, type_line="Creature"):
    n = next(_ORACLE_SEQ)
    return CardIdentity(
        oracle_id=f"{n:08x}-1111-2222-3333-444444444444",
        name=name,
        type_line=type_line,
        power=power,
        toughness=toughness,
        cmc=2,
        colors=(),
    )


def atom(verb, **roles):
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
BF_YOU = Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)
GY_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
GY_ANY = Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)
HAND_YOU = Zone(ZoneKind.HAND, ControllerRef.YOU)
EXILE_ANY = Zone(ZoneKind.EXILE, ControllerRef.ANY)
LIB_YOU = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
ANY_ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)
UNIV = FAnd(())


def gain(n, who=ControllerRef.YOU) -> Atom:
    return atom(Verb.GAIN_LIFE, controller=who, amount=QConst(n))


def record_of(abilities, name="Rec", oid=None) -> CardRecord:
    return CardRecord(
        oracle_id=oid or f"{next(_ORACLE_SEQ):08x}-1111-2222-3333-444444444444",
        name=name,
        type_line="Creature",
        types=("Creature",),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=2,
        power=QConst(2),
        toughness=QConst(2),
        loyalty=None,
        keywords=(),
        abilities=tuple(abilities),
        is_token=False,
    )


class P1aMatchingCase(unittest.TestCase):
    """Watcher carrier on the battlefield; library, hand and one victim."""

    def setUp(self):
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.watch = self.world.add_card(card_id("Watcher"), self.p0, ZONE_BATTLEFIELD)
        self.libs = [
            self.world.add_card(card_id(f"L{i}"), self.p0) for i in (1, 2, 3, 4)
        ]
        self.h1 = self.world.add_card(card_id("H1"), self.p0, ZONE_HAND)
        self.h2 = self.world.add_card(card_id("H2"), self.p0, ZONE_HAND)
        self.victim = self.world.add_card(
            card_id("Victim", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def life(self, player):
        return self.world.players[player].life

    def zone(self, player, kind):
        return list(self.world.players[player].zone(kind).entries)

    def attach_trigger(self, handle, event, effect):
        """Attach ``event -> effect`` as a triggered ability on the world
        card itself (identity-checked oracle-id bridge)."""
        rec = record_of(
            [TriggeredAbility(event, None, effect)],
            name="Rec",
            oid=self.world.cards[handle].identity.oracle_id,
        )
        self.ex.attach_card(handle, rec)

    def zone_rows(self):
        return [
            (e.subject, e.zone_move)
            for e in self.ex.journal.events
            if e.kind == KIND_ZONE_CHANGE
        ]

    def raw_rows(self, kind):
        return [t for t in self.ex.events if t[1] == kind]


class TestTriggerMatching(P1aMatchingCase):
    def test_mill_trigger_matching(self):
        # "Whenever you put a card from your library into your graveyard"
        # — a mill-shaped ZoneChangeEvent must fire on the merged MOVE too.
        self.attach_trigger(self.watch, ZoneChangeEvent(LIB_YOU, GY_YOU), gain(1))
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                controller=ControllerRef.YOU,
                amount=QConst(2),
                **{
                    "destination": GY_YOU,
                    "from": LIB_YOU,
                    "journal_kind": "MILL",
                    "pop_order": "TOP",
                },
            ),
            source=self.watch,
            controller=self.p0,
        )
        # A2(iii): the pop order is TOP of library (last entry first).
        self.assertEqual(
            self.raw_rows("MILL"),
            [
                (0, "MILL", str(self.libs[3]), "library->graveyard"),
                (1, "MILL", str(self.libs[2]), "library->graveyard"),
            ],
        )
        self.assertEqual(
            self.zone_rows(),
            [
                (self.libs[3], ("library", "graveyard", self.p0, self.p0)),
                (self.libs[2], ("library", "graveyard", self.p0, self.p0)),
            ],
        )
        self.assertEqual(self.life(self.p0), 22)  # matcher fired once PER card
        self.assertEqual(
            self.zone(self.p0, ZONE_GRAVEYARD), [self.libs[3], self.libs[2]]
        )
        self.assertEqual(
            [e for e in self.ex.journal.events if e.kind == KIND_CREATURE_DIES], []
        )

    def test_discard_trigger_matching(self):
        # "Whenever you discard a card" = HAND->GRAVEYARD endpoint match.
        self.attach_trigger(self.watch, ZoneChangeEvent(HAND_YOU, GY_YOU), gain(1))
        # A2(i): the DISCARDED SET is the result register — observed through
        # a same-resolution referent="result" consumer (B-9 lane).  The
        # hand holds TWO cards but only H1 is discarded: the register must
        # be exactly [H1], never the candidate pool.
        consumer = atom(
            Verb.TAP,
            target=Selector(
                QConst(1), SelectorMode.CHOOSE, UNIV, ANY_ANY, referent="result"
            ),
        )
        self.ex.apply_effect(
            Seq(
                (
                    atom(
                        Verb.MOVE_ZONE,
                        controller=ControllerRef.YOU,
                        cards=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_YOU),
                        **{"destination": GY_YOU, "from": HAND_YOU},
                    ),
                    consumer,
                )
            ),
            source=self.watch,
            controller=self.p0,
            bindings={"cards": [self.h1]},
        )
        self.assertEqual(
            self.zone_rows(), [(self.h1, ("hand", "graveyard", self.p0, self.p0))]
        )
        self.assertEqual(self.life(self.p0), 21)
        self.assertEqual(self.zone(self.p0, ZONE_GRAVEYARD), [self.h1])
        self.assertTrue(self.world.cards[self.h1].tapped)
        self.assertFalse(
            self.world.cards[self.h2].tapped,
            "result register leaked the full candidate hand",
        )
        self.assertEqual(
            [e for e in self.ex.journal.events if e.kind == KIND_CREATURE_DIES], []
        )

    def test_exile_trigger_matching(self):
        # "Whenever a permanent you control is exiled" — BF->EXILE endpoint
        # match; exile must NEVER look like a death (no BF->GRAVEYARD row).
        self.attach_trigger(
            self.watch,
            ZoneChangeEvent(BF_YOU, EXILE_ANY, subject=None),
            gain(1),
        )
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                target=Selector(QConst(1), SelectorMode.TARGET, UNIV, BF_ANY),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
            source=self.watch,
            controller=self.p0,
            bindings={"target": self.victim},
        )
        self.assertEqual(
            self.zone_rows(),
            [(self.victim, ("battlefield", "exile", self.p0, self.p0))],
        )
        self.assertEqual(self.life(self.p0), 21)
        self.assertEqual(
            [e for e in self.ex.journal.events if e.kind == KIND_CREATURE_DIES], []
        )


if __name__ == "__main__":
    unittest.main()
