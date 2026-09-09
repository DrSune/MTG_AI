# Training Review Protocol

**What this is.** The procedure the project follows around every training run: what must be true
before a run starts, what is watched while it runs, what is looked at afterwards and in what order,
what gets written down, and who decides what happens next.

**What this is not.** A metrics catalogue. Definitions, formulas, null baselines, engine
requirements and per-metric reading notes live in [`METRICS.md`](METRICS.md). This document
references metrics by name and does not redefine them.

**Why it exists now, before training starts.** Nothing in the repository can currently tell you
whether a change made the bot better. At HEAD (`bc14850`) the engine suite reports 10 passed / 29
failed / 2 xfailed. The only scored benchmark pays a do-nothing policy **0.9000** on
`scenarios/M21/level_2` and **0.2358** on `level_1`, because `benchmarker.py:143-163` scores life
proximity and 25 of the level_2 files are byte-identical copies of a state already sitting at 18/20
life. The only opponent is `deepcopy(student)` from at most 20 games ago (`train.py:89-91`), so win
rate is pinned near 50% by construction. There is **no `random.seed`, `np.random.seed` or
`torch.manual_seed` call anywhere in the training path**, so no A/B comparison can attribute a
difference to the change rather than to the shuffle. `TrainingLogger.save_report()` is `pass`
(`training_logger.py:61-63`), so no metric has ever been written to disk from this checkout.

Every one of those is a process failure as much as a code failure. A protocol written after the
first disappointing run is a protocol written to explain the run. This one is written first.

**Standing principles this protocol inherits** (from [`NORTH_STAR.md`](../NORTH_STAR.md)): learned
over hardcoded; incentives not rules; Commander is the priority format; **a metric that a null
policy scores well on is worthless**.

---

## 0. Vocabulary, and four invariants

| Term | Meaning |
|---|---|
| **Run** | One continuous training job under one frozen config, one code SHA, one card-DB hash, one environment-contract epoch. Any change to those four ends the run and starts a new one. |
| **Review** | The procedure in §4, producing one committed report (§5). |
| **Epoch** | The environment contract version. Changing the action space, the priority model, the reward terms, the seat count or the legal-move generator mints a new epoch and breaks cross-epoch comparability of every per-decision series. See §8.6. |
| **Gauntlet** | The frozen, hash-stamped set of decks, matchups and seat assignments used for evaluation. Never sampled from the training distribution. |
| **Anchor** | A fixed opponent that never changes: `RandomAgent` (pinned at 0 Elo), `GreedyAgent`, `RuleBasedAgent`, plus retained milestone checkpoints. |
| **Confirmatory metric** | One of at most six metrics pre-registered before the run with a predicted direction. Only these may justify a decision on their own. |
| **Exploratory metric** | Everything else. Reported, tagged, never decisive alone. Its only power is to generate a confirmatory prediction for the next run. |

### The four invariants

**I1. Gate order is not a preference, it is a truth condition.** Correctness before validity before
strength before style. A strength number computed on an engine that threw errors is not a weaker
number, it is a **false** number, and it is worse than no number because it will be believed.

**I2. Every published quality scalar is null-zero normalised.**

```
NormScore = (M_policy - M_null) / (M_oracle - M_null)
```

`M_null` is **measured in the same episode, on the same positions, under the same RNG stream**,
never assumed. It is not clipped below zero: a policy worse than doing nothing must be able to print
a negative number. Under this convention the 0.900 puzzle score becomes 0 by algebra rather than by
vigilance. Applies to every scored corpus, every benchmark, every derived index.

**I3. Every row carries its null band and its seed band.** A row whose model value falls inside
either band prints `NOT EVIDENCE` and is excluded from the summary. This is a formatting rule
enforced by the harness, not a judgement call at review time. It is the direct analogue of
`bench.py:283`'s `round_spread_pct > 15% means the row is not evidence`, which is the only such
discipline the repository currently has.

**I4. Any metric whose numerator can be satisfied by not acting must be published paired with a
metric whose numerator can only be satisfied by acting well.** Blunder rate pairs with missed gain.
Entropy pairs with regret or with context discrimination. Diversity pairs with strength. Calibration
pairs with resolution. Hand size pairs with permanents. The pairing is part of the metric definition
in `METRICS.md`, and the report renders the pair or neither.

---

## 1. Pre-flight

**A run that starts without these produces numbers nobody can trust, and the DGX hours spent on it
are gone.** Every line is a hard blocker unless marked ADVISORY. Pre-flight writes
`runs/<run_id>/preflight.json`; the run refuses to start without it.

### 1.1 Code, config and data identity

| # | Check | Passing condition | Status today |
|---|---|---|---|
| P1 | Working tree clean, SHA recorded | `git status --porcelain` empty; SHA in manifest | trivial |
| P2 | Config snapshotted verbatim into the run dir, hashed | `config_hash` in manifest, byte-identical copy on disk | trivial |
| P3 | Card DB content hash recorded | SHA-256 of the DB file plus per-table row counts | trivial, and **required**: `card_id` is an autoincrement rowid rebuilt on re-ingest, so every per-card series silently compares different cards across a re-ingest |
| P4 | Environment contract epoch id declared | integer, incremented by hand when the action space, priority model, reward terms or seat count change | trivial |
| P5 | Metric schema version declared | integer. Changing a metric definition mints a new metric id (§10.1), never mutates the old series | trivial |
| P6 | Dependency versions pinned and recorded | `pip freeze` into the run dir | trivial |

### 1.2 Engine conformance, gate G0

| # | Check | Passing condition | Status today |
|---|---|---|---|
| P7 | Rules conformance suite green | 100% pass; zero xfail without a linked issue and a stated removal condition | **BLOCKED.** 10 passed / 29 failed at `bc14850` |
| P8 | Smoke slate, 50 games, all seats | `engine_error_rate == 0`, `no_op_resolution_rate < 3%`, `missed_trigger_rate == 0` on the 1% oracle sample | **BLOCKED.** `execute_move` swallows every rules bug into a log line (`engine.py:278-279`) and `environment.py:153` discards its event list, so none of these can be computed |
| P9 | `termination_reason` histogram on the smoke slate | `life_zero + deckout >= 95%`; `stall_trip + step_cap + adjudicated_timeout < 5%` | **BLOCKED.** `MAX_MOVES_PER_STEP` sets `game_over` with `winner_id = None`; the reward pays -10 to both seats while the win-rate metric scores the same game 0.5 |
| P10 | `effective_card_coverage` on the smoke slate | at least 90% of the cards present in the played decks resolve once with a non-empty state-change set. Below that, the run's claims are scoped to a subset of Magic and the report says so on page 1 | **BLOCKED.** 7 of 397 cards can currently present a target choice at all |

### 1.3 Determinism and attribution, gate G2

| # | Check | Passing condition | Status today |
|---|---|---|---|
| P11 | All RNG seeded, streams separated (shuffle / engine / policy / exploration) | seeds in the manifest, four independent streams | **BLOCKED.** Zero seed calls in the training path |
| P12 | Byte-identical replay | the same seed replays to an identical event-stream hash, twice, in two processes | **BLOCKED.** Entity ids are `uuid4()` and zone-change triggers iterate `set` differences of UUIDs, so trigger ordering is hash-dependent even under a fixed seed |
| P13 | Seed band measured | k=5 seeds on a short calibration slate. `seed_band = 2 x std` recorded per confirmatory metric, written into the manifest, printed on every row of the report | needs P11 |

**P11 to P13 gate the entire protocol.** Until they pass, no comparison in this document can
conclude anything, and the correct response to any observed difference is "we do not know".

### 1.4 Benchmark and corpus calibration, gate G1

| # | Check | Passing condition |
|---|---|---|
| P14 | Every scored corpus ships a baseline certificate | each item carries `null_score`, `random_score` (mean over R=200 uniform rollouts), `oracle_score`, `oracle_line`, corpus content hash. **A scenario file without a `null_score` field does not load.** |
| P15 | Null-favourable items rejected at build time | normalised `random_score > 0.05` rejects the item from the corpus |
| P16 | Every confirmatory metric has a measured null value and a measured random value | computed on the same slate, in the same run, under the same seeds |
| P17 | Position and gauntlet corpora frozen and hashed | the harness refuses to run on a hash mismatch |
| P18 | Anchors exist and are pinned | `RandomAgent` at 0 Elo, never updated. Greedy and RuleBased frozen and hashed. **Anchors are re-baselined at every epoch boundary**, because a random agent over a different action space is a different agent |

### 1.5 Deck and gauntlet pre-flight (microseconds, run before any game)

Pure functions of the decklists. They cost nothing and they stop a run whose decks are broken from
producing a slate of noise.

| # | Check | Passing condition | Why |
|---|---|---|---|
| P19 | Colour-identity legality | **1.000**. Any value below 1.000 is a deck-generator bug | The current builder cannot compute identity at all: `deck_generator.py:96` filters with `mana_cost LIKE '%W%'` and `:182-186` derives deck colours by substring over `mana_cost`. That disagrees with true `colorIdentity` on 40 of 397 cards, and **all 40 are lands**, which is exactly the population a mana-tendency metric is about |
| P20 | Commander is a legal commander | not a basic land, not a random card | `game_initializer.py:81-88` pops `working_deck[0]` as the commander **before** shuffling at `:90`, on a list `deck_generator.py:196` already shuffled. The commander is currently a uniformly random card |
| P21 | Manabase source deficit | `sum(max(0, deficit(c))) <= 3` per deck against a declared published source table | A deck below this measures a broken manabase, not a policy |
| P22 | Curve conformance to the declared archetype recipe | `JSD(deck curve, target curve)` below a declared threshold | Catches a builder that is not building what it claims |
| P23 | Seat rotation defined | every gauntlet matchup is played with the agent rotated through **all** seats, in equal counts | Turn order in a pod is a large confound and Commander is the priority format |

### 1.6 Measurement plumbing

| # | Check | Passing condition |
|---|---|---|
| P24 | Metric store writable, schema created, retention policy set | §10.2 |
| P25 | Pipeline invariants assert clean on the smoke slate | §10.3 |
| P26 | Instrument A/A self-test passes | §10.4. The pipeline is run on two identical checkpoints and **must report no difference on every confirmatory metric**. An instrument that cannot detect its own no-op is the same class of error as a benchmark that pays 0.900 for doing nothing |
| P27 | Measurement compute budget declared and enforced | §9. Default proposal: measurement at most 5% of run GPU time |

### 1.7 Pre-registration (free, and the strongest single defence in this document)

Written into the manifest before the run starts:

```json
"preregistration": {
  "hypothesis": "one sentence: what change is being made and why it should help",
  "confirmatory_metrics": ["at most 6 metric ids"],
  "predictions": [
    {"metric": "<id>", "direction": "up|down|flat", "magnitude": "<number or band>",
     "falsifier": "the observation that would say the change did not work"}
  ],
  "kill_criteria": ["copied verbatim from section 3.3"],
  "planned_n": {"gauntlet_games": 0, "eval_decisions": 0},
  "expected_run_cost": {"gpu_hours": 0, "env_decisions": 0}
}
```

Without this, a 200-number dashboard will always contain a story. With it, the first table of the
review is predicted versus observed with a hit/miss column, and the reviewer is scored as well as
the model. **A prediction that was wrong is worth more than one that was right.**

---

## 2. Run start

1. Write `runs/<run_id>/manifest.json`: identity, seeds, hashes, epoch, pre-registration, budget.
2. Write `runs/<run_id>/preflight.json`: every P-check with pass/fail and the measured value.
3. Copy the config file and the gauntlet manifest into the run dir verbatim.
4. Start the live watch (§3).
5. Append the run to the review log index with its `run_id`, hypothesis and planned end trigger.

---

## 3. During the run

### 3.1 What is watched live

Three severities. **HALT** stops the run automatically. **PAGE** requires a human within an hour.
**NOTE** is recorded and read at review time.

Threshold status: **DERIVED** (arithmetic or a contract requirement), **MEASURED** (from a baseline
already on disk), **PROVISIONAL** (a declared judgement call, to be replaced by the measured A/A and
seed bands after run 1). **No PROVISIONAL threshold may trigger a HALT** until it has been replaced
by a measured band.

| Watch | Cadence | Alarm | Severity | Status |
|---|---|---|---|---|
| `engine_error_rate` | every 1k decisions | `> 0` | PAGE; `> 1/1000` HALT | DERIVED |
| Unhandled-node rate | every 10k decisions | `> 10%`, or one node type in more than 50 cards | PAGE | PROVISIONAL |
| `no_op_resolution_rate` | every 10k decisions | `> 15%`, or any card with n>=20 resolutions at rate 1.0 | PAGE | PROVISIONAL |
| `termination_reason` | every 200 games | `stall_trip + step_cap > 5%` | PAGE; `> 20%` HALT | DERIVED (contract) |
| `terminal_coverage` | every 200 games | `< 0.99` | HALT | DERIVED. A buffer in which the agent has never seen a loss cannot learn to avoid one, and today the frozen branch's reward is discarded (`train.py:335`), so roughly half of all terminal signals never enter the buffer |
| Dead-gradient census | every 50 updates | any trainable tensor with `grad is None` or zero norm for 3 consecutive checks | HALT | DERIVED. This is the check that would have caught the project's actual central bug on day one |
| `clip_fraction`, split by action class and field count | every update | `> 0.5` on any class, or `< 0.01` overall | PAGE | PROVISIONAL |
| `approx_kl` (Schulman k3) per epoch | every update | `> 0.05` | PAGE, and early-stop the epoch loop | PROVISIONAL |
| Importance-ratio p99 | every update | `> 5`. Would currently read about `2.2e4`, because the proactivity bias is applied at collection (`student.py:126-129`) and not at training (`student.py:175-181`) | PAGE | DERIVED |
| Gradient norm pre-clip | every update | spike above 10x the trailing p95 | NOTE | PROVISIONAL |
| Explained variance, outcome channel | every 500 updates | `< 0.05` for 3 consecutive windows | PAGE | PROVISIONAL |
| Buffer staleness p95 | every 100 updates | `> 4` updates | PAGE | DERIVED |
| Outcome share of the advantage signal | every 500 updates | `< 0.05`, or not rising while the shaping anneal runs | PAGE | DERIVED |
| Reward-outcome decoupling | every 500 games | top-reward-decile win rate minus bottom-decile `< 10 points`. The broadest single detector of reward hacking, engine-bug farming and degenerate equilibria at once | PAGE | PROVISIONAL |
| Normalised entropy, non-forced and non-exploration decisions only | every 500 updates | `< 0.15` | PAGE | PROVISIONAL |
| Proactive actions per turn | every 200 games | p50 `< 1.0` | PAGE | PROVISIONAL |
| Activation concentration | every 500 games | any single ability at p50 above 20 activations per game, or the top non-mana ability above 15% of all activations, or a per-game p99/p50 ratio above 20. This is the engine-exploit signature and it appears before any win-rate anomaly | PAGE | PROVISIONAL |
| Throughput (games/hour, decisions/hour) | continuous | below 50% of the first hour's rate | PAGE | DERIVED |
| Per-decision wall clock p99 | every 10k decisions | breaches the clock contract in `DESIGN_LATENCY.md` §1.3. Slow-play exposure (any decision over 5 s) is a PAGE on its own | NOTE / PAGE | DERIVED |
| Checkpoint written and loadable | every checkpoint | load test fails | HALT | DERIVED |
| Metric-store disk headroom | hourly | below 20% free | PAGE | DERIVED |

### 3.2 Decision count per game: monitored, not estimated

**Owner instruction, binding: decisions per game is not estimated up front. It is measured during
real training runs and the measured numbers are the evidence.** It is a first-class watch item here,
not a separate analysis.

**Logged per game, per seat:** total decisions; decisions per turn; turns per game; forced fraction;
split by chosen action class; split by phase and by step; and the non-trivial subset (support above
1 after canonical dedup, no forced short-circuit).

**Reported as** `n, min, p50, p90, p99, max, mean` for each. Never as a mean alone.

**The instrument already exists.** `tools/latency/decisions.py:171-204` computes exactly this shape
and has real output on disk at `reports/decision_counts_devbox.json`. Three changes make it serve
this protocol: run it with the **model** in the loop instead of `random.choice`, key it by **seat**
rather than player index, and emit **per-decision rows** rather than aggregates only.

**Measured baseline, random policy, current engine, 24 games**
(`reports/decision_counts_devbox.json`):

| Statistic | Value |
|---|---|
| decisions_per_game | p50 **2173**, p90 2533, p99/max 2802 |
| decisions_per_seat_per_game | p50 **1077**, p99 1603 |
| turns_per_game | p50 **181** |
| decisions_per_turn | p50 **12.29** |
| forced_fraction | **0.3424** |
| by_chosen_class_pct | PassPriority **55.0**, ActivateMana **37.1**, PassTurn 6.1, PlayLand 0.8, CastSpell 0.6, DeclareAttacker 0.4, DeclareBlocker 0.1 |
| by_phase | Beginning 30716, Combat 11934, PreCombatMain 5690, PostCombatMain 2271, Ending 2172 |

That baseline is a **loose floor on the current engine** by its own docstring. It is recorded here so
the first real measurement has something to be compared against, not as a target.

**Alarms.**

| Condition | Severity | Reading |
|---|---|---|
| `decisions_per_game` p99 rises above 2x its first-hour value | PAGE | Loop, stall, or an engine exploit |
| `decisions_per_turn` p50 rises while `turns_per_game` also rises | PAGE | Degenerate equilibrium forming |
| `forced_fraction` moves more than 0.05 absolute with no epoch change | PAGE | The legal-move generator changed under you |
| Any action class falls to zero selections over 50k decisions while available in more than 5% of menus | PAGE | The class is being ignored. Report the rule-of-three bound `< 3/N`, never a bare zero |
| `decisions_per_game` p50 changes more than 20% across a checkpoint | NOTE, and raise the epoch question | See §8.6 |

**Two things this number is used for.**

1. It is the **denominator of the learning curve**. Elo per environment decision consumed is the
   primary x-axis, GPU-hours second, games last, because game length varies roughly 10x and a games
   axis hides throughput regressions.
2. It is the input to the clock and cost arguments in `DESIGN_LATENCY.md` and `COST_MODEL.md`, which
   currently rest on a random-policy floor.

**Decisions per game is descriptive, not a quality metric.** A random policy produces plenty of
them. It is never quoted as progress.

### 3.3 Early-kill criteria

A run is killed, not paused, when any of these holds. Killing early is cheap. A wasted week of DGX
time is not.

| # | Kill condition | Rationale |
|---|---|---|
| K1 | A G0 alarm HALTs and the cause is a rules bug rather than a config typo | Everything downstream is false |
| K2 | `terminal_coverage < 0.99` and not fixable in place | The agent is not seeing outcomes |
| K3 | Dead-gradient census non-empty for 3 consecutive checks | Part of the model is decoration. The run measures a different architecture than the one on paper |
| K4 | Explained variance on the outcome channel below 0 for 3 consecutive windows | The value head is worse than predicting the mean, so advantages are noise and PPO is a random walk |
| K5 | Two consecutive review windows with no confirmatory metric moving beyond its seed band, past 30% of the planned decision budget | The run has plateaued. Kill it and change something |
| K6 | Reward-outcome decoupling below 10 points and falling, with shaping share rising | Reward hacking confirmed |
| K7 | Throughput below 50% of plan with no fix in sight | The run will not finish inside its budget |
| K8 | Measurement budget breached by more than 2x | Measurement is eating the run |

**Never kill on a single PROVISIONAL threshold.** Provisional alarms page a human, who decides.

### 3.4 Unscheduled reviews

A PAGE alarm forces an **unscheduled mini-review**: stages R0, R1 and R2 of §4 only, plus the
instrument that alarmed, written up as a dated entry in the run's report under section 12
(Incidents). It does not require the full sequence and it does not wait for the calendar.

---

## 4. After the run: the ordered review sequence

**The order is the point.** Correctness before validity, validity before strength, strength before
style. Nobody spends an afternoon admiring the colour preferences of a run whose engine was throwing
errors.

Each stage has a **stop condition**. When a stage stops, later stages are **not performed**, the
report is written up to that point, and every later section reads `NOT REACHED (stage N red)`. That
is a complete and useful review. A review that skips ahead is not.

### R0. Integrity (10 minutes)

- Manifest present and complete: SHA, config hash, card-DB hash, epoch, seeds.
- Pipeline invariants (§10.3) all green.
- The run actually ran the config in the manifest. Spot-check three values against the process log.
- The metric store contains the expected number of rows, within bounds.

**Stop if:** any invariant fails. A pipeline that silently dropped rows produces metrics that are
wrong rather than absent, which is far more dangerous.

### R1. Engine correctness, gate G0 (30 minutes)

Read in this order: `engine_error_rate` with its top-offender table by card and by emitting
`file:line`; `no_op_resolution_rate` with its per-card table; `unhandled_node_rate` by node type;
`missed_trigger_rate` from the 1% oracle sample; the `termination_reason` histogram;
`effective_card_coverage` with the dead-card list (cards that were in hand, with priority held and
mana available, at least 30 times, and never produced a non-no-op resolution).

**If any error fired, watch that game now.** Open the replay at the offending decision before
reading another number. This is the one place a qualitative pass happens early, because a
concentrated error distribution (one card above 20% of errors) is a rules bug you can fix in an hour
and a flat distribution is an architecture problem you need to see.

**Stop if:** `engine_error_rate > 0`, or `no_op_resolution_rate > 15%`, or
`stall_trip + step_cap > 5%`. The report prints `INVALID: engine` on page 1 and **no strength number
is published from this run**.

**Record on page 1 regardless:** `effective_card_coverage`. Every claim in the report is scoped to
that fraction of the pool, and the scoping sentence is printed verbatim: *"this run measures play
over N% of the card pool."*

### R2. Signal validity and attribution, gates G1 and G2 (20 minutes)

- Null column and random column present on every scored row.
- Seed band present on every confirmatory row.
- The A/A self-test from pre-flight, re-run if the harness changed.
- Position-corpus drift: JS divergence between this run's live position distribution and the frozen
  corpus. Rising drift invalidates every corpus-based metric in the report and is printed next to
  them, not in a separate section.
- Menu-invariance and duplicate-invariance probes. Total variation above 0.01 under candidate
  permutation means the policy is keying on list position and every ranking metric is measuring an
  artefact.
- Exploration accounting: what fraction of logged actions were epsilon overrides rather than policy
  samples. Any policy-behaviour metric computed over overridden actions is void.

**Stop if:** determinism failed, or the A/A test reports a difference, or the invariance probes
fail. Numbers exist, but nothing can be attributed.

### R3. Learning health (30 minutes)

Gradient-flow census with dead-tensor names and per-group update ratios. The trust-region trio
(`clip_fraction`, `approx_kl`, ratio log-variance) split by action class **and by number of emitted
action fields**; a monotone rise with field count converts the open question in `DECISIONS.md` R4
from a debate into a measurement. Advantage statistics split by reward channel, with `outcome_share`,
`loss_transition_fraction` and `terminal_coverage`. Explained variance on the outcome channel
**printed beside `EV_null`**, a three-feature linear regression on `[turn, life differential, board
differential]`. Buffer staleness. Per-plan-step head health: gradient contribution and step-k
accuracy against chance at every k, which is the numeric form of the owner's binding directive that
every plan step be trained.

**Stop if:** the model is not learning. A run with dead heads, an exploded importance ratio, or a
value head that loses to a three-feature linear model does not get a strength section.

### R4. Strength (60 minutes)

1. **Anchor Elo**, `RandomAgent` pinned at 0, Bayesian with 95% CIs, over the frozen gauntlet with
   seat rotation.
2. **Cyclic fraction** (HodgeRank on the pairwise logit matrix). This **gates whether Elo may be
   quoted**: above 0.15 the Elo is annotated approximate, above 0.35 it is not a headline at all.
   This is the specific reason a self-play Elo can climb for a year while absolute strength does not
   move.
3. **Forgetting matrix** over retained checkpoints. Headline `worst_ancestor_winrate`; below 0.50 is
   catastrophic forgetting.
4. **Anchor gap**: league Elo delta minus anchor Elo delta over the window. A large positive gap
   means the agent is climbing a ladder made of itself.
5. **Paired branch-point evaluation** against the previous checkpoint (§8.2). This is the primary
   "did the change help" number, not the raw win rate.
6. **Student minus teacher Elo gap**, when a teacher is in the loop. A plateau at the teacher's level
   means the transfer became a cap.

**Never publish** win rate against a frozen copy of the agent's own recent weights. It is pinned near
50% by construction and it is a net information loss on the dashboard.

**Stop if:** strength is flat within CI **and** R3 was clean. That combination is the plateau case
and it goes straight to the decision gates as `ITERATE (change something structural)`.

### R5. Decision quality (45 minutes)

Everything here is reported over three denominators (raw / non-trivial / effective) with the dilution
factor printed, because the measured decision stream is 55% PassPriority and 37% ActivateMana and a
mean over the raw stream is roughly 8% signal.

- Normalised value capture and the regret distribution, at whatever oracle tier is affordable, with
  the tier in the metric name. The **p99 of regret** and the **count of large-regret decisions per
  game** are the numbers, not the mean.
- Regret concentration, decomposed by action class, phase, turn bucket and difficulty cell.
- Missed gain (opportunity regret), the mandatory pair for any blunder-rate number.
- Value calibration with the **Murphy decomposition**: reliability, **resolution**, uncertainty.
  Resolution is the anti-null term. A constant base-rate predictor is perfectly calibrated with zero
  resolution, which is the 0.900 failure wearing a calibration costume.
- PR-AUC and F1 on whichever labelled heads exist. Each row carries candidate set, base rate,
  n_positives, contributing games, AP, AP_null, lift, threshold and clustered-bootstrap CI. Refuse to
  print below 50 positives from 5 distinct games.
- Availability-normalised action-class coverage, computed on the **pre-curation** menu. Any class
  available in more than 5% of menus and selected far below the oracle rate is a red row.
- Puzzle results: null-zero normalised score, trap-take rate, null margin, plus the IRT skill
  estimate with its standard error and the list of items auto-retired for zero discrimination.

### R6. Behaviour and tendencies (60 minutes)

The section the owner asked for by name, and deliberately last among the numeric stages because it is
the most enjoyable to read and the most useless when R1 to R4 are red.

All of it is **pivots over one wide table**, not separate instruments. Every row carries
`(run_id, checkpoint, game_id, seat, deck_colour_identity, declared_archetype, measured_archetype,
opponent_archetype, turn, phase)`, so per-colour and per-archetype views are a `GROUP BY` rather than
forty hand-built metrics.

- **Mana**: utilisation curve by turn, missed land drop rate, colour screw exposure, floated mana
  (gated on production, because a policy that never taps never floats), land-sequencing regret, flood
  and screw conversion.
- **Per colour**: `usage_ratio(c) = share of mana spent on cards of colour identity c, divided by
  share of colour c in the declared decklist`. 1.0 means the colour is used as much as it was given;
  0.4 means the policy systematically ignores it. Plus per-colour win rate, deck utilisation and
  two-for-one rate.
- **Curve**: cast-versus-deck mana-value histograms and their JSD; on-curve rate.
- **Combat**: missed lethal (unanswerable subset as the headline), free-block miss rate, unjustified
  chump rate, suicidal attack rate, trade quality.
- **Tempo**: first-attack survival curve, clock and race index, damage per mana spent.
- **Cards**: differential curve with hand and permanents split out, two-for-one rate, stranded
  castable resources at a loss, deck utilisation.
- **Commander**: commander cast and recast curve against tax, colour-identity legality, threat
  allocation in a pod (a target band, not a maximum), elimination share, commander damage awareness.
- **Deckbuilding and drafting**: colour commitment curve, finished-deck quality, pick confidence. The
  report states plainly that Commander has no draft, so for this project "drafting tendencies" means
  **deckbuilding and colour-preference tendencies**, and that until the teacher actually learns this
  section measures an unlearned random SQL sampler (`teacher.py:76` `ORDER BY RANDOM()`;
  `train_teacher` at `teacher.py:132-156` has no `backward()` and no `optimizer.step()`).
- **Declared versus measured archetype**: k-means over `(mean MV, creature share, colour share,
  interaction share, land count)` against the recipe label. Disagreement is a finding about the deck
  generator, not about the policy.

**Every pivot obeys the sample-size table in §8.4.** A per-colour outcome pivot needs its own game
count per colour. The temptation to read a 5-point win-rate gap off 40 green games will be constant.

### R7. Variability and style (20 minutes)

- Context discrimination: mutual information between chosen action class and state context, bias
  corrected, minus a permutation null. Uniform-random scores 0; always-pass scores 0.
- Matched-state entropy, read as a 2x2 against context discrimination: noise / healthy-stochastic /
  mode collapse / deterministic expert.
- Importance-stratified agreement gap: cross-replay agreement in the top decile of decision stakes
  minus the bottom decile. Both null and random score exactly 0. This is the direct answer to
  "variability in play": consistent where it matters, varied where it does not. Gated on explained
  variance above 0.2, because a broken value function makes "stakes" meaningless.
- Strategy churn, repertoire breadth, and the ignored-card list.

### R8. Eyes on glass (30 minutes, mandatory, not skippable)

Numbers tell you which games to watch. Nothing tells you to watch them except this line.

Watch end to end, in the spectator tool:

1. One **median** game from the gauntlet.
2. The game containing the **single highest-regret decision** of the run.
3. The game with the **worst gate violation**, or if there was none, one game the agent lost from a
   winning position.

Then read the **top 10 highest-regret decisions** with their board states.

Write at least three sentences in section 9 of the report about what you saw that the numbers did not
say. If you have nothing to write, say so explicitly. That is also information.

### R9. Reconcile, decide, write up (30 minutes)

1. Predicted versus observed table with a hit/miss column, from the pre-registration.
2. Conflicts resolved, or explicitly recorded as unresolved (§11).
3. Decision taken against the gates in §6.
4. Report committed. Next review trigger set.
5. Metric registry updated: which metrics actually changed this decision (§10.1).

---

## 5. The report

**Path:** `reports/reviews/RUN-<YYYYMMDD>-<slug>.md`, committed. Fixed section order and fixed row
keys, so consecutive reviews diff cleanly. **Never delete a section.** A section that does not apply
reads `NOT REACHED` or `N/A` with a reason.

The values below are **EXAMPLE VALUES**, present so the shape is unambiguous.

```markdown
# Run Review: RUN-20261115-ppo-per-field-ratio

## 0. Identity
| Field | Value |
|---|---|
| run_id | RUN-20261115-ppo-per-field-ratio |
| git_sha | a1b2c3d (clean) |
| config_hash | 8f3e...c21 |
| card_db_hash | 4d9a...77b (397 cards, 86 vocab rows) |
| env_contract_epoch | 3 |
| metric_schema_version | 2 |
| seeds | shuffle=1001 engine=1002 policy=1003 explore=1004 |
| gauntlet | gauntlet_v2 (hash 0c11...9ef), 12 decks, 4 seats, rotation on |
| started / ended | 2026-11-12 09:14 / 2026-11-15 06:02 |
| consumed | 68.8 GPU-h; 412M env decisions; 189,300 games |
| measurement cost | 2.9 GPU-h (4.2% of run). Budget 5%. PASS |
| previous review | RUN-20261104-baseline |

## 1. Verdict
**ITERATE.** Gates G0/G1/G2 green. Anchor Elo +38 (95% CI +9 to +67) over the previous
checkpoint on 1,200 paired branch points. Two of four predictions hit. Card coverage 71.3%,
so every claim below is scoped to 71.3% of the pool.

## 2. Pre-registration: predicted vs observed
| Metric | Predicted | Observed | Seed band | Hit? |
|---|---|---|---|---|
| clip_fraction (CastSpell) | down, below 0.30 | 0.24 | +/- 0.03 | HIT |
| anchor_elo_vs_greedy | up, at least +25 | +38 [+9, +67] | +/- 18 | HIT |
| mana_utilisation p50 (t4-t8) | up, at least 0.60 | 0.51 | +/- 0.04 | MISS |
| missed_lethal_rate | flat | 0.31 -> 0.19 | +/- 0.06 | MISS (moved, unpredicted) |
Falsifier check: no falsifier triggered.

## 3. Gate G0: engine correctness
| Metric | Value | Threshold | Status |
|---|---|---|---|
| engine_error_rate | 0.0 per 1k decisions | 0 | PASS |
| no_op_resolution_rate | 2.1% | < 3% | PASS |
| unhandled_node_rate | 1.4% | < 2% | PASS |
| missed_trigger_rate (1% sample) | 0.0 | 0 | PASS |
| termination: life_zero / deckout / stall / step_cap | 91.2 / 5.9 / 1.8 / 1.1 % | stall+cap < 5% | PASS |
| effective_card_coverage | 71.3% | >= 90% | **FAIL (advisory)** |
Dead-card list: 114 cards, top 10 attached. Top error offenders: none.
**Scoping sentence:** this run measures play over 71.3% of the card pool.

## 4. Gates G1/G2: validity and attribution
| Check | Value | Status |
|---|---|---|
| replay determinism (2 processes) | identical event hash | PASS |
| seed band measured (k=5) | per-row | PASS |
| A/A self-test | no metric differed beyond band | PASS |
| corpus drift (JS) | 0.07 | PASS (< 0.15) |
| menu permutation TV | 0.004 | PASS (< 0.01) |
| duplicate-candidate max delta | 0.006 | PASS |
| exploration override share of logged actions | 17.4% | excluded from all policy metrics |
| null column present on all scored rows | yes | PASS |

## 5. Learning health
| Metric | Value | Null / baseline | Status |
|---|---|---|---|
| dead tensors | 0 | 0 | PASS |
| update ratio range across groups | 3e-4 to 6e-3 | 1e-4 to 1e-2 | PASS |
| clip_fraction overall | 0.19 | 0.05 to 0.30 | PASS |
| approx_kl per epoch | 0.011 | < 0.03 | PASS |
| ratio p99 | 1.9 | < 5 | PASS |
| ratio log-variance by field count | 1f 0.08, 2f 0.14, 3f 0.31 | monotone rise: R4 evidence | NOTE |
| loss_transition_fraction | 0.498 | ~0.5 | PASS |
| terminal_coverage | 1.000 | 1.000 | PASS |
| outcome_share | 0.22 (was 0.09) | rising | PASS |
| explained_variance (outcome) | 0.34 | EV_null 0.11 | PASS |
| buffer staleness p95 | 1 update | <= 4 | PASS |
| plan-step accuracy k=0..4 | .61 / .44 / .38 / .31 / .27 | chance .19 / .19 / .20 / .21 / .21 | PASS |

## 6. Strength
| Metric | Value | 95% CI | n | Status |
|---|---|---|---|---|
| Elo vs Random (pinned 0) | +612 | [+588, +636] | 1,600 | |
| Elo vs Greedy | +184 | [+150, +218] | 1,600 | |
| Elo vs RuleBased | +41 | [+7, +75] | 1,600 | |
| Elo vs previous checkpoint | +38 | [+9, +67] | 1,200 paired | REAL |
| cyclic_fraction | 0.11 | | 9x9 matrix | Elo quotable |
| worst_ancestor_winrate | 0.57 | | | PASS |
| anchor_gap | +12 Elo | | | PASS (< 50) |
| paired disagreement rate | 21.3% | | | |
| win rate vs frozen self | NOT PUBLISHED (pinned by construction) | | | |

## 7. Decision quality
| Metric | raw | non-trivial | effective | null | Status |
|---|---|---|---|---|---|
| dilution factor (raw/effective) | 11.4 | | | | |
| normalised value capture @O1 | .29 | .48 | .61 | 0.00 | |
| regret p50 / p90 / p99 | .000 / .004 / .061 | | | | |
| large-regret decisions per game (> .10) | 3.4 | | | | |
| regret concentration @1% | 0.44 | | | | |
| missed gain capture ratio | 0.52 | | | 0.00 | |
| Brier: REL / RES / UNC | .011 / .062 / .187 | | | RES_null 0 | |
| ECE (15 equal-mass bins) | 0.043 | | | | |
| class coverage red rows | DeclareBlocker (avail 14%, gap -2.9) | | | | **RED** |
| puzzle NZP / trap rate / null margin | 0.41 / 0.18 / +0.41 | | | 0.00 | |
| IRT theta | 0.83 +/- 0.11 | | | | 12 items retired |

## 8. Behaviour and tendencies
### 8.1 Mana
| Metric | Value | Null | Previous |
|---|---|---|---|
| mana utilisation p50 (t4-t8) | 0.51 | 0.00 | 0.44 |
| missed land drop rate (t<=6) | 0.07 | 1.00 | 0.11 |
| colour screw turns per game | 1.9 | | 2.2 |
| floated / produced (gated) | 0.21 | n/a (gate) | 0.29 |
| land sequencing, strictly dominated rate | 0.14 | 0.31 (random) | 0.17 |
### 8.2 Per colour
| Colour | usage_ratio | win rate | n games | deck utilisation |
|---|---|---|---|---|
| W | 0.94 | 51.2% [46, 56] | 402 | 0.71 |
| U | 0.61 | 47.8% [43, 53] | 411 | 0.55 |
| B | 0.88 | 52.9% [48, 58] | 398 | 0.68 |
| R | 1.02 | 50.4% [45, 55] | 405 | 0.74 |
| G | 0.97 | 49.9% [45, 55] | 400 | 0.72 |
Note: U usage_ratio 0.61 is the standout. See section 10.
### 8.3 Curve / combat / tempo / cards / commander / deckbuilding
(same shape, one table each, null column mandatory)

## 9. Eyes on glass
Games watched: G-118422 (median), G-119730 (highest regret), G-117001 (lost from winning).
Three observations: [free text, three sentences minimum]

## 10. Conflicts and unresolved questions
| Conflict | Metrics involved | Resolution | Status |
|---|---|---|---|
| Utilisation up, win rate flat | mana_utilisation, anchor_elo | floated/produced also fell, so not a tap-and-float hack; attribute to real spending | RESOLVED |
| Entropy down, diversity down | entropy, agreement gap | agreement gap rose, so convergence not collapse | RESOLVED |
| Blue usage 0.61 | usage_ratio(U), deck utilisation | unexplained | **UNRESOLVED**, prediction registered for next run |

## 11. Decision
**ITERATE.** Rationale in three sentences. Changes for the next run, with the
pre-registered predictions each one implies.

## 12. Incidents
Dated entries from any unscheduled mini-review during the run.

## 13. Budget and cost
| Item | Planned | Actual |
|---|---|---|
| GPU-hours | 72 | 68.8 |
| env decisions | 400M | 412M |
| measurement share | <= 5% | 4.2% |
| metric store growth | <= 2 GB/day | 1.7 GB/day |

## 14. Metric lifecycle
Added: none. Retired: 12 puzzle items (zero discrimination). Definitions changed: none.
Decision-utility this review: anchor_elo, clip_fraction_by_class, class_coverage.
Metrics with no decision influence in 5 reviews: [list, proposed for retirement].
```

---

## 6. Decision gates

Applied at R9. Exactly one outcome per review. Each outcome states its evidence requirement, and an
outcome with insufficient n is **not available**.

| Outcome | Criteria (all must hold) | Evidence required |
|---|---|---|
| **SHIP** (promote the checkpoint to the anchor ladder and to the deployed model) | G0/G1/G2 green; `effective_card_coverage >= 90%`; anchor Elo improvement over the current best with 95% CI excluding zero; `cyclic_fraction <= 0.15`; `worst_ancestor_winrate >= 0.50`; no G0 red row; clock contract met with slow-play exposure 0 | Paired evaluation at the n in §8.4, seat-rotated gauntlet |
| **ITERATE** (keep the checkpoint, change something, run again) | Gates green, and either strength improved but below the ship bar, or strength flat with a clearly identified cause | Predicted-versus-observed table plus at least one registered prediction for the next run |
| **ROLL BACK** (return to the previous checkpoint, discard this one) | Any of: anchor Elo **worse** with CI excluding zero; `worst_ancestor_winrate < 0.50`; a confirmatory metric moved against its prediction beyond the seed band with no benign explanation; a G0 regression introduced by this run's code | The rollback target must itself have a green report |
| **KILL** (abandon this line of work) | Two consecutive ITERATE reviews with no confirmatory movement beyond seed bands, or a §3.3 kill criterion fired and is structural rather than a bug | Both prior reports cited by id |
| **INVALID** (the run measured nothing) | Any gate stop in R0, R1 or R2 | The report is still committed. An invalid run is a finding about the harness |

**Thresholds that are declared judgement calls, revisable with evidence:**

| Threshold | Value | Status |
|---|---|---|
| Ship bar on anchor Elo | CI excluding zero **and** point estimate at least +25 | PROVISIONAL |
| Card-coverage ship bar | 90% | PROVISIONAL |
| Cyclic fraction: quotable / headline-forbidden | 0.15 / 0.35 | PROVISIONAL |
| Elo per doubling of reasoning passes, to justify the adaptive-compute programme | at least 25, CI excluding zero | Already declared in `DESIGN_LATENCY.md` §5.4 |
| Plateau window before KILL | 2 reviews | PROVISIONAL |

**No PROVISIONAL threshold may be applied mechanically until run 1 has produced its measured seed
band and A/A band.** Until then those rows print the measured value and the band, and a human makes
the call and says why in section 11.

---

## 7. Cadence

**OWNER DECISION REQUIRED.** The owner said the frequency is to be decided. This is a proposal.

A calendar is the wrong primitive for a training run, so the proposal is **event-driven with a
calendar backstop**.

### 7.1 Triggers

| Trigger | Review type |
|---|---|
| Every 50M environment decisions consumed | Tier 1 |
| Every generation boundary | Tier 2 |
| Any config, code, card-DB or epoch change | Full review of the run that is ending, then a new pre-flight |
| Any PAGE alarm | Unscheduled mini-review (§3.4) |
| Any HALT | Full review, starting at R0 |
| Anchor Elo delta whose CI clears zero | Tier 2, out of band |
| Calendar backstop | Tier 1 at least weekly while a run is live |
| Milestone (a size decision, a go/no-go, anything written down as a project claim) | Tier 3 |

### 7.2 What each tier contains

| Tier | Name | Contents | Wall clock | Compute |
|---|---|---|---|---|
| **1** | Health check | R0, R1, R2, R3, plus decision-count monitoring and the confirmatory metric table. No strength evaluation, no tendencies | about 1 hour | Free, streamed from the log |
| **2** | Full review | R0 through R9: gauntlet Elo, paired evaluation against the previous checkpoint, full tendency pivots, eyes on glass | about 4 hours | One gauntlet slate, 1,200 to 1,600 seat-rotated games, plus paired branch points |
| **3** | Milestone | Tier 2 plus oracle-referenced regret at the expensive tier, held-out-card evaluation with the memorisation residual zeroed, best-response exploitability, sequencing regret, the human preference panel, corpus re-mining, and a full anchor re-baselining if the epoch changed | 1 to 2 days | Large. Budgeted separately and named in the manifest |

### 7.3 Proposed default

- Tier 1: **every 50M decisions, and at least weekly.**
- Tier 2: **every generation boundary, and at least every 2 weeks while training.**
- Tier 3: **at each milestone, minimum every 8 weeks.**

The owner sets the final numbers. The mechanism (event triggers, three tiers, a calendar backstop) is
the part worth keeping regardless of what the numbers become.

---

## 8. Comparison discipline

This section decides whether an observed difference is real. Most of what a review says is a
comparison, and most naive comparisons in an RL dashboard are wrong.

### 8.1 The design: paired, interleaved, common random numbers

- **Always paired.** Compare A and B on the **same** positions, decks, opening hands, library orders,
  opponent and seats. Never two independently run means.
- **Common random numbers.** Separate RNG streams (shuffle / engine / policy / exploration) so that
  forcing a different action does not desynchronise the shuffle. Without separated streams, CRN
  silently fails and the pairing buys nothing.
- **Interleaved in one process.** Alternate arms within a process, as `DESIGN_LATENCY.md` §5.5
  requires for clock drift. The analogue here is deck-draw variance and machine state.
- **Seat rotation, mandatory in a pod.** Every matchup is played with the agent in every seat, equal
  counts. Report the rotated aggregate **and** the per-seat breakdown. Turn order in Commander is a
  large effect and an unrotated pod result is not a policy measurement.
- **Mirrored pairings.** Each deck pairing is played in both directions with the same seeds.
- **Report the paired difference and its CI**, not two means with two CIs. Overlapping marginal CIs
  do not imply a non-significant difference, and non-overlapping ones are not the test.

### 8.2 Paired branch-point evaluation

The primary "did the change help" instrument. It is buildable in the first week of the rebuild
because it needs only snapshot/restore and separated seeds: no oracle, no search, no make/unmake.

1. Play a common prefix under a **neutral third policy** to a randomly sampled decision index.
2. Snapshot.
3. Continue twice, once with A acting for the seat under test, once with B, identical RNG, identical
   opponents.
4. `d_i = outcome_A - outcome_B`. Estimate the mean with a **paired bootstrap** CI.
5. Report the difference **broken down by difficulty cell, phase and turn bucket**.

**Prefix policy matters.** If prefixes come from A, the corpus is on-distribution for A and off for
B, which biases toward A. Use a neutral policy, or split 50/50 and report both.

**Honest sizing.** With a measured disagreement rate `d`, the variance of the paired difference is
approximately `d`, against `0.5` for an unpaired two-arm win-rate comparison, so the sample-size gain
is about `0.5/d`. At `d = 0.15` that is **3.3x fewer samples**, and each sample is a partial game, so
roughly **5 to 7x cheaper in wall clock**. It is 5x, not 100x. The larger win is attribution: it says
*where* the difference came from, which a win rate structurally cannot.

### 8.3 Clustering: the mistake that makes a dashboard lie

**Every confidence interval in this protocol is a clustered bootstrap over games**, resampling
*games* with replacement, 2,000 resamples. Decisions inside a game are massively autocorrelated
through the recurrent state, the deck and the opponent. At a measured **p50 of 2,173 decisions per
game**, a naive per-decision CI is several-fold too narrow. This is the single most common way an RL
dashboard reports significance that does not exist.

### 8.4 Sample size: the arithmetic, printed so nobody has to argue about it

For an unpaired win rate against 50%, alpha 0.05 two-sided, 80% power:

```
n = (z_0.975 + z_0.80)^2 * p(1-p) / delta^2 = 7.85 * 0.25 / delta^2
```

| Question | Games needed |
|---|---|
| Is 60% different from 50% | **196** |
| Is 55% different from 50% | **784** |
| Is 52% different from 50% | **4,900** |

**A 55% win rate over 200 games is not significant.** The Wilson 95% interval is roughly
`[48.1%, 61.6%]` and it contains 50%. This is the exact number the owner asked to be able to reason
about, so it is printed here.

For Elo, with `dElo/dp = 400 / (ln 10 * p(1-p))` which is about `695` near p = 0.5, the standard
error is about `347 / sqrt(n)`:

| Games per pairing | Elo 95% CI |
|---|---|
| 200 | **+/- 48** |
| 400 | **+/- 35** |
| 1,000 | **+/- 22** |
| 2,100 | **+/- 15** |

**A 20-Elo improvement measured over 400 games is not a result.** Print the CI or do not print the
Elo. Draws reduce the variance somewhat; the harness computes the CI from the realised outcome
distribution, and this table is for planning.

**Minimum-n refusal rules, enforced by the harness rather than by discipline:**

| Statistic | Refuse below |
|---|---|
| Any p99 | 3,000 samples |
| Any p99.9 | 10,000 samples |
| ECE or a reliability curve | 1,000 decisions, and 100 per equal-mass bin |
| PR-AUC / AP / F1 | 50 positives from 5 distinct games |
| Brier resolution per turn bucket | 30 games in the bucket |
| Elo per pairing | 400 games |
| Any per-colour or per-archetype outcome pivot | 400 games **in that cell** |
| Any per-decision behaviour rate | 2,000 non-trivial decisions |

Below the threshold the cell prints `n=<value>, INSUFFICIENT`, never a number.

Use **equal-mass, never equal-width** calibration bins. Equal-width bins are empty at the extremes,
which is exactly where the interesting errors live, and ECE then degenerates into bin-count noise.

### 8.5 Multiple comparisons

Between the tendency pivots and the diagnostic tables, a full review renders on the order of
**thousands of cells**. At nominal 95% intervals that manufactures roughly one false "significant"
row per twenty cells. Per-metric CIs are necessary and not sufficient.

**The rule:**

- **At most six confirmatory metrics**, pre-registered before the run with directions. Alpha is spent
  there, with Holm correction across the six.
- **Everything else is EXPLORATORY**: rendered with CIs, tagged in the report, and **may not justify a
  decision on its own**. Its only power is to become a confirmatory prediction for the next run.
- A metric may not be promoted from exploratory to confirmatory **after** its value has been seen in
  the run it would be judging.

### 8.6 Epoch boundaries: the comparability break that is already scheduled

Every per-decision metric uses decisions as its denominator. The planned action-space work collapses
N pairwise blocker clicks into one structured assignment and auto-resolves forced decisions,
currently **34.24% of the stream**, against a class mix of **55.0% PassPriority and 37.1%
ActivateMana**. That change will move decisions per game by a large factor and silently invalidate
every per-decision series across the boundary, **including the Elo-per-decision learning curve**.

Procedure at every epoch boundary:

1. Increment `env_contract_epoch` in the manifest. The metric store partitions on it.
2. **Re-run every retained checkpoint under the new contract** on the gauntlet, to bridge the series.
   Report old-epoch and new-epoch values for the bridge checkpoints.
3. **Re-baseline the anchors.** `RandomAgent` over a different action space is a different agent, and
   its Elo pin of 0 is only meaningful within an epoch.
4. Re-cut and re-hash the position corpus. Report against both versions where both exist.
5. Report per-decision, **per-turn and per-game** denominators side by side, permanently. Turns per
   game survives an action-space change; decisions per game does not.
6. The report prints `EPOCH BOUNDARY` on page 1, and no cross-epoch delta is quoted without the
   bridge.

---

## 9. Measurement budget

Adding a metric is not free, and a protocol that only grows becomes wallpaper.

| Budget | Proposed cap | Enforcement |
|---|---|---|
| Measurement GPU time | **at most 5% of run GPU time** | Printed in report section 13. A breach above 2x is kill criterion K8 |
| Tier 2 review compute | one gauntlet slate, 1,200 to 1,600 games | Declared in the manifest |
| Tier 3 review compute | named and budgeted per milestone, never open-ended | Owner approves |
| Metric store growth | **at most 2 GB/day** | Two-tier logging, §10.2 |
| Review wall clock | Tier 1 one hour, Tier 2 four hours | If a tier routinely overruns, cut metrics |

**Displacement rule.** Adding a metric to a tier requires naming the metric it displaces, or
demonstrating headroom in the budget. This is the mechanism that keeps the registry in §10.1 from
accreting until nobody reads it.

---

## 10. Housekeeping

### 10.1 Metric registry and lifecycle

One file, `docs/metrics_registry.json`, one row per metric:

```
{id, name, definition_version, formula_ref, tier, engine_requirements[],
 null_value, random_value, pairing_partner, owner, added_date,
 how_to_read,                       // one line, rendered into every report
 decisions_influenced: [{review_id, outcome}]}
```

Rules:

- **Changing a definition mints a new id.** Never mutate an existing series.
- **`how_to_read` is stored with the metric and rendered into every report.** A protocol used over a
  year will be read by a future self who does not remember why a threshold was 0.15.
- **Retirement:** a metric with no entry in `decisions_influenced` after 5 reviews is proposed for
  retirement at the next Tier 2. Retiring it is the default; keeping it requires a one-line reason.
- The same discipline applies to puzzle items, which the IRT fit auto-retires for zero discrimination.

### 10.2 Storage and retention

Two-tier logging, sized so the store does not die of its own output.

| Tier | Content | Size | Retention |
|---|---|---|---|
| Always-on compact row | entropy, top-1 probability, top-2 margin, chosen class, value, passes, ms, forced flag, support size, seat, turn, phase | about 40 bytes per decision, about 1.6 GB/day at 40M decisions/day | 30 days full, then downsample to per-game aggregates kept forever |
| Sampled full-vector row | full probability vector, raw pre-transform logits, menu, what was filtered and why, menu hash | about 500 bytes, at 2% stratified sampling about 0.4 GB/day | 30 days, then keep the strata summaries |
| Replays | gzipped typed event stream, about 450 KB per game compressed | selective | every gauntlet game of a reviewed checkpoint forever; 1% of training games for 30 days |
| Reports, manifests, registry | text | tiny | forever, in git |

**Stratified sampling biases every downstream aggregate unless reweighted.** The sampled tier is
aggregated with **Horvitz-Thompson weights** `1 / p(sample | stratum)`, or every metric computed from
it skews toward the over-sampled hard decisions.

Note the existing failure at small scale: `logs/` currently holds 149 files and 449 MB, of which 228
MB is unstructured `StateRecorder` JSON from which no metric is parseable. A protocol that emits 2
GB/day with no retention policy repeats that at 200x scale.

### 10.3 Pipeline data-quality invariants

Asserted at pre-flight on a smoke slate, and again at R0 on the real run. Silent partial logging loss
makes a metric **wrong** rather than absent, which is far more dangerous.

| # | Invariant |
|---|---|
| Q1 | The sum of per-term rewards equals the logged total, for every transition |
| Q2 | Decision count in the replay equals decision count in the training buffer equals decision count in the metric store |
| Q3 | Exactly one terminal record per (game, seat) |
| Q4 | No gaps in the monotonic event index within a game |
| Q5 | Sampled-tier stratum counts match the intended sampling probabilities within tolerance |
| Q6 | Per-run row counts within expected bounds, given games and decisions |
| Q7 | Every decision row's `menu_hash` matches the menu the executed action was drawn from |
| Q8 | Every metric row carries the full identity stamp: run, checkpoint, SHA, card-DB hash, config hash, seed, epoch, schema version |

### 10.4 The A/A test: a null policy for the instrument

Everything else in this protocol tests the **policy** against a null. This tests the **instrument**
against a null.

1. Run the full review pipeline on **two identical checkpoints**, or on one checkpoint against itself
   under different evaluation seeds.
2. **Every confirmatory metric must report no difference.** A metric that reports a difference is
   broken, or its band is understated. It does not get published until fixed.
3. Add a **canary**: one metric computed against a deliberately shuffled label. It must come out at
   chance.
4. Add a **known-answer synthetic run**: a scripted policy whose true metric values are known by
   construction, which the pipeline must reproduce.

The A/A output defines the **A/A band**, which together with the seed band replaces every PROVISIONAL
threshold in this document. Re-run the A/A whenever the harness changes.

---

## 11. When the numbers disagree

They will. Four measurement lenses running on one run guarantees conflicts. This section is the
tie-break, written before the first conflict rather than during it.

### 11.1 Precedence ladder

When two readings conflict, the higher rung wins and the lower reading is recorded as unexplained
rather than discarded.

1. **Engine correctness** beats everything. If G0 is red, all other readings are void, including the
   good ones.
2. **Validity and attribution** beat magnitude. A large effect inside the seed band is not an effect.
3. **Absolute strength against fixed anchors** beats relative strength against the league.
4. **Confirmatory metrics** beat exploratory ones.
5. **Metrics with a measured null** beat metrics without one.
6. **Metrics whose numerator requires acting well** beat metrics satisfiable by inaction.
7. **Direct measurements** beat proxies. A proxy that disagrees with its own calibration target is a
   broken proxy, not a discovery.

### 11.2 Named conflict pairs and their discriminators

| Conflict | The two readings | Discriminator |
|---|---|---|
| Mana utilisation up, strength flat | Learned to spend / learned to dump mana into bad spells | Floated-mana ratio and two-for-one rate. If floating fell and card quality held, it is real spending. If activation concentration rose, it is a mana-generation reward hack |
| Entropy down, strength up | Converging / collapsing | Importance-stratified agreement gap. Consistency rising **on high-stakes decisions only** is convergence. Consistency rising everywhere is collapse |
| Diversity up, strength up | Exploring / adding noise | Context discrimination. Diversity with zero context discrimination is noise wearing diversity's clothes |
| Elo up, tendencies unchanged | Real improvement / rock-paper-scissors cycling | Cyclic fraction, plus anchor Elo against league Elo. If the anchors are flat, the ladder is made of itself |
| Elo up, worst-ancestor win rate down | Progress / catastrophic forgetting | The forgetting matrix decides. Forgetting outranks the aggregate |
| Reward up, win rate flat | Better play / reward hacking | Reward-outcome decoupling. Below 10 points, the reward is not measuring winning |
| Puzzle score up, gauntlet strength flat | Real skill / corpus overfit or a null-favourable item | Null margin per item and IRT discrimination. A rising score concentrated in low-discrimination items is not skill |
| Clip fraction healthy, nothing learning | Stable / frozen | Clip fraction and KL are **in-band** metrics: a frozen policy has ratio 1, clip 0, KL 0, which reads as perfectly healthy. Always read them beside the gradient census and the learning curve |
| Blunder rate excellent, missed gain high | Careful / paralysed | Missed gain wins. A do-nothing policy scores near-perfectly on blunder rate |
| Calibration excellent, resolution zero | Understands the game / predicts the base rate | Resolution wins. Reliability alone is satisfied by a constant |
| A per-colour gap looks large | Real preference / small-n noise | The per-cell sample-size rule. Below 400 games in the cell the row prints INSUFFICIENT |
| Latency fine, quality down under the clock | Trade-off working as designed / clock reward hack | Cross-tab proactivity against clock pressure. Proactivity falling as pressure rises is the hack flagged as R6 in `DECISIONS.md` |
| Two metrics both moved, both plausible causes | | Neither is decisive. Register a discriminating prediction for the next run and mark UNRESOLVED |

### 11.3 The procedure when the table does not cover it

1. **State both readings explicitly** in report section 10, with values, CIs and n.
2. **Name the discriminating observation** that would settle it, even if you cannot make it now.
3. **Check the cheap explanations first, in order:** a pipeline invariant (Q1 to Q8), a seed-band
   artefact, an epoch boundary, corpus drift, a denominator mismatch (raw versus non-trivial versus
   effective), a per-cell sample-size failure.
4. **Watch the games.** Sample five from the region of disagreement.
5. If it still stands, **record it as UNRESOLVED** and register the discriminating prediction in the
   next run's pre-registration. Then move on.

**UNRESOLVED is a legitimate and common outcome. It is not a failure of the review.** What is a
failure is a review that resolves a conflict by quietly picking the reading that supports the change.
The report has an UNRESOLVED row precisely so that path is more work than honesty.

---

## 12. What this protocol needs from the rebuild

Cheap to include now, brutal to retrofit. Full detail in `METRICS.md`; this is the pointer list, so
it lands in the D1 rebuild rather than being bolted on afterwards.

| Requirement | What dies without it |
|---|---|
| Deterministic seeding, separated RNG streams, deterministic trigger ordering, integer entity ids | §1.3, §8.1, §8.2, all of §11. **Gates everything** |
| Typed event stream with a causing-event index, replacing the discarded `List[str]` from `execute_move` and the silent `except` at `engine.py:278` | §4 R1, §10.3, every correctness counter |
| Full decision record: complete probability vector, raw pre-transform logits, value, entropy, chosen index, **how chosen** (sample / argmax / epsilon override), passes taken, wall-clock ms, forced flag, support size, pre-curation menu with what was filtered and why, menu hash, policy version | §4 R5, R7, and every confidence, calibration, PR-AUC and F1 number. `student.py:131` computes the probability vector and `:138` keeps one scalar. **Not reconstructible after the fact** |
| Reward emitted per term, never pre-summed (13 terms are summed at `environment.py:211`) | §3.1 outcome share, §4 R3, §11.2 reward hacking |
| A terminal transition appended for every seat, including when the opponent's move ends the game | `terminal_coverage`, kill criterion K2 |
| Per-seat keying throughout, not `p1`/`p2` | Everything, in the priority format |
| Stable card identity (`scryfallOracleId`), separated card and vocabulary id namespaces, card-DB content hash in the run header | §1.1 P3, every per-card and per-colour series, `effective_card_coverage` |
| `colorIdentity`, `manaValue`, `types`, `subtypes`, `keywords`, `producedMana` as real columns, and `cmc` actually written onto card entities | §1.5, all of §4 R6. The MTGJSON join is 397/397 clean, so this is one offline script |
| Mana accounting events: produced by source and colour, spent per spell, floated per step, colour-screw events | §4 R6 mana and colour sections |
| Snapshot and restore including the stack, which lives on `Engine` and not in the graph | §8.2 paired branch points, the puzzle corpus, every fixture-based instrument |
| Fixed non-self opponents and a checkpoint league | All of §4 R4, and every absolute strength number |
| A local, append-only metric store with a schema version | All of it. `save_report()` is currently `pass` |
| A per-decision wall-clock timer inside the loop | §3.1 clock rows, the `DESIGN_LATENCY.md` contract |

---

## 13. Open questions for the owner

| # | Question | Default if unanswered |
|---|---|---|
| O1 | Review cadence: are the §7.3 numbers right? | 50M decisions / generation / milestone, weekly backstop |
| O2 | Measurement budget: is 5% of GPU time the right cap? | 5% |
| O3 | Ship bar: is "at least +25 anchor Elo with CI excluding zero" right? | Yes, provisionally |
| O4 | Card-coverage ship bar of 90%: does a run below it ship with a scoping sentence, or not ship? | Ships, with the scoping sentence on page 1 |
| O5 | Who signs off on SHIP and KILL: the reviewer, or the owner? | Owner signs SHIP and KILL; reviewer decides ITERATE and ROLL BACK |
| O6 | Retention: 30 days of full decision rows, or longer? | 30 days |
| O7 | Is the human preference panel (about 3 hours per milestone, 200 blinded decisions) worth the owner's time? It is the only non-self-referential validity check in the whole system | Proposed yes, at milestones only |

---

## 14. The short version

1. **Do not start a run that cannot be trusted.** Conformance green, seeds recorded, every benchmark
   null-calibrated, config and hashes snapshotted, predictions written down.
2. **Watch correctness and learning health live.** Kill early and cheaply.
3. **Measure decisions per game. Never estimate it.**
4. **Review in order:** correctness, validity, learning, strength, decision quality, tendencies,
   style, then watch the games. Stop at the first red gate and publish the stopping point.
5. **Commit the report.** Same sections every time, so it diffs.
6. **Compare paired, seat-rotated, clustered by game, with CIs, against a pre-registered
   prediction.** 55% over 200 games is not a result.
7. **When numbers disagree, use the precedence ladder, and write UNRESOLVED when it is unresolved.**
