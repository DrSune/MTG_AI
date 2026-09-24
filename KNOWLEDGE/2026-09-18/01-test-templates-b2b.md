# 2026-09-18 · 01 — B2b bucket implementation + test (`templates_b2b.py` / `test_templates_b2b.py`)

**Context:** B2b was the remaining triggered-ability bucket after B2a. This note records the
completed B2b template module, its test suite, the verified coverage partition, and the final
green validation state.

> **Superseded (2026-09-21):** the coverage partition (18 covered / 32 matched / 44 UNCOVERED),
> template count (18), test count (40) and core-suite number (611) below were expanded by B2b
> round 2 — see `KNOWLEDGE/2026-09-21/01-b2b-round2-expansion.md` (36 templates / 38 covered /
> 52 matched / 24 UNCOVERED / 73 tests / core 899). The "What was built" line counts and the
> round-1 TID list are historical record only.

## What was built
- `MTG_bot/core/compiler/templates_b2b.py` (≈1,160 lines):
  - `_BUCKET = "B2b"`, `_PRIORITY = 50`.
  - `TEMPLATES` contains **18** templates.
  - `UNCOVERED` contains **44** `(exact_normalized_shape_key, reason)` tuples.
  - Helper builders and concrete-sentence `re.fullmatch` patterns follow the B2a layout.
- `MTG_bot/core/compiler/test_templates_b2b.py` (≈973 lines):
  - `TestB2bCoverage` — 12 tests.
  - `TestB2bTriggerEvents` — 10 tests.
  - `TestB2bEffectStructure` — 18 tests.
  - Total: **40 tests**.

## Verified B2b bucket partition
Source: `/tmp/opencode/phase1_buckets/B2b.json`

| Quantity | Value |
|---|---:|
| normalized shape keys | 62 |
| concrete occurrences | 76 |
| covered shapes | 18 |
| matched concrete occurrences | 32 |
| uncovered shapes | 44 |
| unmatched concrete occurrences | 44 |
| `UNCOVERED` entries | 44 |

`UNCOVERED` keys were verified to be exactly the unmatched normalized shape set.

Covered-shape occurrence counts:
- `When this land enters, scry N.` — **5**
- `When this land enters, you gain N life.` — **11**
- all other 16 covered shapes — **1** each

## 18 covered TIDs
```text
B2b-alpine-houndmaster-etb
B2b-fierce-empath-etb
B2b-teferis-tutelage-etb
B2b-temple-etb-scry
B2b-temple-etb-gain-life
B2b-massacre-wurm
B2b-hooded-blightfang
B2b-malefic-scythe
B2b-wildwood-scorge
B2b-falconer-adept
B2b-library-larcenist
B2b-alpine-houndmaster-attack
B2b-bolt-hound
B2b-spined-megalodon
B2b-siege-striker
B2b-brash-taunter
B2b-sporeweb-weaver
B2b-basris-lieutenant
```

## Matching rules
- Templates must `re.fullmatch` the **concrete** oracle sentence, not the normalized shape key.
- Tests drive IR through `TemplateRegistry.match(<concrete sentence>)`; `template.build({})` is
  not a valid probe because builders read regex groups.
- PC-3 ambiguity is zero:
  - every covered concrete sentence matches exactly one template;
  - every uncovered concrete sentence matches zero templates.

## Key IR decisions
- ETB triggers use `ZoneChangeEvent(ANY → BATTLEFIELD YOU)`; the current grammar cannot
  restrict the ETB subject type to creature/land/enchantment.
- `you may` maps to `OptionalEffect`.
- `target` maps to `SelectorMode.TARGET`.
- `another` / `other` adds `FNot(inner=FAtom(IS_SOURCE))`.
- `X is the number of other attacking creatures` uses `QCount` over other attacking creatures.
- `REVEAL` after `SEARCH` cannot reference the searched cards in the current grammar, so reveal
  count is modeled unbounded where required.
- Token colors are dropped because `TokenSpec` has no color field.
- `B2b-falconer-adept` omits token tapped/attacking state because `TokenSpec` does not model it.
- `B2b-basris-lieutenant` simplifies “this creature or another creature you control dies” to any
  creature you control dying, with a `HAS_COUNTER` condition for the `+1/+1` counter text.
- Cast-event shapes remain uncovered because `CastSpellEvent` lacks the needed controller-scoped
  caster/source-zone/ordinal/color/type/noncreature distinctions.

## Verification
Commands run from `/home/sune/Desktop/MTG_AI` with the project venv active:

```bash
python -m pytest MTG_bot/core/compiler/test_templates_b2b.py -q
# 40 passed in 1.14s

python -m pytest MTG_bot/core -q
# 611 passed in 2.30s

pyright MTG_bot/core/compiler/test_templates_b2b.py MTG_bot/core/compiler/templates_b2b.py
# 0 errors, 0 warnings, 0 informations

ruff format MTG_bot/core/compiler/test_templates_b2b.py MTG_bot/core/compiler/templates_b2b.py
# 2 files left unchanged
```

`611` is `571` from the 2026-09-17 B2a session plus the new `40` B2b tests.

## Traps found
Recorded in `KNOWLEDGE/PITFALLS.md`:
1. `PtDelta` uses `magnitude`, not `amount`.
2. Repeated `Atom.args.get(...)` expressions are not reliably narrowed by pyright; bind the result
   to a local variable or typed helper.
3. `assertIs` on freshly constructed frozen dataclasses such as `DurationEot()` recurred in B2b;
   use `assertEqual`, while `assertIs` remains acceptable only for enum singletons.
