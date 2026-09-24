# 2026-09-17 · 01 — Bucket work-input regeneration (tools/gen_buckets.py)

**Context:** machine reboot wiped `/tmp/opencode/phase1_buckets/*.json`; 39 test
failures (31 FAILED + 8 ERROR, all in `test_templates_b{1,3,4}.py`, zero real bugs)
blocked the session. Baseline before regeneration: 469 passed / 39 broken / 2 skipped
(out of the 510 at the 2026-09-16 stop).

## What was built
`tools/gen_buckets.py` (new, 217 lines, deterministic, assertion-gated) regenerates
all 8 bucket files from `MTG_bot/data/M21.json` via `ingest_pool`. Only file added;
no existing file modified.

## Reverse-engineered classifier (asserted in the script)
- **Shape normalization:** uniform `re.sub(r"\d+", "N", s)` — digits (braced or bare)
  → `N`; mana symbols, card names, and punctuation preserved verbatim. No `~`
  substitution anywhere (verified: `grep -c '~' templates_b2a.py` = 0).
- **B1** (15 shapes / 49 occ) = sentences fullmatched by `templates_b1`.
- **B2** = trigger keys matching `^(When|Whenever|At (the )?(start|beginning))\b` →
  exactly **124 shapes**. Note: "As …" sentences are NOT triggers here — the 7 of
  them fall into B5. (The session-1 census regex included `As ~`; the bucket
  classifier does not. Supersedes the census regex for bucket purposes only.)
- **B2a** = 45 `templates_b2a` pattern-matched keys ∪ 17 pinned UNCOVERED = 62;
  exactly the first alphabetical half of B2 (asserted). **B2b** = B2 − B2a (62).
- **B3** (48/55) = 41 pattern-matched ∪ 7 UNCOVERED. **B4** (47/63) = 18 ∪ 29.
- **B5** = remainder = **270 shapes**; B5a/B5b/B5c = alphabetical thirds of 90.
  B5a's concrete sentences exactly equal the 90-entry SHAPES table in
  `test_templates_b5a.py` (imported, not transcribed) — so
  `TestB5aJsonCrossCheck` now runs instead of skipping.

## Re-measured bucket table (post-regeneration)
| Bucket | shapes | occurrences |
|---|---|---|
| B1 | 15 | 49 |
| B2a | 62 | 66 |
| B2b | 62 | 76 |
| B3 | 48 | 55 |
| B4 | 47 | 63 |
| B5a | 90 | 118 |
| B5b | 90 | 112 |
| B5c | 90 | 100 |
| **total** | **504** | **639** |

Total occurrences = 639 = pool-level sentence count pinned by `test_ingest.py`.
Unique shape keys = 504 (matches the handoff's "504 unique shapes across 8 buckets").

## Verification
- `python tools/gen_buckets.py` — all internal assertions pass.
- `python -m pytest MTG_bot/core -q` → **510 passed / 0 failed** (restored the
  2026-09-16 stop baseline; b5a cross-check tests now run, 2-skipped → 0).
- `ruff check` / `ruff format --check` clean.

## Standing rule (for future bucket work)
Bucket shape keys are byte-pinned by the `UNCOVERED` tuples in
`templates_b{2a,3,4}.py` and the `SHAPES`/`EXPECTED_KIND` tables in the bucket
test files. Any generator or test change that alters a shape key is a
knowledge-tree event. Regenerate with `python tools/gen_buckets.py` — never by hand.
