""""Can't be blocked by more than one creature" (2026-11-06): a PREVENT_EFFECT over
``DeclareBlockersEvent(count=QAtLeast(2))``.

CR 509.1b: a restriction may limit how many creatures block an attacker. The prevention is of the
attacker becoming blocked by two or more creatures, so one creature may block it and, once one
does, no other is offered the block. Restrictions add up (CR 509.1b), so a menace attacker
(CR 702.111b: "can't be blocked except by two or more creatures") under the limit can't be blocked
at all; a requirement to block it is obeyed as far as the restrictions allow (CR 509.1c), and one
no declaration can obey (the menace attacker under the limit, a flyer nobody can block) does not
keep the other creatures from blocking. The limit is consulted by
``ReplacementRegistry.blockers_allowed``; no single blocker/attacker pair is vetoed by it.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    DeclareBlockersEvent,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    QAtLeast,
    QConst,
    Selector,
    SelectorMode,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
    from_dict,
    to_dict,
)
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD
from MTG_bot.core.test_executor_blockers import BlockerCase
from MTG_bot.core.test_executor_stack import oid

IS_SOURCE = FAtom(FAtomPred.IS_SOURCE)
SELF = Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
BIG_ONES = FAnd(
    (
        FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        FAtom(FAtomPred.POWER_GE, count=QConst(4)),
        FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
    )
)


def at_most_one_blocker(blocked) -> StaticAbility:
    """"<blocked> can't be blocked by more than one creature." (the B15 carrier)"""
    event = DeclareBlockersEvent(FAnd(()), blocked=blocked, count=QAtLeast(2))
    return StaticAbility(
        effect=Atom(Verb.PREVENT_EFFECT, AtomArgs(pairs=(("condition", blocked), ("event", event))))
    )


class LimitCase(BlockerCase):
    def custom(self, name, power, toughness, seat, abilities=(), keywords=(), types=("Creature",)):
        """A battlefield permanent carrying hand-built abilities (its record attached)."""
        type_line = " ".join(types)
        record = CardRecord(
            oracle_id=oid(), name=name, type_line=type_line, types=types, subtypes=(),
            supertypes=(), colors=(), color_identity=frozenset(), mana_cost=None, mana_value=2,
            power=QConst(power) if power is not None else None,
            toughness=QConst(toughness) if toughness is not None else None, loyalty=None,
            keywords=tuple(KeywordAbility(keyword=k) for k in keywords),
            abilities=tuple(abilities), is_token=False,
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=record.oracle_id, name=name, type_line=type_line,
                power=None if power is None else str(power),
                toughness=None if toughness is None else str(toughness), cmc=2,
                keywords=tuple(k.name for k in keywords),
            ),
            seat,
            ZONE_BATTLEFIELD,
        )
        self.ex.attach_card(handle, record)
        return handle

    def fight(self, **blocks) -> None:
        """Run the combat: everything p0 controls attacks, p1's blockers answer from ``blocks``."""
        for blocker, attacker in blocks.items():
            self.answers[f"block:{getattr(self, blocker)}"] = str(getattr(self, attacker))
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)


class TestOneBlockerAtMost(LimitCase):
    def test_once_one_creature_blocks_it_no_other_is_offered_the_block(self) -> None:
        self.boar = self.custom("Boar", 4, 3, self.p0, (at_most_one_blocker(IS_SOURCE),))
        self.wall_a = self.synth("Wall A", 0, 5, self.p1)
        self.wall_b = self.synth("Wall B", 0, 5, self.p1)
        self.begin()
        self.fight(wall_a="boar", wall_b="boar")
        self.assertEqual(self.vocab_for(self.wall_a), (str(self.boar), "NONE"))
        self.assertEqual(self.forced_block(self.wall_b), "NONE")  # its only word
        self.assertEqual(self.blocked_map(), {str(self.boar): [str(self.wall_a)]})

    def test_without_the_limit_both_block(self) -> None:
        self.boar = self.custom("Boar", 4, 3, self.p0)
        self.wall_a = self.synth("Wall A", 0, 5, self.p1)
        self.wall_b = self.synth("Wall B", 0, 5, self.p1)
        self.begin()
        self.fight(wall_a="boar", wall_b="boar")
        self.assertEqual(self.vocab_for(self.wall_b), (str(self.boar), "NONE"))
        self.assertEqual(
            self.blocked_map(), {str(self.boar): [str(self.wall_a), str(self.wall_b)]}
        )

    def test_it_restricts_the_count_not_a_pair(self) -> None:
        boar = self.custom("Boar", 4, 3, self.p0, (at_most_one_blocker(IS_SOURCE),))
        wall = self.synth("Wall A", 0, 5, self.p1)
        self.begin()
        replacements = self.ex.replacements
        self.assertFalse(replacements.prevents_block_declaration(wall, boar))
        self.assertEqual(replacements.blockers_allowed(boar), 1)
        self.assertIsNone(replacements.blockers_allowed(wall))

    def test_menace_and_the_limit_together_leave_no_legal_block(self) -> None:
        self.boar = self.custom(
            "Boar", 4, 3, self.p0, (at_most_one_blocker(IS_SOURCE),), keywords=(Keyword.MENACE,)
        )
        self.wall_a = self.synth("Wall A", 0, 5, self.p1)
        self.wall_b = self.synth("Wall B", 0, 5, self.p1)
        self.begin()
        self.fight(wall_a="boar", wall_b="boar")
        self.assertEqual(self.blocked_map(), {})
        self.assertFalse([w for _v, w in self.seen_asks if w.startswith("block:")])
        self.assertEqual(self.world.players[self.p1].life, 16)

    def test_a_requirement_to_block_it_is_met_by_one_creature(self) -> None:
        lure = StaticAbility(effect=Atom(Verb.MANDATE_BLOCK, AtomArgs(pairs=(("cards", SELF),))))
        self.boar = self.custom("Boar", 4, 3, self.p0, (at_most_one_blocker(IS_SOURCE), lure))
        self.wall_a = self.synth("Wall A", 0, 5, self.p1)
        self.wall_b = self.synth("Wall B", 0, 5, self.p1)
        self.begin()
        self.fight()  # nobody chooses to block: the requirement forces the first Wall
        self.assertEqual(self.forced_block(self.wall_a), str(self.boar))
        self.assertEqual(self.forced_block(self.wall_b), "NONE")
        self.assertEqual(self.blocked_map(), {str(self.boar): [str(self.wall_a)]})


class TestRequirementsTheRestrictionsForbid(LimitCase):
    """CR 509.1c: a requirement that can't be obeyed is not, and the rest of the declaration
    stands (the fresh-eyes review's repro; before, no blocker was asked at all)."""

    LURE = StaticAbility(effect=Atom(Verb.MANDATE_BLOCK, AtomArgs(pairs=(("cards", SELF),))))

    def test_a_menace_attacker_under_the_limit_leaves_the_other_blocks_open(self) -> None:
        self.boar = self.custom("Boar", 4, 3, self.p0, (at_most_one_blocker(IS_SOURCE), self.LURE),
                                keywords=(Keyword.MENACE,))
        self.bear = self.synth("Bear", 2, 2, self.p0)
        self.wall_a = self.synth("Wall A", 0, 5, self.p1)
        self.wall_b = self.synth("Wall B", 0, 5, self.p1)
        self.begin()
        self.fight(wall_a="bear")
        self.assertEqual(self.vocab_for(self.wall_a), (str(self.bear), "NONE"))
        self.assertEqual(self.blocked_map(), {str(self.bear): [str(self.wall_a)]})
        self.assertEqual(self.world.players[self.p1].life, 16)  # the Boar is unblocked

    def test_a_requirement_nobody_may_obey_leaves_the_other_blocks_open(self) -> None:
        self.kite = self.custom("Kite", 2, 2, self.p0, (self.LURE,), keywords=(Keyword.FLYING,))
        self.bear = self.synth("Bear", 2, 2, self.p0)
        self.wall_a = self.synth("Wall A", 0, 5, self.p1)  # no reach: it may not block the Kite
        self.begin()
        self.fight(wall_a="bear")
        self.assertEqual(self.blocked_map(), {str(self.bear): [str(self.wall_a)]})
        self.assertEqual(self.world.players[self.p1].life, 18)


class TestOverAClass(LimitCase):
    def test_only_the_creatures_the_static_names_are_limited(self) -> None:
        self.troll = self.custom("Troll", 6, 5, self.p0, (at_most_one_blocker(BIG_ONES),))
        self.cub = self.synth("Cub", 3, 3, self.p0)
        self.wall_a = self.synth("Wall A", 0, 7, self.p1)
        self.wall_b = self.synth("Wall B", 0, 7, self.p1)
        self.wall_c = self.synth("Wall C", 0, 7, self.p1)
        self.begin()
        self.answers[f"order:{self.cub}"] = "0"
        self.fight(wall_a="troll", wall_b="troll", wall_c="cub")
        self.assertEqual(self.vocab_for(self.wall_b), (str(self.cub), "NONE"))
        blocked = self.blocked_map()
        self.assertEqual(blocked[str(self.troll)], [str(self.wall_a)])

    def test_the_limit_ends_with_its_source(self) -> None:
        self.anthem = self.custom("Anthem", None, None, self.p0, (at_most_one_blocker(BIG_ONES),),
                                  types=("Enchantment",))
        self.ogre = self.synth("Ogre", 5, 5, self.p0)
        self.wall_a = self.synth("Wall A", 0, 7, self.p1)
        self.wall_b = self.synth("Wall B", 0, 7, self.p1)
        self.begin()
        self.assertEqual(self.ex.replacements.blockers_allowed(self.ogre), 1)
        self.world.move_to_zone(self.anthem, self.p0, ZONE_GRAVEYARD)
        self.assertIsNone(self.ex.replacements.blockers_allowed(self.ogre))


class TestIR(LimitCase):
    def test_the_count_is_a_minimum_over_a_blocked_creature(self) -> None:
        with self.assertRaises(ValueError):
            DeclareBlockersEvent(FAnd(()), blocked=IS_SOURCE, count=QConst(2))
        with self.assertRaises(ValueError):
            DeclareBlockersEvent(FAnd(()), count=QAtLeast(2))
        event = DeclareBlockersEvent(FAnd(()), blocked=IS_SOURCE, count=QAtLeast(2))
        self.assertEqual(from_dict("DeclareBlockersEvent", to_dict(event)), event)
        self.assertNotIn("count", to_dict(DeclareBlockersEvent(FAnd(()), blocked=IS_SOURCE)))

    def test_no_trigger_or_history_reads_a_blocker_count(self) -> None:
        event = DeclareBlockersEvent(FAnd(()), blocked=IS_SOURCE, count=QAtLeast(2))
        trigger = TriggeredAbility(
            event=event, condition=None,
            effect=Atom(Verb.GAIN_LIFE, AtomArgs(pairs=(("amount", QConst(1)), ("controller", ControllerRef.YOU)))),
        )
        with self.assertRaises(NotImplementedError):
            self.custom("Watcher", 1, 1, self.p0, (trigger,))
        with self.assertRaises(ValueError):
            FAtom(FAtomPred.EVENT_THIS_TURN, event=event, count=QConst(1))
