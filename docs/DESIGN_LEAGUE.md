# Design: the league, the Teacher, the critic and the drafter, as one system

**Who the learner plays, with which decks, chosen how.**

Status: **design for the red team, 2026-11-18. Nothing here is built** except what §1 cites as
existing. It covers items 1 (a league with exploiters) and 3 (the deals) of
[`PLAN_LONG_RUN.md`](PLAN_LONG_RUN.md), and the Teacher, the critic and the drafter, because the
owner asked for them as one coherent system.

The owner, 2026-11-18: agreed on "a league with exploiters" and on deals that hold synergies, and:
> "I would even prefer we implement the drafter and the trainer or critic or what you call it,
> that can both draft intelligent decks, as well as make good matchups, utilize synergies,
> utilize exploiting experts etc. ... I think the drafter/teacher/critic is important to get
> right too, and coherent with the rest."

**What stays settled** (built on, not re-argued):
- D15: the Teacher is a curator plus a critic; the drafter is a generative policy; they share the
  critic.
- D16: nicheness and randomness are two knobs.
- D8: inherit representations, not policy; earlier models stay in the league as opponents.
- PLAN_CEILING §7.1-§7.2 (D22): PFSP weighted x(1 − x); L, the frozen held-out pool, is the
  yardstick; L's members never train.
- OWNER_VISION_LEARNING §1-§2: reward ±1, γ = λ = 1; no memorisation through deals.
- OWNER_PREFERENCES #1: play never reads a hidden zone.

**Where this takes over.** The staging of [`DESIGN_TEACHER.md`](DESIGN_TEACHER.md) §7 and the
order of [`PLAN_DRAFTER.md`](PLAN_DRAFTER.md) §8, both written before today's evidence. Those
documents keep their analysis; their status notes say what is superseded (§7 here).

## Summary for the owner

**Today** (§1):
- The learner plays itself 55% of the time, r28's v2 30% and the heuristic 15%.
- The pool has not grown: no gate has passed in r29's 174 updates, and a version joins only by
  passing one.
- Every deck is a coherent deck: two colours, 24 basics, 36 uniform cards.

**What the long run gets** (§3):
1. **A league.**
   - Members: the learner's own snapshots, taken at every gate pass or every 100 updates; r28's
     v1; the exploiter of the exploitability probe (211); the heuristic.
   - Opponents are drawn as AlphaStar's main agents draw them: self-play, prioritized fictitious
     self-play (PFSP) over the past, and a verification share against exploiters and against
     snapshots the learner no longer beats.
2. **Exploiter phases.** 8 machine-hours every 48, each against the newest snapshot. A phase's
   exploiter joins the league. The phases stop after two that find nothing.
3. **Deck recipes, chosen per seat:**
   - coherent 40%;
   - synergy packages 20% (built);
   - roles 20%: counterspells, sweepers;
   - critic-drafted 20% (built).

   Every deal stays fresh.

**What it is for, honestly** (§4):
- Insurance for a multi-day self-play run against cycling and forgetting.
- A standing exploitability probe.
- Closing a measured gap: the network plays package and drafted decks 0.036 and 0.061 worse
  against the heuristic than coherent ones (205 §9).
- More frequent planning situations. A counterspell is in the first 12 cards of 9% of M21 decks,
  and of 60% of counterspell-role decks (§3.4).
- **It is not a lever for the plateau.** The plateau's levers are the value function, the planner
  and search-improved targets (PLAN_LONG_RUN items 2 and 4; PLAN_PLANNING P2-P3).

**What waits, and why** (§3.6-§3.8):
- The Teacher's adaptive choice of decks waits. Every cheap signal it could steer by is flat,
  luck-dominated, unsafe for memorisation or below its standard error here (§2.3). Its
  instruments run from the first day.
- The synergy-aware critic, counter-drafting, the pick-by-pick drafter and nicheness wait too.

**The experiment** (§5): a harm screen of 5.5 + 5.5 machine-hours before the long run, then
registered reads inside it, with stop rules.

---

## 1. The problem, measured

### 1.1 Who the learner plays

- **The code.** `curriculum_job` (`tools/selfplay/learner.py:585-619`) draws one opponent per
  training game from fixed shares:
  - the heuristic, `--p-heuristic`;
  - older frozen versions uniformly, `--p-past`. With none yet, it plays the newest
    (`learner.py:603-604`);
  - itself, `--p-self`, both seats trained;
  - the rest against the newest frozen version.
- **How a version joins.** Only by passing a gate: with r29's flags, 1,000 fresh deals against
  the newest version, a score of at least 0.55 with the lower bound above 0.5
  (`learner.py:1183-1194`). It is a
  registered scaffold (BACKLOG "Self-play gate"), whose removal condition is exactly this
  document: "a league whose opponent sampling follows measured win rates".
- **r29's arm B, the main run** (read 2026-11-18 at update 174 from
  `runs/selfplay/r29b_pself055/metrics.jsonl`):
  - The flags give self 0.55, the heuristic 0.15 and past 0.15. The past share falls through to
    v0, so v0 takes 0.30.
  - Its six gates against v0 (r28's v2) read 0.4973 to 0.5333. None passed, so the pool is still
    {v0, the heuristic}.
  - Training win rates, sampled play: about 0.50 against itself, 0.48-0.57 against v0 and
    0.64-0.77 against the heuristic.
  - 7.3 games and 1,228 decisions a second, 162 s an update, train-bound: its workers are
    refused about 17 times an update while a full batch waits. Arm A, collect-bound, played 8.3
    games a second.
- **Learning.**
  - r28 gained +39 Elo over its init and went flat after update 1,000 (199 §9).
  - Neither r29 arm moved off its init in 5.5 machine-hours (208 §11): A 637.7 and B 633.8 on L,
    the init 633.2, every SE about 4.
  - Each network plays one habit per kind of decision (214 §5):
    - it attacks into a lethal crack-back;
    - it never holds back;
    - it counters by habit. Arm B moved from never countering to always countering.
- **Exploitability.** An exploiter trained 4 machine-hours only against r28's v2 reached a greedy
  gate of 0.5295 [0.5145, 0.5445] at update 52, with sampled play flat at 0.50 (211 §4). It found
  no line v2 fails to answer.
- **Cycles.** None measured so far: L's frozen fit had every pairing within |z| ≤ 2.0 (205 §9).
  208's B9 round robin is not yet read.

### 1.2 With which decks

- **Coherent decks only** (`--coherent-share 1.0`). `build_coherent_deck`
  (`MTG_bot/core/executor/games.py:1572-1610`) deals two seeded colours, 24 basics and 36 cards
  uniform within the pair. It is a registered scaffold (B-45).
- **Built and gated, but unused in training:**
  - **Package decks** (`tools/selfplay/packages.py`): a family's consumers and producers, read off
    the compiled trees. 22, 15 and 18 packages are kept in M21, M20 and FDN at this commit.
  - **Critic-drafted decks** (`tools/selfplay/decks.py:348-386`): k critic swaps on a fresh deal.
- **What those shapes measured:**
  - No extra one-turn search headroom in package decks: +0.0042 [−0.0105, +0.0188]. Drafted
    decks hold none either: −0.0140 (205 §9, S1 and S2).
  - **The network does not generalise across deck shapes.** Against the heuristic, package decks
    play −0.036 [−0.053, −0.019] and drafted decks −0.061 [−0.078, −0.045] worse than coherent
    ones (205 §9, S3 and S4). Training on them would close that gap. It is not extra ceiling.
  - Drafted decks are tempo decks (193 §3, G4; PLAN_CEILING §14.1):
    - the critic values cards by how today's pilots win with them, so swaps add creatures and
      heavier curves, and remove the skill-heavy cards (Riddleform last of 462, Spectral Sailor
      near the bottom; PLAN_CEILING §14.1);
    - games are 1.71 turns shorter;
    - fewer deals are decided by the pilots: −0.045 [−0.086, −0.004].
  - No package ordering line carries value; forcing the sacrifice line costs 0.173 (202 §2-§3).
- **Planning situations are rare in coherent deals** (new, `reports/league_teacher_2026-11-18/`;
  roles read off the compiled trees, 2,000 deals per set and shape, the verified pools at this
  commit). The last column is the chance a copy is among a deck's first 12 cards, its hand by
  turn 6 on the play:

  | Set | Counterspells in the pool | Decks with one | In the first 12 | Sweepers in the pool | Decks with one | In the first 12 |
  |---|---|---|---|---|---|---|
  | M21 | 4 (Cancel, Lofty Denial, Miscast, Rewind) | 29.0% | 9.2% | 2 (Massacre Wurm, Pestilent Haze) | 19.4% | 5.0% |
  | M20 | 4 (Bone to Ash, Convolute, Negate, Tale's End) | 29.7% | 9.7% | 5 | 41.5% | 11.6% |
  | FDN | 6 | 36.7% | 15.7% | 5 | 50.5% | 14.3% |

  - Package decks hold fewer of both (M21: 7.6% and 4.0%).
  - In M21, three quarters of training deals, a seat holds a counterspell by turn 6 in about 18%
    of games. Both seats hold one in under 1%: the board of puzzle B2.

### 1.3 Chosen how

- **Fixed shares.** No opponent or deck is chosen by any measured quantity.
- **The Teacher is not built.** PLAN_CEILING §9.1 put it after the ceiling read.
- **The critic v0 is built and passed its gates** (193 §3):
  - G1: it beats a baseline of colour pair, seat, pilots and 12 deck summaries by 0.00996 ±
    0.00074 nats a game;
  - G2: 83% of a predicted deck gain shows up in play (slope 0.833 [0.776, 0.891]);
  - G3: drafted decks stay diverse;
  - G4: 10,000 drafted games with no engine error.
- **The critic is out of date.** It was fitted on r27's games of 2026-11-12 (6b8014ae) and knows
  none of the cards verified since, FDN included.
- **What the rebuild and the exploit scan skip.** `decks.py rebuild` and the exploit scan read
  only coherent and stress deals (`decks.py:41`, `deals_in` at `decks.py:65-74`;
  `tools/audit/exploit_scan.py:620`). A package or drafted training game would be invisible to
  the critic and the scan.

### 1.4 What a multi-day run risks without a league

- **Cycling.** Self-play chases its own last habit (OpenAI Five, AlphaStar; Czarnecki et al. 2020
  on the cyclic part of game spaces). r29 B is 55% self-play, and its counter habit flipped
  without learning the condition.
- **A pool that never grows.** With gates at 0.50 a version never freezes, so after days the
  "past" is still r28's v2.
- **Forgetting.** Nothing replays an opponent the learner has stopped beating, and nothing checks.

---

## 2. The field's methods, and whether their assumptions hold here

The owner's rule (2026-11-18): every method taken from the literature gets an assumption-transfer
check. A method whose key assumption fails is adapted, with the adaptation argued, or dropped.

**The facts every check is held against:**
- one GPU, one job at a time;
- two-player zero-sum self-play with hidden cards;
- reward ±1 with γ = λ = 1;
- a deck's strength is a noisy win rate that depends on its pilot's skill. That is why
  critic-drafted decks became tempo decks (193; 205 S2);
- a deal is replayable from its seed: `GameWorld(master_seed=seed)`
  (`games.py:1141`) fixes the decks, the shuffles and the engine's randomness;
- the learning signal is weak:
  - r28 at its best gained 1.31 Elo per machine-hour, then 0.34, then 0;
  - a rating's SE is 4-8 Elo near even and 11-19 at a 0.85-0.95 score (PLAN_CEILING §6.4);
  - games run at about 1,000 per update.

### 2.1 Choosing opponents

| Method | Its assumptions | Here | Adaptation and conclusion |
|---|---|---|---|
| **AlphaStar's league** (Vinyals et al. 2019): main agents; main exploiters that beat the current mains; league exploiters against the whole league; PFSP | (a) many agents train at once on large compute; (b) exploiters reset to a supervised human policy, which keeps them diverse; (c) strategy cycles exist and matter; (d) per-pair win rates are cheap; (e) exploiters find weaknesses within their budget (2-4·10⁹ steps); (f) mains patch what exploiters find | (a) **fails**: one GPU, one job; (b) **fails**: there is no human policy; (c) **unmeasured**: L is transitive, B9 unread; (d) holds: about 1,000 games an update; (e) **doubtful**: 211's exploiter gained +20 Elo in 4 h; (f) **doubtful**: the plateau | **Adopted with three changes:** (1) exploiters are time-sliced phases with the main paused, start from the snapshot they target, and stop when they find nothing (§3.3); (2) no league exploiters, which need parallel compute; (3) the league is insurance plus a measuring instrument, never a promised gain. Its branch structure is kept: self-play, PFSP over the past, a verification share |
| **PFSP's weightings** (the same paper). In AlphaStar the main agents weight their PFSP branch by f_hard = (1 − x)^p, and the main exploiters weight the main's checkpoints by f_var = x(1 − x) | win-rate estimates fresh enough to rank opponents; a pool spread in strength | **holds only while the league is small** (corrected after 216 G1). At the week's end there are about 40 members, an active set of 8, and a history branch of 0.25-0.55 of about 1,000 games. A member is then active about one update in five, at about 6-14 games an update on average. Its decayed estimate rests on 60-140 games: an SE of 0.04-0.065 near x = 0.5, and stale for a member not drawn in ten updates. The first draft's 0.02-0.03 holds only under about ten members. Near x = 0.5 the weights are flat (x(1 − x) is 0.25, 0.24 and 0.21 at 0.5, 0.6 and 0.7), so with this noise **PFSP is near-uniform over the history branch**, trimming only members the learner beats or loses to by a wide margin | **Adopted, with what it really does said aloud.** x(1 − x) over the past, as D22 settled: in AlphaStar it is the exploiters' function against the main, used here in the history branch by D22's decision (PLAN_CEILING §7.1's argument holds). (1 − x)², AlphaStar's f_hard with p = 2, only in the verification share, where the point is "make sure you can beat this one" (216 G3). **Forgetting is detected by X0's 48-hour sweep (200 deals a member) and by the floor, not by the weights.** The active set is drawn once per 5 updates, so an estimate rests on about five times the games at the same throughput; the iter row reports each estimate's SE beside x (§3.2) |
| **OpenAI Five's past-opponent sampling** (Berner et al. 2019): 80% self-play, 20% past versions by a learned quality score | the same as PFSP, with a bandit update in place of win rates | holds | **Considered, not adopted**: it does the same job as PFSP, and PFSP is settled (D22) with an evaluation trail behind it |
| **PSRO / double oracle** (Lanctot et al. 2017; McMahan et al. 2003): each new best response is trained against the population's Nash mixture, and the deployed agent is that mixture | (a) the full payoff matrix between members, N² entries with hundreds of games each; (b) a mixture of policies is what gets deployed; (c) each best response is trained close to convergence | (a) **fails** at any useful frequency: 20 members are 190 pairs, about 190,000 games at 500 deals a pair, 3-4 GPU-hours a refresh at evaluation speed (about 16 games a second, 205 §1); (b) **fails**: one network is deployed under a match clock; (c) **fails**: PPO's best responses are slow (211) | **Dropped as the training procedure.** The meta-game survives as an evaluation tool on a small spine of members (§2.2, §5.3) |
| **Fictitious play / NFSP** (Heinrich et al. 2015-16) | an average-policy network kept beside the best response | needs a second trained network, and an average policy is not our deployed player | **Dropped.** PFSP is its practical form |

### 2.2 Measuring strength and cycles

| Method | Its assumptions | Here | Conclusion |
|---|---|---|---|
| **Bradley-Terry / Elo against a frozen pool** (L; `tools/selfplay/rate.py:72-94`) | one scalar strength (transitivity); members that do not change; enough deals | holds while scores stay near even: L fitted with every pairing within \|z\| ≤ 2.0. It **degrades** as the learner pulls away: today's networks sit about +55 Elo above L's strongest member, and lopsided scores cost resolution | **Kept as the yardstick**, with an extension rule (§5.3): new members are rated against the frozen ratings, never refitted |
| **TrueSkill** (Herbrich et al. 2006) | multiplayer free-for-all; Gaussian skill | not needed for two players | **For Commander pods later**: PFSP's x per member then comes from a multiplayer rating (§4.1) |
| **Nash averaging** (Balduzzi et al. 2018); **α-Rank** (Omidshafiei et al. 2019) | a member-versus-member payoff matrix; for Nash averaging, a symmetric zero-sum game | the game is symmetric once seats swap within a deal; the matrix is costly (§2.1) | **Adopted as an evaluation tool** on a spine: about 6 snapshots plus the exploiters, 500 deals per pair, at registered reads. It flags cycles and rates without redundancy bias. Never a training input |

### 2.3 Choosing deals: curricula and environment design

The Teacher's half is here. Its key question is whether any signal is strong enough to steer by.

| Method | Its assumptions | Here | Conclusion |
|---|---|---|---|
| **Prioritized Level Replay** (Jiang et al. 2021) and **Robust PLR** (Jiang et al. 2021b): replay levels with high value loss | (a) a level replays exactly; (b) value loss on a replayed level tracks how much there is still to learn there; (c) one agent; (d) replaying a level teaches only what the level shows; (e) a level is replayed many times (buffers of thousands, replay probability about 0.5) | (a) **holds**: a seed replays exactly; (b) holds on a replayed seed, where the shuffle no longer adds luck; (c) partly: the opponent is part of the level; (d) **fails**: a replayed seed repeats the hidden library order, so the policy can learn "this opening hand, these draws". That is hidden information learnt through training (OWNER_PREFERENCES #1), and the owner forbade memorisation through deals (OWNER_VISION §2); (e) makes (d) worse | **Dropped in its replay form.** Three adaptations, all weaker: (i) the level is a deck pair replayed with fresh shuffles, which leaves memorising decklists, of uncertain value; (ii) the level is a recipe cell, which brings shuffle luck back into the score; (iii) a seed replays at most once, which is memorisation-safe but has unmeasured value. None steers the long run; (ii)'s scores are logged from day one (§3.8) |
| **PAIRED** (Dennis et al. 2020): an adversary builds levels that maximise the regret between an antagonist and the learner | a third trained agent and a generator trained by RL on a regret signal; about 3× compute | **fails**: one GPU, and an RL generator on a per-deal win/loss signal is the infeasible case DESIGN_TEACHER §1.1 measured | **Dropped.** Its useful core survives as an exploiter (a trained antagonist, §3.3) and as counter-drafting by a supervised critic (§3.6), never as an RL generator |
| **ACCEL** (Parker-Holder et al. 2022): small edits to high-regret levels | small, local edits; a reliable regret score per edited level | edits hold: one-card swaps, D0's operator. The score **fails**: per-level win/loss is noisy, and regret approximations track the success rate, not learnability (Rutherford et al. 2024) | **The edit operator is kept** (critic swaps). Regret-scored selection is dropped |
| **Learnability p(1 − p)** (SFL, Rutherford et al. 2024) | binary success, with its variance coming from the agent's own randomness on a fixed level | binary holds. On fresh deals, shuffle luck adds variance. Near-even play makes it flat: the learner's p sits at 0.45-0.55 against most of the league, where p(1 − p) varies by under 1% | **It is PFSP's weighting**: x(1 − x) over opponents is learnability over opponents, so it is used there. Over deal cells it is flat, and reduces to "skip lopsided deck pairs" (POET's minimal criterion). Not a steering signal now |
| **Teacher-student curricula** (Matiisen et al. 2017), **ALP-GMM** (Portelas et al. 2019), **bandits over tasks** (Graves et al. 2017) | per-task learning progress measurable between teacher decisions | **fails**: per-family progress sits below a rating's SE at 1-2 Elo an hour (PLAN_CEILING §9.1; DESIGN_TEACHER §1.1-§1.2, an SNR of 0.19 at 100 games) | **Dropped as the signal.** The bandit frame is kept for when a signal exists (§3.8) |
| **POET's minimal criterion** (Wang et al. 2019) | a cheap pass/fail filter on environments | holds: the critic predicts a deck pair's outcome (G2: slope 0.83) | **Kept as an option**: skip deck pairs whose predicted score for the learner's seat is outside [0.1, 0.9]. Off for now: lopsided pairs are rare among these recipes |
| **Reverse curriculum / puzzle starts** (Florensa et al. 2017) | arranged starts near a payoff | PLAN_PLANNING P2's item | **Not this plan's.** The interface: puzzle starts are a deal kind the recipe dispatcher can carry (§3.10) |

**What the checks decide for the Teacher.**
- The opponent half has a strong signal: thousands of games per member, which PFSP already uses.
  It is adaptive from day one.
- The deck half has none yet. The candidates are:
  - flat: learnability;
  - luck-bound: value loss on fresh deals;
  - memorisation-unsafe: seed replay;
  - below its SE: learning progress.

  So the deck half starts as a coverage curator: fixed registered shares with floors. It steers
  only once an instrument shows cells that differ beyond their noise (§3.8).

### 2.4 Building decks

| Method | Its assumptions | Here | Conclusion |
|---|---|---|---|
| **Evolutionary deck building** (García-Sánchez et al. 2016, Hearthstone) | a fitness per deck from many simulated games against fixed decks played by a fixed AI | **fails twice**: our pilots improve, so fitness moves, and a reliable fitness needs about 1,000 games a deck (G2's precision) | **Dropped as a search**. A surrogate takes its place |
| **MAP-Elites / quality diversity** (Mouret and Clune 2015); **with sliding boundaries** (Fontaine et al. 2019); **deep surrogate MAP-Elites, DSA-ME** (Zhang et al. 2022) | (a) a cheap, reliable fitness, which in DSA-ME is a learned surrogate retrained on evaluated decks; (b) behaviour descriptors that capture real diversity; (c) a stationary fitness | (a) a surrogate exists, the critic, but it is **pilot-relative**: it values what today's pilots win with, and that made tempo decks (193). A QD search on it would fill an archive with the pilot's comfort decks; (b) holds: component-derived descriptors (package, role, curve, colours) cost nothing; (c) **fails**: pilots improve, so elites age (BACKLOG's archive-refresh question) | **Deferred** until the critic is synergy-aware (C1) and pilots play synergies. Then it is the niche-deck archive of D14, re-scored at every refit, each elite confirmed in real games before it is dealt. For the long run, the recipes are a coarse hand-made grid over the same descriptors (§3.4) |
| **Q-DeckRec** (Chen et al. 2018): a learned win-rate predictor against a given opponent deck, searched for the best response deck | a fixed opponent pool and a fixed AI pilot | the critic is the predictor. Fixed pilots **fail**: refits follow the pilots | **Adopted as counter-drafting** (§3.3, §3.7), gated by the exploit scan |
| **Drafting by RL** (Vieira et al. 2020, Legends of Code and Magic; Ward et al. 2021, Magic) | many drafts with a win-rate reward, or human pick data (17lands) | **fails**: no human pick data for M20 or M21 (PLAN_CEILING §5.5), and a per-deck reward is too noisy for RL (DESIGN_TEACHER §5.1) | **The pick head is distilled from construction** (expert iteration over the critic's swaps, D2 in §3.7), never trained by RL on win rates |
| **Expert iteration for the pick head** (Anthony et al. 2017; DESIGN_TEACHER §4.5's masked deck modelling) | an expert better than the apprentice; its targets learnable | the expert is D1's swap search on the critic: better than the apprentice by the critic's own lights, so it inherits the critic's pilot-relativity | **Adopted for D2, after C1.** The pick head imitates construction, and play checks its decks (G2-style, real games), never the critic's opinion of them |
| **DESIGN_TEACHER's probe-delta reward** (2026-09-10): the drop in loss on a frozen probe bank caused by a block of games | blocks of games on one deck; probe gradients per block; the γ experiment answered | **fails today**: decks change every game, there are no blocks, and the γ experiment was never run on this stack | **Parked.** Its two lasting ideas are kept: pair on identical states, and pool over many decks |

### 2.5 Keeping the value function honest under a moving opponent mix

| Method | Its assumptions | Here | Conclusion |
|---|---|---|---|
| **A centralised or privileged critic** (MADDPG, Lowe et al. 2017; AlphaStar's value saw the opponent's observations) | the critic may read training-only information | **refused**: "no privileged critic, ever" (PLAN_CEILING's rulings) | **Dropped** |
| **Fingerprints** (Foerster et al. 2017): the value reads the training iteration or the opponent's identity | that identity is an input | the same ruling; a play-time value cannot have it | **Dropped** |
| **Per-opponent advantage centring** (PLAN_CEILING §7.1: "a setting") | the opponent's identity in the training computation only | still training-only information. The policy gradient stays unbiased (the opponent is drawn before the game), but it is near the ruling's edge | **A setting, off.** It is registered only if §3.5's monitor shows a group the value cannot read |
| **Phasic policy gradient** (Cobbe et al. 2021), **a detached value head**, **a lower value coefficient** | the value loss reaches the policy through a shared trunk | holds: 189 §8 | **PLAN_LONG_RUN item 2's decision, not this plan's.** It interacts (§3.5) |

---

## 3. The design

### 3.1 One system, five parts

| Part | What it decides | What it is | Status |
|---|---|---|---|
| **The league** | who may sit opposite: the registry of frozen members | a file per run (`league.json`) and the snapshot rule | new |
| **The matchmaker** (the Teacher's opponent half) | who sits opposite in each game | PFSP over the league's branches | new |
| **The deal curator** (the Teacher's deck half) | each seat's deck recipe | a registered mix with floors, logged per cell; it adapts later (§3.8) | new; package and drafted recipes exist |
| **The critic** (shared, D15) | a deck pair's predicted result given the pilots, and each member's deck-adjusted strength | C0: a logistic regression per card and per pilot (built). C1: a set network over component embeddings (later) | C0 built, needs a refit |
| **The drafter** (D15, D16) | a deck, from a fresh start | D0: k critic swaps (built); D1: C1's swaps and a counter mode; D2: a pick head | D0 built |

The Teacher is the matchmaker plus the deal curator: a curator, not a reinforcement-learning
agent (D15). It shares the critic with the drafter. The matchmaker is adaptive from day one; the
curator steers once its signal is shown to be real.

### 3.2 The league

**Members and lineages.** A member is a frozen player:
- a snapshot of the learner;
- an external network;
- an exploiter;
- a scripted player;
- later a searched player.

Its registry entry holds a name, kind, lineage, path, sha256 and the update it joined at. Every
member's file is pinned in `reports/LARGE_FILES.sha256` before it is used. The registry refuses:
- a member whose sha256 matches a member of L. L never trains (PLAN_CEILING §7.2): r26's v0-v2,
  u1000 and r27's v1 are out, and so is r28's v0, r27's v1 under another name;
- a member whose file no longer matches its pin.

**The first members:**
- the learner's v0 (its init);
- r28's v1 (update 352): another training history, weaker;
- the exploitability probe's exploiter (`runs/selfplay/probe_exploit_v2/last.pt`, update 60, kind
  exploiter): 211's main exploiter of r28's v2;
- the heuristic.

r28's v1 and the probe exploiter are not pinned yet; pinning them is a build step (§6). So is
loading each into the long run's card table: `_load_net` accepts a member only when its table is
a prefix of the learner's (`learner.py:426-431`), and runs that refreshed their tables at
different commits may fail that. A member that fails is dropped, never patched.

**Snapshots.** A snapshot is taken when a gate passes, as today, or **100 updates after the last
snapshot** (AlphaStar's forced checkpoint).
- Gates stay every 25 updates, as reads.
- Over a 7-day run, at about 165 s an update, that is about 37 snapshots.
- This removes the "Self-play gate" scaffold's harm: the pool grows whether or not the learner
  clears 0.55.

**The branches.** Each training game draws a branch, then a member within it. The shares are said
aloud (§4.4) and depend on r29's B8 (`--p-self` 0.55 or 0):

| Branch | Members | Weighting within | Share, p_self 0.55 | Share, p_self 0 | AlphaStar's |
|---|---|---|---|---|---|
| self | the learner, both seats trained | — | 0.55 | 0 | 35% SP |
| history | snapshots, external networks, exploiters the learner beats (x ≥ 0.7) | x(1 − x), D22; a floor: 10% of the branch uniform over its members, a trickle to every one | 0.25 | 0.55 | 50% PFSP |
| verification | exploiters with x < 0.7; snapshots with x < 0.5 (forgotten) | (1 − x)². Empty: falls to history | 0.10 | 0.25 | 15% |
| anchor | the heuristic | — | 0.10 | 0.20 | — |
| searched | the newest snapshot plus search | — | 0, a setting at most 0.03 (PLAN_CEILING §7.1) | 0 | — |

x is the learner's score against the member (a win 1, a draw 0.5).

**The payoff estimate.**
- Counts of the learner's results against each member, from training games, decayed by 0.9 per
  update: about 10 updates of memory.
- **Its precision** (corrected after 216 G1).
  - With a handful of members, a member gets about 50 games an update, and the SE is near 0.03.
  - At the week's end, about 40 members, a member is active about one update in five, at 6-14
    games an update on average. Its estimate rests on 60-140 games: an SE of 0.04-0.065.
  - So the x(1 − x) weights are near-uniform over the history branch: they trim the extremes
    only.
  - The iter row reports each estimate's SE beside x, so this is visible, not assumed.
- A member never played reads x = 0.5 (AlphaStar's convention), which gives a newcomer full
  weight until it is measured.
- The critic's pilot terms give the same strengths with deck luck regressed out. They are reported
  beside the counts at every refit, not used for drawing.
- **A rarely drawn member's estimate goes stale**, and a stale x can hide forgetting. With 40
  members, the floor gives each under one game an update. So every 48-hour read sweeps the whole
  league: 200 greedy deals against every member, about 20 minutes. A member the learner now
  scores below 0.5 against moves to the verification branch.

**The active set.**
- Each frozen network costs a forward per inference batch (`learner.py:692-757`: requests are
  grouped by model). Many members means many small batches.
- So **every 5 updates** draws up to **K = 8 distinct networks**, without replacement, by the
  branch weights; scripted members are free. Games go only to the active set until the next draw.
  - **Why 5 updates, not 1** (216 G1). The same throughput, fewer and longer exposures: an active
    member's estimate rests on about five times the games, and fewer members are loaded lazily.
  - **The cost:** each update's opponents are less varied. Over 5 updates the set is the same 8.
  - **Said aloud** (§4.4). What removes it: a measured payoff SE at which per-update draws rank
    members as well.
- K is a performance scaffold, set by the GPU smoke's throughput curve (§5.1).
- Inactive members stay on disk. They load lazily through `_load_net` (`learner.py:418-434`),
  which already checks that a member's card table is a prefix of the learner's.

**Redundancy.** Thirty near-identical snapshots would swamp three exploiters if all shared one
PFSP pool. Branch shares are per lineage, as AlphaStar's are, so exploiters keep their share
however many snapshots pile up. Nash averaging (§2.2) reports the main's rating with redundancy
removed.

### 3.3 Exploiting experts

**Main exploiter phases.**
- **The protocol** is 211's, which already ran once:
  - the main stops at a save;
  - an exploiter run starts, trained only against the newest snapshot
    (`--p-heuristic 0 --p-past 0 --p-self 0`), on the main's deck mix;
  - **its init alternates** (216 G2):
    - odd phases start from the target itself;
    - even phases start from another lineage already in the registry: r28's v1 now; later the
      heuristic-imitating start of PLAN_CEILING §8, or a specialist.

    Why: AlphaStar resets its exploiters to the supervised policy to keep them diverse. An
    exploiter started at its target's own weights searches only the target's neighbourhood. 211
    did exactly that (an exploiter from v2 against v2): +20 Elo greedy in 4 h, the sampled win
    rate flat at 0.50, "no line v2 fails to answer". Alternating costs nothing extra.
  - its gates run every 10 updates on 1,000 fresh deals, and it never freezes
    (`--gate-score 1.01`).
- **Length: 8 machine-hours, one phase every 48 machine-hours of main training** (14% of machine
  time).
  - **Why 8.** 211's exploiter gained about +20 Elo in 4 h against a fixed target, about
    5 Elo/h, while its plateaued main gained 0. At that rate a 0.55 exploiter (+35 Elo) needs
    about 7 h.
  - **Why every 48.** It bounds the cost while the main is the priority.
- **It always joins at the end.** Its final x places it in verification (x < 0.7) or history.
- **The stop rule, per init kind** (216 G2): two consecutive phases of one init kind whose final
  gate is below 0.55 end that kind. When both kinds have ended, the time returns to the main. X1
  is recorded per init kind.
- **A flag at 0.60 or more** (211's): replay its winning games and judge each line, legal Magic
  or an engine fault. A fault is fixed by its cause (the bug-hunt protocol, 209 §9).
- **What a phase reads:**
  - X1, its climb: the main's exploitability at that point;
  - X2, how fast the main patches it once it has joined (§5.3).

**Specialists** (PLAN_CEILING §14.3; PLAN_PLANNING P2).
- An exploiter phase whose own seat is dealt one recipe, for example counterspell-role decks, is
  a specialist: it practises one skill against the main, then joins as an opponent.
- **Not scheduled.** Its trigger is registered: B or D puzzle pairs still at 0 after the long
  run's first 1,000 updates with the planner in.

**Deck exploiters (counter-drafting).**
- The critic gains an interaction term per card: its value when the opponent is the learner,
  beyond its value in general. A counter recipe swaps toward cards that beat the learner.
- **Gated** on the exploit scan flagging a card or pair the learner handles badly: a learner-seat
  lift below the opponent seat's, FDR q < 0.05.
- **Why gated.** The scan of 211's games found no learner-specific card (the largest gap at
  z 2.25, Bonferroni 3.89). An ungated counter-drafter would be ridge-shrunk back to plain drafting.

**Searched members.**
- The newest snapshot plus search at n = 4 is +46 Elo over its raw self (205 §9).
- One such game costs about 1 + 2.3n plain games, about 10 at n = 4 (PLAN_CEILING §6.1). At 3% of
  games that is about 24% of collection.
- **Off.** It comes on at 3% or less only if the smoke shows collection slack that absorbs it:
  arm B was train-bound.

**How experts feed the main without passing on their incentives.**
- Only as opponents. Their frozen weights act in the opponent's seat, and the main trains on its
  own seat's ±1.
- Nothing is distilled from them, and no fading pull is used (D8).
- An exploiter's narrow objective (beat snapshot k) and a specialist's forced frequency never
  enter the main's loss.

### 3.4 The deals

**A recipe per seat.**
- Each seat's deck comes from a recipe, drawn independently per seat. Different recipes face
  each other: a counterspell deck against a package deck.
- Every deck is built from the deal's seed and the seat, so every deal is fresh, and a seed
  rebuilds its decks.

| Recipe | What it deals | Code | In the long run's mix (per seat) |
|---|---|---|---|
| `coherent` | today's deck | `games.build_coherent_deck` | 0.40 |
| `package` | a component-derived synergy package: 8 consumer and 8 producer copies, filled as coherent | `packages.build` | 0.20 |
| `role:counter`, `role:sweeper` | **new.** 4 copies of a component-derived role, in a colour pair that holds them, filled as coherent | §3.10 | 0.10 + 0.10 |
| `drafted:8:<critic>` | coherent, then 8 critic swaps inside the coherent band | `decks.drafted_decks` | 0.20 (M21 and M20; FDN once its games are fitted) |
| `counter:<k>:<critic>` | the deck-exploiter recipe | §3.3 | 0 until gated |

**Roles are read off the compiled trees, as packages are.**
- A counterspell is a card with a `COUNTER_SPELL` atom.
- A sweeper destroys, damages, exiles, bounces or shrinks (a `MODIFY_PT` with a `DECREASE`
  toughness) every battlefield object a `Selector` of mode `ALL` picks, whose filter names
  creatures or permanents.
- The census script holds the definition. It caught a false positive (Idol of Endurance moves
  creature cards out of a graveyard) and excludes it. That case becomes a test.
- No card names are read, so a new set's roles need no code.
- 4 copies put one in the first 12 cards 60% of the time (hypergeometric: 1 − C(56,12)/C(60,12) =
  0.601), against 9.2% for counterspells in M21's coherent decks.

**What the mix does to frequency** (M21, by the census; drafted decks assumed to hold
counterspells as coherent ones do):
- A seat holds a counterspell by turn 6 in about 24% of games, from 18%.
- It holds a sweeper in about 19%, from 10%.
- That is a modest rise, said honestly. Frequency of whole natural games is this plan's lever;
  arranged puzzle starts are PLAN_PLANNING P2's.

**Why these shares** (each one a scaffold, §4.4):
- **Coherent stays the plurality.** It keeps continuity with every network's training so far and
  with L's coherent anchor.
- **Package and drafted at 0.2 each.** They close the measured familiarity gap. Drafted stays at
  0.2 because its decks are pilot-comfort decks that remove skill-heavy cards (§3.6's loop).
- **Roles at 0.2.** Role decks put the skill-heavy cards back: counterspells and sweepers.

**Sets.** M21, M20 and FDN as the long run registers them (`--mix-sets`). A recipe that needs a
critic for a set without one falls back to coherent for that set's deals, logged.

**Gates and reads.**
- Gates deal the training mix, so they measure the trained distribution.
- L is read on its own three frozen shapes: coherent, package, and `drafted:8:6b8014ae` (205's
  critic, kept for comparability).
- Role decks are reported beside L, against the heuristic and a reference snapshot. L was not
  fitted on them.

**What else reads the deals.**
- **The critic and the exploit scan.**
  - `train_rows.jsonl` records each seat's recipe (with its critic hash), each seat's member and
    the branch.
  - `decks.py rebuild` rebuilds every recipe at the run's commit, extracting `tools/selfplay` with
    `MTG_bot`.
  - The exploit scan reads every recipe.
- **The opponent simulator's captures** deal coherent or stress decks only today: `_job` gives
  package decks to training and evaluation jobs alone (`learner.py:548`). The wiring (B1) gives
  captures the training mix, so the simulator learns the decks the learner meets.
- **The search's uniform worlds** draw hidden cards from the pool, not from the recipe. Against a
  role or package deck they misdraw more, as 205 §5 noted for packages. The simulator's worlds are
  the fix. This matters to searched members and to PLAN_PLANNING P3, not to T1.

### 3.5 The moving opponent mix and the value function

The brief: say how non-stationarity is kept from corrupting the value function. Five parts:

1. **Targets cannot compound.**
   - With γ = λ = 1 the advantage telescopes to z − V(s_t) (`gae`, `learner.py:254-267`), and the
     return is z.
   - A value error at one state never enters another state's target. A change in the mix moves
     the regression target E[z | s], and that is all it moves.
   - With λ < 1, a stale value would bias the advantages themselves. Full credit is also the
     protection here.
2. **What the value means.**
   - V(s) = Σ P(member | s, mix) · E[z | s, member].
   - It reads the opponent only through the visible state: their cards, their play. It never
     reads a label (OWNER_PREFERENCES #1; no privileged critic).
   - It is honest about the population it was trained against. That is also its limit at play
     time, as any value's is.
3. **The policy gradient stays unbiased whatever the value's lag.**
   - The baseline is a function of the state. The member is drawn before the game, independently
     of the learner's actions, so E[∇log π(a|s) · b(s, member)] = 0 for any such b.
   - A lagging value costs variance, not direction (Williams 1992; Greensmith et al. 2004).
   - **The assumption this rests on** (216 G7): the policy is trained by PPO alone. With the
     planner on, the policy is also trained by a supervised side loss (DESIGN_PLANNER §3.1), and
     the baseline argument does not apply to that loss. Its effect is read by the planner's own
     arms (DESIGN_PLANNER §5), not argued here.
4. **The rate of change is bounded:**
   - payoff estimates decay over about 10 updates;
   - a new member enters at x = 0.5, inside its branch's share;
   - at most one exploiter joins per phase, and its branch is capped at 0.10;
   - the deal mix is fixed within a segment;
   - critic refits, which change the drafted recipe, happen only at registered segment
     boundaries.
5. **It is watched, and the remedy is not this plan's.**
   - Every update logs, per branch and per recipe:
     - the value's explained variance;
     - the mean residual z − V over each game's last third of decisions. By then the state
       reveals most of the opponent.
   - The registered reading: a group whose explained variance stays below half the overall for
     10 updates is a group the value cannot read.
   - Its remedies are PLAN_LONG_RUN item 2's (a detached value head, PPG, the coefficient) or
     memory (history features identify an opponent).
   - Per-opponent advantage centring stays an off setting (§2.5).

**The interaction with item 2.** Today the value loss reaches the policy through the shared trunk
(189 §8). So value-target drift from a mix change can become policy drift. If item 2 detaches the
value head or adopts PPG, the drift stays in the value head. This design does not depend on that
choice, but is safer with it.

### 3.6 The critic

**C0, now.**
- `decks.py fit`, refitted on r29's coherent games between networks. That is about 290,000 so
  far over both arms: A's 162,000 games and B's 176,000, less the heuristic's 15%. Then on the
  long run's games at each segment boundary. A self game's pilots cancel, so it is clean data on
  decks.
- The pilot terms become per member. That gives the deck-adjusted strengths of §3.2.
- Its band (`band_of`, `decks.py:330-345`) is recomputed per set.
- FDN has no games yet. Its cards get values after the long run's first segment.

**C1, later** (CPU, from logged games; no GPU).
- A set network: deck A's cards and deck B's cards as tokens, with role tags, plus the pilots'
  terms and the seat. Pairwise attention, so it can value "A with B" (DESIGN_TEACHER §3.2).
- Its card vectors come from the game network's component embedding
  (`PolicyValueNet.card_table_emb`, `model.py:101-109`). These are inherited representations
  (D8), so an unseen card built from known components gets a value on day one. That is the
  King-tied goal applied to the critic.
- **Its gates:**
  - held-out log-loss beats C0 (5 folds grouped by seed, as G1), and its calibration holds;
  - **a zero-shot read**: fitted without FDN games, C1's predictions on FDN deals beat a
    colour-and-summary baseline on the first FDN games. Otherwise it waits for the planner's
    pilots.

**Pilot-relativity, and the loop it could close.**
- The critic values cards by how today's pilots win with them (193: Spectral Sailor near the
  bottom).
- Drafting on it removes skill-heavy cards. Training on drafted decks then shows the learner
  fewer of them, the pilots never learn them, and the critic keeps undervaluing them.
- **What the mix costs those cards, worked out.** Take a card that is in no package and no role.
  Its expected copies per deck, against a coherent-only diet:
  - coherent 1.0;
  - a package deck about 0.56 (only 20 of its 36 spells are drawn freely);
  - a role deck about 0.89 (32 of 36);
  - a drafted deck about 0 if the card is in the critic's bottom 20.

  Under the 0.4/0.2/0.2/0.2 mix that gives about 0.69 of today's exposure for the critic's bottom
  20, and about 0.8-0.9 for the other cards.
- **Three guards:**
  - the drafted share is capped at 0.2;
  - role recipes put counterspells and sweepers back in;
  - **a floor, read at each refit (X6):** the measured exposure of the previous refit's bottom-20
    cards across the whole training mix (from `train_rows.jsonl` and the rebuilt decks), relative
    to coherent-only. It must stay at or above 0.6; below that, the drafted share is halved. Their
    C0 values are reported across refits: values that rise say the pilots learned those cards.
- The real fix is a critic fitted on a better pilot: a searched pilot, or the planner's network
  (PLAN_CEILING §14.4).

### 3.7 The drafter

- **D0, in the long run.** k = 8 swaps on a fresh coherent deal by the refitted C0, inside the
  band (`decks.swap`, `drafted_decks`).
  - Randomness (D16) is the fresh start deal; k states how much of the critic's value is spent.
  - No nicheness knob: there is no reference population yet (DECISIONS R8).
- **D1, after C1.** Swaps by C1, which sees pairs, so the decks can hold synergies the pilots
  exploit. A counter mode (§3.3) swaps toward a named opponent deck or pilot.
- **D2, the pick head.** A pointer over the pool, distilled from D1's construction (expert
  iteration; DESIGN_TEACHER §4.3-§4.6).
  - It covers NORTH_STAR §4a's three modes: from start, completer, counter-drafter.
  - It needs no RL on win rates (§2.4).
- **Nicheness and QD.** MAP-Elites over component descriptors, with C1 as the surrogate, re-scored
  at each refit. Each elite is confirmed in about 1,000 real deals before it is dealt (G2's
  precision).
  - Nicheness is low density under a reference that is not our own archive: the uniform
    coherent generator, plus any human deck corpus that can be acquired. That addresses R8's
    circularity as far as it can.
  - It is after D2.

D16's two knobs, as they stand:
- **Randomness:** the fresh start, and later a sampled intent.
- **Nicheness:** a directed move to another archive cell, later.

Neither is a temperature over picks.

### 3.8 The Teacher's adaptive half (T2), registered now, switched on later

**The instruments, from the long run's first day.** A cell is a deal's unordered pair of recipes:
15 cells with five recipes.
- **Per-cell learnability:** the learner's score per cell, in training games.
- **Per-cell pilot sensitivity.** In every gate, the share of paired deals in which the same pilot
  wins both games, so the winning seat changes (193's G4 measure), per cell.
  - Between near-equal pilots, it reads how much small differences in play change the result.
    A deal decided by its decks and seats is won by the same seat twice. In a deal sensitive to
    decisions, the same pilot often wins both.
  - Gates already play 1,000 paired deals, about 70 per cell. At one gate every 25 updates, about
    21 a day, that is about 1,400 deals per cell a day: an SE near 0.012 per cell.
- **Per-cell value loss**, mean |z − V| (PLR's score on fresh deals). It is reported knowing that
  luck dominates it.

**The rule** (registered now, applied at the first read after 3 machine-days, and decided at most
once a segment):
- **When it switches on:** the cells' pilot sensitivities differ by more than 3 SE (max against
  min), **and** their ranking is stable between the data's two halves (Spearman ≥ 0.6).
- **What it does then:** each recipe's share becomes base × (1 + (s_r − s̄)/s̄), each between 0.5×
  and 2× its base, renormalised. Here s_r is the mean sensitivity of the cells holding recipe r,
  weighted by how often each is dealt, and s̄ is the mean over all deals.
- **Otherwise** the mix stays, and the reading is reported.

**What it cannot prove.** That the reweighting raises L faster. PLAN_CEILING §9.1's gate (1.3× the
L per machine-day of fixed deals, 3 seeds per arm) costs six multi-day runs. It is the owner's
call when to spend them, after H1-class runs.

**What is not built:**
- **Handicaps** (the owner's "deliberate unfair advantages", OWNER_VISION §6). G4 says stronger
  decks make deals more deck-decided, so handicaps would raise the outcome variance and lower the
  share decided by play. The per-cell sensitivity read measures it before anything is built.
- **A Teacher trained by the Student's learning** (OWNER_VISION §6). Not at this signal-to-noise
  ratio (§2.3).

### 3.9 Data flow

```
 league.json ─┐                 ┌─ payoff (decayed x per member) ─┐
 snapshots ───┤                 │                                  │
 exploiters ──┴─> matchmaker ───┼─> job: branch, member,           │
                                │   recipe per seat, set           │
 critic ─────> deal curator ────┘          │                       │
   ^                                       v                       │
   │                             workers play (recipes.build)      │
   │                                       │                       │
   │                train_rows.jsonl <─────┴─> results ────────────┘
   │                (seed, set, recipes, members, branch, outcome)
   │                       │
   └── decks.py fit <── decks.py rebuild (every recipe, at the run's commit)
                           │
                           └──> exploit_scan ──> flags ──> deck exploiters (gated)
 queue: main ─48 h─> exploiter phase (8 h) ─> pin ─> league.json ─> main resumes
```

### 3.10 Files, flags, tests, metrics

**New modules.** They are pure Python and touch no file the planner build edits.
- **`tools/selfplay/league.py`.** The registry (load, pin check, refusing L), the payoff, the
  branches and PFSP, the active set, the snapshot rule, and its run state. Seeded draws use
  `MTG_bot/utils/rng.py`'s `teacher` stream via `substream("teacher", seed)`.
- **`tools/selfplay/recipes.py`.**
  - It parses a recipe spec and builds one seat's deck: `build(seed, seat, spec, supply,
    critics)`.
  - For `coherent`, `package` and `drafted` it reproduces today's decks byte for byte: it draws
    both deck seeds from today's streams and returns the seat's.
- **`packages.py`.** A `ROLES` table beside `ACTS`, and `roles(supply)`, holding the census's
  definitions.

**Changes to existing files.** These come after the planner merges; they are small and named in
§6:
- `learner.py`, `actor.py`: the wiring;
- `ppo.py`: per-group statistics;
- `decks.py`: rebuild every recipe;
- `exploit_scan.py`: read every recipe.

**Flags. Every default is today's behaviour:**

| Flag | Default (today) | Long run |
|---|---|---|
| `--league FILE` | none: `curriculum_job` exactly as now | the run's `league.json` |
| `--league-shares` | — | per B8, §3.2 |
| `--league-floor` | — | 0.10 |
| `--payoff-decay` | — | 0.9 per update |
| `--league-active K` | — | 8, or the smoke's |
| `--snapshot-every N` | 0: only gate passes | 100 |
| `--deal-mix SPEC` | none: `--coherent-share` and `--package-share` as now | §3.4's mix |
| `--draft-critic` | exists (eval only) | the refitted C0, now also for training |

**Tests. Each named "fails" fails on today's code:**
1. A run whose gates never pass gains a snapshot at `--snapshot-every` (fails: no freeze without
   a pass).
2. The branches, weightings, floor, an empty verification branch falling through, and a
   newcomer's prior x = 0.5.
3. The registry refuses an L member and a member whose file differs from its pin (fails: no
   registry).
4. With default flags, the job stream (opponents, decks, seeds) equals today's for the same seed.
   This guards the default.
5. `recipes.build` deals byte-identical decks to `deal_decks`, `package_decks` and
   `drafted_decks` for today's modes.
6. Roles: Cancel, Negate and Essence Scatter are counterspells; Flame Sweep, Planar Cleansing and
   Massacre Wurm are sweepers; **Idol of Endurance is not**. A role deck holds 4 role copies, is
   legal, and is a function of (seed, seat, spec).
7. `decks.py rebuild` reproduces package, role and drafted decks (fails: `MODES` drops them,
   `decks.py:41`).
8. The exploit scan reads every recipe (fails: `exploit_scan.py:620`).
9. `train_rows.jsonl` carries the member, the branch and each seat's recipe (fails: they are
   absent).
10. A resume restores the league's state: registry version, payoff and last snapshot.
11. **With the planner's agent:** a frozen member saved before planner v1 gives bitwise-equal
    logits on a fixed batch when loaded into the post-planner learner.

**Metrics, checked against METRICS §17:**

| Metric | A null policy | Paired with |
|---|---|---|
| familiarity gap (shape minus coherent, against the heuristic) | **0: looks perfect** (equally bad everywhere) | each shape's level, and L per shape |
| exploiter climb (X1) | an exploiter that fails to train climbs 0 and reads "robust" | the exploiter's own sampled win rate and per-kind KL, which show it learns; 211's +20 Elo in 4 h as the reference |
| patch rate (X2) | a frozen main never patches: not favourable | — |
| cycle flags (X3) | identical snapshots show no cycle | the snapshots' L ratings must differ |
| pilot sensitivity per cell (§3.8) | identical pilots give 0 everywhere | the gate's own score |
| per-branch value EV (§3.5) | a constant value gives about 0: not favourable | — |

`ST-8`, win rate against self, stays deleted. No read here uses it.

---

## 4. The logic check

### 4.1 Against the project's goals

- **King goal.**
  - The league keeps a days-long run from cycling and forgetting, and measures exploitability.
  - The deal mix closes a measured weakness, play on unfamiliar deck shapes, and raises how often
    planning situations arise.
  - Neither claims to break the plateau, and none of the reads is scored as if it did.
- **Learnable over hardcoded.**
  - The opponent choice follows measured win rates (PFSP), not a schedule.
  - Exploiters are trained, not scripted.
  - Roles and packages are read off components.
  - The fixed shares, copies and intervals are scaffolds, each said aloud in §4.4 with what
    removes it.
  - Nothing touches the reward.
- **Generalisation through components.**
  - Packages and roles derive from typed verbs, so FDN needed no code (18 packages, 6 counterspells
    and 5 sweepers found).
  - C1 values cards from component embeddings.
  - Every deal is fresh, so no deck or draw is memorised.
- **Honesty.**
  - No member sees a hidden zone.
  - The value reads no opponent label.
  - The critic reads decklists only to build deals; the learner never sees its output.
  - Seed replay is refused because it would teach hidden draws (§2.3).
  - Counter-drafting uses what an opponent could know from play (tendencies), never a hidden
    card.
- **The ceiling.**
  - Nothing masks an action or changes the reward.
  - Opponents and decks change what the learner meets, not what it is paid for.
- **Commander.**
  - The matchmaker draws N − 1 members per pod.
  - x comes from a multiplayer rating (TrueSkill or Plackett-Luce) as a predicted head-to-head
    score.
  - Recipes generalise: singleton is a copy limit of 1 plus a commander's colour identity as the
    pair, and packages and roles derive the same way.
  - C1 takes N decks.
  - Nothing is built for Commander now (PLAN_LONG_RUN: not before the long run).
- **Latency.**
  - Nothing is added to a decision at play time: the deployed network is the main learner alone.
  - Training throughput is the cost, measured (R3) and capped (KL1).

### 4.2 What could go wrong, and why the design survives it

| Risk | Why it survives |
|---|---|
| Many members fragment inference batches; throughput falls | Active set K, set by the smoke; R3 before launch, KL1 in the run |
| Old snapshots pile up and dilute exploiters | Lineage branch shares; redundancy-free Nash rating at the reads |
| A stale x hides forgetting of an old member | The floor's trickle, and the 48-hour sweep against every member (X0); "forgotten" snapshots move to verification |
| An external member's card table is not a prefix of the long run's (runs that refreshed from one ancestor at different commits append in different orders) | `_load_net` refuses it (`learner.py:426-431`), so it cannot be loaded wrongly. Step A4 loads each candidate into the long run's table first; one that fails is dropped, never patched |
| Exploiters find nothing and waste time | The stop rule (two null phases); 211's prior says this is likely, and the reading itself (exploitability) is worth 16 h |
| An exploiter finds a fault, not a strategy | 211's flag-and-replay protocol; a fault is fixed by cause before training continues on it |
| The value lags a mix change | MC targets, bounded change, the per-branch monitor (§3.5); the policy gradient stays unbiased |
| New recipes surface engine faults (dense role or package decks) | 10,000 games in the smoke; KL3: a recipe with voids above 0.5% is switched off until fixed |
| Drafted decks close a pilot-comfort loop | Capped share; roles; the exposure floor of 0.6 on the critic's bottom-20 cards (§3.6, X6) |
| L loses resolution as the learner pulls away | The extension rule (§5.3) |
| A frozen pre-planner member computes differently after the planner's columns | Interface test 11 with the planner's agent (§6) |
| Each exploiter phase is a resume, and AdamW's moments restart | PLAN_LONG_RUN item 6 (save the optimizer state) is a dependency; until it lands, each phase costs one moment restart, recorded |

### 4.3 The assumptions behind each conclusion, and what follows if one is wrong

| Conclusion | Assumption (whose) | If wrong |
|---|---|---|
| A league in the long run | Multi-day self-play risks cycling and forgetting (field; mine) | No cycles: the league costs its throughput tax (at most 10%, KL1) and some games against weaker selves. Small, and X3 shows it |
| | "A league with exploiters" helps (owner) | Exploiters find nothing: the stop rule ends them after 16 h, and the PFSP part stays as cheap insurance |
| | Sampled training win rates rank members well enough (mine) | Sampled and greedy diverge (211: 0.50 against 0.53): weights misallocate mildly; the floor bounds the damage |
| Exploiters of 8 h | They climb at about 211's 5 Elo/h against a fixed target (mine, from one probe) | Slower: two null phases, then stop; the read "not exploitable at this budget" is reported as bounded by the budget, never as "robust" |
| PFSP x(1 − x) in history, (1 − x)² in verification | The learner is near the top of its league (mine) | A much stronger member (F1, later) would draw too many lost games: the curriculum fallback of AlphaStar's self-play branch (play that member's weaker checkpoints by x(1 − x)) is the registered extension |
| The 0.4/0.2/0.2/0.2 deck mix | Training on a shape closes its familiarity gap (mine, from 205) | Gap persists: the shapes cost coherent practice; R1/R2 and X4 show it, and the mix moves back toward coherent. **Said plainly** (216 G6): the familiarity gain is bought with coherent practice. Each seat is coherent 40% of the time, so both seats are coherent in 16% of games, while L's anchor and r29's whole history are coherent. X4's "coherent L not below the init's" is the standing guard |
| | "Realistic decks have a higher skill ceiling" (owner) | Not relied on: 205 found no extra one-turn headroom; the mix rests on familiarity and frequency |
| | "Deals that hold synergies" teach synergies (owner) | Not relied on as a gain: 202 found no package line with value; packages are coverage |
| | More frequent counter and sweeper situations help planning (mine) | The bottleneck is the signal (214), not frequency: role decks cost little (they are real decks), and the planner and value items carry the gain |
| The deck half waits | The cheap signals are flat, luck-bound, unsafe or below SE (mine, §2.3, from measured numbers) | One is not: the per-cell instruments show it within days and the T2 rule switches on |
| | "A Teacher trained by the Student's learning" (owner, OWNER_VISION §6) | Feasible later at higher SNR (better learner, longer runs): the bandit frame of §3.8 takes the signal |
| The value survives the mix | γ = λ = 1 stays (owner) | λ < 1 would let a stale value bias advantages: this design then needs per-group calibration as a gate, not a monitor |
| | Value drift through the trunk is small (mine) | Item 2's detached head or PPG removes it |
| The critic serves the drafter and the reads | Deck values carry to play (G2's 0.83) | They drift with the pilots: refits at segment boundaries, G2-style calibration at each |
| | The drafter can draft intelligent decks (owner) | "Intelligent" means "what today's pilots win with" (193): C1 and better pilots first, QD after |
| Fresh deals only | No memorisation through deals (owner, OWNER_VISION §2) | If the owner allows bounded replay, PLR's once-replay adaptation (§2.3) becomes a T2 candidate |

### 4.4 Every hand-set number, for BACKLOG "Scaffolds to remove" (entered when built)

| Number | Value | Why this value | What removes it |
|---|---|---|---|
| Branch shares | §3.2 table | AlphaStar's 35/50/15 scaled to r29's self share; the heuristic as today minus 0.05 | A meta-solver's mixture over lineages, once the member matrix is cheap enough (§2.1) |
| History floor | 0.10 | a trickle of games to every member; the 48-hour sweep (§3.2) refreshes every estimate | Thompson sampling over members' posterior x |
| Payoff decay | 0.9 per update | about 10 updates of memory; an SE near 0.03 only while the league is small, 0.04-0.065 at about 40 members (216 G1) | A Bayesian estimate with a drift model |
| Verification thresholds | exploiter x < 0.7; forgotten x < 0.5 | AlphaStar's 70% join rule; "no longer beats" | The meta-solver above |
| Active set K | 8, set by the smoke | throughput | Batched multi-model inference (stacked weights) |
| Active-set draw | every 5 updates | about five times the games per estimate at the same throughput (216 G1) | A measured payoff SE at which per-update draws rank members as well |
| Snapshot timeout | 100 updates | about 4.6 machine-hours; 37 snapshots a week | Snapshots by measured policy change (KL from the last snapshot) |
| Exploiter phases | 8 h every 48 h; inits alternating (the target, another lineage); stop a kind after two of it below 0.55 | 211's rate; a 14% cap; diversity of starts (216 G2) | Co-trained exploiters on a second GPU |
| Deck mix | 0.4/0.2/0.2/0.2 | coverage; the familiarity gap; the drafter's bias capped | T2's rule (§3.8), then the drafter's decks |
| Role copies | 4 | 60% chance in the first 12 cards | T2, or roles learnt as clusters of the card embedding |
| Role definitions | counterspell; sweeper | the two roles puzzles B and D need, rare in coherent deals | Learnt roles (clusters), or the drafter |
| Drafted k | 8 | 193's gated setting | The drafter's own strength calibration |

---

## 5. The registered experiment

### 5.1 Before the long run: the GPU smoke (about 1 h, real flags)

- **Throughput against K:** 2, 4, 8 and 16 distinct networks (copies of the init under different
  names), 3 updates each. The result sets K.
- **10,000 games of the long run's deck mix**, logging voids per recipe (bar: 0.5% or less) and
  rows per batch.
- Memory with K members resident.

### 5.2 E-L, the harm screen

**Changed after the red team (216 C2, G5).**
- E-L now runs as arm G of PLAN_LONG_RUN's multi-arm A/B, from its one init and sharing its
  control C. That A/B's shared reads (L, the whole puzzle suite, entropy, throughput) are added to
  this section's reads, and its arms are matched on updates.
- **B9 (208 §7, the cycle check among versions) is read before it.** It costs about an hour of
  evaluation, and it is the one measurement that says whether the league's insurance is for a real
  risk.

**Arms**, from the multi-arm A/B's init (the main line's checkpoint, PLAN_LONG_RUN's calendar):
- **C:** the long run's configuration without this plan's items: today's opponent shares and
  coherent decks.
- **T:** C plus `--league` (v0, r28's v1, the probe exploiter, the heuristic; snapshots every 100),
  plus `--deal-mix` (§3.4).

**Budget.**
- 5.5 machine-hours per arm, matched as r29's were: machine time from iter rows, and snapshots at
  70%, 80%, 90% and 100% of the budget.
- Reads take about 2 h.
- That makes about 13 h in all, or about 7.5 h if C is shared with the other A/Bs from the same
  init: interactions untested, cheaper.
- Run T after C, one GPU job at a time, through r29's queue machinery.

**What 5.5 hours can and cannot test.** In 5.5 hours the league adds at most one snapshot. So the
screen tests the deal mix, the external members and the branch shares. The league's long-horizon
behaviour (many snapshots, exploiters joining, forgetting) is read only in the run (§5.3), under
its kill criteria.

**Confirmatory reads** (Holm over three):

| # | Read | Prediction | Falsifier |
|---|---|---|---|
| R1 | Harm screen: T against C, 4 snapshot pairs × 1,000 fresh deals, greedy, coherent decks; the interval as B1's, snapshot SD included | 0.49-0.52 | upper bound below 0.50 |
| R2 | L on coherent decks (r27 v1, u1000, r26 v2 as opponents; 1,000 deals each); T − C over the 4 snapshots | −7 to +14 Elo | upper bound below 0 |
| R3 | Trained rows per machine-hour, T over C | 0.90-1.02 | below 0.85 |

**Checks:**
- **L on package and drafted decks** (500 deals per opponent): T − C 0 to +30 Elo, the
  familiarity read.
  - **Uninformative at this size** (216 G4). Its SE is near 10-15 Elo per shape, so at 5.5 h it
    cannot tell 0 from +30. It is reported, never read as a result. The familiarity question is
    read at X4, inside the run.
- Voids per recipe, 0.5% or less.
- Per-branch value EV.
- The exploit scan of T's games: no new flag.
- Memory.

**Decision rule** (applied by the queue's decision step):
- **R3 falsified:** fix the cost and re-smoke; nothing launches on it.
- **R1 or R2 falsified:** the long run starts with the league but coherent decks (and the package
  share as C has it). The deck mix is re-registered after a diagnosis.
- **Otherwise** the long run carries both.

### 5.3 Inside the long run: registered reads, every 48 machine-hours, by the queue

| # | Read | Prediction | Response |
|---|---|---|---|
| X0 | The league sweep: 200 greedy deals against every member (§3.2) | the learner scores 0.5 or more against every snapshot older than 100 updates | a member below 0.5: it moves to the verification branch (forgetting, or a cycle: X3 reads which) |
| X1 | Each exploiter phase's final gate against its target (1,000 deals) | 0.53-0.57 | ≥ 0.60: replay and judge (§3.3); < 0.55 twice in a row: phases stop |
| X2 | The main's training x against each joined exploiter with a final gate ≥ 0.55, 50 updates after it joins | x rises by 0.03 or more | no rise in 100 updates: recorded as an exploit the main's signal does not fix; it stays in verification |
| X3 | Round robin over a spine (every second snapshot plus the exploiters, 500 deals per pair) with a Nash solve | transitive (no triple beyond 2 SE) | a cycle: the verification share doubles (0.10 → 0.20) for the next segment, as AlphaStar's forgetting branch would |
| X4 | L per shape (coherent, package, drafted:8:6b8014ae), network members only (never the heuristic, a training opponent), with the shapes' levels | the familiarity gap (package and drafted minus coherent, against the heuristic) within ±0.015 by update 1,000; coherent L not below the init's | the gap persists: rebalance the mix toward the lagging shape; coherent L below the init's by 2 SE: KL2 |
| X5 | Per-branch and per-recipe value EV, and late-game residuals | no group below half the overall EV for 10 updates | reported, with item 2's and memory's remedies |
| X6 | The exposure of the critic's bottom-20 cards across the whole mix, relative to coherent-only (§3.6) | about 0.69 | below 0.6: the drafted share halves |
| T2 | Per-cell pilot sensitivity (§3.8), at the first read after 3 machine-days | cells within 3 SE | the T2 rule |
| P | The planning puzzles at every gate checkpoint (PLAN_PLANNING §4's runner), per category | no change from the league or the mix alone: frequency is not the bottleneck (§4.3). With the planner in, B and D are the planner's registered reads | B or D pairs still at 0 after 1,000 updates with the planner in: the specialist trigger (§3.3) |

Deal blocks for every read are fresh, registered at launch above the ranges used so far. The
gates use `GATE_SEED0`; L and B9 reads have used up to 1,140,000+.

**The reads' cost**, at about 16 evaluation games a second:
- X0: 40 members × 400 games, about 17 minutes;
- X3: about 36 pairs × 1,000 games, about 40 minutes;
- X4: 3 shapes × 3 opponents × 2,000 games, about 20 minutes.

That is about 1.3 machine-hours per 48, under 3%.

**Kill criteria specific to this plan** (the run's own guards stay):
- **KL1:** trained rows per machine-hour below 0.85 of R3's control for 10 updates: league off
  (today's shares), and the run continues.
- **KL2:** gates against the newest snapshot below 0.45 in three consecutive gates, or coherent L
  below the init's by 2 SE: league and mix off, and the run continues on today's configuration.
- **KL3:** a recipe's voids above 0.5% over 10 updates: that recipe off until its fault is fixed
  by cause.

**L's extension rule.**
- When the main's expected score against L's strongest network member passes 0.75, L gains the
  main's snapshot with search at n = 4 (a player no training member is), rated once against the
  frozen ratings.
- L is never refit (PLAN_CEILING §7.2).

---

## 6. Order of building, and what waits on what

| Step | What | Machine | Waits on |
|---|---|---|---|
| A1 | `league.py` and its tests (1-4, 10) | CPU | nothing |
| A2 | `recipes.py`, `ROLES` in `packages.py`, and their tests (5, 6) | CPU | nothing |
| A3 | `decks.py rebuild` for every recipe, the exploit scan's recipes (tests 7, 8) | CPU | A2 |
| A4 | C0 refitted on r29's games; pin r28's v1 and the probe exploiter, and check each loads into the long run's table (§3.2) | CPU (about 1 h at nice 19) | A3 for later refits; the first refit needs only today's coherent rows |
| B1 | Learner wiring: `--league`, `--snapshot-every`, `--deal-mix`, members loaded lazily, the run state, `train_rows` fields (test 9) | CPU edits | **the planner v1 merge** (same files) |
| B2 | `actor.play` dispatches recipes per seat | CPU | B1 |
| B3 | Per-branch and per-recipe value statistics in the iter row (§3.5) | CPU | the planner merge; item 2's choice of value head (so the stats read the right head) |
| C1 | The GPU smoke (§5.1) | GPU, about 1 h | B1-B3 |
| C2 | E-L (§5.2) | GPU, 7.5-13 h | C1; the value and planner A/Bs (they fix the long run's configuration, which is E-L's base) |
| D | The long run with T1; exploiter phases in the queue | GPU | C2; PLAN_LONG_RUN item 6 (the optimizer state saved), or one moment restart per phase recorded |
| E | C1 critic, counter-drafting (gated), T2 (by its rule), D1/D2, QD and nicheness | CPU first | its own reads; never inside the long run without registration |

**The long run can start with the league and the deck mix while the drafter beyond D0 is
unbuilt.** That is the brief's requirement, and steps A to D are all it needs.

**Interfaces with the planner v1 build** (another agent is changing `features.py`, `model.py`,
`actor.py`, `learner.py` and `ppo.py`). This plan edits none of them before the merge; it names
what it will touch:
1. `Learner.curriculum_job` (`learner.py:585-619`) will delegate the opponent draw and the deck
   choice to `league.draw` and `recipes.draw`. Please keep the job keys `group`, `seats` and
   `record` with today's meaning.
2. `Learner._finish_train`'s result tuple (`learner.py:852-853`: group, zs, turns, set) gains the
   member's name.
3. `actor.Worker.play`'s deck dispatch (`actor.py:330-347`) becomes one call to `recipes`.
4. `model.load`/`upgraded` (`model.py:433-470`): a member frozen before planner v1 must compute
   exactly as when it was saved. New input columns are zero-initialised in old weights, and new
   heads go unread by an old member's play (test 11, jointly owned). The opponent seat's plan
   columns hold whatever such a member's weights ignore. The learner never sees the opponent's
   plan (DESIGN_PLANNER §1).
5. `ppo.ppo_train`'s stats (`ppo.py:219-226`) gain per-group EV beside `kinds`.

---

## 7. What this changes in the other documents, and why

Each edit records why it was made, here and in its commit.

- **`DESIGN_TEACHER.md`.** A status note: the curator-plus-critic shape stays, and so do the
  measured crux (§1.1-§1.2), the "uncomfortable finding" (§2.6) and legality as a mask.
  - Superseded: the probe-delta reward, blocks and the stage order.
  - **Why:** they were written for the deleted stack and for decks held fixed for 30 games. Here
    decks are fresh each game and the γ experiment never ran.
- **`DESIGN_DRAFTER.md`.** A status note: the control surface stands as the long-term product
  design (Commander-first). The staged path on today's 60-card format is §3.6-§3.7 here.
  - **Why:** a reader should find the live order without reading 1,200 lines of
    pre-rebuild design.
- **`PLAN_DRAFTER.md`.** A status note: v0 is built and gated (193). Its §8 "later pieces" are
  ordered in §3.6-§3.8 and §6 here.
  - **Why:** G4 and 205 changed what the drafter is for (realism and familiarity, not learning
    signal).
- **`PLAN_CEILING.md`** §7.1 and §9. A pointer.
  - **Why:** its league and Teacher sections are what this design implements, for the long run
    and not only H1.
- **`PLAN_LONG_RUN.md`** items 1 and 3. A pointer.
  - **Why:** they are this plan's two items.

---

## References

League, meta-games, ratings:
- O. Vinyals et al. Grandmaster level in StarCraft II using multi-agent reinforcement learning.
  Nature 575, 2019. The league, PFSP, main and league exploiters; the published pseudocode for
  the branches and the forced checkpoint.
- C. Berner et al. Dota 2 with Large Scale Deep Reinforcement Learning (OpenAI Five). arXiv
  1912.06680, 2019. Past-opponent sampling.
- M. Lanctot et al. A Unified Game-Theoretic Approach to Multiagent Reinforcement Learning (PSRO).
  NeurIPS 2017.
- H. B. McMahan, G. Gordon, A. Blum. Planning in the Presence of Cost Functions Controlled by an
  Adversary (double oracle). ICML 2003.
- J. Heinrich, M. Lanctot, D. Silver. Fictitious Self-Play in Extensive-Form Games. ICML 2015.
- D. Balduzzi, K. Tuyls, J. Perolat, T. Graepel. Re-evaluating Evaluation (Nash averaging).
  NeurIPS 2018.
- S. Omidshafiei et al. α-Rank: Multi-Agent Evaluation by Evolution. Scientific Reports 9, 2019.
- W. Czarnecki et al. Real World Games Look Like Spinning Tops. NeurIPS 2020.
- R. Herbrich, T. Minka, T. Graepel. TrueSkill: A Bayesian Skill Rating System. NeurIPS 2006.

Curricula and environment design:
- M. Jiang, E. Grefenstette, T. Rocktäschel. Prioritized Level Replay. ICML 2021.
- M. Jiang et al. Replay-Guided Adversarial Environment Design (Robust PLR). NeurIPS 2021.
- M. Dennis et al. Emergent Complexity and Zero-shot Transfer via Unsupervised Environment Design
  (PAIRED). NeurIPS 2020.
- J. Parker-Holder et al. Evolving Curricula with Regret-Based Environment Design (ACCEL). ICML
  2022.
- A. Rutherford et al. No Regrets: Investigating and Improving Regret Approximations for
  Curriculum Discovery (SFL, learnability). NeurIPS 2024.
- T. Matiisen, A. Oliver, T. Cohen, J. Schulman. Teacher-Student Curriculum Learning.
  arXiv:1707.00183 (IEEE TNNLS 2019).
- A. Graves et al. Automated Curriculum Learning for Neural Networks. ICML 2017.
- R. Portelas et al. Teacher Algorithms for Curriculum Learning of Deep RL in Continuously
  Parameterized Environments (ALP-GMM). CoRL 2019.
- R. Wang, J. Lehman, J. Clune, K. Stanley. Paired Open-Ended Trailblazer (POET). arXiv
  1901.01753, 2019.
- C. Florensa et al. Reverse Curriculum Generation for Reinforcement Learning. CoRL 2017.

Deck building:
- T. Anthony, Z. Tian, D. Barber. Thinking Fast and Slow with Deep Learning and Tree Search (expert
  iteration). NeurIPS 2017.
- P. García-Sánchez et al. Evolutionary Deckbuilding in Hearthstone. IEEE CIG 2016.
- J.-B. Mouret, J. Clune. Illuminating Search Spaces by Mapping Elites. arXiv:1504.04909, 2015.
- M. Fontaine et al. Mapping Hearthstone Deck Spaces through MAP-Elites with Sliding Boundaries.
  GECCO 2019.
- Y. Zhang, M. Fontaine, A. Hoover, S. Nikolaidis. Deep Surrogate Assisted MAP-Elites for Automated
  Hearthstone Deckbuilding. GECCO 2022.
- Z. Chen et al. Q-DeckRec: A Fast Deck Recommendation System for Collectible Card Games. IEEE CIG
  2018.
- R. Vieira, A. Tavares, L. Chaimowicz. Drafting in Collectible Card Games via Reinforcement
  Learning. SBGames 2020.
- H. Ward et al. AI Solutions for Drafting in Magic: The Gathering. IEEE CoG 2021.

Value functions and baselines:
- R. Williams. Simple Statistical Gradient-Following Algorithms for Connectionist Reinforcement
  Learning. Machine Learning 8, 1992.
- E. Greensmith, P. Bartlett, J. Baxter. Variance Reduction Techniques for Gradient Estimates in
  Reinforcement Learning. JMLR 5, 2004.
- R. Lowe et al. Multi-Agent Actor-Critic for Mixed Cooperative-Competitive Environments (MADDPG).
  NeurIPS 2017.
- J. Foerster et al. Stabilising Experience Replay for Deep Multi-Agent Reinforcement Learning
  (fingerprints). ICML 2017.
- K. Cobbe, J. Hilton, O. Klimov, J. Schulman. Phasic Policy Gradient. ICML 2021.

Project evidence: KNOWLEDGE/2026-11-12/193 (the critic and its gates), 199 (r28), 202 (package line
values), 2026-11-13/205 (the ceiling read, L), 2026-11-14/208 (r29), 2026-11-17/211 (the
exploitability probe), 2026-11-18/214 (the puzzles); `reports/league_teacher_2026-11-18/` (the role
census).
