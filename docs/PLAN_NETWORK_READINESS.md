# Plan: the network's readiness for the multi-day run (draft for the red team, 2026-11-18)

**Status.** A plan, not built. It covers the five network-side items of
[`PLAN_LONG_RUN.md`](PLAN_LONG_RUN.md) (tier 1 items 2 and 5, tier 2 items 6-8): the value function,
decisions of nothing, the observation gaps, memory of hidden cards, and the optimizer's state on a
resume. A red team reviews it next; then implementation (the owner's order, PLAN_LONG_RUN "The
order the owner set").

**The owner's orders it follows (2026-11-18).**
- "Use field expert methods, techniques, strategies and frameworks to do it best possible. Check
  the soundness of logic before making a plan."
- "No rushing to conclusions or going into patchwork-developing styles."
- Three standing rules (via the coordinator):
  - every method taken from the literature carries an assumption-transfer check;
  - every edit says why;
  - every conclusion lists the assumptions behind it, the owner's and mine, and what changes if
    each is wrong (§7 collects them).

**Evidence produced for this plan** (`reports/network_readiness_2026-11-18/`, CPU only):
- `meaningless.py` + `summarise.py` + `examples.py`: a detector of decisions of nothing, run on 150
  self-play games of r29's b100 (`runs/r29_ab/b100.pt`, sha256 29311738…; outputs `out_{a,b,c}*.jsonl.gz`,
  tables `tables.txt`). The same games give the value's explained variance and calibration by
  turn, and how often each observation gap and each kind of knowledge occurs.
- `inspect_game.py` replays one detector game exactly, to read a decision by hand.
- `census.py` → `census.txt`: which verified cards of M21, M20 and FDN reach each gap and each
  kind of knowledge.
- `params.py`: the network's size (28,070,402 parameters: d 512, 8 layers, ff 2048).

**How each part is laid out.** (1) the problem, measured; (2) the methods considered, each with
its assumption-transfer check; (3) the design: files, data flow, flags whose defaults keep
today's behaviour, tests that fail on today's code, metrics; (4) the logic check against the
project's goals; (5) the registered experiment, or why none is needed; (6) the order, and the
interfaces shared with the planner v1 build.

## Summary for the owner

1. **The value function (§1).**
   - **Logic first.** With γ = λ = 1 the value is only the baseline of `z − V(s)`, so it cannot
     bias what the policy learns. Its errors in the combat puzzles do not cause the bad blocks:
     both heads read one trunk that does not compute lethal damage. A better value changes
     learning in three ways only:
     - less variance;
     - a trunk not pulled by the value's noisy targets;
     - better leaves for the search and the planner's style critic later.
   - **New measurement.** In turns 1-6 (12% of decisions) the value explains almost none of the
     result: EV 0.00-0.03, standard error 0.05-0.07.
     - It is overconfident. Its calibration slope is 0.52-0.65 (standard error about 0.2), so a
       calibrated value would read about half as far from 0. |v| averages 0.25-0.34.
     - From turn 10 it is close to calibrated: slope 0.86-0.93.
   - **The candidate.** One package:
     - a value branch with its own two layers, which sends no gradient into the policy's trunk;
     - a cross-entropy loss on the win probability instead of mean squared error through tanh.
       Tanh's gradient vanishes exactly where the value is confidently wrong, as in C2.
     - It is function-preserving at the switch.
   - **Kept out of the A/B: a baseline scaled per turn by the previous batch's calibration slope.**
     It is exactly unbiased. It is logged in both arms, and adopted on its logged variance gain.
   - **The test.**
     - **First, a 40-minute GPU probe at B8's pause, which needs no new code.** It re-measures on
       today's network whether the value's share of an update dilutes the policy's learning.
       If it does not, the branch is not built.
     - **Then one registered A/B,** 11 machine-hours per arm, at the start of the FDN segment.
       If the build misses that slot, it becomes an arm of the planning A/B, sharing its control.
2. **Decisions of nothing (§2).**
   - **Measured** (150 games, a fork per option):
     - 0.69 decisions of nothing a game (0.36% of decisions). 58 of the 61 trigger-order asks are
       among them, 27 exactly so (copies of one ability of one source);
     - 12.7 single-pick decisions a game with redundant options, mostly copies of a card (6.6% of
       decisions, 20.9 redundant options a game).
   - **Four exact fixes:**
     - interchangeable triggers share one option, and need no ask when all are alike;
     - Duress's ask shows each card once, and the engine's replay contract stays;
     - copies of a card are one option, with a rules-exact class key that the detector validates;
     - a may whose action can do nothing is not offered.
   - Three need no strength A/B: they lose nothing by construction, which tests prove. The copies
     fix shifts an old network's prior, and that shift is measured before it ships.
   - **Honest size.** At 0.36% of decisions, removing decisions of nothing buys little stability
     today. The fixes earn their place by being exact and cheap. In Commander, where order asks
     grow with the board, they buy more. The copies fix touches more: 6.6% of decisions.
3. **Observation gaps (§3).**
   - **Triaged by reach** in the verified pools and by measured frequency.
   - **One schema for the long run:**
     - zero-initialised columns and pointers wherever possible, so an old network computes what
       it did, to float precision;
     - new entities only where nothing else carries the fact, with their disruption measured.
   - **Coordinated with the planner build** (`C_PLAN_*` columns) and the turn-so-far columns.
     **One rule:** every column exists from the long run's start, and flags decide which are
     filled.
4. **Memory (§4).**
   - **What it records.** What each player has legitimately seen in hidden zones:
     - a revealed hand card, counted by name;
     - a card returned to a hand from a public zone;
     - a card put at a known place in a library, until a shuffle;
     - one's own scried cards.
   - **How it is kept.** A journal-fed tracker in the engine. It needs four journal fixes first,
     because the journal is not yet a record of what players know (BACKLOG).
   - **How the network sees it.** Flagged entities, with their invariants tested.
5. **The optimizer's state (§5).**
   - AdamW's moments (214 MiB) and the trainer's minibatch generator are committed with `last.pt`
     and restored on a resume.
   - A test proves an interrupted run trains bitwise like an uninterrupted one.

## 0. The learner these checks are made against ("here")

Every assumption-transfer check below compares a method's setting with this one:
- **Reward and credit.** ±1 at the game's end, −1 for both on a turn-cap or stall draw.
  γ = λ = 1, so `gae` (`tools/selfplay/learner.py:254-267`) gives `A_t = z − V(s_t)` and the return
  of every decision is `z`. No bootstrapped target reaches the learner (the owner, OWNER_VISION §1).
- **Horizon.** About 94 learner decisions per seat a game: r29b's batches hold about 139,400
  decisions from about 1,480 learner seats (iter rows 165-174, `runs/selfplay/r29b_pself055`).
  Games run about 21 turns.
- **The network.**
  - One transformer trunk, 28.07M parameters: d 512, 8 layers, ff 2048, 25.2M of them in the
    encoder (`params.py` on b100).
  - It reads a variable set of tokens: global, two players, every visible card, every option
    (`tools/selfplay/model.py:135-184`).
  - The policy is a pointer head on the option tokens. The value is `tanh` of a head on the
    global token (`model.py:75-76, 180-182`).
- **The update.** PPO, 1 epoch, about 53 optimizer steps an update, lr 2e-5, AdamW betas
  (0.9, 0.99) (`trainer.py:44-45`).
  - The loss is `pg + 0.5 · max(MSE, clipped MSE) − 0.004 · H` (`ppo.py:165-168`), with value
    clipping at 0.5.
  - Advantages are normalised per batch (`ppo.py:112`).
- **The machine.** One GPU, one job at a time. r29b is train-bound: about 160 s an update, about 20
  updates a machine-hour.
- **The game.** Hidden hands and libraries. Self-play with a league of frozen versions and the
  heuristic.

## 1. The value function

### 1.1 The problem, measured

- **M1. The value term moves the policy** (KNOWLEDGE/2026-11-10/189 §8, r25's v0, one update on
  52k decisions).
  - The value term alone moved the policy by KL 0.0021 and changed its top choice in 0.92% of
    decisions; the full update by 0.0026 and 1.00%.
  - The value term alone raised entropy (+0.0029); the policy term alone lowered it (−0.0047).
  - At value coefficient 0.05 the value fitted as well (EV 0.439 against 0.442), and the policy
    moved by KL 0.0029.
  - Measured on r25's v0: 27.25M parameters, today's architecture. It is about 2,000 updates of
    training older than today's network (r26 → r27 → r28's v2 → r29), and has not been re-measured
    since.
- **M2. The value's fit today.** r29b's iter rows 165-174: EV 0.25-0.37 on each batch, value loss
  about 0.53.
- **M3. The value by game phase (new, §2's games of b100).** Each seat's own value against its own
  result, decisive games only. c is `Cov(z, v) / Var(v)`, the slope a calibrated value would show
  as 1. The last column is the EV of the baseline `c · v` (§1.3 g).

  150 games, 28,837 decisions. The standard errors resample whole games, since a game's decisions
  share its result.

  | Turns | Decisions | EV (se) | mean \|v\| | Brier, (v+1)/2 | c (se) | EV of c · v |
  |---|---|---|---|---|---|---|
  | 1-2 | 1,019 | 0.031 (0.046) | 0.253 | 0.241 | 0.65 (0.22) | 0.044 |
  | 3-4 | 905 | 0.004 (0.069) | 0.313 | 0.250 | 0.52 (0.25) | 0.037 |
  | 5-6 | 1,577 | 0.008 (0.062) | 0.335 | 0.250 | 0.53 (0.19) | 0.045 |
  | 7-9 | 3,340 | 0.127 (0.065) | 0.444 | 0.223 | 0.75 (0.12) | 0.143 |
  | 10-14 | 7,332 | 0.313 (0.062) | 0.597 | 0.174 | 0.86 (0.06) | 0.321 |
  | 15+ | 14,664 | 0.539 (0.067) | 0.742 | 0.115 | 0.93 (0.05) | 0.542 |
  | all | 28,837 | 0.369 | | | | |

  - **Early, the value carries almost no information and reads as if it did.**
    - In turns 1-6 its EV is 0.00-0.03, within noise of a constant. A constant 0.5 gives a Brier
      score of 0.25, and these read 0.24-0.25.
    - Its readings are about twice as far from 0 as a calibrated value's would be: c 0.52-0.65,
      about two standard errors below 1.
  - **The cost is small, and it falls on the earliest decisions.** The best scaled baseline would
    explain 0.04 instead of 0.00-0.03, on 12% of decisions. This is in-sample, so an upper bound.
  - **Late it is close to calibrated:** c is 0.86-0.93 from turn 10.
  - **A correction to a first reading.** A first look at 67 games read the early EV as negative
    (−0.05 to −0.12). The full 150 games put it at 0.00-0.03, so the claim "worse than a constant"
    is withdrawn.
  - **Not tanh saturation.** At |v| ≈ 0.3, tanh's gradient factor `1 − v²` is 0.91. Both losses
    share the optimum `E[z | s]`, so the early overconfidence is noise the value fits from batch to
    batch, not the loss's shape.
    - Cross-entropy (§1.3 e) answers the late, confident errors, as in C2.
    - The early cost is answered by the baseline's coefficient (§1.3 g).
- **M4. The value in the combat puzzles** (KNOWLEDGE/2026-11-18/214 §4.2).
  - It orders C1's twins by 0.06-0.14 and C2's by 0.01-0.03.
  - It reads 0.88-0.98 in C2's twin where its own move, not blocking, loses on the spot.
- **M5. Capacity is not what limits the value's fit:** a deeper or wider network fits r27's
  value no better (KNOWLEDGE/2026-11-12/194).
- **M6. The plateau.**
  - r28 was flat after update 1000 (199 §9).
  - Neither r29 arm moved off its init in 5.5 machine-hours (208 §11).
  - The per-kind split at r28's update 685 shows every kind moving along its own advantages, with
    small alignments (+0.002 to +0.022) and nothing drifting between kinds (199 §8).

### 1.2 Logic first: what can a different value change here?

- **The baseline cannot bias the gradient.** `E[∇ log π(a|s) · V(s)] = 0`, since `V(s)` does not
  depend on the action. So under γ = λ = 1:
  - a value error at a position does not steer the policy's choice there;
  - errors do not propagate to other decisions' advantages, as no target bootstraps from V.
- **What the combat puzzles say.** 214 frames the C failures as value errors. That is half right.
  - The value misreads C2.
  - But the policy's choice there (no block, p 0.69-1.00) is learned from `z` alone, whatever V
    says.
  - Both heads read one trunk that does not compute "incoming damage ≥ my life". The missing
    piece is a feature, and the value is one more symptom of it. A loss or architecture that only
    makes V more accurate cannot fix the policy's blocks.
  - What can is a trunk that computes the feature: short-horizon auxiliary targets (§1.3 f), the
    puzzle starts of PLAN_PLANNING P2, or more signal.
- **The three channels through which the value does change learning:**
  1. **Variance.**
     - `Var(A) = (1 − EV) · Var(z)` over the batch. At EV 0.33, a gain of 0.10 cuts the variance
       by 15%, worth at most about 15% fewer games for the same signal.
     - Where EV ≈ 0 (turns 1-6, M3), the baseline buys nothing, and its overconfidence leaves a
       little on the table.
     - PPO's per-batch normalisation and the clip's sign also read V. Both effects are second
       order.
  2. **The trunk.**
     - The value loss's gradient shapes the shared features. That can help: board understanding
       learned from outcomes is PPG's and KataGo's premise.
     - It can also drift the policy (M1). Which dominates at a plateau is not known; §1.6 measures
       it.
  3. **Later uses.** The search's leaves (P3) and the planner's style critic (DESIGN_PLANNER v2)
     need a value that is tactically accurate. C2's 0.9 in a lost position would mislead a
     searcher at its horizon.

### 1.3 Methods considered, each with its assumption-transfer check

**(a) Separate policy and value networks.**
- **The evidence.**
  - Andrychowicz et al. 2021 found separate networks better on MuJoCo control.
  - Raileanu and Fergus 2021 (IDAAC) found that a shared trunk on Procgen fits level-specific
    detail for the value, which hurts the policy on unseen levels. Decoupling, plus a head that
    predicts advantages, improved generalisation.

| Their assumption | Here | What changes |
|---|---|---|
| Value targets bootstrapped (GAE λ 0.95, γ 0.99-0.999), so value errors bias the advantage | Monte-Carlo targets; value errors only add variance (§1.2) | Decoupling's benefit through value accuracy is smaller here; its benefit through interference stays |
| Small MLPs or CNNs; a second network is cheap | A 25.2M-parameter encoder; a second one doubles compute in a train-bound run | Not a second network: a branch (b) |
| Dense rewards, short episodes | One terminal ±1 over about 94 decisions; z given s keeps about 2/3 of its variance (EV about 0.33) | The value's per-sample gradient is mostly noise here, so the interference may cost more than in their dense tasks |
| Generalisation across procedurally generated levels | Generalisation across fresh deals and unseen cards (a King goal) | Holds: the argument that value gradients memorise deal detail into the policy's features transfers |

- **Conclusion.** Isolate the value from the policy's trunk cheaply (b), and measure. Expect no
  large change in EV.

**(b) A critic on stop-gradient features, with its own layers (a value branch).**
- **What it is.** The single-network form of (a). The value reads the trunk's features through a
  stop-gradient and owns the last K layers of its path.
- **Its assumption:** the features reaching the branch still carry the value's information.
  - At the switch they do: the trunk has been trained with the value through all of its lineage.
  - Over a long run the shared layers drift toward policy-only features. The branch's own K layers
    and the EV-by-turn monitor answer that (§1.5, W2).
- **K = 2 of 8.** It keeps the value's last two layers free to adapt. Inference cost: +25% when
  the value is asked for.

**(c) Phasic Policy Gradient (PPG; Cobbe et al. 2021).**
- **What it is.**
  - Separate policy and value networks.
  - A policy phase of N_π = 32 iterations, then an auxiliary phase of E_aux = 6 epochs over those
    iterations' data. It trains the value network, and distils the value into an auxiliary head
    of the policy network under a behaviour-cloning penalty KL(π_old ‖ π) with β = 1.
  - Shown on Procgen (16 games, 100M frames each, γ 0.999, λ 0.95), with large gains in sample
    efficiency. Most of the gain is the policy network's features learned from the value.

| Its assumption | Here | What changes |
|---|---|---|
| Compute for an auxiliary phase about six times the policy phase's | Train-bound (208 §1: arm B at about 826 trained rows a second) | As published it would cut updates per machine-hour several-fold. A scaled form (N_π 8, E_aux 1) still doubles the trainer's work |
| Memory for 32 batches | 32 × 139k decisions, about 4.5M, tens of GB packed beside a 15 GiB floor | Fits only scaled down |
| The value's features help the policy's (pixels → objects) | Unknown here: M1 shows that the value moves the policy, not that it helps | It becomes the experiment's open branch |
| GAE advantages, so the value's accuracy matters for the policy's targets | Monte-Carlo advantages | Less to gain from a better value |

- **Conclusion.** Not first. If the A/B shows that detaching the value hurts the policy (the
  value's shaping was useful), PPG-lite is the registered next variant: the trunk learns from the
  value only under the clone penalty.

**(d) Tuning the value coefficient.**
- **What it is.** Andrychowicz et al. 2021 and common practice treat the value loss's weight as a
  knob.
- **Its assumption:** the shared parameters' step is a mix weighted by each loss's scale.
  - Under Adam, which normalises each parameter by the running RMS of its total gradient, this
    holds for the shared parameters. The value head's own parameters learn at about the same speed
    whatever the weight (189 §8 E: EV 0.439 at 0.05 against 0.442 at 0.5).
- **Conclusion.** A partial isolation that keeps a tenth of the value's pull. It goes into the
  code-free probe of §1.6 as a variant, not into a training arm.

**(e) Cross-entropy on the win probability instead of MSE through tanh.**
- **The precedents.** AlphaZero trains `tanh` with MSE (Silver et al. 2018). KataGo trains
  win/loss/draw with cross-entropy (Wu 2019).
- **The logic.**
  - MSE's gradient with respect to the pre-tanh output x is `2(v − z)(1 − v²)`, which vanishes as
    |v| → 1.
  - A confidently wrong value gets the smallest correction. At v = 0.9 and 0.96 with z = −1 it is
    0.72 and 0.31. Cross-entropy on `σ(2x)` gives 1.9 and 1.96 (`∂/∂x = 2(σ(2x) − y)`): 3-6 times
    more.
  - Both are proper scoring rules (Brier and log loss). Cross-entropy punishes overconfidence
    harder, and overconfidence is M3's failure.
  - Since `tanh(x) = 2σ(2x) − 1`, the switch changes no output at load.

| Its assumption | Here | What changes |
|---|---|---|
| The target is a binary outcome | z ±1, draws −1 for both (0.18% of r29's games), mutual 0, and a void game targets its last value | A soft label `y = (z + 1) / 2` covers all of them |
| No bootstrapping, so the minimiser is the win probability under the policy | Holds | none |
| Value clipping (PPO2's vclip) | Has no cross-entropy analogue; Andrychowicz et al. found it no help | Dropped with this loss (§8 lists it) |

- **Conclusion.** In the treatment, with the branch.

**(f) Auxiliary Monte-Carlo targets.**
- **The evidence.**
  - KataGo's auxiliary targets (ownership, score) densify the signal without changing the reward
    (OWNER_VISION §9).
  - UNREAL's auxiliary tasks (Jaderberg et al. 2017).
- **The candidates here.** Each is an observed fact of the seat's own game, read from its
  trajectory, with no bootstrapping and no change to the reward:
  - a1, my life at my next turn's first decision minus my life now;
  - a2, the opponent's life at the same moment minus now;
  - a3, the game ends before my next turn: I lose, I win, or neither.

| Their assumption | Here | What changes |
|---|---|---|
| Full information; per-point targets on a fixed board | Hidden hands; per-seat targets on a variable token set | The targets carry the opponent's hidden cards as noise, not bias. They are read off the seat's own records (`players_f` at its next turn's first decision) |
| Targets shape the shared trunk | Shaping is what §1.2's channel 2 questions | On the branch they improve only the value. On the trunk they teach the policy lethal arithmetic (the C failures) but pull the trunk |

- **Conclusion.** Designed here, built after the A/B, each placement as its own arm.
  - On the branch first: no risk to the policy; better leaves for the search.
  - On the trunk next: the KataGo bet. It is the same bet as the planner's hindsight heads, so it
    is read beside them.

**(g) The optimal baseline coefficient (control variates).**
- **What it is.** Greensmith, Bartlett and Baxter 2004 give the variance-optimal baseline. Within
  the family `c · V(s)`, per turn bucket b, it is `c_b = Cov(z, V) / Var(V)` over the batch. In
  the batch it never adds variance.
- **Its assumptions:**
  - The baseline may depend on the state, and the turn is in the state. Holds.
  - Batch-fitted coefficients add a bias of order 1/n. With about 139k decisions in about 1,480
    seats that is negligible, and it is the same assumption PPO's per-batch normalisation makes.
    Holds.
- **M3 says this is where the early cost lies, and that it is small.** c is 0.52-0.65 in turns
  1-6, and the scaled baseline's EV there is 0.037-0.045 against the raw value's 0.004-0.031, on 12%
  of decisions (in-sample).
- **The design.** `c_b` is fitted on the previous update's batch and applied to the current one, so
  the baseline does not depend on the outcomes it is subtracted from: exactly unbiased, at no
  compute cost.
- **Conclusion.** It changes the advantages, not the value, so it is kept out of the value A/B.
  - The A/B should change one thing at a time in what the policy learns from.
  - Both arms log, per update, the EV the raw and the scaled baselines give per bucket.
  - The long run adopts it (`--baseline-scale`, default off) if the scaled baseline's EV is at
    least the raw one's in every bucket over the A/B's last 50 updates, in both arms.
  - This is an unbiased variance reduction whose effect is measured on every batch, so no strength
    A/B is needed.

**Not taken:**
- a distributional or larger value network (M5: capacity is not the limit);
- λ < 1 or n-step targets (the owner: γ = λ = 1 stays);
- a privileged critic that sees hidden cards (dropped by the owner on 2026-11-06, OWNER_VISION
  and BACKLOG "Signal plan").

### 1.4 The design (the treatment)

**Flags.** Each default keeps today's behaviour.
- `--value-branch K` (default 0).
  - 0: the value head reads the trunk's output, as today.
  - K ≥ 1: the value reads the trunk's layer L − K through K layers of its own, then its own
    output norm and the value head.
  - Converting a network copies the trunk's last K layers and `out_norm` into the branch, so
    value and policy are unchanged at the switch (`model.with_value_branch`, below).
- `--value-detach` (default off): a stop-gradient where the branch reads the trunk. No value
  gradient reaches any parameter the policy uses.
- `--value-loss mse|bce` (default mse).
  - bce: `binary_cross_entropy_with_logits(2x, (z + 1) / 2)`, with x the value head's pre-tanh
    output and no value clipping.
  - mse: today's clipped loss (`ppo.py:166-167`).

**`tools/selfplay/model.py`** (the planner build is also changing this file: §6):
- config keys `value_branch` and `value_detach`, absent when off, so a network without them saves
  as today;
- `forward(b, ..., value_logit=False)`. The trunk runs its layers one at a time (it is
  `nn.TransformerEncoder` today), so the branch can read layer L − K. `value_logit=True` also
  returns x;
- `with_value_branch(net, K)` builds the branch from copies, as `grow` builds layers (`model.py:373`);
- `upgraded` needs no change: a converted network's checkpoint holds its branch.

**`tools/selfplay/ppo.py`:**
- the value term by `a.value_loss`;
- three new stats in the result:
  - `ev_turn`: EV per turn bucket, from `ret`, `v_old` and the turn (`glob_f[0] × 20`);
  - `c_turn`: §1.3 g's coefficient per bucket;
  - `vll_turn`: the value's log loss per bucket.
- The buckets are 1-2, 3-4, 5-6, 7-9, 10-14 and 15+ turns, a diagnostic only.

**`tools/selfplay/learner.py`:** the flags, passed to the trainer as today's are. `--init` with
`--value-branch` converts the network and logs the conversion.

**Not changed:**
- the actors: they record `v` as today;
- the search: it reads `forward`'s value;
- the trainer's optimizer: it covers every parameter.

**Inference cost.** When the value is asked for, the branch adds K/L of the trunk's forward work:
+25% at K = 2 of 8. Play without search does not ask for it. The GPU smoke measures rows a second.
If inference binds, the trainer can compute V for the batch instead: with γ = λ = 1 any function
of the state is a valid baseline.

**Tests that fail on today's code:**
1. A converted network gives bitwise the same logits and value on CPU over 2,000 recorded
   decisions. On today's code `with_value_branch` does not exist.
2. Running the layers one at a time equals `self.encoder(x)` bitwise, with the padding mask
   canonicalised as the encoder does it.
3. With `--value-detach`, an update whose policy term is zero (advantages 0, entropy coefficient
   0) leaves every parameter outside the branch bitwise unchanged. Today every trunk parameter
   moves (189 §8 D).
4. The bce term's gradient on x at v = 0.9, z = −1 is at least twice the mse term's.
5. `ev_turn` equals a hand computation on a toy batch.

### 1.5 The logic check

- **King.** It changes how the trunk learns and how much noise the advantages carry. Nothing
  strategic is added and no move is capped.
- **Learnable over hardcoded.** K = 2 is a hand-set capacity split, said aloud in §8, removable when
  EV at K = 1, 2 and 3 shows the knee. The turn buckets are a diagnostic, not a scaffold.
- **Generalisation through components.**
  - Detaching removes deal-specific value gradients from the component embeddings and the policy's
    features: IDAAC's argument for unseen levels, here for unseen cards.
  - The cost: the component embeddings no longer learn from outcomes directly, only through the
    policy (and the planner's heads).
- **Honesty.** The value reads the same visible features. Nothing hidden is read.
- **Commander.** The branch's cost grows with tokens, as the trunk's does.
- **Latency.** Zero without search. With search, +25% per leaf evaluation, not per playout step
  (playouts ask the policy).
- **What could go wrong, and why the design survives it:**

| # | Risk | Guard |
|---|---|---|
| W1 | The value's trunk shaping was useful, and detaching slows the policy | The harm screen (R1, R2). The registered response is PPG-lite, not a return to drift |
| W2 | The branch's value decays as the trunk drifts over days | `ev_turn` every update. The kill criterion. The responses are K = 3 or the auxiliary targets on the branch |
| W3 | Entropy falls faster: the value term raised entropy (189 §8 D), and its push leaves the trunk | R6 watches it. The bonus (0.004) was balanced with the value term present. Outside ±0.02 is a registered finding, and the response is 189 §8's re-measurement of the push, not a guessed bonus |
| W4 | Bundling detach and cross-entropy confounds attribution | Stage 0 (§1.6) separates their one-update effects. The A/B decides the package. If it is adopted, a later one-update ablation splits it at almost no cost |
| W5 | The planner's hindsight heads also pull the trunk, and both changes meet in the long run untested together | The pilot (PLAN_LONG_RUN step 6) runs the combination with its own harm screen |
| W6 | Cross-entropy on void games' soft labels | Labels in [0, 1]. Void games are rare (r29b: `voids` per update in the iter rows) |

### 1.6 The registered experiment

**Stage 0: the mechanism probe** (GPU, about 40 minutes with two collected batches, in B8's pause; no new code).
- **The setup.**
  - One batch from the main line's checkpoint at B8 (`learner --collect`, about 139k rows), and a
    held-out set of games the update never sees.
  - The probe is 189 §8's script (`reports/v0_probes_2026-11-10/ent_ablation.py`), brought to
    today's `ppo.steps` and network.
  - Each variant's AdamW is first warmed on an earlier batch of the same network. A fresh Adam's
    first steps are sign-like (§5.1). 189 §8's W controls found fresh and warm alike, but the probe
    should not depend on that.
- **One update per variant:**
  - A, today's loss; A2, the same in another minibatch order (the noise gauge);
  - G, the policy term alone (value coefficient 0): what a detached branch's trunk receives in one
    update;
  - D, the value term alone (advantages zero): 189's replication;
  - E, value coefficient 0.05.
- **Per variant:** KL(before ‖ after) and top-choice change on the held-out decisions, and per-kind
  alignment (`mean(A·Δlog p) / mean(A²)`, `reports/r28_2026-11-12/kinds_split.py`) per unit of
  mean |Δlog p|.
- **The registered rule.**
  - **The branch is built only if G's alignment per unit of movement exceeds A's by at least 20%
    in at least three of the five frequent kinds** (priority, act, attack, block, target), and A2
    differs from A by less than that.
  - Otherwise the value's share does not dilute the policy's learning on today's network. The
    A/B's treatment is then the cross-entropy loss alone, on the shared trunk.
- **Why it comes first.**
  - M1 is eight days and about 2,000 updates old.
  - Under Adam any single-loss update moves each coordinate by about lr, so D's KL alone (189's
    headline) does not show that the value term dilutes the policy's learning. A against G does: G
    is exactly what a detached trunk receives.

**Stage 1: the A/B.**
- **The arms.** C, the control: the main line as registered. V: `--value-branch 2 --value-detach
  --value-loss bce`, or the cross-entropy loss alone if stage 0 says so.
- **The setup.** Both from the same checkpoint and the same flags otherwise. Deals matched by
  `--seed`. C first, then V. One GPU job at a time.
- **The budget:** 11 machine-hours per arm, about 220 updates at r29b's rate. Snapshots at 70, 80,
  90 and 100% of the budget, by r29's machine-time rule (208 §1).

| # | Read | Band (prediction) | Falsifier |
|---|---|---|---|
| R1 | **Harm screen:** V against C head to head, 4 snapshot pairs, 1,000 fresh deals each, both seats, greedy (208's B1 method and interval) | 0.49-0.53 | upper bound below 0.50 |
| R2 | **L:** V's mean Elo minus C's over their 4 snapshots, rated on pool L (208's B2 method) | −5 to +15 | upper bound below 0 (a veto) |
| R3 | **The value:** `ev_turn` over each arm's last 50 updates | V ≥ C − 0.02 in every bucket holding at least 5% of decisions; V > C in turns 1-6 | V below C − 0.05 in any such bucket |
| R4 | **Drift:** directedness, the Hellinger displacement from the init over the path length through snapshots every 25 updates, on a fixed probe set of 20,000 held-out decisions from the init's games (CPU) | V > C | V < C − 0.05 |
| R4b | **Drift:** kinds_split on each arm's 100% snapshot, alignment per unit of movement | V ≥ C in at least three of the five frequent kinds | — |
| R5 | **The puzzles:** every category, both arms' 100% snapshots (`tools/puzzles/runner.py`) | no category's twin-consistent pass rate falls. The value's C-pair margins: V ≥ C, C2's at least 0.05 | a category falls by one pair or more |
| R6 | **Entropy:** the logged `ent` over the last 50 updates | V within ±0.02 of C | outside: a registered finding (W3) |

- **Kill V when:**
  - EV is below 0.20 for 10 consecutive updates (C runs about 0.33);
  - any update's `kl` exceeds 0.05;
  - a non-finite loss appears;
  - the run's standard guards fire (the mulligan at 1.80, the memory floor).
- **The decision, made mechanically:**
  - **Adopt V for the long run** if R1 and R2 are not falsified, R3 is not falsified, and R3 or R4
    favours V.
  - **"Favours" means beyond twice the read's own standard error.** For R3 that is the spread of
    the per-update `ev_turn` over the 50 updates. For R4 it is a bootstrap over the probe set's
    decisions.
  - **If R1 or R2 is falsified with R3 intact:** the value's shaping was useful. PPG-lite is
    registered next.
  - **If R3 is falsified:** K = 3, or the auxiliary targets on the branch, through stage 0 again.
  - **If nothing moves:** keep C. It is simpler.
- **Why "no harm, plus a mechanism" adopts.**
  - From a plateaued init, 11 hours cannot show a strength gain for either arm: neither r29 arm
    moved in 5.5 hours.
  - The long run is days, and the mechanism compounds there.
  - The red team should test this rule hardest.

**Where it goes in the GPU schedule.**
- **Stage 0:** in the pause at B8's read, tonight, before the FDN segment launches. It needs only
  the probe script.
- **Stage 1, preferred:** the FDN segment's first 22 machine-hours.
  - C is the FDN segment itself, so the A/B costs the schedule V's 11 hours.
  - The winner continues as the main line.
  - It needs the branch and the loss built, tested and GPU-smoked with the real flags by the
    launch.
- **Stage 1, fallback:** one more arm of the planning A/B from 2026-11-23, sharing its control
  (PLAN_PLANNING §6). The same reads, the same decision rule.

## 2. Decisions of nothing

The owner: important "for stability and such".
- **The cost of a decision of nothing.** All its options lead to one state, so `E[A | s, a] = 0`
  for every option: its rows carry no expected gradient, only variance, into the shared trunk.
- **They distort the per-kind statistics.** r29b's "trigger" kind has normalised entropy 0.727,
  near uniform, and the entropy bonus pushes it further.
- **They cost an inference each.**
- **In Commander they scale with the board.** Ten tokens entering under one "whenever a creature
  enters" permanent make ten interchangeable triggers, and today nine order asks.

### 2.1 The detector, and what it measured

**The method** (`reports/network_readiness_2026-11-18/meaningless.py`).
- **The games.** r29's b100 on both seats, sampling as training does: coherent decks, M21 with M20
  at 25%, the verified pool.
- **At every decision with two options or more,** each option is played once from a copy of the
  game:
  - **the copy:** taken at the last pause point, an `act` or `priority` ask, where no engine call
    is in flight (the planning solver's mechanism, `tools/puzzles/solver.py:159-224`). Both seats'
    answers since then are replayed;
  - **the option under test;**
  - **the null continuation:** both seats pass, and every other ask takes its canonically smallest
    option, until the first priority point with an empty stack;
  - **the signature taken there.** It is relabelling-invariant: every zone by oracle id, every
    permanent's live state, the stack, combat, the turn's counts, and the live layer, replacement
    and return rows. A library shuffled after the decision compares as a multiset, since a shuffle
    makes every order of the same cards equally likely.
- **Options with equal signatures form one state class.** The determinism check re-ran one option
  at every tenth tested decision: 2,789 re-runs, none differed.
- **A decision of nothing needs every option tested.** A big menu is sampled: 16 options, keeping
  every pair with equal tokens. A sample that lands in one class says nothing about the rest. One
  of Necromentia's 280 card names named nothing in the opponent's zones 16 times.
- **The instrument's own faults, found and fixed before the counted run** (each is in the script's
  history):
  - the encoding key left out the named card of a name option;
  - a tutor's picks were compared in library order before a shuffle;
  - a shuffle between the pause point and the decision made the library a multiset. That made
    seven scry decisions look like decisions of nothing. Shuffles now count only after the tested
    answer.
  - found after the counted run: the encoding key kept the options' entity positions, so two
    copies never shared a key. The "blind" count below comes from a separate 40-game run with the
    fixed key (`blind_d*`, `blind_tables.txt`). No other number used the key.
- **The counted run.** 150 games, three CPU processes at nice 19 beside r29, about 25 minutes.
- **A limit found by reading cases: declarations made of several asks.** The null continuation
  completes a declaration canonically, and breaks a tie between equal objects by their position.
  - Blocks are declared blocker by blocker. Two identical Goblin Wizards attacking: a first block
    on one or the other, then the second blocker's canonical pick (the first Wizard by position),
    ends in different block maps. The detector calls these different (`inspect_game.py`).
  - For picks that build a set (the "1 of 2" picks of a search, cleanup discards, divisions), the
    continuation completing the set can make different first picks equal.
  - So the counts for those asks are approximate in both directions. They are reported apart below
    as "set-building". The single-pick counts carry no such effect.

**The method's assumption-transfer check.** It is symmetry reduction: states equal up to a
permutation of identical objects, as in model checking (Ip and Dill 1996) and lossless abstraction
in imperfect-information games (Gilpin and Sandholm 2007).

| Its assumption | Here | What changes |
|---|---|---|
| A canonical form invariant to relabelling identical objects | Handles never enter the signature; objects are oracle ids plus live state | Holds |
| Equal canonical states have equal futures | The signature leaves out the journal beyond the turn's counts, and timestamps | Equal signatures are an upper bound on decisions of nothing. Different signatures are always different states. Each kind is read by hand (below) |
| Exhaustive successors | One successor per option, under the null continuation | Options equal under "nobody acts" may differ when a player acts between, e.g. two prowess triggers of two sources (below). The exact fixes use rules arguments, never the detector's word. The detector finds the candidates and validates the fixes |
| Determinism | The engine's randomness is keyed by (seed, operation count, tag) | Checked: 2,789 re-runs, none differed |

**The numbers.** 150 games, 28,837 decisions, 192 a game, both seats (§2.6 has the per-kind table).
- **Decisions of nothing (one state class, every option tested): 103, 0.69 a game, 0.36% of
  decisions.** By kind and cause, each read from its cards (`examples.txt`):
  - **the trigger order: 58, 0.39 a game.** That is 58 of the 61 trigger-order asks.
    - 27 of them are copies of one ability of one source, from different events (Watcher of the
      Spheres' case: `card:114`, `card:114:2`). Exactly a decision of nothing (F1).
    - 31 order triggers of different sources (two prowess triggers, Jeskai Elder and Shipwreck
      Dowser). They are equal only under the null continuation: which creature is pumped first is
      visible to a player who responds between the two. They are kept.
  - **a choice among copies only: 13, 0.09 a game.** Exact: F3 makes them one option, and no ask:
    - Cultivate's, Fierce Empath's or Cavalier of Thorns' pick between two Forests or two Chandra's
      Incinerators, followed by a shuffle;
    - Legion's Judgment between two Wardens of the Woods;
    - the legend rule between two equal copies.
  - **a may whose action can do nothing now: 15, 0.10 a game.**
    - Liliana's Scrounger with no Liliana, 12; Icon of Ancestry's reveal with no creature of the
      chosen type among the three, 2; Experimental Overload's return with no instant or sorcery in
      the graveyard, 1.
    - `query.optional_offer` narrows only exact-count selectors with no candidate
      (`query.py:591-623`).
    - Exact when the action's every object selection is empty (F4).
  - **equal outcomes in this state only: 17, 0.11 a game.** Real decisions that happen not to
    matter. They include five mays, of Tolarian Kraken and Goblin Arsonist, not traced one by one,
    and one scry:
    - Rabid Bite's or Garruk, Savage Herald's source among creatures of equal power whose target
      dies either way;
    - Manifold Key untapping an untapped artifact;
    - a division of damage whose amounts all kill the same blockers.

    Not fixed: no exact rule exists, and learning them is the network's work.
- **Redundant options (fewer state classes than options).**
  - **Single-pick asks: 1,902 decisions, 12.7 a game (6.6% of decisions); 3,142 options, 20.9 a
    game.** By kind:
    - act 1,159: copies of a land or a spell in hand;
    - priority 218;
    - target 166;
    - mulligan bottom 122;
    - one_of 71;
    - the trigger order 58;
    - choose 40: Duress's each card twice, and modal picks;
    - block 25;
    - may 20;
    - discard 17;
    - sacrifice 4.

    The decisions of nothing above are counted here too.
  - **Set-building asks: 183 decisions; 680 options.** These are the approximate ones above:
    division amounts past lethal, the picks of a search, cleanup discards.
- **Options the network cannot tell apart that lead to different states ("blind"): 23 decisions in
  the 40-game run with the corrected key, 0.58 a game.**
  - **The cases:** 16 cleanup discards, 2 in a "1 of 2" pick, 2 blocks, 2 legend-rule asks and 1
    act menu. 18 of the 23 are set-building asks.
  - **The traced block case is the continuation's tie-break, not the encoding** (above).
  - The two legend-rule asks and the act menu were not traced. Their options' own tokens are equal,
    and attention to context (an aura's pointer to its host, for one) may still separate them. They
    are upper bounds, and none points at a gap that §3's triage lacks.

### 2.2 The fixes, each exact

**F1. Interchangeable triggers share one option** (`MTG_bot/core/executor/binding.py:1556-1582`,
`_resolution_order`).
- **What changes.** Two firings of one controller are interchangeable when:
  - they share the source and the node;
  - and either they share the event, or the node never reads its event.
  - Today only "the same event" counts as interchangeable (`binding.py:1568`).
- **"Never reads its event"** is a static property of the node: no `event` referent anywhere in
  its tree, its intervening-if condition included, and no `gathered` objects
  (`_Firing.gathered`, `binding.py:311-324`). A reflexive firing's `carried` context makes it
  differ.
- **With every waiting firing of a controller interchangeable, nothing is asked.**
- **Why it is exact.**
  - CR 603.3b lets the controller order its triggers. Interchangeable firings resolve identically,
    and after either one resolves, the states are equal up to which of two identical abilities
    remains.
  - A target chosen as each goes on the stack follows the order, so any outcome of one order is
    reachable in the other by choosing the targets the other way around.
  - Firings of different sources are not merged: the state between their resolutions differs, and
    a player may act there.
- **Tests that fail on today's code.**
  1. Watcher of the Spheres with two fliers entering at once asks nothing. Today it asks
     `card:0` / `card:0:2`.
  2. Two Woodland Champion triggers from two events still ask: "that many" reads the event.
  3. **A property test over the verified pools.** For every triggered ability the scan calls
     event-blind, resolving it with its event replaced by a sentinel gives the same signature as
     with the real event. This guards the scan against an event read it misses.

**F2. Duress's ask shows each card once** (`verbs._v_choose`, `verbs.py:2145-2162`).
- **The engine keeps its vocabulary, both lanes.** r19c's replay contract stays, and so do the
  two unit tests and three packs pinned on the index lane (BACKLOG "Duress / Kitesail Freebooter's
  choose ask lists each card twice").
- **The change is in the protocol layer, for every agent** (the network, the heuristic, LLM
  seats). A `choose:` ask whose vocabulary is exactly the indices `0..k−1` followed by k handle
  tokens drops the indices (`MTG_bot/bench/protocol.py:176-288`, `engine_ask`).
  - The router answers with the handle, which the engine maps back (`verbs.py:2159-2162`).
  - A modal spell's mode ask has indices only, so it is untouched.
- **Why it is exact.** For a count-1 CHOOSE every row is a single card, and each has exactly one
  alias (`verbs.py:2159`). The handles therefore offer exactly the choices the indices do.
- **Test.** Duress against a hand of three nonland noncreature cards offers three options (six
  today). The pinned packs still pass: they answer through the raw provider, which still accepts
  indices.

**F3. Copies of a card are one option.**
- **Where it acts.** At the agent layer (`tools/selfplay/actor.py` `NetAgent.decide`): the network
  scores one token per class, and the answer is the class's lowest-handle member.
- **The class key is rules-exact, not encoding-equal** (`search.option_classes` keys by encoded
  rows: `search.py:188-202`). Per handle the option names:
  - oracle id, zone, controller, owner;
  - tapped, counters by kind, damage, live P/T and keywords;
  - the host and the attached objects' descriptors;
  - entered this turn, phased out, chosen values, granted abilities;
  - a return row; targeted by a stack object; attacking, blocking or blocked by;
  - in a library, its position, unless the resolving effect makes position irrelevant. It does so
    when it shuffles that library later in the same resolution ("then shuffle", Cultivate, Fierce
    Empath), or moves every candidate out of the library (Cavalier of Thorns' five revealed cards).
    That is a static read of the resolving effect's remaining atoms. Without it, two equal cards at
    different depths stay two options, because the one left behind is drawn at a different time.
- **Validation (a test).** Over the detector's recorded decisions, no two options the key merges
  have different state signatures. The detector refines the key, never the reverse.
- **What it changes for an old network.** Its distribution over distinct moves loses the
  multiplicity prior: a move with n copies had n times the mass. It is a run-boundary change, and
  its size is measured before it ships: the mean KL over distinct moves, with and without
  merging, on 10,000 recorded decisions (CPU).
- **The search keeps `search.distinct`:** its own class key stays until measured (BACKLOG "The
  search treats copies of a card as different moves").

**F4. A may whose action can do nothing now is not offered** (`query.optional_offer`).
- **What changes.** The narrowing also covers a CHOOSE, TARGET or ALL selection over an empty
  candidate set, when the action does nothing without its objects.
- **Why it is exact.** CR 117.3: no resources, no action. The engine's own principle, applied to
  more selector shapes.
- **Tests.** Liliana's Scrounger with no Liliana asks nothing; Experimental Overload with no
  instant or sorcery in the graveyard asks nothing.

**Not fixed, and why:**
- **different-source triggers that commute only under the null continuation** (above);
- **a division whose excess past lethal changes nothing.** Lethality depends on deathtouch,
  lifelink, damage triggers and prevention, so an exact static rule is the engine's whole damage
  logic. The network learns it;
- **equal outcomes in one state only** (above).

### 2.3 The logic check

- **King.** Every fix removes noise without removing a choice: each is lossless (§2.2's
  arguments). The exception is F3's prior shift, which is measured.
- **Learnable over hardcoded.** These are rules facts (CR 603.3b, 117.3), not strategy. No option
  the rules allow becomes unreachable: every class still offers its move.
- **Honesty.** No hidden information. F3's key reads only what the seat sees, except the library
  position, which only ever prevents a merge.
- **Commander.** F1 removes the board-scaled order asks.
- **Latency.** Fewer asks and fewer option tokens.
- **What could go wrong:**
  - **The scan misses an event read (F1)** → the property test.
  - **F3's key merges two options that differ** → the validation test.
  - **F2 breaks the heuristic or a pack** → both have tests that read the ask.

### 2.4 The experiment

- **No strength A/B for F1, F2 and F4.** They are lossless by construction, and their tests prove
  it.
- **The read after the build:** the detector rerun on 100 games finds no decision of nothing in
  F1's, F2's and F4's classes, and the trigger-order asks fall by about 27 in 61, F1's share.
- **F3 ships with the long run's schema change** (§3), with its measured prior shift. The pilot's
  harm screen covers it.

### 2.5 Order

F1 and F4 are engine changes (binding.py, query.py), F2 a protocol change; none touches the
planner build's files. F3 touches `actor.py`: §6.

### 2.6 The per-kind table (150 games of b100)

From `tables.txt`.
- "Nothing": one state class, every option tested.
- "Redundant": fewer state classes than tested options; it includes the decisions of nothing.
- Mulligans are not tested: no pause point comes before the first turn. The bottom choice is
  compared by name, which is exact for copies in a hand.

| Kind | Decisions | A game | Nothing | Redundant | Redundant options |
|---|---|---|---|---|---|
| priority | 12,703 | 84.7 | 0 | 218 | 218 |
| act | 7,260 | 48.4 | 0 | 1,159 | 1,707 |
| attack | 4,597 | 30.6 | 0 | 0 | 0 |
| block | 1,286 | 8.6 | 0 | 25 | 37 |
| target | 976 | 6.5 | 9 | 166 | 321 |
| mulligan | 427 | 2.8 | — | — | — |
| divide | 403 | 2.7 | 3 | 114 | 324 |
| may | 266 | 1.8 | 20 | 20 | 20 |
| choose | 202 | 1.3 | 0 | 93 | 367 |
| one_of | 187 | 1.2 | 11 | 82 | 501 |
| mulligan_bottom | 170 | 1.1 | 0 | 122 | 205 |
| scry | 112 | 0.7 | 1 | 1 | 1 |
| discard | 67 | 0.4 | 0 | 21 | 24 |
| trigger | 61 | 0.4 | 58 | 58 | 76 |
| mana, arrange, sacrifice, quality, name, pay, legend, x | 120 | 0.8 | 1 | 6 | 21 |
| **all** | **28,837** | **192.2** | **103** | **2,085** | **3,822** |

## 3. Observation gaps: one schema for the long run

### 3.1 The triage

- **Reach:** verified cards of M21, M20 and FDN that print the gap (`census.txt`). The text
  patterns over-count, and the cards named here were read.
- **Frequency:** the share of decisions with the gap present, from the detector games.

| Gap (BACKLOG "What the network sees" and around it) | Verified cards that reach it | Decisions with it on | Verdict |
|---|---|---|---|
| A player's keywords | M21 Runed Halo (protection from a name); M20 Veil of Summer (hexproof from blue and black) | 3.2% (Runed Halo stays on the battlefield) | **In.** Three player columns |
| A card playable through a standing permission, outside the act ask | M21 Chandra, Heart of Fire; Idol of Endurance; Radha, Heart of Keld; Demonic Embrace. M20 Golos; Mystic Forge | 1.4% | **In.** One card column, the count of permissions covering it |
| Thresholds above 5 bucketed as `num:6+` | M21 Speaker of the Heavens (7 more life). M20 Twinblade Paladin, Angel of Vitality (25 life), Ajani, Strength of the Pride (15). FDN Twinblade Paladin, Angel of Vitality. Every card of mana value 6 or more | static | **In.** Log buckets at the table refresh, initialised as copies of `num:6+`, so the function is unchanged |
| The X a target ask's spell announced | M21 Primal Might, Volcanic Geyser. M20 Voracious Hydra. FDN Primal Might | 0 in 150 games | **In,** though rare here: two zero-start columns cost nothing, and X spells are common in Commander. One global column, and the X of a spell on the stack (one card column): the stack shows no X today |
| A delayed or reflexive trigger's ability index (−1) | M21 Tolarian Kraken, Basri Ket, Basri, Devoted Paladin, Subira. M20 Sorin, Imperious Bloodlord. FDN Faebloom Trick | 0.16% | **In.** A value fix in `F_ABILITY_IDX`, the printed ability holding the node. Not function-preserving for those frames |
| An ability whose token source ceased | M21 Infernal Scarring's granted dies trigger on a token. M20 Mask of Immolation on a token | 0.02% | **Out for now.** It would be a new kind of entity, in a new zone, for 6 decisions in 150 games, and every new entity costs a measured disruption. Entities are data, not columns, so adding it later does not change the schema. Reopen when a dealt pool makes it common (token sacrifice outlets, Commander) |
| Emblems | M21 Basri Ket, Garruk, Unleashed, Liliana, Waker of the Dead. M20 Mu Yanling, Sky Dancer. FDN Vivien Reid | 0.74% | **In.** An entity per emblem in the command zone, its row the emblem's own record (`PoolCompile.emblems`) |
| Phasing | M21 Teferi, Master of Time; Teferi, Timeless Voyager | 0.01% | **In.** One card column |
| A return row (killing Banishing Light returns its card) | M21 Kitesail Freebooter, Idol of Endurance. FDN Banishing Light, Stasis Snare | 2.6% | **In.** A pointer column from the held card to its anchor |
| A trigger's event-derived number (that many, that much) | 16 in M21, 9 in M20, 10 in FDN, among them Woodland Champion, Basri Ket, Brash Taunter, Vito, and the lifegain payoffs | not instrumented | **In.** One stack-entity column, the firing's count or amount |
| Live types (an animated permanent) | M21 Riddleform (a 3/3 Sphinx), Dub, Demonic Embrace. M20 Wakeroot Elemental (a land becomes a 0/0 creature) | not instrumented | **In.** Live-type columns from `layers.type_overlay`, and P/T for every permanent that is a creature now. Today an animated Riddleform has no P/T row, since `features.py:724` reads printed P/T only. Colour changes: no verified card. Out |
| Which planeswalker an attacker attacks | 11 planeswalkers in M21, 9 in M20, 1 in FDN | 1.2% | **In.** A pointer column from attacker to what it attacks |
| Block pairings after blocks are declared | every game with two or more blocks | 0.52% | **In.** A pointer column from blocker to the attacker it blocks |
| A stack object's targets beyond the first | 7 in M21, 6 in M20, 3 in FDN | 0.16% | **Out.** `F_STACK_TARGETED` already marks every targeted object, and pairing is ambiguous only with two targeting objects at once. Reopen if E or C puzzles need it |
| One chosen value per quality | none in the 19 sets (BACKLOG) | 0 | **Out** |

- **What the detector says about the options themselves** (§2.1, "blind").
  - Options with equal own tokens that lead to different states were 0.58 decisions a game in the
    40-game run with the corrected key. 18 of the 23 were set-building asks, where the continuation
    decides the outcome.
  - The one block case traced came from the continuation's tie-break, not the encoding.
  - So the detector shows no option-level gap beyond those triaged above. The gaps are about the
    state around the options: who attacks what, who blocks whom, what a player has or knows.

### 3.2 The schema change (one, at the long run's boundary)

All columns are **appended, never inserted**, and named, never numbered. They go after the
planner build's `C_PLAN_WHEN`..`C_PLAN_TARGET` (§6) and the built `P_GAINED`..`P_CAST`.

**Card float columns** (`cards_f`; `model.upgraded` pads `card_f.weight` with zero columns,
`model.py:447-453`):
- `F_PHASED`;
- `F_PERMITS`, the permissions covering the card for its controller now, ÷ 2 (the permits
  module's own accessor, as `permits.playable` reads it: `permits.py:248-260`);
- `F_LIVE_TYPE0..7`, the type line with `type_overlay` (`layers.py:1237`);
- `F_STACK_X`, a stack spell's announced X ÷ 5 (`StackObject.x_value`);
- `F_EVENT_N`, a stack trigger's firing count or amount ÷ 5. It is read from the stack object's own
  bindings: the event's objects (`binding.py:1675-1681`) or the event's amount;
- memory's `F_KNOWN`, `F_LIB_POS` and `F_OPP_KNOWS` (§4).

**Card pointer columns** (`cards_i`, entity + 1, 0 = none). Each has its own linear map, which
`upgraded` sets to zero for a checkpoint that lacks it (`model.py:454-457`, the `_ptr.weight`
rule):
- `C_ATTACKS`, what an attacker attacks;
- `C_BLOCKS`, the attacker a blocker blocks (the first);
- `C_RETURN`, a held card's anchor.

**Player columns** (`players_f`): `P_HEXPROOF`, `P_PROTECTION` and `P_SHROUD`, from
`layers.keywords(player)`; `P_EMBLEMS`, the emblems the player has, ÷ 2.

**Global column** (`glob_f`): `G_X`, the X of the spell or ability whose targets or modes are being
chosen. It is the row's `:x<N>`, carried in a new `AskContext.x` by the rig (`rig.py:102-132`, as
`slot` is).

**Value fixes in existing columns** (not function-preserving where they apply; measured):
- `F_ABILITY_IDX` of delayed and reflexive triggers;
- `F_HAS_PT`, `F_POWER` and `F_TOUGH` for an animated non-creature.

**New entities** (not function-preserving where they appear; measured):
- emblems;
- memory's known cards (§4).

**The card table** (at the long run's refresh):
- `_bucket` (`features.py:209-214`) gives `num:6`, `num:7`, `num:8-9`, `num:10-14`, `num:15-19`,
  `num:20-29` and `num:30+` instead of `num:6+`.
- Each new token's embedding starts as a copy of `num:6+`'s. A row's component mean then changes
  by nothing: Net2Net's copy initialisation (§3.3). `mv:num:*` follows the same rule.
- `extend_cards` (`model.py:187-215`) needs a "copy from" argument for this. Today new tokens
  start at zero, which rescales their rows.

**One rule for the long run: every column exists from its start, and flags decide which are
filled** (`--memory`, `--planner`). A flag turned on later fills columns that are already there, so
the schema never changes during the run.

### 3.3 Function preservation: the method and its check

**The method: function-preserving network transformations** (Net2Net, Chen, Goodfellow and Shlens
2016). A new input column with zero weights, and a new token initialised as a copy of the one it
splits, leave the network's function unchanged. The repo already does the first (`model.upgraded`).

| Its assumption | Here | What changes |
|---|---|---|
| New units enter a fixed-size computation (widening, deepening) | New columns: holds, exactly up to the floating-point order of a longer matrix product | A test with a tolerance (max abs logit difference < 1e-5, argmax identical), not bitwise |
| — | New entity tokens join a softmax attention over a variable set | Not preserving: every token's attention renormalises. **Measured instead** |

**The measurement.**
- The old network's mean KL, between today's encoding and the new one with every new entity
  present, over 10,000 decisions of the detector games where at least one new entity exists. Also
  reported as a share of all decisions.
- **The bound:** below the median per-update `kl` of r29b, about 0.006. One update moves the policy
  that much anyway.
- **Above the bound:** that entity type stays behind its flag, off, until a registered arm turns it
  on.

**Tests that fail on today's code,** one per column:
- Veil of Summer resolved: the caster's `P_HEXPROOF` is 1.
- An attacker attacking Basri Ket: `C_ATTACKS` points at Basri.
- Banishing Light holding a creature: `C_RETURN` points from the creature to the Light.
- Riddleform animated: `F_HAS_PT` is 1 and the power reads 3.
- Primal Might's target ask: `G_X` holds X.
- Tolarian Kraken's reflexive trigger: `F_ABILITY_IDX` is its printed ability, not −1.
- An emblem from Basri Ket's −6: an entity in the command zone.
- Plus the tolerance test of an old checkpoint over recorded decisions with no new entity.

### 3.4 The logic check

- **King.** Every column is a public fact the rules use and the network could not see. The
  network learns what each is worth; no strategy is encoded.
- **Generalisation through components.** The facts are per object and per player, not per card.
  Log buckets make a threshold of 25 readable for any card that prints one.
- **Honesty.** Every column is public: phasing, permissions (a card's playability from public
  zones and the controller's own library top), keywords, emblems, combat assignments, returns.
  Memory's are §4's.
- **Commander.** Per-player columns and pointers scale with players; emblems and the command zone
  are Commander's own.
- **Latency.** A few columns per token, and a handful of extra entities. Negligible next to the
  card tokens.
- **What could go wrong:**
  - **A column's engine read is wrong** (e.g. `F_PERMITS` counting a permission that does not
    apply) → each column's test, and the bench view's own display, which the LLM seats read, from
    the same accessor.
  - **New entities disrupt** → the measurement and flags.

## 4. Memory: what a player has legitimately seen in hidden zones

### 4.1 The problem, measured

The network sees hidden cards only while an ask offers them (`features.py:652-658`). It forgets:
- a card returned to the opponent's hand from play;
- a hand Duress revealed;
- the card it scried to the top.

The bench's seat view says the same: "cards a player has legitimately seen in a hidden zone ...
are not tracked" (`MTG_bot/bench/view.py:21-22`).

**Reach (the census, verified cards; M21 / M20 / FDN).** These are text-pattern counts, so they
are upper bounds: Grim Tutor's "put it into your hand" is a hidden move, not a public one. The
cards named were read.
- hand reveals 2 / 2 / 2: Duress, Kitesail Freebooter, Thought Distortion, Pilfer;
- cards returned to a hand from a public zone 21 / 27 / 14: Unsummon, Into the Roil, Gravedigger,
  Soul Salvage, ...;
- scry or look at the top 14 / 16 / 14: Opt, the Temples, Anticipate, Mazemind Tome, ...;
- the top revealed 2 / 4 / 1;
- a search's card revealed into the hand 3 / 1 / 1: Cultivate, Fierce Empath, ...;
- a card put at a known end of a library 1 / 1 / 0: Teferi, Timeless Voyager; Eternal Isolation;
- shuffles 16 / 10 / 5.

**Frequency (the detector games):**
- the opponent's hand holds a card known from a public zone at 2.1% of decisions (4.0 a game);
- the decider's own hand holds one the opponent knows at 2.5% (4.7 a game);
- per game:
  - REVEAL rows 0.89, LOOK_AT 0.18, SCRY 0.53, SEARCH 0.45, SHUFFLE 3.5;
  - moves into a hand from the graveyard 0.33, the battlefield 0.31 and exile 0.13;
  - moves into a library from the graveyard 0.19, the battlefield 0.04 and the hand 0.05.

These count only the public-to-hand rule, which the journal can already tell. They are a lower
bound on memory's reach.

**The journal cannot rebuild the rest today** (BACKLOG "The journal is not a record of what
players know"):
- SCRY journals the count, not the cards (`verbs.py:1623`);
- REVEAL has no zone role and reads the library, so Duress journals the target's library as
  revealed (`verbs.py:1650-1727`);
- a move into a library records no end: `move_card` appends, which is the top (`state.py:191-199`),
  and bottom puts insert at 0 (`verbs.py:341-343, 464`, `games.py:599`);
- SHUFFLE is an audit row, not a journal event (`verbs.py:1647`).

### 4.2 Methods, and the assumption-transfer check

**Information sets and perfect recall** (Kuhn 1953).
- A player's knowledge is a function of their observation history, and players remember all of
  it.
- ReBeL's public belief states (Brown et al. 2020) track probability distributions over private
  information given public actions.
- **What is taken here:** the certain part only, a sufficient statistic of what a player has seen.
  Probabilities are the opponent simulator's work (OWNER_VISION §5).

| Their assumption | Here | What changes |
|---|---|---|
| Perfect recall | Paper Magic: a player remembers what was revealed (the owner's §4) | Holds |
| Observations defined by the game (poker: public cards and actions) | The engine's journal must define them, and today it does not | Four journal fixes first (§4.4) |
| Beliefs need a model of the opponent's policy | Certain knowledge needs none | The tracker is exact, policy-free and cheap |
| A card in a hidden zone is tracked by identity | In a hand, cards can be reordered, so identity is lost; a library keeps order until a shuffle | Hands by name (lower bounds), libraries by position: the owner's "counted by name" (PLAN_PLANNING §5) |

### 4.3 The rules of knowledge (exact)

**The state.** For each viewer v and player p:
- **H[v][p]:** for the hand of a player p ≠ v, a count per oracle id, a lower bound on that card's
  copies there. v's own hand is visible.
- **L[v][p]:** the cards of p's library whose identity v knows, each with whether v knows its
  position. The position is read from the true library order whenever asked.

| Event | Update |
|---|---|
| E1. A card moves from a public zone to p's hand | For every v: H[v][p][card] += 1. It was public as it moved |
| E2. A card moves from p's library to p's hand: a draw, or an unrevealed put | For each v that knew it (in L[v][p]): H[v][p][card] += 1, and it leaves L[v][p] |
| E3a. A card leaves p's hand openly: cast, discard, onto the battlefield, revealed | For every v: H[v][p][card] = max(0, H − 1) |
| E3b. A card leaves p's hand unseen: face down into a library | For every v ≠ p: every positive H[v][p][n] − 1 (the card might be any known one). For p: the card joins L[p][p] at the end it went to |
| E4. A REVEAL to all of a whole hand | For every v: H[v][p] = the hand's exact counts |
| E4a. A REVEAL to all of some cards of a hand | For every v and each card: H[v][p][card] = max(H, the revealed copies) |
| E4b. A REVEAL of library cards | For every v: they join L[v][p], positions known |
| E4c. LOOK_AT by w | The same, for w only |
| E5. p scries N | L[p][p] gains the N cards at their new positions (p's arrangement). For v ≠ p: those of the N in L[v][p] lose their position (top group or bottom, unknown) and leave L[v][p] |
| E6. A card goes from a public zone to a known end of p's library | For every v: it joins L[v][p], position known |
| E7. p's library is shuffled | For every v: L[v][p] is emptied |
| E8. A card leaves p's library to a public zone (mill, onto the battlefield) | It leaves every L[v][p]: it is public now |
| E9. p rearranges library cards v did not see (a look and reorder) | For v ≠ p: those cards leave L[v][p]. For p: positions known |
| E10. The game's start, and a mulligan's shuffle | Everything about that player's hand and library is emptied. The London mulligan's bottom cards then follow E3b: their owner knows them at the bottom; the opponent knows nothing |

**Every rule keeps knowledge a lower bound:** where a viewer cannot tell which known card left, it
forgets one of each. Two forgettings are deliberate:
- the counts of a scry's top and bottom groups, which are public in paper (E5);
- a card shuffled back is still in the library, somewhere (E7).

Both are said aloud in §8.

### 4.4 The engine events it reads (the journal fixes first)

- **J1.** REVEAL and LOOK_AT get a zone role (hand or library) and a set of viewers: all for
  REVEAL, the looker for LOOK_AT (`verbs._look`). This closes BACKLOG's "REVEAL has no zone
  role". Duress, Kitesail Freebooter, Thought Distortion and Pilfer then journal the hand.
- **J2.** SCRY journals each card and where it went, in order, visible to the scryer (`_v_scry`
  and `_arrange`).
- **J3.** A move into a library journals its end, top or bottom, or "shuffled in". The bottom puts
  above, and `move_card`'s append to the top.
- **J4.** SHUFFLE becomes a journal event. A library segment rearranged by its owner is journaled
  with the arranger.

Each fix is an engine change with its own packs. None touches the planner build's files.

**The tracker** (`MTG_bot/core/executor/knowledge.py`).
- It reads the journal lazily: each observation consumes the events since its last index, as
  `features._this_turn` makes one journal pass (`features.py:558-597`).
- It holds handles internally, and gives each viewer names and positions only.
- It is copied with forks (a deepcopy, as the rest of the executor).
- The bench's seat view shows it too, closing `view.py`'s known limit, so LLM seats know what the
  network knows: one projection for every agent.

### 4.5 How the network sees it

- **For the opponent's hand:** one entity per known copy.
  - Zone hand, controller and owner the opponent, the card's table row, `F_KNOWN` = 1.
  - Cards the current ask already offers or reveals are subtracted: they are shown as today, with
    `F_REVEALED`.
- **For libraries (one's own and the opponent's):** one entity per known card, with `F_KNOWN` = 1
  and `F_LIB_POS`, the depth from the top ÷ 10, negative counted from the bottom.
- **For one's own hand:** `F_OPP_KNOWS` = 1 on as many of one's copies of each card as the
  opponent knows of, the lowest handles first. Equal copies, so which ones does not matter.
- **No entity of memory is an option.** A known card that becomes playable is offered, and is
  then shown as today. The planner's plannable objects ("a known library top", DESIGN_PLANNER §1)
  read the same entity.

### 4.6 The logic check

- **Honesty** (OWNER_PREFERENCES #1, the binding rule), proved by two invariants with tests:
  - **I1, soundness.** After every journal event of random games over the three pools:
    - each H[v][p][n] is at most the true count;
    - every card in L[v][p] is in p's library, at the position the tracker gives.

    This checks the tracker never claims more than is true.
  - **I2, legitimacy.** One pack per rule E1-E10, showing each item comes from an event v
    witnessed:
    - Duress shows the caster the whole hand, and the target sees `F_OPP_KNOWS`;
    - Unsummon tells both players;
    - a scry to the top tells only the scryer;
    - drawing a known top card moves the knowledge into the hand;
    - casting the known Shock drops the count to 0;
    - a shuffle empties the library knowledge;
    - a mulligan empties everything;
    - a face-down hand-to-library move lowers every count by one;
    - Teferi, Timeless Voyager's top card is known to both until drawn.
  - **I3, hooks complete.** The tracker's count of each library equals the true count after every
    event. An unjournaled library move breaks it.
- **King.** "They revealed a Negate" becomes visible, which is OWNER_VISION §3's first kind of
  history.
- **Learnable.** The facts are certain and rule-made; the network learns what they are worth.
- **Generalisation.** Knowledge rides card entities, read through their components like any card.
- **Commander.** Viewers per seat; reveals to all or to one. The state is keyed by viewer from
  the start.
- **Latency.** One journal pass per observation, and a handful of entities.
- **Function preservation.** New entities; measured as §3.3's.
- **The search** (later, not in scope). Its worlds could keep known cards fixed rather than
  re-sample them (`search.reshuffle_unknown` was dropped because the journal could not say what
  was known: BACKLOG).

### 4.7 The experiment

- **Memory v1's registered test is the planning A/B's memory arm** (PLAN_PLANNING §5: the E
  category above control, L not regressing). The E puzzles need the tracker:
  - the solver's information set must include what the decider knows;
  - `solver.EngineTree.expand`'s key (`tools/puzzles/solver.py:216-222`) gains the tracker's view
    for the decider.
- **Before that arm:**
  - invariants I1-I3 green;
  - the disruption measured;
  - the reach re-measured with the full tracker: decisions with any known hidden card, per game.

## 5. The optimizer's state on a resume

### 5.1 The problem, measured

- The trainer process owns AdamW (`tools/selfplay/trainer.py:44-45`) and its minibatch generator
  (`trainer.py:33`, `default_rng(a.seed)`).
- The learner commits only weights and run state (`learner.py:1298-1306`). On a resume both
  restart (`learner.py:1212`: "the optimiser moments are not saved").
- **What a restart does.** A fresh Adam's first step is `m̂ / √v̂ = g / |g|`: every coordinate
  moves by about lr. In the steady state a noisy coordinate moves by `|E g| / √E g²` of that, far
  less. The second moment needs about 1 / (1 − β₂) = 100 steps, about two updates of 53 steps, to
  settle.
- **Measured** at r27's resume after window 2: no shock overall, `kl` 0.0037-0.0086 over updates
  166-169 (198 §2; BACKLOG).
- The minibatch generator restarting replays the run's first shuffles.
- **The size:** 28,070,402 parameters, so AdamW's two moments are 214.2 MiB in fp32 (`params.py`),
  beside `last.pt`'s 111 MB.

**The method's assumption-transfer check** (Kingma and Ba 2015's bias correction; Loshchilov and
Hutter's AdamW):

| Its assumption | Here | What changes |
|---|---|---|
| A reset optimizer re-warms within about 1 / (1 − β₂) steps | 100 steps, about two updates | Holds |
| The gradient noise is large next to its mean, so reset steps are larger than steady ones | Noisy outcome PPO with small alignments (199 §8) | Holds |

**Conclusion.** A resume today costs a few updates of larger, noisier steps. A multi-day run with
pauses for measurement windows pays it at every pause. The fix is small, and makes a resume exact.

### 5.2 The design

- **The trainer** answers a new message ("opt",) with `opt.state_dict()` (CPU tensors) and
  `rng.bit_generator.state`.
  - The learner asks only in `checkpoint()`, between updates, when the trainer is idle: `update()`
    returns before any checkpoint is made (`learner.py:1242, 1282-1285`).
- **`last.pt`** carries them in `extra["opt"]`, with the update they belong to, in the same atomic
  write. `state.pkl` (the watchers' copy) does not.
  - Frozen versions and `best.pt` carry none.
  - `last.pt` grows to about 330 MB, written every 5 updates.
- **A resume** passes them to the trainer's spawn (`learner.py:445-449`, `ckpt`). The trainer:
  - loads the optimizer state;
  - **re-applies this start's lr, betas, eps and weight decay to every parameter group,** so a
    resume with a new `--lr` uses it (`load_state_dict` would restore the saved lr), and logs both;
  - restores the generator.
- **An old `last.pt` without `opt`:** a fresh optimizer, logged as `{"event": "resume", "opt":
  "fresh"}`.
- **`--init` does not carry an optimizer by default:** a new segment is a new run.
  - `--init-opt` carries the matching parameters' moments and pads grown ones (new embedding rows,
    new columns) with zeros, logged per parameter. It is for a segment boundary that wants
    continuity.
  - Off by default, so today's behaviour holds.
- **Tests that fail on today's code:**
  1. Three updates in one trainer, against two updates, a new trainer from the saved weights,
     optimizer and generator, then the third: the weights are bitwise equal on CPU.
  2. `checkpoint()` writes `extra["opt"]`, and `load_state` reads it back into the spawn's `ckpt`.
  3. A resume with a changed `--lr` trains at the new lr.
  4. An old `last.pt` resumes, logged "fresh".
- **The read at the first real resume:** the three updates' `kl` after it against the three
  before. No jump is predicted.
- **What a pause still loses** (said aloud, not in scope): the games in flight and the partial
  batch. `_release`'s issue order keeps the next batch unbiased (`learner.py:858-879`).

## 6. Order, interfaces, and the GPU schedule

**The planner build, in progress in another worktree** (read 2026-11-18):
- `features.C_PLAN_WHEN`..`C_PLAN_TARGET`, card integer columns after `C_NAMED`;
- `model.PolicyValueNet(planner=True)` with zero-started planner layers, and `forward(b,
  plan=True)` returning a third element;
- `ppo.planner_terms` with `--plan-coef` and `--follow-coef`;
- `planner.Tracker` in the workers.

**The interfaces this plan uses, named so the two builds merge cleanly:**
- **`model.forward(b, plan=False, value_logit=False)`.** The value branch lives inside `forward`.
  The return keeps the planner's order, with the value logit appended last when asked.
- **`ppo_train`'s loss:** `pg + vcoef · value_term(a.value_loss) − ent · H` + the planner's terms,
  unchanged. `ev_turn`, `c_turn` and `vll_turn` join the stats beside the planner's `plan`.
- **Columns** are appended by name after the planner's, merged in that order.
- **`actor.NetAgent.decide`:**
  - F3's classes wrap the encode and infer;
  - the planner's `Tracker` records the executed option, the class's member;
  - memory's entities come from `features.encode`, which reads `executor.knowledge`.
- **`trainer.py`:** the "opt" message. The planner build does not touch this file.

**Build order** (each step its own commit, its tests first):

| # | What | Files | Waits on |
|---|---|---|---|
| 1 | Stage 0's probe script | `reports/` | nothing; runs at B8's pause tonight |
| 2 | F1, F2, F4 | `binding.py`, `bench/protocol.py`, `query.py` | nothing |
| 3 | J1-J4, the journal fixes | `verbs.py`, `state.py`, `events.py`, `games.py` | nothing |
| 4 | The optimizer state | `trainer.py`, `learner.py` | the planner's `learner.py` merged |
| 5 | The value package | `model.py`, `ppo.py`, `learner.py` | stage 0's rule; the planner's merge; then a GPU smoke at the real flags |
| 6 | The knowledge tracker, I1-I3 | `knowledge.py`, `bench/view.py` | 3 |
| 7 | The schema change, memory's view, F3 | `features.py`, `model.py`, `actor.py`, `rig.py` | 6 for memory's entities. After 5 only in merge order, since both edit `model.py`; neither waits on the other's A/B. The disruption measurement and F3's prior shift before it ships |

**The GPU schedule** (one job at a time):
- **Tonight, at B8's pause:** stage 0 (about 40 minutes).
- **The FDN segment's first 22 machine-hours:** the value A/B, if steps 1 and 5 are done and
  smoked by its launch. Otherwise the FDN segment runs as registered, and the value arm joins the
  planning A/B.
- **From 2026-11-23:** the planning A/B, from the FDN segment's checkpoint, on code with step 7
  built. The arms: control, memory v1, the planner v1, and the value arm if it is still open.
  Memory and the planner fill columns the control has too, at zero.
- **Then the pilot of 8-12 machine-hours** with the winners together, its harm screen covering
  the combination (W5) and F3's prior shift. Then the long run, on one schema.

## 7. The assumptions behind the conclusions

**The owner's:**

| # | Assumption | Where it binds | If it is wrong |
|---|---|---|---|
| O1 | γ = λ = 1 stays | §1.2: the value cannot bias the gradient | With λ < 1 the value's targets bootstrap, its errors bias the advantages, and its calibration (cross-entropy) and isolation matter more. §1's conclusions strengthen |
| O2 | The combat failures are value errors (PLAN_LONG_RUN, from 214) | §1.2 reads them as a missing trunk feature that both heads show | If only the value were wrong, the searcher would fix them and the raw policy would not. The puzzles' searched C read (planned in 214 §5) decides. §1's package targets the value's part either way |
| O3 | Decisions of nothing matter for stability | §2 | They are rare: 0.36% of decisions, and redundant options in 6.6%. So the stability gain from F1, F2 and F4 is small. The fixes stay exact and cheap, and the Commander argument stands |
| O4 | Memory counts hands by name | §4.3 | If draw order is fair to show (some clients do: OWNER_VISION §4), identity could be kept. The by-name design is the paper-fair lower bound and stays a subset |
| O5 | The long run starts on one schema | §3.2 | If mid-run changes were acceptable, the bundle could ship in parts. One schema avoids repeated boundaries and their shifts |
| O6 | No hidden information in play | §3.4, §4.6 | Not negotiable. I1 and I2 enforce it |

**Mine:**

| # | Assumption | Where it binds | If it is wrong |
|---|---|---|---|
| A1 | One update's alignment, per unit of movement, predicts a run's drift | Stage 0's rule | The rule could skip the branch wrongly. The A/B still runs the loss alone, and the branch can be tested later. Its cost is bounded by stage 0's size |
| A2 | 11 hours per arm can show harm and mechanism, but not a strength gain | §1.6's decision rule | If harm shows only over days, the pilot and the long run's guards (L every gate) catch it. The adoption rule is the red team's to test |
| A3 | b100's games represent the main line's value now | M3: the early value uninformative and overconfident | `ev_turn` and `c_turn` re-measure it on every update once built. Until then it is one network's reading over 150 games |
| A4 | The detector's signature captures the state | §2's counts | Different signatures stay right; some "nothing" may be real. Only rules-exact fixes ship |
| A5 | The long run deals the verified pools of M21, M20 and FDN | §3.1's reach | A new set reruns `census.py` (seconds) |
| A6 | Zero columns preserve the function; new entities do not, by a measurable amount | §3.3 | Above the bound, the entity type waits behind its flag |
| A7 | The multiplicity prior that F3 removes is noise, not help | F3 | Measured KL; the pilot's harm screen |
| A8 | Restarted moments cost something over a multi-day run | §5 | Measured small (198 §2). The fix's cost is small too, and it makes a resume exact |
| A9 | Two branch layers suffice for the value | §1.4 | M5 says capacity is not the limit. EV by turn shows it, and K = 3 is the response |
| A10 | A stop-gradient is the right granularity, against PPG's constrained sharing | §1.3 b, c | If the value's shaping helped, R1 or R2 shows harm, and PPG-lite is next |
| A11 | Every way a trigger's resolution reads its event goes through the `event` referent, the gathered objects or the reflexive carry | F1's exactness | If a read escapes the scan, F1 merges two firings that differ. F1's property test (a sentinel event) catches it on every verified trigger before it ships |
| A12 | After J1-J4, every library mutation is journaled | §4's tracker | An unjournaled move leaves stale knowledge. I3 (the tracker's library sizes against the true ones after every event) catches it in random games |
| A13 | The trainer is idle whenever the learner commits | §5's synchronous "opt" request | Read in the code: `update()` returns only after the trainer's "done" (`learner.py:453-469`), and every commit comes after it. A future asynchronous commit would need the state sent with "done" instead |

## 8. Hand-set choices said aloud (for docs/BACKLOG.md "Scaffolds to remove")

- **The value branch's depth, K = 2 of 8.** Removable when EV by turn at K = 1, 2 and 3 shows the
  knee.
- **Value clipping dropped with the cross-entropy loss.** A removal, said aloud: Andrychowicz et
  al. 2021 found clipping no help, and cross-entropy has no analogue.
- **The turn buckets of `ev_turn`, `c_turn` and `vll_turn`.** A diagnostic, not a scaffold.
  Listed so nobody reads them as one.
- **Knowledge kept as a lower bound** (§4.3). Position is forgotten after an unseen rearrangement
  and after a scry, and identity after a shuffle. Removable when the opponent simulator holds
  beliefs over positions.
- **The log buckets of numbers** (`num:6` ... `num:30+`). A discretisation, as DESIGN_CARD_POOL
  plans. Removable with a learned numeric encoding.
- **The disruption bound** (the median per-update KL). A rule for shipping, not for play.
- **The detector's null continuation.** A measurement tool. It never touches play.

## References

- Andrychowicz, M. et al. What Matters for On-Policy Deep Actor-Critic Methods? A Large-Scale Study. ICLR 2021.
- Raileanu, R., Fergus, R. Decoupling Value and Policy for Generalization in Reinforcement Learning (IDAAC). ICML 2021.
- Cobbe, K., Hilton, J., Klimov, O., Schulman, J. Phasic Policy Gradient. ICML 2021.
- Schulman, J. et al. Proximal Policy Optimization Algorithms. 2017.
- Silver, D. et al. A general reinforcement learning algorithm that masters chess, shogi, and Go through self-play. Science 2018.
- Wu, D. J. Accelerating Self-Play Learning in Go (KataGo). 2019.
- Jaderberg, M. et al. Reinforcement Learning with Unsupervised Auxiliary Tasks (UNREAL). ICLR 2017.
- Greensmith, E., Bartlett, P., Baxter, J. Variance Reduction Techniques for Gradient Estimates in Reinforcement Learning. JMLR 2004.
- Ip, C. N., Dill, D. L. Better Verification Through Symmetry. Formal Methods in System Design 1996.
- Gilpin, A., Sandholm, T. Lossless Abstraction of Imperfect Information Games. JACM 2007.
- Chen, T., Goodfellow, I., Shlens, J. Net2Net: Accelerating Learning via Knowledge Transfer. ICLR 2016.
- Kuhn, H. W. Extensive Games and the Problem of Information. 1953.
- Brown, N., Bakhtin, A., Lerer, A., Gong, Q. Combining Deep Reinforcement Learning and Search for Imperfect-Information Games (ReBeL). NeurIPS 2020.
- Kingma, D., Ba, J. Adam: A Method for Stochastic Optimization. ICLR 2015.
- Loshchilov, I., Hutter, F. Decoupled Weight Decay Regularization. ICLR 2019.
