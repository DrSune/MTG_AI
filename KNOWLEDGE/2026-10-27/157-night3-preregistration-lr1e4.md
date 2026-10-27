# 157 — Night-3 pre-registration: lever lr 1e-4 (10×); decision table on the same 200g mirror probe
Date: 2026-10-27 (pre-night-3, binding). Window: 2026-10-27 23:59 / 07:00, `--gpu-train`.

## Context
Night-2 = first full chain, MIRROR-FLAT per /152 (mirror 0.523 [0.453,0.592] @200g; policy NOT MOVED: mean|dlogp| 1.69e-6, KL_post 2.4e-9, share|dlogp|>0.1 = 0). Root cause: step-size arithmetic — raw SGD, lr 1e-5, clip 1.0, one update ⇒ weight step ~1e-5 ⇒ sub-threshold policy movement. The instrument (audit bit-exact + deterministic on cuda; F4 discriminators; mirror axis) is proven; the lever is the variable.

## Night-3 change (the ONLY change)
`train()`: `--lr 1e-5` → `--lr 1e-4` (phase-script one-line, documented). Everything else identical: same frozen export (PIN), same deterministic 1000g episodes (seed 510201 — byte-identical re-collect), same beta 0.1 / clip 1.0 / entropy 1e-3 / KL ceiling 0.05, same 200g mirror + teacher probes, same guards.
Changed-dimension smoke (real mode, PITFALL law): trainer on the real 1000g episodes, cuda, under session contention — must show finite loss, clipped grad, F4 keys, and a ~10× larger movement signature (mean|dlogp| ≈ 1e-5, share|dlogp|>0.1 likely > 0, KL_post ~1e-7) before re-arm.

## MOVED discriminator (unchanged from /152)
MOVED = share|dlogp|>0.1 > 0 OR KL_post ≥ 1e-4.

## Decision table (200g mirror probe, same rig/convention as /152)
M = mirror WR point estimate (rld_i1_n3 vs frozen pre-RL anchor).
1. **M ≥ 0.53 AND MOVED** ⇒ learning now visible AND converting to strength ⇒ **3-seed × 400g rotated-seed confirmation** (the /134 v2 gate to any strength claim). If the 3-seed confirmation holds ⇒ wave-2 proceeds on the evidence.
2. **M ∈ [0.47, 0.53) AND MOVED** ⇒ "movement not yet converting to strength at 1 iteration" ⇒ **iter-2 at the same lever**: train rld_i2 on the SAME episodes (importance ratio starts ≈1 — the iter-1 shift is ~1e-5 logp; the clip protects), probe again. One further iteration before any lever change or escalation. (Branch not in /152 because /152 assumed NOT-MOVED was the likely state at 1e-5; filled here, pre-night.)
3. **M < 0.47 AND MOVED** ⇒ actively harmful ⇒ root-cause (reward mapping, crash-row treatment — 15 crash-loss rows are 1.5% of the batch, same as night-2, not new) before further funding.
4. **NOT MOVED at lr 1e-4** ⇒ the single-update lever is underpowered even at 10× ⇒ ESCALATE to owner with the confounder-isolated grid: {lr ∈ 1e-4, 3e-4, 1e-3} × {steps ∈ 1, 10, 20} — the pilot's instrument question ("can this net learn from outcome reward at all?") needs a stronger update regime than the pilot spec's single-conservative-update design; that regime choice is owner-level (training-compute cost per night).
5. **MIRROR-DIVERGENT** (reward/WR divergence) ⇒ HALT per /134.
6. **AUDIT-RED** ⇒ plumbing regression (should be impossible — the audit is bit-deterministic on this export; a RED means the episode/policy pairing changed, i.e. a pin/fingerprint failure) ⇒ root-cause before any training.

## Invariants this night must preserve (violation = data invalid, re-run)
- Export reuse by fingerprint (no re-archive unless provenance says so).
- episodes_iter1.jsonl byte-identical to nights 1-2 (deterministic seed + frozen export) — verify sha256 against night-2's if in doubt (the file is overwritten in place; its sha was recorded in the night-2 ledger's collect line: 3399238 bytes).
- Mirror axis = same frozen pre-RL anchor as nights 1-2 (`bsh_S3a_s1_b`) — the verdict axis is only comparable across nights if the anchor never changes.

## What does NOT count
Same as /152: teacher lane (era-local), single-run mirror without 3-seed confirmation for strength claims, n=200 CI as publishable.
