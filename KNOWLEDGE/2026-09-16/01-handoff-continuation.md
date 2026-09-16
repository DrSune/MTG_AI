# 2026-09-16 · 01 — Handoff: Phase 1 (ability-tree grammar) continuation

**Status at stop: 510/510 core tests green (verified firsthand, `pytest MTG_bot/core -q`),
5 of 7 template buckets landed, foundation complete. Repo committed at stop.**

## 1. What exists (all in `MTG_bot/core/`)

| Module | What it is | State |
|---|---|---|
| `ability_tree.py` (~2055 lines) | THE grammar: 56 node types; 35 verbs; 26 predicates; 13 events; frozen, validated, canonical JSON + sha256 fingerprint; `walk()` | DONE + 3 review fixes (ZoneKind.PLAYER, ControllerRef.TARGET_PLAYER, FAtom.count→Quantity, duration role on TAP/UNTAP/MANDATE_ATTACK) |
| `compiler/ingest.py` | MTGJSON v5 → `RawCard` (oracle-id-keyed, dedup identical printings, raise on conflict; depth-aware sentence split; emblems + `related_names`; `pool_stats`) | DONE (adversarial-reviewed, 2 criticals fixed) |
| `compiler/templates.py` | Template engine: `Template(tid,name,bucket,pattern,priority,build)`, `TemplateRegistry.match() -> ALL matches` (ambiguity visible, never hidden), 5 outcome types | DONE |
| `compiler/compiler.py` | Assembly: rule-reminder consumption → template match → `CardRecord`; continuation rule ('If you do'→OptionalEffect, documented simplification); keyword dedup (parametrized wins); mana-cost/P-T parsers; emblem attachment; `compile_card`/`compile_pool`; `UnparsedFragment` queue; `engine_supported` via optional `supported_verbs` param | DONE |
| `templates_b1.py` | bare keywords (15/15 covered; 3 are MetaOutcome enchant-target) | DONE, tested |
| `templates_b2a.py` | triggers half 1 (45 templates; 45/45 declared-covered shapes verified matching; 17 UNCOVERED machine-readable) | module DONE+verified; **TEST FILE MISSING** (subagent died before writing it) |
| `templates_b3.py` | activated (23 templates; 41/48; 7 UNCOVERED) | DONE, tested |
| `templates_b4.py` | statics (18 templates; 18/47; 29 UNCOVERED) | DONE, tested |
| `templates_b5a.py` | spell effects part 1 (34 templates; 38 covered + 23 pre-consumed reminders; 29 UNCOVERED — recorded in its TEST file's docstring, not yet a machine-readable tuple) | DONE, tested |
| `test_ability_tree.py`, `test_ingest.py`, `test_templates.py`, `test_compiler.py`, `test_templates_b{1,3,4,5a}.py` | 510 tests total, all green | — |

Pool facts (pinned in tests): M21.json = 397 card entries → **305 oracle cards**
(285 cards + 20 tokens after dedup; 112 identical reprints, 0 conflicts); 639 sentences,
510 unique, 504 unique shapes across 8 buckets; 3 emblems (all attached to owners);
34 keyword-reminder + 42 full-paren rule-reminder sentences are pre-consumed by the compiler.

Bucket work-inputs (exact shape → card pairs): `/tmp/opencode/phase1_buckets/*.json`
(B1, B2a, B2b, B3, B4, B5a, B5b, B5c). **These are in /tmp — re-generate if lost** using the
classifier in KNOWLEDGE/2026-09-14/02-phase1-plan.md's census (B5 = everything else; split
alphabetically into thirds; B2 split in half).

## 2. Remaining work (in order)

**T1. `test_templates_b2a.py`** (1 coder, small): the module exists and is verified
(45/45 match, 17 UNCOVERED) — write the test file per the bucket-coder spec (parametrized
over every shape in /tmp/opencode/phase1_buckets/B2a.json; round-trip stability; PC-3
ambiguity ≤1 distinct outcome; pyright-clean). Expectation: green.

**T2. Buckets B2b (62 shapes), B5b (90), B5c (90)** (3 coders, parallel, same spec as the
b3/b5a prompts — see git log for the b3/b5a commit messages which embed the conventions).
Each module: `TEMPLATES` tuple + `UNCOVERED: tuple[tuple[str,str]]` (machine-readable) +
parametrized tests. Conventions: tid prefix per bucket; `~` = this card; fullmatch; honest
UNCOVERED beats wrong guesses (model-poisoning risk — see §5).

**T3. Grammar-addition decision (orchestrator + analyst, before measurement):** one round of
additive grammar changes for the HIGH-FREQUENCY UNCOVERED families (list in §3). Rule:
generalized solution per shape-family (user 2026-09-16: "generalized solutions, learnable
preferred over hardcoded"); a new verb/predicate must be justified by ≥3 pool shapes or a
named cross-set mechanic; after additions, re-run affected bucket tests + full suite.
Candidate families ranked by (frequency in UNCOVERED register, cross-set importance):
1. MODIFY_COST static (6+ shapes; cost reduction/increase is universal across sets — highest yield)
2. power-only comparison predicates (POWER_LE/POWER_GE; 4+ shapes; PT_LE/PT_GE are combined)
3. TAP_ON_ETB / ETB-with-counters ("enters tapped", "enters with N counters")
4. CAST as effect verb (cast from graveyard/exile — 2 shapes here, ubiquitous in other sets)
5. per-opponent loop construct ('each opponent X' — 2 shapes, common)
6. name-contains predicate (2 shapes; vs exact NAME_EQ)
7. player-or-X zone unions (2 shapes)
8. turn-scoped quantities ('life gained this turn', 'put into hand this turn')
9. FIGHT as effect verb (1 shape in M21 but the keyword exists; other sets will need it)
Leave for per-card agent translation (§5): anaphora ('that many'), modal headers ('choose one —'),
cross-card activation (Teferi), dynamic protection-from-name, specific-card tutors, the truly
one-off weird ones.

**T4. Normalize B5a's UNCOVERED** into a machine-readable tuple (currently in the test
docstring) — 10-minute coder task, or fold into T2.

**T5. Measurement harness** (1 coder): `compiler/coverage.py` + `compiler/golden.py` +
`tools/measure_grammar.py` → `reports/grammar_<date>.json`. Must emit the PC-1..PC-10
numbers (pre-registered in 02-phase1-plan.md): card/sentence coverage vs 305/639, per-verb
histogram (PC-6: no orphans, no verb >20%), PC-3 ambiguity count (expect 0), PC-4 golden
stability, PC-5 compile p99, PC-7 executor coverage (after T6), PC-8 targetable fraction,
PC-9 determinism, PC-10 instrument null test (synthetic card). Golden files:
`MTG_bot/core/golden/M21/<oracle_id>.json` (canonical_json per card, committed).
Every run appends a dated row to KNOWLEDGE/NUMBERS.md.

**T6. Executor skeleton** (1 coder): `core/executor.py` — dispatch on node tag for the
core verbs against Phase-0 GameWorld (DEAL_DAMAGE, DRAW, GAIN/LOSE_LIFE, ADD_MANA,
TAP/UNTAP, PUT/REMOVE_COUNTER, MOVE_ZONE, CREATE_TOKEN, MODIFY/SET_PT, SACRIFICE,
DISCARD, EXILE, DESTROY, SEARCH, SHUFFLE, COUNTER_SPELL, MILL, SCRY...); `SUPPORTED_VERBS`
frozenset feeds `compile_pool(supported_verbs=...)` → `LegalityFlags.engine_supported`.
Cards with any unsupported node are flagged, never silently degraded (North Star).

**T7. Adversarial review + semantic spot-check** (1-2 agents): dump compiled trees for
~20 known cards (Black Lotus, Tarmogoyf, Maro, Grizzly Bears, Chandra's Firemaw, a
planeswalker + emblem, Brash Taunter, Caged Zombie, Bloodfell Caves, Alpine Houndmaster,
Capture Sphere, Angel token, Garruk's Gorehorn, ...); a human-meaning check: does the tree
say what the card does? This is the anti-poisoning gate BEFORE any training data is built.

**T8. Per-card translator protocol for the residual tail** (see §5).

**T9. Commit + final measurement pass + NUMBERS.md update.**

## 3. UNCOVERED register (as of stop)

Full dump: `/tmp/opencode/phase1_buckets/UNCOVERED_ALL.md` (B1: 0, B2a: 17, B3: 7, B4: 29,
B5a: 29 in test docstring, B2b/B5b/B5c: not yet built). Headline: ~62 shapes so far need
either a grammar addition (the families in T3) or per-card translation.

## 4. Operating lessons (measured, not vibes)

- **Subagent transport fails happen** (3× in this session: 2 empty results, 1 "Failed to
  execute statement") — ALWAYS verify on disk (ls + targeted probe) after any delegation
  that returns empty; the work may exist even when the result is empty (B2a case).
- **Model tiers on this vLLM pool**: 262k-xhigh (ultra) and 128k-medium (coder) work;
  128k-xhigh (analyst) is NOT available ("Model not found ...128k-xhigh"). Use ultra for
  the analyst's job.
- Memory: ~121 GB total, vLLM pool resident; 7-10 GB headroom observed; ran 2-3 coders
  concurrently safely. Keep ≥5 GB free.
- `TestCase.__init__` sets `self._outcome = None` — never name a test helper `_outcome`
  (shadowed the method in B5a; renamed to `_match_outcome`).
- Pyright: repo has `pyrightconfig.json` (venv .venv, py3.12); run
  `python -m pyright <files>` or `pyright --pythonpath .venv/bin/python`.
- AGENTS.md §6 (knowledge protocol) is now in the repo and binding for all agents.

## 5. Standing decision 2026-09-16 (owner, verbatim intent)

> Deterministic templates for the common case; when a card's text cannot be translated
> honestly by templates, spawn a **translator agent per card** (not per shape) + an
> **adversarial pass** on the result. Wrong functionality is "heavy model poisoning" —
> one wrong tree poisons training more than an explicit unparsed flag. Unless errors are
> very similar (visible from tests/try-except), do NOT batch cards into one agent:
> per-card, so functionality doesn't mix. The translator agent must know: set context,
> ruleset (the actual Magic rules for the relevant interactions), roles/classes of the
> entities involved, the exact grammar types it must target, and the `~` convention.
> Commander-weird cards (leadership skills, legendary commander rules) are the prime
> candidates for this path.

**Per-card translation protocol (design, ready to execute in T8):**
1. Input to translator: the card's full oracle text + M21 set context + the grammar's
   node-type catalog (dumped from ability_tree.py) + 2-3 exemplar compiled trees of
   similar cards (from the golden files) + explicit instruction: produce a CardRecord
   (as canonical JSON) OR declare specific unparsable fragments; NEVER approximate a
   semantic it cannot express; mark every assumption.
2. Validation: the output must (a) `from_dict` cleanly, (b) round-trip, (c) pass a
   `walk()` census (no unknown tags), (d) be diffed against the deterministic template
   result where one exists (any diff on a shared sentence is a red flag requiring review).
3. Adversarial pass: a second agent re-reads the oracle text and the produced tree and
   hunts for semantic mismatches (target vs source, controller vs any, duration, count
   semantics, zone, 'may' vs mandatory). Mismatch → fix loop, max 3 rounds, then the
   fragment goes to the explicit unparsed queue with the reason.
4. Every per-card-translation is recorded in KNOWLEDGE with the card's oracle id, the
   diff vs template, and the adversarial verdict — the poison can always be traced.

## 6. Context the next instance needs to read (in order)

1. `NORTH_STAR.md` (governing), `AGENTS.md` (§6 knowledge protocol, §3 budgets).
2. `KNOWLEDGE/INDEX.md` → this file → `NUMBERS.md` → `PITFALLS.md`.
3. `KNOWLEDGE/2026-09-14/02-phase1-plan.md` (PC-1..PC-10 targets — pre-registered; do not
   move goalposts without a dated entry).
4. The three design docs: `docs/DESIGN_CARD_POOL.md` (the spec), `docs/METRICS.md` §3/§13/§15
   (measurement rails), `docs/DECISIONS.md` (D2 et al — settled).
5. Code: `MTG_bot/core/ability_tree.py` (the type catalog), `MTG_bot/core/compiler/compiler.py`
   (assembly rules — read the docstrings: continuation rule, keyword dedup, reminder
   consumption, emblem attachment, engine_supported).

## 7. Commands (verified working)

```bash
cd /home/sune/Desktop/MTG_AI && source .venv/bin/activate
python -m pytest MTG_bot/core -q                 # 510 passed at stop
python -m pytest MTG_bot/core/compiler/test_templates_b3.py -q   # bucket example
python -m pyright MTG_bot/core/ability_tree.py   # 0 errors at stop
python -m MTG_bot.core.compiler.compiler         # (no CLI yet; harness is T5)
```
