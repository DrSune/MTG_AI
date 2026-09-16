# 2026-09-15 / 01 — ingest: reprint-duplicate oracle ids, dedup decision

Phase 1 step 1 shipped: `MTG_bot/core/compiler/ingest.py` (+ `__init__.py`,
`test_ingest.py`). MTGJSON v5 → structured `RawCard` records keyed on
`scryfallOracleId`; sentence tuple is the template compiler's input.

## Discovery: the M21 pool file has duplicate oracle ids

`MTG_bot/data/M21.json` is not a clean single-set MTGJSON dump. Of its 397
card records, **112 repeat an oracle id** that already appears earlier. Every
such duplicate is *structurally identical* to its first occurrence — name,
type line, colors, cost, P/T, text, everything; only `number` and `uuid`
differ (reprint printings appended to the set file). **0 conflicting
duplicates** (same id, different card) exist in this file.

Command: inline probe over `data.cards` grouping by
`identifiers.scryfallOracleId` (session 2026-09-15); pinned permanently by
`TestSmokeRealM21Pool` in `MTG_bot/core/compiler/test_ingest.py`.

## Decision: dedup identical, raise on conflict

The oracle id names the *card*, not the printing. `ingest_pool` therefore:

- dedupes **identical** duplicates to one entry (first occurrence wins —
  deterministic), and
- raises `StateCorruptionError` on a **conflicting** duplicate (same id,
  different card content) — genuine corruption.

This deviates from the step-1 spec's "exactly 397+20 pool entries" + "raise
on any duplicate oracle id": those two requirements are mutually
unsatisfiable for this file (a dict keyed by oracle id cannot hold 417
entries when only 305 ids exist). The **file-level** record counts are
unchanged (397 card records + 20 token records); the **oracle-id-keyed
pool** is 285 cards + 20 tokens = **305 entries**.

Consequence for Phase 1 targets: any coverage denominator expressed as "the
pool" must decide file-level (417 records) vs oracle-keyed (305 cards).
PC-1's "≥ 90% of pool cards fully compiled" is expected to use the 305-card
denominator — revisit when PC-1 is measured.

## Correction of a session-1 number

NUMBERS.md 2026-09-14 said "6 blank = basic lands" for the no-text card
records. **Wrong**: the 6 no-text records are creatures — Staunch Shieldmate,
Wishcoin Crab, Walking Corpse, Onakke Ogre, Garruk's Gorehorn (×2, the
duplicate pair). Basic lands in this dump *do* have text (`({T}: Add {W}.)`),
which ingest keeps as one structured sentence.

## Pool-level measurements (oracle-id-keyed, post-dedup)

Pinned by `pytest MTG_bot/core/compiler -q` (`TestSmokeRealM21Pool`):

| Number | Value |
|---|---|
| pool entries | **305** (285 cards + 20 tokens) |
| with text | **291** |
| sentences | **655 total, 516 unique** |
| layouts | normal 285 / token 17 / emblem 3 |
| keywords | 24 distinct, 119 total |
| mana value | 0:44, 1:30, 2:63, 3:68, 4:43, 5+:57 |

The sentence split rule `(?<=[.?!])\s+|\n` reproduces the pre-registered
file-level baselines (952 sentences / 509 unique over the 391 no-text-free
card records) exactly — the rule is confirmed, not adjusted.

## Test state

`MTG_bot/core/compiler`: 34 passed. `MTG_bot/core`: 80 passed (46 pre-existing
identity/state/errors + 34 new). No LSP diagnostics on the three new files.
