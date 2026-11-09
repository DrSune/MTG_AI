# Fresh-Eyes Architectural & Algorithmic Analysis (`gemini_analysis.md`)

*Date: 2026-11-09*  
*Author: Gemini (Pair-programming assistant)*  
*Audience: Claude Opus, Frederik Sunesen, and the MTG_AI core engineering team*

---

## Executive Summary

This document presents an independent, fresh-eyes technical analysis of the MTG_AI self-play training pipeline, rules engine integration, and learning dynamics. While the engineering rigor, testing discipline (5,091 core tests, zero xfails), and adherence to Magic CR rules are world-class, our analysis reveals **several latent structural bottlenecks and algorithmic discrepancies**—most notably a fundamental tension between the theoretical derivation of $B^*$ and how minibatches are processed in `ppo.py`.

---

## 1. The Core Theoretical Vulnerability: The $B^*$ Minibatch Decoupling

### The Premise
The PPO audit ([KNOWLEDGE /184 §25-§26](file:///home/sune/Desktop/MTG_AI/KNOWLEDGE/2026-11-05/184-bug-hunt-verified-pool-cleanup.md#L476-L525)) demonstrated that at batch sizes of 98,304 decisions, the policy gradient is $>99\%$ noise ($\lambda = 1$), resulting in an Adam random walk. The audit derived $B^* \ge 2.65\text{M}$ as the critical batch size where gradient signal equals noise ($\text{SNR} \ge 1$).

### The Implementation Gap in `tools/selfplay/ppo.py`
In `ppo.py:84-122`:
```python
for step, (b, act_t, old_logp, A, R, V0, lp0) in enumerate(batches):
    ...
    loss = pg + a.vcoef * vloss - a.ent * ent.mean()
    loss = loss * (len(act_t) * len(batches) / max(n, 1))
    ...
    if a.target_kl > 0 and kl_upd > 1.5 * a.target_kl:
        stop = True
        break
    opt.zero_grad(set_to_none=True)
    loss.backward()
    gn = torch.nn.utils.clip_grad_norm_(model.parameters(), a.max_grad)
    opt.step()
```

1. **Minibatch Stepping vs Batch Stepping**:
   `opt.step()` is executed **inside the minibatch loop** on every single chunk of `mb = 4096` decisions. At 4,096 decisions, the signal-to-noise ratio is virtually zero. Adam is taking ~650 individual optimization steps sequentially on noise-dominated micro-slices.
2. **Adam Scale-Invariance**:
   Rescaling `loss = loss * (len(act_t) * len(batches) / max(n, 1))` scales the magnitude of the gradient $g$, but Adam's update $\Delta \theta = -\alpha \frac{\hat{m}}{\sqrt{\hat{v}} + \epsilon}$ is mathematically invariant to constant scale factors on $g$. It does not transform a noisy 4k minibatch gradient into a $B^*$-quality gradient.
3. **The Early-Stop Truncation Trap**:
   `kl_upd` measures policy drift from the start of the update. Because Adam updates weights across 650 sequential minibatches, `kl_upd` steadily climbs. If it exceeds $1.5 \times \text{target\_kl} = 0.045$ around minibatch 50 or 100, `stop = True; break` fires!
   **Consequence**: The update terminates early, discarding the remaining 550+ minibatches (~2.2 million decisions) without computing a gradient on them. The run would only train on a small fraction of the collected data.

### Recommendation for Opus
- Implement **Gradient Accumulation**: Accumulate gradients across all minibatches in the 2.65M batch before calling `opt.step()`.
- Or adjust the optimizer to perform one (or a few) aggregated steps per iteration so the effective batch size of the optimization step actually equals $B^*$.

---

## 2. Unified Memory Footprint: Pre-Collation Allocation Spike

### The Mechanism
In `tools/selfplay/ppo.py:62-78`:
```python
batches = []
for ch in chunks(packed.lengths(), a.mb, a.tok_budget):
    b = M.collate_packed(packed, ch, device)
    ...
    batches.append((b, act_t, old_logp, A, R, V0, lp0))
```

### The Issue
- `b` consists of padded CUDA tensors.
- When `n = 2,650,000`, there are $\approx 650$ minibatches.
- Pre-collating all 650 minibatches upfront onto the CUDA device creates a massive list holding **10 to 13 GiB of active GPU tensors** simultaneously in unified memory.
- Under `--epochs 1`, batches are never reused; they are consumed sequentially once and discarded.
- While the DGX Spark currently has ~65–75 GiB available, if another workload runs or if host memory drops to the 15–20 GiB range (e.g. resident vLLM), pre-collating 13 GiB will immediately trigger `MemoryError` or trip the `--mem-floor-gib 15.0` circuit breaker.

### Recommendation for Opus
- Collate minibatches **on-the-fly** (streaming generator) during the epoch rather than pre-materializing all 650 minibatches in memory before training starts.

---

## 3. Decision-Time Search: The "Crippled Opponent" Assumption

### The Mechanism
In `tools/selfplay/search.py:80-97` (`determinize`):
```python
pool = supply.deckable
for zone in (ZONE_HAND, ZONE_LIBRARY):
    for h in world.players[opp].zone(zone).entries:
        oid = pool[rng.randrange(len(pool))]
        ...
```

### The Issue
- In training, deals are **coherent 2-color decks** (`--coherent-share 1.0`).
- However, `determinize()` draws cards uniformly at random from the entire 5-color `supply.deckable` pool.
- As logged in `docs/BACKLOG.md`: the simulated opponent holds **54–61% off-color uncastable spells** and only **6–10% lands** (true deck has ~38% lands).
- Search evaluates candidate moves against an opponent who is severely mana-screwed and holding dead cards. This biases the network toward reckless aggression (it assumes the opponent rarely has answers or counterplay).

### Recommendation for Opus
- Transition search to Phase 2 (E2): replace uniform `determinize()` with beliefs sampled from the newly trained and validated opponent simulator (`simulator.py`).

---

## 4. Value Function Bias: Negative Effects of `vclip`

### The Mechanism
In `tools/selfplay/ppo.py:96-97`:
```python
v_clip = V0 + (v - V0).clamp(-a.vclip, a.vclip)
vloss = torch.max((v - R) ** 2, (v_clip - R) ** 2).mean()
```

### The Issue
- Value clipping (`vclip = 0.5`) was adopted from early PPO baselines. Extensive empirical literature (Engstrom et al., 2020; Andrychowicz et al., 2021) has demonstrated that value clipping introduces severe estimation bias and degrades critic accuracy, especially in sparse-reward environments.
- In terminal-reward games ($R \in \{-1, +1\}$), if $V_0 \approx 0$ and $R = 1$, clamping $|v - V_0| \le 0.5$ forces $v_{clip} \le 0.5$, penalizing the critic for correctly predicting a decisive win or loss.

### Recommendation for Opus
- Set `vclip` to a very large number (or remove the clamp) to allow the value head to fit unbiased Monte-Carlo returns.

---

## 5. Draw Reward Asymmetry in Zero-Sum Games

### The Mechanism
In `tools/selfplay/learner.py:625-627`:
```python
if outcome in ("draw-cap", "draw-stall", "draw-other"):
    return self.args.draw_reward  # default -1.0
return 0.0  # draw-mutual
```

### The Issue
- When a game hits the turn cap (60 turns) or stall detector (3 identical rounds), both seats receive $-1.0$.
- While designed to prevent stalling loops, it creates a game-theoretic distortion:
  If a player is in a lost position ($V \approx -0.95$), fighting for a draw yields $-1.0$, which is algebraically identical to (or worse than) losing.
- The policy is actively disincentivized from executing defensive stabilization lines when behind.

### Recommendation for Opus
- Consider setting `draw_reward` to a small negative value (e.g., $-0.1$ or $-0.2$) or $0.0$, preserving zero-sum symmetry while remaining strictly worse than a win ($+1.0$) and strictly better than a loss ($-1.0$).

---

## 6. Live Metrics Blind Spot in `learner.py`

### The Issue
In `learner.py:529-531`:
```python
self.log({"event": "progress", "phase": self.phase, "it": self.it,
          "bc_done": self.bc_done, "bc_target": self.bc_target,
          "mem_gib": round(mem_available_gib(), 1)})
```
During the PPO self-play collection phase (which now lasts 35–45 minutes for 2.65M steps), the 5-minute progress tick logs `bc_done: 0, bc_target: 0`. It does not report:
- `buffer_steps = len(self.buffer)`
- `target_steps = self.args.steps`
- `dec_s` (live decision throughput)

This leaves operators and monitoring daemons blind to generation progress between updates.

### Recommendation for Opus
- Append `"buffer": len(self.buffer)` and `"target": self.args.steps` to the progress event payload.

---

## 7. Scaling Bottlenecks for the King Goal (Commander)

1. **Entity and Option Clamping**:
   - `MAX_OPTIONS = 64`, `MAX_CARDS = 112`, `GRAVE_KEEP = 16`, `EXILE_KEEP = 10`.
   - In 4-player Commander with 100-card singleton decks and token generation, board states regularly exceed 150+ cards and graveyards exceed 40+ cards.
   - Any ask exceeding 64 options currently falls back to `HeuristicAgent` and is **dropped from training** (`overflow`).
2. **Sequential Python Engine**:
   - While baton passing across 18 workers yields ~1,200 dec/s, Python rules execution in `MTG_bot/core` remains the long-term throughput ceiling.
