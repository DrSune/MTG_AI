"""/134 RL-pilot PRECONDITION 2 gates: sampling collection + off-policy audit.

Covers: (a) the row contract of ``--rl-collect`` jsonl rows (idx/logp/
rng_seed recorded, logp a true log-probability), (b) SAMPLER DETERMINISM
(same action-rng seed + same checkpoint => identical (idx, logp) sequence),
(c) the audit GREEN on freshly collected tiny games — recorded logπ ==
recomputed logπ at the collecting weights (max|Δ| <= tol), (d) audit RED:
tampered / deleted logp and a non-matching checkpoint all RAISE naming the
/83 pi_mix trap, and (e) the legacy eval ``--out`` record schema keeps no
rl keys (flag-gated, byte-identical lane).

Real checkpoint (bsh_S3a_s1_best.pt) + engine pool, 2 tiny games; the
module-scoped collection fixture is reused by every audit test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.eval.gameplay_eval_v2 import main as eval_main
from tools.eval.gameplay_eval_v2 import run_v2_game
from tools.training.rl_logprob_audit import audit

REPO = Path(__file__).resolve().parents[2]
NET = str(REPO / "tools" / "training" / "bsh_S3a_s1_best.pt")
RL_SEED = 7


@pytest.fixture(scope="module")
def collection(tmp_path_factory: pytest.TempPathFactory):
    """Two sampled games (net vs default heuristic) written through the
    real --rl-collect lane, plus the legacy --out json for the schema gate."""
    tmp = tmp_path_factory.mktemp("rl_collect")
    eps = tmp / "episodes.jsonl"
    out = tmp / "eval.json"
    rc = eval_main(
        [
            "--games",
            "2",
            "--workers",
            "1",
            "--matchups",
            "teacher",
            "--pool",
            "engine",
            "--policy-a",
            NET,
            "--device",
            "cpu",
            "--rl-collect",
            str(eps),
            "--sample",
            "--rl-seed",
            str(RL_SEED),
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    rows = [json.loads(line) for line in eps.read_text().splitlines()]
    return eps, rows, out


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "tampered.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


# ---------------------------------------------------------- row contract
def test_rows_contract(collection) -> None:
    _, rows, _ = collection
    assert len(rows) == 2  # one owned (sampled) seat per game
    for r in rows:
        assert r["kind"] == "rl_episode"
        assert r["policy"] == NET and isinstance(r["rng_seed"], int)
        assert r["rng_seed"] == RL_SEED * 1_000_003 + r["game_seed"] * 2 + r["seat"]
        assert r["asks"], "seat was never asked — collection lost the game"
        for a in r["asks"]:
            assert a["vocab"] and 0 <= a["idx"] < len(a["vocab"])
            assert float("-inf") < a["logp"] <= 0.0 + 1e-12  # true log-prob
            assert a["obs"].get("_seat") == r["seat"]
            assert "choose" in a  # /134: collector stash state pinned per ask
    # choose sites DO occur in these seeded games, and they carry grounding
    assert any(a["choose"] is not None for r in rows for a in r["asks"])


# ------------------------------------------------------- determinism gate
def test_sampler_determinism() -> None:
    from MTG_bot.core.executor.games import get_supply

    supply = get_supply("engine", "M21")
    seqs = []
    for _ in range(2):
        rec = run_v2_game(
            1,
            False,
            NET,
            "teacher",
            supply=supply,
            device="cpu",
            rl_sample=True,
            rl_rng_base=RL_SEED,
        )
        seqs.append(
            [
                (a["idx"], a["logp"])
                for seat in sorted(rec["rl_asks"])
                for a in rec["rl_asks"][seat]
            ]
        )
    assert seqs[0] == seqs[1] and len(seqs[0]) > 10


# ------------------------------------------------------------ audit GREEN
def test_audit_green(collection) -> None:
    eps, rows, _ = collection
    rep = audit(eps, NET)
    assert rep["episodes_owned"] == len(rows) and rep["episodes_foreign"] == 0
    assert rep["asks"] == sum(len(r["asks"]) for r in rows)
    assert rep["max_abs_delta"] <= rep["tol"]  # same weights => |Δ| ≈ 0
    assert rep["share_gt_tol"] == 0.0


# -------------------------------------------------------------- audit RED
def test_audit_red_tampered_logp(collection, tmp_path: Path) -> None:
    _, rows, _ = collection
    bad = json.loads(json.dumps(rows))
    victim = bad[0]["asks"][len(bad[0]["asks"]) // 2]
    victim["logp"] = victim["logp"] + 0.5  # a shifted pi must never pass
    with pytest.raises(RuntimeError, match="pi_mix"):
        audit(_write(tmp_path, bad), NET)


def test_audit_red_deleted_logp(collection, tmp_path: Path) -> None:
    _, rows, _ = collection
    bad = json.loads(json.dumps(rows))
    del bad[0]["asks"][0]["logp"]
    with pytest.raises(RuntimeError, match="pi_mix"):
        audit(_write(tmp_path, bad), NET)


def test_audit_red_missing_choose_key(collection, tmp_path: Path) -> None:
    """A row that does not pin the collector's digest-stash state is
    silently RE-GROUNDED by a fresh-process replay — the exact cross-
    process mismatch the choose field exists to kill."""
    _, rows, _ = collection
    bad = json.loads(json.dumps(rows))
    del bad[0]["asks"][0]["choose"]
    with pytest.raises(RuntimeError, match="pi_mix"):
        audit(_write(tmp_path, bad), NET)


def test_audit_red_foreign_checkpoint_only(collection) -> None:
    eps, _, _ = collection
    other = str(REPO / "tools" / "training" / "azg1_best.pt")
    with pytest.raises(RuntimeError, match="pi_mix"):
        audit(eps, other)


# ------------------------------------------------------- legacy schema gate
def test_legacy_out_schema_untouched(collection) -> None:
    _, _, out = collection
    doc = json.loads(out.read_text(encoding="utf-8"))
    for rec in doc["records"]["teacher"]:
        assert "rl_asks" not in rec and "rl_meta" not in rec
        assert rec["seat_stats"]["0"]["asks"] > 0
