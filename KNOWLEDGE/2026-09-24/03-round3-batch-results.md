# 2026-09-24 · 03 — Grammar round 3 + template batch: results and state

Status: DONE this session. Both delegations verified by the orchestrator
(own-suite reruns, golden audits, live PC re-measurement).

## What landed

### Grammar round 3 (ability_tree.py, additive-only) — see 02 for the binding spec
Six items, all omit-if-None/empty so every pre-round-3 tree serializes
byte-identically:
1. `StaticAbility.condition: Filter | None = None`
2. `ActivatedAbility.condition: Filter | None = None`
3. `Verb.COUNTER_SPELL` optional role `unless: Cost`
4. `FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN` (slots {who})
5. `CostModifier.extra_deltas: tuple[CostDelta, ...] = ()`
6. `FAtomPred.TARGETS_SOURCE` (slots {})

Verification (orchestrator-repeated): core suite 1086 → **1116** (+30
`test_ability_tree_r4.py`); golden refresh → **0 of 305 worktree-modified**
(byte-stable); PC-4 0 diffs; PC-9 stable.

### Template batch (8 templates + activation-gate mechanism)
- `templates.py`: `ActivationGateOutcome(condition: Filter)` in the
  `SentenceOutcome` union.
- `compiler.py`: post-assembly gate attach — each gate (sentence order)
  binds to the LATEST preceding `ActivatedAbility` without a condition, via
  `dataclasses.replace`; orphan gate ⇒ `StateCorruptionError` (orphan
  additional-cost precedent); continuation-merge ActivatedAbility rebuild
  now carries `condition=ab.condition`.
- `templates_b4.py` (30 templates / 17 UNCOVERED): Stormwing Entity
  (compound `{2}{U}` reduction via `extra_deltas` + R3-4 condition),
  Terror of the Peaks / Pursued Whale (`TARGETS_SOURCE` +
  `IncreaseLife`/`IncreaseGeneric`, `controller_ref=OPPONENT`).
- `templates_b5a.py` (45 templates / 18 UNCOVERED): Gnarled Sage
  (conditional static; pattern generalized to `\+(\d+)/\+(\d+)`), Caged
  Zombie + Celestial Enforcer (activation gates), Miscast + Lofty Denial
  (`unless` Cost role on COUNTER_SPELL).

## Headline numbers (post-batch, `python tools/measure_grammar.py --set M21`)

| Metric | Pre-batch | Post-batch | Δ |
|---|---|---|---|
| PC-1 card_coverage | 0.6689 (204/305) | **0.6885 (210/305)** | +6 cards |
| PC-2 sentence_coverage | 0.7887 (504/639) | **0.8013 (512/639)** | +8 sentences |
| PC-3 ambiguity | 0 | 0 | — |
| PC-4 golden_stability | 0 diffs | 0 diffs (305 verified) | — |
| PC-6 orphans | 2 | 2 | PHASE_IN + FLIP_COIN — **both ratified by owner 2026-09-24** (see 04-owner-decisions.md); FLIP_COIN consumed when the B5c "{T}, Pay N life: Flip a coin." shape is templated |
| PC-8 targetable | 0.2689 (82/305) | **0.2754 (84/305)** | +2 (counter-unless selectors) |
| core suite | 1116 | **1128** | +12 tests |

Fully-parsed new cards: Miscast, Caged Zombie, Celestial Enforcer, Gnarled
Sage, Stormwing Entity, Terror of the Peaks. Partially covered: Pursued
Whale (residual: token-with-text ETB sentence), Lofty Denial (residual:
"If you control a creature with flying, counter that spell unless its
controller pays {4} instead." — anaphora + "instead"; per-card
translation candidate).

## Goldens
Exactly 8 files re-baselined (the 8 cards), staged; structural audit
(abilities key the only changed top-level key in each) performed by the
coder **before** re-staging. Caveat: the coder's re-staging overwrote the
pre-batch index blobs (`git fsck --dangling` found none), so the audit is
not independently re-runnable — recorded as a process lesson: future
re-baseline audits must capture the pre-state copy (e.g. in /tmp) before
`git add`ing the refreshed goldens.

## Residual queue post-batch
**125 shapes / 127 occurrences** (was 133/135). Dump:
`/tmp/opencode/unparsed_queue_post_r3.txt`. The probe is now a standing
tool: `python tools/dump_unparsed_queue.py [--set M21] [--card NAME]
[--out FILE]` — the per-batch work register (supersedes the ad-hoc
`/tmp/opencode/probe_unparsed.py`).

## Round-4 design queue (from 02, still open — the next big lever)
Ranked by residual-occurrence share:
1. Conditional triggers (B2b, ~18 shapes): trigger events need
   cast-from-zone scoping, first/second-this-turn ordinals,
   damage-source attributes, "when you do" anaphora.
2. Replacement/"instead" effects (~10 shapes in B5b).
3. Anaphoric continuations ("It gains …", "That player discards that
   card.", "You choose … from it.") — needs the anaphora convention
   decision.
4. Emblem-with-text loyalty sentences (4 shapes) — recursive emblem
   compilation.
5. Sorcery-mode activation restriction, "During your turn" time-scope
   condition, graveyard/library-top count predicates (the remaining
   "As long as" shapes).
6. ~20 singletons (coin-flip B5c shape, half-counts, per-color counts,
   "must be blocked", "can block only X", restricted mana, gain-control,
   double-counter, until-reveal searches…).

## Process items (owner decisions 2026-09-24 — see 04-owner-decisions.md)
- Commit the working tree: APPROVED (executed at session end).
- PC-6: PHASE_IN + FLIP_COIN orphans RATIFIED as documented.
- Next session: round-4 grammar — conditional triggers (largest residual
  family, ~18 B2b shapes).
- Still open: JOURNAL tooling status decision (open since 2026-09-23).
