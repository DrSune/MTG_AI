# 12 — Wave-3 fix batch B (r20b): trigger-feed, replacement & disclosure lanes

HEAD 6d01577, engine editing **authorized** for this batch. Scope: the 5 suspect packs on the
trigger-install / replacement-effect / layer-parse lanes — warden_of_the_woods,
hooded_blightfang, containment_priest, conspicuous_snoop, rin_and_seri_inseparable.
Outcome: **4 fixed and promoted (runner 200/200; suite 2196); 1 STOP with a written
compiler-backlog root cause (rin)**; every gate green.

## Per-item verdicts

| Suspect | Diagnosis | Fix site |
|---|---|---|
| warden_of_the_woods | "Whenever you cast … target" — `TargetingEvent` sat in `_UNSUPPORTED_EVENTS` (bind-time raise) **and** designation was never an event at all | `events.py` `emit_targeting` (one Handle-sorted row per object, CR 601.2c pre-payment); four emit sites wired: `stack.cast()` + `stack.cast_card` (spell designation), `legality.activate` (folded move — rows land after payment rows, documented clock-order caveat), `binding._designate` (player slot + selector slot; pre-bound firings never reach it, so emits are genuine designations; CR 603.4 empty set emits nothing); `TargetingEvent` removed from the unsupported table; `_match_node` KIND_TARGETING branch with a player-subject guard |
| hooded_blightfang | DAMAGE row with a PLAYER subject hit the 12c raise on card-shape predicates | `binding._player_subject_verdict` — shape-set preds (TYPE_EQ/IS_TOKEN/subtype) are simply FALSE of a player, CONTROLLER_IS compares seats, boolean shapes recurse, everything outside still raises 12e-flag honest |
| containment_priest | enter-the-battlefield replacement never fired: no WAS_CAST pred existed and nothing consumed replacements on a zone move | `quantity.py` `WAS_CAST_THIS_TURN` (turn_window CAST rows); `replacements.py` `replacement_for_zone_change` + `_endpoint_matches`; `verbs._v_move_zone` consumption block (no placement + `ZONE_REPLACED` audit row) draining the action with `bindings={"event": [card]}` — cast creatures spared, put-onto exiled, tokens exempt |
| conspicuous_snoop | "Play with the top card … revealed." compiles to StaticAbility(REVEAL) and `_new_static` raised 12e on the payload verb | `layers._new_static` splits REVEAL/LOOK_AT atoms into lifetime `"disclosure"` layer records (selector-less; inert at re-apply — the verb lane's recorded no-op doctrine now with source-anchored liveness). The grant clause ("may cast Goblin spells from the top") stays **UNPARSED** — compiler backlog, pack green without it |
| rin_and_seri | **compiler mis-split → STOP**: the DB text is ONE activation `{R}{G}{W},T: deal damage = Dogs; gain life = Cats`, but the golden splits it into ActivatedAbility(damage half) + a bare StaticAbility(GAIN_LIFE #Cats, no cost/timing). A static life-gain is not a rules-meaningful object (life gain is an event; "continuous" would loop). The loud 12e raise is CORRECT flag-not-degrade; IR/goldens are FROZEN → stop | no engine change; repro pack stays in `tools/audit/suspects/` with the root-cause finding for the compiler campaign — registering the card raises at attach, so the pack must NOT be promoted (it would abort the scenarios dir) |

## Promotions & pack edits

- 4 packs promoted (status/finding stripped): scenarios dir **196 → 200**.
- warden pack strengthened with the REAL Titanic Growth (M21): tg graveyard, hand 2 (may-DRAW 2,
  baseline-0 law), warden 5/7→9/11 — and it pins the mid-cast drain: the binder cursor queues the
  TARGETING-triggered ability mid-cast and it resolves BEFORE the spell (CR 603.2) via the
  post-`emit_cast` settle.
- snoop pack re-authored: enter + activate idx=1 `decisions:["skip"]` (may-cast asks
  `may:card:0` fire/skip; empty library top → skip is the printed-honest answer).

## Engine unit tests (new)

`MTG_bot/core/test_executor_r20b.py` — **14 tests, all green**: TARGETING feed 5 (fire, skip,
silent-for-other, registration-no-raise, designate-lane emit), zone-replacement 3 (exile entered
nontoken, cast spared, token exempt), player-subject verdicts 4 (shape-false, boolean,
CONTROLLER_IS, unknown-pred still raises), disclosure static install 1, GAIN_LIFE-still-raises 1.
Rig laws learned the hard way: `GameWorld(num_players=…, start_life=…, master_seed=…)`; a cast
needs `ex.begin_turn(p0)` first (`window:not_your_turn`, legality.py:1003); GameEvents ride
`ex.journal.events`, raw verb tuples ride `ex.events`; trigger may-offers answer ONLY via the
executor-wide provider/FIFO lane (the per-op `decisions` tuple dies with the cast ctx).

## Gate evidence (2026-10-01)

1. runner **200/200** (`tools/run_scenarios.py --dir tools/scenarios`)
2. suite **2196 passed + 3 subtests** (`pytest MTG_bot/core -q`) — was 2182, +14 new. Full-tree
   run shows 23 failures, ALL pre-existing at HEAD (rule_engine / strategic_brain / full_system —
   verified identical in a clean HEAD worktree; zero touched this wave). The one NEW collision
   (`test_combat_cast_targeting_step_event_nodes_raise_on_bind` asserted TargetingEvent RAISES)
   was amended per the file's own 13b/16b/16c pattern: leave the raise table, assert CLEAN bind.
3. `tools/measure_grammar.py --with-engine-flags` PC rows **exact**: PC-1 301/305 · PC-2 634/639 ·
   PC-3 0 · PC-4 0 diffs (PC-6/PC-8 pre-existing fails; PC-7 deferred).
4. `tools/traces/catalog.py compare` 9/10 diverge — reconciled: every seed's FIRST divergence is a
   pure TARGETING-row insertion immediately above the spell's CAST row, old rows shift intact
   (rolling fingerprint). `repin` → **6162 entries**, post-repin **0/10 diverge**.
   `python -m MTG_bot.core.executor.games --seeds 100 --pool all` → **0 crash classes**,
   85/100 survived, mean 57.4 turns (identical to the r20a baseline).
5. `pyright` **0 errors / 0 warnings** on the executor package + both test files; `ruff` **Δ0 vs
   HEAD** (diffed against a HEAD worktree with the project config; 4 self-introduced items fixed:
   UP037 quotes, unused local, useless if-else, and the amended binding test restored cleanly
   after a multi-line-anchored edit reflowed neighbouring asserts — verified hunk-by-hunk).

## Standing traps added (→ PITFALLS.md)

- Two event ledgers: binder-matched feed rows → `ex.journal.events`; raw verb +
  replacement-ledger rows → `ex.events`.
- Trigger-ctx decisions need the provider/FIFO lane; per-op tuples are cast-ctx-scoped.
