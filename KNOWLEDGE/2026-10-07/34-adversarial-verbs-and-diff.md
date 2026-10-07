# 34 — Adversarial: verb ontology + fresh-eyes on k-of-n commit (2026-10-07; owner-requested)

## D1 verb-ontology findings (reviewer, card-backed)
1. Verb enum fuses THREE ontologies: effects (DEAL_DAMAGE), policies (MANA_POLICY,
   DAMAGE_ASSIGN_POLICY, GRANT_*), OPERATIONS (CHOOSE, CHOOSE_NAME, FIGHT) in one flat enum —
   §9 violation inside the tokenizer core: operations must be reusable with any menu/effect.
2. **Zone-verb quartet**: MILL / DISCARD / EXILE = MOVE_ZONE with endpoints baked into the
   NAME — one structure, four symbols (the model must learn 4 unrelated tokens for one
   {move x from A to B} concept). SCRY legitimately distinct (reorder). Biggest tokenizer
   finding for future sets (phasing, play-from-exile etc. will pile more endpoints in).
3. PT triad SET_PT/MODIFY_PT/PUT_COUNTER = MTG layers 4b/4c — CORRECTLY separate (KEEP),
   but timestamp/dependency field absent -> "becomes 3/3 then +1/+1" order may be
   indistinguishable (SMELL, unproven — needs targeted test).
4. Stale compiler gap comments (compiler.py:118 etc.) UNDERSTATE the grammar (10 Quantity
   shapes + full FAnd/FOr/FNot algebra exist) — dangerous for §8 per-set reviews.
5. Verified approximations: "Choose one or more" (Sublime Epiphany) QUnbounded unwired;
   "attacks or blocks" (Elder Gargaroth) compiled as TWO atoms = phantom event from one
   disjunct; {3/W} hybrid costs unmodeled despite CostManaHybrid existing.

## D2 fresh-eyes on e1ba62a (my reconciliation: REAL vs scope-nuance)
- "Central claim false": PARTIALLY — md5-frozen claim was true WITHIN the k-of-n batch but
  the commit jointly lands /29's search-pick promotions -> vs HEAD~ episodes DO drift
  (Garruk emblem 1->2 asks, new one_of gold:False). Claim-scope bug in MY commit message
  (verified on disk this turn). Code itself: SAFE verdicts on tag law + REST tuple.
- DEAD ASK (verified): Garruk emblem one_of has gold:False -> zero training signal, pure
  context drift. FIX: script gold answer into pack (or honest drop).
- LEGALITY TRIAD DIVERGENCE (verified lines): TARGET QConst unclamped (binding.py:1372) vs
  ONE_OF clamps k=min(want,len) (selectors.py:440s) vs feasibility matrix (query.py:335s,
  want==1 empty infeasible, want>1 feasible, QAtMost min=1 only when n>0). One card shape,
  three answers -> T3 unification (owner §9: legality is the {menu} axis, must be ONE).
- /29's "offenders 0" was FALSE: final corpus summary has no_discrimination:1,
  null_gt0_offenders=[Fierce Empath big_game_pick (gold 'fire' not lane-needed)].
  Cert caught it; the agent's claim didn't trace to the final file. Offender resolution:
  either lane needs the pick (strengthen lanes) or true-no-decision FAIL-REGISTERED.

## Queued consequences (T3 small / T4 owner-gated)
T3 (no enum surgery): legality triad unification; dead-ask gold fill (garruk emblem,
empath resolution); stale gap comments -> accurate capability notes; timestamp-order probe
test for PT layers; replay-pin the ONE new emblem ask.
T4 (owner review BEFORE touching): verb ontology split {operation | effect | policy} +
zone-verb unification (MILL/DISCARD/EXILE -> MOVE_ZONE+params) — a REWRITE per §9, affects
goldens+vocab: exactly the "first 20 sets change the atomics" case, needs owner sign-off
plus re-vocab + re-cert + full revalidation.

ADDENDUM (doc 36 ⑤, 2026-10-07): the PT timestamp probe LANDED and the
characterized smell is real — the ledger folds SET_PT and MODIFY_PT deltas in
PURE TIMESTAMP order: [+1/+1 then SET_PT 3/3] ⇒ 3/3, [SET_PT 3/3 then +1/+1]
⇒ 4/4. CR (fixed layers 613.3b set BEFORE 613.3c modify) says 4/4 for BOTH
orders. Pinned as test_current_pt_timestamp_behavior (test_executor_verbs.py);
T4's layer-model work must take this test as the loud diff it intends to move.
