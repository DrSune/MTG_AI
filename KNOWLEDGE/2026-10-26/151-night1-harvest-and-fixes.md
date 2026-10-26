# 151 — Night-1 harvest: P0/P1 GREEN (mirror 0.552 = instrument noise, policy not yet moved), P2 died on the CPU audit's unscaled timeout; fix = CUDA audit + PIN/export-freeze guard + audit SHA-identity; re-armed for night-2
Date: 2026-10-26 morning (04:37–06:30 CEST). Engine: 27B NVFP4 restored 02:02:02 after the window (rc=6).

## Night-1 ledger (window 2026-10-25 23:59 → 2026-10-26 02:02, export HEAD b308cf5, payload == e36ae62 semantics)
- **P0 smoke**: collect→audit→train plumbing GREEN (rld_smoke.pt + diag + audit_smoke GREEN).
- **P1 calib (50g)**: audit bit-exact on CPU (max|Δ|=0.0, tol 1e-3, 2411 asks). F4 diag: grad 12.8→clip 1.0, reward_var 0.9856, no crashes — **plumbing alive**; but **policy not yet moved**: mean|dlogp_chosen|=1.9e-6, KL_post=3.1e-9, share|dlogp|>0.1=0.0 (one conservative step: lr 1e-5, clip 1.0). F4 no-op reading: NOT dead plumbing; the iter-1 step is the real test.
- **P1 probe (60g)**: **mirror rld_cal vs frozen pre-RL anchor 0.552 [0.424,0.672]**; teacher lane 0.356 (descriptive only, era-local per the era-drift law). The mirror point estimate is consistent with game-noise around a near-identical net (KL 3e-9) — instrument reading, NOT a strength claim.
- **P2 collect (1000g)**: 2601s = **0.384 g/s net** (cpu, 6 workers) — beats the provisional 0.25 g/s (/149 era). Teacher lane 0.410 [0.379,0.441] vs HeuristicTeacher (era anchor 0.394 — consistent, descriptive).
- **P2 audit (1000g, CPU, guard 3600s)**: **rc=124 TIMEOUT** at 02:02:01 — calib audit measured ~4.8 s/game on CPU ⇒ 1000g needs ~80 min > 360 s guard. The budget formula scaled collection (×18) but NOT the audit. Chain stopped honestly (rc=6), engine restored 02:02:02. Trainer and the 200g probe never ran; **no rld_i1.pt**.

## Fixes (payload lane; all smoke-tested in real mode per the PITFALL law /146)
1. **CUDA audit** (`rl_pilot_phases.sh` audit(): cpu→cuda): inside the window the engine container is stopped ⇒ GPU free. Real-mode smoke: cuda audit of the REAL 1000g iter-1 episodes (46941 asks) **GREEN in 6m09s** (under session contention; ~10× headroom under the 3600s guard), max|Δ|=5.5e-4 < tol 1e-3, mean|Δ|=1.7e-6 — cross-device float noise, as expected; device cannot fake an off-policy match.
2. **Audit policy-identity fix** (`rl_logprob_audit.py`): ownership was pure resolved-PATH equality — the /149 SHA identity existed only in the trainer (`_ckpt_key`). Repo-path audit of export-collected rows ⇒ 0/1000 "foreign" (smoke failure that exposed it). Now mirrors the trainer: SHA-256 of checkpoint bytes when the file exists, resolved-path fallback. +2 tests (cross-path owned; byte-mismatch fail-loud). `pytest tools/training/test_rl_train.py -q` → **11/11**.
3. **PIN + export-freeze guard** (`rl_window.sh`, PIN law /146/147): `payload_fingerprint()` = hash of the working-tree engine+payload tree (MTG_bot/ + tools/eval + tools/training, .py+.pt, tests excluded; drivers/bench/docs/knowledge stay OUT — they don't change engine semantics). At start: existing export with matching fingerprint ⇒ **reuse, no re-archive**; PIN exists and matches ⇒ rebuild from the pinned payload; PIN exists and MISMATCHES ⇒ **fail-loud abort before any engine touch** (owner decision: re-smoke the changed dimension, then re-pin explicitly — never silently). After the first FULL-CHAIN rc=0 the window itself writes the PIN.
   - **Deviation recorded**: PIN was created by the orchestrator PRE-night-2 (law says "after the first completing night") because P2 must re-run from the frozen night-1 export — the tripwire fired once during today's dry-runs when fix #2 changed the payload tree, proving the gate works; re-pinned explicitly with provenance after re-smoke.
4. Smoke record: dry #1 (PIN match → rebuild → FULL CHAIN rc=0 + forced-ERR trap proof), dry #2 (export reuse → FULL CHAIN rc=0), PIN-tamper ⇒ exit 3 "PIN DRIFT" before engine touch.

## Bench lane (RUN-L2 post-mortem — quiet-engine law REINFORCED)
RUN-L2 (masked, 4 deals, 600s, retries): 8/8 void-infra. Deal 1 voided over ~44 min (timeouts/503s while the session — active then idle — held KV); deals 2–4 failed in ~70 s each (503 + 3 retries) right after 23:59 = engine-off window. First live-LLM number still pending the owner's scheduling call (/150 options a/b/c). No strength/cost claims made.

## Night-2 plan (window 2026-10-26 23:59 / 07:00, --gpu-train, PIN-frozen export)
P0 → P1 (calib 50g; deterministic seed ⇒ same data) → P2: collect 1000g (deterministic seed 510201, same frozen export ⇒ byte-identical episodes), **cuda audit (minutes, not hours)**, train on GPU, **200g mirror probe = the verdict axis** (vs the frozen pre-RL anchor; teacher lane descriptive only). Budget: P2 real workload ≈ 95 min inside ≈ 6 h remaining at that point — comfortable.

## Numbers
collect 1000g 2601s/0.384 g/s; cuda audit 46941 asks 369s (max|Δ| 5.5e-4); cpu audit ~4.8 s/game (calib 2411 asks ≈ 4 min); probe 60g 567s ≈ 9.45 s/match.
