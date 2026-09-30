# 2026-09-30 · 11 — Round 16 BINDING (arc 3: combat) — owner-correctness lens is the law

Basis: analyst spec (ses_f0ed0825dffeUCRQhNTvCwh6Wh) MEASURED at 50f2299 + owner directives
(09:14): all cards+atomic abilities must be RIGHT and VALIDATED (compounding-backlog risk);
visual inspection via round-15 viewer; per-card / interaction-by-interaction verification.
All frozen rulings (06 §1-2 + goldens-only-via-audits) continue. PC-1/2/3/4 EXACT invariant.

## Orchestrator rulings
R16-1 **Response window = option (iii)** — combat v1 runs uninterrupted; NO opponent ask-site
(our instants are own-turn-only by construction, so nothing illegal is claimed); mandatory
honesty = SBA passes between damage step -> END_OF_COMBAT -> next step + documented "no chain
spells / no flash responses" limit. Full CR 117 priority (i) / (ii)-lite cast-time responses
DEFERRED (buys only the 5 counter cards + opponent-turn instants; will be additive
DecisionStream vocab later, proven by trace-diff pins). Counter family stays loudly flagged.
R16-2 **D6 trace-diff catalog is MANDATORY in 16a** (before 16b touches shared verbs):
`tools/traces/catalog.json` = pinned per-seed journal fingerprints (10 engine seeds, cap 60) +
diff tool printing FIRST-DIVERGENCE entry + cards involved. Every shared-verb change must ship
with a catalog reconciliation (explicit re-pin + reason) — this is the owner's compounding-risk
answer: any atomic-semantics move surfaces, located, before it compounds.
R16-3 **Validation packs = definition of done per phase**: `tools/scenarios/<Card>.json`
(setup script + DecisionStream vocab-primed answers + journal/state assertions), authored per
NEW-combat card from PRINTED text (analyst's 25 attacker-trigger + 9 blocker + keyword + phase
cards = first wave). Round 17 (next, unbnd here) = full-corpus campaign: packs for all
engine-supported cards, owner-inspected via viewer replays.

## Phases (each = one bounded delegation; analyst projections)
- **16a (coder)**: marked-damage accumulation (fixes instant-lethal simplification:
  verbs.py:271-274 -> SBA-style lethal check at step boundaries via ledger-aware effective_pt)
  + SBA sweep + FIGHT handler (CR 701.12b/d, non-combat) + R16-2 catalog + pack schema v1.
  Flags 18->16; MUST show catalog-diff study of the 31 DEAL_DAMAGE cards (risk-2 gate); all-pool
  0 crashes (Brash Taunter plays); 2022+M green.
- **16b (ultra)**: COMBAT/SECOND_MAIN skeleton, declare-attackers per-creature binary asks +
  whole-set legality (CR 508.1, MANDATE_ATTACK enforced there; summoning sickness CR 302.6 +
  HASTE; defender; vigilance; IS_ATTACKING pred), attacker+CombatDamage emitters, FS/DS split
  (CR 702.7/8 via existing replacement site), binder un-raise SAME COMMIT (risk-1), TurnPhase
  COMBAT marker (5 phase cards fire). 25 bind-bombs->live; flags->12/13; survival >=96.7%;
  catalog re-pinned with reasons; combat packs for the 25.
- **16c (ultra)**: blockers (CR 509: per-blocker ask, at-most-one, reachability+restrictions ->
  DeclareBlockersEvent.blocked consumers Subira/Tome Anima/Ghostly Pilferer/Shacklegeist,
  Snarespinner subject), damage-order asks (CR 510.1), TRAMPLE assignment, Herald
  DAMAGE_ASSIGN_POLICY consumer, BecomesBlockedEvent (Gloom Sower), Mangara attacked filter.
- **16e (coder)**: GAIN_CONTROL executor-side control-overlay map (R16-4: additive-hook ruling
  DENIED for state.py — overlay lives executor-side, consulted at executor call sites; the 2
  cards + Traitorous Greed), ATTACH/equip onto existing attachments table, Repeat node, tail.
  Flags -> ~6 honest (PHASE_OUT 2, COPY 2, COUNTER 5-deferred, remaining policies).
(16d counter/response = deferred by R16-1.)

## Survival expectation
Games finally END by combat, not draw-cap; engine-pool coverage-fired lifts meaningfully
(25 attacker-trigger cards + keyword semantics join). Honest wall after 16e: PHASE_OUT/COPY
(deep semantics, 4 cards) + counter family (5, response-window-gated) — everything else LIVE
and pack-validated.

## Viewer loop (owner-facing)
Per-phase deliverable includes: 2-3 showcase replays (make_replay seeds chosen for new combat
action) reported to the owner for visual audit; findings become ledger rows (P0/P1 conventions
as round 14).
