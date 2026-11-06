"""``Selector.zones`` is ONE set field: the executor lanes that key on a zone
read a SINGLETON or extract the matched zone, never ∃-over-the-set.

The lanes, as the test names label them:
  L1  a search's library-TOP window (selectors: matched-zone extraction);
  L3  the player-side designation (``selectors.role_handles``);
  L4  the graveyard-sweep clause (``selectors.graveyard_sweep_shape``);
  L5  the blind-draw guard (a SINGLETON library);
  L6  the hand window of a self-discard cost
      (``legality._ability_discards_its_source``).

Each lane test evaluates (a) the PRODUCTION predicate on the REAL selector
from the committed goldens, and (b) a deliberately-naive ∃-variant shown to
evaluate DIFFERENTLY on exactly that selector. Executor probes run golden
IR bytes through the real executor and observe zone contents, never just
tree shape.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    CostDiscard,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
    fingerprint,
    from_dict,
    to_dict,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import (
    _ability_discards_its_source,
    ability_playable,
)
from MTG_bot.core.executor.query import legal_targets
from MTG_bot.core.executor.selectors import graveyard_sweep_shape
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    ZONE_STACK,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    UNIV,
    card_id,
    record_of,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_legality import LegalityCase, ability, cost
from MTG_bot.core.test_executor_r21a import R21aCase

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "M21"
_CACHE: dict[str, dict] = {}


def golden(name: str) -> dict:
    """The COMMITTED golden bytes for a card name."""
    if not _CACHE:
        for path in _GOLDEN_DIR.glob("*.json"):
            d = json.loads(path.read_text(encoding="utf-8"))
            _CACHE[d["name"]] = d
    return _CACHE[name]


# ------------------------------------------------------------------ zones
GV_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
LIB_YOU = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
PL_ANY = Zone(ZoneKind.PLAYER, ControllerRef.ANY)
ANY_ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)
HAND_YOU = Zone(ZoneKind.HAND, ControllerRef.YOU)

# The L1 cards: a named search over your graveyard AND library.
L1_CARDS = (
    "Garruk's Warsteed",
    "Liliana's Scorn",
    "Sanctum of All",
    "Teferi's Wavecaster",
    "Basri's Aegis",
    "Chandra's Firemaw",
)
# The L5 probe trio (a blind top-n draw would over-draw for them).
L5_TRIO = ("Chandra's Firemaw", "Teferi's Wavecaster", "Garruk's Warsteed")


def search_atom_dict(card: str) -> dict:
    """The first SEARCH atom dict of a battery golden, found by walking the tree (its path
    differs per card: some tutors sit inside a sorcery's effect)."""

    def walk(node):
        if isinstance(node, dict):
            if node.get("tag") == "Atom" and node["verb"]["name"] == "SEARCH":
                return node
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = walk(value)
                if found is not None:
                    return found
        return None

    atom = walk(golden(card)["abilities"])
    assert atom is not None, f"{card}: no SEARCH atom"
    return atom


def search_steps(card: str) -> list:
    """The steps of the Seq whose first step is the card's SEARCH atom (the named
    tutors: [SEARCH, REVEAL, SHUFFLE] inside the may)."""
    target = search_atom_dict(card)

    def walk(node):
        if isinstance(node, dict):
            if node.get("tag") == "Seq" and node["steps"] and node["steps"][0] == target:
                return node["steps"]
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = walk(value)
                if found is not None:
                    return found
        return None

    steps = walk(golden(card)["abilities"])
    assert steps is not None, f"{card}: no Seq starting with the SEARCH"
    return steps


def search_selector_dict(card: str) -> dict:
    """The ONE_OF search selector dict out of a battery golden."""
    return dict(search_atom_dict(card)["args"]["pairs"])["cards"]


# ---------------------------------------------------------------- schema
class TestFoldedSchemaLaws(unittest.TestCase):
    """The construction + serialization law of ``Selector.zones``."""

    def _sel(self, zones, mode=SelectorMode.CHOOSE, count=2, referent=None):
        return Selector(QConst(count), mode, UNIV, zones=zones, referent=referent)

    def test_zones_sorted_deduped_by_canonical_json(self):
        s = self._sel((LIB_YOU, GV_YOU, GV_YOU, LIB_YOU))
        self.assertEqual(s.zones, (GV_YOU, LIB_YOU))  # deduped + canonical order

    def test_empty_zones_raise(self):
        with self.assertRaises(ValueError):
            self._sel(())

    def test_c2_referent_forces_any_any(self):
        # A referent selector has ONE neutral zone.
        with self.assertRaises(ValueError):
            self._sel((GV_YOU,), mode=SelectorMode.CHOOSE, count=1, referent="result")
        s = self._sel((ANY_ANY,), mode=SelectorMode.CHOOSE, count=1, referent="result")
        self.assertEqual(s.zones, (ANY_ANY,))

    def test_to_dict_zone_key_never_emitted(self):
        d = to_dict(self._sel((GV_YOU, LIB_YOU)))
        self.assertIn("zones", d)
        self.assertNotIn("zone", d)
        # zones always serializes, even a single zone.
        s1 = to_dict(self._sel((GV_YOU,), count=1))
        self.assertIn("zones", s1)
        self.assertNotIn("zone", s1)

    def test_from_dict_stale_zone_key_fails_loud_naming_r0(self):
        d = to_dict(self._sel((GV_YOU,)))
        d["zone"] = d["zones"][0]  # stale bytes: a scalar zone beside the set
        with self.assertRaises(ValueError) as cm:
            from_dict("Selector", d)
        self.assertIn("R0 zone-fold", str(cm.exception))

    def test_roundtrip_two_zones(self):
        s = self._sel((GV_YOU, LIB_YOU))
        self.assertEqual(from_dict("Selector", to_dict(s)), s)

    def test_fingerprint_sensitive_to_zone_membership(self):
        a = self._sel((GV_YOU,), count=1)
        b = self._sel((GV_YOU, LIB_YOU), count=1)
        self.assertNotEqual(fingerprint(a), fingerprint(b))


class TestGoldenBytesFolded(unittest.TestCase):
    """Byte law over the WHOLE baked golden store: no Selector dict in
    any M21 golden carries a scalar 'zone' key, and every zones list is
    exactly canonical-ordered (the schema law visible on disk)."""

    def test_all_goldens_folded_and_canonical(self):
        checked = 0

        def walk(x):
            nonlocal checked
            if isinstance(x, dict):
                if x.get("tag") == "Selector":
                    self.assertNotIn("zone", x)
                    zs = x["zones"]
                    self.assertTrue(zs)
                    # canonical_json's exact key: same dumps parameters.
                    key = lambda z: json.dumps(
                        z, sort_keys=True, separators=(",", ":")
                    )
                    self.assertEqual(zs, sorted(zs, key=key))
                    checked += 1
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        files = sorted(_GOLDEN_DIR.glob("*.json"))
        self.assertEqual(len(files), 305)
        for p in files:
            walk(json.loads(p.read_text(encoding="utf-8")))
        self.assertGreater(checked, 200)


# ----------------------------------------------------- lane divergences
class TestTwinLaneDivergence(unittest.TestCase):
    """Production keyed-lane predicate vs the naive-∃ variant, on the
    REAL selectors from the committed goldens. The pair must disagree:
    the disagreement is what an ∃ reading of the set would break.
    """

    def test_l1_window_gate_closed_on_twins(self):
        for card in L1_CARDS:
            with self.subTest(card):
                sel = from_dict("Selector", search_selector_dict(card))
                # canonical order pin: GRAVEYARD < LIBRARY, controller YOU.
                self.assertEqual(sel.zones, (GV_YOU, LIB_YOU))
                # PRODUCTION L1 gate (selectors.py matched-zone extraction):
                # opens iff a MATCHED LIBRARY+TOP zone is in the set.
                matched = next(
                    (
                        z
                        for z in sel.zones
                        if z.kind is ZoneKind.LIBRARY and z.position is ZonePosition.TOP
                    ),
                    None,
                )
                self.assertIsNone(matched)  # window CLOSED (correct)
                # naive-∃ variant:
                naive = any(z.kind is ZoneKind.LIBRARY for z in sel.zones)
                self.assertTrue(naive)  # ∃ would FALSE-OPEN the lane

    def test_l3_player_side_singleton_vs_exists(self):
        for card in ("Chandra's Magmutt", "Leafkin Avenger"):
            with self.subTest(card):
                # Find the DEAL_DAMAGE ability carrying the TARGET role.
                sel = None
                for ab in golden(card)["abilities"]:
                    eff = ab.get("effect") or {}
                    if eff.get("tag") != "Atom":
                        continue
                    for role, val in eff.get("args", {}).get("pairs", []):
                        if role == "target" and val.get("tag") == "Selector":
                            sel = from_dict("Selector", val)
                self.assertIsNotNone(sel)
                # canonical order pin: BATTLEFIELD < PLAYER.
                self.assertEqual(sel.zones, (BF_ANY, PL_ANY))
                # PRODUCTION L3 PURE predicate (selectors.py role_handles):
                pure = len(sel.zones) == 1 and sel.zones[0].kind is ZoneKind.PLAYER
                self.assertFalse(pure)  # designation STANDS (correct)
                naive = any(z.kind is ZoneKind.PLAYER for z in sel.zones)
                self.assertTrue(naive)  # ∃-PLAYER would re-point the designation

    def test_unsubstantiate_order_control(self):
        # Content-only control: no lane keys on STACK ∪ BATTLEFIELD;
        # canonical order BATTLEFIELD < STACK.
        c = dict(golden("Unsubstantiate")["abilities"][0]["effect"]["args"]["pairs"])[
            "cards"
        ]
        sel = from_dict("Selector", c)
        self.assertEqual(sel.zones, (BF_ANY, Zone(ZoneKind.STACK, ControllerRef.ANY)))

    def test_l6_waker_cost_discard_singleton(self):
        ab = golden("Waker of Waves")["abilities"][1]
        parts = {p["tag"]: p for p in ab["cost"]["parts"]}
        target = from_dict("Selector", parts["CostDiscard"]["target"])
        self.assertEqual(target.zones, (HAND_YOU,))  # a singleton
        # The PRODUCTION legality predicate on the singleton:
        discards = _ability_discards_its_source(from_dict("ActivatedAbility", ab))
        self.assertTrue(discards)  # the hand window opens
        # naive-∃ twin: a HAND ∪ GRAVEYARD discard target.
        twin = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(GV_YOU, HAND_YOU))
        naive = any(z.kind is ZoneKind.HAND for z in twin.zones)
        self.assertTrue(naive)
        self.assertFalse(  # production: zones[0] is NOT hand -> closed
            len(twin.zones) == 1 and twin.zones[0].kind is ZoneKind.HAND
        )

    def test_necromentia_choose_selector_not_sweep_shaped(self):
        # L4: the 3-zone CHOOSE set carries the graveyard-of-the-targeted-
        # player clause, but the PRODUCTION sweep predicate requires ALL
        # mode + MOVE_ZONE + EXILE dest — the zone clause alone must NOT
        # route it into the sweep lane.
        ab = golden("Necromentia")["abilities"][0]

        choose_sel = None

        def find(x):
            nonlocal choose_sel
            if isinstance(x, dict):
                if x.get("tag") == "Selector" and x["mode"]["name"] == "CHOOSE":
                    kinds = [z["kind"]["name"] for z in x["zones"]]
                    if kinds == ["GRAVEYARD", "HAND", "LIBRARY"]:
                        choose_sel = from_dict("Selector", x)
                for v in x.values():
                    find(v)
            elif isinstance(x, list):
                for v in x:
                    find(v)

        find(ab)
        self.assertIsNotNone(choose_sel)
        # canonical order pin: GRAVEYARD < HAND < LIBRARY, one controller
        # ("target opponent" compiles to TARGET_OPPONENT).
        tp = ControllerRef.TARGET_OPPONENT
        self.assertEqual(
            choose_sel.zones,
            (
                Zone(ZoneKind.GRAVEYARD, tp),
                Zone(ZoneKind.HAND, tp),
                Zone(ZoneKind.LIBRARY, tp),
            ),
        )
        exile_tp = Zone(ZoneKind.EXILE, tp)
        self.assertFalse(
            graveyard_sweep_shape(choose_sel, Verb.MOVE_ZONE, exile_tp)
        )  # the mode gate holds


class TestL4UnitSynthetic(unittest.TestCase):
    """No pool card tells ∃ from a single zone on this lane, so the
    falsifier is the UNIT-LEVEL synthetic IR test against the PRODUCTION
    predicate.
    """

    def test_split_zones_do_not_satisfy_the_sweep_clause(self):
        tp = ControllerRef.TARGET_PLAYER
        exile_tp = Zone(ZoneKind.EXILE, tp)
        split = Selector(
            QConst(1),
            SelectorMode.ALL,
            UNIV,
            zones=(Zone(ZoneKind.HAND, tp), GV_YOU),
        )
        # PRODUCTION: needs ONE zone carrying BOTH conjuncts.
        self.assertFalse(graveyard_sweep_shape(split, Verb.MOVE_ZONE, exile_tp))
        # naive ∃-kind ∧ ∃-controller reads the two zones as one clause —
        # the silent-semantics hole the pin closes:
        naive = any(z.kind is ZoneKind.GRAVEYARD for z in split.zones) and any(
            z.controller is tp for z in split.zones
        )
        self.assertTrue(naive)
        # Positive control: the merged single-zone shape still sweeps.
        merged = Selector(
            QConst(1),
            SelectorMode.ALL,
            UNIV,
            zones=(_GV_TP := Zone(ZoneKind.GRAVEYARD, tp),),
        )
        self.assertTrue(graveyard_sweep_shape(merged, Verb.MOVE_ZONE, exile_tp))


# --------------------------------------------------- executor-observed
class LibraryProbe(unittest.TestCase):
    """Shared rig for the twin-search probes: p0 holds the named card in
    library and (a separate copy) in the graveyard; decoys in library."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)

    def seed(self, seld: dict):
        f = seld["filter"]
        pred, sv = f["pred"]["name"], f.get("string_value")
        if pred == "NAME_EQ":
            ident = card_id(sv, type_line="Legendary Creature — Human")
        elif pred == "TYPE_EQ":
            ident = card_id(f"Shrine {sv}", type_line=f"Land — {sv}")
        else:  # pragma: no cover - battery shape guard
            self.fail(f"unexpected battery filter pred {pred}")
        lib_a = self.world.add_card(ident, self.p0, ZONE_LIBRARY)
        lib_b = self.world.add_card(card_id("Decoy B"), self.p0, ZONE_LIBRARY)
        lib_c = self.world.add_card(ident, self.p0, ZONE_LIBRARY)  # the twin
        gv = self.world.add_card(ident, self.p0, ZONE_GRAVEYARD)
        return lib_a, lib_b, lib_c, gv

    def run_search_step(self, card: str, pick: str):
        atom0 = from_dict("Atom", search_atom_dict(card))
        return self.ex.execute(
            atom0,
            source=self.p0,
            controller=self.p0,
            decisions=(pick,),
        )


class TestL1ExecutorObserved(LibraryProbe):
    """The ONE_OF ask on the two-zone selector enumerates BOTH zones: the
    graveyard copy is an IN-VOCABULARY answer and lands in the printed
    destination. A naive-∃ window lane would scope the ask to the library
    TOP window and reject that answer as out of vocabulary."""

    def test_graveyard_answer_resolves_for_every_l1_card(self):
        for card in L1_CARDS:
            with self.subTest(card):
                self.setUp()
                _, _, _, gv = self.seed(search_selector_dict(card))
                lib_before = list(
                    self.world.players[self.p0].zone(ZONE_LIBRARY).entries
                )
                dest = ZONE_HAND if card != "Sanctum of All" else ZONE_BATTLEFIELD
                self.run_search_step(card, str(gv))
                self.assertIn(gv, self.world.players[self.p0].zone(dest).entries)
                # The window lane never fired: library is byte-intact.
                self.assertEqual(
                    self.world.players[self.p0].zone(ZONE_LIBRARY).entries,
                    lib_before,
                )

    def test_library_copy_stays_in_library(self):
        # The ask took the GRAVEYARD copy specifically; the LIBRARY twin
        # was never partitioned out or auto-drawn.
        card = "Basri's Aegis"
        lib_a, lib_b, lib_c, gv = self.seed(search_selector_dict(card))
        self.run_search_step(card, str(gv))
        self.assertEqual(
            self.world.players[self.p0].zone(ZONE_LIBRARY).entries,
            [lib_a, lib_b, lib_c],
        )  # nothing left the library: no partition, no draw
        self.assertIn(lib_c, self.world.players[self.p0].zone(ZONE_LIBRARY).entries)


class TestL5NoBlindDraw(LibraryProbe):
    """Running the search and its tail (every step but SHUFFLE) for the
    trio must move ONLY the answered card; the library is never touched by
    a blind top-n DRAW (the L5 draw guard is SINGLETON-LIBRARY and stays
    closed on the two-zone selector)."""

    def test_tail_never_draws_for_the_trio(self):
        for card in L5_TRIO:
            with self.subTest(card):
                self.setUp()
                _, _, _, gv = self.seed(search_selector_dict(card))
                steps = search_steps(card)
                lib_before = list(
                    self.world.players[self.p0].zone(ZONE_LIBRARY).entries
                )
                self.run_search_step(card, str(gv))
                # the tail: every step after the SEARCH except the SHUFFLE
                tail = [
                    s
                    for s in steps[1:]
                    if not (s.get("tag") == "Atom" and s["verb"]["name"] == "SHUFFLE")
                ]
                for s in tail:
                    node = (
                        from_dict("Atom", s)
                        if s.get("tag") == "Atom"
                        else from_dict("Effect", s)
                    )
                    self.ex.execute(
                        node,
                        source=self.p0,
                        controller=self.p0,
                    )
                self.assertEqual(
                    self.world.players[self.p0].zone(ZONE_LIBRARY).entries,
                    lib_before,
                )  # zero cards drawn
                self.assertEqual(
                    list(self.world.players[self.p0].zone(ZONE_HAND).entries),
                    [gv],
                )


class TestNamedSearchLeavesItsSourceAlone(LibraryProbe):
    """The named tutor ("search your library and/or graveyard for a card named <planeswalker>,
    reveal it, and put it into your hand") has no step that moves the source: a tutor creature
    put on top of its library in response (Griptide) stays there as its own trigger resolves.
    Every non-SHUFFLE step runs here with the card itself on top of the library: it stays
    there, only the named card moves."""

    CARDS = (
        "Garruk's Warsteed",
        "Teferi's Wavecaster",
        "Chandra's Firemaw",
        "Basri's Aegis",
        "Liliana's Scorn",
    )

    def test_the_source_on_top_of_the_library_stays_there(self):
        for card in self.CARDS:
            with self.subTest(card):
                self.setUp()
                _, _, _, gv = self.seed(search_selector_dict(card))
                src = self.world.add_card(card_id(card), self.p0, ZONE_LIBRARY)  # the top
                for s in search_steps(card):
                    if s.get("tag") == "Atom" and s["verb"]["name"] == "SHUFFLE":
                        continue
                    self.ex.execute(
                        from_dict("Atom", s),
                        source=src,
                        controller=self.p0,
                        decisions=(str(gv),),
                    )
                library = self.world.players[self.p0].zone(ZONE_LIBRARY).entries
                self.assertEqual(library[-1], src)
                self.assertEqual(list(self.world.players[self.p0].zone(ZONE_HAND).entries), [gv])


class TestL3WalkerDesignationStands(R21aCase):
    """REAL Magmutt bytes through the executor: the designation the
    player made (a planeswalker card) must STAND — the PLAYER∪BATTLEFIELD
    TARGET selector is NOT player-side (L3 SINGLETON), so the damage lands
    on the walker, not re-pointed at the player."""

    def test_golden_magmutt_atom_honours_walker_designation(self):
        pw = self._walker(self.p1, "4")
        atom = from_dict("Atom", golden("Chandra's Magmutt")["abilities"][0]["effect"])
        self.ex.execute(
            atom,
            source=self.alpha,
            controller=self.p0,
            bindings={"target": pw},
        )
        self.assertEqual(self.world.players[self.p1].life, 20)  # player untouched
        self.assertEqual(dict(self.world.cards[pw].counters), {"LOYALTY": 3})


class TestUnsubstantiateAskBothZones(unittest.TestCase):
    """Content control, executor-observed: the counter-target ask
    enumerates BOTH STACK and BATTLEFIELD candidates (a STACK spell and
    a battlefield creature are both legal)."""

    def test_legal_targets_enumerates_stack_and_battlefield(self):
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=3)
        p0, _p1 = world.player_order[0], world.player_order[1]
        ex = Executor(world)
        ex.begin_turn(p0)
        creature_on_bf = world.add_card(
            card_id("Beta Creature", "1", "1"), p0, ZONE_BATTLEFIELD
        )
        spell_on_stack = world.add_card(
            card_id("Gamma Spell", type_line="Instant"), p0, ZONE_HAND
        )
        from MTG_bot.core.executor.stack import park

        park(ex, p0, spell_on_stack)
        self.assertEqual(world.zone_of(spell_on_stack).kind, ZONE_STACK)
        sel = from_dict(
            "Selector",
            dict(golden("Unsubstantiate")["abilities"][0]["effect"]["args"]["pairs"])[
                "cards"
            ],
        )
        slot = legal_targets(world, ex, sel, source=p0, controller=p0)
        self.assertEqual(set(slot.candidates), {creature_on_bf, spell_on_stack})


class TestL6WakerWindowExecutor(LegalityCase):
    """The L6 hand window: the printed singleton-HAND self-discard cost
    keeps the hand window open (legal); a HAND ∪ GRAVEYARD twin target
    must NOT open it (production singleton vs naive-∃)."""

    OID_OK = "0cafe000-1111-2222-3333-444444444444"
    OID_TWIN = "0badc0de-1111-2222-3333-444444444444"

    def put_in_hand(self, oid: str, abil, name: str):
        h = self.world.add_card(card_id(name, "2", "2", oid=oid), self.p0, ZONE_HAND)
        self.ex.binder.records[oid] = record_of([abil], name=name, oid=oid)
        return h

    def test_singleton_hand_cost_window_open(self):
        abil = ability(
            cost(
                CostDiscard(
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(FAtomPred.IS_SOURCE),
                        zones=(HAND_YOU,),
                    )
                )
            )
        )
        h = self.put_in_hand(self.OID_OK, abil, "R0 Waker")
        self.assertIsNone(ability_playable(self.world, self.ex, h, 0, seat=self.p0))

    def test_twin_zone_cost_window_stays_closed(self):
        twin = Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            FAtom(FAtomPred.IS_SOURCE),
            zones=(GV_YOU, HAND_YOU),
        )
        abil = ability(cost(CostDiscard(twin)))
        self.assertFalse(_ability_discards_its_source(abil))  # production
        self.assertTrue(
            any(z.kind is ZoneKind.HAND for z in twin.zones)
        )  # naive-∃ would open the window
        h = self.put_in_hand(self.OID_TWIN, abil, "R0 Twin")
        self.assertEqual(
            ability_playable(self.world, self.ex, h, 0, seat=self.p0),
            f"window:not_on_battlefield:{h}",
        )


class TestCompilerRebuildCarriesZones(unittest.TestCase):
    """The compiler's ``_fold_meta_filter`` rebuild must carry the FULL
    zone set AND the referent (a positional rebuild would drop zones
    silently)."""

    def test_rebuild_preserves_zones_and_referent(self):
        from MTG_bot.core.compiler.compiler import _fold_meta_filter

        meta = FAtom(FAtomPred.IS_SOURCE)
        two_zone = Selector(
            QConst(1), SelectorMode.TARGET, UNIV, zones=(GV_YOU, LIB_YOU)
        )
        effect = Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(pairs=(("target", two_zone), ("amount", QConst(1)))),
        )
        out = _fold_meta_filter(effect, meta)
        rebuilt = dict(out.args.pairs)["target"]
        self.assertEqual(rebuilt.zones, (GV_YOU, LIB_YOU))
        self.assertIsNone(rebuilt.referent)

        # The referent pass-through (zones=value.zones, referent=value
        # .referent) is latent: a referent selector must be CHOOSE +
        # QConst(1) + the neutral zone, so a TARGET selector never carries
        # one — pinned as such.
        with self.assertRaises(ValueError):
            Selector(
                QConst(1),
                SelectorMode.TARGET,
                UNIV,
                zones=(ANY_ANY,),
                referent="target",
            )
        ref_free = from_dict("Selector", to_dict(two_zone))
        self.assertEqual(ref_free.zones, (GV_YOU, LIB_YOU))  # roundtrip intact
        self.assertIsNone(ref_free.referent)


class TestSameSeedDeterminism(LibraryProbe):
    """With same-seed fresh worlds the designated-order lane must replay
    byte-identical: the canonical zone order is deterministic."""

    def _final_state(self, card: str):
        w = GameWorld(num_players=2, start_life=20, master_seed=42)
        p0 = w.player_order[0]
        ex = Executor(w)
        ident = card_id(
            "Basri, Devoted Paladin", type_line="Legendary Creature — Human"
        )
        w.add_card(ident, p0, ZONE_LIBRARY)
        w.add_card(card_id("Decoy B"), p0, ZONE_LIBRARY)
        w.add_card(ident, p0, ZONE_LIBRARY)
        gv = w.add_card(ident, p0, ZONE_GRAVEYARD)
        ex.execute(
            from_dict("Atom", search_atom_dict(card)),
            source=p0,
            controller=p0,
            decisions=(str(gv),),
        )
        snap = {
            z: [str(h) for h in w.players[p0].zone(z).entries]
            for z in (ZONE_LIBRARY, ZONE_HAND, ZONE_GRAVEYARD, ZONE_BATTLEFIELD)
        }
        return json.dumps(snap, sort_keys=True)

    def test_two_runs_identical(self):
        a = self._final_state("Basri's Aegis")
        b = self._final_state("Basri's Aegis")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
