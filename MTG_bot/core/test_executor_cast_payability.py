"""125 — the effect-CAST offer gate prices the cast (/114 for the effect lane).

Shadow-grid crash (M21 eval, seed 777003, frozen 99c5edc): Conspicuous
Snoop's "you may cast the top card…" may-offer was ACTIONABLE while the
designated card ({3}{R}) could not be paid from {R:3}; the model answered
fire, the deterministic CHOOSE designation named that card, and
``stack.cast_card`` raised LOUD at its payment invariant (kept loud —
last-line rule). The offer layer (``query.optional_offer``'s r23a CAST
gate) read castability STRUCTURE only (does a SpellAbility carrier
exist), never mana.

Fix law (CR 601.2b-e + option-legality /10): an option is offered only
when the cast it hands the engine is CURRENTLY PAYABLE, priced by the
SAME ``build_payment_plan`` the engine folds (one source of truth), the
atom's own ``cost`` role respected (EMPTY Cost = the corpus cost-waiver
idiom, CR 498.2 — always payable; a real Cost REPLACES the printed cost,
which is what cast_card does). A CHOOSE designation is priced through the
stand-in's OWN slice (sorted candidates[:count]) — query/runtime
identity, §8.3; a TARGET/ONE_OF menu keeps the any-payable branch (r18a:
never erase a legal choice the seat could designate and afford).
"""

import dataclasses
import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QConst,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    SpellAbility,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.query import (
    MAY_VOCAB,
    activation_target_slots,
    optional_offer,
)
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    LIB_YOU,
    UNIV,
    card_id,
    record_of,
    referent_sel,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_query import atom


def _cost(generic: int = 0, color: str | None = None, n: int = 1) -> Cost:
    parts = []
    if generic:
        parts.append(CostManaGeneric(amount=QConst(generic)))
    if color:
        parts.append(CostManaColor(color=color, amount=QConst(n)))
    return Cost(parts=tuple(parts))


class CastPayabilityCase(unittest.TestCase):
    """The Snoop-shape gate: optional Verb.CAST over the library."""

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=125)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.src = self.world.add_card(
            card_id("Snoop Host", type_line="Artifact"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def spell_in_library(self, name: str, cost: Cost):
        """A library card with a compiled spell record costing ``cost``."""
        card = self.world.add_card(
            card_id(name, type_line="Instant"), self.p0, ZONE_LIBRARY
        )
        oid = self.world.cards[card].identity.oracle_id
        rec = dataclasses.replace(
            record_of(
                [SpellAbility(kind=SpellKind.INSTANT, effect=None)],
                name=name,
                oid=oid,
            ),
            mana_cost=cost,
        )
        self.ex.binder.records[oid] = rec
        return card

    def offer(
        self,
        count: Quantity | None = None,
        mode=SelectorMode.CHOOSE,
        cost=None,
        sel=None,
    ):
        roles = {
            "source": sel
            or Selector(QConst(1) if count is None else count, mode, UNIV, zones=(LIB_YOU,))
        }
        if cost is not None:
            roles["cost"] = cost
        may = OptionalEffect(inner=atom(Verb.CAST, **roles))
        return optional_offer(self.ex, may, source=self.src, controller=self.p0)

    # ---------------------------------------------------------- the crash
    def test_unaffordable_designation_is_not_offered(self):
        # THE seed-777003 repro: {3}{R} spell, {R:3} pool — cost:mana_generic
        # 2<3 at stack.cast_card. The offer must narrow to skip (CR 117.3:
        # an impossible action has no branch), never phantom-fire.
        self.spell_in_library("Battle-Rattle Shaman", _cost(3, "R"))
        self.world.players[self.p0].mana_pool = {"R": 3}
        self.assertEqual(self.offer(), MAY_VOCAB[1:])

    def test_affordable_designation_is_offered(self):
        self.spell_in_library("Battle-Rattle Shaman", _cost(3, "R"))
        self.world.players[self.p0].mana_pool = {"R": 4}
        self.assertEqual(self.offer(), MAY_VOCAB)

    # ------------------------------------------------------- mixed matrix
    def test_mixed_matrix_count_one_prices_the_stand_in_pick(self):
        # CHOOSE(1) casts the sorted-FIRST candidate (the deterministic
        # stand-in, resolve_selector): when THAT card is unaffordable the
        # fire branch raises at runtime, so the offer must narrow EVEN
        # THOUGH the other card is payable — the gate prices the
        # stand-in's own slice, not the population (query/runtime
        # identity, §8.3).
        costly = self.spell_in_library("Costly", _cost(5))
        cheap = self.spell_in_library("Cheap", _cost(1))
        assert min([costly, cheap]) == costly  # stand-in casts costly
        # Pool pays the SECOND card only: the stand-in would still pick
        # the costly first card -> impossible fire, skip-only.
        self.world.players[self.p0].mana_pool = {"C": 1}
        self.assertEqual(self.offer(), MAY_VOCAB[1:])
        # Pool pays the first candidate -> the branch is live again.
        self.world.players[self.p0].mana_pool = {"C": 5}
        self.assertEqual(self.offer(), MAY_VOCAB)

    def test_mixed_matrix_unbounded_choose_prices_ALL_designees(self):
        # QUnbounded CHOOSE casts EVERY carrier: one unaffordable card in
        # the population makes the whole fire branch raise mid-cast, so
        # the offer narrows until BOTH are payable.
        self.spell_in_library("Cheap", _cost(1))
        self.spell_in_library("Costly", _cost(5))
        self.world.players[self.p0].mana_pool = {"C": 1}
        self.assertEqual(self.offer(count=QUnbounded()), MAY_VOCAB[1:])
        self.world.players[self.p0].mana_pool = {"C": 6}
        self.assertEqual(self.offer(count=QUnbounded()), MAY_VOCAB)

    def test_mixed_matrix_one_of_menu_keeps_the_affordable_branch(self):
        # ONE_OF designates ONE card the seat picks (ask menu): one
        # payable candidate makes the branch actionable (r18a). B2 (gate
        # round — /10 menu-visibility): the ASK VOCABULARY is clamped to
        # exactly the payable carriers — the seat is never presented the
        # unaffordable card, because choosing it was a raise-trap at
        # stack.cast_card (the amended-to-trap is still a trap).
        self.spell_in_library("Cheap", _cost(1))
        self.spell_in_library("Costly", _cost(5))
        self.world.players[self.p0].mana_pool = {"C": 1}
        self.assertEqual(
            self.offer(mode=SelectorMode.ONE_OF),
            MAY_VOCAB,
        )
        self.world.players[self.p0].mana_pool = {}
        self.assertEqual(self.offer(mode=SelectorMode.ONE_OF), MAY_VOCAB[1:])

    def test_one_of_ask_vocabulary_excludes_the_unpayable_card(self):
        # B2 clamp asserted at the ASK itself: names chosen so the COSTLY
        # card sorts FIRST (the pre-clamp vocabulary led with the trap).
        # decisions = ("fire", "0"): the ONE_OF ask answers index 0 of its
        # CLAMPED vocabulary — the payable card — and the unpayable card
        # stays put; before the clamp, index 0 named the unpayable card
        # and the resolution raised.
        costly = self.spell_in_library("Arda Feat", _cost(5))
        bolt = self.spell_in_library("Bolt", _cost(1))
        assert min([costly, bolt]) == costly  # the trap order (pre-clamp)
        self.world.players[self.p0].mana_pool = {"C": 1}
        may = OptionalEffect(
            inner=atom(
                Verb.CAST,
                source=Selector(QConst(1), SelectorMode.ONE_OF, UNIV, zones=(LIB_YOU,)),
            )
        )
        self.ex.apply_effect(
            may, source=self.src, controller=self.p0, decisions=("fire", "0")
        )
        self.assertEqual(self.world.zone_of(bolt).kind, "graveyard")
        self.assertEqual(self.world.zone_of(costly).kind, "library")
        self.assertEqual(self.world.players[self.p0].mana_pool, {})

    def test_unbounded_mixed_carrier_hand_casts_the_spell_and_skips_the_land(
        self,
    ):
        # B1 (gate round, Catalyst shape): CHOOSE-∞ over a population the
        # compiled filter lets LANDS into. The offered set clamps to spell
        # carriers (a land is not a spell): the offer is live, the fire
        # casts the spell, the land stays — never the old whole-set raise.
        land = self.world.add_card(
            card_id("Island", type_line="Land"), self.p0, ZONE_LIBRARY
        )
        bolt = self.spell_in_library("Bolt", _cost(1))
        self.world.players[self.p0].mana_pool = {"C": 9}
        offer = self.offer(count=QUnbounded())
        self.assertEqual(offer, MAY_VOCAB)
        may = OptionalEffect(
            inner=atom(
                Verb.CAST,
                source=Selector(QUnbounded(), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,)),
            )
        )
        self.ex.apply_effect(
            may, source=self.src, controller=self.p0, decisions=("fire",)
        )
        self.assertEqual(self.world.zone_of(bolt).kind, "graveyard")
        self.assertEqual(self.world.zone_of(land).kind, "library")

    def test_zero_carrier_filter_registers_the_gap_loudly(self):
        # B3 (gate round): Radha's shape — the selector's filter admits
        # ZERO spell designees (PLAY_LAND miscompiled to a CAST filtered
        # TYPE_EQ Land). The skip is honest (a land is never a castable
        # designee) but NEVER silent: the mis-shapen atom goes into
        # executor.unresolved_effects (/112 ledger pattern: deduped,
        # counted, queryable) as the COMPILER-lane handoff.
        self.world.add_card(card_id("Island", type_line="Land"), self.p0, ZONE_LIBRARY)
        self.world.add_card(
            card_id("Mountain", type_line="Land"), self.p0, ZONE_LIBRARY
        )
        land_only = FAnd((FAtom(FAtomPred.TYPE_EQ, string_value="Land"),))
        may = OptionalEffect(
            inner=atom(
                Verb.CAST,
                source=Selector(QConst(1), SelectorMode.CHOOSE, land_only, zones=(LIB_YOU,)),
            )
        )
        self.assertEqual(
            optional_offer(self.ex, may, source=self.src, controller=self.p0),
            MAY_VOCAB[1:],
        )
        optional_offer(self.ex, may, source=self.src, controller=self.p0)  # dedupe
        flags = [f for f in self.ex.unresolved_effects if f.startswith("cast-gap")]
        self.assertEqual(len(flags), 1)
        self.assertIn("0 spell designees", flags[0])
        self.assertEqual(self.ex.unresolved_effect_counts[flags[0]], 2)

    def test_mixed_population_unbounded_registers_the_filter_omission(self):
        # B1 handoff #2: Catalyst/HoH filter-omission (FAnd(()) admits
        # lands into a CAST population). The clamp makes play safe — and
        # the atom-shape gap lands in the same queryable ledger.
        self.world.add_card(card_id("Island", type_line="Land"), self.p0, ZONE_LIBRARY)
        self.spell_in_library("Bolt", _cost(1))
        self.world.players[self.p0].mana_pool = {"C": 9}
        self.assertEqual(self.offer(count=QUnbounded()), MAY_VOCAB)
        flags = [f for f in self.ex.unresolved_effects if f.startswith("cast-gap")]
        self.assertEqual(len(flags), 1)
        self.assertIn("non-spell designees", flags[0])

    def test_face_cast_gap_survives_the_clamp(self):
        # /115 regression pin (this round's own regression): the
        # BackFace-only compiled record is NOT a clamp member. Two lanes,
        # both LOUD: the may-offer for a face-cast-absent-only population
        # is skip-only and REGISTERS the compiler's front-text gap (a
        # fire that could only ever guard-skip is a phantom option); the
        # raw designation lane must preserve the designee so cast_card's
        # TYPED refusal still raises — the guarded live lane skips AND
        # LEDGERS it (pinned byte-identical in test_executor_dfc_cast.py).
        # Either way the shape is never a silent clamp-drop.
        from MTG_bot.core.ability_tree import BackFace
        from MTG_bot.core.executor.stack import FaceCastAbsentError

        rec = record_of(
            [BackFace(face_name="Beyeen Coast", abilities=())], name="DFCFixture"
        )
        dfc = self.world.add_card(
            card_id("DFCFixture", type_line="Creature // Land", oid=rec.oracle_id),
            self.p0,
            ZONE_LIBRARY,
        )
        self.ex.attach_card(dfc, rec)
        self.world.players[self.p0].mana_pool = {}
        cast_atom = atom(
            Verb.CAST,
            source=Selector(QUnbounded(), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,)),
            cost=Cost(()),
        )
        may = OptionalEffect(inner=cast_atom)
        self.assertEqual(
            optional_offer(self.ex, may, source=self.src, controller=self.p0),
            MAY_VOCAB[1:],
        )
        flags = [f for f in self.ex.unresolved_effects if f.startswith("cast-gap")]
        self.assertEqual(len(flags), 1)
        self.assertIn("face-cast-absent only", flags[0])
        # Raw lane (bypass): the clamp preserves the designee, so the
        # typed refusal still reaches cast_card. Empty decision pool =>
        # the unbounded CHOOSE stand-in designes the full clamped set.
        with self.assertRaises(FaceCastAbsentError):
            self.ex.apply_effect(cast_atom, source=self.src, controller=self.p0)
        self.assertEqual(self.world.zone_of(dfc).kind, "library")  # nothing cast

    def test_bound_designation_with_non_carrier_narrows_the_offer(self):
        # 12a SOURCE bindings cast ALL bound cards — an explicit
        # designation is never re-picked, so a bound non-carrier makes
        # the fire an impossible offer: skip (the runtime's per-card
        # raise stays the last line if the lane is force-fed).
        land = self.world.add_card(
            card_id("Island", type_line="Land"), self.p0, ZONE_LIBRARY
        )
        bolt = self.spell_in_library("Bolt", _cost(1))
        self.world.players[self.p0].mana_pool = {"C": 9}
        may = OptionalEffect(
            inner=atom(
                Verb.CAST,
                source=Selector(QUnbounded(), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,)),
            )
        )
        self.assertEqual(
            optional_offer(
                self.ex,
                may,
                source=self.src,
                controller=self.p0,
                bindings={"source": [land, bolt]},
            ),
            MAY_VOCAB[1:],
        )
        self.assertEqual(
            optional_offer(
                self.ex,
                may,
                source=self.src,
                controller=self.p0,
                bindings={"source": [bolt]},
            ),
            MAY_VOCAB,
        )

    def test_target_cast_slot_candidates_are_clamped(self):
        # B2 TARGET lane (Catalyst GRAVEYARD shape): the designation slot
        # a spell/activation announcement must offer ranges over PAYABLE
        # carriers only — a land or a cost-short card in the menu is the
        # raise-trap the gate round flagged (CR 601.2b: designations are
        # legal-at-ask).
        grave = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
        g = self.world.add_card(
            card_id("Bolt", type_line="Instant"), self.p0, ZONE_GRAVEYARD
        )
        land = self.world.add_card(
            card_id("Island", type_line="Land"), self.p0, ZONE_GRAVEYARD
        )
        costly = self.spell_in_library("Costly", _cost(5))
        self.world.move_to_zone(costly, self.p0, ZONE_GRAVEYARD)
        self.world.players[self.p0].mana_pool = {"C": 1}
        # Bolt needs a compiled record too (library helper cannot be reused):
        oid = self.world.cards[g].identity.oracle_id
        self.ex.binder.records[oid] = dataclasses.replace(
            record_of(
                [SpellAbility(kind=SpellKind.INSTANT, effect=None)],
                name="Bolt",
                oid=oid,
            ),
            mana_cost=_cost(1),
        )
        effect = atom(
            Verb.CAST,
            source=Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(grave,)),
        )
        slots = activation_target_slots(self.ex, effect, source=self.src, seat=self.p0)
        self.assertEqual(len(slots), 1)
        cands = set(slots[0].candidates)
        self.assertEqual(cands, {g})
        self.assertNotIn(land, cands)  # not a spell: no cast designation
        self.assertNotIn(costly, cands)  # unpayable: no cast designation

    # ----------------------------------------------------------- riders
    def test_land_first_choose_one_is_designee_impossible(self):
        # The /125 amendment direction on the r23a pin: a spell carrier
        # EXISTS, but the sorted-FIRST designee is a land — the runtime
        # CHOOSE(1) stand-in names the land and _v_cast raises 'no
        # SpellAbility' — an impossible fire the offer must never make,
        # regardless of mana.
        land = self.world.add_card(
            card_id("Island", type_line="Land"), self.p0, ZONE_LIBRARY
        )
        bolt = self.spell_in_library("Lightning Bolt", _cost(1))
        assert min([land, bolt]) == land  # the stand-in names the land
        self.world.players[self.p0].mana_pool = {"C": 9}
        self.assertEqual(self.offer(), MAY_VOCAB[1:])

    def test_empty_cost_waiver_is_mana_blind(self):
        # CR 498.2 idiom: an EMPTY Cost cost-role IS the "without paying
        # its mana cost" rider — always payable, never gated by the pool.
        self.spell_in_library("Free Cast", _cost(7, "B", 7))
        self.world.players[self.p0].mana_pool = {}
        self.assertEqual(self.offer(cost=_cost()), MAY_VOCAB)

    def test_real_cost_role_replaces_the_printed_cost(self):
        # cast_card folds the ROLE as the whole cost, not printed+role:
        # printed {1} with role {5} is NOT payable at {C:1} (the engine
        # would owe {5}); printed {5} with role {1} IS payable at {C:1}.
        self.spell_in_library("Cheap Print", _cost(1))
        self.world.players[self.p0].mana_pool = {"C": 1}
        self.assertEqual(self.offer(cost=_cost(5)), MAY_VOCAB[1:])
        self.world2 = GameWorld(num_players=2, start_life=20, master_seed=126)
        p0 = self.world2.player_order[0]
        host = self.world2.add_card(
            card_id("Snoop Host", type_line="Artifact"), p0, ZONE_BATTLEFIELD
        )
        ex2 = Executor(self.world2)
        card = self.world2.add_card(
            card_id("Costly Print", type_line="Instant"), p0, ZONE_LIBRARY
        )
        oid = self.world2.cards[card].identity.oracle_id
        ex2.binder.records[oid] = dataclasses.replace(
            record_of(
                [SpellAbility(kind=SpellKind.INSTANT, effect=None)], name="X", oid=oid
            ),
            mana_cost=_cost(5),
        )
        self.world2.players[p0].mana_pool = {"C": 1}
        may = OptionalEffect(
            inner=atom(
                Verb.CAST,
                source=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,)),
                cost=_cost(1),
            )
        )
        self.assertEqual(
            optional_offer(ex2, may, source=host, controller=p0), MAY_VOCAB
        )

    def test_referent_source_stays_ungated(self):
        # Produced mid-effect (the result register): nothing enumerable
        # pre-execution — r18a rule, byte-unchanged by this fix.
        may = OptionalEffect(inner=atom(Verb.CAST, source=referent_sel("result", UNIV)))
        self.assertEqual(
            optional_offer(self.ex, may, source=self.src, controller=self.p0),
            MAY_VOCAB,
        )

    # -------------------------------------------------------- end-to-end
    def test_affordable_fire_casts_the_card(self):
        # The gate must not eat the legal branch: with a payable pool the
        # fire answer casts the designated card (ex-library, no raise).
        card = self.spell_in_library("Payable", _cost(1))
        self.world.players[self.p0].mana_pool = {"C": 1}
        may = OptionalEffect(
            inner=atom(
                Verb.CAST,
                source=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,)),
            )
        )
        self.ex.apply_effect(
            may, source=self.src, controller=self.p0, decisions=("fire",)
        )
        self.assertEqual(
            self.world.zone_of(card).kind,
            "graveyard",
            "payable fire must resolve the instant (to the graveyard)",
        )
        self.assertEqual(self.world.players[self.p0].mana_pool, {})  # paid in full

    def test_unaffordable_fire_path_is_unreachable_via_offer(self):
        # Full-lane honesty: with the narrowed offer the engine's own
        # dispatch (decisions pool cannot answer 'fire' against a
        # skip-only vocab) never reaches _v_cast — apply_effect skips.
        card = self.spell_in_library("Unpayable", _cost(3, "R"))
        self.world.players[self.p0].mana_pool = {"R": 3}
        may = OptionalEffect(
            inner=atom(
                Verb.CAST,
                source=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,)),
            )
        )
        self.ex.apply_effect(
            may, source=self.src, controller=self.p0, decisions=("fire",)
        )
        # 'fire' is NOT in the narrowed vocab: the pool word stays
        # unconsumed, the site auto-answers skip, the card stays put.
        self.assertEqual(self.world.zone_of(card).kind, "library")

    # ------------------------------------------------- F2 positional law
    # (re-gate round 3, /125): the finite-CHOOSE CAST slice designates the
    # sorted-FIRST candidates of the RAW population (query.py's finite
    # gate branch, verbs.py's "deterministic first-n stand-in"). The
    # runtime must REFUSE a failing head — no cast, a ledger row — and
    # NEVER pay down onto the next payable spell.
    def _mand_cast(self, mode=SelectorMode.CHOOSE, sel=None):
        self.ex.apply_effect(
            atom(
                Verb.CAST,
                source=sel or Selector(QConst(1), mode, UNIV, zones=(LIB_YOU,)),
            ),
            source=self.src,
            controller=self.p0,
        )

    def test_f2_mandatory_head_unpayable_refuses_never_repicks(self):
        # The p1_probe scenario as a pin: Colossus ({5}{R}) sorts FIRST,
        # the pool pays only Bolt. Round 2's population clamp re-picked
        # and CAST Bolt (positional-law violation); F2 refuses the whole
        # effect instead — nothing moves, nothing is paid, the ledger
        # names the refused head.
        colossus = self.spell_in_library("Colossus", _cost(5, "R"))
        bolt = self.spell_in_library("Bolt", _cost(1, "R"))
        self.assertEqual(min([colossus, bolt]), colossus)  # the head
        self.world.players[self.p0].mana_pool = {"C": 1, "R": 1}
        self._mand_cast()
        self.assertEqual(self.world.zone_of(colossus).kind, "library")
        self.assertEqual(
            self.world.zone_of(bolt).kind,
            "library",
            "Bolt was never positionally designated — casting it is a "
            "re-pick the positional law forbids",
        )
        self.assertEqual(self.world.players[self.p0].mana_pool, {"C": 1, "R": 1})
        flags = [f for f in self.ex.unresolved_effects if "finite CAST head" in f]
        self.assertEqual(len(flags), 1)
        self.assertIn("Colossus (cannot be paid for right now)", flags[0])

    def test_f2_land_head_refuses_with_the_carrier_reason(self):
        # Same law through the CARRIER axis: the head is a land (never a
        # spell, CR 109.2), so the finite slice designates the land and
        # refuses — it does NOT fall through to the payable spell behind.
        land = self.world.add_card(
            card_id("Island", type_line="Land"), self.p0, ZONE_LIBRARY
        )
        spell = self.spell_in_library("Payable", _cost(1))
        self.assertEqual(min([land, spell]), land)
        self.world.players[self.p0].mana_pool = {"C": 9}
        self._mand_cast()
        self.assertEqual(self.world.zone_of(spell).kind, "library")
        flags = [f for f in self.ex.unresolved_effects if "finite CAST head" in f]
        self.assertEqual(len(flags), 1)
        self.assertIn("Island (not a SpellAbility carrier)", flags[0])

    def test_f2_clean_head_casts_and_the_tail_stays_untouched(self):
        # The refusal must not eat the legal branch: payable head casts,
        # the unpayable card BEHIND the slice is irrelevant (it is not
        # designated) and no ledger row is written.
        bolt = self.spell_in_library("Bolt", _cost(1))
        self.spell_in_library("Colossus", _cost(5, "R"))
        self.world.players[self.p0].mana_pool = {"C": 1}
        self._mand_cast()
        self.assertEqual(self.world.zone_of(bolt).kind, "graveyard")
        self.assertEqual(self.world.players[self.p0].mana_pool, {})
        self.assertEqual(
            [f for f in self.ex.unresolved_effects if f.startswith("cast-gap")], []
        )

    def test_f2_bound_target_clamp_registers_its_drop(self):
        # F2(4): the TARGET legality clamp stays (CR 603.3-mode) but a
        # BOUND designation the CAST clamp removes is an explicit
        # refusal — it must be LEDGERED, not silently dropped (driven on
        # the resolve_selector lane directly: the role_handles bound
        # shortcut returns plain designations raw, which is the OTHER
        # explicit-designation law — the raw per-card raise — and stays).
        from MTG_bot.core.executor.legality import ctx_for
        from MTG_bot.core.executor.query import cast_designee_ok
        from MTG_bot.core.executor.selectors import resolve_selector

        costly = self.spell_in_library("Colossus", _cost(5, "R"))
        payable = self.spell_in_library("Bolt", _cost(1))
        self.world.players[self.p0].mana_pool = {"C": 1}
        ctx = ctx_for(
            self.ex, self.src, self.p0, bindings={"target": [costly, payable]}
        )
        sel = Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(LIB_YOU,))
        out = resolve_selector(
            sel, ctx, ok=lambda h: cast_designee_ok(self.ex, ctx, h, None)
        )
        self.assertEqual(out, [payable])  # legality drop itself unchanged
        flags = [
            f
            for f in self.ex.unresolved_effects
            if "TARGET designation left the legal set" in f
        ]
        self.assertEqual(len(flags), 1)
        self.assertIn("Colossus (cannot be paid for right now)", flags[0])

    def test_f2_random_cast_draws_the_clamped_pool(self):
        # F2(3): the RANDOM draw is over the CLAMPED population — an
        # unpayable card can never be drawn into a cast (the raw draw
        # only ever reached the raise-trap; the bias is documented on the
        # branch, this pin freezes the intent).
        from MTG_bot.core.executor.legality import ctx_for
        from MTG_bot.core.executor.query import cast_designee_ok
        from MTG_bot.core.executor.selectors import resolve_selector

        self.spell_in_library("Colossus", _cost(5, "R"))
        payable = self.spell_in_library("Bolt", _cost(1))
        self.world.players[self.p0].mana_pool = {"C": 1}
        ctx = ctx_for(self.ex, self.src, self.p0)
        sel = Selector(QConst(1), SelectorMode.RANDOM, UNIV, zones=(LIB_YOU,))
        for _ in range(12):  # every draw of the biased pool
            out = resolve_selector(
                sel, ctx, ok=lambda h: cast_designee_ok(self.ex, ctx, h, None)
            )
            self.assertEqual(out, [payable])


if __name__ == "__main__":
    unittest.main()
