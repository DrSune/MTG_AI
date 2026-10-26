# 155 — First live DUEL: LLM 2/0 vs uniform floor, pair 1.0; first live cost/clock; plumbing+cost measurement only (floor is not a strength bar)
Date: 2026-10-26 (duel ran 15:38→21:57, settled before the 23:59 engine stop). Engine: 27B NVFP4.

## RUN-L3d (deals=1, masked, `nvidia/Qwen3.8-27B-NVFP4-low`, prompt mode, temp 0, 600 s timeout, retries)
`bench --masked duel --a llm --b uniform --deals 1 --set M21 --pool castable`, detached tmux `benchl3d`.
- **2/2 wins** (decisive_rate 1.0), **pair_score 1.0 [1.0, 1.0]** (n=1 pair — degenerate CI, honestly labeled), elo inf (no losses — degenerate).
- **Duplicate-pair mechanism proven live**: both games share `setup_fp 7091e657a091592b…` (same deal, seat-swapped) — the exact-pair statistics' foundation worked in a real run.
- Integrity flags clean: `refused_leaky: 0` (no name-ask hidden-zone exclusion triggered), `usage_missing: 0`, `token_stats: ok`, 0 voids, 0 forfeits.
- Seat detail: game 1 (LLM seat 0): LLM 92 asks/134 acts, 39 turns, won; uniform 141 asks. Game 2 (LLM seat 1): LLM 78 asks/50 acts, 20 turns, won; uniform 78 asks. Seat order shifted game flow (39 vs 20 turns) — expected with a stochastic floor.

## Cost and clock (BEN-T1 — first live numbers)
| game | calls | prompt tok | completion tok | wall |
|---|---|---|---|---|
| LLM seat 0 | 92 | 198,153 | 162,702 | 14,478 s (4.0 h) |
| LLM seat 1 | 78 | 98,596 | 97,489 | 8,263 s (2.3 h) |
≈ 2.3 k tokens/call and ≈ 2.6 min/call **under session contention** (my session idle-but-alive + possible sibling sessions; /153 pace). Prompt tokens accumulate across the game (view growth): mean ~2.1 k prompt tokens/call. The `-low` preset still emits large completions at 27B (mean ~1.8–2.1 k completion tokens/call) — the cost/clock plot will need the plain/medium/xhigh arms later for the full Pareto (DESIGN §8).

## Reading (pre-registered /153, applied)
First live DUEL = **plumbing + cost/clock measurement**, NOT a strength claim: the uniform floor is the bottom rung (the §10 MVP already measured uniform-vs-pass at pair 0.995); the strength question (LLM vs the BC bot) is gated on the bot adapter (B-23 per-seat encoder). What this run IS evidence for: the full live loop (masked honest view → prompt-mode seat → engine-validated numbered answers → duplicate-pair accounting → integrity flags) works end-to-end at production scale, and the quiet-engine refinement (/153) is confirmed — the pair settled in ~6.3 h of engine-up time with a session resident.

## Sizing note for the next duel runs
One pair at contested pace costs ~6 h wall; uncontented (no agent sessions) it should be a fraction of that. Confirmation-size N (DESIGN §6) ⇒ schedule as a dedicated morning engine-up stretch, detached, multiple deals in one run (`--deals N` reuses the same process; deals are independent pairs).

## Window
Night-2 RL window armed and intact at handoff (23:59/07:00, PIN triple-match, /152 pre-registration binding). All of this session's harvest commits touch docs/KNOWLEDGE/reports only — payload fingerprint unchanged (verified at commit time), frozen export stands.
