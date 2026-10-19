"""geyser-FIX batch — "any target" hidden-zone leak pins (R17-2, 2026-10-05).

RED-FIRST file (KNOWLEDGE/2026-10-05/05 §0.1, blueprint step 1): printed
"any target" (CR 109.5 / CR 115.1d) designates a CREATURE, a PLANESWALKER
or a PLAYER — never a card hiding in an opponent's hand or library. The
pre-fix compiler emitted the idiom as ``Selector(TARGET, FAnd(),
Zone(ANY, ANY))`` and the query lane enumerated every card in every zone,
so the offered decision surface contained opponent-hidden handles (D10 /
E3: 116 hidden candidates over 24 probe games at 4dbe864).

These pins compile the REAL M21 records (pool + registry — the same route
the goldens take) and pin the candidate set of the Geyser slot against a
fully populated 2-player world. PRE-fix they fail exactly where the leak
is (red as intended at HEAD); POST-fix the candidate set is battlefield
creatures + planeswalkers + both players, EXACTLY — and Shock's
player-reach (the idiom's player side, delivered by the engine's
widening, not by the filter) stays green end to end.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    Atom,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    FOr,
    QConst,
    Selector,
    SelectorMode,
    SpellAbility,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.query import spell_target_slots
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import card_id, reset_oracle_ids

_M21 = Path(__file__).resolve().parents[2] / "MTG_bot" / "data" / "M21.json"

_POOL = None
_REGISTRY = None


def compiled(name: str):
    """Compile one real M21 card once per process (pool + full registry —
    the golden-producing route, so the pin witnesses the TEMPLATE, not a
    hand-baked IR)."""
    global _POOL, _REGISTRY
    if _POOL is None:
        _POOL = ingest_pool(_M21)
        _REGISTRY = build_full_registry()
    assert _REGISTRY is not None
    for raw in _POOL.values():
        if raw.identity.name == name:
            return compile_card(raw, _REGISTRY).card
    raise AssertionError(f"{name!r} not in the M21 pool")


def _pt(q) -> str | None:
    """P/T for a CardIdentity (printed constant only — the tested cards
    are instants with no P/T; the helper exists for the identity shape)."""
    if q is None:
        return None
    value = getattr(q, "value", None)
    return None if value is None else str(value)


class GeyserCase(unittest.TestCase):
    """p0/p1 world; p1 hides a populated hand + library and fields a
    creature and a planeswalker; p0 fields one creature and holds the
    tested spell."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0 = self.world.player_order[0]
        self.p1 = self.world.player_order[1]
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)
        # opponent hidden zones FULLY populated — the leak witnesses
        self.opp_hand = [
            self.world.add_card(card_id(f"Clutch{i}"), self.p1, ZONE_HAND)
            for i in range(2)
        ]
        self.opp_lib = [
            self.world.add_card(card_id(f"Book{i}"), self.p1, ZONE_LIBRARY)
            for i in range(2)
        ]
        # my hand also carries a straggler (a hand card is never a target)
        self.my_extra_hand = self.world.add_card(
            card_id("Straggler"), self.p0, ZONE_HAND
        )
        # visible population
        self.opp_creature = self.world.add_card(
            card_id("Rival", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )
        self.opp_walker = self.world.add_card(
            card_id("Planes", type_line="Planeswalker"),
            self.p1,
            ZONE_BATTLEFIELD,
        )
        self.my_creature = self.world.add_card(
            card_id("Ally", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.hidden = set(self.opp_hand) | set(self.opp_lib) | {self.my_extra_hand}

    def give_spell(self, name: str, seat=None):
        """World card in ``seat``'s hand carrying the REAL compiled record."""
        seat = seat if seat is not None else self.p0
        rec = compiled(name)
        handle = self.world.add_card(
            CardIdentity(
                oracle_id=rec.oracle_id,
                name=rec.name,
                type_line=rec.type_line,
                power=_pt(rec.power),
                toughness=_pt(rec.toughness),
                cmc=rec.mana_value,
                colors=rec.colors,
            ),
            seat,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        return handle, rec

    def slot_of(self, handle, rec):
        node = next(
            a
            for a in self.ex.binder.handle_record[handle].abilities
            if isinstance(a, SpellAbility) and a.effect is not None
        )
        slots = spell_target_slots(self.ex, node, spell_handle=handle, seat=self.p0)
        # single TARGET slot, no synthesized TARGET_PLAYER twin (the idiom
        # carries no TARGET_PLAYER read — dual-slot synthesis must NOT fire)
        self.assertEqual(len(slots), 1, "exactly one designation slot")
        self.assertFalse(slots[0].synthetic)
        return slots[0]

    def assert_clean_shape(self, candidates):
        got = set(candidates)
        self.assertFalse(
            got & self.hidden,
            f"hidden-zone handles in the offer surface: {got & self.hidden}",
        )
        expected = {self.p0, self.p1, self.opp_creature, self.opp_walker}
        expected.add(self.my_creature)
        self.assertEqual(got, expected)


class TestGeyserHiddenZoneLeak(GeyserCase):
    def test_compiled_geyser_selector_is_the_battlefield_idiom(self):
        """Compiler lane: the printed idiom compiles to the RESTRICTED
        shape — FOr(TYPE Creature / TYPE Planeswalker) over
        Zone(BATTLEFIELD, ANY). The player side is NOT in the filter: it
        joins via the engine's idiom widening (CR 109.5)."""
        rec = compiled("Volcanic Geyser")
        node = next(a for a in rec.abilities if isinstance(a, SpellAbility))
        assert isinstance(node.effect, Atom)
        sel = node.effect.args.get("target")
        assert isinstance(sel, Selector)
        self.assertIs(sel.mode, SelectorMode.TARGET)
        self.assertEqual(sel.zones[0], Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY))
        self.assertIsInstance(sel.filter, FOr)
        idiom_filter = sel.filter
        assert isinstance(idiom_filter, FOr)
        kids = sorted(
            str(k.string_value)
            for k in idiom_filter.children
            if isinstance(k, FAtom)
            and k.pred is FAtomPred.TYPE_EQ
            and k.string_value is not None
        )
        self.assertEqual(kids, ["Creature", "Planeswalker", "Player"])
        self.assertNotIsInstance(sel.filter, FAnd)

    def test_geyser_candidates_exclude_opponent_hidden_zones(self):
        """Query lane (the D10 / E3 leak): the Geyser slot offers ONLY
        battlefield creatures + planeswalkers + both players — no hand,
        no library, not even the spell card in the caster's own hand."""
        handle, rec = self.give_spell("Volcanic Geyser")
        slot = self.slot_of(handle, rec)
        self.assert_clean_shape(slot.candidates)

    def test_shock_reaches_players_and_not_hidden_cards(self):
        """Shock-family guard: the same restricted idiom must STILL name
        both players (the widening survives the type filter) while the
        hidden population stays out."""
        handle, rec = self.give_spell("Shock")
        slot = self.slot_of(handle, rec)
        self.assertIn(self.p1, slot.candidates)
        self.assertIn(self.p0, slot.candidates)
        self.assert_clean_shape(slot.candidates)

    def test_shock_cast_designates_a_player_end_to_end(self):
        """Cast lane: a real compiled Shock paid for and designated at the
        OPPONENT seat resolves through the widened population and lands
        the printed 2 damage (validation oracle + resolution legality
        both accept the player designation)."""
        handle, _rec = self.give_spell("Shock")
        self.world.players[self.p0].mana_pool["R"] = 1
        frame = cast(self.ex, self.p0, handle, targets=(self.p1,))
        self.assertEqual(frame.declared_targets, (self.p1,))
        self.assertEqual(self.world.players[self.p1].life, 18)

    def test_geyser_cast_designates_a_creature(self):
        """Cast lane, card side: Geyser X=2 designated at the opponent's
        2/2 puts it exactly to lethal damage (the restricted candidate
        population feeds the full cast pipeline unchanged)."""
        handle, _rec = self.give_spell("Volcanic Geyser")
        self.world.players[self.p0].mana_pool["R"] = 4  # {X}{R}{R}, X=2
        frame = cast(self.ex, self.p0, handle, targets=(self.opp_creature,), x=2)
        self.assertEqual(frame.declared_targets, (self.opp_creature,))
        # 2 marked damage on a 2/2 — the corpse rides to the graveyard and
        # the damage marks vanish with it (harness convention); the
        # lethality proof IS the graveyard lane.
        self.assertEqual(self.world.zone_of(self.opp_creature).kind, "graveyard")


class TestTwinPredicatesAgree(unittest.TestCase):
    """§8.3 identity: the query offer lane (query._player_widening_applies)
    and the selectors runtime legality lane (_is_any_universal) must be
    the SAME opinion on the same shapes — if they diverge, a designation
    the query offered gets dropped at resolution (or vice versa)."""

    def test_offer_and_resolution_legality_are_one_opinion(self):
        self._shapes()

    def _shapes(self):
        from MTG_bot.core.ability_tree import FAnd, FAtom, FOr
        from MTG_bot.core.executor.query import (
            _is_any_target_idiom as q_idiom,
        )
        from MTG_bot.core.executor.query import _player_widening_applies
        from MTG_bot.core.executor.selectors import (
            _is_any_target_idiom as s_idiom,
        )
        from MTG_bot.core.executor.selectors import _is_any_universal

        bf = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
        any_zone = Zone(ZoneKind.ANY, ControllerRef.ANY)
        hand = Zone(ZoneKind.HAND, ControllerRef.ANY)
        idiom = FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Player"),
            )
        )
        # CR 115.1d twin text — TWO branches, no Player atom: the
        # Finishing Blow regression witness, must NEVER widen
        c_or_pw = FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            )
        )
        lopsided = FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
            )
        )
        shapes = {
            "geyser idiom over battlefield": Selector(
                count=QConst(1), mode=SelectorMode.TARGET, filter=idiom, zones=(bf,)
            ),
            "legacy universal over ANY zone": Selector(
                count=QConst(1),
                mode=SelectorMode.TARGET,
                filter=FAnd(()),
                zones=(any_zone,),
            ),
            "idiom but NOT battlefield-only": Selector(
                count=QConst(1), mode=SelectorMode.TARGET, filter=idiom, zones=(hand,)
            ),
            "target creature or planeswalker (B5a)": Selector(
                count=QConst(1), mode=SelectorMode.TARGET, filter=c_or_pw, zones=(bf,)
            ),
            "non-idiom FOr": Selector(
                count=QConst(1), mode=SelectorMode.TARGET, filter=lopsided, zones=(bf,)
            ),
            "plain universal filter, no ANY zone": Selector(
                count=QConst(1), mode=SelectorMode.TARGET, filter=FAnd(()), zones=(bf,)
            ),
        }
        for label, sel in shapes.items():
            self.assertIs(
                q_idiom(sel.filter),
                s_idiom(sel.filter),
                f"idiom twins diverge on {label}",
            )
            self.assertIs(
                _player_widening_applies(sel),
                _is_any_universal(sel),
                f"widening twins diverge on {label}",
            )
        # and the opinions themselves, pinned (not just equal twins)
        self.assertTrue(
            _player_widening_applies(shapes["geyser idiom over battlefield"])
        )
        self.assertTrue(
            _player_widening_applies(shapes["legacy universal over ANY zone"])
        )
        self.assertFalse(
            _player_widening_applies(shapes["idiom but NOT battlefield-only"])
        )
        self.assertFalse(
            _player_widening_applies(shapes["target creature or planeswalker (B5a)"])
        )
        self.assertFalse(_player_widening_applies(shapes["non-idiom FOr"]))
        self.assertFalse(
            _player_widening_applies(shapes["plain universal filter, no ANY zone"])
        )


class TestKeeperClassesStayBroad(GeyserCase):
    """R17-2 classification tail: the sweep's KEEP classes must not move.
    Cancel prints "target spell" (public STACK) — its slot keeps the
    stack population and the universal player-widening that the STACK
    zone never had to begin with (no player seats on a spell target)."""

    def test_cancel_stack_slot_unchanged(self):
        handle, _rec = self.give_spell("Cancel")
        node = next(
            a
            for a in self.ex.binder.handle_record[handle].abilities
            if isinstance(a, SpellAbility) and a.effect is not None
        )
        assert isinstance(node.effect, Atom)
        sel = node.effect.args.get("target")
        assert isinstance(sel, Selector)
        self.assertIs(sel.zones[0].kind, ZoneKind.STACK)


if __name__ == "__main__":
    unittest.main()
