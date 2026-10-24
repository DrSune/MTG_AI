"""Tests for DAgger wave 1 (tools/eval/dagger_wave.py).

Fast units on the pure lanes (pack table, site parser, chunker, demotion
fallback) plus one end-to-end smoke: 3 real BC-vs-BC games at a small turn
cap writing both episode files and the stats json, with the episode
ENCODING law checked (stream fits max_len, gold indices valid, private obs
tables published out, class separation between the two files)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.eval import dagger_wave as dw
from tools.training import bc_data_v2
from tools._testutil import skip_unless_files


# ----------------------------------------------------------------- pure units
def test_pack_table_transfers_only_site_knowledge() -> None:
    corpus = json.loads(dw.CORPUS.read_text(encoding="utf-8"))
    table = dw.build_pack_table(corpus)
    assert table, "the corpus must back at least one lane"
    for (card, kind), entry in table.items():
        assert kind in dw.PACK_KINDS
        assert kind not in ("mana", "name")  # pool-content accidents, off
        assert dw._transferable(entry["gold"])
        if entry["ambiguous"]:
            assert entry["backings"] == []  # conflicting key is OFF
        for pack, step, gold in entry["backings"]:
            assert pack.endswith(".json") and isinstance(step, int)
            assert gold == entry["gold"]
            src = [
                i
                for i in corpus["items"]
                if i["pack"] == pack and i["step"] == step and i["gold"] == gold
            ]
            # the corpus's own non-evidence items never back a label
            assert src and all(
                i["null"] == 0.0
                and not i["reclassified"]
                and not i["no_discrimination"]
                for i in src
            ), (card, kind)


def test_pack_card_of_site_parsing() -> None:
    hw = {"card:3", "player:0", "card:5"}
    names = {"card:3": "Alpine Houndmaster", "card:5": "Goblin Arsonist"}
    assert dw.pack_card_of("may:card:3", hw, names) == "Alpine Houndmaster"
    assert dw.pack_card_of("attack:card:5:12", hw, names) == "Goblin Arsonist"
    # scry sites carry only the PLAYER -> never pack-backed in game
    assert dw.pack_card_of("scry:player:0:2", hw, names) == ""
    assert dw.pack_card_of("act:main", hw, names) == ""


def test_chunk_seat_fits_budget_and_keeps_classes_apart() -> None:
    def hrow(gold_idx: int | None) -> dict:
        row = {
            "ordinal": 0,
            "what": "may:card:1",
            "candidates": ["fire", "skip"],
            "obs": {"turn": 1},
            "gold": gold_idx is not None,
            "gold_idx": gold_idx,
        }
        return {"row": row, "_tokens": (row["what"], row["obs"])}

    t0 = dw.row_tokens("may:card:1", {"turn": 1})
    history = [hrow(g) for g in (None, 0, None, 1, None, 0, None)]
    golds_pack = [
        {
            "row": 1,
            "kind": "may",
            "gold_idx": 0,
            "heur_idx": 0,
            "policy_idx": 1,
            "backings": [["p.json", 0, "fire"]],
        },
        {
            "row": 5,
            "kind": "may",
            "gold_idx": 0,
            "heur_idx": 1,
            "policy_idx": 1,
            "backings": [],
        },
    ]
    golds_heur = [
        {
            "row": 3,
            "kind": "may",
            "gold_idx": 1,
            "heur_idx": 1,
            "policy_idx": 0,
            "backings": [],
        },
    ]
    trunc = {"gold_row_overflow": 0}
    # budget BOS + 3 rows: the pack chunk spans rows 1..5 but must leave the
    # heur-gold row 3 OUT (file separation), keeping context + own golds
    eps = dw.chunk_seat(history, golds_pack, 1 + 3 * t0, 7, 0, "pack", trunc)
    assert len(eps) >= 1
    total_pack_golds = sum(sum(1 for r in ep["asks"] if r["gold"]) for ep in eps)
    assert total_pack_golds == 2
    assert all(r["gold_idx"] != 1 for ep in eps for r in ep["asks"])
    assert all(ep["n_tokens"] <= 1 + 3 * t0 for ep in eps)
    dw.chunk_seat(
        history,
        [
            {
                "row": 0,
                "kind": "may",
                "gold_idx": 0,
                "heur_idx": 1,
                "policy_idx": 1,
                "backings": [],
            }
        ],
        1,
        7,
        0,
        "pack",
        trunc,
    )
    assert trunc["gold_row_overflow"] == 1
    assert dw.chunk_seat(history, golds_heur, 1 + 3 * t0, 7, 0, "heur", trunc)


def test_certify_backings_demotes_with_heuristic_fallback(monkeypatch) -> None:
    class FakePCert:
        null_word = "skip"

        @staticmethod
        def extract_items(pack, supply):
            return [{"step": 0, "gold": "fire", "ordinal": 3}]

        @staticmethod
        def _drive(pack, supply, ordinal, answer):
            # ok == the null pick SATISFIES the pack -> NOT falsified
            return (None, not pack["falsifies"])

    monkeypatch.setitem(sys.modules, "tools.audit.puzzle_cert", FakePCert)
    import tools.audit
    monkeypatch.setattr(tools.audit, "puzzle_cert", FakePCert, raising=False)

    def fake_read_text(self, **kw):
        if self.suffix == ".json":
            return json.dumps({"falsifies": self.name == "good.json"})
        raise AssertionError(f"unexpected read {self}")

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    def ep(backing):
        return {
            "pack": "xpackc0",
            "card": "xpackc0",
            "source": "dagger",
            "label_class": "pack",
            "backings": [list(backing)],
            "asks": [
                {
                    "ordinal": 0,
                    "what": "w",
                    "candidates": ["fire", "skip"],
                    "obs": {},
                    "gold": True,
                    "gold_idx": 0,
                }
            ],
            "gold_meta": [
                {"pos": 0, "kind": "may", "gold_idx": 0, "heur_idx": 0, "policy_idx": 1}
            ],
        }

    cert, demoted, stats = dw.certify_backings(
        [ep(("good.json", 0, "fire")), ep(("bad.json", 0, "fire"))], supply=None
    )
    assert len(cert) == 1 and len(demoted) == 1
    # the demoted gold row fell back to the heuristic pick, still labelled
    drow = demoted[0]["asks"][0]
    assert drow["gold"] and drow["gold_idx"] == 0
    assert demoted[0]["label_class"] == "heur"
    assert stats["falsified"] == 1 and stats["not_falsified"] == 1

    # agreement fallback: heuristic pick == policy pick -> label dropped
    ep2 = ep(("bad.json", 0, "fire"))
    ep2["gold_meta"][0]["heur_idx"] = 1
    ep2["gold_meta"][0]["policy_idx"] = 1  # agrees with the fallback
    ep2["asks"][0]["gold_idx"] = 0
    cert2, demoted2, stats2 = dw.certify_backings([ep2], supply=None)
    assert cert2 == []
    assert stats2["gold_rows_dropped_agreed"] == 1
    assert stats2["episodes_dropped_empty"] == 1


# ------------------------------------------------------------- smoke (games)
@skip_unless_files(dw.gv2.DEFAULT_POLICY_A, dw.gv2.DEFAULT_POLICY_B)
def test_wave_smoke_three_games(tmp_path) -> None:
    stats_p = tmp_path / "wave.json"
    eps_p = tmp_path / "episodes_dagger.jsonl"
    heur_p = tmp_path / "episodes_dagger_heuristic.jsonl"
    rc = dw.main(
        [
            "--games",
            "3",
            "--workers",
            "1",
            "--pool",
            "engine",
            "--turn-cap",
            "14",
            "--seed-base",
            "900000",
            "--device",
            "cpu",
            "--out",
            str(stats_p),
            "--episodes-out",
            str(eps_p),
            "--heuristic-out",
            str(heur_p),
        ]
    )
    assert rc == 0
    stats = json.loads(stats_p.read_text(encoding="utf-8"))
    assert stats["totals"]["asks"] > 0
    assert stats["totals"]["divergences"] <= stats["totals"]["asks"]

    base = [
        json.loads(ln)
        for ln in dw.EPISODES_V2.read_text(encoding="utf-8").splitlines()
        if ln
    ]
    cert = [
        json.loads(ln) for ln in eps_p.read_text(encoding="utf-8").splitlines() if ln
    ]
    heur = [
        json.loads(ln) for ln in heur_p.read_text(encoding="utf-8").splitlines() if ln
    ]
    assert cert[: len(base)] == base  # original lines verbatim, prepended
    dagger_eps = cert[len(base) :]
    assert all(
        e.get("source") == "dagger" and e["label_class"] == "pack" for e in dagger_eps
    )
    assert all(e["label_class"] == "heur" for e in heur)

    # encoding law over EVERY emitted dagger episode
    for ep in dagger_eps + heur:
        vocab = bc_data_v2.build_vocab_v2([ep])
        enc = bc_data_v2.encode_episode_v2(ep, vocab)
        assert len(enc["seq"]) <= 1024, ep["pack"]
        gold_srcs = [r for r in ep["asks"] if r["gold"]]
        assert len(enc["gold"]) == len(gold_srcs)
        for g, src in zip(enc["gold"], gold_srcs):
            assert 0 <= g["gold_idx"] < len(src["candidates"])
            assert all(not k.startswith("_") for k in src["obs"])
            assert len(src["ground"]) == len(src["candidates"])
    if stats["totals"]["divergences"] > stats["totals"]["dropped_eval_family"]:
        # divergences that were not leak-dropped must surface as labels
        # somewhere across the two files (counted, never silently lost)
        labelled = sum(
            sum(1 for r in e["asks"] if r["gold"]) for e in dagger_eps + heur
        )
        certified_rows = stats["files"]["episodes_dagger"]["certified_gold_rows"]
        heuristic_rows = stats["files"]["episodes_dagger_heuristic"][
            "heuristic_gold_rows"
        ]
        assert labelled == certified_rows + heuristic_rows > 0
