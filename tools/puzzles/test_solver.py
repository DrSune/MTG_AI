"""The exact solver's own tests (KNOWLEDGE/2026-11-18/214 §2). Each fails on a naive solver:
- a tiny real game whose values are computed by hand;
- a strategy-fusion trap, where solving each world on its own (the decider choosing per world)
  picks the wrong root option;
- an opponent best-response game, where a line that beats a passive opponent loses to a perfect
  one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from MTG_bot.bench.protocol import REFUSE_TOKENS
from tools.puzzles import puzzle as P
from tools.puzzles.solver import Decision, Solver, Terminal, pareto

DATA = Path(__file__).resolve().parent / "testdata"


def _solve(name: str):
    pz = P.load(DATA / f"{name}.json")
    return pz, P.solve(pz)


def test_a_tiny_game_has_its_hand_computed_values() -> None:
    # Courser (3/3) and Assailant (2/2) against one 2/2 blocker and 2 life: with both attacking
    # the unblocked one deals at least 2 (ATTACK 1); without the Courser the Assailant is blocked
    # (DECLINE 0). A solver that lets the opponent pass would score DECLINE 1.
    pz, res = _solve("t_two_attackers")
    assert P.solver_record(pz, res)["values"] == {"ATTACK": 1.0, "DECLINE": 0.0}


class _Naive:
    """A naive opponent: it always declines (PASS, NONE, DECLINE) when ``passive``, else it takes
    the first option it is offered."""

    def __init__(self, tree, passive: bool) -> None:
        self.tree = tree
        self.decider = tree.decider
        self.passive = passive
        self.runs = 0

    def expand(self, pos):
        node = self.tree.expand(pos)
        self.runs = self.tree.runs
        if isinstance(node, Terminal) or node.seat == self.decider:
            return node
        refuse = [w for w in node.options if w in REFUSE_TOKENS] if self.passive else []
        word = (refuse or list(node.options))[0]
        return Decision(node.seat, (word,), {word: node.children[word]}, tokens=(word,))


def test_the_opponent_best_responds() -> None:
    # Seat 1 at 3 life with one blocker; seat 0's Assailant (2/2) is asked first, then its
    # Courser (3/3). A perfect opponent blocks the Courser when both attack, and every option is
    # 0. An opponent that never blocks loses to either attack; one that blocks the first attacker
    # it is offered (the Assailant) loses to both.
    pz, res = _solve("t_one_blocker")
    assert P.solver_record(pz, res)["values"] == {"ATTACK": 0.0, "DECLINE": 0.0}
    for passive in (True, False):
        naive = Solver(_Naive(P.tree(pz), passive)).solve(P.roots(pz)[0])
        assert naive.values["ATTACK"] == 1.0


def test_the_opponent_takes_its_best_line_short_of_the_worst() -> None:
    # Undecided (0.5) beats a loss for the decider and loses to a win: the opponent, offered a
    # line to each, takes the undecided one.
    tree = _Mock({
        "root": Decision(0, ("go",), {"go": "opp"}, key="r"),
        "opp": Decision(1, ("x", "y"), {"x": "win", "y": "even"}),
        "win": Terminal(1.0),
        "even": Terminal(0.5),
    })
    assert Solver(tree).solve([(1.0, "root")]).values == {"go": 0.5}


class _Mock:
    """A game tree written out by hand: position -> node."""

    decider = 0

    def __init__(self, nodes: dict) -> None:
        self.nodes = nodes
        self.runs = 0

    def expand(self, pos):
        self.runs += 1
        return self.nodes[pos]


def _trap(revealed: frozenset = frozenset()) -> tuple[_Mock, list]:
    """Three equally likely worlds. "safe" wins in worlds 1 and 2. "guess" lets the opponent move
    (its other move hands the decider the game), then the decider names a world, a, b or c, and
    wins only if it names the true one. In the worlds in ``revealed`` the opponent's move shows
    which world it is; elsewhere the decider sees the same thing in every world."""
    nodes: dict = {}
    for w, right in ((1, "a"), (2, "b"), (3, "c")):
        nodes[f"root{w}"] = Decision(0, ("safe", "guess"), {"safe": f"safe{w}", "guess": f"opp{w}"},
                                     key="root")
        nodes[f"safe{w}"] = Terminal(1.0 if w < 3 else 0.0)
        nodes[f"opp{w}"] = Decision(1, ("x", "y"), {"x": f"blind{w}", "y": f"gift{w}"})
        nodes[f"gift{w}"] = Terminal(1.0)
        key = f"seen{w}" if w in revealed else "blind"
        nodes[f"blind{w}"] = Decision(0, ("a", "b", "c"), {o: f"end{w}{o}" for o in "abc"}, key=key)
        for o in "abc":
            nodes[f"end{w}{o}"] = Terminal(1.0 if o == right else 0.0)
    return _Mock(nodes), [(1 / 3, f"root{w}") for w in (1, 2, 3)]


def test_the_decider_never_acts_on_cards_it_cannot_see() -> None:
    tree, roots = _trap()
    exact = Solver(tree).solve(roots).values
    assert exact == pytest.approx({"safe": 2 / 3, "guess": 1 / 3})
    # Solving each world alone lets the decider name the true world: it picks "guess", wrongly.
    fused = Solver(tree).fused(roots)
    assert fused == pytest.approx({"safe": 2 / 3, "guess": 1.0})
    assert max(exact, key=exact.get) == "safe" and max(fused, key=fused.get) == "guess"


def test_what_the_opponent_shows_splits_the_information_sets() -> None:
    # World 3's move shows the world: the decider names c there, and a or b blind in 1 and 2.
    tree, roots = _trap(revealed=frozenset({3}))
    assert Solver(tree).solve(roots).values == pytest.approx({"safe": 2 / 3, "guess": 2 / 3})


def test_pareto_keeps_only_undominated_vectors() -> None:
    assert sorted(pareto([(1, 0), (0, 1), (0, 0), (1, 0), (0.5, 0.5)])) == [(0, 1), (0.5, 0.5), (1, 0)]
    assert pareto([(1, 1), (1, 0), (0, 1)]) == [(1, 1)]


def test_the_worlds_look_the_same_to_the_decider() -> None:
    # B1's worlds differ in the opponent's hidden card only: the decider's observation at the
    # root is one, so the solver may treat them as one information set.
    pz = P.load(P.SUITE / "b1_counter_the_answer_lethal.json")
    tree = P.tree(pz)
    keys = {tree.expand(pos).key for _, pos in P.roots(pz)[0]}
    assert len(keys) == 1
