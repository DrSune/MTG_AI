# 2026-09-23 · 02 — Additional-cost compiler hook (B5a prerequisite)

**Fact:** the compiler now collects `AdditionalCostOutcome.cost` values and
attaches them to every `SpellAbility.additional_costs` during card assembly —
the missing hook the b5a agent flagged (Option-B finding, 2026-09-22/01 §
"Consequences") as the prerequisite for the B5a additional-cost templates.
Implemented 2026-09-23; core suite 1015, 305 card goldens byte-stable,
pyright 0 errors, ruff no new findings. No git commit (working tree carries
uncommitted parallel-session work — see 01).

## Design decisions
- **Single post-assembly attach, not construction-site threading.**
  `SpellAbility` is `@dataclass(frozen=True)` (ability_tree.py ~1763), so the
  hook collects the outcomes after the meta-filter, then rewrites the ability
  list with `dataclasses.replace(ab, additional_costs=ab.additional_costs +
  collected)` — `replace` re-runs `__post_init__` validation. Chosen over
  threading a costs accumulator through every `SpellAbility(...)`
  construction branch: one place to test, zero behaviour change when no
  additional-cost sentence matches (the common case).
- **Orphan additional-cost = `StateCorruptionError`, not a known gap.**
  _Superseded for castable cards by 03 (2026-09-23 round 3): the raise now
  fires only for land/token/emblem; a castable card with no `SpellAbility`
  gets an effect-less carrier appended (`SpellAbility.effect` became
  `Effect | None`)._ If a sentence matched an additional-cost pattern but
  the card compiled without a `SpellAbility` (land, token, effect-less
  spell), the card can't be cast, so the oracle text/type line is corrupt.
  Error context carries `oracle_id` + `types`; the message carries
  `raw.type_line!r` (RawCard has both `type_line: str` and
  `types: tuple[str, ...]`).
- **Continuation merge preserves costs** — the rebuilt `SpellAbility` in the
  continuation path now carries `additional_costs=ab.additional_costs`.
  Future-proofing: no production template emits `SpellAbility` yet, but a
  template-carried cost + continuation sentence must not drop the cost.
- **Byte-stability is automatic**: `_OMIT_IF_EMPTY["SpellAbility"]` already
  omits empty `additional_costs` from `to_dict`/`canonical_json`, so no
  golden changes — verified by `test_golden.py`.
- **Zero coverage impact for now**: the hook is inert until B5a registers
  sentence patterns that emit `AdditionalCostOutcome`. PC-1/PC-2 stay at the
  last measured values (2026-09-22/04: PC-1 193/305, PC-2 493/639) until the
  B5a templates land.

## What changed (3 files)
- `compiler/templates.py`: `AdditionalCostOutcome(cost: Cost)` frozen
  dataclass; extended `SentenceOutcome` union.
- `compiler/compiler.py`: import; cost collection after the meta-filter
  block; orphan check + `replace`-based attach before the CardRecord build;
  continuation merge carries `additional_costs`.
- `compiler/test_compiler.py`: `TestAdditionalCost` (8 tests) + helpers
  `_hand_card_selector()`, `_additional_cost_discard()`,
  `_additional_cost_sacrifice()`, `_additional_cost_templates(reg)` — the two
  canonical B5a sentences ("As an additional cost to cast this spell, discard
  a card." / "…sacrifice a creature.") now have exact text mirrored in tests,
  ready to copy into `templates_b5a.py`.

## Verification (2026-09-23, repo .venv)
- `pytest MTG_bot/core/compiler/test_compiler.py -q` → **83 passed** (75 + 8 new)
- `pytest MTG_bot/core -q` → **1015 passed**
- `pytest MTG_bot/core/compiler/test_golden.py -q` → **6 passed** (305-card goldens byte-stable)
- `pyright` on the 3 files → 0 errors / 0 warnings; `ruff format` → unchanged;
  `ruff check` → 8 findings, all pre-existing (9 in the base tree — net −1;
  UP007 on the pre-existing `Union` at templates.py:104, TRY004 on the
  intentional `AssertionError` narrowing helpers)
- Per-file test counts (`pytest --collect-only`): b2a 79 / b2b 73 / b3 29 /
  b4 43 / b5a 64 / b5b 56 / b5c 67 / compiler 83.
- Δ 1015 vs 2026-09-22/04's 1004 = +11: my +8 confirmed; the remaining +3 =
  parallel-session test additions in the working tree (b4 42→43 vs the last
  recorded count; b3/b5a text-only changes) — per-file reconciliation
  incomplete, flagged below.

## Follow-ups
1. Register `ac-discard` / `ac-sacrifice` patterns in `templates_b5a.py`
   (known-gap notes at lines ~1247–1252) — the first real coverage gain from
   this hook; the remaining B5a additional-cost queue entries follow per the
   b5a gap list (4 queue entries total per 01).
2. Per-file test-count reconciliation of the +3 residual (needs a full
   `--collect-only` snapshot vs the committed baseline).
3. JOURNAL tooling status decision (owner, per 01's standing rule) — out of
   scope for this session.
