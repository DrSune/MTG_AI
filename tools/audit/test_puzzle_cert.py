"""PZL certificate-harness pins for tools/audit/puzzle_cert.py.

Synthetic packs only (hermetic, sub-second): a LIT block puzzle (null dies,
gold lives), an attack-ladder whose first item clears the random<=0.05 gate
by 0.5**6 construction, the two NO-DISCRIMINATION classes (null pick == gold
and expect-insensitive), and a pure-assertion pack that must yield no items.
Every lane gets a discriminating twin — a harness that cannot fail is not
evidence (standing law).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import puzzle_cert as PC
import pytest

from MTG_bot.core.executor.games import get_supply


@pytest.fixture(scope="module")
def supply():
    return get_supply("all")


def creature(key, power, toughness, controller):
    return {
        "key": key,
        "name": key.title(),
        "power": power,
        "toughness": toughness,
        "type": "Creature",
        "zone": "battlefield",
        "controller": controller,
    }


# seat-1 thug attacks a life-5 defender; the scripted gold is the block ask,
# answered ONLY from the generic combat script (no block map) — so null
# (NONE) eats 2 and fails the expect while gold blocks and lives.
BLOCK_PUZZLE = {
    "world": {"life": 5, "seed": 7},
    "cards": [creature("thug", 2, 2, 1), creature("guard", 2, 2, 0)],
    "steps": [
        # combat_step demands the ACTIVE player (executor/__init__.py:1378);
        # the nine_lives pattern hands the turn to seat 1 first.
        {"op": "end_turn"},
        {"op": "advance_turn"},
        {"op": "combat", "seat": 1, "attack": {"thug": True}, "decisions": ["thug"]},
    ],
    "expect": {"life": {"0": 5, "1": 5}},
}

# six 2/2s must ALL attack or seat 1 never drops 20->8: item k's random score
# is 0.5**(6-k) — the first item is an L1 certificate by construction, the
# last is a coin flip (rejected at build by PZL rule 3, loudly).
ATTACK_LADDER = {
    "world": {"life": 20, "seed": 7},
    "cards": [creature(f"a{i}", 2, 2, 0) for i in range(6)],
    "steps": [{"op": "combat", "seat": 0, "decisions": ["ATTACK"] * 6}],
    "expect": {"life": {"1": 8, "0": 20}},
}

# gold attacks, but expect only asserts MY life — declining changes nothing
# the lanes can see: the expect-insensitive NO-DISCRIMINATION class.
INSENSITIVE = {
    "world": {"life": 20, "seed": 7},
    "cards": [creature("solo", 2, 2, 0)],
    "steps": [{"op": "combat", "seat": 0, "decisions": ["ATTACK"]}],
    "expect": {"life": {"0": 20}},
}

# the gold line IS the pass word: the null-pick-equals-gold class.
NULL_IS_GOLD = {
    "world": {"life": 20, "seed": 7},
    "cards": [creature("solo", 2, 2, 0)],
    "steps": [{"op": "combat", "seat": 0, "decisions": ["DECLINE"]}],
    "expect": {"life": {"0": 20, "1": 20}},
}

# pure assertion pack: rule-regression, never a ladder item.
NO_DECISIONS = {
    "world": {"life": 20, "seed": 7},
    "cards": [creature("wall", 0, 4, 1)],
    "steps": [{"op": "deal_damage", "source": "wall", "target": "wall", "amount": 1}],
    "expect": {"zone": {"wall": "graveyard"}},
}


# ------------------------------------------------------------- extraction


def test_block_item_extracted(supply):
    items = PC.extract_items(BLOCK_PUZZLE, supply)
    assert len(items) == 1
    it = items[0]
    assert it["ask_kind"] == "block"
    assert len(it["vocab"]) == 2  # (attacker handle, NONE)
    assert it["gold"] in it["vocab"]
    assert it["gold_script"] == "thug"  # written as a PACK KEY, resolved


def test_attack_ladder_extracts_six_chained_asks(supply):
    items = PC.extract_items(ATTACK_LADDER, supply)
    assert [i["ask_kind"] for i in items] == ["attack"] * 6
    assert [i["gold"] for i in items] == ["ATTACK"] * 6
    assert items == sorted(items, key=lambda i: i["ordinal"])  # chained order


def test_pure_assertion_pack_yields_no_items(supply):
    assert PC.extract_items(NO_DECISIONS, supply) == []


# ------------------------------------------------------------- certificates


def test_block_puzzle_is_null_certified(supply):
    (it,) = PC.certify_pack(Path("block_puzzle.json"), BLOCK_PUZZLE, supply)
    assert it["oracle"] == 1.0
    assert it["null"] == 0.0  # the do-nothing policy dies on the threat
    assert it["punish_inaction"] is True
    assert it["no_discrimination"] is False
    assert 0.4 <= it["random"] <= 0.6  # a coin flip: rule-3 rejected, loudly
    assert it["l1_ready"] is False  # honest: a 2-candidate coin flip is L1 BAIT


def test_attack_ladder_difficulty_gradient(supply):
    its = PC.certify_pack(Path("attack_ladder.json"), ATTACK_LADDER, supply)
    assert all(i["null"] == 0.0 and i["punish_inaction"] for i in its)
    # 0.5**6 by construction: the first item clears the PZL rule-3 gate
    assert its[0]["random"] <= PC.RANDOM_CEILING
    assert its[0]["l1_ready"] is True
    # ...and the LAST chained ask is a coin flip — the ladder gradient is real
    assert its[-1]["random"] > 0.05
    assert its[-1]["l1_ready"] is False
    # monotone: later asks have MORE surviving randomness
    assert [i["random"] for i in its] == sorted(i["random"] for i in its)


def test_expect_insensitive_offender_flagged(supply):
    (it,) = PC.certify_pack(Path("insensitive.json"), INSENSITIVE, supply)
    assert it["null"] == 1.0
    assert it["no_discrimination"] is True
    assert it["l1_ready"] is False
    assert it["null_pick"] == "DECLINE" != it["gold"]
    assert it["null_gt0_reason"].startswith("expect-insensitive")


def test_null_pick_equals_gold_offender_flagged(supply):
    (it,) = PC.certify_pack(Path("null_is_gold.json"), NULL_IS_GOLD, supply)
    assert it["null"] == 1.0
    assert it["null_pick"] == it["gold"] == "DECLINE"
    assert it["null_gt0_reason"] == "null-pick-equals-gold"
    assert it["punish_inaction"] is False


# ------------------------------------------------------------- harness law


def test_certificates_reproducible_d9_seeds_rotated(supply):
    """D9: rollout seeds are rotated per rollout — yet FIXED per harness run,
    so the whole census is reproducible byte-for-byte."""
    a = PC.certify_pack(Path("b.json"), BLOCK_PUZZLE, supply, rollouts=40)
    b = PC.certify_pack(Path("b.json"), BLOCK_PUZZLE, supply, rollouts=40)
    assert a == b
    seeds = {PC._stable_int("7|block:0|0"), PC._stable_int("7|block:0|1")}
    assert len(seeds) == 2  # rotation: distinct seed per rollout index


def test_vanilla_lane_untouched_by_instrumentation(supply, tmp_path):
    """Idle patches are identity: a gold-line replay through the patched
    runner equals the UNPATCHED run_scenarios.run_pack verdict."""
    from tools.run_scenarios import run_pack

    f = tmp_path / "block.json"
    f.write_text(json.dumps(BLOCK_PUZZLE))
    assert run_pack(f, supply) == []  # green unpatched
    assert PC.replay(BLOCK_PUZZLE, supply) is True  # green through the patch
    assert PC._policy is None and PC._recorder is None  # no state leaked


def test_corpus_writer_schema(supply, tmp_path):
    d = tmp_path / "packs"
    d.mkdir()
    for name, pack in (
        ("block.json", BLOCK_PUZZLE),
        ("ladder.json", ATTACK_LADDER),
        ("assertion.json", NO_DECISIONS),
    ):
        (d / name).write_text(json.dumps(pack))
    items, summary = PC.certify_dir(d, supply, rollouts=50)
    assert len(items) == 7  # 1 block + 6 chained attack asks
    assert summary["items"] == 7
    assert summary["packs_scanned"] == 3
    assert summary["packs_with_decisions"] == 2
    required = {
        "card",
        "ask_kind",
        "candidates_n",
        "gold",
        "null",
        "random",
        "oracle",
        "punish_inaction",
        "l1_ready",
    }
    for it in items:
        assert required <= set(it)
    assert summary["l1_ready"] >= 1
    assert summary["null_gt0_offenders"] == []
    assert summary["broken_packs"] == []
    # json round-trip discipline: everything emitted is serialisable
    assert json.loads(json.dumps({"summary": summary, "items": items}))


# ------------------------------------------------- honest reclassification


def test_pack_level_reclassification_exempts_offender(supply):
    import copy

    p = copy.deepcopy(NULL_IS_GOLD)
    p["eval_reclassification"] = {"reason": "branch-coverage negative twin"}
    (it,) = PC.certify_pack(Path("null_is_gold.json"), p, supply)
    # scores are kept honest, the OFFENDER flag and ladder eligibility drop
    assert it["null"] == 1.0 and it["null_pick"] == it["gold"]
    assert it["reclassified"] is True and it["no_discrimination"] is False
    assert it["reclass_reason"] == "branch-coverage negative twin"


def test_by_ask_kind_reclassification_is_item_granular(supply):
    import copy

    probe = PC.certify_pack(Path("ladder.json"), copy.deepcopy(ATTACK_LADDER), supply)
    kind = probe[0]["ask_kind"]
    p = copy.deepcopy(ATTACK_LADDER)
    p["steps"][0]["eval_reclassification"] = {"by_ask_kind": {kind: "declared twin"}}
    for it in PC.certify_pack(Path("ladder.json"), p, supply):
        assert it["reclassified"] is True and it["no_discrimination"] is False
    # a kind that never matches reclassifies NOTHING (item-level precision)
    p2 = copy.deepcopy(ATTACK_LADDER)
    p2["steps"][0]["eval_reclassification"] = {"by_ask_kind": {"no_such_kind": "x"}}
    assert not any(
        i["reclassified"] for i in PC.certify_pack(Path("ladder.json"), p2, supply)
    )


# ------------------------------------------- FAIL-REGISTERED (2026-10-07)


def test_fail_registered_verdict_is_counted_not_deleted(supply, tmp_path):
    """A reclassification is a REGISTERED FAIL: it stays in the ledger and
    the summary counts (by verdict), excluded from pass rate only."""
    import copy

    p = copy.deepcopy(NULL_IS_GOLD)
    p["eval_reclassification"] = {
        "reason": "branch twin, evidence: null word is gold",
        "verdict": "true-no-decision",
    }
    d = tmp_path / "packs"
    d.mkdir()
    (d / "null_is_gold.json").write_text(json.dumps(p))
    items, summary = PC.certify_dir(d, supply, rollouts=20)
    assert items, "registered fails must STAY in the ledger"
    assert all(i["fail_registered"] and not i["l1_ready"] for i in items)
    assert all(i["fail_verdict"] == "true-no-decision" for i in items)
    assert summary["fail_registered"] == len(items)
    assert summary["fail_registered_by_verdict"] == {"true-no-decision": len(items)}
    # counted in the summary, yet absent from pass material AND offender list
    assert summary["l1_ready"] == 0 and summary["null_gt0_offenders"] == []


def test_untriaged_reclassification_fails_the_runner_gate():
    """tools/run_scenarios.py rejects bare-string / verdictless reclass —
    silent reclassification (the 2026-10-07 false-premise hiding pattern)."""
    import copy

    from tools.run_scenarios import RECLASS_VERDICTS, _triage_check

    p = copy.deepcopy(NULL_IS_GOLD)
    assert _triage_check(p) == []  # no reclassification: nothing to triage
    p["eval_reclassification"] = {"reason": "legacy silent exemption"}
    (bad,) = _triage_check(p)
    assert "verdict" in bad
    p["eval_reclassification"] = {"reason": "x", "verdict": "hides-the-bug"}
    assert _triage_check(p)  # unknown verdicts rejected: {RECLASS_VERDICTS}
    p["steps"][0]["eval_reclassification"] = "bare string, no triage"
    p.pop("eval_reclassification")
    assert any("step 0" in b for b in _triage_check(p))
    # by_ask_kind granularity carries evidence and verdict at the dict level
    p2 = copy.deepcopy(NULL_IS_GOLD)
    p2["steps"][0]["eval_reclassification"] = {
        "verdict": RECLASS_VERDICTS[1],
        "by_ask_kind": {"choose": "engine gap, see legality.py"},
    }
    assert _triage_check(p2) == []
