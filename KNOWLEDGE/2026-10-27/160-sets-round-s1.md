# 160 — Sets round S-1: new sets no longer crash the compiler; keyword lines; an honest deal pool (2026-10-27)

Follows /159. **The code is on branch `sets/onboarding`** (commits `d21b573` and `4baada8`,
pushed to origin). It merges to `main` after the night-3 export, because `rl_window.sh`
fingerprints `MTG_bot/*.py`. After the merge, the next window needs the usual re-smoke and explicit
re-pin. M21's compile output and its supply are byte-identical, so the pilot's game does not
change; only the hash does.

## What changed (branch)
- **B-36 fixed.** The `B3-grant-kw-*` alternation is built from `_KW_MAP`, so "…gains haste…"
  becomes an honest unparsed sentence instead of a `KeyError` that killed whole-set compiles.
- **B-37 fixed.** A Vehicle (printed P/T on a non-creature) is a `StateCorruptionError`, i.e. a
  shape gap, instead of a `ValueError`.
- **B-38 fixed.** An emblem whose planeswalker is a back face stays an orphan, in `compile_pool`
  and in the tolerant pass.
- **B-39 fixed.** Ingest merges token printings that differ only in `relatedCards`. ELD and IKO
  ingest again.
- **B-41, first general mechanism.** A line of bare keywords, with optional reminder text, is a
  rule reminder when every keyword is carried by the identity and built bare
  (`compiler._is_keyword_line`).
  - It runs as a fallback after template matching, so no sentence that compiles today is re-read.
  - The abilities already came from identity keywords, so only the register changes.
- **B-28 addressed (opt-in).** `compile_supply("compiled", set)` deals only castable cards with no
  unparsed text, ambiguity or unparsed face. On M21 it equals `castable`.

  | Set | castable | compiled |
  |---|---|---|
  | M21 | 239 | 239 |
  | ZNR | 219 | 96 |
  | M20 | 249 | 96 |
  | KHM | 202 | 25 |

  Defaults are unchanged.

## Checks
- M21 goldens: 305/305 byte-identical. M21 PC: 1.0 / 1.0.
- Compiled trees, with `PYTHONHASHSEED` fixed (unfixed, a frozenset's `repr` order varies per
  process):
  - zero changes on ZNR and M20;
  - on KHM, only the six cards that used to crash.
- ZNR: PC-1 0.3830 → 0.3936 (111/282); PC-2 0.5496 → 0.5634; unparsed 327 → 317.
- Worktree suites:
  - `pytest MTG_bot`: the 2 D3/D11 gates fail, 3451 pass (the 17 new tests included);
  - `pytest tools`: exit 0. Checkpoint tests skip there, because `.pt` files are untracked.
- Fuzz (`znr_engine_smoke.py --set M20|KHM --games 40`): 40/40 games and 0 crashes on each.
- Bench, `duel --a uniform --b pass --set M20|KHM --pool compiled --deals 10`: 20/20 wins each and
  0 voids. Both new sets play end to end.

## Round-end sealed read (one per set, logged in `reports/sealed_reads_*.tsv`)

| | M20 dev | M20 test | KHM dev | KHM test |
|---|---|---|---|---|
| PC-1 first touch → S-1 | 0.0955 → 0.1146 | 0.1333 → 0.1524 | 0.0389 → 0.0389 | 0.0259 → 0.0431 |
| PC-2 first touch → S-1 | 0.3531 → 0.3798 | 0.2918 → 0.3219 | 0.2954 → 0.3263 | 0.2602 → 0.2853 |
| PC-2 unseen shapes → S-1 | 0.0973 → 0.1283 | 0.0559 → 0.0870 | 0.1094 → 0.1374 | 0.1137 → 0.1333 |

- **Whole set:**
  - M20: PC-1 0.305 → 0.320; dealable fully compiled cards 91 → 96.
  - KHM: crashes 6 → 0, shape gaps 3 → 8 (the vehicles); KHM is dealable again.
- **The sealed split did its job.** The test split moved as much as dev, so the rule generalizes
  rather than fitting the dev register.
- **It is still a small step.** About 89% of unseen sentence shapes remain unparsed. Tied rank 1
  needs compositional parsing (B-41), not more shapes.

## Open items in this lane
- **B-40** (PC-2 counts shape-gap sentences as matched) is left alone. The ZNR gap card is
  Nighthawk Scavenger, which the local agent's queue item "ZNR `1+*`" may remove.
- **Grant keywords beyond the four.** Haste, vigilance and the rest can join `_KW_MAP` once each
  has an executor test showing the granted keyword is honoured.

## Ops warning for tonight (seen 12:05)
The main tree's payload fingerprint no longer matches PIN `8ef64d61…`. The cause is uncommitted
edits in `tools/training/ab_duel.py` and `tools/training/elo.py` (the T-G5 work). This lane's
commits to `main` are data, `tools/audit` and docs only, and none of them is in the payload.
Unless those edits are re-smoked and re-pinned, or set aside, before 23:59, `rl_window.sh`
aborts at the export with PIN DRIFT (exit 3). Check before the window:
`/usr/bin/find MTG_bot tools/eval tools/training -type f \( -name '*.py' -o -name '*.pt' \) ! -name 'test_*.py' | /usr/bin/sort | /usr/bin/xargs /usr/bin/sha256sum | /usr/bin/sha256sum`
must equal line 1 of `/tmp/opencode/RL_PILOT_PIN`.

Update 15:05: resolved. The T-G5 work landed as /161 (`7e0ba44`; was `9c67adf` before the 393 MB file was dropped, docs/COMMIT_MAP_2026-10-27.tsv) with an explicit re-pin
(`07fd1a6e…`, about 12:1x), and the main tree again hashes to the PIN.
