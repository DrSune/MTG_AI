# 2026-09-15 / 02 — ingest: adversarial review fixes, re-measured baselines

Follow-up to `01-ingest-dedup-decision.md`. `MTG_bot/core/compiler/ingest.py`
and `test_ingest.py` were hardened after adversarial review. The fixes changed
two M21 baseline numbers (sentence split) and clarified emblem/token handling,
validation, and dedup semantics.

## Fixes

### 1. Sentence splitting is now paren-depth-aware

`split_sentences` no longer uses the flat rule
`(?<=[.?!])\s+|\n` alone. It tracks parenthesis depth and does not split on
period/question/exclamation followed by whitespace while inside parentheses,
after stripping the candidate sentence.

This matters because reminder text often contains multi-sentence parenthetical
clauses such as temple text, `Discontinuity`, `Mazemind Tome`, and keyword
reminders. The old rule over-split those clauses.

Old rule still reproduces the historical baselines exactly:

- file level: `952` total / `509` unique
- pool level: `655` total / `516` unique

New paren-depth-aware baselines:

- file level: `927` total / `503` unique
- pool level: `639` total / `510` unique

Delta: `25` sentence boundaries inside parentheses are no longer split.
Twenty-three card records changed; zero token records changed.

Affected card records:

- `Temple of Epiphany`, `Temple of Malady`, `Temple of Mystery`,
  `Temple of Silence`, `Temple of Triumph`: 2 printings each, `5 -> 4`
- `Speaker of the Heavens`: 2 printings, `4 -> 3`
- `Discontinuity`: 2 printings, `5 -> 3` each
- `Mazemind Tome`: 2 printings, `6 -> 5`
- `Opt`, `Riddleform`, `Spined Megalodon`, `Wall of Runes`,
  `Alchemist's Gift`, `Malefic Scythe`, `Short Sword`: 1 printing each,
  one sentence boundary merged

Correction to an earlier session note: "Opt ×16" was a mismeasurement. The
file contains exactly one record named `Opt`; card reminder text does not
normally contain the literal substring `Opt (`.

### 2. Emblems are not tokens

Real M21 token records include 17 `token` records and 3 `emblem` records.
The emblems are:

- `Basri Ket Emblem`
- `Garruk, Unleashed Emblem`
- `Liliana, Waker of the Dead Emblem`

All have `layout == "emblem"`, `type == "Emblem"`, `types == ["Emblem"]`,
`colors == []`, and `relatedCards` containing only `reverseRelated` owner
names.

`ingest_card` now sets:

- `is_emblem = layout == "emblem"`
- `is_token = layout == "token" or "Token" in types`

Thus emblems are no longer classified as tokens.

### 3. `related_names` is captured

`RawCard.related_names` is a sorted, deduplicated tuple of all string values
in every list under `relatedCards`. For current M21 emblems this yields owner
names:

- `56c1893f-1382-4a31-a28a-ea604677fcdb`:
  `("Liliana, Waker of the Dead",)`
- `8a908da7-b41c-4712-b7dc-8c6027875d36`:
  `("Garruk, Unleashed",)`
- `ab67e4ec-9392-4130-970f-6ad65656e5c1`:
  `("Basri Ket", "Soldier")`

Names are kept verbatim even if future dumps mix card names and UUIDs; the
field is raw capture, not semantic resolution.

### 4. Validation tightened

`ingest_card` now raises `StateCorruptionError` for:

- missing or blank `type`
- `colors` containing a character outside `WUBRG`
- `colorIdentity` containing a character outside `WUBRG`
- negative integer `manaValue`
- `relatedCards` that is not a dict of lists of strings

`name` remains required. Oracle text is optional.

### 5. Dedup key is explicit

`ingest_pool` compares `_dedup_key(card)`, an explicit tuple over every
captured `RawCard` field, including identity subfields, text/sentences,
layout, `is_token`, `is_emblem`, and `related_names`.

This makes the dedup rule precise:

- reprint printings that differ only in uncaptured raw fields
  (`number`, `uuid`, `rarity`, `purchaseUrls`, etc.) dedupe to one entry;
- same oracle id with a difference in any captured field is corruption.

This supersedes the less explicit "identical duplicates" wording from
`01-ingest-dedup-decision.md`, though the decision is unchanged.

## Measurements

Pinned by `TestSmokeRealM21Pool`:

| Number | Value |
|---|---|
| file-level records | 397 cards + 20 tokens |
| file-level cards with text | 391 |
| file-level sentences | **927 total, 503 unique** |
| pool entries | 305 (285 normal + 17 token + 3 emblem) |
| pool with text | 291 |
| pool sentences | **639 total, 510 unique** |
| pool keywords | 24 distinct, 119 total |
| pool mana value | 0:44, 1:30, 2:63, 3:68, 4:43, 5+:57 |

Exit gate:

```bash
cd /home/sune/Desktop/MTG_AI && source .venv/bin/activate
python -m pytest MTG_bot/core -q
```

Result: `288 passed / 0 failed`.

## Supersedes

- Supersedes the M21 sentence counts in
  `KNOWLEDGE/NUMBERS.md` 2026-09-14: `952/509` file-level.
- Supersedes the pool sentence counts in
  `KNOWLEDGE/2026-09-15/01-ingest-dedup-decision.md`: `655/516`.
- Clarifies the dedup rule from
  `KNOWLEDGE/2026-09-15/01-ingest-dedup-decision.md` in terms of the
  explicit `_dedup_key`.
- The discipline from `PITFALLS.md` remains: changing the sentence split is
  a knowledge-tree event, not a silent bugfix.
