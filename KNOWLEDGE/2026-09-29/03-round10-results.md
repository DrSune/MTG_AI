# 2026-09-29 · Round-10 results (grammar close-out, 4/4 rows)

Binding spec: `02-grammar-round10-decision.md`. Outcome: **all 4 rows landed;
grammar round-10 DONE; residual unparsed queue = the 5 permanent-defer shapes
exactly; no COMMIT (staging left for orchestrator).**

## Phase 10-A — grammar additions (all landed, `test_ability_tree_r11.py` 83 green)

| Item | IR change | Notes |
|---|---|---|
| R10-1 | `ActivationGateOutcome` gains `window` + `condition`; compiler C25 slot-disjoint attach (compiler.py ~L1284-1318) | gate sentence attaches `timing=SORCERY` to sibling triggered/activated ability; lossy Speaker path NOT upgraded (below) |
| R10-2 | `NAME_PARTITION_COUNT_GE` predicate | Chrome Replicator etb same-name-token |
| R10-3 | `DeclareAttackersEvent.attacked` + `ATTACK_AGAINST_COUNT_GE` | `attacked` = filter over attackers; Mangara draws when ≥2 attackers vs you-or-your-planeswalkers |
| R10-4 | `Verb.DAMAGE_ASSIGN_POLICY` + `_DAMAGE_ASSIGN_SCOPES` ("AS_UNBLOCKED") | Garruk, Savage Herald loyalty −7 GRANT_ABILITY(StaticAbility+OptionalEffect, DurationEot) |

**MID GATE (phase A):** `pytest MTG_bot/core -q` 1712 passed · PC-1 297/305 · PC-4 0.

## Phase 10-B — batch rows (ledger, C16 notes inline)

| # | Row | Template | Tests | C16 note |
|---|---|---|---|---|
| 1 | Liliana's Steward (b5a) | `B5a-activate-sorcery-gate` (UNCOVERED withdrawn) | b5a 89 green, incl. `test_steward_e2e_cross_bucket_attach` | R10-1 gate; window=SORCERY attached to sibling activated ability |
| 2 | Chrome Replicator (b2a) | `B2a-etb-same-name-token` (UNCOVERED pruned) | b2a 89 green | R10-2 `NAME_PARTITION_COUNT_GE(2)` as etb condition |
| 3 | Mangara, the Diplomat (b2b) | declare-attackers attacker-count draw | b2b 118 green | R10-3; occurrence count in bucket = 1; `attacked` = FOr(CONTROLLER_IS YOU, Planeswalker∧YOU) |
| 4 | Garruk, Savage Herald (b5c) | `B5c-loyalty-assign-as-unblocked` (UNCOVERED → 1 row, phase-in only) | b5c 77 green | R10-4; pattern anchored on `[±N]` loyalty cost, ASCII apostrophe in corpus sentence |

Counts after batch: b2b registry **60 templates / 61 covered shapes / 75 matched
occurrences / 1 UNCOVERED row** · b5c registry **87 templates (51 activated) / 90
covered / 1 UNCOVERED**. `tools/gen_buckets.py` b2a pattern-keys pin 60→61; script
runs clean; **all 8 bucket JSONs byte-identical** to pre-round-10 snapshot
(`cmp`, `/tmp/buckets_pre_r10_2026-09-29`).

## Gates (final, post golden-refresh; `python tools/measure_grammar.py --set M21`)

PC-1 **0.9869 (301/305)** PASS · PC-2 **0.9922 (634/639)** PASS (predicted 635 —
1 occurrence more consumed than forecast, no action) · PC-3 **0** PASS ·
PC-4 **0 diffs** (305 files) PASS — pre-refresh diff was **exactly the 4 landed
goldens** (`cbcb6d9a…` Mangara, `cc1203cb…` Steward, `f379fa0b…` Chrome,
`fc762e40…` Herald), changed-key set `["abilities"]` ⊆ {abilities, keywords} ·
PC-5 0.239 ms PASS · PC-6 orphans **1** (`PHASE_IN`) — standing FAIL ·
PC-7 deferred · PC-8 **0.3213** — pre-existing FAIL (executor-era) · PC-9 stable ·
PC-10 100%/0% PASS. Unparsed queue **9 → 5**, and the 5 are **exactly** the
permanent-defer table: Transmogrify ×2, Sanctum of All, Liliana Waker-of-the-Dead
action-history, Conspicuous Snoop introspection. `DAMAGE_ASSIGN_POLICY` orphan
consumed ✓. Suite: **1717 passed** · pyright 0 errors on all touched files ·
ruff check delta 0 vs HEAD · ruff format clean.

## Corrections & deviations

- **False deviation retracted**: round-9 notes claimed Seasoned Hallowblade
  carried an "Activate only as a sorcery." tail that would make PC-1 land at 300.
  The actual M21 oracle text in the corpus has **no such tail**
  (`Discard a card: …indestructible… (Damage … don't destroy it.)`). PC-1 landed
  at **301 — exactly the binding prediction**. The b5a probe that asserted the
  phantom shape was renamed to `test_sorcery_gate_attach_probe` on a synthetic
  card. Trap recorded in PITFALLS.md.
- **Speaker NOT upgraded** (decision, not oversight): binding scope = 4 rows;
  `_build_speaker_activation_gate` keeps its LOSSY note. Follow-up: apply the
  now-general R10-1 `window` mechanism to Speaker (would make its timing
  lossless; costs a b5b pin update).

## Standing items for next round

1. Speaker → R10-1 gate mechanism (lossless upgrade, b5b pins).
2. PC-6 `PHASE_IN` orphan (only vocabulary orphan remaining).
3. PC-8 targetable_fraction 0.3213 — rises with executor-era semantics.
4. Permanent-defer 5 sentences = Phase-2 executor's first consumers.
