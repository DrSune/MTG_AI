"""The planning puzzle format: a scenario pack's world (``tools/run_scenarios.py``) plus the
decision, the prior over hidden cards, and the answer.

A puzzle is one JSON file in ``tools/puzzles/suite/``:

    name, set ("M21" | "M20"), category (A | B1 | B2 | B3 | C | D), twin (its twin's name),
    note (the skill and why the answer is right, in words),
    world   : the pack world ({"seed": int}; "library_top" is always on),
    life    : {"0": int, "1": int},
    cards   : the cards both worlds share, in the pack format (real, verified cards only;
              "zone", "controller", "start_tapped", "counters"). Library cards are listed
              top first.
    decider : the deciding seat (0 or 1),
    prelude : the decisions (both seats, in order) from the arranged start, seat 0's first main
              phase of turn 1, to the puzzle's decision: option words with pack keys for
              objects ("cast:shock", a target "bear", "ATTACK", "PASS"; "p0"/"p1" a player),
    world_prior : [{"p": float, "label": str, "cards": [...]}]: the hidden cards of each world
              (the opponent's hand, a library's top), the same count in every zone in every
              world; the probabilities sum to 1,
    horizon : the last turn played (turn 1 is seat 0's first),
    objective : "win" | "survive" | "result" (solver.OBJECTIVES: what a game still running after
              the horizon scores),
    answer  : the right root options, as option words with pack keys,
    grade   : "proven" | "dominant" | "model-verified",
    solver  : written by ``solver.py --write``: each root option's value, runs, decisions,
              seconds.

Handles are allocated in card order, the world's own cards last, so every object both worlds share
has the same handle in each; the decider's observation names objects by view ids
(``solver.canonical``), never by handles.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from MTG_bot.core.executor.games import Game, get_supply
from tools.puzzles.solver import EngineTree, Pos, Solved, Solver
from tools.run_scenarios import ScenarioRunner

SUITE = Path(__file__).resolve().parent / "suite"
CATEGORIES = ("A", "B1", "B2", "B3", "C", "D", "T")  # T: the solver's own test positions
GRADES = ("proven", "dominant", "model-verified")
REQUIRED = ("name", "set", "category", "twin", "note", "world", "cards", "decider", "world_prior",
            "horizon", "objective", "answer", "grade")
SETUP_OPS = ("life",)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HANDLE = re.compile(r"\b(card|player):(\d+)\b")


def load(path: str | Path) -> dict:
    pz = json.loads(Path(path).read_text())
    missing = [k for k in REQUIRED if k not in pz]
    if missing:
        raise ValueError(f"{path}: missing {missing}")
    if pz["category"] not in CATEGORIES or pz["grade"] not in GRADES:
        raise ValueError(f"{path}: category {pz['category']!r} or grade {pz['grade']!r} unknown")
    total = sum(w["p"] for w in pz["world_prior"])
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"{path}: the world prior sums to {total}")
    shape = {_shape(w["cards"]) for w in pz["world_prior"]}
    if len(shape) != 1:
        raise ValueError(f"{path}: the worlds hide different numbers of cards per zone: {shape}")
    return pz


def _shape(cards: list[dict]) -> tuple:
    count: dict[tuple, int] = {}
    for c in cards:
        k = (c["controller"], c.get("zone", "battlefield"))
        count[k] = count.get(k, 0) + 1
    return tuple(sorted(count.items()))


def _ordered(cards: list[dict]) -> list[dict]:
    """The pack lists a library bottom first (the runner puts the last one on top): the puzzle
    lists it top first."""
    libs = [c for c in cards if c.get("zone") == "library"]
    rest = [c for c in cards if c.get("zone") != "library"]
    return rest + libs[::-1]


def supply_of(pz: dict) -> Any:
    return get_supply("verified", pz["set"])


def check_cards(pz: dict) -> None:
    """Real cards only, every one verified (``cardtool.py status``)."""
    supply = supply_of(pz)
    names = {supply.metas[oid].name for oid in supply.deckable}
    for card in pz["cards"] + [c for w in pz["world_prior"] for c in w["cards"]]:
        if "real" not in card:
            raise ValueError(f"{pz['name']}: card {card.get('key')!r} is not a real card")
        if card["real"] not in names:
            raise ValueError(f"{pz['name']}: {card['real']!r} is not a verified {pz['set']} card")


def build(pz: dict, w: int) -> tuple[Game, dict[str, Any]]:
    """World ``w``'s game at the arranged start, and the pack keys' handles."""
    supply = supply_of(pz)
    pack = {"world": {**pz["world"], "library_top": True},
            "cards": _ordered(pz["cards"]) + _ordered(pz["world_prior"][w]["cards"])}
    runner = ScenarioRunner(pack, supply)
    for seat, life in pz.get("life", {}).items():
        runner.run_step({"op": "life", "seat": int(seat), "set": int(life)})
    ex = runner.ex
    # As a dealt game (games._setup_game): a chosen name or creature type comes from the format's
    # pool, never from the world, whose names would show hidden cards.
    ex.name_pool = tuple(sorted({(supply.metas[o].name, supply.metas[o].type_line)
                                 for o in supply.deckable}))
    ex.creature_type_pool = supply.creature_types
    game = Game(executor=ex, seed=int(pz["world"].get("seed", 7)), pool_mode="verified")
    handles = dict(runner.handles)
    order = game.world.player_order
    handles.update({f"p{i}": order[i] for i in range(len(order))})
    return game, handles


def resolve(word: str, handles: dict[str, Any]) -> str:
    """A puzzle's option word with pack keys -> the engine's token."""
    return _WORD.sub(lambda m: str(handles[m.group(0)]) if m.group(0) in handles else m.group(0), word)


def keyed(token: str, handles: dict[str, Any]) -> str:
    """An engine token -> the puzzle's word (pack keys in place of handles)."""
    back = {str(h): k for k, h in handles.items()}
    return _HANDLE.sub(lambda m: back.get(m.group(0), m.group(0)), token)


def tree(pz: dict) -> EngineTree:
    return EngineTree(supply_of(pz), pz["set"], pz["decider"], pz["horizon"], pz["objective"])


def roots(pz: dict) -> tuple[list[tuple[float, Pos]], list[dict[str, Any]]]:
    """Per world: (its probability, the position before the prelude's answers), and its handles."""
    out, hs = [], []
    for w, world in enumerate(pz["world_prior"]):
        game, handles = build(pz, w)
        script = tuple(resolve(word, handles) for word in pz.get("prelude", ()))
        out.append((world["p"], Pos(game, script)))
        hs.append(handles)
    return out, hs


def solve(pz: dict) -> Solved:
    check_cards(pz)
    return Solver(tree(pz)).solve(roots(pz)[0])


def root_words(pz: dict, solved: Solved) -> dict[str, str]:
    """Root option word (canonical) -> the puzzle's keyed word, read in world 0."""
    t = tree(pz)
    rts, hs = roots(pz)
    node = t.expand(rts[0][1])
    return {w: keyed(tok, hs[0]) for w, tok in zip(node.options, node.tokens)}


def solver_record(pz: dict, solved: Solved) -> dict:
    words = root_words(pz, solved)
    values = {words[w]: round(v, 6) for w, v in solved.values.items()}
    best = max(values.values())
    right = sorted(k for k, v in values.items() if v >= best - 1e-9)
    return {"values": values, "best": right, "runs": solved.runs, "decisions": solved.decisions,
            "seconds": round(solved.seconds, 2), "worlds": len(pz["world_prior"])}


def write_result(path: str | Path, pz: dict, solved: Solved) -> None:
    pz = dict(pz)
    pz["solver"] = solver_record(pz, solved)
    Path(path).write_text(json.dumps(pz, indent=1) + "\n")
