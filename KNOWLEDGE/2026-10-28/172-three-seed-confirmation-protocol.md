# /172 — 3-SEED × 400g CONFIRMATION PROTOCOL (pre-registered BEFORE the M2 result)

Date: 2026-10-28 23:1x (window #4 still pending fire at 23:59; M2 unknown).
Status: **BINDING PRE-REGISTRATION** — this protocol is fixed before seeing M2 so that
no seed, count, or verdict rule can be moved post-hoc. If /171 §7 branch 1 does not
fire (M2 < 0.53 or not MOVED2), this document is superseded-unused and the iter-2
table's other branches govern.

## 1. Trigger

`M2 ≥ 0.53 AND MOVED2` in the iter-2 probe (rld_i2 vs frozen anchor bsh_S3a_s1_b,
200g, seed-base 512002 / dps 1413) — per /171 §7 branch 1. Then (and only then) the
confirmation below runs, as the gate to ANY strength claim (/134 v2; owner 3-seed law).

## 2. What "3-seed" means here

Three INDEPENDENT training chains at the confirmed lever (**lr 1e-2, steps 2 from the
base**, the iter-2 lever): different 1000g collect seeds ⇒ different episodes ⇒
different nets. Probing the same net on rotated probe seeds would NOT satisfy the
3-seed law (training-data independence is the claim under test).

- **Chain A** = `rld_i2` (already trained on the iter-1 episodes, seed-base 510201;
  bit-deterministic, SHA-recorded at harvest).
- **Chain B** = fresh 1000g collect + `train steps=2` (new collect seed).
- **Chain C** = fresh 1000g collect + `train steps=2` (another new collect seed).

All three nets are the SAME lever on DIFFERENT data — a pure data-independence test.

## 3. Seed allocation (D9-disjoint from every consumed block)

Used blocks (pilot lane, from `tools/ops/rl_pilot_phases.sh` + entries):
collect 510101/50g (510102–510151), collect 510201/1000g (510202–511201),
smoke 511001/2g (511002–511003), probe 512001/60g (512002–512061),
probe 512002/200g (512003–512202), seat probe 610301–610340; dps 1409–1413;
rl-seeds 4242–4244. Duel registry (`reports/monitoring/duel_seeds.json`): 1–540,
90001–90124 (BC-era nets).

| Item | Games | seed-base | seed span | dps | rl-seed |
|---|---|---|---|---|---|
| Chain B collect | 1000 | **513001** | 513002–514001 | **1414** | **4245** |
| Chain C collect | 1000 | **514501** | 514502–515501 | **1415** | **4246** |
| Probe A (rld_i2) | 400 | **516001** | 516002–516401 | **1416** | – |
| Probe B (chain B net) | 400 | **517001** | 517002–517401 | **1417** | – |
| Probe C (chain C net) | 400 | **518001** | 518002–518401 | **1418** | – |

Disjointness: every span is ≥ ~500 clear of the next nearest used block
(511201, 512202, 610301, and the other new spans); probe spans mutually disjoint
with 100-seed gaps; dps/rl-seeds all new. The P1/P2 pilot probes' 59-deal overlap
(512003–512061, different nets, diagnostic lanes) is noted as a known quirk of the
pilot rig — NOT replicated in the confirmation (all confirmation blocks disjoint).

## 4. Schedule (two window nights, 23:59→07:00 each, gpu-train)

- **Night 1** (P0/P1 standard, then): chain B (collect ~43m + audit ~5m + train
  steps=2 ~48m) + **Probe A** (400g ~62m) + **Probe B** (400g ~62m) ≈ 220 min
  (fits the P2 budget formula: PHASE1_WALL×18 + 45m margin ≈ 4.7h).
- **Night 2** (P0/P1 standard, then): chain C (collect + audit + train) + **Probe C**
  (400g) ≈ 160 min.
- Each night: export reuse (payload unchanged — no fingerprinted-tree change;
  if the sibling lands engine code, the pin wire aborts honestly and the schedule
  shifts per their merge note), audit GREEN gate before each train, probe on CPU
  inside the window (device=cpu per the probe() convention — 400g ≈ 62m).

Wiring (to implement at arming, per /171 lessons): the phase script's P2 becomes a
confirmation block (parameterized collect seeds; `train rld_cB ep 2` /
`train rld_cC ep 2`; two/three 400g probes on the allocated seeds). tools/ops change
⇒ `rm .export_fp` before the dry-run so the rebuild overlays the new driver
(documented in /171 §4). Dry-run full chain rc=0 required before arming. No
fingerprinted-tree change expected; if any (e.g. a meter added to the chain — see
§6), real-mode smoke + explicit re-pin first.

## 5. Verdict rules (fixed now)

Per-chain mirror decisive WR at 400g: M_A, M_B, M_C (vs frozen anchor, each on its
own disjoint probe block). Gates per chain: audit GREEN, MOVED (share_post > 0 OR
KL_post ≥ 1e-4), draw-detector < 5/400, no probe crashes, no DIVERGENT signal.

- **CONFIRMED** (strength claim permitted): ALL THREE M_X ≥ 0.53 AND the pooled
  1200g decisive WR has CI95 lower bound > 0.50 AND all per-chain gates hold.
  → the RL pilot has produced a verified, data-independent strength movement at
  iteration scale; wave-2 funding discussion (owner) + era-boundary bundle decision.
- **PARTIAL** (exactly two M_X ≥ 0.53, gates hold): NO strength claim. Report to
  owner as pilot-positive-but-unconfirmed; regime call (third seed re-run with a
  fresh block, or accept-with-disclosure — owner decision, not mine).
- **NOT CONFIRMED** (≤ one M_X ≥ 0.53): the single-net iter-2 result does not
  replicate → pilot negative at iteration scale; back to the /133 label-information
  analysis + regime call. The M2 number stands as a measured single-seed datum,
  labeled unconfirmed.
- Any chain AUDIT-RED / DIVERGENT / draw-halt: halt that chain, root-cause; the
  verdict can degrade to at most PARTIAL-with-disclosure. No chain is re-run on a
  moved seed without a new pre-registration entry.

## 6. Standing gates to ADD at the confirmation phase (per /134 F5)

- **eval_acc puzzle meter** per chain (anchor baseline vs each net, M21 vocabulary —
  same set, so the meter is meaningful; cross-set use stays diagnostic-only per
  /135 FATAL-2): halt that chain on drop > 3pts vs pre-RL. The meter CLI must be
  identified at arming time (candidate: `tools/training/packrec.py` wrapping
  `tools/audit/puzzle_cert.py`; anchor baseline number from the BC training records
  if no fresh anchor run is cheap) — this was the recorded gap in /171 §2.
- Era-parity sentinel (ladder, /161) unchanged; runs outside the window.

## 7. Provenance

Pre-registered 2026-10-28 before the iter-2 probe (window #4 fires 23:59 the same
evening). Seed blocks allocated against the full consumed list in §3; the allocation
table above is the binding D9 record for the confirmation.
