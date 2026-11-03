"""Round-12d pins: continuous layers (plan /06 §12d). Covers the
StaticAbility anthem half (set-membership recompute, condition cycles,
materialized PT entries folding with verb PTs), keyword_of over printed +
granted + lost keywords (seq-order basis), the GRANT_ABILITY/LOSE_ABILITY
verbs incl. the end-of-turn expiry half of the Duration vocab, GRANTED
activated abilities through the FULL legality surface (negative-index
rows, both seats, the grantee-coordinates controller rule, tokens via the
same path), lethal-damage readout through the materialized stack, and the
Choose ORDER contract (decision token = index into query.choose_options).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Ability,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    ControllerRef,
    Cost,
    CostTap,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QAtMost,
    QConst,
    QCount,
    QUnbounded,
    Selector,
    SelectorMode,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import ability_playable, activate
from MTG_bot.core.executor.query import choose_options, legal_activations
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD, GameWorld

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
IS_TAPPED = FAtom(FAtomPred.IS_TAPPED)


def target_sel(filter_: object = UNIV) -> Selector:
    return Selector(QConst(1), SelectorMode.TARGET, filter_, zones=(BF_ANY,))  # pyright: ignore[reportArgumentType]


def scope_you() -> Selector:
    """An anthem's affected set: ALL creatures you control (CHOOSE-mode
    like the compiled payloads, resolved at recompute)."""
    return Selector(QConst(99), SelectorMode.ALL, CREATURE, zones=(BF_YOU,))


def modify_all(pt_p=0, pt_t=0) -> Atom:
    roles: dict = {"target": scope_you()}
    if pt_p:
        roles["power"] = PtDelta(PtDirection.INCREASE, QConst(pt_p))
    if pt_t:
        roles["toughness"] = PtDelta(PtDirection.INCREASE, QConst(pt_t))
    return atom(Verb.MODIFY_PT, **roles)


def tap_add_mana(color="G") -> ActivatedAbility:
    return ActivatedAbility(
        cost=Cost(parts=(CostTap(),)),
        effect=atom(
            Verb.ADD_MANA, controller=ControllerRef.YOU, amount=QConst(1), color=color
        ),
    )


def gain(n) -> Atom:
    return atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(n))


def record_of(abilities, name, oid, keywords=()) -> CardRecord:
    return CardRecord(
        oracle_id=oid,
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
        keywords=keywords,
        abilities=tuple(abilities),
        is_token=False,
    )


class LayerCase(unittest.TestCase):
    def setUp(self):
        self.world = GameWorld(num_players=2, start_life=20, master_seed=21)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.banner = self.world.add_card(
            card_id("Banner", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.beta = self.world.add_card(
            card_id("Beta", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def attach(self, handle, abilities, keywords=(), name=None):
        card = self.world.cards[handle]
        bound = self.ex.attach_card(
            handle,
            record_of(
                abilities,
                name=card.identity.name if name is None else name,
                oid=card.identity.oracle_id,
                keywords=keywords,
            ),
        )
        self.settle()  # recompute: the keyword/static layers need one pass
        return bound

    def pt(self, handle):
        return self.ex.ledger.effective_pt(self.world.cards[handle].identity, handle)

    def pump(self, target, p=0, t=0, duration=None, source=None):
        roles: dict = {"target": target_sel()}
        if p:
            roles["power"] = PtDelta(PtDirection.INCREASE, QConst(p))
        if t:
            roles["toughness"] = PtDelta(PtDirection.INCREASE, QConst(t))
        if duration is not None:
            roles["duration"] = duration
        self.ex.execute(
            atom(Verb.MODIFY_PT, **roles),
            source=source or self.banner,
            controller=self.p0,
            bindings={"target": target},
        )

    def grant(self, targets, ability: Ability, duration=None, source=None, ctrl=None):
        roles: dict = {"target": target_sel(), "ability": ability}
        if duration is not None:
            roles["duration"] = duration
        return self.ex.apply_effect(
            atom(Verb.GRANT_ABILITY, **roles),
            source=source or self.banner,
            controller=ctrl or self.p0,
            bindings={"target": list(targets)},
        )

    def lose(self, targets, keyword: Keyword, source=None, ctrl=None):
        return self.ex.apply_effect(
            atom(
                Verb.LOSE_ABILITY, target=target_sel(), ability=KeywordAbility(keyword)
            ),
            source=source or self.banner,
            controller=ctrl or self.p0,
            bindings={"target": list(targets)},
        )

    def settle(self):  # force one recompute pass through a no-op atom
        self.ex.execute(gain(0), source=self.banner, controller=self.p0)


class TestStaticAnthem(LayerCase):
    def test_anthem_set_membership_recomputes(self):
        self.attach(self.banner, [StaticAbility(effect=modify_all(1, 1))])
        self.settle()
        self.assertEqual(self.pt(self.banner), (3, 3))  # includes itself
        self.assertEqual(self.pt(self.alpha), (3, 3))
        self.assertEqual(self.pt(self.beta), (2, 2))  # not "you"
        newguy = self.world.add_card(card_id("Newguy", "1", "1"), self.p0)
        self.world.move_to_zone(newguy, self.p0, ZONE_BATTLEFIELD)
        self.settle()
        self.assertEqual(self.pt(newguy), (2, 2))  # entered the set
        self.world.move_to_zone(newguy, self.p0, ZONE_EXILE)
        self.settle()
        self.assertEqual(len(self.ex.ledger.changes_for(newguy)), 1)
        self.assertEqual(self.pt(newguy), (1, 1))  # stale entry terminal

    def test_anthem_detach_drops_the_buff(self):
        self.attach(self.banner, [StaticAbility(effect=modify_all(2, 2))])
        self.settle()
        self.assertEqual(self.pt(self.alpha), (4, 4))
        self.ex.binder.detach(self.banner)
        self.settle()
        self.assertEqual(self.pt(self.alpha), (2, 2))

    def test_static_condition_cycles_through_the_journal(self):
        # "creatures you control get +1/+1 as long as Banner is tapped"
        self.attach(
            self.banner,
            [StaticAbility(effect=modify_all(1, 0), condition=IS_TAPPED)],
        )
        self.settle()
        self.assertEqual(self.pt(self.alpha), (2, 2))  # condition false
        self.ex.execute(
            atom(Verb.TAP, target=target_sel()),
            source=self.banner,
            controller=self.p0,
            bindings={"target": self.banner},
        )
        self.assertEqual(self.pt(self.alpha), (3, 2))
        self.ex.execute(
            atom(Verb.UNTAP, target=target_sel()),
            source=self.banner,
            controller=self.p0,
            bindings={"target": self.banner},
        )
        self.assertEqual(self.pt(self.alpha), (2, 2))

    def test_materialized_pt_folds_with_verb_pts_and_eot(self):
        self.attach(self.banner, [StaticAbility(effect=modify_all(1, 1))])
        self.settle()
        self.pump(self.alpha, 2, 2, DurationEot())
        self.assertEqual(self.pt(self.alpha), (5, 5))  # base+static+verb
        self.ex.end_turn()  # the VERB entry sweeps...
        self.assertEqual(self.pt(self.alpha), (3, 3))  # ...the layer stays
        self.ex.binder.detach(self.banner)
        self.settle()
        self.assertEqual(self.pt(self.alpha), (2, 2))  # and dies with it

    def test_timestamp_order_survives_the_eot_sweep(self):
        # SET 1/1 (earlier clock) THEN +3/+3 permanent (later): live = 4/4.
        # After the Eot sweep removes the SET, the permanent delta folds
        # onto the PRINTED base — the documented base->timestamp->order
        # rule, pinned (this is what "layers are ordinary ledger entries"
        # costs, and why the fold is one shared stack).
        self.ex.execute(
            atom(
                Verb.SET_PT,
                target=target_sel(),
                power=QConst(1),
                toughness=QConst(1),
                duration=DurationEot(),
            ),
            source=self.banner,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.pump(self.alpha, 3, 3)
        self.assertEqual(self.pt(self.alpha), (4, 4))
        self.ex.end_turn()
        self.assertEqual(self.pt(self.alpha), (5, 5))


def _your_graveyard_count() -> QCount:
    """``the number of cards in your graveyard`` (the counted-static shape:
    Kinetic Augur, Blanchwood Armor, Malefic Scythe's soul counters)."""
    return QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            UNIV,
            zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),),
        )
    )


class TestCountedStatic(LayerCase):
    """B-52 (2026-10-29): a counted static P/T value is continuously
    recomputed (CR 611.3a: a static ability's effect is not locked in;
    CR 613.4a/c: a characteristic-defining or modifying P/T effect applies
    the value of the moment). It used to freeze at its first value."""

    def bury(self, name):
        card = self.world.add_card(card_id(name, type_line="Instant"), self.p0)
        self.world.move_to_zone(card, self.p0, ZONE_GRAVEYARD)
        self.settle()
        return card

    def test_counted_delta_follows_its_count_both_ways(self):
        # "Creatures you control get +X/+0, where X is the number of cards
        # in your graveyard." Up with each card, down when one leaves.
        self.attach(
            self.banner,
            [
                StaticAbility(
                    effect=atom(
                        Verb.MODIFY_PT,
                        target=scope_you(),
                        power=PtDelta(PtDirection.INCREASE, _your_graveyard_count()),
                    )
                )
            ],
        )
        self.assertEqual(self.pt(self.alpha), (2, 2))
        first = self.bury("Zap One")
        self.assertEqual(self.pt(self.alpha), (3, 2))
        self.bury("Zap Two")
        self.assertEqual(self.pt(self.alpha), (4, 2))
        self.assertEqual(self.pt(self.banner), (4, 2))
        self.world.move_to_zone(first, self.p0, ZONE_EXILE)
        self.settle()
        self.assertEqual(self.pt(self.alpha), (3, 2))
        self.assertEqual(self.pt(self.beta), (2, 2))  # not "you": untouched

    def test_counted_set_follows_its_count_and_keeps_its_timestamp(self):
        # Kinetic Augur's shape: "~'s power is equal to the number of
        # cards in your graveyard" (a SET over the source). The entry is
        # revalued in place: CR 613.7a, a static's effect keeps its
        # timestamp while its value moves, so the ledger does not grow a
        # new entry (a new place in the timestamp fold) per change.
        self.attach(
            self.alpha,
            [
                StaticAbility(
                    effect=atom(
                        Verb.SET_PT,
                        target=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAtom(FAtomPred.IS_SOURCE),
                            zones=(BF_ANY,),
                        ),
                        power=_your_graveyard_count(),
                    )
                )
            ],
        )
        self.assertEqual(self.pt(self.alpha), (0, 2))
        (entry,) = self.ex.ledger.changes_for(self.alpha)
        first = self.bury("Zap One")
        self.bury("Zap Two")
        self.assertEqual(self.pt(self.alpha), (2, 2))
        self.world.move_to_zone(first, self.p0, ZONE_EXILE)
        self.settle()
        self.assertEqual(self.pt(self.alpha), (1, 2))
        (now,) = self.ex.ledger.changes_for(self.alpha)
        self.assertEqual(
            (now.record_id, now.created_clock), (entry.record_id, entry.created_clock)
        )
        self.assertEqual(now.power_set, 1)

    def test_constant_anthem_is_never_rewritten(self):
        # The recompute re-reads every value; a value that did not change
        # must leave the ledger byte-identical (replay fingerprints).
        self.attach(self.banner, [StaticAbility(effect=modify_all(1, 1))])
        before = self.ex.ledger.dump()
        self.bury("Zap One")
        self.settle()
        self.assertEqual(self.ex.ledger.dump(), before)


class TestKeywordLayers(LayerCase):
    def test_keyword_of_printed_and_after_detach(self):
        self.attach(self.banner, [], keywords=(KeywordAbility(Keyword.FLYING),))
        self.assertTrue(self.ex.layers.keyword_of(self.banner, Keyword.FLYING))
        self.assertFalse(self.ex.layers.keyword_of(self.alpha, Keyword.FLYING))
        self.ex.binder.detach(self.banner)
        self.settle()  # the map-recompute point
        self.assertFalse(self.ex.layers.keyword_of(self.banner, Keyword.FLYING))

    def test_granted_keyword_with_eot_expiry(self):
        self.grant([self.beta], KeywordAbility(Keyword.FIRST_STRIKE), DurationEot())
        self.assertTrue(self.ex.layers.keyword_of(self.beta, Keyword.FIRST_STRIKE))
        self.ex.end_turn()
        self.assertFalse(self.ex.layers.keyword_of(self.beta, Keyword.FIRST_STRIKE))

    def test_permanent_grant_outlives_the_turn_cycle(self):
        self.grant([self.alpha], KeywordAbility(Keyword.TRAMPLE))
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)
        self.assertTrue(self.ex.layers.keyword_of(self.alpha, Keyword.TRAMPLE))

    def test_lose_removes_a_printed_keyword_and_detach_restores(self):
        self.attach(self.beta, [], keywords=(KeywordAbility(Keyword.FLYING),))
        self.assertTrue(self.ex.layers.keyword_of(self.beta, Keyword.FLYING))
        self.lose([self.beta], Keyword.FLYING, source=self.banner, ctrl=self.p0)
        self.assertFalse(self.ex.layers.keyword_of(self.beta, Keyword.FLYING))
        # The LOSE layer's SOURCE is the aura, not the victim: detaching
        # the victim keeps the printed keyword under the (still live) lose
        # layer; detaching the AURA is what ends the LOSE layer.
        self.ex.binder.detach(self.banner)
        self.settle()
        self.assertTrue(self.ex.layers.keyword_of(self.beta, Keyword.FLYING))

    def test_layer_seq_order_is_the_tiebreak(self):
        # later registration wins the SAME keyword (the dump-order rule):
        # lose-then-grant keeps it, grant-then-lose takes it away.
        self.grant([self.alpha], KeywordAbility(Keyword.HASTE))
        self.lose([self.alpha], Keyword.HASTE)
        self.assertFalse(self.ex.layers.keyword_of(self.alpha, Keyword.HASTE))
        self.grant(
            [self.beta], KeywordAbility(Keyword.HASTE)
        )  # after the lose, for Beta
        self.assertTrue(self.ex.layers.keyword_of(self.beta, Keyword.HASTE))

    def test_grant_via_a_firing_trigger_uses_the_registry(self):
        # ETB on Banner grants Alpha haste — proves the trigger-fire ExecCtx
        # carries the layer registry (binder edit), not just direct calls.
        self.world.move_to_zone(self.banner, self.p0, ZONE_EXILE)
        self.attach(
            self.banner,
            [
                TriggeredAbility(
                    event=_etb_event(),
                    condition=None,
                    effect=atom(
                        Verb.GRANT_ABILITY,
                        # CHOOSE-mode: the compiled-payload convention for
                        # effect-time search (TARGET needs a designation).
                        target=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAtom(FAtomPred.NAME_EQ, string_value="Alpha"),
                            zones=(BF_ANY,),
                        ),
                        ability=KeywordAbility(Keyword.HASTE),
                    ),
                )
            ],
        )
        # The ETB must ride a journalled atom (raw world moves are not
        # what the journal diffs — the enter-atom is the 12b convention).
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(FAtom(FAtomPred.NAME_EQ, string_value="Banner")),
                destination=BF_YOU,
            ),
            source=self.banner,
            controller=self.p0,
            bindings={"cards": self.banner},
        )
        self.assertTrue(self.ex.layers.keyword_of(self.alpha, Keyword.HASTE))


class TestGrantedAbilities(LayerCase):
    def test_granted_activated_legality_and_the_grantee_rule(self):
        self.grant([self.beta], tap_add_mana("G"))
        rows = legal_activations(self.world, self.ex, self.p1)
        self.assertEqual([(r.source, r.ability_idx) for r in rows], [(self.beta, -1)])
        self.assertEqual(rows[0].payment.tap, (self.beta,))
        # p0 granted it but does NOT control it: no row, and the direct
        # gate says so (CR 602.3 — the CONTROLLER, not the granter).
        self.assertEqual(legal_activations(self.world, self.ex, self.p0), [])
        self.assertIn(
            "not_controller",
            ability_playable(self.world, self.ex, self.beta, -1, seat=self.p0) or "",
        )
        events = activate(self.ex, self.beta, -1, seat=self.p1)
        self.assertEqual(self.world.players[self.p1].mana_pool, {"G": 1})
        self.assertTrue(self.world.cards[self.beta].tapped)
        self.assertTrue(events)

    def test_granted_row_dies_with_the_eot_grant(self):
        self.grant([self.beta], tap_add_mana(), DurationEot())
        self.assertEqual(len(legal_activations(self.world, self.ex, self.p1)), 1)
        self.ex.end_turn()
        self.assertEqual(legal_activations(self.world, self.ex, self.p1), [])
        self.assertEqual(self.ex.layers.granted_activated(self.beta), ())

    def test_static_anthema_grants_the_ability_to_the_whole_set(self):
        self.attach(
            self.banner,
            [
                StaticAbility(
                    effect=atom(
                        Verb.GRANT_ABILITY,
                        target=scope_you(),
                        ability=tap_add_mana("W"),
                    )
                )
            ],
        )
        self.settle()
        rows = legal_activations(self.world, self.ex, self.p0)
        self.assertEqual(
            sorted(r.source for r in rows), sorted([self.banner, self.alpha])
        )
        activate(self.ex, self.alpha, -1, seat=self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool, {"W": 1})
        self.ex.binder.detach(self.banner)  # the anthema's rows vanish
        self.settle()
        self.assertEqual(self.ex.layers.granted_abilities(self.alpha), ())

    def test_token_activates_what_it_was_granted(self):
        # The granted path needs no compiled record: a token (no oracle-id
        # bridge) activates its granted {T} happily.
        token = self.world.add_card(card_id("Token", "1", "1"), self.p0)
        self.world.move_to_zone(token, self.p0, ZONE_BATTLEFIELD)
        self.grant([token], tap_add_mana())
        self.assertEqual(
            [
                (r.source, r.ability_idx)
                for r in legal_activations(self.world, self.ex, self.p0)
            ],
            [(token, -1)],
        )
        activate(self.ex, token, -1, seat=self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool, {"G": 1})


class TestChooseOrder(LayerCase):
    def test_decision_token_indexes_the_query_enumeration(self):
        node = Choose(QAtMost(1), (gain(1), gain(2)))
        opts = choose_options(self.ex, node, source=self.banner, controller=self.p0)
        # size-ascending, index-lex: (empty), (0), (1)
        self.assertEqual([o.option_idxs for o in opts], [(), (0,), (1,)])
        # life accumulates across the three casts: chose-nothing, then
        # option-0 (+1), then option-1 (+2).
        for token, expected_life in (("0", 20), ("1", 21), ("2", 23)):
            self.ex.apply_effect(
                node,
                source=self.banner,
                controller=self.p0,
                decisions=(token,),
            )
            self.assertEqual(self.world.players[self.p0].life, expected_life)
        # an out-of-range token is a vocabulary miss, not a silent default
        with self.assertRaises(ValueError):
            self.ex.apply_effect(
                node,
                source=self.banner,
                controller=self.p0,
                decisions=("3",),
            )


def _etb_event():
    from MTG_bot.core.ability_tree import ZoneChangeEvent

    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=BF_YOU,
        subject=FAtom(FAtomPred.IS_SOURCE),
    )


if __name__ == "__main__":
    unittest.main()
