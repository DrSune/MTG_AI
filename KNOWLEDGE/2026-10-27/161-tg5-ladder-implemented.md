# 161 — T-G5 fix ladder implemented (per /135 decision): set-plumbing, admissibility-driven fit, engine git-stamp, era-parity sentinel cell
Date: 2026-10-27 morning. Implements ladder items (1)–(4) of the T-G5 fairness audit (KNOWLEDGE/2026-10-20/135). Item (5) (puzzle-meter native set-split corpus) is non-blocking and NOT touched.

## Item 1 — set_code plumb (FATAL-1: the ladder was M21-locked)
The engine already supported set-scoped supplies (`get_supply(mode, set_code)` in MTG_bot/core/executor/games.py, default SET_CODE="M21", loads MTG_bot/data/{set}.json) — the lock was pure plumbing. Now threaded end to end:
- `ab_duel.py`: `run_duel_game`, `_duel_init` (spawn-pool initargs), `run_duel`, `run_curve` (via **duel_kw), `main --set` (default M21). The dealt supply is set-scoped at every call site.
- `elo.py`: `run_ladder(..., set_code)`, `main --set`.
- The duel summary now stamps `set` + `pool` (a winrate from one supply is not comparable to another — half of item 3 at the duel layer).
- ZNR note: the ladder can now PLAY a ZNR pool the moment MTG_bot/data/ZNR.json exists (owner-verified source still pending, per the standing ZNR block); the plumbing is proven on M21 today (smoke below).

## Item 2 — per-pair admissibility drives the fit (the /26 fabricated-ratings hole, closed)
Old: `fit_elo` fit ALL pairs; under-powered pairs (bootstrap wr CI straddling 0.5) minted ratings that looked like skill. New: `ladder_ratings()` (pure, testable) —
- a pair is ADMISSIBLE iff its bootstrap winrate CI excludes 0.5 (per-pair, not vs-anchor-only);
- the fit AND the bootstrap CI use the admissible pairs ONLY;
- a policy is RATED iff it lies in the anchor's connected component in the admissible-pair graph; every other policy is **UNRATED** (reported by name + reason, no number printed — the anchor stays 0 by construction: it is the reference, not a claim);
- `doc["unrated"]`, `doc["fit_excluded_pairs"]` (with each pair's wr CI), per-pair `in_fit` flag, and `headline_claims` = rated non-anchor policies.
- Test-finding recorded (a real trap in the domain): a draw-heavy pair (10w/30d) has winrate FLOOR 0.5 (an all-draw resample still scores 0.5), so its CI lies entirely ABOVE 0.5 and it is legitimately admissible — the under-powered case is the coin-flip pair (20w/20b), whose CI is symmetric around 0.5. The test asserts exactly this.

## Item 3 — pool default + engine git-stamp
- `elo.py --pool` default: "all" → **"engine"** (rig-aligned; "all" mixes in the 19 uncompiled engine-flagged cards and shifts every supply — the audit's pool-default mismatch). `ab_duel.py` keeps "all" (single-duel scratch use) but stamps the pool it played.
- `doc["engine"] = {git_head, mtgbot_dirty_files, set, pool}` — the table now stamps the ENGINE BUILD, not just the date (dirty count matters because the export/overlay path can add to HEAD).

## Item 4 — era-parity sentinel cell in every ladder run
- Pinned from /123 (2026-10-19 shadow 2×2 grid, M21 engine-pool control): `bsh_S3a_s3_best vs random, set=M21, pool=engine, n=40 → ref 0.575`, 95% binomial band [0.422, 0.728] (0.575 ± 1.96·√(0.575·0.425/40)).
- Every `run_ladder` re-plays the cell (fresh D9 seeds; `--sentinel off` to skip) and records `doc["sentinel"] = {measured, ref, band, crashes, seeds, ok, provenance}` + `doc["era_invalid"]`. Out of band ⇒ the table prints flagged, but **no claim rides it** (harness/engine drift would confound the era comparisons the matrix exists to make).
- A silent re-pin of the control cell is itself drift: `test_sentinel_band_status` pins the reference values (0.575 / n=40 / M21 / engine / the exact checkpoint path).

## Verification (VERIFIED = EXECUTED)
- **test_duel_elo.py 17/17** (13 pre-existing + 4 new): `test_fit_excludes_inadmissible_pairs` (exclusion bookkeeping + decisive gap: admissible-only fit keeps B−A ≈ wide while the old full-pair fit balances the 50/50 pair at A==B), `test_unrated_component_isolation` (C reachable only via all-draw pairs ⇒ UNRATED), `test_all_inadmissible_all_unrated` (fit empty, anchor 0 by construction, others unrated), `test_sentinel_band_status`. The schema test was STRENGTHENED: at 4 games/pair the old code fabricated ratings for scripted/first; the test now asserts ratings == {random} and both others UNRATED + 3 fit-excluded pairs + engine stamp + the supply-scoped anchor string.
- **Collector invariance (the night-3 invariant)**: 2-game re-collect from the updated tree at the exact P2 seeds (seed-base 510201 ⇒ first games 510202/510203 — the block is base+1; rl-seed 4244, dps 1412, engine pool) ⇒ rows SEMANTICALLY BYTE-IDENTICAL to night-2's `episodes_iter1.jsonl` (112 asks each; max|Δlogp| = 0.0; all obs/outcome/rng_seed equal). The only differing field is the `policy` path string, which is cwd-dependent by design (rig records the path it was given); the window always runs from the export cwd, so tonight's rows will carry the identical export path as night-2's ⇒ byte-identical re-collect preserved. (Module-level proof also holds: gameplay_eval_v2 imports neither ab_duel nor elo.)
- **Ladder real-mode smoke** (engine up, changed dimension in real mode): `elo random scripted bsh_S3a_s3_best --games 4 --workers 2 --pool engine --set M21 --reps 120` ⇒ rc=0 in 46 s (12 round-robin + 40 sentinel games). Output verified live: `anchor: random=0 (set=M21, pool=engine)`; `engine: 3a1e05b (dirty=1)` (a sibling-session commit landed mid-work — the stamp honestly reports the live build, which is what it exists for); **sentinel measured 0.438 (ref 0.575, band [0.422, 0.728]) → OK** (inside the 95% binomial band at n=40, toward its edge — honest measurement recorded); both non-anchor policies **UNRATED** ("no admissible path to the anchor (every pair's bootstrap winrate CI straddles 0.5)") — the fabricated-rating hole closed in real mode; all 3 pairs fit-excluded and listed; `headline claims: NONE`. Multiprocess path exercised (workers=2 → spawn pool with the new set_code initargs).

## Window impact (night-3, armed 23:59)
Payload tree changed (tools/training: ab_duel.py, elo.py, test_duel_elo.py) ⇒ explicit re-pin (provenanced with the evidence above) + dry-run rebuild from the pinned payload + the armed lever (/158: lr 1e-2 × 1 step) is untouched by this work. The deterministic re-collect will reproduce night-2's episodes (invariant above); audit + training + probe run exactly as pre-registered in /158.

## Day-queue state (/154)
Item 1 (T-G5 ladder) DONE. Remaining: §3.1.4 active-player fallback fix + legacy re-collect (gameplay_eval_v2.py); ZNR `1+*` shape gap (parse_pt); bench sizing per DESIGN §6.
