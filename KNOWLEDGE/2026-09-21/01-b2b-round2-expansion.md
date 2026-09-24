# 2026-09-21 · 01 — B2b round 2: 20-shape expansion via T3 grammar (`templates_b2b.py` / `test_templates_b2b.py`)

**Context:** T3 round-1 grammar additions (2026-09-19: `CastSpellEvent` controller/ordinal/
`from_zone`, `CardDrawnEvent`, `SacrificeEvent`, `TapStateEvent`, `EachPlayer`,
`Cost`/`CostManaGeneric`, `KeywordAbility`, `ZonePosition`, `POWER_GE`/`COLOR_IN`/`NAME_EQ`,
`Verb.PAY`/`CAST`/`LOSE_GAME`) unblocked the cast/draw/sacrifice/tap families that were
UNCOVERED in the 2026-09-18 B2b session. This note records the round-2 expansion, the
updated verified partition, and the final green gate state.

## What changed
- `MTG_bot/core/compiler/templates_b2b.py` (now 1,711 lines):
  - `TEMPLATES`: **18 → 36** (18 new templates).
  - `UNCOVERED`: **44 → 24** (20 shape keys consumed).
- `MTG_bot/core/compiler/test_templates_b2b.py` (now 1,634 lines): **40 → 73 tests**.
  - `TestB2bCoverage` — 12 (assertion constants updated: `TEMPLATES == 36`,
    `UNCOVERED == 24`, covered shapes 38, matched occurrences 52, `EXPECTED` rows 38).
  - `TestB2bTriggerEvents` — 10 → **25** (15 new trigger tests, incl. one negative
    `ValueError` pin).
  - `TestB2bEffectStructure` — 18 → **36** (18 new effect tests).
  - `EXPECTED`: 18 → **38** rows (20 new shape keys: 17 tids × 1 key +
    `B2b-named-card-search` × 3 named-card keys).

## 18 new tids
```text
B2b-named-card-search
B2b-nine-lives-leave
B2b-power-ge-enters-draw
B2b-opponent-second-spell-draw
B2b-other-enters-power-damage
B2b-flying-enters-self-boost
B2b-untapped-pay
B2b-other-rogue-enters-mill
B2b-cast-cat-create-dog
B2b-cast-dog-create-cat
B2b-noncreature-counter
B2b-riddleform
B2b-colored-cast-counter
B2b-draw-counter
B2b-draw-target-mill
B2b-draw-self-boost
B2b-draw-pay
B2b-sacrifice-any-damage
```

## Verified B2b bucket partition (round 2)
Source: `/tmp/opencode/phase1_buckets/B2b.json` (unchanged: 62 shapes / 76 occurrences)

| Quantity | Value |
|---|---:|
| normalized shape keys | 62 |
| concrete occurrences | 76 |
| covered shapes | **38** |
| matched concrete occurrences | **52** |
| uncovered shapes | **24** |
| unmatched concrete occurrences | **24** |
| `UNCOVERED` entries | **24** |
| `TEMPLATES` | **36** |

- New covered shape key numbers (1-indexed over the 62): 1, 2, 3, 9, 16, 21, 22, 23, 39,
  45, 49, 50, 51, 52, 53, 55, 56, 57, 58, 62 — each 1 occurrence, so matched occurrences
  = 32 (round-1) + 20 = **52**.
- Remaining uncovered key numbers: 4, 8, 12, 15, 17, 18, 19, 20, 26, 27, 30, 31, 34, 37,
  38, 40, 41, 42, 47, 48, 54, 59, 60, 61.
- PC-3 ambiguity zero: every covered concrete sentence matches exactly one template, every
  uncovered concrete sentence matches zero, patterns pairwise disjoint over concrete
  sentences, and no template matches any of the 24 N-normalized uncovered sentences.

## Key IR decisions (round 2)
- **`B2b-named-card-search`** (3 named-card shapes: Chandra, Flame's Catalyst / Garruk,
  Savage Herald / Teferi, Timeless Voyager): `SEARCH` (selector `QConst(1)` CHOOSE
  `NAME_EQ(name)`, subject zone LIBRARY/YOU, `zones=(GRAVEYARD, YOU,)`) → `REVEAL`
  count `QConst(1)` → `MOVE_ZONE` to HAND/YOU with `ZonePosition.TOP`; whole sequence in
  `OptionalEffect` ("you may"); trigger is the standard ETB
  `ZoneChangeEvent(ANY/ANY → BATTLEFIELD/YOU)`.
- **Cat/Dog token pair** (`cast-cat-create-dog` / `cast-dog-create-cat`): shared factory
  `_cast_subtype_token_builder(trigger_subtype)` over the general pattern
  `(white|green) (?P<tok>Dog|Cat)`; only the trigger subtype differs; the color word is
  decorative — `TokenSpec` has no color field, so it is not stored.
- **"your second spell"** → `CastSpellEvent.ordinal == 2`; controller-scoped cast events
  now expressible (`controller=OPPONENT` + empty `FAnd()` filter for "any spell").
- **"deals that much damage"** (Terror of the Peaks) → `DEAL_DAMAGE` with
  `amount=QProp(referent="event", field=POWER, agg=FIRST)` — event-scoped quantity
  reference.
- **`+2/+2` counter is unbuildable** (counter kinds are ±1 only): the shape
  "Whenever you cast a noncreature spell, put a +2/+2 counter on this creature" is pinned
  as a **negative** test — `TemplateRegistry.match` propagates builder exceptions, so the
  test asserts `ValueError` through the registry.
- `EachPlayer` over `OPPONENTS` for "each opponent" mill; `Cost`/`CostManaGeneric` for
  "you may pay {…}"; `SET_PT` with `DurationEot` for "until end of turn";
  `POWER_GE` FAtom over the ETB subject; `COLOR_IN` over `CastSpellEvent.filter`.
- `PtDelta.magnitude` (not `amount`) — pre-existing PITFALLS entry, applied again in the
  new effect tests.

## Verification
Commands run from `/home/sune/Desktop/MTG_AI` with the project venv active:

```bash
python -m pytest MTG_bot/core/compiler/test_templates_b2b.py -q
# 73 passed in 0.82s

python -m pytest MTG_bot/core -q
# 899 passed in 1.59s

pyright MTG_bot/core/compiler/templates_b2b.py MTG_bot/core/compiler/test_templates_b2b.py
# 0 errors, 0 warnings, 0 informations

ruff format --check MTG_bot/core/compiler/templates_b2b.py MTG_bot/core/compiler/test_templates_b2b.py
# 2 files already formatted
```

### Core-suite reconciliation (899)
`899 = 833` (2026-09-19 post-T3) `+ 33` (B2b round 2: 40 → 73) `+ 33` (post-baseline
growth in other bucket test files with **no dated knowledge note found**:
`test_templates_b2a.py` 61 → 73, `test_templates_b5a.py` 53 → 64,
`test_templates_b4.py` 34 → 42, `test_templates_b5b.py` 54 → 56 — all verified via
per-file `--collect-only`). **Owner action needed:** backdate or document that 2026-09-20
work; the 2026-09-19/03 T3 note's 833 does not include it.

### ruff check status (not a gate, per PITFALLS 2026-09-19)
`ruff check` on `templates_b2b.py` reports **21 ISC004** (unparenthesized implicit string
concatenation in the `UNCOVERED` tuple) — same pre-existing house style as
`templates_b2a.py` (14 findings); compiler dir total 113 findings at this date. Gate
interpretation per PITFALLS: no new violation *kinds* beyond pre-existing +
`ruff format --check` clean → satisfied.

## Superseded
The coverage partition and test-count sections of `2026-09-18/01-test-templates-b2b.md`
(18 templates / 44 UNCOVERED / 40 tests / 18 covered / 32 matched / core 611) are
superseded by this note.
