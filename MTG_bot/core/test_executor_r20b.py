"""Round-20b regression tests: the wave-3 trigger-feed / replacement / static
lane batch.

Each test pins one r20b root cause and the machinery that fixed it:

1. WAS_CAST_THIS_TURN (Containment Priest): the zone-agnostic twin of
   CAST_THIS_TURN_FROM — the condition reads the journalled 601.2h CAST
   rows, so a replacement with FNot(WAS_CAST) spares a cast creature and
   exiles a put-onto one; tokens are exempt via the event subject.
2. ZONE-CHANGE replacement consumption (verbs._v_move_zone): a matching
   replacement eats the battlefield move (no placement, ZONE_REPLACED
   audit row), and the consumed action runs through the pending drain
   with the moving card bound as ``event``.
3. TARGETING feed (events.emit_targeting + binding matcher): designation
   IS an event — one Handle-sorted row per designated object, emitted by
   the cast lane (601.2c, before payment), the folded activate, and the
   trigger-designation lane; a TargetingEvent(IS_SOURCE) trigger fires
   when its permanent is designated, the may-offer answers fire/skip,
   and another object's designation stays silent.
4. Player-subject verdicts (Hooded Blightfang): a DAMAGE row with a
   PLAYER subject is judged by _player_subject_verdict — card-shape
   predicates are simply false of a player, CONTROLLER_IS compares
   seats, and everything outside the shape set still raises 12c.
5. Disclosure statics (Conspicuous Snoop "Play with the top card
   revealed."): REVEAL/LOOK_AT payload statics install as lifetime
   "disclosure" layers (the verb lane's recorded no-op doctrine, with
   source-anchored liveness); the GAIN_LIFE-in-StaticAbility compiler
   mis-split (Rin and Seri) keeps its loud raise — flag-not-degrade.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    DurationPermanent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    OptionalEffect,
    QConst,
    ReplacementAbility,
    Selector,
    SelectorMode,
    SpellAbility,
    SpellKind,
    StaticAbility,
    TargetingEvent,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.binding import _player_subject_verdict
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    card_id,
    record_of,
    reset_oracle_ids,
)

UNIV = FAnd(())


def atom(verb, **roles) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def _bf_target() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        UNIV,
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )


def _event_exile() -> Atom:
    """The Containment Priest action shape straight from the golden:
    EXILE with the CHOOSE selector's ``referent="event"`` anaphora."""
    return atom(
        Verb.EXILE,
        target=Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            UNIV,
            Zone(ZoneKind.ANY, ControllerRef.ANY),
            referent="event",
        ),
    )


def _nontoken_enter_repl():
    """The compiled Containment Priest replacement, node-for-node:
    subject = nontoken creature, condition = FNot(WAS_CAST_THIS_TURN)."""
    return ReplacementAbility(
        event=ZoneChangeEvent(
            from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
            to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
            subject=FAnd(
                (
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FNot(inner=FAtom(pred=FAtomPred.IS_TOKEN)),
                )
            ),
        ),
        condition=FNot(
            inner=FAtom(pred=FAtomPred.WAS_CAST_THIS_TURN, who=ControllerRef.ANY)
        ),
        action=_event_exile(),
    )


class R20bCase(unittest.TestCase):
    """Shared rig: p0/p1, synthetic cards via _card(), real-lane enter/cast."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        for color in "WUBRG":
            self.world.players[self.p0].mana_pool[color] = 5
        self.ex.begin_turn(self.p0)  # the cast window lane (legality.py:1003)

    # ------------------------------------------------------------- helpers

    def _card(
        self,
        name,
        *,
        p="2",
        t="2",
        type_line="Creature",
        zone=ZONE_BATTLEFIELD,
        seat=None,
        cmc=2,
        is_token=False,
    ):
        ident = CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line=type_line,
            power=p,
            toughness=t,
            cmc=cmc,
            is_token=is_token,
        )
        return self.world.add_card(ident, seat if seat is not None else self.p0, zone)

    def _zone(self, handle) -> str:
        return self.world.zone_of(handle).kind

    def _hand_count(self, seat) -> int:
        return sum(
            1
            for h, c in self.world.cards.items()
            if self.world.zone_of(h).kind == ZONE_HAND
            and self.world.controller_of(h) == seat
        )

    def _enter(self, handle):
        """The scenario harness's 'enter' lane: the real MOVE_ZONE atom
        hand -> battlefield (the not-cast put-onto the replacement lane
        must catch)."""
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    Zone(ZoneKind.HAND, ControllerRef.YOU),
                ),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                tapped_on_enter=False,
            ),
            source=handle,
            controller=self.world.controller_of(handle),
            bindings={"cards": handle},
        )

    def _warden(self, name="Warden Clone"):
        """Synthetic Warden of the Woods: TargetingEvent(IS_SOURCE) ->
        may draw one."""
        handle = self._card(name)
        self.ex.attach_card(
            handle,
            record_of(
                [
                    TriggeredAbility(
                        event=TargetingEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                        condition=None,
                        effect=OptionalEffect(
                            inner=atom(
                                Verb.DRAW,
                                amount=QConst(1),
                                controller=ControllerRef.YOU,
                            )
                        ),
                    )
                ],
                name=name,
                oid=self.world.cards[handle].identity.oracle_id,
            ),
        )
        return handle

    def _growth(self, name="Growth"):
        """Synthetic Titanic Growth: instant, tap-the-target — one
        TARGET slot, no cost (the rig's mana pool is cosmetic)."""
        ident = CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line="Instant",
            power=None,
            toughness=None,
            cmc=2,
        )
        handle = self.world.add_card(ident, self.p0, ZONE_HAND)
        self.ex.attach_card(
            handle,
            record_of(
                [
                    SpellAbility(
                        kind=SpellKind.INSTANT,
                        effect=atom(Verb.TAP, target=_bf_target()),
                    )
                ],
                name=name,
                oid=ident.oracle_id,
            ),
        )
        return handle

    def _targeting_rows(self):
        # GameEvents live on the EventJournal, not the executor's raw
        # verb-row list (binding.match_new scans journal.events @504).
        return [
            e for e in self.ex.journal.events if getattr(e, "kind", None) == "TARGETING"
        ]

    # ------------------------------------------------ 1: TARGETING feed

    def test_targeting_feed_fires_warden_trigger(self):
        warden = self._warden()
        self._card("Library Top", zone=ZONE_LIBRARY)
        self._card("Library Second", zone=ZONE_LIBRARY)
        growth = self._growth()
        before = self._hand_count(self.p0)
        # The may-offer asks in the TRIGGER's fresh ctx (the settle's
        # ExecCtx), never the cast's per-op tuple — answer it on the
        # executor-wide provider lane, the scenario harness's pattern.
        self.ex.decisions.provider = lambda vocab, what: "fire"
        try:
            cast(self.ex, self.p0, growth, targets=(warden,))
            self.ex.fire_triggers()
        finally:
            self.ex.decisions.provider = None
        rows = self._targeting_rows()
        self.assertEqual([r.subject for r in rows], [warden])
        self.assertEqual(rows[0].cause, growth)
        # Bookkeeping: the hand held ONLY the spell, which resolves to the
        # graveyard (-1); the fired may-DRAW refills it (+1 from library).
        self.assertEqual(self._hand_count(self.p0), before, "may-DRAW fired")
        # The spell itself still resolved: its TAP hit the warden.
        self.assertTrue(self.world.cards[warden].tapped)

    def test_targeting_trigger_may_skip(self):
        warden = self._warden()
        self._card("Library Top", zone=ZONE_LIBRARY)
        growth = self._growth()
        before = self._hand_count(self.p0)
        self.ex.decisions.provider = lambda vocab, what: "skip"
        try:
            cast(self.ex, self.p0, growth, targets=(warden,))
            self.ex.fire_triggers()
        finally:
            self.ex.decisions.provider = None
        self.assertEqual(
            self._hand_count(self.p0), before - 1, "may-DRAW skipped"
        )  # the spell left the hand and nothing refilled it
        self.assertTrue(self.world.cards[warden].tapped)

    def test_targeting_trigger_silent_for_other_designations(self):
        warden = self._warden()
        bystander = self._card("Bystander")
        self._card("Library Top", zone=ZONE_LIBRARY)
        growth = self._growth()
        before = self._hand_count(self.p0)
        cast(self.ex, self.p0, growth, targets=(bystander,), decisions=("skip",))
        self.ex.fire_triggers()
        self.assertEqual([r.subject for r in self._targeting_rows()], [bystander])
        self.assertEqual(self._hand_count(self.p0), before - 1)  # silent, no draw
        self.assertFalse(self.world.cards[warden].tapped)  # never touched

    def test_targeting_event_trigger_registers_without_raise(self):
        # The r20b registration gap: TargetingEvent left _UNSUPPORTED_EVENTS.
        handle = self._card("Register Me")
        self.ex.attach_card(  # must NOT raise NotImplementedError
            handle,
            record_of(
                [
                    TriggeredAbility(
                        event=TargetingEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                        condition=None,
                        effect=atom(
                            Verb.DRAW,
                            amount=QConst(1),
                            controller=ControllerRef.YOU,
                        ),
                    )
                ],
                name="Register Me",
                oid=self.world.cards[handle].identity.oracle_id,
            ),
        )

    def test_designate_lane_emits_targeting(self):
        # The binder._designate emit site: a trigger that DESIGNATES (asks)
        # journals its own TARGETING row with the ability as cause.
        trigger_man = self._card("Triggers on Entry")
        self.ex.attach_card(
            trigger_man,
            record_of(
                [
                    TriggeredAbility(
                        event=ZoneChangeEvent(
                            from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                            to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                            subject=FAtom(
                                pred=FAtomPred.TYPE_EQ, string_value="Creature"
                            ),
                        ),
                        condition=None,
                        effect=atom(Verb.TAP, target=_bf_target()),
                    )
                ],
                name="Triggers on Entry",
                oid=self.world.cards[trigger_man].identity.oracle_id,
            ),
        )
        walker = self._card("Walker", zone=ZONE_HAND)

        def answer(vocab, what):
            return vocab[0]  # any prompt: take the Handle-sorted first

        self.ex.decisions.provider = answer
        try:
            self._enter(walker)
            self.ex.fire_triggers()
        finally:
            self.ex.decisions.provider = None
        rows = [r for r in self._targeting_rows() if r.cause == trigger_man]
        self.assertTrue(rows, "the designation lane journalled TARGETING")

    # -------------------------------------- 2: zone-change replacement

    def test_zone_replacement_exiles_entered_nontoken(self):
        priest = self._card("Priest Clone")
        self.ex.attach_card(
            priest,
            record_of(
                [_nontoken_enter_repl()],
                name="Priest Clone",
                oid=self.world.cards[priest].identity.oracle_id,
            ),
        )
        fodder = self._card("Fodder", zone=ZONE_HAND)
        self._enter(fodder)
        self.assertEqual(self._zone(fodder), ZONE_EXILE)
        self.assertTrue(
            any(
                isinstance(row, tuple) and row[1] == "ZONE_REPLACED"
                for row in self.ex.events
            ),
            "the consumption left an audit row",
        )

    def test_zone_replacement_spares_cast_creature(self):
        priest = self._card("Priest Clone")
        self.ex.attach_card(
            priest,
            record_of(
                [_nontoken_enter_repl()],
                name="Priest Clone",
                oid=self.world.cards[priest].identity.oracle_id,
            ),
        )
        ident = CardIdentity(
            oracle_id=card_id("Fresh Cast").oracle_id,
            name="Fresh Cast",
            type_line="Creature",
            power="2",
            toughness="2",
            cmc=2,
        )
        beaster = self.world.add_card(ident, self.p0, ZONE_HAND)
        self.ex.attach_card(
            beaster,
            record_of(
                [SpellAbility(kind=SpellKind.CREATURE)],
                name="Fresh Cast",
                oid=ident.oracle_id,
            ),
        )
        cast(self.ex, self.p0, beaster)
        self.assertEqual(
            self._zone(beaster),
            ZONE_BATTLEFIELD,
            "WAS_CAST_THIS_TURN flipped the FNot condition: spared",
        )

    def test_zone_replacement_token_exempt(self):
        priest = self._card("Priest Clone")
        self.ex.attach_card(
            priest,
            record_of(
                [_nontoken_enter_repl()],
                name="Priest Clone",
                oid=self.world.cards[priest].identity.oracle_id,
            ),
        )
        kit = self._card("Kitten", zone=ZONE_HAND, is_token=True)
        self._enter(kit)
        self.assertEqual(self._zone(kit), ZONE_BATTLEFIELD, "tokens are exempt")

    # -------------------------------------------- 3: player-subject lane

    def _ctx(self):
        anchor = self._card("Anchor")
        return self.ex._ctx(
            source=anchor, controller=self.p0, bindings={}, decisions=()
        )

    def test_player_subject_shape_predicates_are_false(self):
        ctx = self._ctx()
        for pred in (
            FAtomPred.TYPE_EQ,
            FAtomPred.SUBTYPE_EQ,
            FAtomPred.NAME_EQ,
            FAtomPred.IS_TOKEN,
            FAtomPred.IS_PERMANENT,
        ):
            f = (
                FAtom(pred=pred, string_value="Creature")
                if pred in (FAtomPred.TYPE_EQ, FAtomPred.SUBTYPE_EQ, FAtomPred.NAME_EQ)
                else FAtom(pred=pred)
            )
            self.assertFalse(
                _player_subject_verdict(f, self.p1, ctx),
                f"{pred.name} is simply false of a player",
            )

    def test_player_subject_boolean_shapes(self):
        ctx = self._ctx()
        creature = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
        self.assertFalse(_player_subject_verdict(FAnd((creature,)), self.p1, ctx))
        self.assertFalse(_player_subject_verdict(FOr((creature,)), self.p1, ctx))
        self.assertTrue(
            _player_subject_verdict(FNot(inner=creature), self.p1, ctx),
            "a player is truly not a creature",
        )

    def test_player_subject_controller_is_compares_seats(self):
        ctx = self._ctx()
        you = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        self.assertTrue(_player_subject_verdict(you, self.p0, ctx))
        self.assertFalse(_player_subject_verdict(you, self.p1, ctx))

    def test_player_subject_unknown_pred_still_raises(self):
        ctx = self._ctx()
        with self.assertRaises(NotImplementedError):
            _player_subject_verdict(
                FAtom(pred=FAtomPred.LIFE_LEAD_OVER_START_GE, count=QConst(1)),
                self.p1,
                ctx,
            )

    # ------------------------------------------------ 4: static payloads

    def test_reveal_static_installs_disclosure_layer(self):
        snoop = self._card("Snoop Clone")
        self.ex.attach_card(  # must NOT raise: the r20b REVEAL-12e gap
            snoop,
            record_of(
                [
                    StaticAbility(
                        effect=atom(
                            Verb.REVEAL,
                            controller=ControllerRef.YOU,
                            count=QConst(1),
                            duration=DurationPermanent(),
                        ),
                        condition=None,
                    )
                ],
                name="Snoop Clone",
                oid=self.world.cards[snoop].identity.oracle_id,
            ),
        )
        self.assertTrue(
            any(
                r.kind == "disclosure" and r.source == snoop
                for r in self.ex.layers.records
            ),
            "the disclosure fact is registered, anchored to the source",
        )

    def test_gain_life_static_is_guarded_and_flagged(self):
        # AMENDED r23a (2026-10-02): flag-not-degrade stands, but the
        # raise-at-attach KILLED GAMES (Rin and Seri's cast lane,
        # reports/games_2026-10-02.json). The refusal stays LOUD — it is
        # RECORDED, not thrown: the permanent enters, and the
        # unparseable static (compiler mis-split half — the suspect file
        # keeps the attribution) lands in executor.unparseable_statics
        # for coverage to see. No silent skip anywhere.
        card = self._card("Mis-Split Legend")
        self.ex.attach_card(
            card,
            record_of(
                [
                    StaticAbility(
                        effect=atom(
                            Verb.GAIN_LIFE,
                            amount=QConst(1),
                            controller=ControllerRef.YOU,
                        ),
                        condition=None,
                    )
                ],
                name="Mis-Split Legend",
                oid=self.world.cards[card].identity.oracle_id,
            ),
        )
        self.assertEqual(len(self.ex.unparseable_statics), 1)
        self.assertIn("GAIN_LIFE", self.ex.unparseable_statics[0])
        self.assertIn(str(card), self.ex.unparseable_statics[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
