"""K2 tooling: replays are exact, the probe value moves the right way, uninformative asks drop out."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load("k2_gen", "gen.py")
train = _load("k2_train", "train.py")


def test_generation_is_deterministic_and_replays_never_diverge(monkeypatch) -> None:
    # The base game's random stream derives from the master seed, so seed it as main() does. A
    # 16-turn cap keeps it fast; M21 game 2 then has informative asks (options whose boards
    # differ). ReplayDivergence would raise out of play().
    gen.rng.seed_all(20261028)
    monkeypatch.setattr(gen, "TURN_CAP", 16)
    first = gen.play(("M21", "castable", 2, 60))
    second = gen.play(("M21", "castable", 2, 60))
    assert first and first == second
    assert any(len({tuple(a) for a in row["after"]}) > 1 for row in first)
    for row in first:
        assert len(row["after"]) == len(row["options"]) == len(row["facts"])
        assert row["kind"] in gen.ELIGIBLE


def _board(**fields: int) -> list[int]:
    b = [0] * 24
    for key, v in fields.items():
        b[train.COL[key.replace("_", ".", 1)]] = v
    return b


def test_the_probe_value_rewards_what_it_should() -> None:
    base = train.value(_board())
    assert train.value(_board(me_life=3)) > base
    assert train.value(_board(opp_creatures=-1, opp_power=-2, opp_toughness=-2)) > base
    assert train.value(_board(me_creatures=-1, me_power=-2, me_toughness=-2)) < base
    assert train.value(_board(opp_tapped=1)) > base


def test_uninformative_and_sourceless_asks_drop_out(tmp_path) -> None:
    def row(source, after):
        return {"kind": "target", "source": source, "options": ["a", "b"],
                "facts": [{"word": "a"}, {"word": "b"}], "before": [0] * 24, "after": after,
                "set": "M21", "seed": 1, "pos": 0}

    same = [[0] * 24, [0] * 24]
    differ = [[0] * 24, _board(me_life=2)]
    lines = [{"kind": "manifest"}, row("x", same), row(None, differ), row("y", differ)]
    (tmp_path / "k2_M21.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    rows, dropped = train.load(tmp_path)
    assert [r["source"] for r in rows] == ["y"]
    assert rows[0]["best"] == [1]
    assert dropped["uninformative"] == 1 and dropped["no source card"] == 1
    assert len(train.option_features({})) == train.N_OPT
