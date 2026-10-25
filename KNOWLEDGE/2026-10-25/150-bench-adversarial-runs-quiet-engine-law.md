# 150 — Bench adversarial pass + RUN-L1/L1b post-mortems: 2 FATAL found and neutralized, first live-LLM lane blocked by an ops finding (quiet-engine requirement), retry law added

Date: 2026-10-25 (owner: "develop the benchmark further ... do adversarial passes"). Engine: 27B NVFP4 (post-CED handback); gateway 8000.

## Adversarial pass (read-only, ses_e8bf393) — findings applied where in-scope
- **F1 FATAL — name-ask hidden-zone leak**: verbs.py CHOOSE_NAME enumerates ALL world cards (hidden hand/library included); bench `Ask.leaky` flags them; DESIGN §3.5 neutralization (refuse reporting pairs with leaky_asks>0) was COUNTED but never ENFORCED. Fix (coder, today): `refused-leaky` void class in duel.py, excluded from all stats, reported as count. Full fix (free-text naming vs oracle corpus, engine-validated) = deferred lane.
- **F2 FATAL — manifest lacks model identity**: model came from env, never recorded. Fix: `identities` block in manifest (model, base_url, timeout_s, temperature, max_tokens, strikes, primer, masked, usage_missing, transient_retries) + refuse to start an llm duel without it. **Verified live** in the RUN-L1b manifest.
- A3 (usage-missing → `token_stats: invalid`), A4 (strikes-exhausted + refuse=None → `AgentForfeitError` voids, never silently plays option 0), implemented (coder).
- A5/A6/A7 (pre-registration code hook; timeout=loss design gap; runtime leak audit / paired-masked lane): NOTED, deferred — the "exploratory" label stays honest; §4 amendment is a design-doc task.
- NOTES: n=2 → NaN winrate/±inf elo in JSONL (label carries it); one 429 voids a pair; primer censuses M21+ZNR regardless of --set; no `seed` in request body (cross-run determinism unenforceable).

## Fix added by me (on top of coder's): transient-5xx retry
`OpenAICompatClient.complete`: HTTP 502/503/504 retried up to `MTG_BENCH_LLM_TRANSIENT_RETRIES` (default 3), backoff 10/20/40s (capped 60); 4xx + timeouts stay fail-loud first hit (AGENTS 5xx-retry law). Counter surfaced in manifest identity. +2 tests (503-503-200 → success with retries=2; 400 → one attempt). `pytest MTG_bot/bench -q`: **70/0**.

## RUN-L1 post-mortem (unmasked, timeout 120s default) — 4/4 void-infra
`TimeoutError` at 120s: 27B under session contention measures ~6.4 tok/s (915 prompt / 196 completion in 30.7s); later calls grow. Also: `completion_tokens: 1428` vs `max_tokens: 512` — usage counts REASONING tokens (plain model name = deep reasoning). 120s is structurally too short. (This run's manifest has NO identity block — it predates F2; the L1b manifest proves the fix.)

## RUN-L1b post-mortem (masked, 600s) — 4/4 void-infra HTTP 503
NEW failure class. Isolation test: engine healthy (container up 5h, direct 8002 /v1 200, /health 200, vLLM decode throughput 0.0) while a fresh 400-token completion via the GATEWAY hung 300s → HTTP 000 (no response). ⇒ the stall is at the gateway/admission layer: **with an active orchestrator session (262k-xhigh KV) resident, new chat completions do not reach vLLM.** The 2 calls that succeeded landed in gaps; the rest 503.

## OPS LAW (new, binding for the bench lane)
**Live LLM bench runs require a QUIET engine: no active agent session contention.** Unmeasured variant: whether an idle-but-alive session still blocks admission (the isolation ran while I was mid-turn). Scheduling options for the first real live number (owner's call):
(a) owner-authorized quiet-engine slot (owner away, my session dormant, bench from a detached tmux script — window-pattern plumbing exists);
(b) test the idle-session variant: after this session goes quiet, a detached bench script probes whether completions flow with zero active turns;
(c) hosted model (refused by design: local-first, `MTG_BENCH_ALLOW_REMOTE` gate) — last resort only.

## What the first live number may claim (per adversarial, pre-registered)
End-to-end execution, engine-validated answers, recorded outcomes with distinct void classes (void-infra / forfeit-no-refuse / refused-leaky), no silent infra-loss. NOT strength, NOT determinism, NOT cost/clock.

## Deferred (post-tonight, payload-re-smoke law respected)
Rig active-player fallback (§3.1.4); T-G5 elo/ab_duel set-plumb (touches pilot payload `ab_duel.py` — NO before 23:59 window); name-ask lane redesign; §4 timeout=loss; primer pool-scoping.
