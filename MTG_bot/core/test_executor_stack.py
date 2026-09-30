"""Round-13b test suite: the spell stack, the casting pipeline, the CAST
event feed, the mana-policy consumers and the PLAY_LAND move.

Coverage contract (mission /11 §13b):
  * CR 601.2 order end-to-end (legality -> declaration -> payment ->
    stack -> resolution -> put), instant AND permanent destinations;
  * the SpellKind window table (instants ungated, everything else
    sorcery-timed on 13a's phase clock);
  * target designation through the query's OWN oracle, including the
    ANY-target player widening and the TARGET_PLAYER coordinate channel;
  * the crafted QX spell (X-floor witness, declared-X fold, too-big X
    as a reason not a raise, {X} flowing from declaration into effect);
  * land drop gates and the once-per-turn ledger;
  * the CastSpellEvent trigger feed: controller / ordinal / from_zone /
    from_zone_not / COLOR_IN filter, triggers resolving ABOVE the spell;
  * the effect-side CAST atom (cost waiver vs full cost, cast-from-
    wherever, the cast event firing);
  * PAY / CHOOSE / CHOOSE_NAME / MANA_POLICY (Vodalian THIS_MANA, Orrery
    ALL_YOURS) and their legality-gate consumers;
  * the fingerprint completeness fold (a stack frame must change the
    executor fingerprint) and replay identity WITH the new folds.
"""

from __future__ import annotations

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    CastSpellEvent,
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    CostTap,
    CounterKind,
    EtBState,
    FAtom,
    FAtomPred,
    FOr,
    OptionalEffect,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import (
    ability_playable,
    activate,
    ctx_for,
    spell_castable,
)
from MTG_bot.core.executor.query import (
    legal_casts,
    optional_offer,
    spell_target_slots,
    verb_choose_options,
)
from MTG_bot.core.executor.stack import (
    SpellObject,
    cast,
    land_playable,
    park,
    play_land,
)
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_STACK,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    UNIV,
    atom,
    card_id,
    record_of,
    reset_oracle_ids,
)

_OID = itertools.count(9000)

ANY_ZONE = Zone(ZoneKind.ANY, ControllerRef.ANY)
HAND_OPP = Zone(ZoneKind.HAND, ControllerRef.OPPONENT)
BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
CREATURE_F = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
INSTANT_F = FAtom(FAtomPred.TYPE_EQ, string_value="Instant")
INSTANT_OR_SORCERY = FOr((INSTANT_F, FAtom(FAtomPred.TYPE_EQ, string_value="Sorcery")))


def oid() -> str:
    return f"{next(_OID):08x}-1111-2222-3333-444444444444"


def spell_rec(
    name,
    kind,
    *,
    cost=None,
    effect=None,
    type_line="Instant",
    types=("Instant",),
    colors=(),
    power=None,
    toughness=None,
    cmc=2,
    additional_costs=(),
    extra_abilities=(),
    my_oid=None,
):
    """A compiled CardRecord carrying a SpellAbility (printed cost on the
    record, as the frozen grammar demands) plus optional extra ability
    nodes (triggers, statics)."""
    return CardRecord(
        oracle_id=my_oid or oid(),
        name=name,
        type_line=type_line,
        types=types,
        subtypes=(),
        supertypes=(),
        colors=colors,
        color_identity=frozenset(colors),
        mana_cost=cost,
        mana_value=cmc,
        power=QConst(int(power)) if power is not None else None,
        toughness=QConst(int(toughness)) if toughness is not None else None,
        loyalty=None,
        keywords=(),
        abilities=(
            (SpellAbility(kind=kind, effect=effect, additional_costs=additional_costs),)
            + tuple(extra_abilities)
        ),
        is_token=False,
    )


def any_target(n=1) -> Selector:
    return Selector(QConst(n), SelectorMode.TARGET, UNIV, ANY_ZONE)


class StackCase(unittest.TestCase):
    """p0/p1 with an executor; own turn open in FIRST_MAIN (window-ready)."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)

    # ------------------------------------------------------------- helpers

    def give(
        self,
        name,
        kind,
        *,
        cost=None,
        effect=None,
        seat=None,
        zone=ZONE_HAND,
        type_line="Instant",
        types=("Instant",),
        colors=(),
        power=None,
        toughness=None,
        additional_costs=(),
        extra_abilities=(),
    ):
        """A world card + its compiled record attached (oracle bridge),
        wherever asked. Returns the handle."""
        seat = seat if seat is not None else self.p0
        rec = spell_rec(
            name,
            kind,
            cost=cost,
            effect=effect,
            type_line=type_line,
            types=types,
            colors=colors,
            power=power,
            toughness=toughness,
            additional_costs=additional_costs,
            extra_abilities=extra_abilities,
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name=name,
                type_line=type_line,
                power=power,
                toughness=toughness,
                cmc=2,
                colors=colors,
            ),
            seat,
            zone,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def mana(self, seat, **keys):
        pool = self.world.players[seat].mana_pool
        for key, amount in keys.items():
            pool[key] = pool.get(key, 0) + amount

    def journal_rows(self, kind):
        return [row for row in self.ex.journal.dump() if row[1] == kind]

    def journal_events(self, kind):
        """The real GameEvent objects (typed .data + the .cast property),
        unlike the fingerprint-facing dump() which reprs the payload."""
        return [e for e in self.ex.journal.events if e.kind == kind]

    def shock(self, name="Shock", cost_amt=1):
        return self.give(
            name,
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("R", QConst(cost_amt)),)),
            effect=atom(Verb.DEAL_DAMAGE, target=any_target(), amount=QConst(2)),
        )

    def dummy_frame(self, handle, x=None):
        return SpellObject(
            handle=handle,
            node=SpellAbility(kind=SpellKind.INSTANT),
            controller=self.p0,
            spell_kind="INSTANT",
            x_value=x,
        )


class TestCastPipeline(StackCase):
    def test_instant_deals_damage_lands_graveyard_and_emits_cast(self):
        shock = self.shock()
        self.mana(self.p0, R=1)
        frame = cast(self.ex, self.p0, shock, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)  # dealt
        self.assertEqual(self.world.zone_of(shock).kind, ZONE_GRAVEYARD)  # put
        self.assertNotIn("R", self.world.players[self.p0].mana_pool)  # paid
        self.assertEqual(frame.spell_kind, "INSTANT")
        self.assertEqual(frame.declared_targets, (self.p1,))
        self.assertEqual(frame.from_zone, "hand")
        evs = self.journal_events("CAST")
        self.assertEqual(len(evs), 1)
        ev = evs[0]
        self.assertEqual(ev.subject, shock)  # the SPELL card is the subject
        caster, ordinal, kind, from_zone, xval = ev.cast
        self.assertEqual(caster, self.p0)
        self.assertEqual(ordinal, 1)  # first cast this turn
        self.assertEqual(kind, "INSTANT")
        self.assertEqual(from_zone, "hand")
        self.assertIsNone(xval)
        # the park AND the put both ride the journal: hand->stack (601.2h)
        # then stack->graveyard (601.2j). The stack zone is visible to the
        # journal even though the WORLD fingerprint skips it.
        zc = [e.data[:2] for e in self.journal_events("ZONE_CHANGE")]
        self.assertIn(("hand", "stack"), zc)
        self.assertIn(("stack", ZONE_GRAVEYARD), zc)

    def _zap(self, name):
        return self.give(
            name,
            SpellKind.INSTANT,
            effect=atom(
                Verb.DEAL_DAMAGE,
                target=Selector(QConst(1), SelectorMode.TARGET, CREATURE_F, BF_ANY),
                amount=QConst(0),  # probe casts: the target must survive
            ),
        )

    def test_targets_validated_through_the_query_oracle(self):
        creature = self.world.add_card(
            card_id("Target", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        ok = cast(self.ex, self.p0, self._zap("Zap"), targets=(creature,))
        self.assertEqual(ok.declared_targets, (creature,))
        # off-population: a PLAYER handle cannot satisfy a creature target
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, self._zap("Zap2"), targets=(self.p1,))
        self.assertIn("off_population", str(cm.exception))
        # cardinality: two creatures into an exactly-1 slot
        other = self.world.add_card(
            card_id("Other", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, self._zap("Zap3"), targets=(creature, other))
        self.assertIn("count_above_max", str(cm.exception))

    def test_any_target_population_widens_to_players(self):
        shock = self.shock()
        node = next(
            a
            for a in self.ex.binder.handle_record[shock].abilities
            if isinstance(a, SpellAbility)
        )
        slots = spell_target_slots(self.ex, node, spell_handle=shock, seat=self.p0)
        self.assertEqual(len(slots), 1)
        self.assertIn(self.p1, slots[0].candidates)  # ANY-target names players
        self.assertIn("card", {h.namespace for h in slots[0].candidates})

    def test_multi_target_spell_stays_loud(self):
        spell = self.give(
            "DoubleZap",
            SpellKind.INSTANT,
            effect=Seq(
                (
                    atom(
                        Verb.DEAL_DAMAGE,
                        target=Selector(
                            QConst(1), SelectorMode.TARGET, CREATURE_F, BF_ANY
                        ),
                        amount=QConst(1),
                    ),
                    atom(
                        Verb.DEAL_DAMAGE,
                        target=Selector(
                            QConst(1),
                            SelectorMode.TARGET,
                            FAtom(FAtomPred.TYPE_EQ, string_value="Enchantment"),
                            BF_ANY,
                        ),
                        amount=QConst(1),
                    ),
                )
            ),
        )
        creature = self.world.add_card(
            card_id("Victim", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        with self.assertRaises(NotImplementedError):
            cast(self.ex, self.p0, spell, targets=(creature,))

    def test_creature_lands_battlefield_etb_live(self):
        etb = TriggeredAbility(
            event=ZoneChangeEvent(ANY_ZONE, BF_ANY, subject=UNIV),
            condition=None,
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
        )
        critter = self.give(
            "ETBling",
            SpellKind.CREATURE,
            cost=Cost((CostManaGeneric(QConst(2)),)),
            type_line="Creature",
            types=("Creature",),
            power="2",
            toughness="2",
            extra_abilities=(etb,),
        )
        self.mana(self.p0, C=2)
        cast(self.ex, self.p0, critter)
        self.assertEqual(self.world.zone_of(critter).kind, ZONE_BATTLEFIELD)
        # the ETB trigger went live BEFORE the settle matched the event:
        self.assertEqual(self.world.players[self.p0].life, 23)

    def test_window_table(self):
        creature = self.give(
            "Bear",
            SpellKind.CREATURE,
            type_line="Creature",
            types=("Creature",),
            power="2",
            toughness="2",
        )
        instant = self.give("Free", SpellKind.INSTANT)  # costless: window-only
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)  # opponent's turn now
        self.assertEqual(
            spell_castable(self.ex, self.p0, creature)[0], "window:not_your_turn"
        )
        # documented permissive reading: instants are ungated at this API
        self.assertIsNone(spell_castable(self.ex, self.p0, instant)[0])
        # own turn, FIRST_MAIN: creature ok; END_TURN phase: gated
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)
        self.assertIsNone(spell_castable(self.ex, self.p0, creature)[0])
        self.ex.phase = "END_TURN"
        self.assertEqual(spell_castable(self.ex, self.p0, creature)[0], "window:phase")
        # a pushed frame gates the sorcery window (the API keeps it real)
        self.ex.phase = "FIRST_MAIN"
        self.ex.stack.push(self.dummy_frame(instant))
        self.assertEqual(
            spell_castable(self.ex, self.p0, creature)[0], "window:stack_nonempty"
        )
        self.ex.stack.pop()

    def test_cast_rejections_are_reasons(self):
        # unknown handle
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, self.p0)  # a PLAYER handle is no card
        self.assertIn("unknown_card", str(cm.exception))
        # not in hand: a battlefield creature
        bf = self.world.add_card(card_id("OnBF", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.assertEqual(
            spell_castable(self.ex, self.p0, bf)[0], f"cast:not_in_hand:{bf}"
        )
        # no compiled record
        bare = self.world.add_card(card_id("Bare", "1", "1"), self.p0, ZONE_HAND)
        self.assertEqual(
            spell_castable(self.ex, self.p0, bare)[0], f"cast:no_record:{bare}"
        )
        # a land is not a spell (record attached, but NO SpellAbility node)
        land_id = card_id("Plains", type_line="Land")
        land = self.world.add_card(land_id, self.p0, ZONE_HAND)
        self.ex.attach_card(land, record_of([], name="Plains", oid=land_id.oracle_id))
        self.assertEqual(
            spell_castable(self.ex, self.p0, land)[0], f"cast:not_a_spell:{land}"
        )

    def test_effectless_cast_still_casts(self):
        critter = spell_rec(
            "Gorelike",
            SpellKind.CREATURE,
            cost=Cost((CostManaGeneric(QConst(1)),)),
            effect=None,
            type_line="Creature",
            types=("Creature",),
            power="1",
            toughness="1",
            cmc=1,
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=critter.oracle_id,
                name="Gorelike",
                type_line="Creature",
                power="1",
                toughness="1",
                cmc=1,
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, critter)
        self.mana(self.p0, C=1)
        cast(self.ex, self.p0, handle)
        self.assertEqual(self.world.zone_of(handle).kind, ZONE_BATTLEFIELD)
        self.assertNotIn("C", self.world.players[self.p0].mana_pool)


class TestXGate(StackCase):
    def setUp(self):
        super().setUp()
        # the crafted QX card: {X} generic demand, X damage any target
        self.xspell = self.give(
            "X-Crunch",
            SpellKind.INSTANT,
            cost=Cost((CostManaGeneric(QX()),)),
            effect=atom(Verb.DEAL_DAMAGE, target=any_target(), amount=QX()),
        )

    def test_zero_witness_keeps_the_row_enumerable(self):
        self.mana(self.p0, C=4)
        rows = legal_casts(self.world, self.ex, self.p0)  # x=None -> X=0 witness
        row = next(r for r in rows if r.handle == self.xspell)
        self.assertFalse(row.land)
        assert row.payment is not None
        self.assertEqual(row.payment.mana, ())  # X=0 folds a zero cost

    def test_declared_x_folds_into_the_plan_and_effect(self):
        self.mana(self.p0, C=4)
        rows = legal_casts(self.world, self.ex, self.p0, x=3)
        row = next(r for r in rows if r.handle == self.xspell)
        assert row.payment is not None
        self.assertEqual(row.payment.mana, (("C", 3),))
        cast(self.ex, self.p0, self.xspell, x=3, targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 17)  # X=3 damage
        self.assertEqual(self.world.players[self.p0].mana_pool.get("C"), 1)

    def test_x_too_big_is_a_reason_not_a_raise(self):
        self.mana(self.p0, C=2)
        reason, node, _rec, _plan = spell_castable(self.ex, self.p0, self.xspell, x=9)
        self.assertIsNone(node)
        assert reason is not None
        self.assertIn("cost:mana_generic:2<9", reason)
        with self.assertRaises(ValueError):
            cast(self.ex, self.p0, self.xspell, x=9, targets=(self.p1,))


class TestLandDrop(StackCase):
    def setUp(self):
        super().setUp()
        self.plains = self.world.add_card(
            card_id("Plains", type_line="Land"), self.p0, ZONE_HAND
        )

    def test_play_land_stamps_the_ledger_once_per_turn(self):
        play_land(self.ex, self.p0, self.plains)
        self.assertEqual(self.world.zone_of(self.plains).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.land_ledger[self.p0], (self.world.turn, 1))
        second = self.world.add_card(
            card_id("Plains2", type_line="Land"), self.p0, ZONE_HAND
        )
        reason = land_playable(self.ex, self.p0, second)
        assert reason is not None
        self.assertIn("land:used_this_turn", reason)
        # next turn: allowance refreshed
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)
        self.assertIsNone(land_playable(self.ex, self.p0, second))

    def test_land_gates(self):
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)
        self.assertEqual(
            land_playable(self.ex, self.p0, self.plains), "land:not_own_turn"
        )
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)
        creature = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_HAND)
        self.assertEqual(land_playable(self.ex, self.p0, creature), "land:not_a_land")
        self.ex.phase = "END_TURN"
        self.assertEqual(land_playable(self.ex, self.p0, self.plains), "land:phase")
        self.ex.phase = "FIRST_MAIN"
        self.ex.stack.push(self.dummy_frame(creature))
        self.assertEqual(
            land_playable(self.ex, self.p0, self.plains), "land:stack_nonempty"
        )
        self.ex.stack.pop()
        self.assertIsNone(land_playable(self.ex, self.p0, self.plains))

    def test_extra_land_plays_hook(self):
        second = self.world.add_card(
            card_id("Plains2", type_line="Land"), self.p0, ZONE_HAND
        )
        self.ex.extra_land_plays = 1  # the 13c ADD_LAND_PLAY hook
        play_land(self.ex, self.p0, self.plains)
        play_land(self.ex, self.p0, second)
        self.assertEqual(self.ex.land_ledger[self.p0], (self.world.turn, 2))
        third = self.world.add_card(
            card_id("Plains3", type_line="Land"), self.p0, ZONE_HAND
        )
        reason = land_playable(self.ex, self.p0, third)
        assert reason is not None
        self.assertIn("used_this_turn", reason)

    def test_etb_state_tapped_land_enters_tapped(self):
        # 17a regression pin: the compiled EtBState node ("enters the
        # battlefield tapped" — every M21 checkland and temple) is
        # consumed by the journal's battlefield-ENTRY hook, so the real
        # land drop stamps it. A plain land without the node stays
        # untapped, and the stamp is NOT a tap event (CR 614.1c: an
        # entered state never "becomes tapped").
        rec = spell_rec(
            "Checkland",
            SpellKind.SORCERY,
            type_line="Land",
            types=("Land",),
            extra_abilities=(EtBState(tapped=True),),
        )
        land = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name="Checkland",
                type_line="Land",
                cmc=0,
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(land, rec)
        play_land(self.ex, self.p0, land)
        self.assertTrue(self.world.cards[land].tapped)
        self.assertFalse(self.world.cards[self.plains].tapped)
        # the entry journalled the MOVE, never a tap-toggle row
        tap_rows = [
            e
            for e in self.ex.journal.events
            if e.kind == "TAP_STATE" and e.subject == land
        ]
        self.assertEqual(tap_rows, [])

    def test_etb_state_initial_counters_land(self):
        # "enters with a soul counter" (Equipment idiom, templates_b5c)
        # lands on the permanent as it enters, through the same hook.
        rec = spell_rec(
            "Haunted Gear",
            SpellKind.SORCERY,
            type_line="Land",
            types=("Land",),
            extra_abilities=(
                EtBState(initial_counters=((CounterKind.SOUL, QConst(1)),)),
            ),
        )
        gear = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id, name="Haunted Gear", type_line="Land", cmc=0
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(gear, rec)
        self.ex.extra_land_plays = 1
        play_land(self.ex, self.p0, self.plains)
        play_land(self.ex, self.p0, gear)
        self.assertEqual(self.world.cards[gear].counters.get("SOUL"), 1)

    def test_legal_casts_row_shapes(self):
        shock = self.shock()
        self.mana(self.p0, R=1)
        rows = legal_casts(self.world, self.ex, self.p0)
        handles = [r.handle for r in rows]
        self.assertEqual(handles, sorted(handles))  # Handle-sorted (§5.5)
        land_row = next(r for r in rows if r.handle == self.plains)
        spell_row = next(r for r in rows if r.handle == shock)
        self.assertTrue(land_row.land)
        self.assertIsNone(land_row.payment)
        self.assertIsNone(land_row.node)
        self.assertFalse(spell_row.land)
        assert spell_row.payment is not None
        self.assertEqual(spell_row.payment.mana, (("R", 1),))


class TestCastTriggerFeed(StackCase):
    """The CastSpellEvent binder half: seven corpus cards' compile idiom."""

    def watch(self, event, name="Watch", owner=None):
        owner = owner if owner is not None else self.p0
        trig = TriggeredAbility(
            event=event,
            condition=None,
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
        )
        handle = self.world.add_card(card_id(name, "1", "1"), owner, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            handle,
            record_of(
                [trig], name=name, oid=self.world.cards[handle].identity.oracle_id
            ),
        )
        return handle

    def tiny(self, name="Tiny", colors=(), seat=None, zone=ZONE_HAND):
        return self.give(
            name,
            SpellKind.INSTANT,
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(0)),
            colors=colors,
            seat=seat,
            zone=zone,
        )

    def test_ordinal_scoped_to_the_caster_and_turn(self):
        self.watch(CastSpellEvent(UNIV, controller=ControllerRef.YOU, ordinal=2))
        life0 = self.world.players[self.p0].life
        cast(self.ex, self.p0, self.tiny("A"))  # 1st: watch stays silent
        self.assertEqual(self.world.players[self.p0].life, life0)
        cast(self.ex, self.p0, self.tiny("B"))  # 2nd: the watch fires
        self.assertEqual(self.world.players[self.p0].life, life0 + 1)
        # next turn: the ordinal restarts (journal.begin_turn resets)
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)
        cast(self.ex, self.p0, self.tiny("C"))
        self.assertEqual(self.world.players[self.p0].life, life0 + 1)  # NOT +2

    def test_opponent_second_spell_mangara_shape(self):
        self.watch(CastSpellEvent(UNIV, controller=ControllerRef.OPPONENT, ordinal=2))
        life0 = self.world.players[self.p0].life
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)  # now the watched player casts twice
        cast(self.ex, self.p1, self.tiny("OA", seat=self.p1))
        self.assertEqual(self.world.players[self.p0].life, life0)
        cast(self.ex, self.p1, self.tiny("OB", seat=self.p1))
        self.assertEqual(self.world.players[self.p0].life, life0 + 1)

    def test_color_in_filter_quirion_shape(self):
        blue = FAtom(FAtomPred.COLOR_IN, colors=("U", "B"))
        self.watch(CastSpellEvent(blue, controller=ControllerRef.YOU))
        life0 = self.world.players[self.p0].life
        cast(self.ex, self.p0, self.tiny("Colorless"))
        self.assertEqual(self.world.players[self.p0].life, life0)  # no fire
        cast(self.ex, self.p0, self.tiny("BlueOne", colors=("U",)))
        self.assertEqual(self.world.players[self.p0].life, life0 + 1)  # fired

    def test_from_zone_not_ghostly_shape(self):
        self.watch(
            CastSpellEvent(
                UNIV,
                controller=ControllerRef.OPPONENT,
                from_zone_not=Zone(ZoneKind.HAND, ControllerRef.OPPONENT),
            )
        )
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)
        life0 = self.world.players[self.p0].life
        cast(self.ex, self.p1, self.tiny("FromHand", seat=self.p1))
        self.assertEqual(self.world.players[self.p0].life, life0)  # hand: excluded
        from MTG_bot.core.executor.stack import cast_card

        exiled = self.tiny("FromExile", seat=self.p1, zone=ZONE_EXILE)
        cast_card(self.ex, self.p1, exiled, cost_override=Cost(()))
        self.assertEqual(self.world.players[self.p0].life, life0 + 1)  # fired

    def test_cast_trigger_resolves_above_the_spell(self):
        # the trigger's GAIN_LIFE row must land BEFORE the spell's DAMAGE
        self.watch(CastSpellEvent(UNIV, controller=ControllerRef.YOU))
        shock = self.shock()
        self.mana(self.p0, R=1)
        cast(self.ex, self.p0, shock, targets=(self.p1,))
        tags = [e[1] for e in self.ex.events]
        self.assertLess(tags.index("GAIN_LIFE"), tags.index("DAMAGE"))
        self.assertEqual(self.world.players[self.p1].life, 18)  # spell still resolves


class TestEffectCast(StackCase):
    """The Verb.CAST atom (the finding: an EFFECT verb, cost-waiver idiom)."""

    def waiver(self):
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, ANY_ZONE)
        return OptionalEffect(
            Atom(
                verb=Verb.CAST,
                args=AtomArgs(pairs=(("source", sel), ("cost", Cost(())))),
            )
        )

    def full_cost(self):
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, ANY_ZONE)
        return OptionalEffect(
            Atom(verb=Verb.CAST, args=AtomArgs(pairs=(("source", sel),)))
        )

    def caster(self, name="Caster"):
        return self.world.add_card(card_id(name, "1", "1"), self.p0, ZONE_BATTLEFIELD)

    def test_cast_waiver_end_to_end(self):
        exiled = self.give(
            "ExileBurn",
            SpellKind.INSTANT,
            cost=Cost((CostManaGeneric(QConst(4)),)),  # expensive: waiver proves it
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
            zone=ZONE_EXILE,
        )
        self.ex.apply_effect(
            self.waiver(),
            source=self.caster(),
            controller=self.p0,
            bindings={"source": exiled},
            decisions=("fire",),
        )
        self.assertEqual(self.world.zone_of(exiled).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p0].life, 21)  # the effect ran
        self.assertEqual(self.world.players[self.p0].mana_pool, {})  # nothing paid

    def test_cast_pays_full_cost_without_the_waiver_role(self):
        exiled = self.give(
            "PaidBurn",
            SpellKind.INSTANT,
            cost=Cost((CostManaGeneric(QConst(2)),)),
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
            zone=ZONE_EXILE,
        )
        self.mana(self.p0, C=5)
        self.ex.apply_effect(
            self.full_cost(),
            source=self.caster("Caster2"),
            controller=self.p0,
            bindings={"source": exiled},
            decisions=("fire",),
        )
        self.assertEqual(self.world.players[self.p0].mana_pool.get("C"), 3)
        self.assertEqual(self.world.zone_of(exiled).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p0].life, 21)

    def test_cast_may_skip_consumes_only_the_decision(self):
        exiled = self.give("SkipMe", SpellKind.INSTANT, zone=ZONE_EXILE)
        self.ex.apply_effect(
            self.waiver(),
            source=self.caster("Caster3"),
            controller=self.p0,
            bindings={"source": exiled},
            decisions=("skip",),
        )
        self.assertEqual(self.world.zone_of(exiled).kind, ZONE_EXILE)  # untouched

    def test_cast_targets_through_the_direct_api(self):
        # the cast_card TARGETS parameter (CR 603.3): the direct API can
        # designate for an effect-cast spell; the ATOM side cannot.
        from MTG_bot.core.executor.stack import cast_card

        shock = self.give(
            "ExileShock",
            SpellKind.INSTANT,
            effect=atom(Verb.DEAL_DAMAGE, target=any_target(), amount=QConst(2)),
            zone=ZONE_EXILE,
        )
        cast_card(self.ex, self.p0, shock, cost_override=Cost(()), targets=(self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)
        self.assertEqual(self.world.zone_of(shock).kind, ZONE_GRAVEYARD)
        # off-population still validated:
        with self.assertRaises(ValueError):
            cast_card(
                self.ex,
                self.p0,
                self.give(
                    "Zapped",
                    SpellKind.INSTANT,
                    zone=ZONE_EXILE,
                    effect=atom(
                        Verb.DEAL_DAMAGE,
                        target=Selector(
                            QConst(1), SelectorMode.TARGET, CREATURE_F, BF_ANY
                        ),
                        amount=QConst(1),
                    ),
                ),
                cost_override=Cost(()),
                targets=(self.p1,),  # player, not creature
            )

    def test_cast_land_designation_raises(self):
        land_id = card_id("Wasteland", type_line="Land")
        land = self.world.add_card(land_id, self.p0, ZONE_EXILE)
        self.ex.attach_card(
            land, record_of([], name="Wasteland", oid=land_id.oracle_id)
        )
        with self.assertRaises(ValueError) as cm:
            self.ex.apply_effect(
                self.waiver(),
                source=self.caster("Caster4"),
                controller=self.p0,
                bindings={"source": land},
                decisions=("fire",),
            )
        self.assertIn("SpellAbility", str(cm.exception))


class TestPayVerb(StackCase):
    def pay_offer(self, cost_part):
        return OptionalEffect(
            Atom(verb=Verb.PAY, args=AtomArgs(pairs=(("cost", Cost((cost_part,))),)))
        )

    def test_offer_narrows_without_resources_pays_with(self):
        src = self.world.add_card(card_id("Urns", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        effect = self.pay_offer(CostManaColor("G", QConst(1)))
        self.assertEqual(
            optional_offer(self.ex, effect, source=src, controller=self.p0), ("skip",)
        )
        self.mana(self.p0, G=1)
        self.assertEqual(
            optional_offer(self.ex, effect, source=src, controller=self.p0),
            ("fire", "skip"),
        )
        self.ex.apply_effect(
            effect, source=src, controller=self.p0, decisions=("fire",)
        )
        self.assertNotIn("G", self.world.players[self.p0].mana_pool)  # paid

    def test_fire_on_unpayable_raises(self):
        """AMENDED 14b (B-5 query/runtime identity): the runtime now ASKS
        with the query-narrowed offer vocab, so an unpayable 'fire' is
        rejected AT THE DECISION CHANNEL ('fire' is not in the vocabulary
        at all) instead of reaching _v_pay. Same loud ValueError, one
        station earlier — the illegal decision can no longer be made."""
        src = self.world.add_card(card_id("Urns2", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        with self.assertRaises(ValueError) as cm:
            self.ex.apply_effect(
                self.pay_offer(CostManaColor("G", QConst(2))),
                source=src,
                controller=self.p0,
                decisions=("fire",),
            )
        self.assertIn("not in", str(cm.exception))
        self.assertIn("skip", str(cm.exception))


class TestChooseVerb(StackCase):
    def duress(self, name="Duress"):
        pool = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_OPP)
        result = Selector(
            QConst(1), SelectorMode.CHOOSE, UNIV, ANY_ZONE, referent="result"
        )
        effect = Seq(
            (
                atom(Verb.CHOOSE, target=pool, count=QConst(1)),
                atom(
                    Verb.DISCARD, controller=ControllerRef.TARGET_PLAYER, cards=result
                ),
            )
        )
        return self.give(name, SpellKind.SORCERY, type_line="Sorcery", effect=effect)

    def test_choose_picks_and_discards(self):
        spell = self.duress()
        h1 = self.world.add_card(card_id("HandOne", "1", "1"), self.p1, ZONE_HAND)
        h2 = self.world.add_card(card_id("HandTwo", "1", "1"), self.p1, ZONE_HAND)
        first, second = sorted([h1, h2])
        probe = Atom(
            verb=Verb.CHOOSE,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_OPP),
                    ),
                )
            ),
        )
        rows = verb_choose_options(self.ex, probe, source=spell, controller=self.p0)
        self.assertEqual(rows, ((first,), (second,), ()))  # ORDER contract
        cast(self.ex, self.p0, spell, targets=(self.p1,), decisions=("1",))
        self.assertEqual(self.world.zone_of(second).kind, ZONE_GRAVEYARD)  # pick "1"
        self.assertEqual(self.world.zone_of(first).kind, ZONE_HAND)  # left alone

    def test_empty_pool_consumes_no_decision(self):
        spell = self.duress("Duress2")
        cast(self.ex, self.p0, spell, targets=(self.p1,), decisions=())
        self.assertTrue(any(e[1] == "CHOOSE" for e in self.ex.events))

    def test_kitesail_shape_exiles_the_pick(self):
        pool = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_OPP)
        result = Selector(
            QConst(1), SelectorMode.CHOOSE, UNIV, ANY_ZONE, referent="result"
        )
        effect = Seq(
            (
                atom(Verb.CHOOSE, target=pool, count=QConst(1)),
                atom(Verb.EXILE, target=result),
            )
        )
        spell = self.give(
            "Freeboot",
            SpellKind.CREATURE,
            type_line="Creature",
            types=("Creature",),
            power="2",
            toughness="1",
            effect=effect,
        )
        loot = self.world.add_card(card_id("Loot", "1", "1"), self.p1, ZONE_HAND)
        cast(self.ex, self.p0, spell, decisions=("0",))
        self.assertEqual(self.world.zone_of(loot).kind, ZONE_EXILE)


class TestChooseName(StackCase):
    def halo(self):
        halo = self.world.add_card(card_id("Halo", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        rec = record_of(
            [ActivatedAbility(cost=Cost((CostTap(),)), effect=atom(Verb.CHOOSE_NAME))],
            name="Halo",
            oid=self.world.cards[halo].identity.oracle_id,
        )
        self.ex.attach_card(halo, rec)
        return halo

    def test_name_recorded_and_predicate_reads_it(self):
        from MTG_bot.core.executor.quantity import eval_filter

        halo = self.halo()
        chosen = self.world.add_card(
            card_id("Narnam", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex.apply_effect(
            atom(Verb.CHOOSE_NAME),
            source=halo,
            controller=self.p0,
            decisions=("Narnam",),
        )
        self.assertEqual(self.ex.name_choices[halo], "Narnam")
        ctx = ctx_for(self.ex, source=halo, controller=self.p0)
        self.assertTrue(eval_filter(FAtom(FAtomPred.NAME_CHOSEN), chosen, ctx))
        other = self.world.add_card(
            card_id("Other", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.assertFalse(eval_filter(FAtom(FAtomPred.NAME_CHOSEN), other, ctx))

    def test_predicate_without_a_record_raises(self):
        halo = self.halo()
        self.world.add_card(card_id("Victim", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        with self.assertRaises(NotImplementedError) as cm:
            self.ex.execute(
                atom(
                    Verb.DESTROY,
                    target=Selector(
                        QConst(1),
                        SelectorMode.ALL,
                        FAtom(FAtomPred.NAME_CHOSEN),
                        BF_ANY,
                    ),
                ),
                source=halo,
                controller=self.p0,
            )
        self.assertIn("NAME_CHOSEN", str(cm.exception))


class TestManaPolicy(StackCase):
    """The R9-3 consumers: Vodalian Arcanist's THIS_MANA, Orrery's ALL_YOURS."""

    def vodalian(self):
        pol = StaticAbility(
            effect=Atom(
                verb=Verb.MANA_POLICY,
                args=AtomArgs(
                    pairs=(("scope", "THIS_MANA"), ("filter", INSTANT_OR_SORCERY))
                ),
            )
        )
        tap_add = ActivatedAbility(
            cost=Cost((CostTap(),)),
            effect=atom(
                Verb.ADD_MANA, controller=ControllerRef.YOU, amount=QConst(2), color="C"
            ),
        )
        handle = self.world.add_card(
            card_id("Vodalian", "0", "1", type_line="Creature"),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.ex.attach_card(
            handle,
            record_of(
                [pol, tap_add],
                name="Vodalian",
                oid=self.world.cards[handle].identity.oracle_id,
            ),
        )
        return handle

    def orrery(self):
        pol = StaticAbility(
            effect=Atom(
                verb=Verb.MANA_POLICY, args=AtomArgs(pairs=(("scope", "ALL_YOURS"),))
            )
        )
        handle = self.world.add_card(
            card_id("Orrery", type_line="Artifact"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.attach_card(
            handle,
            record_of(
                [pol], name="Orrery", oid=self.world.cards[handle].identity.oracle_id
            ),
        )
        return handle

    def test_this_mana_buys_instants_not_creatures(self):
        vod = self.vodalian()
        activate(self.ex, vod, 1, seat=self.p0)  # {T}: add {C}{C}
        self.assertEqual(self.world.players[self.p0].mana_pool.get("C"), 2)
        self.assertTrue(self.ex.mana_ledger.has(self.p0))
        critter = self.give(
            "Bear",
            SpellKind.CREATURE,
            cost=Cost((CostManaGeneric(QConst(2)),)),
            type_line="Creature",
            types=("Creature",),
            power="2",
            toughness="2",
        )
        reason = spell_castable(self.ex, self.p0, critter)[0]
        assert reason is not None
        self.assertIn("cost:mana_generic:0<2", reason)  # tagged pair NOT usable
        instant = self.give(
            "Quick",
            SpellKind.INSTANT,
            cost=Cost((CostManaGeneric(QConst(2)),)),
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
        )
        self.assertIsNone(spell_castable(self.ex, self.p0, instant)[0])
        cast(self.ex, self.p0, instant)  # SAME mana buys the instant
        self.assertNotIn("C", self.world.players[self.p0].mana_pool)

    def test_restriction_survives_the_source(self):
        vod = self.vodalian()
        activate(self.ex, vod, 1, seat=self.p0)
        self.ex.binder.detach(vod)  # the Arcanist LEAVES (lifecycle half);
        # the restriction rides the MANA, not the permanent: it persists
        critter = self.give(
            "Bear2",
            SpellKind.CREATURE,
            cost=Cost((CostManaGeneric(QConst(2)),)),
            type_line="Creature",
            types=("Creature",),
            power="2",
            toughness="2",
        )
        reason = spell_castable(self.ex, self.p0, critter)[0]
        assert reason is not None
        self.assertIn("cost:mana_generic:0<2", reason)

    def test_all_yours_spends_any_colour(self):
        spell = self.give(
            "BlueOnly",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("U", QConst(2)),)),
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
        )
        self.mana(self.p0, R=2)
        self.assertEqual(spell_castable(self.ex, self.p0, spell)[0], "cost:mana:U:0<2")
        orrery = self.orrery()
        self.assertTrue(self.ex.mana_permission(self.p0))
        self.assertIsNone(spell_castable(self.ex, self.p0, spell)[0])
        cast(self.ex, self.p0, spell)
        self.assertNotIn("R", self.world.players[self.p0].mana_pool)  # paid with red
        self.ex.binder.detach(orrery)  # battlefield exit expires the layer
        self.assertFalse(self.ex.mana_permission(self.p0))  # live-layer read

    def test_dispatched_policy_lives_and_dies_with_its_anchor(self):
        anchor = self.world.add_card(
            card_id("Scepter", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.apply_effect(
            Atom(verb=Verb.MANA_POLICY, args=AtomArgs(pairs=(("scope", "ALL_YOURS"),))),
            source=anchor,
            controller=self.p0,
        )
        self.assertTrue(self.ex.mana_permission(self.p0))
        self.ex.binder.detach(anchor)  # battlefield exit expires the layer
        self.assertFalse(self.ex.mana_permission(self.p0))

    def test_activation_cannot_demonstrate_tagged_mana_use(self):
        vod = self.vodalian()
        activate(self.ex, vod, 1, seat=self.p0)  # tagged {C}{C}
        urn = self.world.add_card(
            card_id("Urn2", type_line="Artifact"), self.p0, ZONE_BATTLEFIELD
        )
        rec = record_of(
            [
                ActivatedAbility(
                    cost=Cost((CostManaGeneric(QConst(1)),)),
                    effect=atom(
                        Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)
                    ),
                )
            ],
            name="Urn2",
            oid=self.world.cards[urn].identity.oracle_id,
        )
        self.ex.attach_card(urn, rec)
        reason = ability_playable(self.world, self.ex, urn, 0, seat=self.p0)
        assert reason is not None  # the tagged mana cannot buy an activation
        self.assertIn("cost:mana_generic", reason)


class TestJournalFingerprintRaises(StackCase):
    def test_stack_frame_fold_changes_the_fingerprint(self):
        spell = self.shock()
        base = self.ex.state_fingerprint()
        self.ex.stack.push(self.dummy_frame(spell, x=3))
        fp_with_frame = self.ex.state_fingerprint()
        self.assertNotEqual(base, fp_with_frame)
        # the SAME frame with a different locked X differs too (frame DATA
        # is replayed state, not just its existence)
        self.ex.stack.frames[0].x_value = 4
        self.assertNotEqual(fp_with_frame, self.ex.state_fingerprint())
        self.ex.stack.pop()
        self.assertEqual(base, self.ex.state_fingerprint())  # popped clean
        # (the WORLD fingerprint never sees stack frames at all —
        # ZONE_STACK is outside PLAYER_ZONES; this fold is the only
        # witness, which is exactly the completeness hole /11 risk-1 named)

    def test_park_moves_and_zone_lookup_works(self):
        spell = self.shock()
        park(self.ex, self.p0, spell)
        self.assertEqual(self.world.zone_of(spell).kind, ZONE_STACK)
        self.assertEqual(self.world.controller_of(spell), self.p0)

    def test_lose_game_emits_a_journal_row(self):
        self.ex.execute(
            atom(Verb.LOSE_GAME),
            source=self.p0,
            controller=self.p0,
        )
        evs = self.journal_events("GAME_LOST")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].subject, self.p0)
        self.assertEqual(evs[0].data, ("LOSE_GAME",))

    def test_counter_spell_still_raises(self):
        # the mission pin: v1 has no response window, so a counter can
        # never legally resolve — the loud flag STAYS (no silent no-op)
        with self.assertRaises(NotImplementedError) as cm:
            self.ex.execute(
                atom(Verb.COUNTER_SPELL, target=any_target()),
                source=self.p0,
                controller=self.p0,
            )
        self.assertIn("COUNTER_SPELL", str(cm.exception))

    def test_replay_identity_with_the_new_folds(self):
        """Two executors, one scripted op sequence: byte-identical
        fingerprints INCLUDING the stack/land/mana/name-choice folds."""
        runs = []
        for _ in range(2):  # identical script, identical data: must match
            world = GameWorld(num_players=2, start_life=20, master_seed=11)
            p0 = world.player_order[0]
            ex = Executor(world)
            ex.begin_turn(p0)
            vod = record_of(
                [
                    StaticAbility(
                        effect=Atom(
                            verb=Verb.MANA_POLICY,
                            args=AtomArgs(
                                pairs=(
                                    ("scope", "THIS_MANA"),
                                    ("filter", INSTANT_OR_SORCERY),
                                )
                            ),
                        )
                    ),
                    ActivatedAbility(
                        cost=Cost((CostTap(),)),
                        effect=atom(
                            Verb.ADD_MANA,
                            controller=ControllerRef.YOU,
                            amount=QConst(1),
                            color="C",
                        ),
                    ),
                ],
                name="V",
                oid="0f00aaaa-1111-2222-3333-444444444444",
            )
            v = world.add_card(
                CardIdentity(
                    oracle_id=vod.oracle_id,
                    name="V",
                    type_line="Creature",
                    power="0",
                    toughness="1",
                    cmc=0,
                ),
                p0,
                ZONE_BATTLEFIELD,
            )
            ex.attach_card(v, vod)
            inst_rec = spell_rec(
                "I",
                SpellKind.INSTANT,
                cost=Cost((CostManaGeneric(QConst(1)),)),
                effect=atom(
                    Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)
                ),
                my_oid="0f00bbbb-1111-2222-3333-444444444444",
            )
            i = world.add_card(
                CardIdentity(
                    oracle_id=inst_rec.oracle_id, name="I", type_line="Instant", cmc=1
                ),
                p0,
                ZONE_HAND,
            )
            ex.attach_card(i, inst_rec)
            land = world.add_card(
                CardIdentity(
                    oracle_id="0f00cccc-1111-2222-3333-444444444444",
                    name="L",
                    type_line="Land",
                    cmc=0,
                ),
                p0,
                ZONE_HAND,
            )
            activate(ex, v, 1, seat=p0)  # tagged mana + ledger segment
            cast(ex, p0, i)  # full cast pipeline (park, frame, event, put)
            play_land(ex, p0, land)  # land ledger
            ex.end_turn()
            runs.append((world.fingerprint(), ex.state_fingerprint()))
        self.assertEqual(runs[0][0], runs[1][0])  # world replay
        self.assertEqual(runs[0][1], runs[1][1])  # executor folds replay


if __name__ == "__main__":
    unittest.main()
