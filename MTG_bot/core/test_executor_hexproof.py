"""T4-P1c pins: CR 702.11 HEXPROOF targeting enforcement (gap L-4).

Pins the enforcement the six goldens (Sporeweb Weaver, Spined Megalodon,
Ranger's Guile, Garruk's Harbinger, Nine Lives, Heroic Intervention) have
waited for: a permanent with hexproof CAN'T be the target of spells or
abilities an OPPONENT controls — and every shape that must NOT be moved
stays put:

  * the controller's own spells still target their own hexproof creature
    (CR 702.11b's direction clause, read through the engine's opponent
    convention: a distinct seat);
  * "hexproof from {quality}" (Spined Megalodon: COLOR_HAS U param)
    vetoes ONLY sources matching the row's filter;
  * granted hexproof (Ranger's Guile's GRANT row) blocks while live, and
    a LOSE_ABILITY stops the block (the keyword name gate);
  * a hexproof creature's CONTROLLER is still a legal "any target"
    player (702.11 protects the object, not the player);
  * non-targeting sweepers (ALL-mode DESTROY) still hit — the mode gate
    means only SelectorMode.TARGET enumeration is filtered;
  * the keyword is zone-limited: a hexproof card in a graveyard is an
    ordinary target;
  * the STACK lane (fresh-eyes MAJOR, CR 702.11b): a creature SPELL on
    the stack keeps its QUALITY-conditioned hexproof — the binder's
    continuous lifecycle fires only on battlefield entry, so the rows
    are sourced from the compiled record, never collapsed to bare;
  * the cast lane (601.2c) refuses the off-population designation, the
    trigger ask vocabulary never SHOWS the hexproof creature (menu
    presents the truth, §10), and a legal target still lands.
"""

from __future__ import annotations

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    QConst,
    Selector,
    SelectorMode,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.executor.stack import cast, park
from MTG_bot.core.executor.query import legal_targets
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
        fresh-eyes stack rig — the folded ``cast`` helper resolves on the
        spot, so the standing-spell shape parks the card directly, exactly
        where CR 601.2h leaves it before any response): the compiled
        record is filed in the binder's ORACLE registry (what
        ``attach_pool`` does for hand cards — registered but NOT
        attached: the battlefield-only lifecycle never fired for this
        handle, which is precisely the hole the MAJOR was found in) and
        the printed identity seeds the zone-less HEXPROOF name."""
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
                Zone(ZoneKind.STACK, ControllerRef.ANY),
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
        any_target = Selector(QConst(1), SelectorMode.TARGET, UNIV, ANY_PLAYER)
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
                    Zone(ZoneKind.ANY, ControllerRef.ANY),
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
        any_creature = Selector(QConst(1), SelectorMode.TARGET, CREATURE, ANY_ANY)
        slot = legal_targets(
            self.world, self.ex, any_creature, source=bolt, controller=self.p0
        )
        self.assertIn(weaver, set(slot.candidates))

    def test_non_targeting_sweeper_still_destroys_hexproof(self):
        weaver = self.hexproof_creature("Sporeweb Weaver", self.p1)
        plain = self.plain_creature("Horned Bash", self.p1)
        sweep_all = Selector(QConst(99), SelectorMode.ALL, CREATURE, BF_ANY)
        self.ex.execute(
            atom(Verb.DESTROY, target=sweep_all),
            source=self.banner,
            controller=self.p0,
        )
        for handle in (weaver, plain):  # ALL-mode: no target, no veto (702.11)
            self.assertEqual(self.world.zone_of(handle).kind, ZONE_GRAVEYARD)


class TestHexproofLanes(HexproofCase):
    """The veto is one oracle consumed by EVERY target surface (T4 §10
    blindness audit): the cast validator, the trigger ask vocabulary."""

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
        self.assertNotIn(str(weaver), vocab)  # menu presents legality, §10
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
                    Zone(ZoneKind.HAND, ControllerRef.YOU),
                ),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER),
            ),
            source=handle,
            controller=self.p0,
            bindings={"cards": handle},
        )


class TestHexproofOnStack(HexproofCase):
    """Fresh-eyes MAJOR (2026-10-07): CR 702.11b covers the creature
    SPELL on the stack, but the binder's continuous lifecycle fires only
    on battlefield entry (stack.py gates both attach lanes on
    ``dest == ZONE_BATTLEFIELD``). The identity-seeded NAME gate still
    passed on the stack, so the empty live-row scan collapsed "hexproof
    from blue" into a BARE veto — an opponent's red Counterspell was
    wrongly refused against Sporeweb Weaver's spell (both quality cards
    ARE in the M21 pool: Weaver blue, Garruk's Harbinger black). The fix
    sources the stack rows from the compiled record: quality stays
    quality, bare stays total."""

    def test_stack_hexproof_from_blue_still_lets_red_source_target(self):
        spell = self.hexproof_spell("Sporeweb Weaver", self.p1, hexproof_from=("U",))
        self.assertEqual(self.world.zone_of(spell).kind, ZONE_STACK)
        red = self.spell_source("Shock", ("R",), self.p0)
        self.assertIn(spell, self.targetable_stack_spells(red, self.p0))

    def test_stack_hexproof_from_blue_vetoes_blue_source(self):
        spell = self.hexproof_spell("Sporeweb Weaver", self.p1, hexproof_from=("U",))
        blue = self.spell_source("Cancel", ("U",), self.p0)
        self.assertNotIn(spell, self.targetable_stack_spells(blue, self.p0))

    def test_stack_bare_hexproof_vetoes_every_opponent_source(self):
        spell = self.hexproof_spell("Nine Lives", self.p1)  # bare printed
        for colors in (("U",), ("R",)):
            src = self.spell_source(f"React {colors}", colors, self.p0)
            self.assertNotIn(spell, self.targetable_stack_spells(src, self.p0))

    def test_controller_can_target_own_hexproof_spell_on_stack(self):
        spell = self.hexproof_spell("Sporeweb Weaver", self.p1, hexproof_from=("U",))
        # Own BLUE source: the color row WOULD veto an opponent, but the
        # 702.11b direction clause frees the controller's own targeting.
        own = self.spell_source("Bounce", ("U",), self.p1)
        self.assertIn(spell, self.targetable_stack_spells(own, self.p1))

    def test_stack_without_registered_record_reads_bare(self):
        # Defensive edge: an identity-seeded name with NO compiled record
        # cannot occur through spell_castable in the real pipeline, but if
        # one ever reaches the stack the read is BARE (over-block), never
        # a silent hexproof-blind target.
        spell = self.hexproof_spell(
            "Phantom Idol", self.p1, hexproof_from=("U",), register=False
        )
        red = self.spell_source("Shock", ("R",), self.p0)
        self.assertNotIn(spell, self.targetable_stack_spells(red, self.p0))


ANY_PLAYER = Zone(ZoneKind.PLAYER, ControllerRef.ANY)
ANY_ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
