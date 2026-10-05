# 11 — STALL rule in the games loop (CR 104.4b repeated-loop draw)

Date: 2026-10-05. Batch: STALL-RULE. HEAD 67dca46, no commit (owner instruction).
Lanes touched: `MTG_bot/core/executor/games.py`, `executor/events.py`,
`test_executor_games.py` — the authorized games/executor terminal lanes only.
Goldens and `state.py` untouched. No wall-clock, no RNG in the rule: pure state
comparison, fully deterministic.

## Rule (as implemented)

- **Observation point**: top of each turn inside `_play` (post-untap, post-draw,
  pre-act), for the active seat.
- **World fingerprint** (`_stall_fingerprint`): per seat in `player_order`:
  life total; battlefield multiset of `(oracle_id, tapped, sorted counters,
  printed P/T)`; hand / library / graveyard **sizes**; plus one global
  stack-empty bit. Aura-buffed stats are captured because the aura itself is in
  the battlefield multiset.
- **Streak semantics**: per-seat streak — each seat's turn-top fingerprint is
  compared with *that same seat's* previous turn-top observation, i.e. exactly
  one full round later, so both players' churn lies inside every window.
- **Trigger**: `REPEAT_ROUNDS = 3` identical consecutive per-seat observations →
  immediate terminal DRAW. Threshold rationale: one repeat proves nothing
  (a pass-turn mirror is legal play); threshold 2 false-fires on loops whose
  first cycle absorbs a draw (hand size dips then recovers); 3 is the minimum
  that sees the full cycle twice with margin.
- **Terminal**: `game.turns = world.turn` at detection; reason
  `"STALL (CR 104.4b repeated-loop draw: world fingerprint unchanged for 3
  consecutive rounds)"` (report bucket key after split-on-`(` = `STALL`);
  `survived=False`.
- **Audit row**: `KIND_STALL_BREAK = "STALL_BREAK"` emitted by the harness (like
  the GAME_LOST twin): `subject=None, cause=seat, cause_verb="STALL",
  data=(REPEAT_ROUNDS,)`. Rides into `state_fingerprint()`; `coverage_of`
  ignores it (player-handle cause).
- **Library ORDER is deliberately excluded** — the canonical pathological loop
  (ETB shuffle-back) rewrites library order with seeded RNG every cycle while
  making zero progress; sizes are the progress observable. Fingerprint identity
  alone is the documented trigger condition: a state-identity round trip *is*
  the observable content of "the same actions recur".

## Synthetic verification (StallRuleTest, 5 pins)

Loop card: 0-mana 1/1 creature, ETB = move-self→library + shuffle; deck = 60
copies; deterministic policy casts exactly one spell per turn (RandomPolicy's
dice make the stall geometrically rare, ~0.004 per window — never use it for
this pin). Fixed literal UUID oracle id to dodge the global oracle-counter
pitfall.

- Terminates at **turn 5** (≤ 2·REPEAT_ROUNDS+2), not 60; lives [20,20]; exactly
  one STALL_BREAK journal row; two fresh runs equal reason/turns/fingerprint.

## Corpus before/after (`--seeds 100 --pool all`)

- Before (baseline this morning): endings
  `{'game over: player:1': 51, 'game over: player:0': 47, 'turn cap 60 reached': 2}`,
  survived 2, 0 crash classes.
- After: **identical endings, identical survivors**. The two cap games (seed 53,
  101 acts; seed 91, 200 acts) are long grinds with real state progress every
  round — fingerprint changes, stall never fires. Honest outcome: the rule
  changed **zero** corpus classifications; it is a safety net, not a reclassifier.
- Journal catalog (`tools/traces/catalog.py compare`): **0/10 diverging seeds** —
  no repin; the check adds comparisons but mutates nothing.
- Decisive long game pinned: seed 73 → 56 turns, `game over: player:0(life<=0)`,
  not STALL.

## Gates

- pytest MTG_bot/core: **2391 passed** (2386 baseline + 5 new), 0 failed.
- run_scenarios: **355/355 packs passed**.
- measure_grammar: PC-9 determinism stable PASS (Δ0); unchanged PC rows
  (grammar_2026-10-05.json).
- games CLI: 0 crash classes over 100 games; endings unchanged (above).
- ruff Δ0 on the three touched files; pyright: no new errors.

## Corpus looper scan (report only)

The card corpus is `MTG_bot/data/mtg_bot.db` table `cards` (397 rows; note
`MTG_bot/data/M21.json` is set *metadata*, not cards). Regex
`shuffle…library | return…library` over 391 text rows → **1 candidate**:
*Transmogrify* (exile target creature, dig to creature, put onto battlefield,
shuffle rest). It cannot self-loop: it always changes battlefield and hand
counts. No card in the shipped corpus can sustain a fingerprint-invariant
cycle; the rule is defense for future pools.
