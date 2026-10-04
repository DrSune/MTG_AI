"""BUGCATCH B4a matcher pins for tools/audit/branch_coverage.py.

Synthetic journal-shaped Games only — no engine game runs here (hermetic
and fast, mirroring the test_detectors.py discipline). Every matcher lane
gets a LIT fixture and its discriminating DARK/UNMATCHABLE twin: a lane
that cannot fail is not evidence (standing law).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import branch_coverage as BC
import detectors as D

CARD = "Test Card"
TAG = "card:3"  # the card's own handle in every fixture below
VERBS = {"DISCARD", "CAST", "DEAL_DAMAGE", "SACRIFICE", "UNTAP"}


def row(
    clock: int,
    kind: str,
    subject: str,
    cause: str,
    verb: str,
    data: tuple[object, ...] | None = None,
) -> D.Row:
    return D.Row(clock, clock, kind, subject, cause, verb, data)


def game(rows: list[D.Row], source: str = "pack:fixture.json") -> BC.Game:
    return BC.Game(source, rows, {TAG: CARD, "card:9": "Other Spell"})


def branch(kind: str, jk: str, pred: str, bid: str = "test:01:X") -> dict:
    return {
        "branch_id": bid,
        "kind": kind,
        "signature": {"journal_kind": jk, "data_predicate": pred},
    }


def match(br: dict, rows: list[D.Row], verbs: set[str] | None = None) -> BC.Verdict:
    return BC.match_branch(CARD, br, [game(rows)], verbs or VERBS)


# ---------------------------------------------------------------- verb lane

VERB_BRANCH = branch(
    "Conditional", "ZONE_CHANGE", "row for verb DISCARD present iff MAY_DONE"
)


def test_verb_present_lit():
    v = match(VERB_BRANCH, [row(5, "ZONE_CHANGE", "card:9", TAG, "DISCARD")])
    assert v.status == BC.LIT
    assert v.matched_by == ["pack:fixture.json"]


def test_verb_wrong_kind_stays_dark():
    # same verb+attribution but the row kind is outside the signature kinds
    v = match(VERB_BRANCH, [row(5, "TAP_STATE", "card:9", TAG, "DISCARD")])
    assert v.status == BC.DARK


def test_verb_unattributed_stays_dark():
    # the discard happened, but nothing about it names the card
    v = match(VERB_BRANCH, [row(5, "ZONE_CHANGE", "card:9", "card:8", "DISCARD")])
    assert v.status == BC.DARK


def test_attribution_through_data_payload():
    # TARGETING-style: the card only appears inside the data tuple
    br = branch("OptionalEffect", "NONE", "row for verb SACRIFICE present == may")
    v = match(
        br, [row(6, "ZONE_CHANGE", "card:9", "card:9", "SACRIFICE", ("tag", TAG))]
    )
    assert v.status == BC.LIT


def test_unobserved_verb_is_unmatchable():
    br = branch("OptionalEffect", "NONE", "row for verb SHUFFLE present == may")
    v = match(br, [row(5, "ZONE_CHANGE", "card:9", TAG, "DISCARD")])
    assert v.status == BC.UNMATCHABLE
    assert "SHUFFLE" in v.missing


# ---------------------------------------------------------------- CAST lane

CAST_BRANCH = branch(
    "OptionalEffect", "CAST", "row for verb CAST present == may-accepted"
)


def test_own_casting_never_lights_the_may_cast_side():
    # subject == the card itself is the card's OWN casting (13b law)
    v = match(CAST_BRANCH, [row(4, "CAST", TAG, TAG, "CAST")])
    assert v.status == BC.DARK


def test_effect_cast_lit_and_fanout():
    # the may side: a DIFFERENT spell, attributable to the card via data
    rows = [
        row(4, "CAST", TAG, TAG, "CAST"),  # own cast
        row(7, "CAST", "card:9", "card:9", "CAST", (TAG, 1)),  # effect cast
    ]
    v = match(CAST_BRANCH, rows)
    assert v.status == BC.LIT
    assert all("subj=card:9" in e for e in v.evidence)


# ------------------------------------------------------- mode-choice lane


def test_choose_mode_is_unmatchable_with_reason():
    br = branch(
        "Choose", "ZONE_CHANGE", "data carries chosen mode index (one row per option)"
    )
    v = match(br, [row(5, "ZONE_CHANGE", "card:9", TAG, "MOVE_ZONE")])
    assert v.status == BC.UNMATCHABLE
    assert "chosen-mode" in v.missing


# -------------------------------------------------- targeting-cardinality


def test_one_of_lit_rest_dark_on_single_designation():
    rows = [row(3, "TARGETING", "card:9", TAG, "TARGET", (TAG, "player:0"))]
    one = branch(
        "Selector:ONE_OF",
        "TARGETING",
        "designation row's chosen-set cardinality differs per branch",
    )
    rest = branch(
        "Selector:REST",
        "TARGETING",
        "designation row's chosen-set cardinality differs per branch",
    )
    assert match(one, rows).status == BC.LIT
    assert match(rest, rows).status == BC.DARK


def test_rest_lit_on_multi_designation():
    rows = [
        row(3, "TARGETING", "card:9", TAG, "TARGET", (TAG, "player:0")),
        row(4, "TARGETING", "card:5", TAG, "TARGET", (TAG, "player:0")),
    ]
    rest = branch(
        "Selector:REST",
        "TARGETING",
        "designation row's chosen-set cardinality differs per branch",
    )
    assert match(rest, rows).status == BC.LIT


def test_partition_modes_are_not_lumped_into_each_other():
    rows = [
        row(3, "TARGETING", "card:9", TAG, "ONE_OF", (TAG, "player:0")),
        row(4, "TARGETING", "card:8", TAG, "REST", (TAG, "player:0")),
        row(5, "TARGETING", "card:7", TAG, "REST", (TAG, "player:0")),
    ]
    one = branch(
        "Selector:ONE_OF",
        "TARGETING",
        "designation row's chosen-set cardinality differs per branch",
    )
    rest = branch(
        "Selector:REST",
        "TARGETING",
        "designation row's chosen-set cardinality differs per branch",
    )
    assert match(one, rows).status == BC.LIT
    assert match(rest, rows).status == BC.LIT


def test_rest_singleton_does_not_fake_one_of():
    rows = [row(3, "TARGETING", "card:9", TAG, "REST", (TAG, "player:0"))]
    one = branch(
        "Selector:ONE_OF",
        "TARGETING",
        "designation row's chosen-set cardinality differs per branch",
    )
    assert match(one, rows).status == BC.DARK


# ------------------------------------------------------------- dies lane


def test_died_branch_lit_by_own_cause_dark_by_own_subject():
    br = branch("Conditional", "CREATURE_DIES", "cause==own-handle & DIED_THIS_TURN")
    lit = match(br, [row(9, "CREATURE_DIES", "card:9", TAG, "DESTROY")])
    dark = match(br, [row(9, "CREATURE_DIES", TAG, "card:8", "DESTROY")])
    assert lit.status == BC.LIT
    assert dark.status == BC.DARK


# ------------------------------------------------------- fan-out (EachPlayer)


def test_eachplayer_fanout_counts_rows():
    br = branch(
        "EachPlayer",
        "DAMAGE",
        "one row per controller for verb DEAL_DAMAGE; count == seated players",
    )
    rows = [
        row(2, "DAMAGE", "player:0", TAG, "DEAL_DAMAGE", (3,)),
        row(3, "DAMAGE", "player:1", TAG, "DEAL_DAMAGE", (3,)),
    ]
    v = match(br, rows)
    assert v.status == BC.LIT
    assert v.matched_by == ["pack:fixture.json"]


# ------------------------------------------------------- corpus attribution


def test_corpus_lane_lights_by_identity_name():
    g = BC.Game(
        "corpus:7",
        [row(5, "TAP_STATE", "card:44", TAG, "UNTAP", (False,))],
        {TAG: CARD, "card:44": "Tapped Land"},
    )
    br = branch(
        "OptionalEffect", "TAP_STATE", "row for verb UNTAP present == may-accepted"
    )
    v = BC.match_branch(CARD, br, [g], VERBS)
    assert v.status == BC.LIT
    assert v.matched_by == ["corpus:7"]


# --------------------------------------------------------------- heat lane


def test_heat_is_dark_gated_and_scales_with_class_weight_and_hits():
    """§E: heat = dark x BCS x (1 + class weights) x (1 + anomaly_hits)."""
    results = [
        {"status": BC.DARK, "card": "Low", "branch_id": "low:01"},
        {"status": BC.DARK, "card": "High", "branch_id": "high:01"},
        {"status": BC.DARK, "card": "Hit", "branch_id": "hit:01"},
        {"status": BC.DARK, "card": "Zed", "branch_id": "zed:01"},
        {"status": BC.LIT, "card": "Lit", "branch_id": "lit:01"},
        {"status": BC.UNMATCHABLE, "card": "Unm", "branch_id": "unm:01"},
    ]
    darks = BC.attach_heat(
        results,
        {"Low": 10, "High": 10, "Hit": 10, "Zed": 10, "Lit": 99, "Unm": 99},
        {
            "High": ["branch_entanglement"],
            "Hit": ["single_fold"],
            "Zed": ["single_fold"],
        },
        {"Hit": 1},
    )
    # LIT/UNMATCHABLE carry no heat at all: the queue cannot point at a branch
    # already proven to fire.
    assert {d["card"] for d in darks} == {"Low", "High", "Hit", "Zed"}
    queue = BC.heat_queue(darks, {c: 10 for c in ("Low", "High", "Hit", "Zed")})
    assert [q["card"] for q in queue] == ["Hit", "High", "Zed", "Low"]
    assert queue[0]["heat"] == 40.0  # 10 x (1+1 class) x (1+1 anomaly hit)
    assert queue[1]["heat"] == 20.0  # 10 x (1+1 class) x (1+0 hits)
    assert queue[3]["heat"] == 10.0  # no flags, no hits: plain BCS
    # equal heat falls back to name, so the order is stable and reviewable
    assert queue[1]["classes"] == ["branch_entanglement"]
    assert queue[2]["classes"] == ["pt_layers"]


def test_class_weights_resolve_flags_through_the_C_table():
    assert BC.class_weight([]) == 0.0
    assert BC.class_weight(["single_fold"]) == 1.0  # -> pt_layers
    assert BC.class_weight(["single_fold", "keyword_x_consumer"]) == 2.0
    # an unrecognised flag is still priced, never silently free
    assert BC.class_weight(["something_new"]) == BC.UNKNOWN_CLASS_WEIGHT


def test_card_heat_rollup_counts_dark_branches():
    darks = [
        {"card": "One", "heat": 10.0},
        {"card": "Many", "heat": 10.0},
        {"card": "Many", "heat": 10.0},
        {"card": "Many", "heat": 4.0},
    ]
    per_card = {
        "One": {"bcs": 10, "dark": 1, "collision_flags": []},
        "Many": {"bcs": 10, "dark": 3, "collision_flags": []},
    }
    rollup = BC.card_heat_rollup(darks, per_card)
    assert [e["card"] for e in rollup] == ["Many", "One"]
    assert rollup[0]["heat"] == 24.0  # 3 dark x mean(10,10,4)=8
    assert rollup[0]["mean_branch_heat"] == 8.0
    assert rollup[1]["heat"] == 10.0


# ------------------------------------------------------- membership (§F PC-11)


def test_membership_is_derived_by_name_never_by_handle(tmp_path):
    import membership as MEM

    packs = tmp_path / "scenarios"
    packs.mkdir()
    # a real card is declared by PRINTED NAME in the "real" slot
    (packs / "a.json").write_text(
        '{"cards": [{"key": "sp", "real": "Secure the Scene", "zone": "hand"}]}',
        encoding="utf-8",
    )
    # a synthetic card spells itself "name" and is not real-card evidence
    (packs / "b.json").write_text(
        '{"cards": [{"key": "g", "name": "secure_the_scene", "zone": "battlefield"}]}',
        encoding="utf-8",
    )
    member = MEM.disk_membership(packs, tmp_path / "absent-suspects")
    assert member.get("Secure the Scene", {}).get("packs") == ["a.json"]
    assert "secure_the_scene" not in member, "handles must not confer membership"


def test_pc11_residue_counts_only_members_at_or_above_t(tmp_path):
    import membership as MEM

    bcs = {
        "cards": {
            "Rich Covered": {"bcs": 40, "in_pack": True, "handle": "rich_covered"},
            "Rich Bare": {"bcs": 40, "in_pack": False, "handle": "rich_bare"},
            "Cheap Bare": {"bcs": 1, "in_pack": False, "handle": "cheap_bare"},
        }
    }
    out = MEM.pc11(bcs, 20)
    assert out["cards_at_or_above_t"] == 2
    assert out["residue"] == 1 and out["residue_names"] == ["Rich Bare"]


def test_refresh_rewrites_stale_flags_and_keeps_an_audit_trail():
    import membership as MEM

    bcs = {
        "cards": {
            "Secure the Scene": {"in_pack": False, "in_suspect": True},
            "Never Seen": {"in_pack": True, "in_suspect": False},
        }
    }
    member = {"Secure the Scene": {"packs": ["a.json"], "suspects": []}}
    bcs, block = MEM.refresh(bcs, member)
    assert bcs["cards"]["Secure the Scene"] == {"in_pack": True, "in_suspect": False}
    assert bcs["cards"]["Never Seen"]["in_pack"] is False, "disk says no"
    assert block["before"] == {"in_pack": 1, "in_suspect": 1}
    assert block["after"] == {"in_pack": 1, "in_suspect": 0}
    assert block["changed_count"] == 2
