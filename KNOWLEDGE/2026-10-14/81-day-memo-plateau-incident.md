# 81 — Day memo: plateau mapped (volume/tokens dead), frontier = parity, box-OOM incident + fixes, one compliant pilot crawling

Date: 2026-10-14 (owner recovery prompts; killed twice by OOM events, second one MY fault -> P0 laws active).
## Results today (all committed)
1. bshb (5.9x live shadow data): teacher 0.3594 / mirror 0.4821 -> VOLUME LAW NEGATIVE (/80): more live clones don't move the 0.37-0.43 band.
2. Digit-cure finals (/78): ntk_scratch 0.4308 (band-top, not decisive), transplant 0.3814 -> TOKENS NOT BINDING either. NUMTOK stays env-gated OFF (byte-identical legacy gates).
3. Frontier battle 400g: bsh_S3a_s1 vs bc9 champ 0.4649 [.416,.515] = PARITY (champion era retired; clones are same-class with clean vocab: live-UNK 0.0007).
4. Batched CUDA rollout inference + failed_games surfacing + zero-game-tolerant aggregate: 36 tests green, committed (3e707da + guards).
## The incident (own it)
18:19 launched 6-worker cuda gen_games -> ~10 GiB free exhausted by 6 CUDA contexts+caches (uncharged to cgroups) -> kernel OOM killed my process + tmux scope, gateway breaker tripped. Owner laws now in PITFALLS P0: per-process fraction caps, systemd-run MemoryMax scopes on every job, never N CUDA workers behind the engine. Fixed in code (worker fraction guard + parent margin precheck) before relaunch; compliant 1-worker scoped pilot relaunched 23:5x.
## State of the plateau (what would break it)
Imitation ceiling ~ greedy-teacher level by construction; volume and tokenizer ruled out with numbers; capacity (S4 35M) UNTESTABLE engine-on (GPU law) -> needs owner engine-down window. Last untested lever = BETTER-THAN-EXPERT LABELS: on-policy search improvements (adv_mix). Mini-pilot (6 games, 43 min/game under contention) lands tonight; if share(adv_mix>0.1) is real -> improvement-learner build; if ~0 -> imitation/search-shaping is exhausted and RL-from-outcome or capacity are the owner's Type-1 fork.
## Asks for owner
(a) engine-down window (2-3 h) for the S4 capacity test on shadow data; (b) ZNR verified source still pending; (c) pilot verdict will propose either improvement-label wave (cheap) or the RL/capacity fork (expensive) — no irreversible moves before then.
