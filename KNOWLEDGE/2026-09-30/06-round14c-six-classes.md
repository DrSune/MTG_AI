# Round 14c — six crash classes root-caused and closed; PC-7 v1.1 (2026-09-30)

Mission: close B-13/B-15/B-16/B-17/B-18/QX, re-measure vs 14b-2, no commits. Every
class was root-caused against the COMPILED IR + a live probe before any edit; two
initially-assumed causes were WRONG (recorded so nobody re-assumes them):

- **B-18 was NOT "cost-plan staleness"** (the 14b-2 guess): Bad Deal's DISCARD reads
  the live hand list — the compiled zone is `Zone(HAND, ANY)` (the actor lives in the
  `controller` role), so the selection POPULATION spans both hands and the
  Handle-sorted CHOOSE stand-in picked the CASTER'S low handles. Fix = re-scope the
  CHOOSE/RANDOM/ALL stand-ins to the ACTOR's live hand at take time (CR 701.8a).
- **B-16 was NOT Necromentia reading a player as a card zone**: the EXILE atom carries
  a `referent='result'` Selector under role `target`; `role_handles` gave BINDING
  precedence to the spell's designated OPPONENT (`player:0` from the synth
  TARGET_PLAYER slot) — a designation HIJACKING an anaphora. Fix = bindings never win
  over a referent-carrying Selector; and `_v_search` now writes the 13b `result`
  register (the CHOOSE-atom convention its docstring already promised). Necromentia
  now runs SEARCH→EXILE→SHUFFLE and dies one station later at CREATE_TOKEN's
  `MOVED_TO_ZONE_THIS_TURN` (B-7 family, next wall — pinned).
- **B-17 is compiler-frozen, not executor-fixable**: Scryfall-verified Tavern Swindler
  has NO cast effect; the golden parks the ACTIVATED tail ("If you win the flip…")
  on the SpellAbility (B-11-family tail split, activation flavour). Any "fix" would
  mean re-baselining the compiler (frozen scope) — STOP + ledger.
- **B-13/B-15/QX are one theme — the engine must ENUMERATE and ASK, not raise**:
  ONE_OF asks `take_decision(vocab=sorted candidate handles)` (C15; forced at 1,
  empty = C17 nothing, exhaustion = loud ValueError); REST = complement of
  `ctx.one_of_pick`, no ask; TARGET-in-any-role reads the spell's `target`
  designation ∩ still-legal (CR 601.2c); and per CR 601.2f `cast()` declares the
  legality fold's X=0 witness (CR 107.1) into `x_value` so effect-side QX reads the
  SAME X the cost paid. Partition atoms skip the draw-idiom + count-clamp.

**Numbers** (`.venv/bin/python -m MTG_bot.core.executor.games --seeds N --pool P`):
10-seed all 1→**2/10** (mean 35.9, cov 41), engine 3→**6/10** (mean 46.2, cov 44),
castable 0/10 mean 14.0→18.3 (cov 39). Engine ≥5/10 ⇒ **PC-7 v1.1 30 seeds:
10/30 = 33.3% survived to the 60-cap, mean 34.9t, 51/286 cards (19.1%) fired,
2021 actions.** New dominant class = B-7-family filter preds 13/22 (CONTROLLER_COUNT_GE,
CAST_THIS_TURN_FROM, MOVED_TO_ZONE_THIS_TURN); then B-9 3/22, B-17 3/22, NEW B-19
Zone(STACK) runtime KeyError 2/22 (B-2's runtime twin; query side fixed,
`ZONE_KIND_TO_STATE` lacks STACK — next round's small fix), Verb.FIGHT handler-less 1.

Gates: core **2001 passed** (+5 pins, 2 pins AMENDED in place with dated markers),
PC-1/2/3/4 **EXACT**, pyright 0, ruff delta 0, replay determinism green. Edited
(UNCOMMITTED): selectors.py, verbs.py, stack.py, quantity.py (ExecCtx.one_of_pick),
query.py doc, + 3 test files. Ledger updates in 03-game-loop-bugs.md §"Round 14c".
