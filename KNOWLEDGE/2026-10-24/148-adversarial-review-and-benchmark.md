# 148 — External adversarial review + instrument-first LLM benchmark (2026-10-24)

Owner request: adversarial review of goals and setup, with changes for generalization and tests;
plus a new idea, turning the project into an LLM benchmark. This note is a pointer. The content
lives in the docs below.

## Read these
- `docs/REVIEW_2026-10-24.md`: findings A-0..A-7 with re-verified citations; recommendations
  §3.1 validity → §3.2 generalization → §3.3 tests → §3.4 eval → §3.5 process.
- `docs/DESIGN_BENCHMARK.md`: tracks, LLM tool surface, Goodhart table, contamination,
  statistics, METRICS §17 rows, ABC mapping, release gates.
- `docs/DECISIONS.md` D19 (benchmark = instrumentation first, owner) and R9 (scoring cap/stall draws).
- `docs/BACKLOG.md`: scaffolds registered, tickets B-23..B-33, the parked public leaderboard.

## Owner decisions this session
1. Benchmark: **instrument first** (overrule clause raised and accepted); leaderboard parked.
2. Scope: docs + test fixes + MVP; no paid LLM calls; local models first, hosted later.
3. History: **drop `*.pt` from the unpushed history**, keep the files on disk, pin them by SHA-256.

## Done (all pushed; `origin/main` verified equal to local after each push)
- Pushed five weeks of unpushed work: 326 commits, last push had been 2026-09-14.
- The checkpoint drop: 210 SHAs changed, mapped in `docs/COMMIT_MAP_2026-10-24.tsv`. Old SHAs in
  KNOWLEDGE still resolve with `grep ^<sha>`. Backups are in `~/mtg_ai_evidence/` (the bundle,
  checkpoint copies, and a `/tmp/opencode` mirror); the tag `backup/pre-ptdrop-2026-10-24` is local only.
- HEAD's pack runner was broken by the R0 Selector change; the uncommitted fix is now committed.
- Overwritten eval/smoke records were restored; the later runs are kept under their own names.
- `tools/save.sh` refuses files over 95 MB and verifies the push.

## Biggest open risks (see REVIEW §0)
- The live bot is omniscient and reads card names. The RL pilot is armed on exactly that net:
  read REVIEW §3.1.1 before resuming it.
- No checkpoint beats the 100-line heuristic it imitates; the measurement overstated progress.
- The engine has no priority system, so the game being learned is "batch Magic".
