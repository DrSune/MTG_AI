"""CR 702.11 HEXPROOF targeting: a permanent with hexproof CAN'T be the
target of spells or abilities an OPPONENT controls (Sporeweb Weaver,
Spined Megalodon) — and every shape that must NOT be moved stays put:

  * the controller's own spells still target their own hexproof creature
    (CR 702.11b's direction clause, read through the engine's opponent
    convention: a distinct seat);
  * "hexproof from {quality}" (Spined Megalodon: COLOR_HAS U param)
    vetoes ONLY sources matching the row's filter;
  * granted hexproof (Ranger's Guile's GRANT row) blocks while live, and
    a LOSE_ABILITY stops the block (the keyword name gate);
  * a hexproof creature's CONTROLLER is still a legal "any target"
    player (702.11 protects the object, not the player);
  * non-targeting sweepers (ALL-mode DESTROY) still hit — only
    SelectorMode.TARGET enumeration is filtered;
  * the keyword is zone-limited: a hexproof card in a graveyard is an
    ordinary target;
  * the STACK lane: hexproof is defined on a permanent (CR 702.11b) and a
    permanent card's abilities work only on the battlefield (CR 113.6), so
    an opponent may target a hexproof creature SPELL (TestHexproofOnStack);
  * the cast lane (601.2c) refuses the off-population designation, the
    trigger ask vocabulary never SHOWS the hexproof creature (the menu
    presents only legal choices), and a legal target still lands.
"""

from __future__ import annotations

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    DurationEot,
    FAtom,
    FAtomPred,
    FOr,
    Keyword,
    KeywordAbility,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    SpellKind,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.executor.stack import cast, park
from MTG_bot.core.executor.query import _widen_any_target, legal_targets, player_target_slot
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, ZONE_STACK
from MTG_bot.core.test_executor_binding import etb_trigger
from MTG_bot.core.test_executor_layers import (
    BF_ANY,
    CREATURE,
    LayerCase,
    UNIV,
    atom,
    card_id,
    record_of,
    target_sel,
)
from MTG_bot.core.test_executor_stack import spell_rec

_OID = itertools.count(30000)


def _oid() -> str:
    return f"{next(_OID):08x}-1111-2222-3333-444444444444"


class HexproofCase(LayerCase):
    """The layers rig (banner/alpha p0, beta p1, attach/grant/lose/
    settle) plus: a battlefield creature whose record carries a live
    HEXPROOF keyword row (bare or filtered), colored spell-shape query
    sources, and a turn window open for the cast lane."""

    def setUp(self) -> None:
        super().setUp()
        self.ex.begin_turn(self.p0)

    def tearDown(self) -> None:
        self.ex.decisions.provider = None

    def hexproof_creature(self, name, seat, hexproof_from=None):
        """A 2/2 whose printed record carries one HEXPROOF row: bare
        (no params → blocks every opponent target) or one Filter param
        per quality (the compiled Megalodon/Protean values shape)."""
        handle = self.world.add_card(card_id(name, "2", "2"), seat, ZONE_BATTLEFIELD)
        params = ()
        if hexproof_from is not None:
            params = tuple(FAtom(FAtomPred.COLOR_HAS, color=c) for c in hexproof_from)
        self.attach(
            handle,
            [],
            keywords=(KeywordAbility(keyword=Keyword.HEXPROOF, params=params),),
        )
        return handle

    def spell_source(self, name, colors, seat):
        """A colored card acting as the source handle of a query (the
        COLOR_HAS rows read the source card's printed identity)."""
        return self.world.add_card(
            CardIdentity(
                oracle_id=_oid(),
                name=name,
                type_line="Instant",
                power=None,
                toughness=None,
                cmc=2,
                colors=tuple(colors),
            ),
            seat,
            ZONE_HAND,
        )

    def targetable_creatures(self, source, controller):
        """The TARGET-mode candidate list one 'deal 1 damage to target
        creature' query would show at ``source``'s coordinates."""
        slot = legal_targets(
            self.world,
            self.ex,
            target_sel(CREATURE),
            source=source,
            controller=controller,
        )
        return set(slot.candidates)

    def plain_creature(self, name, seat):
        """A keyword-less creature: the moving control for every veto."""
        handle = self.world.add_card(card_id(name, "2", "2"), seat, ZONE_BATTLEFIELD)
        self.attach(handle, [])
        return handle

    def hexproof_spell(self, name, seat, hexproof_from=None, register=True):
        """A printed-hexproof creature card STANDING on the stack (the
        folded ``cast`` helper resolves on the spot, so the standing-spell
        shape parks the card directly, exactly where CR 601.2h leaves it
        before any response): the compiled record is filed in the binder's
        ORACLE registry (what ``attach_pool`` does for hand cards —
        registered but NOT attached: the battlefield-only lifecycle never
        fired for this handle) and the printed identity seeds the
        zone-less HEXPROOF name."""
        params: tuple[FAtom, ...] = ()
        if hexproof_from is not None:
            params = tuple(FAtom(FAtomPred.COLOR_HAS, color=c) for c in hexproof_from)
        rec = record_of(
            [],
            name=name,
            oid=_oid(),
            keywords=(KeywordAbility(keyword=Keyword.HEXPROOF, params=params),),
        )
        if register:
            self.ex.binder.records[rec.oracle_id] = rec
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name=name,
                type_line="Creature",
                power="2",
                toughness="2",
                cmc=2,
                keywords=("HEXPROOF",),
            ),
            seat,
            ZONE_HAND,
        )
        park(self.ex, seat, handle)
        self.settle()  # rebuild the derived maps: seed the printed name
        return handle

    def targetable_stack_spells(self, source, controller):
        """The TARGET-mode candidates one 'counter target creature
        spell'-shaped query shows from ``source``'s coordinates."""
        slot = legal_targets(
            self.world,
            self.ex,
            Selector(
                QConst(1),
                SelectorMode.TARGET,
                CREATURE,
                zones=(Zone(ZoneKind.STACK, ControllerRef.ANY),),
            ),
            source=source,
            controller=controller,
        )
        return set(slot.candidates)


class TestHexproofLegality(HexproofCase):
    def test_opponent_cannot_target_hexproof_creature(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        plain = self.plain_creature("Horned Bash", self.p1)
        bolt = self.spell_source("Shock", ("R",), self.p0)
        cands = self.targetable_creatures(bolt, self.p0)
        self.assertNotIn(weaver, cands)  # 702.11b: opponent's spell, vetoed
        self.assertIn(plain, cands)  # the twin without the keyword lands

    def test_controller_can_target_own_hexproof_creature(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        bolt = self.spell_source("Shock", ("R",), self.p1)
        self.assertIn(weaver, self.targetable_creatures(bolt, self.p1))

    def test_opponent_activated_ability_source_is_vetoed(self):
        mine = self.hexproof_creature("Line Keeper", self.p0)
        theirs = self.plain_creature("Pest Invader", self.p1)
        cands = self.targetable_creatures(theirs, self.p1)
        self.assertNotIn(mine, cands)  # ability source, same direction rule
        own_source = self.plain_creature("Banner Wolf", self.p0)
        self.assertIn(mine, self.targetable_creatures(own_source, self.p0))

    def test_hexproof_from_color_vetoes_only_matching_source(self):
        megalodon = self.hexproof_creature(
            "Spined Megalodon", self.p1, hexproof_from=("U",)
        )
        blue = self.spell_source("Cancel", ("U",), self.p0)
        red = self.spell_source("Shock", ("R",), self.p0)
        self.assertNotIn(megalodon, self.targetable_creatures(blue, self.p0))
        self.assertIn(megalodon, self.targetable_creatures(red, self.p0))

    def test_bare_hexproof_vetoes_any_colored_source(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        blue = self.spell_source("Cancel", ("U",), self.p0)
        self.assertNotIn(weaver, self.targetable_creatures(blue, self.p0))

    def test_hexproof_creature_controller_is_a_legal_player_target(self):
        # 702.11 protects the hexproof OBJECT; "any target" still lists
        # the player who controls it (the Skeleton Archer population).
        self.hexproof_creature("Sporeweb Weaver", self.p1)
        any_target = Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(ANY_PLAYER,))
        slot = legal_targets(
            self.world, self.ex, any_target, source=self.banner, controller=self.p0
        )
        self.assertIn(self.p1, set(slot.candidates))

    def test_granted_hexproof_blocks_while_live(self):
        alpha = self.plain_creature("Alpha", self.p0)
        self.grant(
            [alpha],
            KeywordAbility(keyword=Keyword.HEXPROOF),
            source=self.banner,
            ctrl=self.p0,
        )
        self.settle()
        theirs = self.plain_creature("Beta Blade", self.p1)
        self.assertNotIn(alpha, self.targetable_creatures(theirs, self.p1))
        self.assertIn(alpha, self.targetable_creatures(self.banner, self.p0))

    def test_lost_hexproof_stops_blocking(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        self.lose([weaver], Keyword.HEXPROOF, source=self.banner, ctrl=self.p0)
        self.settle()
        bolt = self.spell_source("Shock", ("R",), self.p0)
        self.assertIn(weaver, self.targetable_creatures(bolt, self.p0))

    def test_hexproof_is_dead_outside_the_battlefield(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.ALL,
                    UNIV,
                    zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                ),
                destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER),
            ),
            source=self.banner,
            controller=self.p0,
            bindings={"cards": weaver},
        )
        self.assertEqual(self.world.zone_of(weaver).kind, ZONE_GRAVEYARD)
        bolt = self.spell_source("Collected Company-ish", ("R",), self.p0)
        # An ANY-zone TARGET query DOES enumerate the graveyard creature;
        # the zone guard must NOT veto it there — hexproof (CR 113.10,
        # 112.6) functions only on the battlefield/stack, so an over-broad
        # keyword map read would wrongly remove this ordinary target.
        any_creature = Selector(QConst(1), SelectorMode.TARGET, CREATURE, zones=(ANY_ANY,))
        slot = legal_targets(
            self.world, self.ex, any_creature, source=bolt, controller=self.p0
        )
        self.assertIn(weaver, set(slot.candidates))

    def test_non_targeting_sweeper_still_destroys_hexproof(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        plain = self.plain_creature("Horned Bash", self.p1)
        sweep_all = Selector(QConst(99), SelectorMode.ALL, CREATURE, zones=(BF_ANY,))
        self.ex.execute(
            atom(Verb.DESTROY, target=sweep_all),
            source=self.banner,
            controller=self.p0,
        )
        for handle in (weaver, plain):  # ALL-mode: no target, no veto (702.11)
            self.assertEqual(self.world.zone_of(handle).kind, ZONE_GRAVEYARD)


class TestHexproofLanes(HexproofCase):
    """The veto is one oracle consumed by EVERY target surface: the cast
    validator, the trigger ask vocabulary."""

    def target_bolt(self, name="Lightning Bolt", colors=("R",)):
        rec = spell_rec(
            name,
            SpellKind.INSTANT,
            effect=atom(
                Verb.DEAL_DAMAGE, target=target_sel(CREATURE), amount=QConst(2)
            ),
            colors=colors,
        )
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name=name,
                type_line="Instant",
                power=None,
                toughness=None,
                cmc=3,
                colors=tuple(colors),
            ),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle

    def test_cast_lane_refuses_the_hexproof_designation(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        bolt = self.target_bolt()
        with self.assertRaises(ValueError) as raised:
            cast(self.ex, self.p0, bolt, targets=(weaver,))
        self.assertIn("off_population", str(raised.exception))  # 601.2c veto

    def test_cast_lands_on_a_legal_target_despite_hexproof_twin(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        plain = self.plain_creature("Horned Bash", self.p1)
        bolt = self.target_bolt()
        cast(self.ex, self.p0, bolt, targets=(plain,))
        self.assertEqual(self.world.zone_of(plain).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(weaver).kind, ZONE_BATTLEFIELD)

    def test_trigger_ask_vocabulary_never_shows_the_hexproof_creature(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        plain = self.plain_creature("Horned Bash", self.p1)
        archer = self.world.add_card(
            card_id("Skeleton Archer", "1", "1"), self.p0, ZONE_HAND
        )
        self.attach(
            archer,
            [
                etb_trigger(
                    atom(
                        Verb.DEAL_DAMAGE, target=target_sel(CREATURE), amount=QConst(2)
                    )
                )
            ],
        )
        asks: list[tuple[tuple[str, ...], str]] = []

        def provider(vocab, what):
            asks.append((tuple(vocab), what))
            return str(plain) if str(plain) in vocab else vocab[0]

        self.ex.decisions.provider = provider
        self.enter_archer(archer)
        self.assertTrue(asks, "the ETB target ask never happened")
        vocab = asks[0][0]
        self.assertNotIn(str(weaver), vocab)  # the menu presents only legal choices
        self.assertIn(str(plain), vocab)
        self.assertEqual(self.world.zone_of(plain).kind, ZONE_GRAVEYARD)  # died

    def enter_archer(self, handle):
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.ALL,
                    UNIV,
                    zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                ),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER),
            ),
            source=handle,
            controller=self.p0,
            bindings={"cards": handle},
        )


class TestHexproofOnStack(HexproofCase):
    """CR 702.11b defines hexproof on a permanent, and a permanent card's
    abilities function only on the battlefield (CR 113.6): an opponent may
    target a hexproof creature SPELL, so a counterspell can counter it."""

    def test_opponent_may_target_a_bare_hexproof_spell(self):
        spell = self.hexproof_spell("Nine Lives", self.p1)  # bare printed
        self.assertEqual(self.world.zone_of(spell).kind, ZONE_STACK)
        for colors in (("U",), ("R",)):
            src = self.spell_source(f"React {colors}", colors, self.p0)
            self.assertIn(spell, self.targetable_stack_spells(src, self.p0))

    def test_opponent_blue_source_may_target_a_hexproof_from_blue_spell(self):
        spell = self.hexproof_spell("Sporeweb Weaver", self.p1, hexproof_from=("U",))
        blue = self.spell_source("Cancel", ("U",), self.p0)
        self.assertIn(spell, self.targetable_stack_spells(blue, self.p0))

    def test_controller_can_target_own_hexproof_spell_on_stack(self):
        spell = self.hexproof_spell("Sporeweb Weaver", self.p1, hexproof_from=("U",))
        own = self.spell_source("Bounce", ("U",), self.p1)
        self.assertIn(spell, self.targetable_stack_spells(own, self.p1))


class TestPlayerHexproof(HexproofCase):
    """CR 702.11c-d: a player with hexproof can't be the target of spells or abilities their
    opponents control ("from [quality]": of that quality). The static "You have hexproof"
    (Leyline of Sanctity) and the one-shot grant to you and your permanents (Veil of Summer) give
    it; every target surface that lists players refuses the player: a PLAYER-zone selector, the
    synthesized "target player"/"target opponent" slot, the players of "any target", and a
    trigger's player designation. Each test fails on the engine before the fix, which never read
    a player's hexproof."""

    YOU = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(Zone(ZoneKind.PLAYER, ControllerRef.YOU),))

    def leyline(self, seat):
        """A permanent with "You have hexproof." (templates_b16), controlled by ``seat``."""
        handle = self.world.add_card(card_id("Leyline", type_line="Enchantment"), seat, ZONE_BATTLEFIELD)
        hexproof = KeywordAbility(keyword=Keyword.HEXPROOF)
        self.attach(handle, [StaticAbility(effect=atom(Verb.GRANT_ABILITY, target=self.YOU, ability=hexproof))])
        return handle

    def veil(self, seat, colors=("B", "U")):
        """Veil of Summer's grant: you and the permanents you control, hexproof from the colours,
        until end of turn."""
        you_and_yours = Selector(
            QUnbounded(), SelectorMode.ALL, FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            zones=(BF_ANY, Zone(ZoneKind.PLAYER, ControllerRef.YOU)),
        )
        quality = FOr(tuple(FAtom(FAtomPred.COLOR_HAS, color=c) for c in colors))
        self.ex.apply_effect(
            atom(Verb.GRANT_ABILITY, target=you_and_yours, duration=DurationEot(),
                 ability=KeywordAbility(keyword=Keyword.HEXPROOF, params=(quality,))),
            source=self.banner,
            controller=seat,
        )
        self.settle()

    def player_slot(self, source, seat, ref=ControllerRef.TARGET_PLAYER):
        return set(player_target_slot(self.ex, seat, {ref}, source=source).candidates)

    def players_in(self, selector, source, controller):
        return set(legal_targets(self.world, self.ex, selector, source=source,
                                 controller=controller).candidates) & {self.p0, self.p1}

    def test_you_have_hexproof_refuses_the_opponents_target_player(self):
        self.leyline(self.p1)
        shock = self.spell_source("Shock", ("R",), self.p0)
        self.assertEqual(self.player_slot(shock, self.p0), {self.p0})  # not p1
        self.assertEqual(self.player_slot(shock, self.p0, ControllerRef.TARGET_OPPONENT), set())
        # p1 still targets themself (702.11c: "your opponents control").
        own = self.spell_source("Peer", ("B",), self.p1)
        self.assertEqual(self.player_slot(own, self.p1), {self.p0, self.p1})

    def test_a_player_zone_selector_and_any_target_leave_the_player_out(self):
        self.leyline(self.p1)
        shock = self.spell_source("Shock", ("R",), self.p0)
        players = Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(ANY_PLAYER,))
        self.assertEqual(self.players_in(players, shock, self.p0), {self.p0})
        any_target = Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(ANY_ANY,))
        slot = legal_targets(self.world, self.ex, any_target, source=shock, controller=self.p0)
        widened = _widen_any_target(self.ex, any_target, slot, shock, self.p0)
        self.assertNotIn(self.p1, widened.candidates)
        self.assertIn(self.p0, widened.candidates)

    def test_hexproof_from_blue_and_black_refuses_only_those_colours(self):
        bear = self.plain_creature("Bear", self.p1)  # a permanent p1 controls: hexproof too
        self.veil(self.p1)
        # CR 611.2c: the objects were fixed as the spell resolved; one entering later is not.
        late = self.plain_creature("Late Bear", self.p1)
        blue = self.spell_source("Opt", ("U",), self.p0)
        black = self.spell_source("Duress", ("B",), self.p0)
        red = self.spell_source("Shock", ("R",), self.p0)
        for source in (blue, black):
            self.assertEqual(self.player_slot(source, self.p0, ControllerRef.TARGET_OPPONENT), set())
            self.assertNotIn(bear, self.targetable_creatures(source, self.p0))
            self.assertIn(late, self.targetable_creatures(source, self.p0))
        self.assertEqual(self.player_slot(red, self.p0, ControllerRef.TARGET_OPPONENT), {self.p1})
        self.assertIn(bear, self.targetable_creatures(red, self.p0))

    def test_the_grant_ends_with_the_turn(self):
        self.veil(self.p1)
        black = self.spell_source("Duress", ("B",), self.p0)
        self.assertEqual(self.player_slot(black, self.p0, ControllerRef.TARGET_OPPONENT), set())
        self.ex.layers.sweep_at_eot()
        self.settle()
        self.assertEqual(self.player_slot(black, self.p0, ControllerRef.TARGET_OPPONENT), {self.p1})

    def test_a_trigger_targeting_an_opponent_with_hexproof_is_removed(self):
        # CR 603.3d: "target opponent loses 2 life" with the only opponent hexproof.
        self.leyline(self.p1)
        lose = atom(Verb.LOSE_LIFE, controller=ControllerRef.TARGET_OPPONENT, amount=QConst(2))
        drainer = self.world.add_card(card_id("Drainer", "1", "1"), self.p0, ZONE_HAND)
        self.attach(drainer, [etb_trigger(lose)])
        self.ex.execute(
            atom(Verb.MOVE_ZONE,
                 cards=Selector(QConst(1), SelectorMode.ALL, UNIV,
                                zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),)),
                 destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER)),
            source=drainer,
            controller=self.p0,
            bindings={"cards": drainer},
        )
        self.assertEqual(self.world.players[self.p1].life, 20)


ANY_PLAYER = Zone(ZoneKind.PLAYER, ControllerRef.ANY)
ANY_ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
