"""Regression gate: the action space must never make sequential decision count
scale multiplicatively in board size.

Why this file exists
--------------------
`reports/LATENCY_FINDINGS.md` Finding 1 measured that decision latency is FLAT in board
token count and in legal-menu WIDTH. Finding 2 and the §4 variance table identify the one
quantity that is not flat and that multiplies straight into the match clock: the number of
SEQUENTIAL model calls per game.

`docs/DESIGN_LATENCY.md` §1.3 sets the contract at B = 1,050 s of bank per seat per
75-minute Commander pod. Sequential decisions divide that bank. Anything that makes the
decision count grow as a PRODUCT of two board dimensions is a denial-of-service surface:
an opponent can build a board that costs them nothing and costs us the match clock.

Today `engine.py:141-148` emits one `DeclareBlockerAction` per (blocker, attacker) pair, so
committing a full block assignment on an A-attacker / B-blocker board takes A*B sequential
decisions. That is the failure this gate is written against.

The gate is deliberately stated as a SHAPE assertion, not as a wall-clock assertion, so it
is hardware independent and cannot be silenced by a faster machine.

Status
------
`test_block_assignment_scales_additively` is expected to FAIL on the current engine and is
marked `xfail(strict=True)`. When `BLOCK_ASSIGN` from `docs/DESIGN_ACTION_SPACE.md` §1.3
lands, the xfail marker must be deleted in the same commit. `strict=True` means the test
also fails if it starts passing while the marker is still there, so the marker cannot rot.
"""

from __future__ import annotations

import pytest

# The budget, and its provenance.
#
# A block assignment is ONE structured move (CR 509.1a declares all blocks at once), plus at
# most one damage-division field per blocked attacker (CR 510.1c: a blocked creature's damage
# is "divided as its controller chooses" among its blockers -- note that damage assignment
# ORDER was removed from the game, so there is no ordering decision here any more).
#
# So the honest bound on decode steps for one combat is linear in the board, not quadratic:
#
#     decisions <= C0 + C1 * (attackers + blockers)
#
# C1 = 2 covers one BLOCKER field and one BLOCKED field per participating creature.
# C0 = 4 covers the verb, the terminators, and the attacker-side division fields.
BUDGET_C0 = 4
BUDGET_C1 = 2

# Kept small on purpose. Committing a 16x16 block assignment through the current
# per-pair action space takes 256 engine round trips and 19.1 s of pure CPU on the dev
# box (reports/block_commit_timing.txt), so the large boards belong in the sweep tool
# (tools/latency/decisions.py --combat-sweep), not in CI.
# The quadratic cost only exceeds the additive bound once the board is big enough for
# A*B to overtake C0 + C1*(A+B). Below the crossover a per-pair action space still fits
# inside the budget, so those cases legitimately PASS today and must not be marked xfail:
# with strict=True an unexpected pass is itself a failure.
#
#   board   A*B (actual)   C0+C1*(A+B) (bound)   within budget?
#   1x1     1              8                     yes
#   2x2     4              12                    yes
#   4x4     16             20                    yes
#   6x6     36             28                    NO
#   8x8     64             36                    NO
#
# So the gate marks only the post-crossover cases as expected failures. When BLOCK_ASSIGN
# lands, every row passes and the strict markers force their own removal.
_SWEEP = [(1, 1), (2, 2), (4, 4), (6, 6), (8, 8)]


def _budget(attackers: int, blockers: int) -> int:
    return BUDGET_C0 + BUDGET_C1 * (attackers + blockers)


def _sweep_params():
    """Attach xfail only where the current per-pair action space actually breaches the
    bound, so the marker means what it says."""
    out = []
    for a, b in _SWEEP:
        expected_now = a * b                      # current engine: one action per pair
        marks = ()
        if expected_now > _budget(a, b):
            marks = pytest.mark.xfail(strict=True, reason=(
                f"engine.py:141-148 emits one DeclareBlockerAction per (blocker, attacker) "
                f"pair, so a {a}x{b} board needs {expected_now} sequential calls against a "
                f"bound of {_budget(a, b)}. Remove this marker when BLOCK_ASSIGN lands "
                f"(docs/DESIGN_ACTION_SPACE.md 1.3)."
            ))
        out.append(pytest.param(a, b, marks=marks))
    return out


def _sequential_block_decisions(attackers: int, blockers: int) -> int:
    """How many separate times must the network be run to commit a full block?"""
    from tools.latency.decisions import _plant_board

    graph, engine = _plant_board(attackers, blockers, seed=7)
    n = 0
    while n <= 10_000:
        moves = engine.get_legal_moves()
        blocks = [m for m in moves if type(m).__name__ == "DeclareBlockerAction"]
        if not blocks:
            return n
        engine.execute_move(blocks[0])
        n += 1
    raise AssertionError("block declaration did not terminate")


@pytest.mark.parametrize("attackers,blockers", _sweep_params())
def test_block_assignment_scales_additively(attackers, blockers):
    n = _sequential_block_decisions(attackers, blockers)
    bound = _budget(attackers, blockers)
    assert n <= bound, (
        f"{attackers}x{blockers} board needs {n} sequential model calls, bound is {bound}. "
        f"Sequential decision count is the only measured quantity that can breach the "
        f"match clock (reports/LATENCY_FINDINGS.md)."
    )


def test_block_assignment_is_currently_multiplicative():
    """Pin the CURRENT behaviour, so the size of the problem cannot drift unnoticed
    while the fix is pending. Delete this test in the same commit that deletes the
    xfail above."""
    assert _sequential_block_decisions(8, 8) == 64
    assert _sequential_block_decisions(4, 6) == 24


@pytest.mark.slow
def test_decisions_per_seat_per_game_within_bank():
    """End-to-end floor: seeded self-play games must not exceed the per-seat decision
    budget. This is a FLOOR on today's engine (broken targeting, no real priority,
    two seats -- docs/ARCHITECTURE.md), so it is set loose and its job is to catch a
    regression that multiplies it, not to certify the real number."""
    from tools.latency.decisions import run_games, summarise_games

    results, _ = run_games(n_games=6, max_steps=8000, seed=20260910, mode="Commander")
    s = summarise_games(results)
    p99 = s["decisions_per_seat_per_game"]["p99"]
    assert p99 <= 5_000, f"p99 decisions per seat per game = {p99}"
