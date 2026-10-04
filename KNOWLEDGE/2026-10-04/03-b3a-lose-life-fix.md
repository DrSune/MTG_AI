# 03 — B3a: LOSE_LIFE journal fix, D6 adjudications, §C flags (2026-10-04)

Batch: BUGCATCH B3a · HEAD `2fba372` · engine ADDITIVE lane authorized
(compiler/goldens FROZEN, no commits). Files: `MTG_bot/core/executor/
events.py`, `MTG_bot/core/test_executor_b3a_life_journal.py` (new),
`tools/audit/detectors.py`, `tools/audit/test_detectors.py`,
`tools/audit/bcs.py`, re-pinned `catalog.json`, regenerated
`anomalies.json` + `bcs.json`.

## Scope A — the life-loss feed (D1 genuine finding, fixed)

**Root cause.** `EventJournal.record_atom` diffs life and emits a decrease
row ONLY under `cause_verb == "DEAL_DAMAGE"` (as DAMAGE). A `LOSE_LIFE`
resolution ("you lose 3 life"; also the life-as-cost lane) left ZERO rows
— the fold `start + gains − damage` under-counted losses on 4/20 seeds
(10: −4/−4, 12: −3 "Life Goes On", 13: −2/−2, 17: −2/−2).

**Fix (CR 118.5).** New journal kind `KIND_LIFE_LOST = "LIFE_LOST"`,
subject the player, data `(actual_delta,)` after the verb's 0-clamp —
never a DAMAGE row (losing life is not dealt damage; DamageDealtEvent
must not subscribe to losses) and never a negative LIFE_GAINED row
(`binding.py:861` dispatches LifeGainedEvent **by kind**, a negative gain
row would fire "whenever you gain life" triggers). Life mutations exist
only at `verbs.py:313/348/405`; no grammar node reads LIFE_LOST, so the
kind is inert to triggers until a `LoseLifeEvent` ships.

**GAIN_LIFE symmetric check: gains were NOT silent** — the pre-existing
diff already emits LIFE_GAINED on any increase. No row added.

**Gate-wording deviation (disclosed).** The brief asked for "D1 CLEAN with
detector UNCHANGED" *and* "seed-12 fold reconstructs 17". Mutually
impossible: shipped D1 folds only LIFE_GAINED(+)/DAMAGE(−); the only
ways to pass an unchanged D1 after the fix are the two rules-buggy row
choices above. Adjudicated in favor of the fold-reconstruction wording:
D1's fold VOCABULARY was synced (losses += LIFE_LOST). This strictly
strengthens D1 — an under-counting loss still HITS (`test_d1_still_fires_
when_life_lost_undercounts`); no detector was weakened anywhere in B3a.

**Result.** D1: 4/20 HIT → **clean 20/20**. Seed 12 paste:
`player:0: 20+0−0−3=17, final=17 OK=True` (one LIFE_LOST row).
Engine pins: 5 new in `test_executor_b3a_life_journal.py` (row shape,
clamp=actual-delta, gain-still-gain, damage-not-loss, mixed fold).

## Scope B — the 3 D6 suspects: ALL FALSIFIED (no engine bug)

1. **Seed 16 grant-on-graveyard-source.** Layer `#9 kind=grant tag=Eot
   live source=card:72 (Crash Through, in GY) target=card:68 (Burlfist
   Oak, alive)`. **CR 611.2a**: an effect once created exists
   independently of its source — an instant correctly sits in the
   graveyard while its EOT grant stays live. No leak.
2. **+3. Seeds 16/17 repl doubles.** Same card registered twice (seed 16
   card:38, seed 17 card:43, Containment Priest; consecutive seq, both
   `expired`; single battlefield entry hand→stack→battlefield→GY). NOT a
   CR 614.3 co-registration: `replacements.attach_source` (`replacements.py:167`)
   SELF-DETACHES the previous record, so the pair are lifecycle audit
   ghosts that never co-exist. Double registration mechanism:
   `binder.attach_card` from the cast-resolution lane (`stack.py:675/802`)
   plus the journal-lifecycle lane (`binding.py:546 → _register:433`) on
   the ZONE_CHANGE row. Golden has exactly one replacement node; the
   single-priest scenario pack is green. No engine fix.

**D6 tightening (rules-cited, not loosened-blind).** (iii) repl lane
groups **live rows only** — expired = self-detached ghost, CR 614.3 needs
simultaneous application. (iv) layer lane skips the SOURCE side for
duration-tagged `grant`/`lose` (CR 611.2a); static/keyword source deps
and ALL target-side flags unchanged (fault tests still fire). Net: 3
suspects → 0; anomalies **0 hits / 20 seeds** (was 4 D1 HITs + 3 D6).
6 new detector tests, suite 28 → **34**.

## Scope C — bcs.json §C collision flags (machine-readable)

`COLLISION_FLAGS` in bcs.py → `cards[<name>].collision_flags` + heat
projection: branch_entanglement {Destructive Tampering, Fabled Passage},
keyword_x_consumer {Makeshift Battalion, Mistral Singer},
replacement_x_ordering {Teferi's Ageless Insight, Caged Zombie},
single_fold {Basri's Solidarity, Secure the Scene}. Also falsified the B1
vocabulary note: `VERB_TO_JOURNAL["LOSE_LIFE"]` "LIFE_GAINED" → the real
**LIFE_LOST** feed (2 Liliana, Waker of the Dead branch signatures now
target a row that actually exists). Diff: scores 305/305 zero drift,
mean 14.1; only field deltas = collision_flags (305 keys, 8 non-empty) +
those 2 Liliana signatures.

## Gate ledger (all run at final code state)

1. `pytest tools/audit -q` → **34 passed**.
2. Detectors regen 20 seeds → **0 hits**; seed-12 fold 20+0−0−3=17.
3. `pytest MTG_bot/core -q` → **2350 passed + 3 subtests, 0 failed**
   (baseline 2345 + exactly the 5 new pins).
4. `tools/measure_grammar.py` → PC-1 303/305 · PC-2 637/639 · PC-3 0 ·
   PC-4 0 verified · PC-8 0.3213 · PC-9 stable — **Δ0 vs C6** (PC-6/PC-8
   standing FAILs unchanged).
5. `catalog.py compare` → 3/10 diverge (seeds 2/3/4), each PURELY the
   inserted LIFE_LOST row: identical endings, n+1, first-diff is the new
   row (downstream hash shifts = chain fingerprint). Repinned
   (md5 `372a5fd3…`) → **0/10**. `games --seeds 100 --pool all
   --deck-pairs-seed 1409 --turns 60` → **0 crash classes**, 100
   decisive 53/47, mean_turns 33.48. **Honesty note**: the same command
   on a stashed HEAD copy of events.py reproduces 53/47 / 33.48 exactly
   — the C6 row's 48/52 / 33.49 is historical/environment drift, NOT
   B3a (my lane changes zero game outcomes).
6. pyright **0 errors** on all four touched files; ruff **Δ0** (both
   trees clean; worktree-vs-worktree, no stdin per-file-ignore trap).
