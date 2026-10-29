# /173 — WINDOW #4 HARVEST (branch 2 → lever step-up) + STEPS-3 ARMING

Date: 2026-10-29 (harvest ~17:00–18:00; window #5 armed 18:00, fires 23:59).
Status: **BINDING** — pre-registered M3 decision table below.

## 1. Window #4 (iter-2 night) — chain 23:59:06 → 02:37:31, FULL CHAIN rc=0 (158 min)

Engine restored on the normal path (gateway 200, plugin-log-check clean). Export
**reuse** at 23:59:06 (fourth production reuse; payload fp `31b3b78c…` == tree).

| Invariant | Result |
|---|---|
| Episodes (1000g, seed-base 510201 / dps 1412 / rl-seed 4244) | **BYTE-IDENTICAL** (third consecutive night): SHA-256 `2e09d72b5f0caaf1540688f1180a2024c05f1741409e424a6da552d79206ab30`; 403W/581L/1D/**15X** (crash-row pin exact) |
| audit_iter1 | GREEN, **bit-identical** to nights 2–3: max\|Δ\| = 5.507469177246094e-4, mean 1.6923831339184937e-06, share>tol 0.0 (46941 asks) |
| P0/P1 | smoke GREEN (41 asks, grad 44.7 — identical display to n3); rld_cal (50g) mirror 0.5424 @60g — **identical to n3** (deterministic reproduction) |
| rld_i1 (steps 1, ~24m) | grad_norm_preclip **2.526103973388672 — bit-identical across independent nights** |
| rld_i2 (steps 2, ~48m) | `step_grad_norms = [2.526103973388672, 6.008041858673096]` — **pass-1 grad bit-identical to the standalone rld_i1 run: the pass-1 equivalence is confirmed on production 1000g data** (as pre-registered in /171 §4); KL_post 1.2892593279542177e-3 (cumulative vs frozen anchor), share_post 0.01685094054238299, \|Δlogp\|_post 7.20e-3, no ceiling breach, 93882 asks (2×46941 ✓) |
| Probe rld_i2 (200g, 512002/1413) | **M2 = 0.523 [0.453, 0.592]** (103W/3D/94L decisive); teacher 0.348 (era-local, not adjudicating); draws 3/200 (stall 0), 0 probe crashes |

## 2. Determinism record — CORRECTION (recorded honestly, gate-irrelevant)

rld_i1 diag, independent night re-run vs the n3 copy: pre-update keys and gradient
**bit-identical**; the two **post-update** keys differ by ~1e-9 relative
(`kl_post` 8.424083900436205e-4 vs 8.424085258158404e-4;
`|Δlogp|_post` 5.193425452647129e-3 vs 5.1934254927728934e-3). The steps-3 smoke
added a second datum: pass-2 grad 48.85174560546875 (3-step run) vs
48.85175323486328 (2-step run) — ~1.6e-7 relative. **Revised record: updates and
pre-update diagnostics are bit-reproducible on this GPU; post-update diagnostics
agree to ~1e-9…1e-7 relative; separate runs from pass-2 onward are NOT guaranteed
bit-identical.** Every gate threshold is ≥1e-4 and mirror noise is ±0.05 — no gate
or verdict is affected; the "bit-identical" claims in /171 §1/§4 stand for pre-keys
and pass-1 only.

## 3. Gates + /171 §7 table application

- AUDIT GREEN → not AUDIT-RED. **MOVED2 on both keys** (share_post 0.0169 > 0;
  KL_post 1.289e-3 ≥ 1e-4). Draw-detector 3 < 5 ✓. No MIRROR-DIVERGENT (single
  chain, M2 vs M1 neutral within noise). eval_acc F5: still the recorded bounded
  gap (/171 §2 argument holds a fortiori at KL 1.29e-3); standing gate lands at
  the confirmation phase per /172 §6.
- **M2 = 0.523 ∈ [0.47, 0.53) AND MOVED2 ⇒ BRANCH 2: lever step-up night —
  `--lr 1e-2 --steps 3` from the base (measured grid point on the steps axis,
  /157 lesson).** Steps-axis so far (single seed, same episodes): 1 step M =
  0.5279, 2 steps M = 0.523 — both within noise; movement is not converting.

## 4. Window #5 armed (steps-3 night)

Phase script (+3 lines, OUT of the PIN set): P2 = `train rld_i1 ep 1` +
`train rld_i2 ep 2` + **`train rld_i3 ep 3`** + **`probe p2 rld_i3`** (seed held
at 512002/1413 for cross-iteration comparability). rld_i1/rld_i2 stay in the
chain for window self-containment — they are bit-reproducible (pre-keys/grads),
so each night also yields a free determinism datum. No re-pin needed (tree fp
unchanged: `31b3b78c…`; sibling commits since arming are docs-only — see §5).
`rm .export_fp` forced rebuild+overlay (driver sha `730e3492…`); dry-run full
chain **rc=0** (17:42, CPU, all 3 trains + probe verified in the phase ledger);
**window #5 armed 18:00:11** (tmux rlwindow, `--gpu-train`, START 23:59,
HARD-RESTART 07:00, preflight PASS, no cancel file). Expected chain ~225 min
(collect ~43m + audit ~5m + trains 24/48/72m + probe ~31m + P0/P1) — fits the
P2 budget (PHASE1_WALL×18 + 45m ≈ 4.7h).

Smoke (steps 3, cuda, 2g): rc=0; pass-1 grad **50.3505744934082 bit-identical**
(THIRD confirmation of pass-1 equivalence); pass-3 grad norm 24260.29 (cuda) /
32740.49 (cpu dry) on the 2g batch — **harvest watch item** (clip 1.0 + KL ceiling
0.05 are the pre-registered brakes; 1000g smoothing expected per the 1/√G scaling
seen on passes 1–2: 50.35@2g → 2.526@1000g ⇒ pass-3 O(1e3) expected).

## 5. Sibling-lane state (no engine changes)

Three sibling commits landed after the window (16:05–16:58), all **docs-only**:
`2d06451` (plan: mapping new cards onto components + RL long-run exploration
notes), `fcfc5de` (**backlog B-49: noncreature permanents with no spell effect
cannot be cast — 44 M21 cards**, 63 FDN, 47 M19), `9af5d71` (backlog B-50/B-51:
engine findings). HEAD advanced to `5c18ad9` by arming (further docs). **None
implement engine code** — B-49/B-50/B-51 are recorded findings, not fixes; the
fingerprinted tree is untouched (PIN-MATCH verified at arming) and the M21
byte-invariance chain stands. **B-49 is noted as a future era-boundary-bundle
item**: when implemented it changes M21 casting legality for 44 cards ⇒ the
episode baseline re-baselines (that is what the bundle is for — /171 §8 ordering
unchanged).

## 6. PRE-REGISTERED M3 decision table (window #5 probe: rld_i3 vs anchor, 200g, seed 512002/1413)

MOVED3 = share_post > 0 OR KL_post ≥ 1e-4 (expectation: yes; KL_post3 ≈ 1.6–1.8e-3
cumulative — measured increments are decreasing: 8.4e-4 then +4.5e-4).

1. **M3 ≥ 0.53 AND MOVED3** ⇒ **confirmation per /172 WITH LEVER ADDENDUM**
   (fixed now, before M3): the confirmed lever is **lr 1e-2, steps 3 from the
   base** — the minimal-steps run that crossed 0.53 (M3 datum; 1-step 0.5279 and
   2-step 0.523 did not). Chain A = `rld_i3` (the crossing net); chains B/C train
   at steps 3 on fresh collects (513001/dps 1414/rl 4245; 514501/1415/4246);
   probes 400g on 516001/517001/518001 (dps 1416–1418); verdict rules per /172 §5
   UNCHANGED (CONFIRMED = all three ≥ 0.53 + pooled 1200g CI-lo > 0.50 + per-chain
   gates; PARTIAL = exactly two, no claim; NOT CONFIRMED = ≤ one). Budget: night 1
   ≈ 43+5+72+62+62 = 244 min, night 2 ≈ 182 min — both fit. Only the lever changes
   vs /172; seeds/counts/verdict/schedule are as pre-registered.
2. **M3 ∈ [0.47, 0.53) AND MOVED3** ⇒ **final measured point on the steps axis:
   next night steps 4** (total KL ≈ 2e-3, well under the 0.05 ceiling; train
   ≈ 96 min; fits the slot). **The single-seed ladder ENDS after steps 4
   REGARDLESS of M4** — pre-committed stop; then owner-level regime decision
   (the /157 branch-4 spirit: label-information ceiling analysis, or pivot to the
   era-boundary bundle). No open-ended per-night iteration.
3. **M3 < 0.47 AND MOVED3** ⇒ fallback B (lr 3e-3 × 3 steps) + root-cause
   (steps-axis anomaly: multi-pass REINFORCE on fixed anchor advantages degrades
   strength — check advantage-sign drift, entropy collapse, clip saturation).
4. **NOT MOVED3** ⇒ recalibrate the scaling law. **DIVERGENT3 / AUDIT-RED3** ⇒
   HALT + root-cause (as in /171 §7).
- Soft watch (NOT gates): `step_grad_norms[2]` (pre-clip) on 1000g — 2g smoke gave
  24260 (cuda); if > 1e4 on 1000g or KL_post > 1e-2, flag as anomaly for
  root-cause. Hard gates unchanged.

## 7. Next

- 23:59 → 07:00: window #5 (steps-3 night). Harvest tomorrow per §6 (verify
  ARTIFACTS in `/tmp/opencode/rld_n1/`: `audit_iter1.json`, `rld_i1/i2/i3_diag.json`
  (expect i3 step_grad_norms len 3; pass-1 grad 2.526103973388672), `probe_p2.json`
  = rld_i3 vs anchor; episodes by SHA only — expect `2e09d72b…`).
- Then arm per §6: confirmation night 1 (if branch 1) / steps-4 final point
  (branch 2) / fallback B (branch 3).
- Era-boundary bundle (§3.1.4 + B-43 + **B-49 when implemented** + re-baseline):
  after the multi-seed decision or the next plateau — not mid-chain.

## 8. Reports/ convention (per /171 §9)

This commit updates the `reports/` latest-artifact copies to window #4 content
(`probe_p2.json` = rld_i2 probe, `rld_i1_diag.json` — note §2: the committed copy
is the n3 one; tonight's n4 rld_i1 diag differs only in the two post-keys at
~1e-9 relative, recorded above; `rld_i2_diag.json` new; plus the window #4 phase
ledger `rl_window_2026-10-28.md`, `rl_window_dryrun.md`, and the small JSONs).
Episodes: SHA only, never committed.

## 9. Addendum (23:1x, pre-fire): sibling-lane docs read — era-boundary bundle scope

Read today's sibling docs (`docs/PLAN_CARD_ONBOARDING.md`,
`docs/PLAN_COMPONENT_TRAINING.md`, `docs/BACKLOG.md` — all docs-only commits):

- **Engine-touching card work is staged on branch `cards/mapping`** (worktree
  `/home/sune/Desktop/MTG_AI-sets`) "until an era boundary: the record loader
  touches `MTG_bot/`, which the RL pin fingerprints." The era-boundary bundle
  therefore absorbs, in addition to §3.1.4 + B-43 (+ B-49 when implemented):
  the `cards/mapping` merge (card records as data, `verified` supply mode) —
  all of it re-baselines the episode baseline after the multi-seed decision.
- **Their Step 0.5 (owner direction, recorded by the sibling): "RL must actually
  update. One gradient step per night is a no-op (/156, /158). Collect, then
  train many epochs (PPO-style, with a learned value for per-decision
  advantages) before the next collect. Keep the outcome reward. Add no
  shaping."** — this is the regime my pre-committed steps ladder points at:
  the {1,2,3,4} steps axis measures "how much update per collect"; if it
  plateaus, the owner-level call is the many-epoch regime (+ possibly a value
  head for per-decision advantages — a trainer change requiring its own
  pre-registration + smoke + re-pin) vs the label-information side (their
  Step 0.1–0.4: stop learning choices from HeuristicTeacher, make volumes
  learnable, make discards labelable, fold the component tail).
- **B-73 (soak, 2026-10-29): anomaly detectors flag ~2% of M21 games on
  `main`** (18 flags / 800 castable games, classes d1/d3/d5/d6, all
  pre-existing) + B-69/70/71/72/74 engine findings (several "weaker than
  printed"). These are era-boundary fix-queue candidates; any M21-affecting
  fix re-invalidates the byte-invariant chain ⇒ the bundle's re-baseline
  remains the only place to land them (ordering per /171 §8 unchanged).
- Their K2 table cites the pilot as "flat two nights" from the /156 era —
  current state (crossing lever MOVED, mirror 0.523–0.528) is in /171–/173;
  the sibling's read ("one update per night cannot teach anything") is
  consistent with the branch-2 step-up now armed.
