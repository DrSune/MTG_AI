# 19 — Owner extension (design note, 2026-10-06 14:08): abstention must come WITH a reason

Owner: "for the abstention training/idea — it should also explain why it abstains. Really
cool extension." Interpretation used here (correct me if you meant something else): the
policy's PASS decisions (response windows, optional-trigger decisions) become a learned,
EXPLAINED act, not a fallback. Where this already exists: WINDOW_PASS journal rows (R17-1,
live since Rung-1/2), the pass-floor Elo anchor (+34 — currently our strongest player),
and every null-vs-gold corpus item (null = universal abstainer).

## Design (simplest inspectable form; engine untouched)
1. **ABSTAIN is already a legal candidate** at window/optional asks — no engine change.
   Training target extends: action in candidates U {ABSTAIN}; batch-3 DAgger states already
   carry the real choice (null-vs-gold is exactly expert-abstains-when... data).
2. **Explanations are GROUNDED REASON CODES, not prose** (closed vocab, engine-checkable):
   NO_COST_WINDOW (can't pay any instant right now) / NO_TARGET_WORTH / HOLD_VALUE
   (counter better kept for named threat seen in obs) / INFO_INCOMPLETE (hidden info decides)
   / RULES_UNCERTAIN (phase-2: model flags its own gaps) / COST_GT_BENEFIT.
   Prose rendering = static template per code -> human-readable in replays/viewer.
3. **The killer feature: reason correctness is TESTABLE.** Each code has engine facts that
   make it admissible at that state (e.g. NO_COST_WINDOW requires zero payable instants in
   the recorded observation). A replay checker asserts cited facts -> a hallucinated reason
   fails automatically. This is the falsifiable-twin law applied to explanation, and it is
   the reward-hacking gate: abstaining is easy to fake (pass-floor!), a WRONG reason on a
   RIGHT abstention is still a fail. Elo alone cannot see this; the reason lane can.
4. **Loss/eval:** joint CE over (action, reason) pairs, reason supervised only on abstain
   rows (masked); report action-acc, reason-acc, and the composition (right-action-WRONG-
   reason = the interesting failure class, tracked separately).
5. **Why this is genuinely valuable here**: window play is the E1 residual (games show the
   gap at windows), a reason head forces the model to carry the causal variable for passing,
   and RULES_UNCERTAIN gives a training signal for where the card-semantics are missing
   (feeds the teacher/mining backlog). Later: free-text + cited-fact checking, same law.

## Queue position
Batch 3 (capacity A/B + DAgger) pre-registered, unchanged — it runs FIRST and its rollout
logs already record every abstain (WINDOW_PASS) with states. The reason vocab is a v3
schema tag on the collector -> batch 4. No engine/compiler touches; design-only until then.
