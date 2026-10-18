"""Tests for the B7 bucket — the ZND-2 LANDFALL + Equipment-ETB family
(spec KNOWLEDGE/2026-10-18/101, grammar round 20).

Covers templates_b7.py plus the ZND-2 extensions to templates_b6.py:
- all 20 templateable landfall register rows single-match
  ``B7-landfall-trigger``, all 8 Equipment-ETB rows single-match
  ``B7-equip-etb``, and the six honest residue rows match NOTHING (gap
  ledger in the templates_b7 docstring);
- FM2 falsifier: the landfall subject filter is ``TYPE_EQ "Land"`` — an
  object whose type line lacks "Land" never fires (executor-level lock).
  NOTE (binding spec G-FM2): these locks prove the CORPUS-appropriate
  CR 603.8b reading for this register — land-not-nonland, own-not-
  opponent, enters-not-buries. The full rule's control-change corner
  cases (a land you control entering under an opponent's control, etc.)
  are NOT claimed; they stay gap-ledger residue;
- FM6 shared-tail law: every landfall tail tree is BYTE-IDENTICAL to the
  ``templates_b6._TAIL_BUILDERS`` tree for the same sentence — one
  encoding per tail, b7 never forks;
- FM8 lifecycle: a hand→graveyard land move does not fire landfall;
- the B4 T3 widening: creature/artifact/enchantment share one disjoint
  pattern, land stays separate; M21 census pin — the two new sentences
  occur ZERO times in M21, so goldens and buckets stay byte-identical;
- B6 T4: the Murasa Sproutling tail (HAS_KICKER move); honest census
  per pre-commit gate FM1: the ONE name-referent register row (Jace copy-
  exception tail) is not encodable under the frozen grammar, so NO named
  head is registered (zero consumers = §10 phantom; /98 T4 precedent) —
  the row stays honest register residue;
- full IR-tree equality for the representative tails, the Nissa loyalty
  self-name anaphor and the Equipment-ETB attach;
- M21 zero-match for every B7 pattern (and the extended B6 tables).
"""

from __future__ import annotations

import itertools
import unittest
import uuid
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    CounterKind,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    PtDelta,
    PtDirection,
    QConst,
    Selector,
    SelectorMode,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    canonical_json,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import CardIdentity, RawCard, split_sentences
from MTG_bot.core.compiler.templates import AbilityOutcome
from MTG_bot.core.compiler.templates_b6 import (
    _TAIL_BUILDERS,
    _TAIL_DRAKE,
    _build_tail,
    _etb_event,
)
from MTG_bot.core.compiler.templates_b6 import (
    TEMPLATES as B6_TEMPLATES,
)
from MTG_bot.core.compiler.templates_b7 import (
    _LANDFALL_TAILS,
    TEMPLATES,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    GameWorld,
)

REGISTRY = build_full_registry()

# ---------------------------------------------------------------------------
# The committed 2026-10-18 ZNR register sentences (dumped programmatically
# from the evidence extract — never hand-typed).
# ---------------------------------------------------------------------------

_LANDED_LANDFALL_SENTENCES: Final[tuple[str, ...]] = (
    "Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn.",
    "Landfall — Whenever a land you control enters, put a loyalty counter on Nissa.",
    "Landfall — Whenever a land you control enters, creatures you control get +1/+1 until end of turn.",
    "Landfall — Whenever a land you control enters, you gain 1 life.",
    "Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn.",
    "Landfall — Whenever a land you control enters, put four +1/+1 counters on target Plant you control.",
    "Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn.",
    "Landfall — Whenever a land you control enters, equipped creature gets +2/+2 until end of turn.",
    "Landfall — Whenever a land you control enters, this creature deals 1 damage to each opponent.",
    "Landfall — Whenever a land you control enters, put a +1/+1 counter on this creature.",
    "Landfall — Whenever a land you control enters, put a +1/+1 counter on this creature.",
    "Landfall — Whenever a land you control enters, add one mana of any color.",
    "Landfall — Whenever a land you control enters, each opponent mills three cards.",
    "Landfall — Whenever a land you control enters, this creature gains indestructible until end of turn.",
    "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token.",
    "Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn.",
    "Landfall — Whenever a land you control enters, exile the top card of your library.",
    "Landfall — Whenever a land you control enters, this creature gets +2/+2 until end of turn.",
    "Landfall — Whenever a land you control enters, tap target creature an opponent controls.",
    "Landfall — Whenever a land you control enters, put a +1/+1 counter on this creature.",
)

_RESIDUE_LANDFALL_SENTENCES: Final[tuple[str, ...]] = (
    "Landfall — Whenever a land you control enters, choose one —",
    "Landfall — Whenever a land you control enters, if this card is in your graveyard and it's your turn, you may cast it from your graveyard this turn.",
    "Landfall — Whenever a land you control enters, this creature can attack this turn as though it didn't have defender.",
    "Landfall — Whenever a land you control enters, if it's your main phase, there's an additional combat phase after this phase.",
    "Landfall — Whenever a land you control enters, you gain 4 life if this is the first time this ability has resolved this turn.",
    "Whenever a land an opponent controls enters, if that player had another land enter the battlefield under their control this turn, they return a land they control to its owner's hand.",
)

_EQUIP_ETB_SENTENCE: Final = (
    "When this Equipment enters, attach it to target creature you control."
)

_MURASA_ROW: Final = (
    "When this creature enters, if it was kicked, return target card "
    "with a kicker ability from your graveyard to your hand."
)
_JACE_ROW: Final = (
    "When Jace enters, if Jace was kicked, create a token that's a copy "
    "of Jace, except it's not legendary and its starting loyalty is 1."
)
_ENTERS_TAPPED: Final = {
    "creature": "This creature enters tapped.",
    "artifact": "This artifact enters tapped.",
    "enchantment": "This enchantment enters tapped.",
    "land": "This land enters tapped.",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _template(tid: str):
    for t in TEMPLATES:
        if t.tid == tid:
            return t
    raise AssertionError(f"template {tid} missing")


def _b7_tids(sentence: str) -> list[str]:
    return [t.tid for t in TEMPLATES if t.pattern.fullmatch(sentence)]


def _reg_tids(sentence: str) -> list[str]:
    return [m.template.tid for m in REGISTRY.match(sentence)]


def _build_landfall(sentence: str) -> TriggeredAbility:
    t = _template("B7-landfall-trigger")
    m = t.pattern.fullmatch(sentence)
    assert m is not None, sentence
    outcome = t.build(m)
    assert isinstance(outcome, AbilityOutcome)
    ability = outcome.ability
    assert isinstance(ability, TriggeredAbility)
    return ability


def _raw(
    name: str,
    sentences: tuple[str, ...],
    *,
    types: tuple[str, ...] = ("Creature",),
    subtypes: tuple[str, ...] = (),
    colors: tuple[str, ...] = (),
    mana_cost_raw: str | None = None,
    mana_value: int = 0,
    power_raw: str | None = None,
    toughness_raw: str | None = None,
    keywords: tuple[str, ...] = (),
) -> RawCard:
    """Minimal RawCard stub for end-to-end compile_card tests (b6 law)."""
    identity = CardIdentity(
        oracle_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"mtg://{name}")),
        name=name,
    )
    type_line = " ".join(types)
    if subtypes:
        type_line += " — " + " ".join(subtypes)
    return RawCard(
        identity=identity,
        type_line=type_line,
        types=types,
        subtypes=subtypes,
        supertypes=(),
        colors=colors,
        color_identity=frozenset(colors),
        mana_cost_raw=mana_cost_raw,
        mana_value=mana_value,
        power_raw=power_raw,
        toughness_raw=toughness_raw,
        loyalty_raw=None,
        keywords=keywords,
        sentences=sentences,
        layout="normal",
        is_token=False,
        is_emblem=False,
        token_name_refs=(),
        related_names=(),
    )


def _m21_sentences() -> list[str]:
    import json
    import os

    m21 = os.path.join(os.path.dirname(__file__), "..", "..", "data", "M21.json")
    if not os.path.exists(m21):
        return []
    with open(m21) as f:
        cards = json.load(f)["data"]["cards"]
    out: list[str] = []
    for c in cards:
        out.extend(split_sentences(c.get("text")))
    return out


# ---------------------------------------------------------------------------
# Hand-built expected trees (derived from oracle clauses, not from the
# builders — the equality tests below are the lock).
# ---------------------------------------------------------------------------

_LANDFALL_EVENT: Final = ZoneChangeEvent(
    from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
    to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
    subject=FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        )
    ),
)


def _self(zone: Zone) -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        zone,
    )


BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


def _expected_self_pt(p: int, t: int) -> TriggeredAbility:
    return TriggeredAbility(
        event=_LANDFALL_EVENT,
        condition=None,
        effect=Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _self(BF_ANY)),
                    ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                    ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


# ---------------------------------------------------------------------------
# 1. Pattern discipline
# ---------------------------------------------------------------------------


class TestB7Patterns(unittest.TestCase):
    def test_register_landfall_rows_single_match_b7(self) -> None:
        for s in _LANDED_LANDFALL_SENTENCES:
            self.assertEqual(_b7_tids(s), ["B7-landfall-trigger"], s)
            self.assertEqual(_reg_tids(s), ["B7-landfall-trigger"], s)

    def test_landed_census_is_twenty_rows(self) -> None:
        # 20 of the 26 evidence landfall rows template; the 5 "Landfall —"
        # stragglers + the non-Landfall Conundrum row are the ledger.
        self.assertEqual(len(_LANDED_LANDFALL_SENTENCES), 20)
        self.assertEqual(len(_RESIDUE_LANDFALL_SENTENCES), 6)

    def test_residue_rows_match_nothing_anywhere(self) -> None:
        for s in _RESIDUE_LANDFALL_SENTENCES:
            self.assertEqual(_reg_tids(s), [], s)

    def test_equip_etb_row_single_match(self) -> None:
        # Census: 8 register rows share this ONE sentence (all 8 ZNR
        # equipment with a plain enters-and-attach ETB).
        self.assertEqual(_b7_tids(_EQUIP_ETB_SENTENCE), ["B7-equip-etb"])
        self.assertEqual(_reg_tids(_EQUIP_ETB_SENTENCE), ["B7-equip-etb"])

    def test_landfall_head_is_syntactic_keyword_only(self) -> None:
        ability = _build_landfall(_LANDED_LANDFALL_SENTENCES[0])
        # No KeywordAbility atom, no condition: "Landfall —" is pure head
        # syntax wrapping a plain enters trigger (CR 603.8b shape).
        self.assertIsNone(ability.condition)
        self.assertIsInstance(ability.event, ZoneChangeEvent)
        self.assertNotIn("KeywordAbility", canonical_json(ability))

    def test_em_dash_is_literal_not_hyphen(self) -> None:
        fake = _LANDED_LANDFALL_SENTENCES[0].replace("—", "-")
        self.assertEqual(_b7_tids(fake), [])

    def test_m21_pool_sentences_never_match_b7(self) -> None:
        sentences = _m21_sentences()
        if not sentences:
            self.skipTest("M21.json not present")
        for s in sentences:
            hits = [t.tid for t in TEMPLATES if t.pattern.fullmatch(s)]
            self.assertEqual(hits, [], f"M21 sentence matched B7: {s!r}")


# ---------------------------------------------------------------------------
# 2. IR-tree equality (FM6 shared-tail law included)
# ---------------------------------------------------------------------------


class TestB7Trees(unittest.TestCase):
    def test_self_pt_tail_tree(self) -> None:
        got = _build_landfall(
            "Landfall — Whenever a land you control enters, "
            "this creature gets +2/+2 until end of turn."
        )
        self.assertEqual(canonical_json(got), canonical_json(_expected_self_pt(2, 2)))

    def test_nissa_loyalty_tree(self) -> None:
        got = _build_landfall(
            "Landfall — Whenever a land you control enters, "
            "put a loyalty counter on Nissa."
        )
        expected = TriggeredAbility(
            event=_LANDFALL_EVENT,
            condition=None,
            effect=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
                            Selector(
                                QConst(1),
                                SelectorMode.CHOOSE,
                                FAnd(
                                    children=(
                                        FAtom(pred=FAtomPred.IS_SOURCE),
                                        FAtom(
                                            pred=FAtomPred.NAME_CONTAINS,
                                            string_value="Nissa",
                                        ),
                                    )
                                ),
                                BF_ANY,
                            ),
                        ),
                        ("counter_kind", CounterKind.LOYALTY),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
        self.assertEqual(canonical_json(got), canonical_json(expected))

    def test_equip_etb_tree(self) -> None:
        t = _template("B7-equip-etb")
        m = t.pattern.fullmatch(_EQUIP_ETB_SENTENCE)
        assert m is not None
        outcome = t.build(m)
        assert isinstance(outcome, AbilityOutcome)
        got = outcome.ability
        expected = TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.ATTACH,
                args=AtomArgs(
                    pairs=(
                        ("equipment", _self(BF_ANY)),
                        (
                            "target",
                            Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAnd(
                                    children=(
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ,
                                            string_value="Creature",
                                        ),
                                        FAtom(
                                            pred=FAtomPred.CONTROLLER_IS,
                                            who=ControllerRef.YOU,
                                        ),
                                    )
                                ),
                                BF_ANY,
                            ),
                        ),
                    )
                ),
            ),
        )
        self.assertEqual(canonical_json(got), canonical_json(expected))

    def test_fm6_every_tail_reuses_the_shared_builder(self) -> None:
        # Census: 20 register rows carry 14 distinct sentences; 13 are
        # table tails + the loyalty self-name arm. One encoding per tail
        # sentence: the b7 landfall effect tree is BYTE-IDENTICAL to
        # templates_b6's shared-table tree. b7 imports the table — it
        # never forks an encoding.
        self.assertEqual(len(set(_LANDED_LANDFALL_SENTENCES)), 14)
        self.assertEqual(len(_LANDFALL_TAILS), 13)
        for tail in _LANDFALL_TAILS:
            self.assertIn(tail, _TAIL_BUILDERS, tail)
            sentence = "Landfall — Whenever a land you control enters, " + tail
            got = _build_landfall(sentence)
            self.assertEqual(
                canonical_json(got.effect),
                canonical_json(_build_tail(tail)),
                tail,
            )

    def test_pc3_within_b7(self) -> None:
        for s in _LANDED_LANDFALL_SENTENCES + (_EQUIP_ETB_SENTENCE,):
            self.assertLessEqual(len(_b7_tids(s)), 1, s)


# ---------------------------------------------------------------------------
# 3. B4 T3 widening (disjoint split, M21 census pin)
# ---------------------------------------------------------------------------


class TestB4EntersTappedWidening(unittest.TestCase):
    def test_disjoint_single_claim(self) -> None:
        for noun in ("creature", "artifact", "enchantment"):
            self.assertEqual(
                _reg_tids(_ENTERS_TAPPED[noun]),
                ["B4-enters-tapped-creature"],
                noun,
            )
        self.assertEqual(_reg_tids(_ENTERS_TAPPED["land"]), ["B4-enters-tapped-land"])

    def test_m21_census_new_sentences_absent(self) -> None:
        # The byte-identity premise for gate 3: M21 contains ZERO
        # "This artifact/enchantment enters tapped." sentences, so the
        # widening cannot move a golden, a bucket or a PC-4 fingerprint.
        sentences = _m21_sentences()
        if not sentences:
            self.skipTest("M21.json not present")
        for noun in ("artifact", "enchantment"):
            s = _ENTERS_TAPPED[noun]
            self.assertEqual(sentences.count(s), 0, noun)

    def test_b4_land_arm_still_exact(self) -> None:
        # The disjointness pin: widening the non-land arm must NOT make
        # the land sentence claimable by the creature-arm template.
        from MTG_bot.core.compiler import templates_b4

        creature_arm = next(
            t for t in templates_b4.TEMPLATES if t.tid == "B4-enters-tapped-creature"
        )
        land_arm = next(
            t for t in templates_b4.TEMPLATES if t.tid == "B4-enters-tapped-land"
        )
        self.assertIsNone(creature_arm.pattern.fullmatch(_ENTERS_TAPPED["land"]))
        self.assertIsNotNone(land_arm.pattern.fullmatch(_ENTERS_TAPPED["land"]))


# ---------------------------------------------------------------------------
# 4. B6 ZND-2 extensions (T4)
# ---------------------------------------------------------------------------


class TestB6Znd2Extensions(unittest.TestCase):
    def test_murasa_row_single_match_and_tree(self) -> None:
        self.assertEqual(_reg_tids(_MURASA_ROW), ["B6-etb-kicked-trigger"])
        t = next(t for t in B6_TEMPLATES if t.tid == "B6-etb-kicked-trigger")
        m = t.pattern.fullmatch(_MURASA_ROW)
        assert m is not None
        outcome = t.build(m)
        assert isinstance(outcome, AbilityOutcome)
        got = outcome.ability
        expected = TriggeredAbility(
            event=_etb_event(),
            condition=FAtom(pred=FAtomPred.WAS_KICKED),
            effect=Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAtom(pred=FAtomPred.HAS_KICKER),
                                Zone(
                                    kind=ZoneKind.GRAVEYARD,
                                    controller=ControllerRef.YOU,
                                ),
                            ),
                        ),
                        (
                            "destination",
                            Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                        ),
                    )
                ),
            ),
        )
        self.assertEqual(canonical_json(got), canonical_json(expected))

    def test_named_head_NOT_registered_is_honest_not_phantom(self) -> None:
        # PRE-COMMIT GATE FM1 (/101): spec /101 T4 claimed 4 name-referent rows
        # (Jace/Chandra/Nissa); the committed register carries exactly ONE and
        # its copy-exception tail is NOT encodable under the frozen grammar
        # (Verb.COPY slots are {source}-only). A head matching ZERO register
        # rows is a §10 PHANTOM, not a pre-registered idiom: HAS_KICKER (ZND-1)
        # had named ZND-2 consumers, this has none. Withdrawn per the /98 T4
        # precedent — it lands together with its consumer instead.
        self.assertNotIn("B6-etb-kicked-trigger-named", {t.tid for t in B6_TEMPLATES})
        # The register's one name-referent row stays UNPARSED (honest residue).
        self.assertEqual(_reg_tids(_JACE_ROW), [])
        # And the self-anaphor must NOT steal it: "if it was kicked" is a
        # different anaphor, so the name-referent head cannot borrow it.
        self.assertEqual(
            [t.tid for t in B6_TEMPLATES if t.pattern.fullmatch(_JACE_ROW)], []
        )

    def test_self_anaphor_still_rejects_a_renamed_head(self) -> None:
        # The mirror law the withdrawn twin owned: the landed self-anaphor head
        # matches "this <type> enters, if IT was kicked" only — a named head
        # stays unmatched rather than silently binding the wrong referent (PC-3).
        named = (
            "When Jace, Mirror Mage enters, if Jace, Mirror Mage was "
            "kicked, " + _TAIL_DRAKE
        )
        self.assertEqual(_reg_tids(named), [])

    def test_m21_never_matches_the_new_b6_shapes(self) -> None:
        sentences = _m21_sentences()
        if not sentences:
            self.skipTest("M21.json not present")
        for s in sentences:
            hits = [
                t.tid
                for t in B6_TEMPLATES
                if t.tid in ("B6-etb-kicked-trigger",) and t.pattern.fullmatch(s)
            ]
            self.assertEqual(hits, [], f"M21 sentence matched the ETB heads: {s!r}")


# ---------------------------------------------------------------------------
# 5. compile_card end-to-end
# ---------------------------------------------------------------------------


class TestCompileCardEndToEnd(unittest.TestCase):
    def test_baloth_compiles_clean(self) -> None:
        raw = _raw(
            "Test Canopy Baloth",
            (
                (
                    "Landfall — Whenever a land you control enters, "
                    "this creature gets +2/+2 until end of turn."
                ),
            ),
            types=("Creature",),
            subtypes=("Beast",),
            colors=("G",),
            mana_cost_raw="{G}{G}",
            mana_value=2,
            power_raw="4",
            toughness_raw="3",
        )
        res = compile_card(raw, REGISTRY)
        self.assertEqual(res.unparsed, (), f"register: {res.unparsed}")
        text = repr(res.card)
        self.assertIn("MODIFY_PT", text)
        self.assertIn("string_value='Land'", text)

    def test_landfall_residue_card_keeps_the_row(self) -> None:
        raw = _raw(
            "Test Skyclave Squid",
            (
                (
                    "Landfall — Whenever a land you control enters, this "
                    "creature can attack this turn as though it didn't have "
                    "defender."
                ),
            ),
            types=("Creature",),
            subtypes=("Squid",),
            power_raw="4",
            toughness_raw="4",
        )
        res = compile_card(raw, REGISTRY)
        self.assertEqual(len(res.unparsed), 1)
        self.assertIn("as though", res.unparsed[0][0])


# ---------------------------------------------------------------------------
# 6. Executor falsifiers (FM2 / FM8 / direction / one-fire / attach)
#    Harness per test_executor_p1a_move.py: GameWorld + Executor +
#    attach_card, drives the COMPILED trees.
# ---------------------------------------------------------------------------

_ORACLE_SEQ = itertools.count(1_900)


def _card_id(name: str, type_line: str = "Creature") -> CardIdentity:
    n = next(_ORACLE_SEQ)
    return CardIdentity(
        oracle_id=f"{n:08x}-aaaa-bbbb-cccc-444444444444",
        name=name,
        type_line=type_line,
        power="2" if "Creature" in type_line else None,
        toughness="2" if "Creature" in type_line else None,
        cmc=2,
        colors=(),
    )


def _record_of(
    abilities, name: str, oid: str, type_line: str = "Creature"
) -> CardRecord:
    return CardRecord(
        oracle_id=oid,
        name=name,
        type_line=type_line,
        types=tuple(w for w in type_line.split(" — ")[0].split()),
        subtypes=tuple(type_line.split(" — ")[1].split()) if " — " in type_line else (),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=2,
        power=QConst(2),
        toughness=QConst(2),
        loyalty=None,
        keywords=(),
        abilities=tuple(abilities),
        is_token=False,
    )


def _enter_atom() -> Atom:
    return Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAnd(children=()),
                        Zone(ZoneKind.HAND, ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
            )
        ),
    )


class LandfallExecutorCase(unittest.TestCase):
    """The compiled Nissa-tail trigger (gain-1-life is the cleanest fire
    counter) sits on a watcher creature; the falsifying zone moves are run
    through the executor so the JOURNALS, not the pattern, are judged."""

    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=13)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        trigger = _build_landfall(
            "Landfall — Whenever a land you control enters, you gain 1 life."
        )
        self.watch = self.world.add_card(
            _card_id("Watcher Beast", "Creature — Beast"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)
        self.ex.attach_card(
            self.watch,
            _record_of(
                [trigger],
                "Watcher Beast",
                self.world.cards[self.watch].identity.oracle_id,
            ),
        )
        self.land_p0 = self.world.add_card(
            _card_id("Forest", "Land"), self.p0, ZONE_HAND
        )
        self.land_p1 = self.world.add_card(
            _card_id("Forest", "Land"), self.p1, ZONE_HAND
        )
        self.creature = self.world.add_card(
            _card_id("Vanilla 3/3", "Creature"), self.p0, ZONE_HAND
        )

    def life(self, player) -> int:
        return self.world.players[player].life

    def enter(self, handle, controller) -> None:
        self.ex.execute(
            _enter_atom(),
            source=handle,
            controller=controller,
            bindings={"cards": handle},
        )

    def move_to(self, handle, controller, destination) -> None:
        self._move(
            handle, controller, Zone(ZoneKind.HAND, ControllerRef.YOU), destination
        )

    def _move(self, handle, controller, origin, destination) -> None:
        self.ex.execute(
            Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAnd(children=()),
                                origin,
                            ),
                        ),
                        ("destination", destination),
                    )
                ),
            ),
            source=handle,
            controller=controller,
            bindings={"cards": handle},
        )


class TestLandfallExecutor(LandfallExecutorCase):
    def test_own_land_enter_fires_exactly_once(self) -> None:
        before = self.life(self.p0)
        self.enter(self.land_p0, self.p0)
        self.assertEqual(self.life(self.p0), before + 1)
        self.assertEqual(self.world.zone_of(self.land_p0).kind, ZONE_BATTLEFIELD)

    def test_non_land_enter_never_fires_FM2(self) -> None:
        before = self.life(self.p0)
        self.enter(self.creature, self.p0)
        # The move REALLY happened (non-vacuous falsifier):
        self.assertEqual(self.world.zone_of(self.creature).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.life(self.p0), before)

    def test_opponent_land_enter_never_fires(self) -> None:
        before0, before1 = self.life(self.p0), self.life(self.p1)
        self.enter(self.land_p1, self.p1)
        self.assertEqual(self.world.zone_of(self.land_p1).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.life(self.p0), before0)
        self.assertEqual(self.life(self.p1), before1)

    def test_hand_to_graveyard_never_fires_FM8(self) -> None:
        # FM8 lifecycle: a land card leaving the hand for the graveyard is
        # a hand→graveyard zone move, NOT an enters event — landfall must
        # stay silent even though the subject card IS a land.
        before = self.life(self.p0)
        self.move_to(self.land_p0, self.p0, Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU))
        self.assertEqual(self.world.zone_of(self.land_p0).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.life(self.p0), before)

    def test_from_any_origin_fires_the_other_landfall_legs_FM5(self) -> None:
        # FM5 (the commit-gate's probe folded into the suite): the head is "a
        # land you control enters" — ORIGIN-INDEPENDENT. Graveyard→battlefield
        # (recursion) and exile→battlefield (re-animation) are ENTERS and must
        # fire; a pure EXIT out of the battlefield must not.
        graveyard = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
        exile = Zone(ZoneKind.EXILE, ControllerRef.YOU)
        battlefield = Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)
        # Route the land out to the graveyard first (silent, per FM8 above).
        self.move_to(self.land_p0, self.p0, graveyard)
        before = self.life(self.p0)
        self._move(self.land_p0, self.p0, graveyard, battlefield)
        self.assertEqual(self.life(self.p0), before + 1, "GY→battlefield is an enters")
        # Out to exile and back: fires again — each enters is its own event
        # (the head has no once-per-turn bound).
        self._move(self.land_p0, self.p0, battlefield, exile)
        mid = self.life(self.p0)
        self._move(self.land_p0, self.p0, exile, battlefield)
        self.assertEqual(self.life(self.p0), mid + 1, "exile→battlefield is an enters")
        # Pure EXIT: battlefield→graveyard, silent.
        after = self.life(self.p0)
        self._move(self.land_p0, self.p0, battlefield, graveyard)
        self.assertEqual(self.world.zone_of(self.land_p0).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.life(self.p0), after, "an exit is not an enters")

    def test_untap_phase_moves_are_not_enters(self) -> None:
        # Second FM8 leg: the land is already on the battlefield; a turn
        # boundary must not re-fire the trigger.
        self.enter(self.land_p0, self.p0)
        after_first = self.life(self.p0)
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)
        self.assertEqual(self.life(self.p0), after_first)


class TestEquipEtbExecutor(unittest.TestCase):
    def test_compiled_attach_atom_executes(self) -> None:
        # The B7 tree is not just IR decoration: the ATTACH slots drive the
        # executor's attachment table exactly like the b5a Equip atom.
        world = GameWorld(num_players=2, start_life=20, master_seed=17)
        p0 = world.player_order[0]
        equip = world.add_card(
            _card_id("Test Knife", "Artifact — Equipment"), p0, ZONE_BATTLEFIELD
        )
        creature = world.add_card(_card_id("Host", "Creature"), p0, ZONE_BATTLEFIELD)
        ex = Executor(world)
        t = _template("B7-equip-etb")
        m = t.pattern.fullmatch(_EQUIP_ETB_SENTENCE)
        assert m is not None
        outcome = t.build(m)
        assert isinstance(outcome, AbilityOutcome)
        ability = outcome.ability
        assert isinstance(ability, TriggeredAbility)
        assert isinstance(ability.effect, Atom)
        ex.execute(
            ability.effect,
            source=equip,
            controller=p0,
            bindings={"equipment": equip, "target": creature},
        )
        self.assertEqual(ex.attachments.get(equip), creature)


if __name__ == "__main__":
    unittest.main()
