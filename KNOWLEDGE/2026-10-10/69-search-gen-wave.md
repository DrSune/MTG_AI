# 69 — Search-data generation wave (mcts.py walk + cost reality)

Date: 2026-10-10. Follows /67 (mandate) and /68 (substrate).

## What landed
- `tools/training/ab_duel.py`: `BcAsk` split into `_decide` / `menu_probs` /
  `_forward_menu` (argmax-preserving, softmax over full menu). 77 training tests green.
- `tools/search/mcts.py`: boundary-walk generator. Live game = chain of clean-boundary
  Positions; at each boundary a throwaway `_probe` fork finds the globally-first ask
  (any seat) = search root; top-k (k=3) apply-branches by root `menu_probs`, UCB1 (c=sqrt2),
  N=8 rollouts (seat 50/50 greedy-teacher vs fresh root net), visit-fraction `pi` +
  shaped `value` rows (bc_data_v2-compatible), chosen branch BECOMES the live game.
  Asks swallowed inside adopted branches counted honestly.
- `tools/search/gen_games.py` (pool runner + budget guard + gen_stats_v1.json),
  `tools/search/test_mcts.py` (11 tests).

## Fixes found the hard way
1. **STALL-inside-probe walk spin** (seed 9001 turn 17): a STALL draw sets only
   `game.reason` (CR 104.4b repeat detector) + KIND_STALL_BREAK, never a world loser, so
   `over_reason()` stays None. A throwaway probe replaying the mid_act resume's turn-top
   stall-bump can end *inside the fork* with reason "STALL (...)" and the walk never
   notices -> 4000-step spin. Fix: `Probe`/`_probe` distinguishes STALL terminations
   (terminal: adopt + break + result "draw") from the benign "turn cap" horizon reason
   (cleared before adoption); `stagnant>8` no-progress guard raises `SearchError`;
   WALK_STEP_CAP 4000->1500.
2. **pytest-timeout signal race** (tools/search suite under CPU load): global `timeout=120`
   in pyproject; SIGALRM is sometimes *lost* inside torch C regions (490 s standalone run
   survived the 120 s alarm) and sometimes *lands* inside the module fixture's `gen_game`,
   where pytest's `Failed` is caught by gen_game's crash bucket -> phantom "crash:Failed:
   Timeout" and two downstream test failures. Fix: `@pytest.mark.timeout(1800)` on the
   three e2e mini tests (verified green under load). Lesson: any long test that catches
   BaseException must not be subject to a global signal timeout.

## Cost reality (the headline negative result) — 2026-10-10 15:0x
- Full knobs (k=3, N=8, turn_cap=60, net-as-agent rollouts): **one game needs ~60-100+ min
  of dedicated CPU**; a dedicated-core probe spent 7+ min on the first root_search alone.
- 32-game run, 16 workers, 90-min budget, machine system load ~24 (20 cores, other tenants):
  each worker got ~43% of a core (32 CPU-min in 75 wall-min) => **0 games finished inside
  the 90-min budget**. The budget guard harvested nothing. Rate: ~0.43 cores/game-worker.
- k/N knobs are NOT the dominant cost: mini game (k=1,N=1,cap3) still cost ~8 min CPU
  (probes/apply-forks/setup dominate; probe forks replay turn-tops, ~quadratic in turn count).
- Memory is a non-issue: ~250-330 MB RSS per worker (16 workers ~= 5 GB).
- Commands: `.venv/bin/python tools/search/gen_games.py --games 32 --workers 16
  --budget-min 90 --seeds 9100`; log /tmp/opencode/gen_run.log.

## Gates after this wave
- `pytest tools/training -q` = 77 passed. `pytest tools/search -q` = 21 passed (after
  e2e timeout markers; earlier run 1 failed = the phantom-timeout above).
- `pytest MTG_bot/core -q` = 2521 passed +2 subtests. run_scenarios = 398/398.

## Open decision (owner)
Path to the 32-game corpus needs one of: (a) overnight/multi-hour wall budget on an idle
machine, (b) cheaper walk (probe result caching / larger clean boundaries), or (c) knob
review (rollout cap dominates; N/k are secondary). Not yet chosen — do not burn more
90-min budgets at full knobs without one of these.

## Postscript — the budget guard itself was broken (same day)
`gen_games.py` checked the deadline *inside* the `as_completed` loop body; with ZERO
game completions the body never runs, so the pool overran 90 min unnoticed (killed
manually at ~94 min, 0 harvest). Fixed: `cf.wait` loop + `pool._processes[*].terminate()`
(`shutdown(wait=False)` never kills RUNNING children). Verified by executing the exact
path: 4 workers, 0.5-min budget -> "BUDGET exceeded; cutting pool at 0/4", clean exit,
workers reaped. Adversarial lesson: a budget guard must be tested on the case it exists
for (nothing finishing), not the happy path.
