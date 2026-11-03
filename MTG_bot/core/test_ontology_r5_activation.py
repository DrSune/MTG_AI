"""Ontology R5-7 (docs/DESIGN_ATOM_ONTOLOGY.md §10, gate round 3 GO): one CR
605.1a classifier, ``AbilityActivatedEvent(source, kind, actor)``, the
activation lock in ``ability_playable`` and one journal row per activation.

CR 605.1a, read from the Comprehensive Rules: "An activated ability is a mana
ability if it meets all of the following criteria: it doesn't require a target
(see rule 115.6), it could add mana to a player's mana pool when it resolves,
it's not a loyalty ability (see rule 606, "Loyalty Abilities"), and its cost
and effect don't move any card to or from a library."
"""

from __future__ import annotations

import unittest

import pytest

from MTG_bot.core.ability_tree import (
    AbilityActivatedEvent,
    AbilityKind,
    ActivatedAbility,
    Atom,
    CardRecord,
    Choose,
    ControllerRef,
    Cost,
    CostDiscard,
    CostLoyalty,
    CostManaGeneric,
    CostSacrifice,
    CostTap,
    DelayedTrigger,
    DurationEot,
    FAtom,
    FAtomPred,
    Phase,
    QConst,
    Selector,
    SelectorMode,
    StaticAbility,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    activation_matches_kind,
    from_dict,
    is_loyalty_ability,
    is_mana_ability,
    to_dict,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_ABILITY_ACTIVATED
from MTG_bot.core.executor.legality import ability_playable, activate
from MTG_bot.core.executor.query import legal_activations
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld
from MTG_bot.core.test_executor_binding import (
    BF_ANY,
    HAND_YOU,
    LIB_YOU,
    UNIV,
    atom,
    card_id,
    draw_one,
    gain,
    mill_one,
    record_of,
    reset_oracle_ids,
)

# ---------------------------------------------------------------- IR pieces


def add_mana(color: str = "G") -> Atom:
    return atom(Verb.ADD_MANA, controller=ControllerRef.YOU, amount=QConst(1), color=color)


def target_creature() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(BF_ANY,),
    )


def tap_ability(effect, *, cost=None) -> ActivatedAbility:
    return ActivatedAbility(cost=cost or Cost(parts=(CostTap(),)), effect=effect)


def seq(*steps):
    from MTG_bot.core.ability_tree import Seq

    return Seq(steps=steps)


class TestManaAbilityClassifier(unittest.TestCase):
    """CR 605.1a, every criterion, on synthetic abilities (0 pool cards hit
    the library criterion today, so the IR shapes are built here)."""

    def test_plain_mana_ability(self) -> None:
        self.assertTrue(is_mana_ability(tap_ability(add_mana())))

    def test_mana_ability_that_does_more_is_still_one(self) -> None:
        # "{T}: Add {B}. You lose 1 life." — 605.1a asks only "could add mana";
        # the old drivers' "only ADD_MANA/TAP atoms" test said no.
        lose = atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=QConst(1))
        self.assertTrue(is_mana_ability(tap_ability(seq(add_mana("B"), lose))))

    def test_no_reachable_add_mana_is_not_one(self) -> None:
        # "{T}: Tap target creature" (Shacklegeist): no mana, and a target.
        tap = atom(Verb.TAP, target=target_creature())
        self.assertFalse(is_mana_ability(tap_ability(tap)))
        self.assertFalse(is_mana_ability(tap_ability(gain(1))))

    def test_mana_choice_is_one(self) -> None:
        # a dual land's "Add {R} or {G}": ADD_MANA reachable in every option
        both = Choose(count=QConst(1), options=(add_mana("R"), add_mana("G")))
        self.assertTrue(is_mana_ability(tap_ability(both)))

    def test_non_tap_cost_is_fine(self) -> None:
        # Prismite: "{2}: Add one mana of any color."
        prism = ActivatedAbility(
            cost=Cost(parts=(CostManaGeneric(QConst(2)),)), effect=add_mana("ANY")
        )
        self.assertTrue(is_mana_ability(prism))

    def test_a_target_disqualifies(self) -> None:
        # 605.5a: an ability with a target is not a mana ability.
        ping = atom(Verb.DEAL_DAMAGE, target=target_creature(), amount=QConst(1))
        self.assertFalse(is_mana_ability(tap_ability(seq(add_mana("R"), ping))))

    def test_a_target_player_disqualifies(self) -> None:
        # "target player gains 1 life": the TARGET_PLAYER coordinate is a target.
        heal = gain(1, who=ControllerRef.TARGET_PLAYER)
        self.assertFalse(is_mana_ability(tap_ability(seq(add_mana(), heal))))

    def test_loyalty_disqualifies_even_zero(self) -> None:
        plus = ActivatedAbility(cost=Cost(parts=(CostLoyalty(1),)), effect=add_mana("R"))
        zero = ActivatedAbility(cost=Cost(parts=(CostLoyalty(0),)), effect=add_mana("R"))
        for ability in (plus, zero):
            self.assertTrue(is_loyalty_ability(ability))
            self.assertFalse(is_mana_ability(ability))

    def test_effect_moving_a_card_from_a_library_disqualifies(self) -> None:
        # draw (library -> hand), mill (library -> graveyard), a MOVE_ZONE
        # whose selector names the library, and a Verb.DRAW atom
        draw_verb = atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1))
        for extra in (draw_one(), mill_one(), draw_verb):
            with self.subTest(extra=extra.verb.name):
                self.assertFalse(is_mana_ability(tap_ability(seq(add_mana(), extra))))

    def test_effect_moving_a_card_to_a_library_disqualifies(self) -> None:
        # "Put a card from your hand on top of your library."
        put_back = atom(
            Verb.MOVE_ZONE,
            cards=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,)),
            destination=LIB_YOU,
        )
        self.assertFalse(is_mana_ability(tap_ability(seq(add_mana(), put_back))))

    def test_scry_keeps_cards_in_the_library(self) -> None:
        # 701.22a: scry puts cards on top or bottom of the SAME library.
        scry = atom(Verb.SCRY, controller=ControllerRef.YOU, count=QConst(1))
        self.assertTrue(is_mana_ability(tap_ability(seq(add_mana(), scry))))

    def test_cost_moving_a_card_from_a_library_disqualifies(self) -> None:
        lib_card = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,))
        for part in (CostDiscard(target=lib_card), CostSacrifice(target=lib_card)):
            with self.subTest(part=type(part).__name__):
                ability = ActivatedAbility(cost=Cost(parts=(part,)), effect=add_mana())
                self.assertFalse(is_mana_ability(ability))
        # sacrificing a permanent (Treasure) moves it to the graveyard: fine
        treasure = ActivatedAbility(
            cost=Cost(
                parts=(
                    CostTap(),
                    CostSacrifice(
                        target=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAtom(FAtomPred.IS_SOURCE),
                            zones=(BF_ANY,),
                        )
                    ),
                )
            ),
            effect=add_mana("ANY"),
        )
        self.assertTrue(is_mana_ability(treasure))

    def test_foreign_abilities_are_not_looked_into(self) -> None:
        # A delayed trigger adds its mana when IT resolves, not this ability.
        later = DelayedTrigger(
            duration=DurationEot(),
            event=TurnPhaseEvent(phase=Phase.FIRST_MAIN),
            condition=None,
            effect=add_mana(),
        )
        self.assertFalse(is_mana_ability(tap_ability(later)))
        # "Target creature gains '{T}: Add {G}'": the granted ADD_MANA is the
        # granted ability's, and the grant targets.
        grant = atom(
            Verb.GRANT_ABILITY,
            target=target_creature(),
            ability=tap_ability(add_mana()),
            duration=DurationEot(),
        )
        self.assertFalse(is_mana_ability(tap_ability(grant)))

    def test_only_activated_abilities_qualify(self) -> None:
        self.assertFalse(is_mana_ability(StaticAbility(effect=add_mana())))
        self.assertFalse(is_mana_ability(None))

    def test_kind_matching(self) -> None:
        mana = tap_ability(add_mana())
        other = tap_ability(gain(1))
        loyal = ActivatedAbility(cost=Cost(parts=(CostLoyalty(-1),)), effect=gain(1))
        table = {
            AbilityKind.ANY: (True, True, True),
            AbilityKind.NON_MANA: (False, True, True),
            AbilityKind.LOYALTY: (False, False, True),
        }
        for kind, expected in table.items():
            got = tuple(activation_matches_kind(a, kind) for a in (mana, other, loyal))
            self.assertEqual(got, expected, kind)


class TestAbilityActivatedEventNode(unittest.TestCase):
    def test_kind_is_required(self) -> None:
        with pytest.raises(TypeError):
            AbilityActivatedEvent(source=UNIV)  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="kind must be an AbilityKind"):
            AbilityActivatedEvent(source=UNIV, kind="ANY")  # type: ignore[arg-type]

    def test_roundtrip_and_strict_decode(self) -> None:
        node = AbilityActivatedEvent(
            source=FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE), kind=AbilityKind.NON_MANA
        )
        d = to_dict(node)
        self.assertNotIn("actor", d)  # omitted at its None default
        self.assertEqual(from_dict("AbilityActivatedEvent", d), node)
        del d["kind"]
        with pytest.raises(ValueError, match="missing fields"):
            from_dict("AbilityActivatedEvent", d)

    def test_zero_loyalty_has_one_spelling(self) -> None:
        self.assertEqual(CostLoyalty(0).delta, 0)
        with pytest.raises(ValueError, match="never QConst"):
            CostLoyalty(QConst(0))


# ---------------------------------------------------------- engine fixtures


def _oid(n: int) -> str:
    return f"{n:08x}-5555-6666-7777-888888888888"


def aura_record(lock_kind: AbilityKind, oid: str) -> CardRecord:
    """Faith's Fetters' lock alone: PREVENT_EFFECT over the enchanted
    permanent's activations of ``lock_kind``."""
    enchanted = FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE)
    lock = atom(
        Verb.PREVENT_EFFECT,
        condition=enchanted,
        event=AbilityActivatedEvent(source=enchanted, kind=lock_kind),
    )
    base = record_of([StaticAbility(effect=lock)], name="Lock Aura", oid=oid)
    from dataclasses import replace

    return replace(
        base,
        type_line="Enchantment — Aura",
        types=("Enchantment",),
        subtypes=("Aura",),
        power=None,
        toughness=None,
    )


FREE = Cost()


class EngineCase(unittest.TestCase):
    """A host with a mana ability (0), a non-mana ability (1) and a loyalty
    ability (2), all free of mana so the gate is the only thing judged."""

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=57)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.host = self.world.add_card(
            CardIdentity(
                oracle_id=_oid(1),
                name="Locked Walker",
                type_line="Legendary Planeswalker — Test",
                cmc=3,
                loyalty="3",
            ),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.abilities = [
            ActivatedAbility(cost=FREE, effect=add_mana("G")),
            ActivatedAbility(cost=FREE, effect=gain(1)),
            ActivatedAbility(cost=Cost(parts=(CostLoyalty(0),)), effect=gain(2)),
        ]
        self.ex.attach_card(self.host, record_of(self.abilities, oid=_oid(1)))

    def lock_with(self, kind: AbilityKind) -> object:
        aura = self.world.add_card(
            card_id("Lock Aura", type_line="Enchantment — Aura", oid=_oid(2)),
            self.p1,
            ZONE_BATTLEFIELD,
        )
        self.ex.attach_card(aura, aura_record(kind, _oid(2)))
        self.ex.attach_aura(aura, self.host)
        return aura

    def playable(self) -> tuple[str | None, ...]:
        return tuple(
            ability_playable(self.world, self.ex, self.host, i, seat=self.p0)
            for i in range(3)
        )

    def rows(self):
        return [e for e in self.ex.journal.events if e.kind == KIND_ABILITY_ACTIVATED]


LOCKED = "prohibited:activation_lock"


class TestActivationLock(EngineCase):
    """CR 602.5: "A player can't begin to activate an ability that's
    prohibited from being activated." The gate sits in ability_playable."""

    def test_no_lock(self) -> None:
        self.assertEqual(self.playable(), (None, None, None))

    def test_non_mana_lock_spares_only_the_mana_ability(self) -> None:
        # Faith's Fetters: loyalty abilities are non-mana (605.1a), so locked.
        self.lock_with(AbilityKind.NON_MANA)
        self.assertEqual(self.playable(), (None, LOCKED, LOCKED))
        rows = {o.ability_idx for o in legal_activations(self.world, self.ex, self.p0)}
        self.assertEqual(rows, {0})
        with pytest.raises(ValueError, match=LOCKED):
            activate(self.ex, self.host, 1, seat=self.p0)
        activate(self.ex, self.host, 0, seat=self.p0, decisions=("G",))
        self.assertEqual(self.world.players[self.p0].mana_pool.get("G"), 1)

    def test_any_lock_takes_the_mana_ability_too(self) -> None:
        # Arachnus Web's "can't be activated": every source of the payment
        # witness asks ability_playable, so a locked mana ability is skipped.
        self.lock_with(AbilityKind.ANY)
        self.assertEqual(self.playable(), (LOCKED, LOCKED, LOCKED))
        self.assertEqual(legal_activations(self.world, self.ex, self.p0), [])

    def test_loyalty_lock(self) -> None:
        self.lock_with(AbilityKind.LOYALTY)
        self.assertEqual(self.playable(), (None, None, LOCKED))

    def test_lock_ends_when_the_aura_leaves(self) -> None:
        aura = self.lock_with(AbilityKind.NON_MANA)
        self.world.move_to_zone(aura, self.p1, ZONE_GRAVEYARD)
        self.ex.binder.on_events()
        self.assertEqual(self.playable(), (None, None, None))

    def test_lock_reads_its_own_host_only(self) -> None:
        self.lock_with(AbilityKind.ANY)
        other = self.world.add_card(
            card_id("Free Elf", "1", "1", oid=_oid(3)), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.attach_card(other, record_of([self.abilities[1]], oid=_oid(3)))
        self.assertIsNone(ability_playable(self.world, self.ex, other, 0, seat=self.p0))


class TestActivationJournal(EngineCase):
    """One ABILITY_ACTIVATED row per activation, mana abilities included."""

    def test_every_activation_journals_one_row(self) -> None:
        activate(self.ex, self.host, 0, seat=self.p0, decisions=("G",))
        activate(self.ex, self.host, 1, seat=self.p0)
        activate(self.ex, self.host, 2, seat=self.p0)
        got = [(r.subject, r.cause, r.activation) for r in self.rows()]
        self.assertEqual(
            got,
            [
                (self.host, self.p0, (0, True, None)),  # mana (605.1a)
                (self.host, self.p0, (1, False, None)),
                (self.host, self.p0, (2, False, 0)),  # [0]: a loyalty ability
            ],
        )

    def test_zero_loyalty_ability_is_the_turns_loyalty_ability(self) -> None:
        activate(self.ex, self.host, 2, seat=self.p0)
        self.assertEqual(self.world.cards[self.host].counters.get("LOYALTY"), 3)
        self.assertEqual(self.ex.loyalty_clock.get(self.host), self.world.turn)
        self.assertEqual(
            ability_playable(self.world, self.ex, self.host, 2, seat=self.p0),
            "window:loyalty:once_per_turn",
        )

    def _watch(self, kind: AbilityKind) -> None:
        watcher = self.world.add_card(
            card_id("Watcher", "1", "1", oid=_oid(4)), self.p1, ZONE_BATTLEFIELD
        )
        trigger = TriggeredAbility(
            event=AbilityActivatedEvent(source=UNIV, kind=kind),
            condition=None,
            effect=gain(1),
        )
        self.ex.attach_card(watcher, record_of([trigger], oid=_oid(4)))

    def _life_after_each(self) -> list[int]:
        out = []
        for idx in range(3):
            decisions = ("G",) if idx == 0 else ()
            activate(self.ex, self.host, idx, seat=self.p0, decisions=decisions)
            self.ex.fire_triggers()
            out.append(self.world.players[self.p1].life)
        return out

    def test_trigger_kinds(self) -> None:
        for kind, expected in (
            (AbilityKind.ANY, [21, 22, 23]),
            (AbilityKind.NON_MANA, [20, 21, 22]),
            (AbilityKind.LOYALTY, [20, 20, 21]),
        ):
            with self.subTest(kind=kind.name):
                self.setUp()
                self._watch(kind)
                self.assertEqual(self._life_after_each(), expected)

