# 2026-09-14 · 02 — Phase 1 plan: ability-tree grammar

## Deliverables (all in `MTG_bot/core/` unless noted)

1. **`ability_tree.py`** — the typed grammar: frozen dataclasses for CardRecord, Ability
   (Static/Triggered/Activated/Spell/Keyword/Replacement), Effect (Seq/Choose/Optional/
   Conditional/Repeat/Atom), Verb, Selector, Filter, Quantity, Duration, EventSpec, Counter,
   nested TokenRecord. Canonical serialization (`to_dict`/`from_dict`, stable-key
   `canonical_json()`, `fingerprint()`). No English anywhere in the tree — structured only.
2. **`compiler/ingest.py`** — MTGJSON v5 structured ingest → `CardIdentity` + structured raw
   record (types/subtypes/supertypes, colors, manaValue, mana_cost as token list, P/T, loyalty,
   keywords, text → sentence list, tokens as nested records). Keyed on scryfallOracleId.
3. **`compiler/templates.py` + `compiler/compiler.py`** — curated template set (oracle sentence →
   tree fragment) + deterministic compilation to a full CardRecord. Unmatched sentences go to an
   explicit unparsed queue (never dropped silently). Template IDs are stable and recorded in
   the output so ambiguity is detectable.
4. **`compiler/golden.py` + `compiler/coverage.py`** — golden files per card (committed under
   `MTG_bot/core/golden/M21/`); coverage instrumentation (per-verb/per-filter counts,
   enabled fraction, unparsed queue).
5. **`executor.py`** — tree → GameWorld operations for the core verbs (damage, draw, life,
   mana, tap/untap, counters, zone moves, token creation, P/T modifiers). Every node type
   without an executor is `engine_supported=False` on the card (LegalityFlags already exists
   from Phase 0). No silent degradation (NORTH_STAR / DESIGN_CARD_POOL commitment).
6. **`tools/measure_grammar.py`** — the Phase 1 measurement harness → `reports/grammar_*.json`
   + headline rows for KNOWLEDGE/NUMBERS.md.

## Pre-registered measurement targets (PC = Phase-1 Coverage)

Pre-registered BEFORE implementation per METRICS.md rail 1.6 (pre-registration) so we cannot
post-hoc pick convenient denominators.

| ID | Metric | Definition | Target | Stretch |
|---|---|---|---|---|
| PC-1 | card_coverage | cards+tokens with zero unparsed fragments / total pool (417) | ≥ 0.90 | ≥ 0.95 |
| PC-2 | sentence_coverage | fully-matched oracle sentences / 952 | ≥ 0.95 | ≥ 0.98 |
| PC-3 | ambiguity | cards whose text matches ≥2 distinct template sets producing different trees | 0 | 0 |
| PC-4 | golden_stability | tree fingerprint diffs across a recompile of the same input | 0 | 0 |
| PC-5 | compile_latency | p99 ms per card, offline | < 50 | < 20 |
| PC-6 | vocabulary_health | (a) verbs with 0 uses in pool = 0 orphans; (b) max single-verb share of all Atom nodes | orphans 0; max share < 0.20 | — |
| PC-7 | executor_coverage | (a) all top-25 frequent verbs have executors; (b) cards fully executable (every node) | 25/25; ≥ 0.70 | ≥ 0.85 |
| PC-8 | targetable_card_fraction (EC-7) | cards with ≥1 TARGET-mode selector / pool — the legacy number was 7/397; the tree must restore the true value | report true value; structural sanity: ≥ 0.40 | ≥ 0.50 |
| PC-9 | determinism | 2 independent compilations of the pool → identical multiset of fingerprints | exact | exact |
| PC-10 | instrument_null_test | harness run on synthetic cards: one fully-parseable, one with a planted unknown fragment | harness reports 100%/0% respectively, unparsed queue exact | — |

Plus, standing (not phase-gated): **semantic spot-check** — compiled trees for ~20 known cards
(Black Lotus, Tarmogoyf, Maro, Grizzly Bears, a planeswalker, a token-creator, an anthem, an
ETB trigger, an X-cost spell, a replacement effect) read by a human/adversarial agent must
match real Magic meaning. This is the anti-"gaming the system" check: coverage without
correctness is decoration.

## Sequencing

A. `ability_tree.py` types + tests ‖ B. `compiler/ingest.py` + tests (independent, parallel)
C. templates.py + compiler.py (needs A+B)
D. coverage.py + golden.py + tools/measure_grammar.py (needs C)
E. executor.py (needs A; can start after C for measurement)
F. full measurement pass → iterate C (template set) until PC targets met → record numbers
G. adversarial review of types/serialization + semantic spot-check → fixes
H. analyst review vs NORTH_STAR/DECISIONS → alignment fixes

## Non-goals (this phase)

- Tree → vector encoder (DESIGN_CARD_POOL Step 2 — Phase 3, needs the model)
- Action token grammar (DESIGN_ACTION_SPACE.md — later phase)
- Stack/priority (Phase 2 engine work; the grammar must REPRESENT it, not execute it)
- New sets beyond M21 (the pool is M21 + its 20 tokens; the harness must be pool-agnostic)
