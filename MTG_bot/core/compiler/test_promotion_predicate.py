"""The structural pick-ask promotion rule, censused over M21.

Pins the whole-M21 contract of ``_is_liftable_pick``:

* every entity CHOOSE surface of the pool falls in exactly one bucket of
  the predicate's decision order: cost > referent > self-designation >
  count!=1 > liftable core;
* every core surface with an answerable lane lands on the asking ONE_OF
  channel; the gap-blocked surfaces (PICK_ASK_FORCE_SILENT, gap ledger
  L-27..L-29) stay on the silent CHOOSE lane, never a phantom ask;
* nothing outside the core changes mode (the search-pick flip and
  Cultivate-style ONE_OFs are identical in both compilations);
* every promoted ask's menu is decidable at the controller seat the ask
  fires at (opponent and bound-player menus may not lift).

The numbers are M21's; the rule, not a registration list, promotes new cards.
"""

from __future__ import annotations

import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

import MTG_bot.core.compiler.compiler as comp
from MTG_bot.core.ability_tree import (
    ControllerRef,
    Cost,
    FAnd,
    Selector,
    SelectorMode,
    QConst,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

# M21's CHOOSE surfaces per bucket of the predicate's decision order (base tree).
TOTAL_SURFACES = 144
CORE_LIFTABLE = 21
SELF_DESIGNATION = 50
ANAPHORIC_REFERENT = 35
COST_VICTIM = 25
COUNT_NOT_ONE = 13

# (card, verb) rows the predicate matches but the encoder keeps silent —
# must stay in lockstep with compiler.PICK_ASK_FORCE_SILENT (L-27..L-29).
GAP_BLOCKED_EXPECT = {
    ("Goremand", "SACRIFICE"),
    ("Run Afoul", "SACRIFICE"),
    ("Liliana's Steward", "MOVE_ZONE"),
    ("Liliana, Waker of the Dead", "MOVE_ZONE"),
    ("Keral Keep Disciples", "DEAL_DAMAGE"),
    ("Runed Halo", "GRANT_ABILITY"),
    ("Furious Rise", "MOVE_ZONE"),
    ("Radha, Heart of Keld", "CAST"),
}


def _walk(obj, in_cost: bool, verb: str | None):
    """Yield (nearest_atom_verb, in_cost, Selector) for every Selector in
    an ability tree, tracking the cost subtree and the enclosing Atom's verb
    (the FORCE_* override key)."""
    if isinstance(obj, Selector):
        yield verb, in_cost, obj
        return
    if isinstance(obj, tuple):
        for item in obj:
            yield from _walk(item, in_cost, verb)
        return
    if not is_dataclass(obj) or isinstance(obj, type):
        return
    own_verb = getattr(obj, "verb", None)
    verb = own_verb.name if own_verb is not None else verb
    in_cost = in_cost or isinstance(obj, Cost)
    for f in fields(obj):
        value = getattr(obj, f.name, None)
        if value is None or isinstance(value, (str, bytes, int, float, bool)):
            continue
        yield from _walk(value, in_cost, verb)


def _classify(selector: Selector, in_cost: bool) -> str:
    """The predicate's own decision order — a total function on surfaces."""
    if in_cost:
        return "cost"
    if selector.referent is not None:
        return "referent"
    if comp._filter_carries_is_source(selector.filter):
        return "selfref"
    if not (isinstance(selector.count, QConst) and selector.count.value == 1):
        return "count"
    return "core"


# --- controller-seat tripwire (gap ledger L-27) ---
# The ONE_OF ask channel answers only at the effect controller's seat, so a
# promoted selector's menu must be answerable there: ControllerRef.YOU (the
# controller's own zones) and ControllerRef.ANY (widened, includes the
# controller) pass; a menu pinned to OPPONENT, ALL_OPPONENTS or the bound
# TARGET_PLAYER (Liliana's Steward's hand) cannot. The check is grammatical
# only: L-27 rows whose menu is on the controller's side but whose decider is
# not (Goremand's battlefield) stay pinned via PICK_ASK_FORCE_SILENT.
_MENU_SEATS_AT_ACTIVE = (ControllerRef.YOU, ControllerRef.ANY)


def _menu_decidable_at_active_seat(selector: Selector) -> bool:
    """Grammar-only seat check on a promoted ask site (no executor run)."""
    return all(
        zone.controller in _MENU_SEATS_AT_ACTIVE
        for zone in selector.zones
    )


class PromotionPredicateCensus(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        registry = build_full_registry()
        pool = ingest_pool(Path("MTG_bot/data/M21.json"))
        # Base = the predicate declines every surface and the overrides are
        # empty, so nothing is promoted. Live = the shipped rule.
        saved = comp._is_liftable_pick
        saved_ask = comp.PICK_ASK_FORCE_ASK
        saved_silent = comp.PICK_ASK_FORCE_SILENT
        try:
            comp._is_liftable_pick = lambda node, in_cost: False
            comp.PICK_ASK_FORCE_ASK = frozenset()
            comp.PICK_ASK_FORCE_SILENT = frozenset()
            cls.base = {
                raw.identity.name: compile_card(raw, registry).card
                for raw in pool.values()
            }
        finally:
            comp._is_liftable_pick = saved
            comp.PICK_ASK_FORCE_ASK = saved_ask
            comp.PICK_ASK_FORCE_SILENT = saved_silent
        cls.live = {
            raw.identity.name: compile_card(raw, registry).card for raw in pool.values()
        }
        # Enumerate CHOOSE surfaces from the BASE tree; the predicate's
        # buckets partition them.
        cls.surfaces: dict[str, list[tuple[str, str]]] = {
            "cost": [],
            "referent": [],
            "selfref": [],
            "count": [],
            "core": [],
        }
        for name, card in cls.base.items():
            for ab in card.abilities:
                for verb, in_cost, sel in _walk(ab, False, None):
                    if sel.mode is not SelectorMode.CHOOSE:
                        continue
                    bucket = _classify(sel, in_cost)
                    cls.surfaces[bucket].append((name, str(verb)))

    def test_partition_counts_are_the_enumeration(self):
        self.assertEqual(
            {
                "cost": len(self.surfaces["cost"]),
                "referent": len(self.surfaces["referent"]),
                "selfref": len(self.surfaces["selfref"]),
                "count": len(self.surfaces["count"]),
                "core": len(self.surfaces["core"]),
            },
            {
                "cost": COST_VICTIM,
                "referent": ANAPHORIC_REFERENT,
                "selfref": SELF_DESIGNATION,
                "count": COUNT_NOT_ONE,
                "core": CORE_LIFTABLE,
            },
        )
        self.assertEqual(sum(len(v) for v in self.surfaces.values()), TOTAL_SURFACES)

    def test_core_surfaces_ask_except_the_ledger_rows(self):
        expected = [s for s in self.surfaces["core"] if s not in GAP_BLOCKED_EXPECT]
        self.assertEqual(
            len(GAP_BLOCKED_EXPECT), len(self.surfaces["core"]) - len(expected)
        )
        self.assertEqual(
            {(n, v) for n, v in self.surfaces["core"] if v and (n, v) not in expected}
            - {tuple(r) for r in comp.PICK_ASK_FORCE_SILENT},
            set(),
        )
        promoted = 0
        for name in {n for n, _ in expected}:
            base = repr(self.base[name].abilities).count("SelectorMode.ONE_OF")
            live = repr(self.live[name].abilities).count("SelectorMode.ONE_OF")
            self.assertGreater(live, base, f"{name}: core surface did not lift")
            promoted += live - base
        self.assertEqual(promoted, len(expected))

    def test_gap_blocked_surfaces_stay_choose_not_phantom(self):
        for name, _verb in GAP_BLOCKED_EXPECT:
            base = repr(self.base[name].abilities)
            live = repr(self.live[name].abilities)
            self.assertEqual(
                base.count("SelectorMode.ONE_OF"),
                live.count("SelectorMode.ONE_OF"),
                f"{name}: FORCE_SILENT surface was lifted (phantom ask)",
            )
            self.assertEqual(
                base.count("SelectorMode.CHOOSE"), live.count("SelectorMode.CHOOSE")
            )

    def test_no_promotion_leaks_outside_the_core(self):
        # Every non-core surface keeps CHOOSE in the live tree, and the
        # only ONE_OF deltas pool-wide are the core-minus-rows lifts.
        non_core = [
            s
            for bucket, rows in self.surfaces.items()
            if bucket != "core"
            for s in rows
        ]
        self.assertTrue(non_core)
        for name in {n for n, _ in non_core} | {n for n, _ in self.surfaces["core"]}:
            self.assertLessEqual(
                repr(self.base[name].abilities).count("SelectorMode.ONE_OF"),
                repr(self.live[name].abilities).count("SelectorMode.ONE_OF"),
                f"{name}: a ONE_OF surface vanished",
            )
        total_delta = sum(
            repr(self.live[n].abilities).count("SelectorMode.ONE_OF")
            - repr(self.base[n].abilities).count("SelectorMode.ONE_OF")
            for n in self.base
        )
        self.assertEqual(total_delta, CORE_LIFTABLE - len(GAP_BLOCKED_EXPECT))

    def _lifted_ask_selectors(self) -> list[tuple[str, str, Selector]]:
        """(card, verb, live Selector) for every surface the pass promoted from
        CHOOSE to the asking ONE_OF: parallel walks over the structurally
        identical base and live trees."""
        lifted: list[tuple[str, str, Selector]] = []
        for name in self.base:
            for ab_base, ab_live in zip(
                self.base[name].abilities, self.live[name].abilities
            ):
                base_w, live_w = (
                    list(_walk(ab_base, False, None)),
                    list(_walk(ab_live, False, None)),
                )
                self.assertEqual(
                    len(base_w), len(live_w), f"{name}: promotion changed tree shape"
                )
                for (verb_b, _c_b, sel_b), (verb_l, _c_l, sel_l) in zip(base_w, live_w):
                    if (
                        sel_b.mode is SelectorMode.CHOOSE
                        and sel_l.mode is SelectorMode.ONE_OF
                    ):
                        lifted.append((name, str(verb_l), sel_l))
        return lifted

    def test_promoted_asks_are_decidable_at_the_active_seat(self):
        """L-27 tripwire: every promoted selector's menu is answerable at the
        controller seat the ONE_OF channel fires at."""
        lifted = self._lifted_ask_selectors()
        self.assertEqual(len(lifted), CORE_LIFTABLE - len(GAP_BLOCKED_EXPECT))
        for name, verb, sel in lifted:
            self.assertTrue(
                _menu_decidable_at_active_seat(sel),
                f"L-27 class: ({name}, {verb}) promoted to an ask whose menu "
                f"sits on {sel.zones[0].controller.name} seats — no candidate is "
                "answerable at the controller seat this ask fires at",
            )
        # Self-check: the scan refuses the menu of a real L-27 row (had the
        # predicate promoted it, the loop above would fail).
        caught = {
            (name, verb)
            for name, verb in GAP_BLOCKED_EXPECT
            for ab in self.base[name].abilities
            for verb_w, _ic, sel in _walk(ab, False, None)
            if sel.mode is SelectorMode.CHOOSE
            and str(verb_w) == verb
            and not _menu_decidable_at_active_seat(sel)
        }
        self.assertIn(("Liliana's Steward", "MOVE_ZONE"), caught)
        # Self-check: an opponent-battlefield menu does not pass the scan.
        hostile = Selector(
            count=QConst(1),
            mode=SelectorMode.ONE_OF,
            filter=FAnd(()),
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ALL_OPPONENTS),),
        )
        self.assertFalse(_menu_decidable_at_active_seat(hostile))


if __name__ == "__main__":
    unittest.main()
