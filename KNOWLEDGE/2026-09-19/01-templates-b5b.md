# 2026-09-19 · 01 — B5b bucket implementation + test (`templates_b5b.py` / `test_templates_b5b.py`)

**Context:** B5b (static modifier / continuous-effect shapes) was the last of the missing bucket
modules flagged in the 2026-09-16 stop note (B2b landed 2026-09-18; B5c also landed in between but
was never recorded in NUMBERS.md — see baseline reconciliation below). This note records the
completed B5b template module, its test suite, the verified coverage partition, and the final
green validation state.

## What was built
- `MTG_bot/core/compiler/templates_b5b.py` (1,476 lines):
  - `_BUCKET = "B5b"`, `_PRIORITY = 100`.
  - `TEMPLATES` contains **35** templates (11 module-private selector helpers + 35 builders).
  - `UNCOVERED` contains **51** `(concrete_sentence, reason)` tuples.
  - Patterns `re.fullmatch` the **concrete** oracle sentence (B5b.json keys are normalized; the
    concrete rows in `/tmp/opencode/b5b_table.txt` drive the patterns).
- `MTG_bot/core/compiler/test_templates_b5b.py` (1,370 lines), **54 tests**:
  - `TestTemplateInventory` — 35 templates, unique tids, bucket, priority, registry wiring.
  - `TestShapeTable` — 91-row SHAPES table integrity (40 COVERED / 51 UNCOV, unique sentences,
    tid validation against `TEMPLATES`).
  - `TestMatching` — PC-3: every COVERED sentence matches exactly one template with the right
    tid; every UNCOV sentence matches zero.
  - `TestStructuralAssertions` — per-builder IR checks for all 35 tids across the 40 covered rows
    (verbs, roles, quantities, selectors, TokenSpec, Cost parts, KeywordAbility).
  - `TestCanonicalStability` — PC-4: rebuild each covered outcome, `canonical_json` identical;
    35 unique tids.
  - `TestEndToEndCompile` — `compile_card` on Shock, Opt, Basri's Solidarity, Fungal Rebirth,
    Gnarled Sage, Garruk's Warsteed.
  - `TestB5bJsonCrossCheck` — optional; skipped if `/tmp/opencode/phase1_buckets/B5b.json`
    absent; asserts 90 shapes and sentence-set equality with the SHAPES table.

## Verified B5b bucket partition
Source: `/tmp/opencode/phase1_buckets/B5b.json`

| Quantity | Value |
|---|---:|
| normalized shape keys | 90 |
| concrete occurrences | 112 |
| distinct concrete sentences | 91 |
| covered shapes | 39 |
| covered concrete rows | 40 (one shape carries two concrete rows) |
| covered tids | 35 (32 single-shape + 3 multi-shape) |
| uncovered shapes / rows | 51 / 51 |
| `UNCOVERED` entries | 51 |
| rule-reminder pre-consumed | 0 |
| RR shapes | 0 |

Multi-shape tids: `B5b-put-counter` (3 shapes), `B5b-return-cards-hand` (2), `B5b-named-damage` (2);
two-row shape: `B5b-modpt-plus` (+1/+1 variants).

## 35 covered TIDs
```text
B5b-cont-discard            B5b-cont-draw               B5b-cont-gain-4
B5b-cont-gain-mv            B5b-damage-any              B5b-discard-target-2
B5b-flash                   B5b-haste                   B5b-hexproof
B5b-lifelink                B5b-look-3                  B5b-menace
B5b-modpt-minus             B5b-modpt-plus              B5b-modpt-x
B5b-named-damage            B5b-perm-hex-ind            B5b-prowess
B5b-put-counter             B5b-reach                   B5b-return-cards-hand
B5b-return-creatures-battlefield  B5b-reveal-hand       B5b-sacr-flying
B5b-sacr-grant              B5b-scr                     B5b-scr-reveal
B5b-search-shuffle          B5b-seq-modpt-firststrike   B5b-seq-modpt-hexproof
B5b-seq-modpt-trample       B5b-tap-2-target            B5b-tap-spirits
B5b-token-demon             B5b-token-zombie
```

## Key IR decisions
- Keyword shapes (flash/haste/hexproof/lifelink/menace/prowess/reach) build `KeywordAbility`;
  end-to-end they land in `card.keywords`, **not** `card.abilities` (caught by a first-run test
  failure in `test_gnarled_sage_reach`; assertion fixed to check `card.keywords`).
- `B5b-reach` pattern matches the full reminder text
  `Reach (This creature can block creatures with flying.)` — it is not intercepted by
  `_is_rule_reminder` (not full-paren; bare-stripped form never equals a raw keyword).
- Continuous effects (`cont-*`) build `StaticAbility` with `DurationEot`-free persistent effects.
- `B5b-modpt-x` models "X is the number of ... " via `QX()`; mana-value-driven `cont-gain-mv`
  uses `QProp(MANA_VALUE, QAgg.FIRST)` style referents.
- Token shapes carry no color (grammar `TokenSpec` has no color field — documented loss).
- Activated shapes (`sacr-grant`, `tap-spirits`) use `Cost(CostSacrifice)` / `Cost(CostTap)`.

## Verification
Commands run from `/home/sune/Desktop/MTG_AI` with the project venv active:

```bash
.venv/bin/python -m pytest MTG_bot/core/compiler/test_templates_b5b.py -q
# 54 passed in 0.79s

.venv/bin/python -m pytest MTG_bot/core -q
# 724 passed in 1.44s

pyright MTG_bot/core/compiler/templates_b5b.py MTG_bot/core/compiler/test_templates_b5b.py
# 0 errors, 0 warnings, 0 informations
```

### Baseline reconciliation (important)
`724 = 611 (2026-09-18 post-B2b) + 54 (new B5b) + 59 (B5c, landed after 2026-09-18 but never
recorded in NUMBERS.md)`. B5c's 59 tests were verified via
`pytest MTG_bot/core/compiler/test_templates_b5c.py --collect-only` on this date. The B5c
implementation note still needs a retroactive entry; this reconciliation keeps the 724 total
admissible.

## Traps found
No new entries required — the recurring pyright union-narrowing trap (unittest
`assertIsInstance` invisible to pyright) is already standing in `PITFALLS.md` (2026-09-15 entry);
it recurred here for `Seq.steps` and `ActivatedAbility.cost` and was fixed with `_as_seq` /
`_as_activated` typed guards, matching the B4/test_compiler convention.
