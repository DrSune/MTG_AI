# 153 — First live-LLM number (track R): delta 0.411 vs null [0.189, 0.650]; RUN-L3 duel post-mortem = work-volume arithmetic, not infra; quiet-engine law refined; duel (deals=1) running detached
Date: 2026-10-26 (14:35–15:45 CEST). Engine: 27B NVFP4 up (gateway 200). Sibling sessions (claude-ced, claude-mtg) may share the engine.

## The first live-LLM number — RUN-L3r (track R)
`bench --masked rules --answerer llm --limit 12` — model `nvidia/Qwen3.8-27B-NVFP4-low` (same 27B weights; low reasoning preset — the plain model's reasoning-token bloat is what burned L1/L1b/L2: measured `completion_tokens` 1428 vs `max_tokens` 512), temp 0, 600 s timeout, transient-5xx retries, masked lane, M21+ZNR item pool.
- Wall ≈ 21 min (14:49→15:10), RC=0, detached (tmux `benchrules`).
- **all-keys 0.518 [0.278, 0.758]; delta vs null 0.411 [0.189, 0.650] — CI excludes 0.**
- Exclusions honest: 116 items excluded by reason (opaque decision word 44, ability index not oracle-mappable 58, combat damage-order/trample lanes 5, engine-error 3, no scorable lane 6).
- Stderr note (logged, not hidden): `supply[ZNR]: shape-gap exclusion 'Nighthawk Scavenger': parse_pt: unexpected value '1+*'` — known shape gap, excluded as reported.
- Reading (pre-registered here, post-hoc-safe): first LIVE number = plumbing + baseline signal, NOT a strength claim; n=12 exploratory, confirmation size per DESIGN §6. The delta CI excluding 0 is the first evidence the local model adds value on the R track over the null floor in prompt mode.
- Record: DESIGN_BENCHMARK §10 table row; `/tmp/opencode/bench_rules_l3.report.json` + `bench_rules_l3_items.jsonl` (manifest+12 items, durable copy to reports/ at harvest — /tmp is not durable).

## RUN-L3 (duel, deals=2) post-mortem — 4 h, zero settled games
Detached shell timeout at 4 h (14:40), jsonl 0 bytes (games flush on settle). Engine logs: 125 POST /v1/chat/completions in the window, ALL 200 OK, generation throughput ~15–16 tok/s sustained ⇒ **the engine was healthy and serving; the failure is work-volume arithmetic, not infra**: a duel game ≈ 25–100+ LLM asks; at the measured ~1.8 min/ask under session/sibling contention, one game is 1–5 h, and deals=2 = 4 games. The first duel attempt that can settle is deals=1 (2 games) in a detached run with a generous budget.

## OPS LAW REFINEMENT (supersedes /150's unmeasured variant)
1. A fresh session + engine up ⇒ completions flow immediately (probes: 3.6 s / 6.1 s, both presets).
2. A session holding KV does NOT hard-block completions: RUN-L3r settled 12 items in 21 min with my session idle-but-alive, at ~1.8 min/ask (vs ~6 s/ask in probes) — contention slows, it does not wall.
3. Hard walls observed before: L1 (120 s timeout too short), L1b (503 bursts under heavy session activity), L2 deals 2–4 (engine OFF — the RL window), L2 deal 1 (44 min of slow calls + 600 s timeouts).
4. Consequence: **detached runs (tmux) with per-request timeout 600 s and retries work**; the first live numbers no longer require an owner-scheduled quiet slot — they require (a) engine up, (b) bounded item counts, (c) wall-clock headroom vs the next engine-off window (23:59 tonight).
5. Duel estimate at current pace: deals=1 ≈ 2–3 h ⇒ should settle well before 23:59. If not, settled games persist in the jsonl at engine-off.

## RUN-L3d (duel, deals=1, masked, -low) — RUNNING detached since 15:38 (tmux `benchl3d`)
Pre-registered reading: first live DUEL number = pair score vs the uniform floor + cost/clock (tokens/ask, latency); the floor is not a strength bar (review: bot adapter blocked on B-23; LLM-vs-floor is a plumbing+cost measurement, same as the R run). Manifest carries the full identity block (F2). `refused-leaky` will report any name-ask exclusion.

## Carried
Quiet-engine owner-scheduling item from /150 is RESOLVED as unnecessary (refinement 4 above) — the bench lane is unblocked for any engine-up window; it remains blocked during RL windows (engine off) and should be sized to fit inside engine-up stretches.
