# 04 — B4a: branch-coverage matcher and §E heat queue (2026-10-04)

Batch: BUGCATCH B4a · tools-only · no commits · no scenario or engine edits.
Files: `tools/audit/b4_journal.py`, `tools/audit/branch_coverage.py`,
`tools/audit/test_branch_coverage.py`, `tools/audit/branch_coverage.json`.

## Instrument

Two evidence lanes:

- pack lane: rerun every `tools/scenarios/*.json` pack in-process via
  `ScenarioRunner`; keep only green journals because a failing lane is not
  evidence.
- corpus lane: replay 20 catalog seeds (`--pool all`, deck-pair seed 1409,
  60 turns) via `detectors.replay_game`.

A row is attributable to a card only when the card's handle is the row's
subject, cause, or appears in the row data. Pack attribution uses the
pack's declared real-card handles; corpus attribution uses
`detectors.ReplayData.identity_name`.

Classifications are:

- `LIT`: machine-readable signature appeared on an attributable row.
- `DARK`: machine-readable signature was never seen.
- `UNMATCHABLE`: the journal lacks the referenced vocabulary. Current
  honest classes are `mode-choice` (chosen-mode index is not journalled)
  and `verb-tag` (verb never appears as any observed cause verb).

## Measured output

`python tools/audit/branch_coverage.py` over 304 green pack journals and
20 corpus seeds:

- 97 declared branches.
- 28 LIT.
- 22 DARK.
- 47 UNMATCHABLE.
- `fabled_passage:01:Conditional` → OK.
- Life Goes On died precedent → NOT-DECLARED in B1; attributed
  `LIFE_GAINED` evidence was present.

Heat is DARK-only: `BCS × (1 + len(collision_flags))`, ties by BCS, card
name, and branch id. No collision-flagged card reached the emitted top 15.

## CAST caveat (binding for later B4 adjudication)

Eight verb-`CAST` branches remain DARK. The 13b `KIND_CAST` row is
`(caster, ordinal, spell_kind, from_zone, x_value)` and names the spell,
not the permanent granting permission. Therefore the current matcher
excludes a card's own casting as the may-cast side and does not claim an
effect-cast other spell is attributable from the explicit CAST row alone.
A future positive control must expose an attributable world-diff row or
introduce an explicit cast-source journal contract before these rows can
move from DARK to LIT.

## Gate ledger

- `pytest tools/audit/test_branch_coverage.py -q` → 14 passed.
- `pytest tools/audit -q` → 48 passed.
- `pytest MTG_bot/core -q` → 2350 passed + 3 subtests, unchanged.
- `pyright` on the three new Python files → 0 errors, 0 warnings, 0
  informations.
- `ruff check` on the three new Python files → all checks passed.

## Ruling amendment (2026-10-04, same day): B4a correction + B4b pair coverage

This section supersedes the heat and suspect-membership portions of the
original B4a section above. Branch totals, evidence lanes, and attribution law
remain unchanged.

### Binding decisions

- Run **A then B in one session**.
- **T = 20** for the complexity floor.
- PC-13 is gated by the **§C collision class**, not §F's literal "both ends
  BCS ≥ T". The literal rule is vacuous here because every collision-flagged
  card has BCS ≤ 16.
- Complexity floor: **BCS ≥ T on ONE end**. Both ends must still be able to
  express the class's two mechanisms.
- Membership must be disk-truth, derived from **printed names in `"real"`
  card values** across `tools/scenarios/` and `tools/audit/suspects/`.
  Handles never confer membership.
- Heat is upgraded to a §E-faithful branch instrument calibration:

  ```text
  heat(branch) =
      dark
    × BCS
    × (1 + collision-flag-derived class weight)
    × (1 + card anomaly_hits from anomalies.json)
  ```

- Card rollup:
  `card_heat = dark_branch_count × mean(branch heat)`.
- Pair heat:
  `BCS_a × BCS_b × class weight × 1[untested]`.
- Engine option C (`cast-source` journal field) remains **deferred**. B4b does
  not close the CAST attribution gap.

### Corrected A results

- Branch totals remain **97 / 28 LIT / 22 DARK / 47 UNMATCHABLE**.
- Disk membership corrected `bcs.json`:
  - in-pack cards by printed name: **276**.
  - `in_pack`: **267 → 276**.
  - `in_suspect`: **22 → 0** because `tools/audit/suspects/` is empty.
  - membership flags changed on **22** cards.
  - all 22 stale suspect cards are covered by a green pack anyway.
- PC-11 at T=20 after disk truth:
  - cards at or above T: **66**.
  - covered: **65**.
  - true residue: **1** — `Sublime Epiphany`, BCS 29.
  - curve: T=10 → 8, T=15 → 2, T=20 → 1, T=25 → 1, T=30 → 0.
- `anomalies.json` has `all_hits` empty in both catalog and replay summaries,
  so the anomaly factor is wired but inert.
- Top branch heat remains the high-BCS DARK OptionalEffect/Selector branches
  because the flagged cards are low BCS and no anomaly hits fired:
  `Chandra, Heart of Fire` 37; `Chandra, Flame's Catalyst` 34;
  `Garruk's Harbinger` and `Radha, Heart of Keld` 32;
  `Demonic Embrace` 29; `Liliana's Devotee` 24; `See the Truth` 19.
- Top card rollup:
  `Garruk's Harbinger` 96 / dark 3 / mean 32;
  `Chandra, Heart of Fire` 74 / dark 2 / mean 37;
  `Chandra, Flame's Catalyst` 68 / dark 2 / mean 34;
  `See the Truth` 38 / dark 2 / mean 19;
  `Jeskai Elder` and `Waker of Waves` 34 / dark 2 / mean 17.

### B4b pair matrix result

Instrument: `tools/audit/pair_coverage.py`.
Artifact: `tools/audit/pair_coverage.json`.
Command: `.venv/bin/python tools/audit/pair_coverage.py --quiet`.

Headline:

- Candidate pairs: **8577**.
- Tested: **2399**.
- Untested: **6178**.
- Classes with zero tested coverage: **none**.
- Pairs co-fired in corpus: **2389**.
- Pairs designed in packs: **13**.
- Corpus games: **20**.
- Pair universe: **17919**.

Per-class coverage:

| Class | Members | Candidate pairs | Tested | Coverage |
|---|---:|---:|---:|---:|
| `pt_layers` | 108 | 3003 | 681 | 22.68% |
| `replacement_x_replacement` | 27 | 273 | 70 | 25.64% |
| `replacement_x_trigger` | 9 | 36 | 9 | 25.0% |
| `grant_x_consumer_missing` | 108 | 3003 | 681 | 22.68% |
| `sacrifice_x_dies_token_anthem` | 124 | 4223 | 1004 | 23.77% |
| `x_census_x_name` | 56 | 1404 | 420 | 29.91% |
| `branch_entanglement` | 124 | 4386 | 1370 | 31.24% |

Top untested pair: `Basri Ket + Siege Striker`, heat **3710**, co-fire **0**,
classes `pt_layers` and `grant_x_consumer_missing`. The top ten untested pairs
are all zero co-fire and mostly involve `Basri Ket`, the BCS-70 card.

### Honest co-fire limit

Co-fire means both cards were attributable to some row in one replay. It does
**not** prove the two mechanisms resolved against each other in the same layer,
replacement window, or trigger stack. PC-13 coverage from this instrument is a
work order for forced splices, not a clean bill of health.

### Deferred engine instrumentation spec

Trigger met: material verb-`CAST` branches still cannot be attributed from
journal rows alone. Proposed contract:

- Extend the 13b `KIND_CAST` row, or add a sibling world-diff row, with an
  explicit `source_handle`/`source_ref` for the permanent or effect that
  granted permission.
- Keep `subject = spell cast` and `cause = spell cast` for existing consumers.
- Attribution law for may-cast branches: the granting permanent is attributable
  only through this source field, never through the spell's own handle.
- Positive control: a green pack where a permanent grants an extra cast and the
  new source field appears on the cast row.
- Negative control: the same card without the grant must not produce that row.
- Until then, the eight verb-`CAST` branches stay DARK.

### Updated gate ledger

- `.venv/bin/pytest tools/audit -q` → **60 passed**.
- `.venv/bin/pytest MTG_bot/core -q` → **2350 passed + 3 subtests**, unchanged.
- `.venv/bin/python tools/audit/branch_coverage.py --quiet` →
  **97 branches: 28 LIT / 22 DARK / 47 UNMATCHABLE**.
- `.venv/bin/python tools/audit/pair_coverage.py --quiet` →
  **8577 candidate pairs: 2399 tested / 6178 untested**.
- `pyright` on the six audit Python files → **0 errors, 0 warnings, 0
  informations**.
- `ruff check` on the six audit Python files → **all checks passed**.
