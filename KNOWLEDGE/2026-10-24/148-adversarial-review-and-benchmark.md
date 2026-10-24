# 148 — External adversarial review + instrument-first LLM benchmark (2026-10-24)

Owner request: adversarial review of goals and setup, with changes for generalization and tests;
plus a new idea, turning the project into an LLM benchmark. This note is a pointer. The content
lives in the docs below.

## Read these
- `docs/REVIEW_2026-10-24.md`: findings A-0..A-7 with re-verified citations; recommendations
  §3.1 validity → §3.2 generalization → §3.3 tests → §3.4 eval → §3.5 process.
- `docs/DESIGN_BENCHMARK.md`: tracks, the LLM tool surface, the Goodhart table, contamination,
  statistics, the scorecard (§6.1), METRICS §17 rows, ABC mapping, release gates; §10 holds the
  measured MVP numbers.
- `docs/DECISIONS.md` D19 (benchmark = instrumentation first, owner) and R9 (scoring cap/stall draws).
- `docs/BACKLOG.md`: scaffolds registered, tickets B-23..B-34, the parked public leaderboard.

## Owner decisions this session
1. Benchmark: **instrument first** (overrule clause raised and accepted); leaderboard parked.
2. Scope: docs + test fixes + MVP; no paid LLM calls; local models first, hosted later.
3. History: **drop `*.pt` from the unpushed history**, keep the files on disk, pin them by SHA-256.
4. Mid-session additions, all folded into DESIGN_BENCHMARK §3.6, §3.7, §6.1:
   - an engine primer covering ≥ 99% of atomic-subcomponent scenarios, as undubious as possible;
   - the same action space as our bot;
   - scores = Elo vs bot(s) + puzzles + LLM-vs-LLM.

## Done (all pushed; `origin/main` verified equal to local after each push)
- **History.**
  - Pushed five weeks of unpushed work: 326 commits; the last push had been 2026-09-14.
  - The checkpoint drop changed 210 SHAs, mapped in `docs/COMMIT_MAP_2026-10-24.tsv`.
  - Backups are in `~/mtg_ai_evidence/` (bundle, checkpoint copies, `/tmp/opencode` mirror).
  - Tag `backup/pre-ptdrop-2026-10-24` is local only: never push it.
- **Repairs.**
  - HEAD's pack runner was broken by R0; the uncommitted fix is now committed.
  - Overwritten eval/smoke records were restored; the later runs are kept under their own names.
  - `tools/save.sh` refuses files over 95 MB and verifies the push.
- **Tests.**
  - B0 baseline in CLAUDE.md: only the two D3/D11 gates fail.
  - 428 packs run inside pytest.
  - The R3b battery sits behind `-m red_first`; legacy failures are strict xfails
    (`MTG_bot/known_failures.txt`).
  - Checkpoint-dependent tools tests skip loudly.
  - `tools/check.sh` is the pre-push gate.
  - A tools test no longer rewrites the tracked census.
- **Engine.**
  - `DecisionStream.asking_seat`: the deciding seat travels with every ask. EachPlayer reuses one
    tag for two players, so tags alone cannot route.
  - rng `bench` stream + `substream`.
- **Benchmark MVP, `MTG_bot/bench/`** (59 tests):
  - the per-seat view with a metamorphic hidden-information test;
  - name masking;
  - the Ask protocol + exact routing;
  - `SeatRouter`;
  - the floors (Pass, UniformRandom);
  - duplicate duels;
  - stats (Wilson, paired bootstrap, SPRT, Bradley–Terry);
  - the local-first LLM seat;
  - track R;
  - the engine primer;
  - CLI `python -m MTG_bot.bench`.

## Numbers (exploratory, 2026-10-24)

| Measurement | Result |
|---|---|
| uniform vs pass, 50 duplicate pairs | 0.995 [0.985, 1.0] |
| pass vs pass | exactly 0.5 |
| uniform vs `RandomPolicy`, 40 pairs | 0.49 [0.40, 0.58]: indistinguishable |
| track R | 312 items, 0 reader mismatches; oracle 1.0; null 0.274 all-keys, 0.0 changed-keys |
| primer | 178 components, **99.92% of uses exercised** by a passing pack |

"Exercised" is not "verified"; that needs mutation testing.

## New bugs found while building
- **B-34:** `RandomPolicy.is_mana_activation` counts "Tap target creature" as a mana ability.
- **Masking:** the masker missed names outside the pool (a pack's synthetic "Garruk Omenbound").
  Fixed.

## Not done / blocked
- **Live local-LLM runs.** The endpoint lists models, but completions return 503 (backend not
  loaded; GPU lent to CED). Schedule GPU time.
- **Bot adapter.** Waits on the per-seat encoder (B-23): an omniscient bot vs an LLM is not a fair
  comparison.

## Biggest open risks (see REVIEW §0)
- The live bot is omniscient and reads card names. The RL pilot is armed on exactly that net:
  read REVIEW §3.1.1 before resuming it.
- No checkpoint beats the 100-line heuristic it imitates; the measurement overstated progress.
- The engine has no priority system, so the game being learned is "batch Magic".
