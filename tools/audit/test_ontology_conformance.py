"""tools/audit/ontology_conformance.py — checker self-tests.

The corpus has ZERO true positives for V3′ (split designation) and, by the
R1a landing, zero V2′ phantoms — so those checks are pinned with SYNTHETIC
FIXTURES (ontology §6, gate A3): a checker that cannot fire on a hand-built
violation is not a checker.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import MTG_bot.core.ability_tree as at  # noqa: E402
from tools.audit import ontology_conformance as oc  # noqa: E402

_OID = "01020304-0506-4708-890a-0b0c0d0e0f10"
_BF = at.Zone(kind=at.ZoneKind.BATTLEFIELD, controller=at.ControllerRef.ANY)


def _fa(s: str) -> at.FAtom:
    return at.FAtom(pred=at.FAtomPred.TYPE_EQ, string_value=s)


def _atom(verb: at.Verb, subtype: str) -> at.Atom:
    return at.Atom(
        verb=verb,
        args=at.AtomArgs(
            pairs=(
                (
                    "target",
                    at.Selector(
                        at.QConst(1), at.SelectorMode.TARGET, _fa(subtype), zones=(_BF,)
                    ),
                ),
            )
        ),
    )


def _card(name: str, **over) -> at.CardRecord:
    base = dict(
        oracle_id=_OID,
        name=name,
        type_line="Creature — Cat",
        types=("Creature",),
        subtypes=("Cat",),
        supertypes=(),
        colors=("W",),
        color_identity=frozenset({"W"}),
        mana_cost=None,
        mana_value=1,
        power=at.QConst(1),
        toughness=at.QConst(1),
        loyalty=None,
        keywords=(),
        abilities=(),
        is_token=False,
    )
    base.update(over)
    return at.CardRecord(**base)


def _suite(**cards) -> dict:
    return {"FIX": {oid: c for oid, c in cards.items()}}


# --------------------------------------------------------------------------
# V2′ phantom detection (synthetic TPs)
# --------------------------------------------------------------------------
def test_v2_detects_seq_single_child():
    card = _card(
        "Phantom Seq",
        abilities=(at.StaticAbility(effect=at.Seq((_atom(at.Verb.TAP, "Cat"),))),),
    )
    out = oc.check_v2(_suite(a=card), {"choose_count_eq_len": []})
    assert out["seq_single_child"] == ["FIX:Phantom Seq"]


def test_v2_detects_single_child_filter():
    card = _card(
        "Phantom FAnd",
        abilities=(
            at.StaticAbility(
                effect=_atom(at.Verb.TAP, "Cat"), condition=at.FAnd((_fa("Cat"),))
            ),
            at.StaticAbility(
                effect=_atom(at.Verb.TAP, "Cat"), condition=at.FOr((_fa("Cat"),))
            ),
        ),
    )
    out = oc.check_v2(_suite(a=card), {"choose_count_eq_len": []})
    assert sorted(out["filter_single_child"]) == [
        "FIX:Phantom FAnd:FAnd",
        "FIX:Phantom FAnd:FOr",
    ]


def test_v2_detects_phantom_menu_and_honours_the_whitelist():
    phantom = _card(
        "Choose All",
        abilities=(
            at.StaticAbility(
                effect=at.Choose(
                    at.QConst(2),
                    (_atom(at.Verb.TAP, "Cat"), _atom(at.Verb.UNTAP, "Cat")),
                )
            ),
        ),
    )
    out = oc.check_v2(_suite(a=phantom), {"choose_count_eq_len": []})
    assert out["choose_count_eq_len"] == ["FIX:Choose All"]
    wled = oc.check_v2(_suite(a=phantom), {"choose_count_eq_len": ["Choose All"]})
    assert wled["choose_count_eq_len"] == []
    assert wled["choose_count_eq_len_whitelisted"] == ["FIX:Choose All"]


def test_v2_clean_on_legal_shapes():
    """The negative control: a real conjunction, a two-step Seq, a real menu
    and the MEANINGFUL empty wrappers are all legal."""
    card = _card(
        "Legal",
        abilities=(
            at.StaticAbility(
                effect=_atom(at.Verb.TAP, "Cat"),
                condition=at.FAnd((_fa("Cat"), _fa("Bird"))),
            ),
            at.StaticAbility(
                effect=at.Seq((_atom(at.Verb.TAP, "Cat"), _atom(at.Verb.UNTAP, "Bird")))
            ),
            at.StaticAbility(
                effect=at.Choose(
                    at.QConst(1),
                    (_atom(at.Verb.TAP, "Cat"), _atom(at.Verb.UNTAP, "Bird")),
                )
            ),
            at.StaticAbility(effect=_atom(at.Verb.TAP, "Cat"), condition=at.FAnd(())),
        ),
    )
    out = oc.check_v2(_suite(a=card), {"choose_count_eq_len": []})
    assert out["seq_single_child"] == []
    assert out["filter_single_child"] == []
    assert out["choose_count_eq_len"] == []


# --------------------------------------------------------------------------
# V3′ split designation (WARN) — TP + the two legal exclusions
# --------------------------------------------------------------------------
def _seq_with_selectors(step_selectors):
    steps = []
    for sel, verb in step_selectors:
        steps.append(at.Atom(verb=verb, args=at.AtomArgs(pairs=(("target", sel),))))
    return at.StaticAbility(effect=at.Seq(tuple(steps)))


def _target_sel(subtype="Cat", referent=None):
    """A fresh TARGET selector, or the C2 anaphora shape (mode CHOOSE,
    referent-bound, neutral zone) that V3′ must exclude."""
    if referent is None:
        return at.Selector(
            at.QConst(1), at.SelectorMode.TARGET, _fa(subtype), zones=(_BF,)
        )
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        _fa(subtype),
        zones=(at.Zone(kind=at.ZoneKind.ANY, controller=at.ControllerRef.ANY),),
        referent=referent,
    )


def test_v3_fires_on_re_designation():
    sel = _target_sel()
    card = _card(
        "Split",
        abilities=(_seq_with_selectors([(sel, at.Verb.TAP), (sel, at.Verb.UNTAP)]),),
    )
    out = oc.check_v3(_suite(a=card))
    assert len(out["split_seq_designations"]) == 1
    assert "Split" in out["split_seq_designations"][0]


def test_v3_excludes_referent_and_non_target_modes():
    """Legal identical repeats: anaphora (referent-bound) and all-of loops."""
    anaphora = _card(
        "Anaphora",
        abilities=(
            _seq_with_selectors(
                [
                    (_target_sel(), at.Verb.TAP),
                    (_target_sel(referent="target"), at.Verb.UNTAP),
                ]
            ),
        ),
    )
    assert oc.check_v3(_suite(a=anaphora))["split_seq_designations"] == []
    all_mode = at.Selector(
        at.QUnbounded(), at.SelectorMode.ALL, _fa("Cat"), zones=(_BF,)
    )
    loops = _card(
        "AllLoop",
        abilities=(
            _seq_with_selectors([(all_mode, at.Verb.TAP), (all_mode, at.Verb.UNTAP)]),
        ),
    )
    assert oc.check_v3(_suite(a=loops))["split_seq_designations"] == []


# --------------------------------------------------------------------------
# V1′ field-coverage drift control
# --------------------------------------------------------------------------
def test_v1_clean_on_the_live_module():
    out = oc.check_v1()
    assert out["unclassified"] == [] and out["stale"] == []
    # re-pinned 2026-10-30: R5-11 adds the container field TokenSpec.colors (26)
    assert out["container_fields"] == out["classify_tokens"] == 26


def test_v1_reports_unclassified_and_stale(monkeypatch):
    real = dict(oc.CLASSIFY)
    broken = {k: v for k, v in real.items() if k != ("FAtom", "colors")}
    broken[("NoSuchClass", "no_such_field")] = "SET-R1a"
    monkeypatch.setattr(oc, "CLASSIFY", broken)
    out = oc.check_v1()
    assert "FAtom.colors" in out["unclassified"]
    assert "NoSuchClass.no_such_field" in out["stale"]


# --------------------------------------------------------------------------
# V5′ SET-R1a order canonicalization of census signatures
# --------------------------------------------------------------------------
def test_canon_struct_sig_sorts_children_not_time_or_menu():
    s = "FAnd(children=[2]{Z;A})"
    assert oc._canon_struct_sig(s) == "FAnd(children=[2]{A;Z})"
    # TIME and MENU containers are NOT touched (their order is semantics)
    steps = "Seq(steps=[2]{Z;A})"
    assert oc._canon_struct_sig(steps) == steps
    # nested groups canonicalize innermost-out, and the transform is idempotent
    nested = "FOr(children=[2]{FAnd(children=[2]{Z;A});B})"
    once = oc._canon_struct_sig(nested)
    assert once == "FOr(children=[2]{B;FAnd(children=[2]{A;Z})})"
    assert oc._canon_struct_sig(once) == once
    # malformed / marker-free input passes through untouched
    assert oc._canon_struct_sig(
        "Atom(verb=~,args=AtomArgs(pairs=[1]{[2]{<S>;QConst}}))"
    ) == ("Atom(verb=~,args=AtomArgs(pairs=[1]{[2]{<S>;QConst}}))")


def test_canon_struct_sig_sorts_all_set_r1a_groups():
    # FAtom.colors is a SET-R1a field: a pure colours re-order must not
    # register as a census shape change (found live as a CastSpellEvent pair).
    pre = "CastSpellEvent(filter=FAtom(colors=[4]{W;U;B;R},who=0))"
    post = "CastSpellEvent(filter=FAtom(colors=[4]{B;R;U;W},who=0))"
    assert oc._canon_struct_sig(pre) == oc._canon_struct_sig(post)
    # initial_counters (EtBState) is the dict-keyed SET field
    a = "EtBState(initial_counters=[2]{MINUS_1_MINUS_1;PLUS_1_PLUS_1})"
    b = "EtBState(initial_counters=[2]{PLUS_1_PLUS_1;MINUS_1_MINUS_1})"
    assert oc._canon_struct_sig(a) == oc._canon_struct_sig(b)
    # an ACTUAL content change inside a set group still survives the canon
    assert oc._canon_struct_sig("FAnd(children=[2]{A;B})") != oc._canon_struct_sig(
        "FAnd(children=[2]{A;C})"
    )


# --------------------------------------------------------------------------
# V4′ FAIL-CLOSED (R1a diff-gate B2): a missing baseline is never a green
# --------------------------------------------------------------------------
def test_v4_missing_baseline_fails_closed(tmp_path):
    v4 = oc.check_v4({"M21": {"Foo": 1}}, tmp_path / "absent.json", False)
    assert v4.get("baseline_missing") is True
    assert v4["baseline_written"] is False


def test_v4_missing_baseline_fails_closed_cli(tmp_path, monkeypatch):
    monkeypatch.setattr(oc, "V4_BASELINE", tmp_path / "no_such_baseline.json")
    rc = oc.main(["--sets", "M21"])
    assert rc != 0, "CLI must exit nonzero when the V4 baseline is missing"


# --------------------------------------------------------------------------
# V4′ SHAPE-HASH PROBES (R3 /141 §6): deletions and tag/filter swaps fail
# even when the node COUNTS do not move (the count-only blind spot).
# --------------------------------------------------------------------------
def _v4_probe_baseline(tmp_path, obj):
    p = tmp_path / "v4_shape_baseline.json"
    p.write_text(json.dumps(obj))
    return p


def test_v4_shape_probe_clean_passes(tmp_path):
    cur = {"M21": {"Foo": {"count": 2, "shapes": ["a1", "b2"]}}}
    v4 = oc.check_v4(cur, _v4_probe_baseline(tmp_path, cur), False)
    assert v4["new_emissions"] == []


def test_v4_shape_probe_deletion_fails(tmp_path):
    base = {"M21": {"Foo": {"count": 2, "shapes": ["a1", "b2"]}}}
    cur = {"M21": {"Foo": {"count": 1, "shapes": ["a1"]}}}
    v4 = oc.check_v4(cur, _v4_probe_baseline(tmp_path, base), False)
    assert any("REMOVED" in e for e in v4["new_emissions"]), v4["new_emissions"]


def test_v4_shape_probe_tag_or_filter_swap_fails_at_constant_count(tmp_path):
    # THE count-only blind spot: identical counts, a node whose tag/filter
    # was swapped — the old census saw 2 -> 2 and stayed green.
    base = {"M21": {"Foo": {"count": 2, "shapes": ["a1", "b2"]}}}
    cur = {"M21": {"Foo": {"count": 2, "shapes": ["a1", "c3"]}}}
    v4 = oc.check_v4(cur, _v4_probe_baseline(tmp_path, base), False)
    assert any("SWAPPED" in e for e in v4["new_emissions"]), v4["new_emissions"]
    assert any("REMOVED" in e for e in v4["new_emissions"]), v4["new_emissions"]


# --------------------------------------------------------------------------
# V4′ EXTINCTION PROBES (R3 diff-gate follow-up, FIX-1 /144 verdict
# FIX-THEN-GO): the first check_v4 iterated CURRENT names only, so whole-
# card CHOOSE extinction (rename, drop, last node deleted -> card leaves
# the census) passed silently. Union-iteration + count-comparison fix.
# --------------------------------------------------------------------------
@dataclasses.dataclass
class _XArgs:
    pairs: tuple


@dataclasses.dataclass
class _XStep:
    verb: str
    args: _XArgs


@dataclasses.dataclass
class _XCard:
    name: str
    abilities: tuple


def _x_card(sel, name="Extinction Probe"):
    # gate pattern borrowed from /tmp/opencode/r3gate/probe_freeze.py:
    # CHOOSE selector nested at args.pairs[0][1] (container-nested leaf).
    return _XCard(name, (_XStep("SEARCH", _XArgs(pairs=(("cards", sel),))),))


def _x_sel(count=1):
    return at.Selector(
        at.QConst(count),
        at.SelectorMode.CHOOSE,
        at.FAnd(()),
        zones=(at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU),),
    )


def test_v4_whole_card_extinction_fails(tmp_path):
    base = {"M21": {"Goner": {"count": 2, "shapes": ["a1", "b2"]}}}
    v4 = oc.check_v4({"M21": {}}, _v4_probe_baseline(tmp_path, base), False)
    assert any("Goner" in e and "REMOVED" in e for e in v4["new_emissions"]), (
        "card-level CHOOSE extinction must error (BREAK-R3-1)",
        v4["new_emissions"],
    )


def test_v4_whole_set_extinction_fails(tmp_path):
    base = {"M21": {"Foo": {"count": 1, "shapes": ["a1"]}}}
    v4 = oc.check_v4({}, _v4_probe_baseline(tmp_path, base), False)
    assert any("Foo" in e and "REMOVED" in e for e in v4["new_emissions"]), (
        "dropping a whole SET's census must error",
        v4["new_emissions"],
    )


def test_v4_count_decrease_at_identical_shapes_fails(tmp_path):
    # Two byte-identical selectors at different index-paths have different
    # signatures, BUT a hand-crafted (or shape-collapsing) census can lose
    # a node with the shape SET unchanged: the count comparison is the
    # belt that makes REMOVED count-level, not just name-level.
    base = {"M21": {"Foo": {"count": 2, "shapes": ["a1"]}}}
    cur = {"M21": {"Foo": {"count": 1, "shapes": ["a1"]}}}
    v4 = oc.check_v4(cur, _v4_probe_baseline(tmp_path, base), False)
    assert any("count" in e for e in v4["new_emissions"]), v4["new_emissions"]


def test_v4_ir_card_deleted_fails(tmp_path):
    # IR-level red-first (borrowed gate pattern): single CHOOSE node at
    # pairs[0][1]; deleting it makes the card LEAVE the census entirely.
    cards = {"M21": {"oid1": _x_card(_x_sel())}}
    cen = oc.choose_census(cards)
    assert cen["M21"]["Extinction Probe"]["count"] == 1
    bl = _v4_probe_baseline(tmp_path, cen)
    gone = {"M21": {}}  # card dropped from the pool (rename/drop)
    v4 = oc.check_v4(oc.choose_census(gone), bl, False)
    assert any("REMOVED" in e for e in v4["new_emissions"]), (
        "card deleted from IR => V4′ must FAIL",
        v4["new_emissions"],
    )


def test_v4_ir_last_node_deleted_fails(tmp_path):
    # Same card, node extinct via mode swap CHOOSE->ALL: card leaves the
    # census (choose_census omits zero-node cards) — the name-level hole.
    cards = {"M21": {"oid1": _x_card(_x_sel())}}
    cen = oc.choose_census(cards)
    bl = _v4_probe_baseline(tmp_path, cen)
    silent = {
        "M21": {
            "oid1": _x_card(dataclasses.replace(_x_sel(), mode=at.SelectorMode.ALL))
        }
    }
    v4 = oc.check_v4(oc.choose_census(silent), bl, False)
    assert any("REMOVED" in e for e in v4["new_emissions"]), (
        "last CHOOSE node deleted => V4′ must FAIL",
        v4["new_emissions"],
    )


def test_v4_ir_honest_recensus_passes(tmp_path):
    cards = {"M21": {"oid1": _x_card(_x_sel())}}
    cen = oc.choose_census(cards)
    v4 = oc.check_v4(oc.choose_census(cards), _v4_probe_baseline(tmp_path, cen), False)
    assert v4["new_emissions"] == [], v4["new_emissions"]


def test_v4_shape_sig_moves_with_tag_field_and_selector():
    sel = at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        at.FAnd(()),
        zones=(at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU),),
    )
    sig = oc._choose_shape("Atom", "target", sel)
    assert sig == oc._choose_shape("Atom", "target", sel)  # rebuild-stable
    assert sig != oc._choose_shape("CostTap", "target", sel)  # TAG swap
    assert sig != oc._choose_shape("Atom", "cards", sel)  # holder field swap
    moved_zone = dataclasses.replace(
        sel,
        zones=(at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.YOU),),
    )
    assert sig != oc._choose_shape("Atom", "target", moved_zone)  # FILTER/zone
    assert sig != oc._choose_shape(
        "Atom", "target", dataclasses.replace(sel, count=at.QConst(2))
    )  # count shape
    # R3: index path keeps two byte-identical selectors in one field
    # (pairs[2][1] vs pairs[5][1]) from collapsing into one signature.
    assert sig != oc._choose_shape("Atom", "target", sel, (2,))
    assert sig != oc._choose_shape("Atom", "target", sel, (5,))
    assert oc._choose_shape("Atom", "target", sel, (2,)) != oc._choose_shape(
        "Atom", "target", sel, (5,)
    )


# --------------------------------------------------------------------------
# V5′ R1a content delta: authoritative over the truncated committed view
# --------------------------------------------------------------------------
def test_v5_r1a_content_delta_is_the_two_unwraps():
    v5 = oc.check_v5({})  # live harvest unused when artefacts exist
    if not v5.get("available"):
        pytest.skip("committed census baseline absent")
    delta = v5["r1a_content_delta"]
    assert delta["available"], "R1a full census artefacts missing"
    # the ONLY content-level map effect of R1a is the FAnd single-child
    # unwrap at its two emission sites (Negate: FNot, Dauntless: FAtom)
    assert delta["new_struct_sig_count"] == 2, delta["new_struct_sigs"]
    assert delta["gone_struct_sig_count"] == 2, delta["gone_struct_sigs"]
    assert delta["new_branching_count"] == 1
    assert delta["gone_branching_count"] == 2  # one row merges into an existing
    assert all("FAnd(children=[1]" in s for s in delta["gone_struct_sigs"])
    assert all(
        "children" not in s.split("filter=")[-1] for s in delta["new_struct_sigs"]
    )


def test_v5_live_new_branchings_are_all_census_tail_rows(compiled):
    # Every branching the live-vs-committed view calls NEW exists in the
    # uncapped POST census => it is a top-40 truncation artefact of the
    # committed baseline, not a checker harvest bug.
    v5 = oc.check_v5(compiled)
    delta = v5["r1a_content_delta"]
    if not delta.get("available"):
        pytest.skip("uncapped census artefacts absent")
    post = json.loads((oc.REPO / delta["post"]).read_text())

    def fold_menu(menu: str) -> str:
        # R0 zone-fold re-pin: the frozen R1a-era census rows predate the
        # zone+zones fold; a single-zone menu relabels 1:1 (zone: -> zones:).
        return menu.replace(" zone:", " zones:")

    tail = {
        cls: {
            (
                fold_menu(oc._canon_fshape(r["menu"])),
                r["count_kind"],
                tuple(oc._canon_fshape(c) for c in r["children"]),
            )
            for r in rows
        }
        for cls, rows in post["C_branching"]["branchings"].items()
    }
    # R0 zone-fold: fused multi-zone menus (zones:A+B) exist ONLY in the
    # post-fold census; merge its uncapped rows when the artifact is there.
    r0_full = oc.REPO / "reports" / "ontology_census_2026-10-19_r0_post_full.json"
    if r0_full.exists():
        r0 = json.loads(r0_full.read_text())
        for cls, rows in r0["C_branching"]["branchings"].items():
            tail.setdefault(cls, set()).update(
                (
                    oc._canon_fshape(r["menu"]),
                    r["count_kind"],
                    tuple(oc._canon_fshape(c) for c in r["children"]),
                )
                for r in rows
            )
    checked = 0
    for cls, row_strs in v5["new_branchings"].items():
        for s in row_strs:
            menu, cnt, kids = s.split(" / ", 2)
            key = (menu, cnt, tuple(ast.literal_eval(kids)))
            assert key in tail.get(cls, set()), f"{cls}:{s[:80]} in neither census"
            checked += 1
    assert checked > 0, "no live-new branchings to classify (view changed?)"


# --------------------------------------------------------------------------
# Corpus guard: the R1a exit condition stays true
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def compiled():
    return oc.compile_pools(("M21",))


def test_corpus_has_no_phantoms_and_no_new_choose_emissions(compiled):
    cards = {s: v["cards"] for s, v in compiled.items()}
    v2 = oc.check_v2(cards, oc._load_whitelist())
    assert v2["seq_single_child"] == []
    assert v2["filter_single_child"] == []
    assert v2["choose_count_eq_len"] == []
    assert v2["choose_count_eq_len_whitelisted"] == []
    v4 = oc.check_v4(
        oc.choose_census(cards), oc.V4_BASELINE, False, sets=("M21",)
    )  # fixture compiles M21 only (R1a scope); union-strictness is pinned by
    # the extinction probes above and the full CLI run.
    assert v4["baseline_written"] is False
    assert v4["new_emissions"] == [], v4["new_emissions"]


def test_corpus_filters_are_construction_sorted(compiled):
    """Every FAnd/FOr in the compiled pools is canonically sorted and has no
    same-class child — the SET-R1a law, verified on 305 compiled cards."""
    import dataclasses

    from MTG_bot.core.ability_tree import canonical_json

    checked = 0
    for entry in compiled.values():
        cards = entry["cards"]
        for card in cards.values():
            for node in oc.iter_nodes(card):
                if type(node).__name__ in ("FAnd", "FOr"):
                    kids = list(node.children)
                    assert kids == sorted(kids, key=canonical_json), card.name
                    assert not any(type(k) is type(node) for k in kids), card.name
                    checked += 1
    # M21 alone carries 337 FAnd/FOr nodes (measured at the R1a landing): the
    # guard is that the corpus really exercises the law hundreds of times.
    assert checked >= 300, f"expected hundreds of filters, got {checked}"
