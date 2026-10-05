# 14 — Pending: eval-granularity batch (memory-gated, 2026-10-05)

**Status**: NOT RUN. Two dispatch attempts died at the gateway circuit-breaker (usable RAM
1.6–1.7 GB → 0.85 GiB avail while engine serves ~239K-token session). Nothing lost; spec below
is the exact mission. **Relaunch when `free` avail ≥ 3 GiB and run ONE agent at a time**
(the memory-gate law, appended to /12 protocol).

## Mission (verbatim spec)
Owner charge: "if we have 10 total, we have 10% granularity" — we have **4** l1_certified
puzzles; the eval set must make small REAL improvements visible and memorization unable to
masquerade as skill.

1. Repair the 52 cert offenders (`tools/audit/puzzle_corpus.json`):
   - ~40 `null-pick-equals-gold`: re-script packs so gold is the ACTIVE correct play; the
     pack must FAIL under null policy (that is the point). If the card's printed promise has
     genuinely no active choice → reclassify honestly WITH reason (not a fake repair).
   - ~12 `expect-insensitive`: add falsifiable lanes (gold call must change an observable
     lane — zone/life/pt/counters/tapped; Fabled-Passage law).
   - Every repaired pack stays GREEN — strengthening EVAL, not changing verdicts.
2. Re-run `puzzle_cert` → `puzzle_corpus.json` v2 + `tools/audit/eval_split.json`:
   FAMILY-WISE train/eval split (same-card items can't leak into eval).
3. Granularity math printed (NUMBERS law): with E discriminating items (random-score in
   [.02,.9]) at accuracy p, corpus-mean SE ≈ sqrt(p(1−p)/E); report detectable-at-3SE effect
   size BEFORE (E=4) and AFTER. Target E_active ≥ 40 — report actual honestly.

## Gates
run_scenarios ALL green (355 names preserved) · pytest core 2391+2 unchanged · tools/audit
green (cert-v2 pins) · no engine/catalog touches · deliverable
KNOWLEDGE/2026-10-05/15-eval-granularity.md + eval_split.json.
Return: l1_ready before→after, E_active before→after, 3SE detectable effect before→after,
honest-reclass count, gate lines. (<300 words)

## Context this batch plugs into
batch-1 null (10-batch1-bc-floor.md): holdout BELOW floor = observation-schema gaps + tiny
eval set. A/B Elo harness (07d948a) is the CONSUMER: ELO movement needs E_active ≥ 40 to see
skill before it sees noise. Curriculum (09 §2) needs the split file to keep the 0kg/1000kg
band honest.

## Backlog add-ons from owner (2026-10-05 21:36 message, unnumbered → folded here)
- B5: **gradient-significance gating** — skip/backprop-selectively on over-confident or
  insignificant updates (catastrophic-forgetting brake); owner caveat noted: may starve
  nuance early → pilot as A/B against plain updates, never as silent default.
- B6: **when-does-winrate-rise curve**: ab_duel.py already accepts checkpoint lists vs one
  frozen reference — run per-batch during batch-2/3 training; degradation-vs-frozen is the
  forgetting tripwire the owner named.
</content>
