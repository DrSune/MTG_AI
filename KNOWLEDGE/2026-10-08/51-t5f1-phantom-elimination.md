# 51 — T5-F1: phantom ask class eliminated (charter §10 phase F1)

Date: 2026-10-08. State: COMPLETE (uncommitted at time of writing).

## What was built
- `MTG_bot/core/executor/offers.py` — `offer_or_autopick(ctx, vocab, what)`:
  the single shared gate implementing stack.py:442's rule in the decision
  channel. One-word surface → consume silently + journal, NEVER present;
  zero-word → explicit ValueError (producer-contract violation); else the
  ordinary `take_decision` lane. Structural `DecisionSite` protocol.
- `DecisionStream.journal` (decisions.py): ordered log of EVERY resolved
  demand — asked or auto-picked. `ask_log` stays the PUBLIC lane (only
  genuine asks; BC/rollout recorders consume it — a phantom row there
  was the bug). `ExecCtx.take_decision` pool lane appends both.
- MAY_DONE (quantity.py) reads the journal first, prefix-matching
  `may:<source>` (ask_log fallback kept for the patched-lane tools that
  append ask_log only — puzzle_cert, dagger_rollout_v3).
- May site tag gained the per-offer digest: `may:<source>:<site_digest(effect)>`
  — two may-offers on one source are two keys; value-based digest is
  deterministic (no set fields on ability_tree dataclasses, verified).

## Adoption sites (the §10 audit named 3; a full-corpus census found 5 phantoms)
`__init__.py`: choose lane (bounds-clamped menu), may lane, attack lane
(mandated attacker = one-word surface), block lane (must-block/menace
narrowing to one pair), order lane (trivial last slot). Target/one_of
lanes already carry the §1.4 auto-fill (never 1-candidate); trample vocab
is always ≥2 words — audited, unchanged.

## Census (KNOWLEDGE charter §10 acceptance evidence)
`/tmp/opencode/phantom_census.py` wraps `DecisionStream.take` (the only
public ask funnel) and sweeps every scenario pack:
- PRE-F1: `1-candidate asks presented = 5` (attack×3, order×1, block×1),
  autopicks = 0.
- POST-F1 (2026-10-08): **packs=386 green=386 | 1-candidate=0 |
  multi=315 | silent autopicks=5** — each former phantom site now
  consumes silently. The choose/may clamps fixed earlier produce 0 picks
  IN THIS CORPUS (no pack exercises them; they remain pinned by
  test_executor_phantoms.py instead).

## Re-anchored pins (dated, all with in-code T5-F1 comments)
- test_executor_games: narrowing autopicks (no ask, journalled);
  seed-73 stall-corpus game 56 → 50 turns (forced attackers no longer
  bill the policy RNG; same loser, still decisive).
- test_executor_stack: unpayable-pay autopicks skip and PARKS the
  scripted supply word; land-cast waiver auto-skips (bare-CAST loud
  layer unchanged).
- test_executor_binding: may pushes carry the digest tag.
- test_executor_blockers/_combat: `forced_attack`/`forced_block` probes
  (no ask + journalled word) replace narrowed-vocab ask pins; combat
  harness provider prefix-matches site tags (run_scenarios convention).
- packs combat_mandate_furor / stalker_must_be_blocked: narrowed-vocab
  ask pins → `not_asked`/`not_asked_to_block` lanes (outcome pins kept).

## Gate numbers (commands in headings)
- `.venv/bin/python -m pytest MTG_bot/core -q` → 2502 passed +2 subtests,
  0 failed (baseline 2491 + 11 new test_executor_phantoms.py).
- `.venv/bin/python tools/run_scenarios.py` → 386/386.
- `.venv/bin/python -m pytest tools/audit tools/training -q` → 154 passed.
- Ruff: zero new findings (7 pre-existing before and after on touched files).
- BC snapshot `tools/training/episodes_v2.jsonl`: 214 ask rows,
  0 single-candidate (regenerations from here cannot mint phantoms).
