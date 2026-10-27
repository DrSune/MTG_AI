"""K1 tooling: atom tokens leak no identity, the compound split keeps every atom in training, K1b
statistics behave."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import curve
import gen
import train

from MTG_bot.core.ability_tree import to_dict
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

DATA = Path(__file__).resolve().parents[2] / "MTG_bot" / "data" / "M21.json"


def test_ir_tokens_carry_rules_and_never_the_cards_identity() -> None:
    pool = ingest_pool(DATA)
    raw = next(r for r in pool.values() if r.identity.name == "Shock")
    card = compile_card(raw, build_full_registry()).card
    tokens = train.ir_tokens({"abilities": [to_dict(a) for a in card.abilities]})
    assert "Verb.DEAL_DAMAGE" in tokens and "num:2" in tokens and "role:target" in tokens
    joined = " ".join(tokens)
    assert "Shock" not in joined and raw.identity.oracle_id not in joined
    assert tokens == train.ir_tokens({"abilities": [to_dict(a) for a in card.abilities]})


def test_text_tokens_mask_the_cards_own_name() -> None:
    raw = next(r for r in ingest_pool(DATA).values()
               if r.identity.name == "Barrin, Tolarian Archmage")
    words = train.text_tokens(raw)
    assert "barrin" not in words and "~" in words


def test_the_compound_split_holds_out_rare_pairs_but_no_unseen_atom() -> None:
    tokens = {
        "a": ["Atom", "Verb.DRAW", "Verb.DESTROY"],
        "b": ["Atom", "Verb.DRAW", "Verb.GAIN_LIFE"],
        "c": ["Atom", "Verb.DESTROY", "Verb.GAIN_LIFE"],
        "d": ["Atom", "Verb.DRAW"],
        "e": ["Atom", "Verb.DESTROY"],
        "f": ["Atom", "Verb.GAIN_LIFE"],
        "g": ["Atom", "Verb.EXILE"],  # its only atom pair is unique, but EXILE is seen nowhere else
    }
    held = train.compound_split(sorted(tokens), tokens, share=0.4)
    assert held and "g" not in held
    seen = set().union(*(train.atoms_of_tokens(tokens[c]) for c in tokens if c not in held))
    for c in held:
        assert train.atoms_of_tokens(tokens[c]) <= seen


def test_a_recorded_row_has_the_24_board_numbers() -> None:
    assert len(gen.COLUMNS) == 24 and gen.COLUMNS[0] == "me.life" and gen.COLUMNS[12] == "opp.life"
    rows = gen.play(("M21", "castable", 3, "stress"))
    assert rows and all(len(r["pre"]) == 24 and len(r["delta"]) == 24 for r in rows)
    assert all(r["unit"] == "card" or r["unit"].startswith("ability:") for r in rows)


def test_k1b_cap_is_per_card_and_independent_of_row_order() -> None:
    rows = [{"oid": oid, "seed": s, "turn": t, "pre": [s, t]}
            for oid in ("a", "b") for s in range(5) for t in range(4)]
    kept = curve.capped(rows, 7)
    assert sorted(r["oid"] for r in kept) == ["a"] * 7 + ["b"] * 7
    # the same rows are kept whatever order they arrive in (only the card order may differ)
    assert sorted(map(str, curve.capped(list(reversed(rows)), 7))) == sorted(map(str, kept))


def test_k1b_skill_skips_cards_the_floor_already_predicts_and_pairs_cards() -> None:
    floor = {"a": 1.0, "b": 2.0, "exact": 0.0}
    model = {"a": 0.5, "b": 2.0, "exact": 0.0}
    skill = curve.skills(model, floor, {"a", "b", "exact"})
    assert skill == {"a": 0.5, "b": 0.0}
    same = curve.paired_gap(skill, skill, "test")
    assert same["gap"] == 0 and same["ci95"] == [0, 0] and same["cards"] == 2
    better = curve.paired_gap({c: v + 0.25 for c, v in skill.items()}, skill, "test")
    assert better["gap"] == 0.25 and better["ci95"] == [0.25, 0.25]
