# /174 — WINDOW #5 HARVEST (M3 flat + MOVED3 → steps-4 FINAL point) + ARMING

Date: 2026-10-30 (harvest ~11:11–12:25; window #6 armed 12:25:43, fires 23:59).
Status: **BINDING** — pre-registered M4 watch items + owner-call framing below.

## 1. Window #5 (steps-3 night) — chain 23:59:06 → 03:42:35, FULL CHAIN rc=0 (~223 min)

Engine restored on the normal path (gateway 200). Export **reuse** at
23:59:06 (fifth production reuse; payload fp `31b3b78c…` == tree).

| Invariant | Result |
|---|---|
| Episodes (1000g, 510201/1412/4244) | **BYTE-IDENTICAL** (fourth consecutive night): SHA-256 `2e09d72b5f0caaf1540688f1180a2024c05f1741409e424a6da552d79206ab30`; 403W/581L/1D/**15X** |
| audit_iter1 | GREEN, **bit-identical** to nights 2–4: max\|Δ\| = 5.507469177246094e-4, mean 1.6923831339184937e-06, share>tol 0.0 (46941 asks) — file unchanged vs commit |
| P0/P1 | smoke identical display (2g/41 asks, grad 44.7, KL −1.83e-9, \|dlogp\| 3.219e-6); rld_cal mirror 0.542 @60g (32W/1D/27L) — **identical to nights 3–4** |
| rld_i1 (steps 1) | pre-keys + grad **bit-identical** again; post-keys drift ~5e-8/7.6e-8 relative vs the committed n4 copy |
| rld_i2 (steps 2) | pass-1 grad bit-identical; pass-2 grad 6.008195400238037 vs committed 6.008041858673096 (~2.6e-5 relative); post-keys ~1.6e-6/4.4e-6 relative |
| rld_i3 (steps 3, ~72m) | `step_grad_norms = [2.526103973388672, 6.007637023925781, 2.3506879806518555]` — **pass-1 grad BIT-IDENTICAL (4th independent confirmation)**; pass-3 grad on 1000g = **2.35 — the 2g blow-up (24260) did NOT carry over; the watch item resolves as a pure 2g-batch artifact** (1/√G smoothing held); KL_post 2.094148951675418e-3 cumulative (increments 8.4e-4 / +4.5e-4 / +8.0e-4 — not monotone, but ≤ 1/24 of the 0.05 ceiling), share_post 0.020515114718476384, \|Δlogp\|_post 8.69e-3, no ceiling breach, 140823 asks (3×46941 ✓), 15 crashes |
| Probe rld_i3 (200g, 512002/1413) | **M3 = 0.518 [0.448, 0.587]** (102W/3D/95L decisive); teacher 0.353; draws 3/200 (stall 0), 0 probe crashes |
| F5 eval_acc (rld_i3, `eval_ckpt` cpu, ~15s) | **0.6432 — delta 0.0000 vs anchor** (fourth consecutive 0.0000; /172 §8 gate: halt at < 0.6132) |

## 2. Determinism record — UPDATED (band, not point values)

Across the five independent GPU runs of the same computation: pre-update keys
and pass-1 grad norms are **bit-identical** (now 5 confirmations incl.
50.3505744934082 at 2g and 2.526103973388672 at 1000g); pass≥2 grad norms
drift **up to ~1e-4 relative** across separate runs (observed 1.6e-7, 2.6e-5,
6.7e-5 — the 6.7e-5 datum is pass-2 of the 3-step run vs pass-2 of the 2-step
run: 6.007637023925781 vs 6.008041858673096); post-update keys drift
**~1e-6…1e-8 relative** (observed 1.6e-9 to 4.4e-6). Interpretation: the
pass-1 update is fully reproducible; later passes accumulate floating-point
reduction-order noise that grows with pass depth. **No gate is affected**:
every threshold sits on KL/|Δlogp| at ≥1e-4 with ≥100× measured margin, mirror
noise is ±0.05, and the F5 tripwire sat at exactly 0.0000 four times running.
Supersedes the narrower bands in /171 §1 and /173 §2 (pre-keys/grad claims
stand; post/pass≥2 bands widened honestly).

## 3. Gates + /173 §6 table application

- AUDIT GREEN (bit-identical). **MOVED3 on both keys** (share_post 0.0205 > 0;
  KL_post 2.094e-3 ≥ 1e-4). Draw-detector 3 < 5 ✓. No divergence signal
  (M3 vs M2 neutral within noise; no reward/WR contradiction). F5 delta 0.0000 ✓.
- **M3 = 0.518 ∈ [0.47, 0.53) AND MOVED3 ⇒ BRANCH 2: steps-4 night is the
  FINAL measured point on the steps axis; the single-seed ladder ENDS after
  it REGARDLESS of M4 → owner-level regime decision** (pre-committed stop per
  /173 §6). Steps-axis so far (single seed, same episodes, lr 1e-2):
  {1: 0.5279, 2: 0.523, 3: 0.518} — flat within ±0.05 noise at every scale
  tested; point estimates drift −0.005 per step but are indistinguishable
  from flat. The honest synthesis: **movement exists at every scale (both
  MOVED keys live, KL 8.4e-4 → 2.1e-3) but is not converting into mirror
  strength; eval_acc is untouched at every scale (0.6432, four times).**

## 4. Window #6 armed (steps-4 night)

Phase script (OUT of the PIN set): P2 now = collect + audit +
`train rld_i3 ep 3` + **`train rld_i4 ep 4`** + **`probe p2 rld_i4`**
(seed held 512002/1413). rld_i1/rld_i2 **dropped** from the chain —
bit-reproducible and twice recorded; all four trains would be ~319 min, over
the 4.7h budget formula; i3 stays as a free determinism datum + net
persistence. Budget now 43+5+72+96+31 = **~247 min < 4.7h** ✓. No re-pin
(tree fp unchanged: `31b3b78c…`; sibling commits since arming are
docs/knowledge-only — see §8). `rm .export_fp` forced rebuild+overlay;
dry-run full chain **rc=0** (12:10, CPU; ledger shows i3×3-updates + i4×4-updates
+ probe p2, rc_phases=0); **window #6 armed 12:25:43** (tmux rlwindow,
`--gpu-train`, START 23:59, HARD-RESTART 07:00, preflight PASS, single
driver, no cancel file).

Smoke (steps 4, cuda, 2g): rc=0; pass-1 grad **50.3505744934082 BIT-IDENTICAL
(5th confirmation)**; `step_grad_norms = [50.35, 48.85, 24276.1, 57.58]` —
the 2g pass-3 blow-up reproduces (24276 vs last smoke's 24260) and pass-4
settles back to 57.6; KL_post 8.98e-4, share_post 0.0282, no breach, 852 asks.
(1000g pass-3 measured 2.35 last night ⇒ 1000g pass-4 expected healthy;
watch item below.)

## 5. PRE-REGISTERED M4 watch items + HARD GATES (window #6 probe: rld_i4 vs anchor, 200g, seed 512002/1413)

- **HARD GATES**: episodes byte-identical (SHA `2e09d72b…`, 15 crash rows,
  4th… fifth night); audit GREEN (expect bit-identical 5.507469177246094e-4);
  no KL-ceiling breach; draw-detector < 5/200; 0 probe crashes;
  **F5: eval_ckpt(rld_i4) ≥ 0.6132** (anchor 0.6432; >3pt drop ⇒ halt).
- MOVED4 = share_post > 0 OR KL_post ≥ 1e-4 (expectation: yes;
  KL_post4 ≈ 2.4–2.9e-3 — increment pattern 8.4/4.5/8.0e-4 ⇒ +4–8e-4).
- rld_i4 `step_grad_norms[0]` = 2.526103973388672 expected (6th bit-identity).
- **Soft watch**: `step_grad_norms[3]` (pass-4) on 1000g — pass-3 on 1000g
  was 2.35 (healthy); if pass-4 > 1e4 or KL_post > 1e-2, flag anomaly for
  root-cause (clip 1.0 + ceiling 0.05 remain the pre-registered brakes).

## 6. OWNER-CALL FRAMING (pre-registered for the morning after M4 — the ladder ENDS after this night regardless of M4)

Data summary to carry into the decision:
1. Steps axis (single seed, same episodes, lr 1e-2):
   {1: M 0.5279, 2: 0.523, 3: 0.518, 4: M4} — flat within noise at every
   scale measured; movement present at every scale (both MOVED keys live);
   KL cumulative ≤ ~3e-3 (≤ ~17% of ceiling); eval_acc 0.6432 unchanged
   (0.0000 five times running).
2. The rig itself is proven sound: five nights of byte-identical episodes +
   bit-identical audits, pass-1 bit-identical training, deterministic probes.
   "Movement not converting" is a property of the algorithm/data pair, not
   of the rig.
Options on the table (owner decides; the /173 pre-commitment named B and C;
A and D are added for completeness):
- **(A) Multi-epoch regime with a learned value head** (sibling Step 0.5,
  owner direction recorded 2026-10-29): per-decision advantages instead of
  batch-mean ±1; PPO-style or REINFORCE-with-value. Attacks the most
  plausible cause of "movement not converting" (coarse credit assignment).
  Requires a TRAINER rewrite (tools/training is in the PIN set): its own
  pre-registration, real-mode smoke, re-pin, and a re-baselined steps ladder.
- **(B) Label-information side** (/133 analysis + sibling Steps 0.1–0.4):
  stop learning choices from HeuristicTeacher, make volumes learnable, make
  discard labelable, fold the component tail. Attacks the diagnosed binding
  constraint (LABEL INFORMATION) directly.
- **(C) Era-boundary bundle FIRST**: §3.1.4 seat-rig fix + B-43 OWNER fix +
  B-49 (cast legality, 44 M21 cards) + B-69–74 fix queue + the sibling's
  `cards/mapping`/`cards/integration` merge (their /177 package lists the
  "RL consumers to update at the merge" explicitly) + re-baseline +
  re-collect + re-pin. Then re-run the regime decision on the fixed engine
  — the current mirror verdicts carry the era's known biases (symmetric rig,
  recorded in /172).
- **(D) Pilot-negative close**: declare the REINFORCE-at-iteration-scale
  pilot complete with its measured flat axis; resume the /133 label-
  information analysis as the program's main thread.
Framing note (not a recommendation): C was already the scheduled structural
milestone and the sibling has now built its side of it; B is the most direct
attack on the diagnosed constraint; A is the owner's own recorded direction
for "RL must actually update". M4 itself only adds the fourth axis datum.

## 7. Reports/ convention (per /171 §9)

This commit updates the `reports/` latest-artifact copies to window #5
content (`probe_p2.json` = rld_i3 probe; `rld_i3_diag.json` new;
`rld_i1/i2_diag.json` = n5 copies, post-keys per §2; plus window #5 phase
ledger `rl_window_2026-10-29.md`, `rl_window_dryrun.md`, and the small JSONs).
Episodes: SHA only, never committed.

## 8. Sibling-lane state

Four sibling commits since my last arming, all knowledge/ontology docs on
main (PIN-MATCH verified at arming; fingerprint untouched): R5 gate rounds
3→4 (R5-7/9/10/11 + two engine items GO on `cards/integration`; R5-2/5/8/12
fix-then-round-4; R5-13 FIRST_MATCH rejected for REVEAL.until) and **/177:
the M21 campaign era-boundary package on `cards/integration` (NOT merged) —
263 of 281 castable verified, verification numbers, fixes by area, gates,
and the RL consumers to update at the merge**. Their era-boundary package is
now concrete; at merge, the RL-consumer list in their /177 must be diffed
against my pilot's pin surface (episode pool, anchor, eval families) before
the re-pin. B-73 (~2% M21 anomaly flags) and B-69–74 remain the fix queue.

## 9. Next

- 23:59 → 07:00: window #6 (steps-4 FINAL ladder point). Harvest tomorrow per
  §5 (verify `rld_i4_diag.json`: steps 4, step_grad_norms len 4,
  step_grad_norms[0] = 2.526103973388672, pass-3 ≈ 2.35, pass-4 watch;
  `probe_p2.json` = rld_i4 → M4; episodes SHA `2e09d72b…`; audit bit-identical;
  F5 delta).
- After M4: **the ladder is done regardless of result** → write the owner
  decision memo per §6 (data + options A/B/C/D), arm per the owner's call.
