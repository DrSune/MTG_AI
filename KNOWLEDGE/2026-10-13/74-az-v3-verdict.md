# 74 — AZ-v3 verdict: 3-generation iterative loop MATCHES the head, does NOT beat the one-shot bar (0.3093 vs 0.3927); line parked per stop-rule

Date: 2026-10-13 02:47. Chain (healthy head bc10_S3a_s1, gate 0.3118@100g): G1 0.3438 ADOPT | G2 0.2857/0.2784 KEEP-parent | G3 0.2245/0.2577 KEEP-parent.
FINAL (azg1, 200g each): vs teacher 0.3093; vs bc10_S4_s2 0.5294; vs bc9_S3_s1 (the one-shot bar net) 0.4346 — the best AZ child LOSES the direct duel to the one-shot net.
Stop rule (/72): 3 generations failed to clear 0.3927 -> PARK the line as implemented.

## What the whole AZ arc (67-74) established, all executed evidence:
1. Infrastructure wins: fork 6 ms, rollout 58 s/game, GPU distill 2 min/epoch, WR-gated driver, checkpoint admission probes (three laws born).
2. Negative results (each 200g-grade): one-shot distill mix 0.179, search-only 0.223, iterative-best 0.309 — ALL below one-shot BC (0.39). Iteration is NOT compounding at k<=4/N<=10, greedy/random rollouts, cap<=40.
3. Degeneracy classes discovered: argmin-0 collapse checkpoints that PASS the acc gate (hidden-variance law); warm-start inherits collapse (head probe law).
4. Puzzle acc and gameplay WR formally diverge (v5 0.839/0.31; v6 0.905/0.18).
5. Value signal quality is the binding constraint: visit distributions from cheap playouts rank MTG plans no better than the net's own policy (G1 gain = noise; G2/G3 regressions).
## If resumed (owner decision — the "bigger world" of /67):
(a) N-simulations law: AlphaZero-class needs >=50-100x current rollout budget OR (b) learned value head + PUCT deeper search (engine fork cost is no longer the bottleneck; rollout policy speed is — net-rollouts on GPU), or (c) full-BPTT rollouts (owner's maximal world). All three are weeks, not nights. Meanwhile the ONE-SHOT BC line (0.3927) remains the gameplay frontier and the recommended base for new data-collection ideas.
