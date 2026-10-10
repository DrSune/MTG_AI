"""Round-13c pins: the four permission verbs (plan /13 arc 2). Covers
ADD_LAND_PLAY (Azusa: the optional gate, the cumulative repeat-activation
reading, the controller anchor), GRANT_TYPE (the Dub/Demonic static shape
over the executor attachment table, the Riddleform runtime sibling with
its Eot expiry, the type overlay as the single TYPE_EQ oracle),
GRANT_ACTIVATION (Teferi's static via the OptionalEffect-unwrapping
``_new_static`` path AND the runtime handler; cross-seat IR-faithful
scope; every non-timing gate untouched; the validator raises), and
GET_EMBLEM (the (owner, oid) idempotence gate, owner-anchored statics and
END_TURN-trigger drain, the orphan raise, and the replayed-state
fingerprint). NAME_CONTAINS / IS_ATTACHED_TO_SOURCE get direct unit pins.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    ActivationWindow,
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    Cost,
    CostTap,
    DurationEot,
    DurationPermanent,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    Phase,
    QConst,
    Selector,
    SelectorMode,
    StaticAbility,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import ability_playable, activate, ctx_for
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.executor.stack import land_playable, play_land
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld

_ORACLE = iter(range(1, 1 << 16))


def card_id(name, power=None, toughness=None, type_line="Creature"):
    return CardIdentity(
        oracle_id=f"00000000-0000-0000-0001-{next(_ORACLE):012d}",
        name=name,
        power=power,
        toughness=toughness,
        type_line=type_line,
        cmc=2,
    )


def atom(verb, **roles):
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
BF_YOU = Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)
UNIV = FAnd(())
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
IS_ATTACHED = FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE)
PW_EQ = FAtom(FAtomPred.TYPE_EQ, string_value="Planeswalker")
TEFERI_NAMED = FAtom(FAtomPred.NAME_CONTAINS, string_value="Teferi")
TEFERI_GATE = FAnd((PW_EQ, TEFERI_NAMED))


def target_sel(filter_: object = UNIV) -> Selector:
    return Selector(QConst(1), SelectorMode.TARGET, filter_, BF_ANY)  # pyright: ignore[reportArgumentType]


def scope_you() -> Selector:
    return Selector(QConst(99), SelectorMode.ALL, CREATURE, BF_YOU)  # pyright: ignore[reportArgumentType]


def rec(name, oid, abilities=(), type_line="Creature", emblem=None) -> CardRecord:
    creature = "Creature" in type_line
    walker = "Planeswalker" in type_line
    return CardRecord(
        oracle_id=oid,
        name=name,
        type_line=type_line,
        types=tuple(type_line.replace("—", " ").split()),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=2,
        power=QConst(2) if creature else None,
        toughness=QConst(2) if creature else None,
        loyalty=3 if walker else None,  # CardRecord: int, PW-exactly
        keywords=(),
        abilities=tuple(abilities),
        is_token=type_line == "Emblem",  # CardRecord: emblems are token-shaped
        emblem=emblem,
    )


def gain(n) -> Atom:
    return atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(n))


class PermCase(unittest.TestCase):
    def setUp(self):
        self.world = GameWorld(num_players=2, start_life=20, master_seed=21)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)

    def settle(self):
        self.ex.layers.recompute()

    def place(self, name, seat, type_line="Creature", abilities=(), emblem=None):
        cid = card_id(name, "2", "2", type_line)
        handle = self.world.add_card(cid, seat, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            handle, rec(name, cid.oracle_id, abilities, type_line, emblem)
        )
        return handle

    def life(self, player):
        return self.world.players[player].life

    def overlay(self, handle):
        return self.ex.layers.type_overlay(handle)


# ------------------------------------------------------------- ADD_LAND_PLAY


class TestLandPlayBonus(PermCase):
    def setUp(self):
        super().setUp()
        self.azusa = self.place(
            "Azusa",
            self.p0,
            abilities=[
                ActivatedAbility(
                    cost=Cost(parts=()),
                    effect=OptionalEffect(
                        atom(
                            Verb.ADD_LAND_PLAY,
                            count=QConst(2),
                            duration=DurationPermanent(),
                        )
                    ),
                )
            ],
        )
        self.hands = []
        for _ in range(5):
            cid = card_id("Plains", type_line="Land")
            land = self.world.add_card(cid, self.p0, ZONE_HAND)
            self.ex.attach_card(land, rec("Plains", cid.oracle_id, (), "Land"))
            self.hands.append(land)
        self.ex.begin_turn(self.p0)

    def blocked(self, seat, handle):
        return land_playable(self.ex, seat, handle) or ""

    def test_baseline_allowance_is_one_then_activation_widens_it(self):
        self.assertIsNone(land_playable(self.ex, self.p0, self.hands[0]))
        play_land(self.ex, self.p0, self.hands[0])
        self.assertIn("land:used_this_turn", self.blocked(self.p0, self.hands[1]))
        activate(self.ex, self.azusa, 0, seat=self.p0, decisions=("fire",))
        self.assertEqual(self.ex.layers.land_play_bonus(self.p0), 2)
        play_land(self.ex, self.p0, self.hands[1])
        self.assertIsNone(land_playable(self.ex, self.p0, self.hands[2]))
        play_land(self.ex, self.p0, self.hands[2])
        self.assertIn(  # allowance 1+2 spent
            "land:used_this_turn", self.blocked(self.p0, self.hands[3])
        )

    def test_repeat_activations_stack_cumulatively(self):
        # honest CR reading of a repeatable zero-cost activation (documented
        # in the handler): each activation grants +2 MORE lands.
        play_land(self.ex, self.p0, self.hands[0])
        activate(self.ex, self.azusa, 0, seat=self.p0, decisions=("fire",))
        play_land(self.ex, self.p0, self.hands[1])
        play_land(self.ex, self.p0, self.hands[2])
        self.assertIn("land:used_this_turn", self.blocked(self.p0, self.hands[3]))
        activate(self.ex, self.azusa, 0, seat=self.p0, decisions=("fire",))
        self.assertEqual(self.ex.layers.land_play_bonus(self.p0), 4)
        self.assertIsNone(land_playable(self.ex, self.p0, self.hands[3]))

    def test_skip_decision_grants_nothing(self):
        activate(self.ex, self.azusa, 0, seat=self.p0, decisions=("skip",))
        self.assertEqual(self.ex.layers.land_play_bonus(self.p0), 0)
        play_land(self.ex, self.p0, self.hands[0])
        self.assertIn("land:used_this_turn", self.blocked(self.p0, self.hands[1]))

    def test_bonus_is_anchored_to_its_controller(self):
        activate(self.ex, self.azusa, 0, seat=self.p0, decisions=("fire",))
        self.assertEqual(self.ex.layers.land_play_bonus(self.p0), 2)
        self.assertEqual(self.ex.layers.land_play_bonus(self.p1), 0)


# ------------------------------------------------------------------ GRANT_TYPE


class TestTypeOverlay(PermCase):
    def setUp(self):
        super().setUp()
        self.dub = self.place(
            "Dub",
            self.p0,
            type_line="Artifact — Equipment",
            abilities=[
                StaticAbility(
                    effect=atom(
                        Verb.GRANT_TYPE,
                        target=Selector(
                            QConst(99), SelectorMode.ALL, IS_ATTACHED, BF_ANY
                        ),  # pyright: ignore[reportArgumentType]
                        types=("Knight",),
                    )
                )
            ],
        )
        self.host = self.place("Squire", self.p0)
        self.other = self.place("Recruit", self.p0)
        self.knight = FAtom(FAtomPred.TYPE_EQ, string_value="Knight")

    def ctx(self):
        return ctx_for(self.ex, source=self.dub, controller=self.p0)

    def test_attachment_drives_the_static_overlay(self):
        self.assertEqual(self.overlay(self.host), ())
        self.ex.attach_aura(self.dub, self.host)
        self.settle()
        self.assertEqual(self.overlay(self.host), ("Knight",))
        self.assertEqual(self.overlay(self.other), ())
        ctx = self.ctx()
        self.assertTrue(eval_filter(self.knight, self.host, ctx))
        self.assertFalse(eval_filter(self.knight, self.other, ctx))
        # overlay UNIONS: the printed types survive ("in addition to")
        self.assertTrue(eval_filter(CREATURE, self.host, ctx))

    def test_detach_purges_the_edge_and_the_overlay(self):
        self.ex.attach_aura(self.dub, self.host)
        self.settle()
        self.assertEqual(self.overlay(self.host), ("Knight",))
        self.ex.binder.detach(self.dub)  # the purge inside _register/detach
        self.ex.attachments.pop(self.dub, None)
        self.settle()
        self.assertEqual(self.overlay(self.host), ())

    def test_runtime_grant_type_expires_at_end_of_turn(self):
        riddle = self.place("Riddleform", self.p0, type_line="Enchantment")
        self.ex.apply_effect(
            atom(
                Verb.GRANT_TYPE,
                target=target_sel(),
                types=("Sphinx",),
                duration=DurationEot(),
            ),
            source=riddle,
            controller=self.p0,
            bindings={"target": self.host},
        )
        self.settle()
        self.assertEqual(self.overlay(self.host), ("Sphinx",))
        self.ex.begin_turn(self.p0)
        self.ex.end_turn()
        self.settle()
        self.assertEqual(self.overlay(self.host), ())

    def test_permanent_runtime_grant_outlives_its_source(self):
        # MTG-correct split: a RESOLVED effect ("target creature is a Demon")
        # persists after its source leaves the battlefield; a STATIC grant
        # (the Dub shape above) dies with the permanent via binder.detach.
        totem = self.place("Totem", self.p0, type_line="Artifact")
        self.ex.apply_effect(
            atom(
                Verb.GRANT_TYPE,
                target=target_sel(),
                types=("Demon",),
                duration=DurationPermanent(),
            ),
            source=totem,
            controller=self.p0,
            bindings={"target": self.host},
        )
        self.settle()
        self.assertEqual(self.overlay(self.host), ("Demon",))
        self.world.move_to_zone(totem, self.p0, "graveyard")
        self.settle()
        self.assertEqual(self.overlay(self.host), ("Demon",))  # effect, not aura

    def test_type_eq_false_for_non_world_handles(self):
        ctx = self.ctx()
        self.assertFalse(eval_filter(self.knight, self.dub, ctx))  # before bind
        self.ex.attach_aura(self.dub, self.host)
        self.settle()
        emblem = type(self.dub)("emblem", 999)
        self.assertFalse(eval_filter(self.knight, emblem, ctx))

    def test_attach_aura_validation(self):
        with self.assertRaises(ValueError):
            self.ex.attach_aura(self.dub, self.dub)
        ghost = type(self.dub)("card", 999_999)
        with self.assertRaises(ValueError):
            self.ex.attach_aura(self.dub, ghost)
        with self.assertRaises(ValueError):
            self.ex.attach_aura(ghost, self.host)
        self.ex.attach_aura(self.dub, self.host)  # the happy path writes the table
        self.assertEqual(self.ex.attachments[self.dub], self.host)


# ----------------------------------------------------------- GRANT_ACTIVATION


class TestActivationWindow(PermCase):
    def setUp(self):
        super().setUp()
        # Teferi's static is NOT live in setUp — the blocking tests query the
        # pre-grant world; grant_static() flips the permission on.
        fc = card_id("Teferi, Who Outcast Oversight", type_line="Planeswalker")
        self.teferi = self.world.add_card(fc, self.p0, ZONE_BATTLEFIELD)
        self._teferi_oid = fc.oracle_id
        self.ex.attach_card(
            self.teferi,
            rec("Teferi, Who Outcast Oversight", fc.oracle_id, [], "Planeswalker"),
        )
        self.sorcery_abil = ActivatedAbility(
            cost=Cost(parts=()), effect=gain(1), timing=ActivationWindow.SORCERY
        )
        tcid = card_id("Teferi, Time Raveler", type_line="Planeswalker")
        self.p1_teferi = self.world.add_card(tcid, self.p1, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            self.p1_teferi,
            rec(
                "Teferi, Time Raveler",
                tcid.oracle_id,
                [self.sorcery_abil],
                "Planeswalker",
            ),
        )
        jcid = card_id("Jaya", type_line="Planeswalker")
        self.p1_jaya = self.world.add_card(jcid, self.p1, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            self.p1_jaya,
            rec("Jaya", jcid.oracle_id, [self.sorcery_abil], "Planeswalker"),
        )
        bcid = card_id("Grunt", "2", "2")
        self.beast = self.world.add_card(bcid, self.p1, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            self.beast, rec("Grunt", bcid.oracle_id, [self.sorcery_abil])
        )
        self.ex.begin_turn(self.p0)

    def query(self, handle, seat, stack_empty):
        return (
            ability_playable(
                self.world, self.ex, handle, 0, seat=seat, stack_empty=stack_empty
            )
            or ""
        )

    def grant_static(self):
        # Flip Teferi's compiled static on: the OptionalEffect-wrapped
        # GRANT_ACTIVATION that ``_new_static`` unwraps. Re-attaching the
        # same-oid record is the binder's idempotent refresh path.
        self.ex.attach_card(
            self.teferi,
            rec(
                "Teferi, Who Outcast Oversight",
                self._teferi_oid,
                [
                    StaticAbility(
                        effect=OptionalEffect(
                            atom(
                                Verb.GRANT_ACTIVATION,
                                filter=TEFERI_GATE,
                                window=ActivationWindow.INSTANT,
                            )
                        )
                    )
                ],
                "Planeswalker",
            ),
        )
        self.settle()

    def test_sorcery_gate_blocks_before_the_grant(self):
        self.assertTrue(
            self.query(self.p1_teferi, self.p1, True).startswith("window:sorcery")
        )
        self.assertTrue(
            self.query(self.p1_teferi, self.p1, False).startswith("window:sorcery")
        )

    def test_grant_relaxes_matching_permanents_across_seats(self):
        # Teferi's compiled filter is shape-only (TYPE_EQ + NAME_CONTAINS):
        # the grant is IR-faithfully GLOBAL — the relaxation is timing, and
        # a matching permanent anywhere may run its sorcery-timed activation
        # at instant speed. Non-matching permanents keep every gate.
        self.grant_static()  # the static's activation_grant layer is live
        self.assertEqual(self.query(self.p1_teferi, self.p1, False), "")
        self.assertEqual(self.query(self.p1_teferi, self.p1, True), "")
        self.assertTrue(
            self.query(self.p1_jaya, self.p1, False).startswith("window:sorcery")
        )
        self.assertTrue(
            self.query(self.beast, self.p1, False).startswith("window:sorcery")
        )

    def test_non_timing_gates_untouched(self):
        self.grant_static()
        tcid = card_id("Teferi, Payboard", type_line="Planeswalker")
        tap_pw = self.world.add_card(tcid, self.p1, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            tap_pw,
            rec(
                "Teferi, Payboard",
                tcid.oracle_id,
                [
                    ActivatedAbility(
                        cost=Cost(parts=(CostTap(),)),
                        effect=gain(1),
                        timing=ActivationWindow.SORCERY,
                    )
                ],
                "Planeswalker",
            ),
        )
        self.world.cards[tap_pw].tapped = True
        self.settle()
        reason = self.query(tap_pw, self.p1, False)
        self.assertNotEqual(reason, "")
        self.assertFalse(reason.startswith("window"), reason)  # now a COST reason

    def test_runtime_handler_path(self):
        # the dispatched sibling of the static path: an inline atom grant
        tcid = card_id("Teferi, Temporal Trick", type_line="Planeswalker")
        pw = self.world.add_card(tcid, self.p1, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            pw,
            rec(
                "Teferi, Temporal Trick",
                tcid.oracle_id,
                [self.sorcery_abil],
                "Planeswalker",
            ),
        )
        self.assertNotEqual(self.query(pw, self.p1, False), "")
        events = self.ex.execute(
            atom(
                Verb.GRANT_ACTIVATION,
                filter=TEFERI_GATE,
                window=ActivationWindow.INSTANT,
            ),
            source=self.teferi,
            controller=self.p0,
        )
        self.assertTrue(any(row[1] == "GRANT_ACTIVATION" for row in events))
        self.assertEqual(self.query(pw, self.p1, False), "")

    def test_runtime_handler_validators(self):
        with self.assertRaises(NotImplementedError):
            self.ex.execute(
                atom(
                    Verb.GRANT_ACTIVATION,
                    filter=TEFERI_GATE,
                    window=ActivationWindow.SORCERY,
                ),
                source=self.teferi,
                controller=self.p0,
            )
        with self.assertRaises(ValueError):
            self.ex.execute(
                atom(Verb.GRANT_ACTIVATION, window=ActivationWindow.INSTANT),
                source=self.teferi,
                controller=self.p0,
            )

    def test_name_contains_is_case_sensitive_and_world_guarded(self):
        ctx = ctx_for(self.ex, source=self.teferi, controller=self.p0)
        self.assertTrue(eval_filter(TEFERI_NAMED, self.p1_teferi, ctx))
        self.assertFalse(
            eval_filter(
                FAtom(FAtomPred.NAME_CONTAINS, string_value="teferi"),
                self.p1_teferi,
                ctx,
            )
        )
        ghost = type(self.p1_teferi)("card", 999_999)
        self.assertFalse(eval_filter(TEFERI_NAMED, ghost, ctx))


# ------------------------------------------------------------------ GET_EMBLEM


EMBLEM_OID = "00000000-0000-0000-0002-000000000e01"


def garruk_emblem():
    return rec(
        "Garruk's emblem",
        EMBLEM_OID,
        [
            TriggeredAbility(
                TurnPhaseEvent(Phase.END_TURN, actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)), None, gain(2)
            )
        ],
        type_line="Emblem",
    )


class TestEmblems(PermCase):
    def source_card(self, emblem):
        return self.place(
            "Garruk, Unleashed",
            self.p0,
            type_line="Planeswalker",
            abilities=[],
            emblem=emblem,
        )

    def test_get_emblem_binds_owner_anchored_trigger(self):
        pw = self.source_card(garruk_emblem())
        self.ex.begin_turn(self.p0)
        events = self.ex.execute(atom(Verb.GET_EMBLEM), source=pw, controller=self.p0)
        self.assertTrue(any(row[1] == "GET_EMBLEM" for row in events))
        self.assertEqual(len(self.ex.emblems), 1)
        emblem_handle = next(iter(self.ex.emblems.values()))
        self.assertNotIn(emblem_handle, self.world.cards)  # never a world card
        self.assertEqual(self.ex.binder.emblem_owner[emblem_handle], self.p0)
        self.ex.end_turn()
        self.assertEqual(self.life(self.p0), 22)  # END_TURN trigger for the OWNER
        self.assertEqual(self.life(self.p1), 20)

    def test_duplicate_emblem_is_idempotent(self):
        pw = self.source_card(garruk_emblem())
        first = self.ex.execute(atom(Verb.GET_EMBLEM), source=pw, controller=self.p0)
        second = self.ex.execute(atom(Verb.GET_EMBLEM), source=pw, controller=self.p0)
        self.assertFalse(any(row[-1] == "duplicate" for row in first))
        self.assertTrue(any(row[-1] == "duplicate" for row in second))
        self.assertEqual(len(self.ex.emblems), 1)
        handle = next(iter(self.ex.emblems.values()))
        bound = sum(1 for (h, _i) in self.ex.binder.attached if h == handle)
        self.assertEqual(bound, 1)  # ONE trigger binding, not two
        self.ex.begin_turn(self.p0)
        self.ex.end_turn()
        self.assertEqual(self.life(self.p0), 22)  # NOT 24 — one emblem, one trigger

    def test_emblem_static_anchors_to_owner(self):
        emblem = rec(
            "Liliana's emblem",
            "00000000-0000-0000-0002-000000000e02",
            [
                StaticAbility(
                    effect=atom(Verb.GRANT_TYPE, target=scope_you(), types=("Demon",))
                )
            ],
            type_line="Emblem",
        )
        pw = self.source_card(emblem)
        self.place("Ally", self.p0)
        self.place("Foe", self.p1)
        self.ex.execute(atom(Verb.GET_EMBLEM), source=pw, controller=self.p0)
        self.settle()
        overlays = {
            self.world.cards[h].identity.name: self.ex.layers.type_overlay(h)
            for h in self.world.cards
            if self.world.zone_of(h).kind == "battlefield"
        }
        self.assertEqual(overlays["Ally"], ("Demon",))  # "creatures you control"
        self.assertEqual(overlays["Foe"], ())

    def test_orphan_and_unbound_sources_raise(self):
        bare = self.place("Amnesia", self.p0, type_line="Planeswalker")
        with self.assertRaises(ValueError):
            self.ex.execute(atom(Verb.GET_EMBLEM), source=bare, controller=self.p0)
        ghost = type(bare)("card", 999_998)
        with self.assertRaises(ValueError):
            self.ex.execute(atom(Verb.GET_EMBLEM), source=ghost, controller=self.p0)

    def test_get_emblem_rejects_roles(self):
        pw = self.source_card(garruk_emblem())
        with self.assertRaises(ValueError):
            self.ex.execute(
                atom(Verb.GET_EMBLEM, target=target_sel()),
                source=pw,
                controller=self.p0,
            )

    def test_binder_dump_has_emblems_row(self):
        pw = self.source_card(garruk_emblem())
        self.ex.execute(atom(Verb.GET_EMBLEM), source=pw, controller=self.p0)
        rows = {row[0] for row in self.ex.binder.dump()}
        self.assertIn("emblems", rows)

    def test_emblem_ops_replay_to_equal_fingerprints(self):
        # NOTE: card_id() draws from a MODULE-GLOBAL oracle iterator, so a
        # literal second script() run would build DIFFERENT identities.
        # The replay contract is same-world-same-ops, hence the fixed oids.
        def fixed(oid, name, type_line="Creature"):
            return CardIdentity(
                oracle_id=oid,
                name=name,
                power="2",
                toughness="2",
                type_line=type_line,
                cmc=2,
            )

        def script(seed):
            world = GameWorld(num_players=2, start_life=20, master_seed=seed)
            ex = Executor(world)
            p0 = world.player_order[0]
            p1 = world.player_order[1]
            a = fixed("00000000-0000-0000-0009-000000000a01", "Azusa")
            azusa = world.add_card(a, p0, ZONE_BATTLEFIELD)
            ex.attach_card(
                azusa,
                rec(
                    "Azusa",
                    a.oracle_id,
                    [
                        ActivatedAbility(
                            cost=Cost(parts=()),
                            effect=OptionalEffect(
                                atom(
                                    Verb.ADD_LAND_PLAY,
                                    count=QConst(2),
                                    duration=DurationPermanent(),
                                )
                            ),
                        )
                    ],
                ),
            )
            g = fixed(
                "00000000-0000-0000-0009-000000000f01",
                "Garruk, Unleashed",
                "Planeswalker",
            )
            pw = world.add_card(g, p0, ZONE_BATTLEFIELD)
            ex.attach_card(
                pw,
                rec(
                    "Garruk, Unleashed",
                    g.oracle_id,
                    [],
                    "Planeswalker",
                    emblem=rec(
                        "Garruk's emblem",
                        EMBLEM_OID,
                        [
                            TriggeredAbility(
                                TurnPhaseEvent(Phase.END_TURN, actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
                                None,
                                gain(2),
                            )
                        ],
                        "Emblem",
                    ),
                ),
            )
            host_id = fixed("00000000-0000-0000-0009-000000000b01", "Boar")
            host = world.add_card(host_id, p1, ZONE_BATTLEFIELD)
            ex.attach_card(host, rec("Boar", host_id.oracle_id))
            ex.begin_turn(p0)
            ex.apply_effect(
                atom(
                    Verb.GRANT_TYPE,
                    target=target_sel(),
                    types=("Knight",),
                    duration=DurationEot(),
                ),
                source=pw,
                controller=p0,
                bindings={"target": host},
            )
            ex.execute(atom(Verb.GET_EMBLEM), source=pw, controller=p0)
            ex.execute(atom(Verb.GET_EMBLEM), source=pw, controller=p0)  # duplicate row
            ex.attach_aura(pw, host)  # oracle edge write (table is opaque in v1)
            ex.end_turn()
            return ex.state_fingerprint()

        self.assertEqual(script(11), script(11))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
