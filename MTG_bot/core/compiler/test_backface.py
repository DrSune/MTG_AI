"""ZND-2f: BackFace encode half (KNOWLEDGE/2026-10-18/106, SPEC-AMENDED).

Covers the four binding claims of the amendment:
1. Landed: 61 face abilities (25 enters-tapped + 36 add-mana) compile into
   a ``BackFace`` node appended to the card's abilities; faces compile
   through the SAME registry via the synthetic single-faced route.
2. Residual: the 10 pay-3-life sentences land ONLY in
   ``CompileResult.back_face_unparsed`` — never in the front register,
   never counted as covered (TRUTH LAW).
3. Phantom defenses: every ``walk()`` verdict consumer (games.py
   produces_mana, compiler.py engine_support) excludes the BackFace
   subtree via ``skip=BackFace``; coverage.py TAGS face verbs separately
   so a face ADD_MANA never merges into the front verb histogram.
4. Determinism: node equality and serializer round-trip are stable.
"""

from __future__ import annotations

import inspect
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Final

from MTG_bot.core.ability_tree import (
    Ability,
    ActivatedAbility,
    Atom,
    AtomArgs,
    BackFace,
    CardRecord,
    ControllerRef,
    Cost,
    CostTap,
    EtBState,
    QConst,
    Verb,
    canonical_json,
    from_dict,
    to_dict,
    walk,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry, measure_pool
from MTG_bot.core.compiler.ingest import CardFace, RawCard, ingest_pool
from MTG_bot.core.errors import StateCorruptionError
from MTG_bot.core.executor import games
from MTG_bot.core.identity import CardIdentity

REPO: Final = Path(__file__).resolve().parents[3]
ZNR_JSON: Final = REPO / "MTG_bot" / "data" / "ZNR.json"

# Verbatim ZNR face text (the exact shapes the amendment census found).
ENTERS_TAPPED: Final = "This land enters tapped."
ADD_B: Final = "{T}: Add {B}."
PAY3_HEAD: Final = "As this land enters, you may pay 3 life."
PAY3_TAIL: Final = "If you don't, it enters tapped."

# A real ActivatedAbility with the exact shape the compiler produces for
# "{T}: Add {B}" (verified against a live ZNR face compile).
T_MANA: Final = ActivatedAbility(
    cost=Cost(parts=(CostTap(),)),
    effect=Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("amount", QConst(1)),
                ("color", "B"),
                ("controller", ControllerRef.YOU),
            )
        ),
    ),
)
ETB_TAPPED: Final = EtBState(tapped=True)


def _oid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def _face(name: str, sentences: tuple[str, ...]) -> CardFace:
    """Structured back face in the shape ingest produces for a land face."""
    return CardFace(
        name=name,
        type_line="Land",
        types=("Land",),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost_raw=None,
        mana_value=0,
        power_raw=None,
        toughness_raw=None,
        loyalty_raw=None,
        keywords=(),
        sentences=sentences,
    )


def _mdfc(
    n: int,
    *,
    front: tuple[str, ...] = ("Deal 2 damage.",),
    face: CardFace | None = None,
    type_line: str = "Instant",
) -> RawCard:
    """MDFC RawCard in the exact shape ingest_pool folds (front = the
    RawCard itself, back = the folded CardFace). Default front has NO mana
    verb, so any ADD_MANA in the tree provably came from the face."""
    return RawCard(
        identity=CardIdentity(oracle_id=_oid(n), name=f"Card {n}"),
        type_line=type_line,
        types=tuple(type_line.split(" — ")[0].split()),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost_raw=None,
        mana_value=0 if type_line == "Land" else 2,
        power_raw=None,
        toughness_raw=None,
        loyalty_raw=None,
        keywords=(),
        sentences=front,
        layout="modal_dfc" if face is not None else "normal",
        is_token=False,
        is_emblem=False,
        token_name_refs=(),
        related_names=(),
        back_face=face,
    )


def _record(n: int, abilities: tuple[Ability, ...]) -> CardRecord:
    """Minimal land CardRecord root for walk/serializer fixtures."""
    return CardRecord(
        oracle_id=_oid(n),
        name=f"Record {n}",
        type_line="Land",
        types=("Land",),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=0,
        power=None,
        toughness=None,
        loyalty=None,
        keywords=(),
        abilities=abilities,
        is_token=False,
    )


class TestFaceCompile(unittest.TestCase):
    """Amendment claim 1+2: what lands in the tree, what stays residual."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = build_full_registry()

    def test_enters_tapped_and_add_mana_face(self) -> None:
        raw = _mdfc(
            1,
            face=_face("Swamp // Back", (ENTERS_TAPPED, ADD_B)),
        )
        result = compile_card(raw, self.registry)
        faces = [a for a in result.card.abilities if isinstance(a, BackFace)]
        self.assertEqual(len(faces), 1)
        face = faces[0]
        self.assertEqual(len(face.abilities), 2)
        etb, activated = face.abilities
        assert isinstance(etb, EtBState)
        assert isinstance(activated, ActivatedAbility)
        assert isinstance(activated.effect, Atom)
        self.assertIs(activated.effect.verb, Verb.ADD_MANA)
        # appended LAST among the card's own components (§11 board law:
        # the face is the card's own component, ordered after front text)
        self.assertIs(result.card.abilities[-1], face)
        self.assertEqual(result.back_face_unparsed, ())

    def test_add_mana_only_face(self) -> None:
        raw = _mdfc(2, face=_face("Only", (ADD_B,)))
        result = compile_card(raw, self.registry)
        face = next(a for a in result.card.abilities if isinstance(a, BackFace))
        self.assertEqual(len(face.abilities), 1)
        (activated,) = face.abilities
        assert isinstance(activated, ActivatedAbility)
        assert isinstance(activated.effect, Atom)
        self.assertIs(activated.effect.verb, Verb.ADD_MANA)

    def test_pay3_pair_lands_in_residual_never_covered(self) -> None:
        """TRUTH LAW: the pay-3-life pair is ZND-2f2 scope — it must sit
        in back_face_unparsed ONLY (never the front register, never a
        compiled ability)."""
        raw = _mdfc(3, face=_face("Residual", (PAY3_HEAD, PAY3_TAIL)))
        result = compile_card(raw, self.registry)
        face = next(a for a in result.card.abilities if isinstance(a, BackFace))
        self.assertEqual(face.abilities, ())  # nothing compiled from it
        self.assertEqual(
            {s for s, _ in result.back_face_unparsed},
            {PAY3_HEAD, PAY3_TAIL},
        )
        # Front register stays face-blind. (The synthetic Instant front's
        # own damage sentence may self-land in the register — that is the
        # fixture shape, not the claim; the claim is the FACE pair never
        # crosses into it.)
        front_sents = {s for s, _ in result.unparsed}
        self.assertNotIn(PAY3_HEAD, front_sents)
        self.assertNotIn(PAY3_TAIL, front_sents)

    def test_single_faced_card_has_no_backface_anywhere(self) -> None:
        raw = _mdfc(4, front=(ADD_B,), face=None)
        result = compile_card(raw, self.registry)
        self.assertFalse(any(isinstance(n, BackFace) for n in walk(result.card)))
        self.assertEqual(result.back_face_unparsed, ())


class TestSerializer(unittest.TestCase):
    """Tag-only visibility: BackFace round-trips; empty face omits fields."""

    def test_round_trip_full_face(self) -> None:
        face = BackFace("Valley", (ETB_TAPPED, T_MANA))
        d = to_dict(face)
        self.assertEqual(d["tag"], "BackFace")
        self.assertEqual(from_dict("BackFace", d), face)

    def test_round_trip_empty_face_omits_abilities(self) -> None:
        face = BackFace("Shelter", ())
        d = to_dict(face)
        self.assertEqual(d, {"tag": "BackFace", "face_name": "Shelter"})
        self.assertEqual(from_dict("BackFace", d), face)

    def test_round_trip_inside_card_record(self) -> None:
        card = _record(5, (ETB_TAPPED, BackFace("V", (T_MANA,))))
        d = to_dict(card)
        self.assertEqual(from_dict("CardRecord", d), card)
        self.assertEqual(
            canonical_json(card), canonical_json(from_dict("CardRecord", d))
        )

    def test_post_init_validation(self) -> None:
        with self.assertRaises(ValueError):
            BackFace("X", ("not an ability",))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            BackFace(7, ())  # type: ignore[arg-type]


class TestWalkSkip(unittest.TestCase):
    """The exclusion primitive: yield the node, never descend."""

    def test_skip_yields_node_without_children(self) -> None:
        face = BackFace("V", (T_MANA,))
        self.assertIn(T_MANA, list(walk(face)))
        skipped = list(walk(face, skip=(BackFace,)))
        self.assertIn(face, skipped)
        self.assertNotIn(T_MANA, skipped)

    def test_skip_through_tuple_fields(self) -> None:
        face = BackFace("V", (T_MANA,))
        card = _record(6, (T_MANA, face))
        with_skip = list(walk(card, skip=(BackFace,)))
        without = list(walk(card))
        self.assertIn(face, with_skip)  # node itself still visible
        self.assertEqual(
            [n for n in without if isinstance(n, ActivatedAbility)],
            [T_MANA, T_MANA],
        )
        self.assertEqual(
            [n for n in with_skip if isinstance(n, ActivatedAbility)],
            [T_MANA],
        )


class TestPhantomDefenses(unittest.TestCase):
    """Amendment claim 3: verdict folds never read the unplayable face."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = build_full_registry()

    def test_produces_mana_fold_excludes_face_both_directions(self) -> None:
        """games.compile_supply fold, replayed verbatim on fixtures:
        face ADD_MANA must NOT set produces_mana; front ADD_MANA must."""
        face_card = _record(7, (BackFace("V", (T_MANA,)),))
        front_card = _record(8, (T_MANA,))

        def fold(record: CardRecord) -> bool:
            verbs = frozenset(
                node.verb
                for node in walk(record, skip=(BackFace,))
                if isinstance(node, Atom)
            )
            return Verb.ADD_MANA in verbs

        self.assertFalse(fold(face_card))  # phantom mana suppressed
        self.assertTrue(fold(front_card))  # fold still live, not vacuous
        # and without the skip the face WOULD leak — the defense is real
        leaky = frozenset(n.verb for n in walk(face_card) if isinstance(n, Atom))
        self.assertIn(Verb.ADD_MANA, leaky)

    def test_engine_support_invariance_both_directions(self) -> None:
        """compile_card's engine_support fold: a face-only unsupported
        verb must not flip the verdict; a front unsupported verb must."""
        gated = set(Verb) - {Verb.ADD_MANA}
        face_raw = _mdfc(9, front=("Deal 2 damage.",), face=_face("V", (ADD_B,)))
        front_raw = _mdfc(10, front=(ADD_B,))
        self.assertTrue(
            compile_card(face_raw, self.registry, gated).legality.engine_supported
        )
        self.assertFalse(
            compile_card(front_raw, self.registry, gated).legality.engine_supported
        )

    def test_consumer_gates_pin_skip_backface(self) -> None:
        """Source pins: every verdict fold literally passes skip=BackFace."""
        from MTG_bot.core.compiler import compiler, coverage

        for fn in (
            compiler._star_pt_gaps,  # compile_card's verdict folds, shared with card records
            compiler._engine_supported,
            compiler.compile_pool,
            coverage.measure_pool,
            games.compile_supply,
        ):
            self.assertIn(
                "skip=BackFace",
                inspect.getsource(fn),
                msg=f"{fn.__qualname__} lost its skip=BackFace fold",
            )


class TestCoverageTagging(unittest.TestCase):
    """Amendment claim 3b: face verbs are TAGGED, never merged."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = build_full_registry()

    def test_face_verbs_tagged_and_residual_rows(self) -> None:
        # Card A: single-faced land whose FRONT compiles an ADD_MANA.
        # Card B: MDFC whose FACE carries ADD_MANA + the pay-3 pair.
        # If face verbs merged into the front histogram, ADD_MANA would
        # read 2; tagged separation keeps it at exactly 1.
        land = _mdfc(11, front=("{T}: Add {W}.",), face=None, type_line="Land")
        mdfc = _mdfc(
            12,
            front=(ENTERS_TAPPED,),
            face=_face("V", (ADD_B, PAY3_HEAD, PAY3_TAIL)),
        )
        report = measure_pool(
            {_oid(11): land, _oid(12): mdfc}, self.registry, set_name="TEST"
        )
        summary = report.backface_summary
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["cards_with_faces"], 1)
        self.assertEqual(summary["verb_histogram"], {Verb.ADD_MANA.name: 1})
        self.assertEqual(summary["unparsed_rows"], 2)  # the pay-3 pair
        self.assertEqual(summary["sentence_total"], 3)
        self.assertEqual(summary["cards_face_whole"], 0)
        # front histogram sees ONLY card A's front mana (PC-6/PC-8 safe)
        self.assertEqual(report.verb_histogram.get(Verb.ADD_MANA.name), 1)

    def test_pool_without_faces_has_no_backface_key(self) -> None:
        raw = _mdfc(13, front=(ENTERS_TAPPED,), face=None, type_line="Land")
        report = measure_pool({_oid(13): raw}, self.registry, set_name="TEST")
        self.assertIsNone(report.backface_summary)
        self.assertNotIn("backface", report.to_json())


class TestZnrCensus(unittest.TestCase):
    """The amendment's pinned census: 36 faces, 61 covered, 10 residual,
    31 whole — the uplift is EXACTLY +61, no more (TRUTH LAW)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(ZNR_JSON)
        cls.registry = build_full_registry()
        cls.report = measure_pool(cls.pool, cls.registry, set_name="ZNR")

    def test_face_census_matches_spec_amendment(self) -> None:
        summary = self.report.backface_summary
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary["cards_with_faces"], 36)
        self.assertEqual(summary["verb_histogram"], {Verb.ADD_MANA.name: 36})
        self.assertEqual(summary["unparsed_rows"], 10)
        self.assertEqual(summary["cards_face_whole"], 31)
        self.assertEqual(summary["sentence_total"], 71)

    def test_pool_without_skip_would_leak_36_extra_verbs(self) -> None:
        """Counterfactual: the 36 face ADD_MANA exist in the trees — the
        tagging (not the encoding) is what keeps PC-6/PC-8 unchanged."""
        leaked = 0
        for raw in self.pool.values():
            try:
                res = compile_card(raw, self.registry)
            except StateCorruptionError:  # strict-shape cards
                continue  # (star P/T fronts) are measure-lane gaps, not faces
            leaked += sum(
                1
                for a in res.card.abilities
                if isinstance(a, BackFace)
                for n in walk(a)
                if isinstance(n, Atom) and n.verb is Verb.ADD_MANA
            )
        self.assertEqual(leaked, 36)


if __name__ == "__main__":
    unittest.main()


class FaceCompileFailureDegradesTest(unittest.TestCase):
    """Gate F1 (/106 review, archetype-4): the face field surface became
    REACHABLE this wave — a malformed face must degrade to face-unparsed
    and may NEVER crash the pool pass or lose the playable FRONT card."""

    def test_malformed_face_degrades_front_survives(self) -> None:
        bad = CardFace(
            name="Broken Face",
            type_line="Planeswalker",  # loyalty_raw=None => inner post-init raises
            types=("Planeswalker",),
            subtypes=(),
            supertypes=(),
            colors=(),
            color_identity=frozenset(),
            mana_cost_raw=None,
            mana_value=0,
            power_raw=None,
            toughness_raw=None,
            loyalty_raw=None,
            keywords=(),
            sentences=("This land enters tapped.", "{T}: Add {B}."),
        )
        result = compile_card(
            _mdfc(901, front=("Deal 2 damage.",), face=bad),
            registry=build_full_registry(),
        )
        # front survives: no crash, no BackFace node, and the tree equals the
        # CONTROL (same card with no face) — front verdict untouched:
        self.assertFalse(any(isinstance(a, BackFace) for a in result.card.abilities))
        control = compile_card(
            _mdfc(901, front=("Deal 2 damage.",)), registry=build_full_registry()
        )
        self.assertEqual(result.card.abilities, control.card.abilities)
        self.assertEqual(result.unparsed, control.unparsed)
        # every face sentence degraded into the honest residual channel:
        self.assertEqual(
            [(s, "face-compile-failed") for s in bad.sentences],
            list(result.back_face_unparsed),
        )

    def test_pool_pass_survives_malformed_face(self) -> None:
        good = _mdfc(
            903, front=("Tap target creature.",), face=_face("G", ("{T}: Add {B}.",))
        )
        bad_face = replace(
            _face("Bad", ("As this land enters, you may pay 3 life.",)),
            type_line="Planeswalker",
        )
        bad = replace(_mdfc(904, front=("Tap target creature.",)), back_face=bad_face)
        pool = {good.identity.oracle_id: good, bad.identity.oracle_id: bad}
        # the tolerant pass must complete (no exception) and keep both cards
        report = measure_pool(pool, build_full_registry())
        self.assertEqual(report.entry_count, 2)
        # both cards' FRONTS stay in the compiled pool (no gap-card exile):
        self.assertEqual(len(getattr(report, "shape_gaps", ())), 0)
