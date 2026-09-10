# METRICS.md - the measurement catalogue

**Status:** normative reference. Written 2026-09-09 against HEAD `bc14850`.
**Scope:** every metric this project computes, defined precisely enough to implement, plus the
conventions that make a computed number admissible as evidence, plus the engine instrumentation the
rebuild must emit so that the metrics can exist at all.

This document exists because of one finding. Nothing in the repository can currently tell you
whether a change made the bot better. The only benchmark pays a do-nothing policy **0.9000** on
`scenarios/M21/level_2` (25 byte-identical puzzles, `p1_life: 18`, goal `p1_life >= 20`, scored by
`min(1.0, p1_life / 20.0)` at `MTG_bot/strategic_brain/benchmarker.py:162`) and **1.000** on the 25
`level_1` puzzles with `p1_life: 1` and goal `p1_life > 0` (`benchmarker.py:159`). The only opponent
is a `copy.deepcopy` of the student's own weights refreshed every 20 games
(`MTG_bot/strategic_brain/train.py:50,90`), so the win rate is pinned near 50% by construction.
`TrainingLogger.save_report()` is `pass` (`MTG_bot/utils/training_logger.py:61-63`) and
`log_metrics` returns immediately without W&B (`training_logger.py:36-38`), so **no metric has ever
been written to disk from this checkout.**

The protocol is therefore not documentation of a working system. It is the specification of the
missing measuring stick, written before the engine rebuild (`docs/DECISIONS.md` D1) so that the
instrumentation lands *in* the rebuild rather than being bolted on afterwards.

Companion documents: `docs/DESIGN_SPECTATOR.md` (the replay stream this catalogue reads),
`docs/DESIGN_LATENCY.md` §5 (the statistical template this catalogue inherits),
`docs/DESIGN_ACTION_SPACE.md` (the decision record), `docs/DECISIONS.md` (D1, D8, D9, D10, R4, R6).

---

## 0. How to read this catalogue

Every metric has an **ID**, a **tier**, and an **epoch**.

| Tier | Cadence | Budget |
|---|---|---|
| **TIER 1** | every run, streamed or one offline pass over the replay | must total under 1% of run compute |
| **TIER 2** | weekly, on the frozen evaluation gauntlet | must total under 3% of weekly compute |
| **TIER 3** | milestone only (generation boundary, size decision, go/no-go) | must total under 1% of the cumulative budget |

**Epoch** is the environment-contract version at which a metric becomes computable. A metric is not
"missing" before its epoch, it is **not yet applicable**, and the report prints `n/a (epoch)` rather
than a zero.

| Epoch | Unlocked by | What becomes measurable |
|---|---|---|
| **E0** | rebuilt engine: typed event stream, decision records with full probability vectors, seeding, per-seat keying, per-term rewards, local metric store | run health, engine correctness, mana, combat, tempo, calibration, variability, decision counts |
| **E1** | real priority for non-active players plus a stack the model can act on; mulligan actions | interaction and timing, mulligan family |
| **E2** | 3+ seats, `ATTACK` naming a defender, command zone (tax, recast, commander damage), decklists persisted per seat | Commander family, politics, seat-order analysis |
| **E3** | make/unmake with an undo journal at 10-50 us, self-contained snapshot/restore including the stack | the oracle ladder, regret, oracle-labelled PR-AUC, auto-mined puzzles |
| **E4** | ability-tree compiler, `format_legal` / `engine_supported` flags, held-out card pool | generalisation family |

At E1 the priority gap is not a measurement gap, it is a rules gap: `MTG_bot/rule_engine/engine.py`
grants the decision to the non-active player only at Declare Blockers, so instant-speed interaction
is currently not merely unmeasured, it is structurally impossible to play. Roughly a third of this
catalogue is dark at E0. That is stated up front rather than discovered later; §14 gives the
day-one subset.

**Null column.** `Y` means a null (always-pass) or uniform-random policy scores *well* on this
metric and it must never be quoted alone. `N` means a degenerate policy scores badly or at exactly
zero by construction. `gate` means the metric is a validity check, not a quality score.

---

## 1. Rails: the conventions that make a number admissible

These are not advice. The harness enforces them, and a report that violates one prints the offending
row struck through with the words `NOT EVIDENCE`.

### 1.1 Rail A - gate ordering

Three gates, evaluated in order. A number produced while an upstream gate is red is not a weaker
number, it is a **false** number.

| Gate | Question | Instruments | If red |
|---|---|---|---|
| **G0 engine truth** | did the rules actually run? | `EC-*` family (§3) | no strength, quality or tendency number may be published for this run |
| **G1 signal validity** | does a null or random policy score this too? | `VAL-1` null column, per metric | the row is excluded from the summary |
| **G2 attribution** | is the delta the change, or the seed? | `VAL-2` seed band, `VAL-3` A/A | the comparison is not published as a finding |

`docs/DESIGN_LATENCY.md` §5.2 already encodes exactly this discipline for latency
(`round_spread_pct > 15%` means the row is not evidence). This generalises it.

### 1.2 Rail B - null-zero normalisation is the scoring convention, not a per-metric fix

Every **quality scalar** in this document is published as an affine rescaling in which a declared
null reference scores exactly 0 and a declared upper reference scores exactly 1:

```
NormScore = (M_policy - M_null) / (M_ref - M_null)
```

`M_null` is **measured in the same episode, on the same positions, under the same RNG stream**,
never assumed. It is **not clipped below zero**: a policy worse than doing nothing must be allowed
to print a negative number, because that is a real and diagnostic state.

Under this convention the 0.900 and the 1.000 both become 0 by algebra rather than by vigilance.
That is the point. The failure was not that somebody forgot to check, it was that the scoring
function had no baseline term in it.

Where an upper reference does not exist (no oracle before E3), publish the pair
`(M_policy, M_null)` and the raw difference, and say so. Do not invent a denominator.

### 1.3 Rail C - three denominators, always printed together

**No per-decision average may be reported over the raw decision stream.** Measured on the current
engine with a random policy (`reports/decision_counts_devbox.json`, 24 games): `PassPriorityAction`
55.0%, `ActivateManaAbilityAction` 37.1%, `forced_fraction` 0.3424. An average over that stream is
roughly 8% signal.

| Denominator | Definition |
|---|---|
| `raw` | all decisions |
| `NTD` | non-trivial decisions: support > 1 after canonical dedup, and no forced-field short-circuit (`DESIGN_ACTION_SPACE.md` §1.4) |
| `EDC` | effective decision count: reference value spread `max_a Q - min_a Q > eps`. Needs E3. Before E3, use the policy's own top-1 minus top-2 margin as a declared proxy and label it as a proxy in the row. |

The **dilution factor** `raw / EDC` is printed next to every per-decision mean.

### 1.4 Rail D - statistics

Inherited wholesale from `docs/DESIGN_LATENCY.md` §5.2, which is the best measurement writing in the
repository.

- **Cluster by game.** Decisions inside a game are massively autocorrelated through the recurrent
  state, the deck and the opponent. At a measured p50 of 2,173 decisions per game
  (`reports/decision_counts_devbox.json`) a naive per-decision CI is several-fold too narrow. Every
  confidence interval in this protocol is a **clustered bootstrap over games**, 2,000 resamples,
  resampling games with replacement. This is the single most common way an RL dashboard lies.
- **Paired, interleaved, matched seeds** for every A/B. Report the paired difference and its CI,
  never two independently-run means.
- **Equal-mass bins**, never equal-width, for every calibration curve. Equal-width bins are empty at
  the extremes, which is exactly where the interesting errors are.
- **Never publish the mean of a heavy-tailed distribution alone.** Regret and latency are both
  heavy-tailed; the mean describes no decision that ever happened.
- **Declared prior on every aggregate**: seat count, format, deck-pairing distribution, corpus
  version hash.
- **Minimum-n refusal**, enforced by the harness rather than by discipline:

| Statistic | Refuse to print below |
|---|---|
| any p99 | 3,000 samples |
| any p99.9 | 10,000 samples |
| ECE or reliability curve | 1,000 decisions and 100 per equal-mass bin |
| PR-AUC / AP / F1 | 50 positives drawn from >= 5 games |
| Brier resolution per turn bucket | 30 games in the bucket |
| Elo per pairing | 400 games |
| any per-colour or per-archetype pivot of a game-level metric | 400 games **in that cell** |
| mutual-information style metrics | 20 observations per context cell |

- **Elo reality check, printed in the report header:** at 400 games per pairing the Elo CI is
  roughly +/- 35. **A 20-Elo improvement over 400 games is not a result.** The harness prints the CI
  and refuses to render a rising line without it.

### 1.5 Rail E - multiple comparisons, and the confirmatory / exploratory split

This catalogue defines roughly 110 metrics, most with pivots over colour x archetype x turn bucket x
phase x seat. That is thousands of cells. At 95% intervals over 2,000 cells you manufacture about
100 spurious "significant" rows per review. Per-metric CIs are necessary and **not sufficient**.

- **Confirmatory set: six fixed metrics plus at most two pre-registered per run.** Alpha is spent
  here. Fixed six: `ST-1` anchor Elo, `DQ-1` paired branch-point delta, `CAL-2` win-probability
  resolution, `MANA-2` mana utilisation, `CMB-1` missed-lethal rate, `COL-1` colour usage ratio.
  Nothing else may be cited as the reason for a decision.
- **Everything else is EXPLORATORY**, rendered under a Benjamini-Hochberg FDR of 0.10 within each
  family, and **is forbidden from justifying a decision on its own.** An exploratory finding
  promotes to a pre-registered confirmatory slot on the *next* run. That is the only path from
  observation to conclusion.
- A metric moved into the confirmatory set stays there for at least three reviews, so the set does
  not become a rotating excuse.

### 1.6 Rail F - pre-registration

Before a run starts, its manifest carries a `predictions` block: for each confirmatory metric, the
expected direction, the expected magnitude band, and **what result would falsify the change's
rationale**. The first table of the review is `predicted vs observed` with a hit/miss column.

This is free, and it is the only mechanism in the protocol that scores the **reviewer** rather than
the model. Without it a 200-number dashboard is a machine for generating post-hoc stories.
"Entropy fell, the model is converging" and "entropy fell, which we predicted would not happen, so
something is wrong" are the same observation with different consequences.

### 1.7 Rail G - the instrument must pass its own null test

Every rail above tests the **policy** against a null. `VAL-3` tests the **instrument** against a
null: run the whole review pipeline on two identical checkpoints under different seeds and require
it to report "no difference" on every confirmatory metric. Given that this project has already
shipped a scoring function that paid 0.900 for doing nothing, an instrument that cannot detect its
own no-op is the same class of error one level up.

Mandatory before the first real review and after any change to the metric pipeline.

### 1.8 Rail H - epoch boundaries and comparability breaks

Every per-decision metric in this catalogue uses decisions as a denominator. The action-space work
(`DESIGN_ACTION_SPACE.md`) collapses N pairwise blocker clicks into one structured `BLOCK_ASSIGN`
and auto-resolves forced fields, measured today at 34.24% forced. That change will move
decisions-per-game by a large factor and will silently invalidate every per-decision series across
the boundary, **including the Elo-per-decision learning curve which is the primary axis D9 asks
for**.

Rules:
1. Every metric row is stamped with `environment_contract_epoch`.
2. Series do not cross an epoch boundary. The plot breaks, visibly.
3. Every per-decision metric is also reported **per turn and per game**, which survive the boundary.
4. At each boundary, retained checkpoints and every anchor are **re-run under the new contract** to
   bridge the series. A `RandomAgent` over a different action space is a different agent and must be
   re-baselined, not carried over.

### 1.9 Rail I - the measurement budget

Measurement is capped at **5% of DGX time**, split 1% / 3% / 1% across tiers 1 / 2 / 3. The budget
is printed in every review in GPU-hours and game-equivalents consumed. **Adding a metric requires
naming the metric it displaces.** This rail is what stops the catalogue from becoming wallpaper by
accretion; without it the tier-2 set alone (a 400-game gauntlet, ~800 fixture games for line
diversity, an anchor cross-table at 200 games per pair, rollout counterfactuals at roughly 8
game-equivalents per sampled decision) plausibly exceeds the training it is supposed to be
measuring. §13 totals the bill.

### 1.10 Rail J - metric lifecycle

`metrics/registry.yaml`, committed, one entry per metric: `id, name, version, definition,
engine_requirements, tier, epoch, null_reference, owner, how_to_read, added_on,
decisions_influenced`.

- **Changing a definition mints a new id.** Never mutate a series in place.
- `how_to_read` is a stored string rendered into every report, so the future reader who does not
  remember why the threshold is 0.15 does not have to guess.
- `decisions_influenced` records every time a metric caused a run to be kept, killed or rolled back.
  **A metric that has influenced no decision after 10 reviews is retired**, exactly as `PZL-3`
  retires puzzles with zero discrimination.

### 1.11 Rail K - thresholds are calibrated before they are alarms

No threshold in this catalogue is an alarm until it has a **measured baseline distribution**. The
first five runs after each epoch boundary are a **calibration window**: the harness records each
metric's distribution across seeds and configurations and writes p5/p50/p95 into the registry. Only
then does a threshold become a halt condition. Numbers given as thresholds below are **declared
judgement calls, revisable, and marked `[guess]`** where they are guesses rather than measurements.
A protocol that halts on invented thresholds halts on noise.

### 1.12 Rail L - pipeline completeness invariants

Verifying the game is correct is not the same as verifying the measurement did not lose anything.
Silent partial logging loss makes a metric *wrong*, which is far worse than *absent*. Checked every
run, hard failure:

1. Sum of per-term rewards equals the logged total for every transition, to 1e-6.
2. `decisions in replay == decisions in training buffer == decisions in metric store`.
3. Exactly one terminal record per (game, seat).
4. No gap in the monotonic event index; footer counts match the streamed counts.
5. Sampled-tier stratum counts within 3 sigma of the intended sampling probabilities.
6. Per-run row counts within the registry's expected band.
7. Every row carries `run_id, git_sha, card_db_content_hash, config_hash, seed, generation,
   checkpoint_id, metric_schema_version, environment_contract_epoch`, equal across the run.

### 1.13 Rail M - cross-metric precedence

Conflicts between lenses are guaranteed. Declared precedence, applied top down:

| Conflict | Precedence |
|---|---|
| any G0 gate red vs any strength number | gate wins, strength is not published |
| Elo rising vs `ST-3` cyclic fraction > 0.35 | cyclic fraction wins, Elo is not a headline |
| mana utilisation rising vs `RWD-2` reward decoupling falling | decoupling wins, read utilisation as a suspected reward hack |
| entropy falling vs `VAR-2` context discrimination rising | discrimination wins, read it as convergence |
| entropy falling vs `VAR-2` flat | read it as mode collapse |
| diversity rising vs Elo flat | Elo wins, diversity is noise until strength moves |
| puzzle score rising vs `ST-1` anchor Elo flat | anchor Elo wins |
| any exploratory metric vs any confirmatory metric | confirmatory wins, always |

### 1.14 Rail N - report order

Fixed. The review renders in this order and no other: **gates (G0/G1/G2 pass or fail) -> one
strength verdict -> predicted vs observed on the confirmatory six -> family summaries -> exploratory
appendix -> budget consumed.** A dashboard whose first screen is not the gates will be read as
though the gates passed.

### 1.15 Rail O - somebody has to watch the games

**Mandatory, 30 minutes, before any number in the review is read:** the reviewer opens the spectator
and watches (a) three full games end to end from the gauntlet, (b) the single game with the worst
gate violation, (c) the ten highest-regret decisions with their board states (E3+; before E3, the
ten decisions with the largest own-value drop).

Every serious RL project finds its worst bugs this way. The spectator is already being built for
exactly this purpose (`docs/DESIGN_SPECTATOR.md`). Numbers tell you which games to watch; no number
tells you to watch them.

### 1.16 The review process

**Triggers.** Event-driven, not calendar-driven. The owner deferred the frequency question; a
calendar is the wrong primitive for a training run.

| Trigger | Review type |
|---|---|
| every 50M environment decisions consumed | TIER 1 |
| every generation boundary | TIER 1 + TIER 2 |
| any config, reward, engine-contract or card-DB change | TIER 1 + the confirmatory six, before and after |
| any G0 gate turning red | **unscheduled**, immediate, run halts automatically |
| `ST-1` anchor Elo delta whose CI clears zero | TIER 2 |
| a size decision, a go/no-go, or before any claim leaves the project | TIER 3 |
| 7 days elapsed with none of the above | TIER 1, as a liveness check |

**Automatic halt** (no human in the loop) on: `EC-1 engine_error_rate > 0`,
`RWD-4 terminal_coverage < 0.99`, `PH-3 ratio p99 > 100`, `EC-5 stall + step_cap share > 20%`.
These are the conditions under which the run is provably wasting DGX time.

**The review document** is `reviews/YYYY-MM-DD-<run_id>.md`, committed, with fixed sections:
`gates | headline | predicted vs observed | what changed since last review | what surprised us |
open contradictions | decision taken | budget consumed | next-review trigger`.

**Decision authority.** The review decides exactly one of: `continue` / `continue with one named
config change` / `rollback to checkpoint N` / `kill the run` / `halt and fix the engine`. It may not
decide "keep watching". A review that cannot pick one of those five has found that the confirmatory
set is not answering the question, which is itself a finding and goes in the registry.

**Sign-off** is the owner. The record lives in the repository, not in W&B, because W&B is a viewer
and the repository is the archive.

---

## 2. Evaluation populations

Metrics are meaningless without saying what they were computed over. Four declared populations, each
versioned and content-hashed; every metric row names the one it used.

| Population | Definition | Used by |
|---|---|---|
| **P-LIVE** | the training rollouts themselves | run health, engine correctness, decision counts, reward integrity |
| **P-GAUNTLET** `gauntlet_vN` | the frozen evaluation slate: fixed decks, fixed pairings, fixed seeds, **seat order rotated** | strength, tendencies, calibration, drafting |
| **P-POS** `positions_vN.jsonl` | the frozen stratified position corpus of `DESIGN_LATENCY.md` §5.3, bucketed by legal-action count x entity count x phase | decision quality, latency, invariance probes |
| **P-PZL** `puzzles_vN` | the rebuilt puzzle corpus (§10), every item carrying a measured null certificate | puzzle skill |

**The gauntlet specification is normative and nobody may run an ad-hoc evaluation slate.**
`gauntlet_v1`, built at E0: D decks x A archetype pairings x S seeds, sized so that every published
per-colour cell reaches 400 games. Refreshed only at epoch boundaries, hashed, and a result on
`gauntlet_v2` is never compared to one on `v1` without a bridge re-run.

**Seat order.** In Commander, turn order is a large and real confound. Every pod evaluation rotates
the agent under test through **all seats** and publishes both the rotated aggregate and the per-seat
breakdown. `SYS-6` measures the seat effect itself so it is never mistaken for a policy effect.

**Corpus drift** (`VAL-5`) is printed next to every corpus-based metric, not in a separate section.
As the policy improves, `P-POS` goes off-distribution for it and every number computed over it
quietly changes meaning.

---

## 3. Family EC: engine correctness (gate G0)

Cheap, every run, non-negotiable. These answer "does this run count as evidence at all?"

Today `execute_move` swallows every rules bug into a log line and returns a list of event strings,
and `MTG_bot/strategic_brain/environment.py:153` calls it **without capturing the return value**. A
card that throws costs the agent nothing, produces no state change, and is invisible in every
metric. That is the definition of an unmeasurable system, and it is why "the policy is bad" and "the
spell did nothing" are currently the same observation.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **EC-1** | `engine_error_rate` | exceptions per 1,000 decisions, split by exception type x `oracle_id` x emitting `file:line` | E-EVT typed `engine_error` event carrying a truncated traceback, replacing the swallow-and-log at the `execute_move` except block | T1 / E0 | target exactly **0**. A concentrated distribution (one card > 20% of errors) is a card bug; a flat distribution is an architecture bug | none. This is the one clean metric in the catalogue | gate |
| **EC-2** | `unhandled_node_rate` | during each resolution, walk the `effects_json` tree: `nodes_with_no_handler / nodes_visited`, broken out by `ability_type` | E-EVT `effect_node_entered` / `effect_unhandled` emitted at the resolver dispatch point, not the caller | T1 / E0 | < 2% good, residual concentrated in node types you can name. > 10% means the card pool is largely decorative. Denominator context: the M21 pool has 27 distinct `ability_type` values, 163 `triggered_ability`, 160 `keyword`, 92 `activated_ability`, 84 `loyalty_ability`, and **70 nodes with no `ability_type` key at all** | data errors in the effect tree look identical to unimplemented handlers. Pair with `EC-6` | gate |
| **EC-3** | `no_op_resolution_rate` | a resolution is a no-op if it emits zero state-change events (`zone_change`, `life_change`, `counter_change`, `pt_recompute`, `tap`, `damage`, `draw`, `attach`). Rate over all resolutions, and per `oracle_id` with denominators | E-EVT state-change events; `_move_card_to_zone` instrumented as the single zone choke point | T1 / E0 | < 3% (some spells legitimately fizzle). **Any card with n >= 20 resolutions and rate 1.0 is a blank**, and the `+1.0 * discovery_factor` cast bonus at `environment.py:199` is actively teaching the agent to cast blanks | none | gate |
| **EC-4** | `missed_trigger_rate` | oracle pass sampled at 1% of games: independently evaluate every registered trigger condition against pre/post state; `matched but no stack push / matched` | E-EVT `trigger_fired` with causing-event index, **plus trigger conditions expressible as pure predicates evaluable off the hot path**. If conditions remain imperative handler code this metric cannot be built as specified; the fallback is a differential replay against a second implementation, which is a much larger project and should be said out loud rather than assumed | T1 (1% sample) / T3 (full pass) / E0 | target 0 | intentional replacement effects; whitelist them explicitly rather than tuning a threshold | gate |
| **EC-5** | `termination_reason` | histogram over `{life_zero, deckout, poison, concede, stall_trip, step_cap, adjudicated_timeout, engine_error}`, as percentages and per seat | engine distinguishing them | T1 / E0 | `life_zero + deckout > 95%` good. `stall_trip + step_cap + adjudicated_timeout > 5%` is the earliest and cheapest detector of a degenerate mutual-pass equilibrium. Today two of these silently corrupt everything: the move cap sets `game_over` with `winner_id = None`, the reward pays **-10.0 to both** players (`environment.py:171`) while `train.py:375,377` scores the same game 0.5, and `train.py:370-373` adjudicates timeouts by life total so a stalled game is a **win** | none | gate |
| **EC-6** | `effective_card_coverage` | `oracle_ids that resolved at least once with a non-empty state-change set / oracle_ids present in any deck played`. Plus the **dead-card list**: cards held in hand with priority and full mana >= 30 times that never produced a non-no-op resolution | `EC-3` events plus E-ID stable identity | T1 headline / T2 full table / E0 | > 90% and rising. Below 50%, "the model has learned to play Magic" means "the model has learned the subset of Magic this engine implements", and **every strength number in the report is silently scoped to that subset** | none | gate |
| **EC-7** | `targetable_card_fraction` | cards in the pool that can present a target choice / cards in the pool | static analysis of the effect trees plus the resolver's target-discovery path | T1 / E0 | measured today: `type:"selector"` appears 137 times across 81 cards, the key `target` appears 10 times across 10 cards, and only 7 of those are at the top level where `get_spell_potential_targets` can reach it. **7 of 397.** This one number explains most of the model's apparent stupidity and must be on the front page until it is above 0.8 | none | gate |
| **EC-8** | `no_op_action_rate` | fraction of *executed actions* (not resolutions) producing zero observable state delta | E-EVT | T1 / E0 | **hard gate: > 1% and the entire decision-quality and tendency report prints `INVALID`.** Measuring policy quality in an engine where the actions do nothing measures a different game | none | gate |
| **EC-9** | `menu_hash_mismatch_rate` | fraction of decisions where the executed action was not the scored one | E-DEC menu hash recorded at scoring time and re-checked at execution | T1 / E0 | target exactly 0. Live risk today: `environment.py` re-derives a fresh legal-move list at execution and indexes it with an index computed against a different list | none | gate |
| **EC-Σ** | engine correctness composite | the front-page block: `EC-1, EC-3, EC-5, EC-6` | above | T1 / E0 | the only instrument that separates "the policy is bad" from "the spell did nothing". `DESIGN_SPECTATOR.md` §2 calls its `totals` block the single most valuable line in the file and it is right: this turns "the bot looks dumb" into "63 of its spells resolved as no-ops" | none | gate |

---

## 4. Family VAL: validity and attribution (gates G1, G2)

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **VAL-1** | `null_delta` | for every scored metric M, publish `M_policy`, `M_null` (always the first legal pass), `M_random` (uniform over the menu), and `null_delta = M_policy - max(M_null, M_random)`, **computed on the same corpus, in the same run, with the same seeds** | two extra cheap policy runs | T1 / E0 | `null_delta <= 0` prints `NOT EVIDENCE` and the row leaves the summary. No judgement call, no threshold to argue about | the null and random references must be re-derived at every epoch boundary (Rail H) | gate |
| **VAL-2** | `seed_band` | run the identical config under k = 5 seeds; `seed_band = 2 * std across seeds`, per headline metric | E-SEED determinism | T1 (top 6) / T2 (full table) / E0 | **any A/B difference smaller than the seed band is not evidence.** Printed next to the value, always | 5 seeds gives a poor variance estimate; treat the band as approximate and widen it by the bootstrap CI of the std | gate |
| **VAL-3** | `aa_null` | run the full review pipeline on two identical checkpoints under different seeds, plus one canary metric fed a deliberately shuffled label, plus a known-answer synthetic run | the pipeline | T2, and mandatory after any pipeline change / E0 | the pipeline must report "no difference" on every confirmatory metric and must score the shuffled-label canary at chance. Anything else means the instrument, not the model, is producing the finding | none | gate |
| **VAL-4** | `oracle_independence_check` | regret measured against a different-lineage oracle divided by regret against a same-lineage oracle, at equal budget, on a 200-decision subsample | E3 oracle ladder x 2 lineages | T3 / E3 | ~1.0 means the cheap self-referential oracle is trustworthy. 3 means two-thirds of true regret is invisible to self-reference and every `DQ-*` number carries a footnote | needs two genuinely independent training lineages, not two checkpoints from one run | gate |
| **VAL-5** | `corpus_drift` | Jensen-Shannon divergence between the live rollout position distribution and `P-POS`, over legal-action bucket x entity count x phase | E-DEC | T1 / E0 | rising drift **invalidates every corpus-based metric** and is printed next to them, not in a separate section. `[guess]` alarm at JS > 0.15, to be calibrated | none | gate |
| **VAL-6** | `null_favourable_register` | the standing list of metrics a null or random policy scores well on, rendered into every report | this document, §12 | T1 / E0 | its purpose is procedural: the next person who adds a metric must check it against the register before shipping | none | gate |

---

## 5. Family ST: strength

Elo answers "is A better than B" after thousands of games and cannot say why, where, or by how much
on any given move. It is still the only absolute strength number available, and today the project
has none: the only opponent is the agent's own weights from at most 20 games ago
(`train.py:50,90`), so `episode/student_win_rate_gen` and `..._smooth` (`train.py:397-398`) are
~50% by construction and carry zero information. **Both are deleted from the dashboard.**

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **ST-1** | `anchor_elo` **[confirmatory]** | Bayesian Elo (Whole-History) over checkpoints plus fixed anchors, with `RandomAgent` **pinned at 0 forever**, 95% CI, on P-GAUNTLET | E-LEAGUE: `RandomAgent`, `GreedyAgent` (max immediate life swing), `RuleBasedAgent` (curve out, attack if profitable). `MTG_bot/docs/TESTING_STRATEGY.md:15-18` promises all three and grep finds **zero** of them | T1 batched / T2 full ladder / E0 | the only absolute strength number. Publish only when `ST-3 <= 0.35`. +/- 35 Elo CI at 400 games per pairing | anchors are epoch-specific and must be re-baselined at every boundary | N |
| **ST-2** | `elo_per_decision` | Elo vs the anchor ladder against three x-axes: **environment decisions consumed** (primary), GPU-hours (second), games (last) | `ST-1` plus `SYS-1` | T1 / E0 | decisions is the honest axis and makes D9's monitored decision count the denominator of the whole protocol. Games is reported last because game length varies ~10x and a games axis hides throughput regressions | epoch boundaries break the decision axis (Rail H) | N |
| **ST-3** | `cyclic_fraction` | build the antisymmetric matrix `A_ij = logit(W_ij)` over k checkpoints plus anchors; HodgeRank least squares `s = argmin sum (A_ij - (s_i - s_j))^2`; report `‖A - grad(s)‖_F^2 / ‖A‖_F^2` | `ST-1` cross-table | T2 / E0 | > 0.15 annotate Elo as approximate. **> 0.35 and Elo is meaningless and may not be a headline.** This is the specific reason a self-play Elo can climb for a year while absolute strength does not move. Diagnostically the largest cyclic triangles name the three strategies that beat each other, which is a genuinely interesting Magic result | small k makes the decomposition unstable; needs >= 6 players in the table | gate |
| **ST-4** | `forgetting_matrix` | full `W_ij` over a log-spaced ladder of retained checkpoints (1, 2, 4, 8, ... generations back) plus anchors. Headline `worst_ancestor_winrate = min_{j<i} W_ij` | retained checkpoints | T2 / E0 | < 0.50 means the agent has forgotten how to beat something it used to beat. Any row declining over three consecutive windows is catastrophic forgetting | needs enough games per cell (400) or the matrix is noise | N |
| **ST-5** | `anchor_gap` | `delta Elo_league - delta Elo_anchor` over a window | `ST-1` | T2 / E0 | ~0 healthy. **> 50 Elo means the agent is climbing a ladder made of itself**: it is becoming a specialist in a metagame that does not exist. The subtlest and most expensive failure this project can have | needs both ladders measured over the same window | N |
| **ST-6** | `student_minus_teacher_elo` | Elo gap between the student and the teacher/donor model, logged at every evaluation | `ST-1` plus the teacher as a ladder entry | T2 / E0 | `docs/DECISIONS.md` D8 requires the student to exceed the teacher within a stated number of generations. **A plateau at the teacher's level means the transfer became a cap and the run should be restarted without it** | the teacher does not currently learn: `train_teacher` has no `backward()` and no `optimizer.step()`, and archetype selection is `ORDER BY RANDOM()` blended 50/50 with `random.random()` | N |
| **ST-7** | `best_response_exploitability` | freeze checkpoint theta; train a fresh policy against it for a budget B = 2% of theta's training decisions; report the best-responder's win rate | a full (small) training run | T3 / E0 | > 70% at B = 2% means theta has a hole a cheap opponent can find. **The only robustness number available without a human.** Cost: one training run at 2% scale per milestone, budgeted explicitly in §13, not waved through as "milestone" | the budget B is arbitrary; hold it fixed forever so the series is comparable | N |
| **ST-8** | `win_rate_vs_self` | *deleted.* Kept here only so nobody re-adds it | - | - | pinned at ~50% by construction (`train.py:50,90`) | - | Y |

---

## 6. Family PH / RWD: policy and run health

Nothing in the tree computes entropy, KL, clip fraction, gradient norm or explained variance:
`grep -rn "entropy\|kl_div\|clip_grad\|grad_norm\|explained_var" --include=*.py .` outside `attic/`
returns zero lines. And `grep -rn "manual_seed\|np.random.seed\|random.seed"` returns four hits, all
four in `tools/latency/` (`bench.py:148`, `decisions.py:114,236`, `positions.py:70`) and **none in
the training path**.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **PH-1** | `gradient_flow_census` | after each optimizer step, per named trainable tensor: `dead = grad is None or ‖grad‖ == 0`; report `zero_frac`, per-group `update_ratio = ‖p_after - p_before‖ / (‖p_before‖ + 1e-12)`, **and the list of dead tensor names** | optimiser side only, nothing from the engine | T1, hard gate in the first 100 updates / E0 | healthy: `zero_frac == 0.000`, `update_ratio` in [1e-4, 1e-2] per group. Any tensor dead for 3 consecutive updates fails the gate. **This would have caught the project's central bug on day one**: `type_head`, `source_head`, `target_head`, `intent_proj` and `action_memory_embedder` receive no gradient, and `action_type_embed` is identically zero because the plan loop teacher-forces through a hard argmax, which is why the halting decision and both `thinking/*` metrics measure a randomly-initialised 10-way head | a live gradient does not mean a *useful* head; a tensor can receive gradient and be multiplied downstream by ~0. Pair with `PH-2` | N |
| **PH-2** | `head_ablation_delta` | on P-POS, zero each head's output in turn; report delta top-1 agreement with the unablated policy and delta value MAE (cheap), or delta Elo (expensive) | P-POS | T3 / E0 | a head with live gradients and delta ~ 0 is a decoration. This is the check that says whether five plan steps are five plan steps or one step with four ornaments, which matters because the plan decoder is 86.6% of the decision's weight traffic (`DESIGN_LATENCY.md` §0) | ablation is out of distribution; read relative changes, not absolute | N |
| **PH-3** | `trust_region` | per PPO epoch over minibatch transitions: `r_t = exp(logpi_new - logpi_old)`; `clip_frac = mean(1[|r-1| > eps])`; `approx_kl = mean(r - 1 - log r)` (Schulman k3); exact KL where `menu_hash_old == menu_hash_new`; `kl_undefined_frac`; `ratio_logvar`; `ratio_p99`. **Split by action class and by number of emitted action fields** | E-DEC `logpi_old` recorded with exactly the transform actually sampled from, the full old probability vector, and a menu hash | T1 / E0 | `clip_frac` 0.05-0.30 at eps = 0.2 healthy; < 0.01 means updates are no-ops; > 0.5 means a stale buffer or a collection/train transform mismatch, **and the class split localises it**. The field-count split converts `DECISIONS.md` R4 from a debate into a number: if `ratio_logvar` rises monotonically with field count, the trust region is systematically tighter on complex moves and the per-move product-of-fields ratio is the wrong choice. `kl_undefined_frac > 0.20` voids the row. Today the estimator is broken twice: `student.py:129` mutates `logits[0,i] -= 10.0 * proactivity_bias` **in place** and `student.py:180-181` recomputes without it, so `ratio` at `student.py:183` is `e^{+/-10}` (~22026) on every pass action; and `train.py:295-298` pushes every plan step >= 1 with step 0's `log_prob` and `value` | **in-band metric, not maximise-me.** A frozen policy has `r = 1`, `clip_frac = 0`, `KL = 0`, which reads as perfectly healthy. Never present without `PH-1` and `ST-2` | Y |
| **PH-4** | `explained_variance` **[per channel]** | on a **held-out** transition set: `EV = 1 - Var(R - V) / Var(R)`, computed separately for the outcome channel and the shaping channel. Published beside `EV_null`, a 3-feature linear regression of the outcome return on `[turn, life differential, board differential]` | E-RWD per-term rewards | T1 / E0 | `EV_outcome <= 0` means the value head is worse than predicting the mean, the advantages are noise and PPO is a random walk. `> 0.3` by mid-training is a reasonable ask `[guess]`. **`EV_shape` is a decoy**: shaped return is dominated by per-cast and per-attack bonuses which are near-deterministic functions of hand size and board count, so a two-feature model scores well. If the value head does not beat a three-feature linear regression, the owner should be able to read that sentence off the dashboard | held-out set must be from the same policy version or it measures staleness | N |
| **PH-5** | `advantage_stats` | pre-normalisation `adv_mean`, `adv_std`, `|skew|`, per channel | E-RWD | T1 / E0 | `adv_std` drifting > 10x across generations means the effective learning rate is silently drifting. There is no advantage normalisation at `train.py:390` | none | Y |
| **PH-6** | `buffer_staleness` | per sampled trajectory, `age = current_update_index - update_index_at_collection` (p50/p95/max), plus policy-distance staleness `KL(pi_collect ‖ pi_current)` on the stored menus | E-DEC policy version stamp | T1 / E0 | p95 age above ~4 updates makes the clipped objective's assumptions false. This is the cause and `PH-3` is the symptom; log both so the diagnosis is one step. `ExperienceBuffer.push` only pops at capacity 1000 and is never cleared | none | Y |
| **PH-7** | `grad_norm_preclip` | global gradient norm before clipping | optimiser | T1 / E0 | spikes precede divergence. There is **no gradient clipping anywhere** in the current student | none | Y |
| **PH-8** | `plan_step_health` | per plan step k = 0..K-1: gradient-norm contribution, top-1 accuracy against the action actually executed at that step, the chance line `1/|A_k|`, and the fraction of executed actions sourced from step k | E-DEC per-step distributions | T1 gate / T2 curve / E0 | the owner's binding directive is that every action is trained regardless of plan depth. Make it a number: **step-k accuracy must exceed chance at every k.** If step-(K-1) accuracy is at chance, the plan is one step with decorations, and `COST_MODEL.md` says cut it | meaningless today: steps >= 1 are sampled under `torch.no_grad()` (`train.py:249-266`) | N |
| **RWD-1** | `shaping_to_outcome` | `sum |shaping terms| / sum |outcome term|` per game, p50 and p90 | E-RWD | T1 / E0 | > 1.0 late in training means the gradient is optimising shaping, not winning. Today 13 terms are summed at `environment.py:211` (+1.0 per cast at `:199`, +0.5 per attack, +0.05 proactivity, +0.05 per point of mana generated at `:208`, board presence, board delta, card delta, damage, life, penalty) against a +/-10 terminal at `:169,171`; `docs/BACKLOG.md` puts it at roughly +20 shaping vs +/-10 outcome per 200-step game | should fall as `discovery_factor` anneals. **If it does not fall, the anneal is not working**, and nothing currently checks that | Y |
| **RWD-2** | `reward_outcome_decoupling` | rank games by total reward; `win_rate(top decile) - win_rate(bottom decile)` | per-game reward totals plus outcomes | T1 / E0 | < 10 points `[guess]` means the reward is not measuring winning: reward hacking, engine-bug farming, degenerate equilibrium or shaping dominance all produce this same signature. **A random policy scores ~0.** One line of code, broadest single detector in the catalogue | in a mirror self-play match the outcome is near a coin flip, which compresses the spread; evaluate on P-GAUNTLET as well as P-LIVE | N |
| **RWD-3** | `per_term_outcome_correlation` | Pearson r between each reward term's per-game total and the game result, with n | E-RWD | T1 / E0 | any term with `r < -0.1, n > 500` is actively teaching the wrong thing. Anneal that term to zero rather than rebalancing it: a shaping term that anti-correlates with the outcome is a rule, not an incentive | terms are correlated with each other; report the partial correlations too | N |
| **RWD-4** | `terminal_coverage` | `(game, seat) pairs with a terminal-reward transition present in the buffer / total (game, seat) pairs` | E-RWD, E-DEC | T1, **automatic halt below 0.99** / E0 | must be **1.000**. Today it is roughly 0.5: `train.py:302` accumulates reward only in the student branch, `train.py:317` in the frozen branch discards it, so when the opponent's move ends the game the -10.0 computed at `environment.py:171` is thrown away with no transition appended. **A buffer in which the agent has never once seen a loss cannot learn to avoid one**, and no other metric in this document would tell you that | none. Boolean-grade | N |
| **RWD-5** | `menu_filter_hits` | count per curation rule applied to the menu before the model sees it (repeat cap, mana subsampling, pass removal, stall override), as a share of decisions | E-SLATE pre-curation menu plus the rule that fired | T1 / E0 | tells you what fraction of the agent's proactivity belongs to the training loop rather than to the policy. Today `train.py:166-198` curates and records only a positional map at `:200-205`, which does not say what was removed or why. **The scaffolds cannot be deleted until this number says what they are doing** | none | gate |

---

## 7. Family CAL / CLS: calibration, PR-AUC, F1, confidence

The owner named PR-AUC, F1 and confidences explicitly. Two things must be said before the table.

**First: the current value head is not a win probability and cannot be calibrated as one.**
`student.py:188` regresses `value` against the Monte-Carlo return of the *summed 13-term shaped
reward*, unbounded, with `advantage = return - value` at `train.py:390` and no GAE and no
normalisation. Brier or ECE on that output is a category error. Calibration requires a **separate
win-probability head**. That is model work, not instrumentation, and it is listed as such in §11
(`E-HEAD`). The same is true of the opponent-hand belief metric: the 512-d belief vector produced at
`model.py:226` has **no supervision anywhere** and reaches `train.py:221` as a variable that is
never referenced again. Adding a supervised decoder changes the model being measured, and that
change must be pre-registered like any other.

**Second: "PR-AUC" without naming the head, the candidate set and the base rate is meaningless.**
The full enumeration:

| Head | Positive label | Base rate | Correct metric | Status |
|---|---|---|---|---|
| win at turn N | this seat wins | 0.25 pod / 0.5 duel | **Brier with Murphy decomposition**, not PR-AUC. Not rare | head does not exist (`E-HEAD`) |
| dominant-action existence | a strictly dominant legal action exists and was taken | measured, ~2-8% of NTD | **PR-AUC + F1**, free label, no oracle | needs `E-DEC` only |
| opponent-hand belief | card c is in seat j's hand now | 0.08 on the honest candidate set | **average precision + F1 + P@h**, with lift over the counting null | decoder and loss do not exist |
| oracle-optimal action | `Q*(s,a) >= max Q* - eps` | varies with menu size | **PR-lift**, macro-averaged over menu-size strata | needs E3 |
| "will pass p+1 change my action" | argmax changes | measure it, do not assume; ~0 today | PR-AUC, free self-supervised label | needs a working pass loop |
| trigger-missed / effect-unhandled | engine correctness | - | **not an ML metric.** Correctness counters only (`EC-*`) | - |

Keeping engine correctness *out* of the model scorecard is what makes "the policy is bad" and "the
engine did nothing" distinguishable.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **CAL-1** | `win_prob_brier` | `BS = (1/N) sum_k (W_k(s) - y_k)^2` over a categorical head across `{seat 0 wins, ..., seat n-1 wins, draw}` | `E-HEAD` win-probability head, plus the terminal outcome **and its reason** propagated to every decision of the game | T1 / E0 | never quoted alone. Not binary: Commander is four seats and MTR produces genuine draws, so a two-class formulation is wrong for the priority format | see `CAL-2` | Y |
| **CAL-2** | `win_prob_resolution` **[confirmatory]** | Murphy: `BS = REL - RES + UNC` over B equal-mass bins. `REL = sum (n_b/N)(pbar_b - obar_b)^2`; `RES = sum (n_b/N)(obar_b - obar)^2`; `UNC = obar(1-obar)`. **Report all three.** Headline is `RES` at turn >= 3 | as `CAL-1`, plus turn/phase/seat tags | T1 aggregate / T2 the turn x phase grid / E0 | **`RES` is the anti-null term.** A constant base-rate predictor has `REL = 0` (perfectly calibrated), a respectable Brier and `RES = 0`. That is the 0.900 puzzle failure in calibration clothing, and reporting any calibration number without a resolution term reproduces it exactly | (a) mirror self-play pins the true win probability at 1/n, so calibration looks perfect for the wrong reason: **only meaningful against a fixed-strength opponent.** (b) D10's hard-loss clock changes the label distribution, so runs across that boundary are not comparable | N |
| **CAL-3** | `ece` / `mce` / `signed_bias` / `sharpness` | over 15 equal-mass bins: `ECE = sum (n_b/N)|obar_b - pbar_b|`; `MCE = max_b |...|`; signed bias distinguishes over- from under-confidence; sharpness `= Var(W)` | as `CAL-2` | T1 / E0 | `MCE` large at the extremes with small `ECE` means the model is badly wrong exactly in the positions that decide games, and averaging hides it | equal-width bins would make this meaningless; equal-mass is mandatory | Y |
| **CAL-4** | `time_to_resolution` | `turn* = min { turn : RES(turn) >= 0.05 * UNC }` | `CAL-2` per turn | T2 / E0 | "how early does it know who is winning". Falls monotonically as the model improves. **A strength proxy independent of Elo**, and a null predictor has `RES = 0` at every turn so the statistic is undefined and prints as infinity rather than as a good score | game length; also report against turn *fraction* | N |
| **CAL-5** | `calibration_shift` | `ECE(vs anchor ladder) - ECE(self-play)`, same for `REL` | `ST-1` league | T3 / E0 | a large positive gap is the cleanest symptom of overfitting to the self-play distribution: the value head is calibrated on the states it generated and mis-calibrated everywhere else | needs the league to exist | N |
| **CAL-6** | `action_confidence_calibration` | reliability curve of `pi(a|s)` against the empirical rate that a was the reference-optimal action; `ECE_action` plus the **overconfidence coefficient** = slope of the reliability line minus 1 | `E-DEC` full probability vector plus reference labels | T2 / E0 (dominant-action label) or E3 (oracle label) | pi = 0.9 while optimal 55% of the time is exploration collapse, and is the specific mechanism `DECISIONS.md` D8 warns about for distillation: confidently wrong in exactly the places the teacher was wrong. Under-confidence (pi ~ 0.3 but 80% optimal) means the legality mask is doing the work, not the policy: cross-check `CLS-5` | reference-label quality | N |
| **CLS-1** | `dominant_action_prauc` | the strictly-dominant-action label from `CMB-2` and `CMB-3`: over decisions where a provably dominant action exists, compute precision, recall, **F1 at a held-out threshold** and **PR-AUC of the policy's probability mass on the dominant action** | `E-DEC` full probability vector; the combat solver of `CMB-1` | T1 / E0 | **the cheapest legitimate PR-AUC in the project.** The label is provable, needs no oracle, no rollouts and no human corpus, and costs one restricted combat solve per combat step. Report per action class: pooled F1 hides that recall on blocks is 0.04 | the dominance test is restricted (see `CMB-1` scope); report the covered fraction next to the score | N |
| **CLS-2** | `oracle_prlift` | label every candidate `y_a = 1` iff `Q*(s,a) >= max Q* - eps` (eps = 0.01 win-prob, declared); score `s_a = pi(a|s)`; `prevalence = E[|positives|/|A|]`; **`PR_lift = (PR-AUC - prevalence)/(1 - prevalence)`**, stratified by menu size and macro-averaged | E3 oracle plus `E-DEC` | T2 / E3 | **raw PR-AUC is prevalence-gameable and is never published.** A uniform policy scores exactly `prevalence`, hence lift 0. Prevalence is not stable across positions (three mana taps that are all optimal have prevalence 1.0), so pooling raw AUC across position types is meaningless. **ROC-AUC is explicitly rejected**: with 1-3 positives in a 40-candidate menu the true-negative mass inflates it toward 0.95 for almost any policy | oracle bias (`VAL-4`) | N |
| **CLS-3** | `belief_ap` | decode the belief vector: `b_{j,c} = sigmoid(<MLP(b_t), v_card(c)>)` per opponent seat j and candidate card c. Label from the replay: 1 iff c is in seat j's hand at that decision. Report **average precision with step interpolation** (`AP = sum (R_n - R_{n-1}) P_n`, not trapezoidal, which is optimistically biased on sparse positives), plus **P@h** where h is the true hand size, plus top-h set overlap | `E-HEAD` decoder and loss; per-decision hidden-zone ground truth; `E-ID` stable card identity | T2 (S3) / T3 (S1 and the ablation) / E0 | **the candidate set decides everything and must be declared.** S1 = full legal pool, base rate 7/25,000, random AP 2.8e-4, every number looks spectacular. S2 = the 99 cards of that seat's deck, 7/99. **S3 = cards not yet seen in any public zone, 7/87 ~ 0.080, and S3 is the honest one because its uniform predictor is the card-counting null, which is strong.** Report `AP`, `AP_null` and `lift = AP/AP_null` side by side; **lift <= 1.0 means the head learned nothing beyond counting.** Reporting S1 alone would be the level-2 mistake in a new coat | **the deck-prior leak.** Re-evaluate with the board tokens masked; a head that keeps most of its AP with the board hidden has learned the deck prior, which is the null, not inference. **Report `AP(full) - AP(board-masked)` as the actual result** | Y on S1, N on S3 with lift |
| **CLS-4** | `classification_reporting_contract` | every PR-AUC/F1 row publishes `(candidate set, base rate, n_positives, n contributing games, AP, AP_null, lift, F1@threshold, the threshold, clustered-bootstrap 95% CI)` | - | T1 / E0 | **a single AP with no base rate next to it is not admissible.** Refuse to print below 50 positives or 5 contributing games | - | gate |
| **CLS-5** | `mask_reliance` | `rho(s) = H(pi|s) / log|support(s)|` plotted against support size, per field for structured actions. Plus **mask-ablation mass**: widen the legality mask and report the probability mass the policy assigns to illegal actions | `E-DEC`, `E-SLATE` | T1 (rho) / T2 (ablation) / E0 | `DESIGN_ACTION_SPACE.md` §4.9 names the first half: if rho stays near 1.0 as support grows, nothing is being learned and the wins are the mask's. The ablation half is the direct measurement of learned-over-hardcoded: a policy that has learned the rules puts little mass on illegal actions even unmasked. `[guess]` target illegal mass < 0.10 by milestone 2, falling | with a very tight mask the ablation is out of distribution and unstable. Sample it, never train on it | Y |
| **CLS-6** | `confidence_profile` | top-1 probability `p1`, margin `p1 - p2`, and normalised entropy, **reported per support-size bucket** {2-4, 5-8, 9-16, 17-32, 33-128, 129-512} and never aggregated without a declared prior | `E-DEC` | T1 / E0 | `DECISIONS.md` measures a median legal-action count of 1 over 2,400 decisions and `DESIGN_LATENCY.md` §1.2 measures 21.2% of priority windows with exactly one legal move. **An unstratified "mean confidence 0.94" is a statement about the engine's degeneracy, not the policy's** | up to 70% of early actions are uniform random (`train.py:94`, exploration starting at 0.7 with a 0.15 floor) and nothing records which. Compute only over policy-sampled decisions, which requires `E-DEC how_chosen` | Y |

---

## 8. Family TEND: play tendencies

This is the body of the owner's ask. Two design rules govern the whole family.

**Rule 1: prefer discrimination metrics over level metrics.** A level metric ("how often does it
block?") is maximised by a constant policy. A discrimination metric ("does it block *more often when
the block is free*?") requires conditional structure that no constant policy can fake. The level_2
disaster was a level metric with no conditioning. Every metric below is either a conditional, or
paired with its gate, or flagged `Y` in the null column.

**Rule 2: colour and archetype are axes, not metrics.** Every row emitted by every instrument here
carries `(run_id, checkpoint_id, game_id, seat, deck_colour_identity, archetype, opp_archetype,
turn, phase, epoch)`. The per-colour and per-archetype views are then pivots over one table. This is
the only way the ask scales: 40 metrics x 5 colours x 6 archetypes is 1,200 numbers built separately
and one `GROUP BY` built properly.

Two consequences of Rule 2 stated now:

- **Two colour attributions exist and answer different questions.** *Deck colour* is what the
  builder gave the seat. *Cast colour* is what the policy chose to spend mana on. Their ratio is
  `COL-1`.
- **"Archetype" is currently a label with nothing behind it**, so the protocol defines it twice: the
  *declared* recipe id, and a *measured* post-hoc k-means cluster over
  `(mean mana value, creature share, colour share, interaction share, land count)`. Report both.
  Disagreement is itself a finding about the deck generator, and given `ORDER BY RANDOM()` selection
  and a teacher that takes no optimiser step, they will disagree.

### 8.1 Mana tendencies (the owner named this)

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **MANA-1** | `missed_land_drop_rate` | over turns where the seat held >= 1 land in hand at its precombat main: turns ending with `lands_played == 0` / such turns. Split at turn <= 6 and > 6 | keyframe hand contents, `is_land`, lands-played counter | T1 / E0 | < 1% on turns 1-6 is correct play; > 10% means the policy does not understand that land drops are free. **A null policy scores 1.000, the worst possible value**: the denominator conditions on the land being available, which makes the metric inherently anti-null | legitimate late holds (bluff, hand-size effects); hence the turn split | N |
| **MANA-2** | `mana_utilisation` **[confirmatory]** | per turn t: `available(t)` = total mana producible from untapped permanents at the seat's precombat main, from a **real mana solver over `producedMana`**, not a land count; `spent(t)` = mana actually paid for spells and activations during t. Report the curve over t = 1..15 plus the aggregate `sum spent / sum available` | `E-MANA` mana events, `E-CARD` `producedMana` | T1 / E0 | 0.75-0.95 on turns 3-8 for a strong Commander deck, dipping only when deliberately holding interaction. Below 0.5 from turn 4 is flood, screw or paralysis, and `MANA-4` / `MANA-8` say which. Null = 0.000 | **a policy that dumps mana into bad spells scores well.** Gate against `CARD-2` and win rate: rising utilisation with flat win rate means it learned to spend, not to spend well | N |
| **MANA-3** | `curve_conformance` | `JSD(H_cast ‖ H_deck)` over mana value, plus `on_curve_rate` = fraction of turns 2-8 where the seat cast >= 1 spell of MV >= available(t) - 1 | `E-DECK` decklist in the header, `E-CARD` `manaValue` on the entity | T1 / E0 | near 0 means it casts its deck. **Large JSD with mass at low MV is the classic reward hack**: `environment.py:199` pays `+1.0 * discovery_factor` per cast regardless of what was cast, a direct incentive to cast the cheapest thing repeatedly. This metric is the detector for that specific term | genuinely screwed games shift `H_cast` down honestly; condition on `MANA-2 >= 0.6` | N |
| **MANA-4** | `colour_screw_exposure` | at each precombat main, count hand cards `castable_by_total_mana AND NOT castable_by_colour`. `screw_turns` = turns with >= 1; `screw_severity` = sum of max MV among such cards | `E-CARD` true `colorIdentity` and `producedMana` | T1 / E0 | > 2 screw-turns per game means the **builder**, not the pilot, is at fault; attribute accordingly and pivot per colour pair. **Today this is not approximately wrong, it is systematically wrong**: `deck_generator.py:96` builds the pool with `mana_cost LIKE '%W%'` and `:182-186` derives a deck's colours by substring over `mana_cost`; colour-from-cost disagrees with true `colorIdentity` on **40 of 397 cards (10.1%)** and **every one of the 40 is a land**, which is exactly the population a mana metric is about | none once the DB is fixed | N |
| **MANA-5** | `source_deficit` | per colour c in the deck's identity, with pip requirements from the decklist: `deficit(c) = required_sources(pip_count, earliest_MV) - actual_sources(c)` against a fixed published source table, declared and versioned. Report `sum max(0, deficit(c))` per deck | decklist plus `producedMana`. **No games needed** | T1 pre-flight / E0 | computable before a single game is played, so it **gates the run**: a deficit > 3 on any colour means the games that follow measure a broken manabase, not a policy | the reference table is a human heuristic and is declared as such, not treated as ground truth | N |
| **MANA-6** | `land_sequencing_regret` | at each land drop with >= 2 distinct legal lands, solve a bounded knapsack over the hand: for candidate land l, `castable(l)` = max total MV of a hand subset castable next turn given the resulting base. `regret = max_l' castable(l') - castable(l_chosen)`. Report mean regret and `strictly_dominated_rate` | produced-mana per land, ETB-tapped flag, hand contents | T2 / E0 | separates "plays lands" from "plays the right land". Microseconds per decision, no search, no rollouts, no opponent model. A random policy has positive mean regret; a strong policy drives `strictly_dominated_rate` under 5% `[guess]`. Track the hard subset (>= 3 candidate lands) separately since the trivial cases are solvable at zero | **myopic by construction** (one turn ahead). Read changes across checkpoints, not the absolute level | N |
| **MANA-7** | `wasted_mana` | `sum over steps of (mana in pool at the moment the pool empties) / mana produced` | `E-MANA` float events | T1, **gated** / E0 | **a null policy never taps, so it produces 0 and wastes 0, a perfect score. Never report this ratio without the gate `produced >= 3 * turns` and never without `MANA-2` beside it.** It matters anyway because `environment.py:208` pays `max(0, delta pool) * 0.05 * discovery_factor` for *producing* mana with no requirement to spend it: tap everything, float everything, collect. The measured 37.1% `ActivateManaAbilityAction` share under a random policy is exactly the shape a trained policy would converge to | see gate | **Y** |
| **MANA-8** | `flood_screw_conversion` | classify each (game, seat, turn) as screwed / flooded / normal by declared rules; report `P(win | first flooded turn <= X)` and `P(win | screwed turns 3-5)` against the same conditional for the baselines. Companion `sink_rate` = share of surplus mana routed into activated abilities, X-costs or draw | keyframes plus `E-MANA` | T2 / E0 | the win-rate conditional says whether the bot *handles* variance; `sink_rate` says whether it knows what mana sinks are for. In Commander, flood conversion is a large share of real skill | heavily archetype-dependent; uninterpretable unless pivoted by archetype | N |

### 8.2 Colour tendencies (the owner named this)

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **COL-1** | `colour_usage_ratio` **[confirmatory]** | per colour c: `(share of mana spent on cards of colour identity c) / (share of colour c in the declared decklist)` | `E-DECK`, `E-CARD` `colorIdentity`, `E-MANA` spend-per-spell | T1 / E0 | 1.0 means the policy uses the colour as much as it was given it. 0.4 means it systematically ignores its cards of that colour. One `GROUP BY` over the tendency table, and **the crispest per-colour number available** | requires the deck's colour identity to be correct, which today it is not (see `MANA-4`), and requires the commander to be a real commander, which today it is not (`game_initializer.py:81-88` pops `working_deck[0]` **before** shuffling at `:90` over a list `deck_generator.py:196` already shuffled, so the commander is a uniformly random card, frequently a basic land) | N |
| **COL-2** | `colour_win_rate` | win rate on P-GAUNTLET pivoted by deck colour identity and by colour pair | `ST-1` machinery plus `E-DECK` | T2 / E0 | needs **400 games per colour cell**, which the gauntlet is sized for. The standing temptation is to read a 5-point gap off 40 green games; the harness refuses to print the cell | archetype and colour are confounded in the current builder; report the colour x archetype grid, not colour alone | N |
| **COL-3** | `colour_cast_latency` | median turn of first spell cast per colour, as a Kaplan-Meier survival curve with right censoring | `E-DECK`, cast events | T2 / E0 | a colour whose curve is censored far to the right is a colour the policy does not play. Survival form is required because a policy that never casts a colour has an undefined mean and a perfectly readable curve | manabase quality (`MANA-5`) | N |
| **COL-4** | `colour_identity_legality` | fraction of the 99 legal under the commander's `colorIdentity` | `E-CARD`, `E-DECK` | T1 pre-flight / E2 | **must be 1.000 by construction. Any value below is a deck-generator bug.** One line, costs nothing, catches a whole class of silent corruption. The current builder cannot even compute identity | none | gate |

### 8.3 Combat

Combat is where badness is provable rather than arguable, because a large fraction of combat errors
are strictly dominated. **Scope declaration, and this is load-bearing:** the general "minimum damage
the defender can let through" problem is **not a bipartite assignment problem and is NP-hard** once
multi-blocking, trample, deathtouch, menace and attacker-controlled damage-assignment order are
present. Any claim that it is a sub-millisecond exact matching is wrong.

So the combat family is defined over a **declared, versioned, restricted subset**
`combat_scope_v1`: positions where no attacker has trample, deathtouch or menace, no blocker has
deathtouch, and at most one blocker may be assigned per attacker. On that subset the defender's
optimal assignment **is** a min-cost bipartite matching over `|A| x |B|`, exact and cheap. Every
combat metric publishes `scope_coverage` = the fraction of combat steps inside the subset, and
positions outside it are reported separately under an explicit branch-and-bound solver with a node
cap and a `solver_timeout_rate`; a timed-out position is excluded and counted, never approximated
silently. If `scope_coverage` falls below 0.5 the family is reported as scoped and is not a headline.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **CMB-1** | `missed_lethal_rate` **[confirmatory]** | at every declare-attackers step inside `combat_scope_v1`: attacking with all legal attackers maximises damage-through for the lethal question, so compute `min_damage` under the defender's optimal matching once; the position is **forced lethal** if `min_damage >= defender life`. Metric = `forced lethal available and not taken / forced lethal available`. **Headline is the unanswerable subset** (defender has zero untapped mana); the contaminated superset is reported separately | keyframe: effective P/T, keywords, attachments, tapped, life. `E-ACT` structured `ATTACK_SET` makes "not taken" unambiguous | T1 / E0 | 0.00-0.02 for a strong player. **A null policy and any never-attacks policy score 1.000, the worst possible value.** There is no version of this metric that a do-nothing policy wins. Answers the coach's first question: when you had the game won, did you take it | hidden information: the defender may hold a trick, so a "missed lethal" can be correct fear. Hence the unanswerable subset as headline. Also `scope_coverage` | N |
| **CMB-2** | `free_block_miss_rate` | a free block: attacker power < blocker toughness and blocker power >= attacker toughness, inside `combat_scope_v1`. Metric = `free block available and not made / free block available` | as `CMB-1` | T1 / E0 | 0.00 correct, > 0.05 means the bot does not understand blocking. Null = 1.000. **The cleanest single number for "it never blocks"**, which Elo cannot see. Note the current engine emits one action per (blocker, attacker) pair, so making one block costs a whole model call; the structured-decision collapse (`E-ACT`) is a prerequisite for this to measure judgement rather than patience | `scope_coverage` | N |
| **CMB-3** | `unjustified_chump_rate` | a chump block: blocker dies, attacker survives. **Justified** if `defender_life <= incoming unblocked damage` or the blocker was dying to an SBA anyway. **Unjustified** if `defender_life > incoming + 5` and blocker MV >= 2. Metric = unjustified / total blocks | as `CMB-1`, plus `E-EVT` death causes | T1 / E0 | the conditional is the whole metric: chumping at 3 life is correct, chumping at 38 is throwing away a card. A constant "always block" policy scores badly here and well on `CMB-2`; **the pair pins down judgement, which neither does alone** | the +5 and MV >= 2 constants are `[guess]` and calibrated in the first window | N |
| **CMB-4** | `suicidal_attack_rate` | an attack is suicidal if a block exists where the blocker survives and the attacker dies, and the attack was not required (`race_index < 1`, no trample value). Report raw and conditioned | as `CMB-1` plus `TMP-2` | T1 / E0 | bluffing and forced damage in a race are legitimate, hence the conditioning | `scope_coverage`; bluffing is not observable | N |
| **CMB-5** | `trade_quality` | per combat: `sum MV(opponent permanents that died) - sum MV(own permanents that died) + 0.5 * (life damage prevented)`. Per-combat mean and per-game total, pivoted per colour | `E-EVT` deaths attributed to a cause, `E-CARD` mana value | T1 / E0 | pivot per colour has a **known correct shape**: green should be winning combats, blue should mostly be avoiding them. A per-colour metric with an expected shape is rare and valuable | MV is a crude value proxy; a 1-MV token engine beats a 6-MV do-nothing | N |
| **CMB-6** | `attack_participation` | `sum creatures declared attacking / sum creatures legally able to attack` | keyframes | T1, **paired only** / E0 | **maximised by "attack with everything, always".** Report only as a 2-D scatter with `CMB-4`. The interesting quantity is the conditional difference `E[participation | profitable] - E[participation | unprofitable]`, which is a discrimination metric no constant policy can fake | see left | **Y** |
| **CMB-7** | `combat_regret` | with snapshot/restore, enumerate top-k attack sets and block assignments, evaluate each with a short rollout or the value head, `regret = V(best) - V(chosen)` in win-probability units | E3 | T3 / E3 | 100-1000x a normal decision. Milestone only, on a frozen 200-position corpus, never in a training loop | oracle bias (`VAL-4`) | N |

### 8.4 Tempo

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **TMP-1** | `first_action_survival` | Kaplan-Meier survival curves with right censoring for turn of first attack, first spell, first permanent | keyframes | T1 / E0 | the shape is the archetype fingerprint. **Means are wrong here**: a policy that never attacks has an undefined mean and a perfectly readable curve, flat at 1.0, visually unmistakable | archetype | N |
| **TMP-2** | `clock_and_race_index` | `dmg[t]` per (seat -> opponent) per turn; `clock(t) = opp_life(t)/mean(dmg over last 3 turns)`; `race_index(t) = own_clock/opp_clock` | damage events | T1 / E0 | `race_index > 1` while still attacking all-out is the definition of losing a race you should have stopped racing. **The correlation between `race_index` and attack aggression is the "does it know when to race vs grind" measurement**; zero correlation means one gear | multiplayer makes "the race" ill-defined; at E2 report per opponent pair | N |
| **TMP-3** | `damage_per_mana` | `sum damage dealt / sum mana spent` | `E-MANA`, damage events | T1 / E0 | archetype-diagnostic, useless as a cross-archetype ranking. Pivot only | archetype | N |
| **TMP-4** | `game_length` | median and p90 turn of game end, by archetype, **with `EC-5 termination_reason` as a categorical beside it** | `EC-5` | T1 / E0 | **a do-nothing policy maximises game length.** Never aggregate over games that did not terminate in a win | see left | **Y** |

### 8.5 Card advantage and resources

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **CARD-1** | `card_differential` | `(own hand + own nonland permanents) - (opp hand + opp nonland permanents)` per turn; area under the curve and the value at turn 8. **Publish the two components separately** | keyframes | T1 / E0 | **hand size alone is maximised by never casting anything. Never report hand size as card advantage.** The permanents term is what makes it honest, and even so a null policy scores positively on the hand component, which is why the split is mandatory | at E2, "opp" is three opponents; report per pair and as a table aggregate | **Y** (hand component) |
| **CARD-2** | `two_for_one_rate` | own cards that caused >= 2 opposing cards to leave the battlefield or hand / own cards spent | `E-EVT` causal chains | T1 / E0 | 0.1-0.25 in Commander for strong play. Blue and black should exceed red and green: another per-colour pivot with a known correct shape | needs the causing-event index to be real, not inferred | N |
| **CARD-3** | `stranded_resources` | for the **losing** seat only: hand size at game end, total MV in hand, and `castable_stranded` = MV of cards that were castable at some point and never cast | keyframes plus `E-MANA` | T1 / E0 | **the crispest signature of a paralysed policy**: it had the cards, it had the mana, it passed. A null policy maxes it. Restricting to the loser removes the "I won before I needed them" defence | none | N |
| **CARD-4** | `deck_utilisation` | share of the declared decklist ever cast, and ever drawn, across the game | `E-DECK` | T2 / E0 | ties the builder to the pilot. A deck where 40% of drawn cards are never cast is either miscoloured (`MANA-4`) or full of cards the policy does not understand. **Pivot per colour: this is where "it never casts its blue cards" becomes visible** | game length | N |
| **CARD-5** | `life_as_resource` | voluntary life paid (fetch, pain, activated costs) vs win rate | `E-MANA` cost events | T2 / E0 | in Commander at 40 life, refusing to pay life is a real and common bot pathology | requires cards with such costs to exist in the pool | N |

### 8.6 Interaction and timing (E1: currently unplayable, not merely unmeasured)

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **INT-1** | `instant_speed_rate` | instants cast during an opponent's turn or with a non-empty stack / instants cast | `E-PRIO` | T1 / E1 | ~0.8+ for reactive instants in strong play. **Structurally 0.000 today** | proactive instants are a separate class | N |
| **INT-2** | `hold_discrimination` | `E[untapped mana at end of own turn | >= 1 castable instant in hand] - E[untapped mana at end of own turn | no castable instant in hand]` | `E-PRIO`, `E-MANA`, hand contents | T1 / E1 | **the template for every "sophisticated instrument" in this catalogue.** A bot that always taps out scores 0. A bot that always leaves mana up scores 0. Only a bot that leaves mana up *because it has something to do with it* scores positive. **No constant policy can score on it.** `[guess]` target >= +1.5 mana for a deck with meaningful interaction | decks with no instants have an empty first arm; report n for both arms and refuse below 200 turns per arm | N |
| **INT-3** | `removal_efficiency` | per resolved removal spell: `mv_delta = MV(target) - MV(removal)`; `value_leak` = target had already attacked, resolved an ETB or activated; `dead_removal_rate` = cast with no legal target of MV >= 2 | targeting that works | T2 / E1 | mean `mv_delta > +1` is correct discipline; negative means spending a card to kill worse cards. `value_leak_rate > 0.6` means it always removes too late | **has no population until the ability tree lands**: 7 of 397 cards can currently present a target choice (`EC-7`) | N |
| **INT-4** | `missed_answer_rate` | for each opposing key event (a resolving spell of MV >= 4, removal aimed at the seat's best permanent, or a lethal attack): did the seat hold a legal answer **and** the mana to cast it when priority passed. `had answer and did not use / had answer` | `E-PRIO`, `E-MANA`, hand contents | T2 / E1 | the coach's "why didn't you counter that" as a number. Strong play well under 0.2, residual deliberate. Null and random both ~1.0 | **correctly saving an answer is indistinguishable from missing it.** Partial control: report the MV of what it declined to answer vs the MV of the largest thing it later answered in the same game; a bot that saved correctly shows a positive gap | N |
| **INT-5** | `counterspell_discipline` | `counter_hit_MV` distribution; `counters_stranded` at game end; `first_thing_seen_rate` | `E-PRIO`, stack events | T2 / E1 | a strong player's `counter_hit_MV` sits well above the table's mean spell MV | pool composition | N |
| **INT-6** | `premature_commitment_rate` | for each instant-speed action at priority window w, does a strictly later window w' exist in the same **no-information-gained interval** (no draw, no reveal, no opponent choice between them) at which the identical token sequence was still legal. Rate over instant-speed actions | `E-PRIO`, `E-ACT` typed fields, `E-EVT` for the interval | T1 / E1 | holding instants until the last safe window is one of the most reliable correctness signals in real Magic, and it is learned, never rewarded. **Denominator trap: a policy that never casts instants has an undefined rate and prints `n/a (0 instant-speed actions)`, never a good score** | none once priority exists | N |

### 8.7 Mulligans (E1: zero code exists; specify before the code)

`grep "def mulligan"` across `MTG_bot/` returns nothing, while `MTG_bot/main.py:262` calls
`engine.mulligan(player_id)`, a method that does not exist.
`DESIGN_ACTION_SPACE.md` §1.3 specifies `MULLIGAN_TAKE` / `MULLIGAN_KEEP:CARD_TO_BOTTOM`.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **MUL-1** | `keep_rate_curve` | `keep_rate(k)` for k = 0..7 lands in the opening seven, plus a second cut by `castable_by_turn_3`. Summary scalar `keep_curve_discrimination = keep_rate(2..4) - keep_rate({0,1,6,7})` | `E-MULL` | T1 / E1 | **the shape is the metric, not the level.** Correct: near 0 at k in {0,1,6,7}, near 1 at k in {2,3,4}. **An always-keep policy produces a flat line, instantly distinguishable and unfakeable.** `[guess]` strong >= 0.7, random = 0 | archetype- and format-adjusted; pivot | N |
| **MUL-2** | `keep_decision_auc` | label each keep/mull decision by the eventual game result; ROC-AUC of `P(keep)` against `win` | `E-MULL`, outcomes | T2 / E1 | 0.50 means the mulligan decision carries no information; 0.60+ is real signal. **The owner's AUC ask applied where a real label exists for free** | outcome is a very noisy label over a 200-decision game; hence weekly on >= 2,000 opening hands | N |
| **MUL-3** | `post_mulligan_ladder` | win rate for hands kept at 7 / 6 / 5 / 4 | `E-MULL` | T2 / E1 | a correct policy shows a monotone decline of roughly 5-8 points per card. **A non-monotone ladder (kept-at-6 beating kept-at-7) means the keep decision at 7 is worse than random and the bot should be mulliganing more** | needs 400 games per rung | N |
| **MUL-4** | `bottoming_quality` | under the London mulligan, MV distribution and land count of bottomed vs kept cards | `E-MULL` bottom choices | T2 / E1 | bottoming your only two lands is a specific, detectable, very bot-like error | none | N |

### 8.8 Commander (E2: the priority format, currently the least instrumented)

`grep -i "commander_tax\|commander_damage\|poison"` over `MTG_bot/**.py` returns **zero hits**.
`DESIGN_SPECTATOR.md` §2 plans all three in the keyframe.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **CMD-1** | `commander_recast_curve` | median first-cast turn; casts per game; total tax paid; and `P(recast within 2 turns | current tax = 0, 2, 4, 6, 8, 10+)` | `E-CMD` tax, recast, command zone; `E-DECK` declared commander | T1 / E2 | **the curve shape is the skill.** A correct policy declines monotonically and crosses 0.5 somewhere around tax 4-6 for a mid-cost commander. **Never recasting (flat 0) and always recasting (flat 1) are both wrong and both distinguishable from correct.** Pivot by commander MV | blocked today by the random-commander bug (`COL-1` confounds column) | N |
| **CMD-2** | `commander_damage_awareness` | fraction of games where the seat took >= 15 commander damage from one source without removing or blocking it | `E-CMD` | T2 / E2 | commander damage is a second, invisible life total; ignoring it is a classic new-player error and a certain bot error | requires the pod to contain a commander that can connect | N |
| **CMD-3** | `threat_allocation_correlation` | at each decision directing damage or removal at an opponent, compute a **declared, frozen** threat score for every opponent j: `0.4*norm(board power) + 0.2*norm(cards in hand) + 0.2*(commander on battlefield) + 0.1*norm(mana available) - 0.1*norm(life)`. Then `rho = Spearman(damage and removal directed at j, threat_rank(j))`. Companion `archenemy_share` | `E-SEAT` 3+ seats, `E-ACT` attack naming a defender | T2 / E2 | rho ~ 0 means the bot cannot tell who is winning, which is the random-policy score by construction. rho ~ 1.0 means it always hits the leader, which is **also wrong**: real politics involves not becoming the archenemy. **Target band 0.3-0.7** `[guess]`. The band-not-maximum structure is deliberate: it is the only shape a degenerate policy cannot climb | **the threat function is a measuring heuristic, exposed to the analyst, never to the agent. It is the ruler, not a rule the bot is taught. Do not feed it into the reward** | N |
| **CMD-4** | `elimination_and_kingmaking` | `elimination_share` (which seat actually killed each opponent), `overkill_damage` (damage sent at a seat already dead on board), and `P(win | 4-player)` vs `P(win | 3-player)` vs `P(win | heads-up)` | `E-SEAT`, `E-EVT` | T2 / E2 | a bot whose heads-up win rate is fine and whose 4-player win rate collapses has a politics problem, not a play problem, **and no single-number Elo can tell you which** | seat order (see §2); rotate and report per seat | N |
| **CMD-5** | `seat_order_effect` | win rate by seat position in the pod, for the same agent against the same opponents | `E-SEAT` | T2 / E2 | this is a property of the format, not of the policy. Measured so that it is subtracted from every pod metric rather than misattributed | none | gate |

---

## 9. Family DFT: drafting, deckbuilding and per-colour preference (the owner named this)

Framing that must be in the protocol. `MTG_bot/strategic_brain/draft_simulator.py` is 113 lines and
is **imported by nothing**; every pick is `random.choice(current_pack)` at `:77`; `build_deck` takes
the **first 23 non-lands in pool order** at `:100` and fills with random basics to 40. Nothing in
the training path drafts. Decks come from `Teacher.select_archetypes` (`ORDER BY RANDOM()` at
`teacher.py:76`, under a permanent SQL ban on every life-gain card at `:74`) into
`DeckGenerator.build_from_sequence`, with weights from a `TeacherModel` whose `train_teacher`
(`teacher.py:132-156`) contains **no `backward()` and no `optimizer.step()`** and which is blended
50/50 with `random.random()` at `teacher.py:67`.

And Commander has no draft. So **for this project "drafting tendencies" is deckbuilding and
colour-preference tendency**, and that surface is 100% unlearned random SQL today. The draft
instruments below stay in the catalogue because Limited is a cheap, well-instrumented training
environment and because the pick head is a natural place to measure confidence; but the per-colour
ask is answered primarily by `COL-1..4` and `DFT-5`.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **DFT-1** | `colour_commitment_curve` | `P(pick in current top-2 colours by pool count)` as a function of pick index 1..45 | `E-DRAFT` model-driven pick function returning `(card_id, full probability vector over the pack)`, plus the pack contents at pick time | T2 / E0 | **the slope is the skill and no constant policy has a slope.** A strong drafter rises from ~0.4 at picks 1-3 to > 0.85 by pick 8 and > 0.95 in packs 2-3. **A random drafter is flat at ~0.4 across all 45 picks.** The best draft metric available without a human reference corpus | none | N |
| **DFT-2** | `signal_reading` | `open_residual(c) = (share of c among cards seen) - (base rate of c in the set)`; `signal_corr = Spearman(final deck colour share, open_residual)`. Companion `switch_turn` = the pick index at which the top-2 colours last changed | `E-DRAFT` plus wheel tracking (which cards came back) | T3 / E0 | **`signal_corr` alone is partly gameable**: a random drafter's colours also follow the packs, because it picks uniformly from what it is shown. Reading signals means committing **early** to the open colour, so the metric is the pair `(signal_corr, switch_turn)`. **Report both or neither** | none | Y alone, N as a pair |
| **DFT-3** | `pick_confidence` | per pick: `entropy(pi over pack)`, `top1_margin = p1 - p2`, and top-1 agreement against the same weights re-run with the pack order shuffled | **the full probability vector** | T2 / E0 | the order-invariance check is a bug detector: a pick that changes with pack order is keying on list position. Today `student.py:131` computes `probs` and `:138` keeps only the scalar `log_prob` of the chosen index, so **no confidence, entropy, PR-AUC, F1 or calibration metric anywhere in this catalogue is recoverable post hoc from a logged action index** | none | N |
| **DFT-4** | `pick_prauc_vs_reference` | with an external pick-order reference, label each pack's cards "top-3 by reference" and compute PR-lift of the model's pick distribution, plus top-1 agreement and Spearman of the full ranking | an external corpus | T3 / needs data | **No such corpus exists in the repo and there is no public per-decision Commander corpus at all.** Candidates: 17lands (Limited only, pick order and game outcome, not per-priority-window decisions), or the owner's own recorded play. **Be honest: either acquire the reference or drop the ask for the draft lens** and satisfy the PR-AUC requirement from `CLS-1` and `CLS-3`, which need no external data. Computing an AUC against a self-generated label would be theatre | reference bias caps the model at reference level; never an objective | N |
| **DFT-5** | `finished_deck_quality` | on the 40- or 100-card result: `JSD(deck curve ‖ declared target curve)`, creature count, interaction count, land count against a declared heuristic, off-colour card count, and `MANA-5` source deficit | decklist, `E-CARD` | T1 pre-flight / E0 | a pure function of the decklist: microseconds, no games. **Run as a gate on every run: if the deck is broken, the games measure nothing.** Today it would immediately report that `build_deck` takes the first 23 non-lands in pool order | the target curve is a declared heuristic, not truth | N |
| **DFT-6** | `draft_to_play_consistency` | share of maindeck cards ever cast across the games played with that deck | a path from `build_deck` into the environment, which does not exist | T3 / E0 | the only metric that closes the loop from picking to playing | game count per deck | N |
| **DFT-7** | `archetype_exposure` | games per declared archetype per window, and its Gini; plus the **measured** k-means archetype assignment and the declared-vs-measured confusion matrix | `E-DECK` | T2 / E0 | an archetype below 1% of games for two consecutive windows is vanishing from the distribution, which is forgetting in the making. The confusion matrix tells you whether the generator builds what it claims | the current sampler is random, so at E0 this measures the sampler, not the teacher | N |
| **DFT-8** | `per_archetype_winrate_vs_anchor` | matrix, one row per archetype, against the **fixed** anchor, tracked over time | `ST-1` | T2 / E0 | a collapsing row while overall Elo rises is catastrophic forgetting of a specific strategy | 400 games per row | N |

---

## 10. Family PZL: puzzles, rebuilt

The existing corpus is 131 files, 17 distinct `setup` blocks, 3 card ids carrying 128 of them, and
`level_1` files carry a `p2_attacking_creatures` key that `_evaluate_scenario` never reads, so the
threat was authored and never instantiated. `benchmarker.py:116` caps a scenario at 5 steps and runs
`deterministic=True`, which forces a single reasoning pass, so **the puzzle suite evaluates a
different model from the one that plays.**

Five construction rules, and rule 3 is the one that makes the failure structurally unrepeatable.

1. **Score is a difference measured in the same episode**: `NormScore` per Rail B, unclipped below.
   `_calculate_proximity` (`benchmarker.py:143-163`) is deleted, not patched.
2. **Binary terminal goal.** No proximity partial credit. Proximity is what leaks the 0.9.
3. **Every puzzle ships a measured baseline certificate**: `null_score`, `random_score` (mean over
   200 uniform-random rollouts), `oracle_score`, `oracle_line`. **A puzzle whose normalised
   `random_score > 0.05` is rejected at build time, and a scenario file without a `null_score` field
   does not load.**
4. **The opponent must punish inaction.** Every puzzle is "you lose on the opponent's next turn
   unless", and the setup must actually instantiate the threat.
5. **At least one trap**: a plausible-but-wrong action whose immediate shaping reward looks good.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **PZL-1** | `nzp_score` | the triple `(solve_rate, trap_take_rate, null_margin = solve_rate - random_solve_rate)` over `P-PZL` | rebuilt corpus | T1 / E0 | a null policy prints `(0, 0, 0)`. **A greedy-shaping policy prints a high trap rate**, which is exactly the diagnosis you want when 13 shaping terms are steering the agent | corpus difficulty drift; frozen and hashed | N |
| **PZL-2** | `pass_budget_sweep` | solve rate as a function of forced reasoning-pass count {1, 2, 4, 8, 16} | a working pass loop | T2 / E0 | never report "as it runs" alone. This is also the cheap numerator of `DESIGN_LATENCY.md` §5.4's >= 25-Elo-per-doubling gate | the gate itself should not be run until `PH-9` shows non-zero cross-pass churn | N |
| **PZL-3** | `irt_theta` | over the solve matrix `S[checkpoint, puzzle]`, fit 2PL `P(solve) = sigmoid(a_p (theta_c - b_p))` by joint MLE. Report `theta_c` **with a standard error**, item discrimination `a_p`, and item information `I_p(theta) = a_p^2 P(1-P)` | the accumulated solve matrix | T1 / E0 | three things a solve rate cannot give: (a) **theta has a standard error**, so "generation 7 beats generation 6" becomes a testable claim; (b) **`a_p ~ 0` puzzles are dead weight and are auto-retired**, which applied to the current 131-file corpus would retire almost all of it on the first fit; (c) adaptive selection of the ~200 most informative items at the current skill, roughly a 4x cost reduction *and* higher resolution. Costs seconds | **IRT assumes unidimensional skill and MTG is not.** Report per-concept theta (combat math, sequencing, stack interaction, mana) and check the residual correlation structure; if strongly multi-factor, split the scale rather than forcing one | N |
| **PZL-4** | `mined_corpus_yield` | mine puzzles from self-play: keep a position iff stakes > 0.10, sharpness > 0.05, a random policy solves it in < 5% of 200 rollouts, and the reference line terminates within 8 actions. Report keep rate and corpus growth | E3 | T3 / E3 | makes the corpus grow with the engine's capabilities and guarantees the null-zero property **by construction rather than by review** | **the oracle defines correct, so the corpus inherits oracle bias and the policy cannot exceed the oracle on it.** Puzzles are for regression detection and skill tracking, never for the ceiling. State this in the corpus header | N |

---

## 11. Family DQ: decision quality

### 11.1 The reference ladder, and an honest correction

Half of this family is parameterised by which reference it is measured against.

| Tier | Reference | Cost per evaluated decision | Available |
|---|---|---|---|
| **O1 shallow** | 1-ply expansion, value head on each child, leaves batched | `|menu|` makes plus one batched forward, ~4 ms | E3 |
| **O2 search** | IS-MCTS, 400-800 sims, 8-16 determinizations | ~0.5-1 s | E3 plus a determinization sampler |
| **O3 committee** | O2 under k = 3 checkpoints from **different training seeds**, Q averaged | ~3 s | E3, milestone |

**There is no valid O0.** A proposed "self-oracle" of the same weights run at more reasoning passes
is *not* a stronger reference on this architecture: the pass loop halts on an argmax over a head
that receives no gradient, so extra passes are the same reference run more times. Before E3 the only
honest references are (a) a **different, stronger checkpoint**, and (b) the policy's own rollouts
(`DQ-2`). Say which, always.

`DESIGN_TRAINING.md` §5 states the gate: at today's `copy.deepcopy(graph)` of 6.0 ms, one O2
evaluation costs about 20 hours. **Every oracle-referenced metric is gated on `E-MU`.**

### 11.2 The metrics

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **DQ-1** | `paired_branch_delta` **[confirmatory]** | to compare policies A and B: play a common prefix under a **neutral third** policy to a sampled decision index t, snapshot, continue twice under identical RNG streams and identical opponents, once with A acting and once with B. `d_i = outcome_A - outcome_B`; estimate with a **paired bootstrap**, broken down by phase, turn bucket and stakes cell | `E-SNAP` snapshot/restore, `E-SEED` with **separated** RNG streams (shuffle / engine / policy) | T2, and at **every checkpoint promotion** / E0 | **the missing measuring stick in its cheapest honest form.** Needs no oracle, no search, no make/unmake. Unpaired win rate needs `n = 2 (z.975 + z.80)^2 p(1-p)/delta^2 = 2 * 7.85 * 0.25 / 0.0009 ~ 4,360 games per arm` for 80% power at a 3-point difference. Paired branch points at a measured 15% disagreement rate have `Var(d) = 0.15/n` against `0.5/n`, so **~3.3x fewer samples and each is a partial game: roughly 5-7x cheaper in wall clock. It is 5x, not 100x.** The larger win is attribution: it says the difference is concentrated in declare-blockers on high-stakes positions, which a win rate structurally cannot | **prefix policy choice.** A prefix generated by A makes the corpus on-distribution for A and off for B. Use a neutral third policy, or split 50/50 and report both. Easy to get wrong silently | N |
| **DQ-2** | `ordering_violation_rate` | sample decision t; `a1 = argmax pi`, `a2` = second. Snapshot, play m paired continuations from each branch under **common random numbers**, differing only in the forced first action. `Delta_t = mean_j[outcome(a1) - outcome(a2)]`; `OVR = P(Delta < 0)` over decisions significant at 95%; `RCD = E[max(0, -Delta)]` | `E-SNAP`, `E-SEED` | T2 (100 decisions as a smoke test at T1) / E0 | estimates `Q^pi(a1) - Q^pi(a2)`, the policy's own Q, so it is unbiased for the thing that matters for improvement: **is the policy's own ordering internally correct.** `OVR = 0` does not mean good, it means **locally converged**, and that is the metric's real value: it is the only cheap signal that distinguishes "keep training" from "this run has plateaued and needs a different opponent, architecture or reward" | m: at m = 8 the per-decision test is very noisy. Aggregate `OVR` is fine at m = 4; per-decision blunder attribution needs m >= 32 | N |
| **DQ-3** | `normalised_value_capture` | over `P-POS`: `NVC = sum_s [Q*(s, a_pi) - Qbar_rand(s)] / sum_s [max_a Q*(s,a) - Qbar_rand(s)]`, where `Qbar_rand` is the mean `Q*` over the legal menu. Report the tier in the name (`NVC@O1`) | E3 oracle | T2 (O1) / T3 (O2) / E3 | random = **0.000 by construction**, oracle = 1.000. `[guess]` < 0.30 at any milestone means the policy is not making decisions | (a) `Qbar_rand` is dominated by near-equal mana taps and drifts toward `V(s)`, inflating NVC: **report over NTD and EDC, never raw.** (b) as the policy improves the corpus goes off-distribution: re-cut and report both versions | N |
| **DQ-4** | `search_regret` | per decision `r_t = max_a Q*(s,a) - Q*(s, a_t) >= 0` in win-probability units. Report `p50, p90, p99, max` and `regret_rate(tau)` for tau in {0.02, 0.05, 0.10} | E3 | T2 (O1) / T3 (O2) / E3 | **the mean is nearly useless and may not be published alone**: regret is a heavy-tailed mixture over a 92%-trivial stream. What you want is p99 and `regret_rate(0.10)`, **the number of game-losing mistakes per game**. Good trajectory: p50 falls to 0 while p99 falls slowly. Bad trajectory: **p50 falls while p99 is flat**, meaning it is getting better at easy decisions and no better at the ones that decide games, which a rising Elo hides | opponent strength changes the supply of high-stakes positions; stratify by `DQ-6` | N |
| **DQ-5** | `regret_concentration` | `RC@1% = (sum of the top 1% largest r_t) / (sum r_t)`, plus regret decomposed by action class, phase, turn bucket, seat and stakes cell | `DQ-4` plus the per-decision tags `tools/latency/decisions.py:182-204` already computes | T2 / E3 | near 1.0 means a handful of catastrophes: go fix those decision types. Near 0.01 means uniformly slightly wrong: a capacity or representation problem. **These require completely different responses and are indistinguishable in Elo.** The class decomposition is where you learn that 60% of lost value is in block assignment | needs `E-ID` namespace separation or the per-class aggregation is scrambled | N |
| **DQ-6** | `decision_difficulty_index` | do **not** collapse to a scalar. A 2-D grid: **stakes** `sigma = max_a Q* - Qbar_rand` in buckets {<0.01, 0.01-0.03, 0.03-0.10, >0.10}; **sharpness** `gamma = Q*(a1*) - Q*(a2*)` in buckets {<0.005, 0.005-0.02, >0.02}. Oracle-free proxies for the always-on tier, calibrated against the grid weekly: support size after dedup, and **search instability** = the number of reference-budget doublings at which the argmax changes | E3 for the grid; proxies at E0 | T1 (proxies) / T2 (grid) / E3 | **every metric in this document is reported per cell and re-aggregated under a declared prior.** Without this, "regret fell 20%" is uninterpretable: the policy improved, or games got shorter, or the opponent got weaker and stopped producing hard positions, or the rebuild changed the position distribution. **Difficulty stratification is what makes any longitudinal claim legal** | proxy-to-grid calibration must be re-fitted at every epoch boundary | gate |
| **DQ-7** | `blunder_rate` | on segments where only the agent's own action intervened: `delta_t = V(s_{t+1}) - V(s_t)`; `BR(tau) = |{delta < -tau}| / |NTD|` | per-decision value (produced at `model.py:180`, used at `train.py:296`, **never logged**), plus `E-EVT` to say whether a chance or opponent event intervened | T1 as a **screen only** / E0 | chess centipawn-loss with the engine's own critic. **A null policy scores near-perfectly**: passing rarely moves the value by more than epsilon, so BR ~ 0 for a policy that loses slowly. **The most seductive trap in this family and it is flagged in the report header every time it prints.** Legitimate only after its correlation with `DQ-4` has been measured: publish `Spearman(BR-flagged, top-decile regret)` at every weekly review and stop using the screen below 0.4 | critic error: a critic that is optimistic right before its own bad moves hides exactly the blunders you want | **Y** |
| **DQ-8** | `sequencing_regret` | per turn, take the actions actually committed, enumerate the **adjacent-transposition neighbourhood** (|A|-1 swaps, not |A|!), replay each from the turn's start under identical RNG, evaluate the end states. Report mean, p95, and `P(SEQ > 0)` | `E-SNAP`, `E-MU`, `E-SEED` | T3, or T2 on a 200-turn subsample / E3 | isolates a large and distinct skill: **right cards, wrong order.** A policy can have low `DQ-4` and high `DQ-8`, which is a specific representation problem (the plan decoder is not conditioning on the realised prefix). `[guess]` `P(SEQ>0) > 0.3` is an alarm | **a lower bound by construction** (adjacent transpositions only) and labelled as one | N |
| **DQ-9** | `cross_pass_dynamics` | per decision across passes p = 1..P: top-1 churn `1[argmax pi_p != argmax pi_{p-1}]`, `KL(pi_p ‖ pi_{p-1})`, `|V_p - V_{p-1}|`, top-1 margin | `E-DEC` per-pass distributions | T1 / E0 | churn and KL should decay in p and be **larger on high-stakes decisions**. **Flat-zero churn means the passes are functionally identical**, which is provably the case today. **The go/no-go precondition for the entire adaptive-compute programme**; `DESIGN_LATENCY.md` §5.4's Elo-per-doubling gate should not be run until this is non-zero. Alarm on the exploit named in §3.6: mean passes rising > 20% while the Elo CI contains zero means the model learned to make its plan artificially unstable to justify thinking | one softmax and one dot product per pass, free next to a ~40 ms pass | N |
| **DQ-10** | `allocation_efficiency` | `AE = Spearman(passes_taken, stakes)`. Plus the **anytime profile**: regret as a function of forced pass budget {1,2,4,8,16} per stakes cell | `E-DEC`, `DQ-6` | T1 (AE) / T2 (profile) / E0 | does it think longer where the stakes are higher. `AE <= 0` means the halting head allocates compute at random and `DESIGN_LATENCY.md` §3 has failed. **~0 by construction today.** `[guess]` gate: `AE >= 0.2` with a CI excluding zero | needs stakes, which before E3 is the declared proxy | N |
| **DQ-11** | `class_coverage_gap` | per action class c: `Avail_c = P(a class-c action exists)` over NTD, computed on the **pre-curation** menu; `Sel_c = P(chosen class = c | c available)`; `Gap_c = logit(Sel_c) - logit(Sel*_c)` against the reference. For classes with zero selections in N decisions, publish the **rule-of-three** bound `Sel_c < 3/N` rather than a bare zero. Plus per-class recall against opportunity | `E-SLATE` pre-curation menu with class tags | T1, **front page** / E0 | **the cheapest high-value instrument in the catalogue and the one that would have caught the failure this project actually had.** Two counters per decision, no oracle, no rollouts. Random-policy baseline on the current engine: `DeclareBlocker 0.1%`, `CastSpell 0.6%`, `DeclareAttacker 0.4%`. `[guess]` alarm: any class with `Avail_c > 5%` and `Gap_c < -2.0` is a red row. A null policy has `Gap_c ~ -inf` on every non-pass class. **This is also the metric against which the four scaffolds fighting that symptom (proactivity bias, forced-play probability, stall detector, repeat cap) can finally be evaluated and deleted** | class granularity: `CAST` bundles a removal spell and a durdle. Also report at (class x MV bucket) and (class x card type) once `E-ID` lands. **`Avail_c` must be pre-curation or the metric measures the filter, not the policy** | N |
| **DQ-12** | `missed_gain` | `mg_t = max_a Q*(s,a) - Q*(s, a_pass)` at **every** decision where passing is legal, regardless of what the policy did. Report `sum mg` per game and the **capture ratio** `sum [Q*(a_t) - Q*(a_pass)] / sum mg` | E3, one extra oracle query per decision | T2 / E3 | **the null-policy antidote and the mandatory partner of `DQ-7`.** A do-nothing policy scores exactly 0.000 on the capture ratio by construction. `DQ-7` rewards inaction, `DQ-12` punishes it, and the pair is what makes the family non-gameable. High `sum mg` with low capture is this repository's documented symptom and **is the metric the four proactivity scaffolds should have been measured against** | oracle bias | N |
| **DQ-13** | `invariance_probes` | (a) **permutation**: re-score the same decision with the candidate list permuted under a fixed RNG; report `TV(pi, pi o sigma)` and self-agreement. (b) **duplicate**: for semantically identical candidates (`PlayLand(Forest#1)` vs `#2`), report `max |pi(a_i) - pi(a_j)|` over duplicate groups | one extra forward on a 1% sample | T1 / E0 | both should be ~0. **Declared gate: `TV > 0.01` means the policy is keying on list position and every ranking metric above it is measuring an artefact.** Live risk today: the action descriptor the network scores carries no card identity, so two different 2/2s are byte-identical | none | gate |

---

## 12. Family VAR: variability in play (the owner named this)

Three separable quantities, and conflating them will mislead. **A uniform-random policy maximises
all three naive forms**, so diversity is meaningful only conditioned on strength and is reported as
the 2-D point `(Elo, diversity)`, never as a scalar to be maximised.

The design principle: **healthy diversity is variation that is conditioned on state and concentrated
in low-stakes decisions. Noise is variation that is unconditional and uniform across stakes.**

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **VAR-1** | `normalised_entropy` | `H/log|A|` over **non-forced** (`|A| >= 2`) and **non-exploration-override** decisions, stratified by support size, per action class | `E-DEC` full probability vector, **pre-bias logits**, and `how_chosen` | T1 / E0 | `[guess]` 0.3-0.7 mid-training; < 0.15 collapse; ~1.0 untrained. **A uniform policy attains 1.0, the maximum: high entropy is not good.** What is good is a trajectory that starts near 1, declines, and stops well above 0. Raw mean entropy on this engine measures the **action space**, not the policy: median legal-action count is 1 over 2,400 decisions and 21.2% of priority windows have exactly one legal move. Entropy should be **low** for mana taps and forced passes and **high** for close combat decisions; uniformly collapsed is mode collapse, uniformly maximal means no discrimination | post-bias entropy overstates decisiveness by up to 10 nats on pass actions because `student.py:129` mutates the logits in place. Also, exploration starts at 0.7 with a 0.15 floor and nothing records which actions were overrides | **Y** |
| **VAR-2** | `context_discrimination` | bucket every non-forced decision by `c = (phase, step, turn bucket, life bucket, board-diff bucket, menu signature)`; let `a` be the chosen action class. Miller-Madow-corrected `I(A;C) = sum p(a,c) log2[p(a,c)/(p(a)p(c))] - (|A|-1)(|C|-1)/(2N ln2)`. Permute `c` 100x, take `I_shuffled_p95`. **`I_excess = I(A;C) - I_shuffled_p95`, in bits**, computed within menu-signature strata and stratum-weighted | `E-DEC`, `E-SLATE` | T1 / E0 | **the anti-null companion for every entropy and diversity number.** A uniform-random policy has `I_excess ~ 0` by construction (it cannot condition on anything) and an always-pass policy has `I_excess ~ 0` (no variation to explain). `[guess]` >= 0.3 bits by mid-run, rising monotonically. **Flat near 0 while entropy is high is noise wearing diversity's clothes** | menu composition correlates with context (blocks are legal only in combat); the within-signature stratification is the control | N |
| **VAR-3** | `entropy_stakes_correlation` | `rho_HS = Spearman(H/log|A|, -ValueSpread)` where `ValueSpread = max_a Q(s,a) - sum_a pi(a) Q(s,a)` | `E-DEC`, value spread (already a specified halting-head input, so free) | T2 / E0 | a good policy is confident when the decision matters and indifferent when it does not, so `rho_HS` should be clearly positive. **A uniform policy has `rho_HS = 0` by construction**, and so does one whose apparent confidence is only a function of menu size | if no Q exists, substitute the value spread across the plan's top-k and **say so in the row** | N |
| **VAR-4** | `matched_state_entropy` | group decisions by state fingerprint `(menu signature, phase, step, turn bucket, life bucket, board-diff bucket)`; for groups with n >= 20 compute normalised entropy of the chosen-index distribution. Report the n-weighted mean and p10/p50/p90 across groups | `E-DEC` | T1 / E0 | read as a 2x2 against `VAR-2`, and the cell is a one-word verdict in the report header: high H + `I_excess` ~ 0 = **NOISE** (exploration-random looks exactly like this); high H + high `I_excess` = **HEALTHY-STOCHASTIC**; low H + `I_excess` ~ 0 = **MODE COLLAPSE**, the worst cell; low H + high `I_excess` = **DETERMINISTIC EXPERT**, resolved by `VAR-6` | fingerprint granularity | Y alone |
| **VAR-5** | `line_jaccard` | fix a game seed (deck, opening hand, opponent), re-roll the **policy sampling seed** k = 16 times, take the multiset `L = {(turn, oracle_id, action_class)}` over the first 6 turns, report the mean pairwise `|L_a ∩ L_b| / |L_a ∪ L_b|` over 120 pairs, averaged over >= 50 fixtures | `E-SEED`, `E-SNAP` or deterministic re-init from a fixture spec | T2 / E0 | memorised single line ~ 1.0; pure noise ~ 0.1, **measured against a random control on the same fixtures and published beside it**; `[guess]` healthy 0.40-0.70, to be calibrated in the first window | menu determinism: if only one line is legal, Jaccard is 1.0 for trivial reasons. Restrict to fixtures offering >= 3 distinct intentional lines in turns 1-6 | Y alone |
| **VAR-6** | `importance_stratified_agreement_gap` | on `VAR-5`'s re-rolled replays, tag each decision with stakes `sigma = |V_{t+1} - V_t|` (or `|advantage|`). Compute cross-replay agreement (modal-action share at matched decision points) separately for the **top decile** and **bottom decile** of sigma. `gap = agreement(top) - agreement(bottom)` | `VAR-5` plus per-decision value | T2 / E0 | **the sharpest answer to "variability in play" in this catalogue.** A good player is consistent where it matters and varied where it does not. **A random policy scores exactly 0 by construction** (it has no notion of stakes, so it cannot vary its consistency with them); a collapsed policy scores ~0 with both terms at 1.0; a noisy policy scores ~0 with both terms low. `[guess]` healthy >= +0.25 and rising | **a broken value function makes sigma meaningless.** Gated on `PH-4 EV_outcome > 0.2`; below that the row prints `NOT EVIDENCE`. Use `|advantage|` as a fallback sigma | N |
| **VAR-7** | `strategy_churn` | Jensen-Shannon divergence between `p(action_class, phase, turn bucket)` in window w and window w-k, in bits | `E-DEC` | T1 sparkline / E0 | ~0 for many windows means a frozen policy: pair with `VAR-4` to tell "converged" from "collapsed". Large spikes plus `ST-3 > 0.15` is the rock-paper-scissors signature | window length | Y |
| **VAR-8** | `repertoire` | (a) `distinct_cast_oracle_ids` per 1000 games; (b) `cast_gini` over cards available in the decks played; (c) **`cast_rate_given_castable`** per card = `times cast / times (in hand AND priority held AND cost payable)`, with the **ignored set** = cards with denominator >= 50 and rate <= 0.02; (d) `var_across_cards(cast_rate_given_castable)` | `E-MANA` for "cost payable", `E-ID` | T2 / E0 | (c) and (d) are the valuable ones and the only ones random loses on: a random policy has roughly `1/menu_size` uniformly across cards, so its **variance across cards is ~0**. A discriminating policy has high variance because it likes some cards. The ignored-set table is a genuinely useful deckbuilding artefact | "cost payable" requires real mana accounting, which does not exist in any form today: `state_converter.py:155-162` computes potential mana as the **count of untapped lands assuming each makes exactly one** | (a)(b) Y, (c)(d) N |
| **VAR-9** | `opponent_conditional_adaptation` | `E_cell[ KL( P(class | opponent archetype A, cell) ‖ P(class | archetype B, cell) ) ]`, matched on difficulty cell and phase | a league with >= 2 archetypes | T2 / E0 | ~0 means the agent plays its own game regardless of the table, a real weakness in Commander where threat assessment is the format. Rising `VAR-9` with rising strength is the good trajectory | **undefined with a single frozen self-copy opponent**, which is one more argument for the league | N |
| **VAR-10** | `opponent_identity_probe` | logistic probe on the belief vector predicting opponent identity from the state at **turn <= 2**, before informative play. Report AUC against chance `1/|pool|` | `E-HEAD` access to `b_t`, a league | T3 / E0 | meaningfully above chance at turn 2 means the model is encoding **who** it is playing rather than **what** is on the board, and the only use of that is exploitation of a nonexistent metagame. `[guess]` alarm AUC > 0.70 on a 2-opponent pool | deck identity leaks opponent identity legitimately; control by pairing the same deck across opponents | N |

---

## 13. Family GEN: generalisation (E4)

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **GEN-1** | `residual_to_composed_ratio` | `rho = E_c[ ‖gate_c * E_atomic[oracle_id_c]‖ / ‖v_composed(tree_c)‖ ]`. Report mean, median, p95 **and the per-card top-20 list** | the compiler, `E-ID` | T1 / E4 | per `DESIGN_CARD_POOL.md`: if rho climbs, the primitive vocabulary is too weak and the model is memorising. **Which cards it memorises is far more informative than the mean**, and the answer is usually the cards whose compiled trees are wrong, which makes rho double as compiler-coverage instrumentation | **two leaks.** (1) There is a **second, undeclared atomic embedding**: `CardEmbedder.atomic_embedding` at `model.py:25` is a per-id lookup fused into every board token at `:29-32`, not gated, not zero-initialised, not decayed. A rho over only the declared residual while that table exists measures nothing; fold it in or include its norm in the numerator and say which. Compounding it, 60 of 86 `game_vocabulary` ids collide with the 1-397 card-id range, so the row for "Creature" **is** the row for card 1. (2) **Weight decay drives rho to 0 for free**, so rho is never reported alone, always paired with `GEN-2` | Y alone |
| **GEN-2** | `held_out_card_strength` | hold card set C_held entirely out of training decks; build eval decks containing C_held; **force `gate = 0`** so the model plays from composition alone; measure Elo vs the anchor ladder. Report three gaps: `G1 = Elo(seen, residual on) - Elo(held-out, residual off)`; `G2 = Elo(held-out, off) - Elo(held-out, on)` (should be ~0, otherwise the gate leaks); **`G3 = Elo(held-out, off) - Elo(GreedyAgent on the same decks)`** | the compiler, legality flags, a controlled pool, `ST-1` | T3 / E4 | **`G3` is mandatory.** A held-out score published without the score of an agent that has never seen *any* card, on the same decks, is not a demonstration of auto-extension. Also report **per-primitive coverage**: for each verb and filter predicate in the grammar, occurrences in C_held and the win-rate delta. **A held-out set that exercises no unseen composition is not a test, it is a reshuffle** | >= 400 games per pairing; stratify C_held by `colorIdentity` x primary type x `manaValue` or the holdout is not representative | N |
| **GEN-3** | `pool_generalisation_gap` | reserve 15% of cards, stratified as above, never used in any training deck; build decks from holdout-only and evaluate against the **same fixed anchor**; `gap = WR_seen - WR_holdout` at equal deck power | `E-CARD` full metadata | T3 / E4 | `[guess]` gap > 8 points at equal deck power, or a widening gap across milestones, is memorisation. 397 cards from one set is a small enough pool that memorising 397 embeddings is the path of least resistance, and memorised embeddings **are** hardcoding, just gradient-descended | "equal deck power" is hard to establish; use `DFT-5` and `MANA-5` as the matching criteria and report them | N |

---

## 14. Family SYS: systems, throughput and decision count (the owner named decision count)

`tools/latency/decisions.py` is a working, torch-free instrument that already produces this family
and should be **subsumed, not replaced**. `summarise_games` (`decisions.py:171-204`) already emits
`decisions_per_game`, `decisions_per_seat_per_game`, `turns_per_game`, `decisions_per_turn`,
`forced_fraction`, `by_chosen_class`, `by_chosen_class_pct`, `by_step`, `by_phase`, each as
`{n, min, p50, p90, p99, max, mean}`. Measured output already on disk
(`reports/decision_counts_devbox.json`, 24 games, random policy, current engine):
`decisions_per_game` p50 **2173** / p90 2533 / p99 **2802**; `decisions_per_seat_per_game` p50 1077
/ p99 1603; `turns_per_game` p50 181; `decisions_per_turn` p50 12.29; `forced_fraction` 0.3424;
`engine_ms_per_decision` 8.771.

Three changes make it serve the protocol: run it with the **model** in the loop instead of
`random.choice`, key it by **seat** rather than player index, and emit **per-decision rows** rather
than only aggregates. Its own docstring is honest that every number it produces is a loose floor on
the current engine.

| ID | Metric | Definition | Data required | Tier / epoch | How to read | Confounds | Null |
|---|---|---|---|---|---|---|---|
| **SYS-1** | `decisions_per_game` **(D9)** | p50 / p90 / p99 / max of decisions per game and **per seat per game**, broken down by phase, step and chosen action class, plus `decisions_per_turn` and `forced_fraction` | `E-DEC`, `E-SEAT` | T1 / E0 | **descriptive, not quality**: a random policy has a value and a do-nothing policy has a large one. `DECISIONS.md` D9 makes it a monitored tier-1 metric and a **regression gate**: if measured p99 climbs past the clock budget, that is the alarm. It is also the denominator of `ST-2` and therefore of the whole protocol | **epoch-fragile.** Collapsing pairwise block declarations into one structured decision and auto-resolving forced fields will move this by a large factor. Rail H applies with full force | **Y** |
| **SYS-2** | `decision_latency` | end-to-end per decision: p50 / p90 / p99 / p99.9 / max, stratified by support size and phase; plus **match-budget occupancy** (sum latency over a game / per-seat allowance, p50 and p95 across games), **match-forfeit probability** over >= 10,000 resampled matches, **value-weighted miss rate**, and **slow-play exposure** (decisions over 5 s, must be 0) | **a per-decision wall-clock timer inside the training loop.** Nothing times a decision in training today; the only timing lives offline in `tools/latency/bench.py` | T1 (p50/p99, occupancy) / T2 (forfeit probability) / E0 | the full table is `DESIGN_LATENCY.md` §5.2 and is not restated here. `round_spread_pct > 15%` voids the row | thermal and clock drift; interleave A/B arms in one process | gate |
| **SYS-3** | `throughput` | games per day, decisions per second, GPU utilisation, `effective_gb_per_s` and its ratio to theoretical, measured `kernel_launches`, sync count, `tail_ratio_p99_over_p50` | `bench.py` machinery | T1 / E0 | a throughput regression is invisible in a games-based learning curve, which is why `ST-2` reports decisions first | warm-up cost and graph hits/misses are reported separately, never folded into steady state | gate |
| **SYS-4** | `storage_and_retention` | bytes/day written by the metric pipeline, store size, oldest retained run, downsample state | the store | T1 / E0 | **budget: two-tier logging.** Always-on compact row (~40 B: entropy, top-1 prob, top-2 margin, chosen class, value, passes, ms, forced flag, support size) at 40M decisions/day is **~1.6 GB/day**; a 2% stratified full-vector tier (~500 B) adds **~0.4 GB/day**; replays at ~450 KB gz per game add more. **Retention: full replays 30 days, then keyframes only; per-decision rows 90 days, then daily aggregates; aggregates forever.** The repo already carries 449 MB of unusable unstructured JSON in `logs/`, of which 228 MB is `StateRecorder` output; that is the small version of this failure | **the sampled tier biases every downstream aggregate unless reweighted.** All sampled-tier statistics use **Horvitz-Thompson weights `1/p(sample | stratum)`**, or every metric skews toward hard decisions | gate |
| **SYS-5** | `measurement_budget_consumed` | GPU-hours and game-equivalents spent on measurement, per tier, against the 5% cap | the harness | T1, printed in every review / E0 | **Indicative bill, to be replaced by measurement in the first calibration window.** T1: one offline streaming pass over the run's replays plus arithmetic PPO already does, < 1%. T2: 400-game gauntlet + ~800 fixture games (`VAR-5`) + anchor cross-table at 200 games per pair + `DQ-2` at ~8 game-equivalents per sampled decision x 500 decisions ~ 4,000 game-equivalents; at a projected 11k-29k games/day this is hours, not days, and it runs on a separate checkpoint so it does not compete with training. T3: `ST-7` is a whole (2%-scale) training run, `GEN-2` is >= 400 games per pairing, `DQ-4@O2` is |P| x ~0.7 s. **These are the items that blow the cap if left uncosted** | none | gate |
| **SYS-6** | `seat_effect` | win rate by seat position in a pod for a fixed agent against fixed opponents | `E-SEAT` | T2 / E2 | a property of the format. Measured so that it is subtracted rather than misattributed to the policy | needs full rotation, which the gauntlet mandates | gate |

---

## 15. Engine requirements

**This is the section that must land in the rebuild.** Each requirement is cheap to include now and
expensive or impossible to retrofit. Ordered by how many metrics die without it.

| Req | What the engine and replay stream must emit | Metrics that die without it | Evidence it is absent |
|---|---|---|---|
| **E-SEED** | every RNG seeded; **streams separated** (shuffle / engine / policy / exploration); deterministic trigger ordering; integer entity ids | `VAL-2`, `VAL-3`, `DQ-1`, `DQ-2`, `DQ-8`, `VAR-5`, `VAR-6`, and **every A/B comparison in the protocol** | no `random.seed`, `np.random.seed` or `torch.manual_seed` anywhere in the training path (four hits, all in `tools/latency/`); entity ids are `uuid4()`; zone-change triggers iterate `set` differences of UUIDs, so trigger order is hash-dependent even under a fixed seed |
| **E-DEC** | a first-class decision record: `run_id, checkpoint_id, generation, game_id, seat, turn, phase, step, decision_id`, priority holder, the full candidate menu as tokenized actions, **what was filtered before the model saw it and why**, the **full probability vector**, **raw pre-transform logits**, per-field distributions for structured actions, value, entropy, chosen index, **how chosen** (policy sample / argmax / exploration override), passes taken and per-pass distributions, **wall-clock ms**, forced flag, support size, **menu hash**, `policy_version` | `CLS-*`, `CAL-6`, `VAR-1..4`, `VAR-7`, `DQ-9..13`, `PH-3`, `DFT-3`, and every confidence, entropy, PR-AUC, F1 and calibration metric | `student.py:131` computes `probs`; `student.py:138` keeps only the scalar `log_prob` of the chosen index. `student.py:129` destroys the pre-bias logits **in place**. `rethink_prob` is not in the returned tuple at all. **Unrecoverable post hoc from a logged action index.** |
| **E-EVT** | the engine's own typed event stream with a **causing-event index** and the emitting `file:line`; typed `engine_error` replacing the swallow-and-log; `_move_card_to_zone` instrumented; untap, draw, combat damage, cleanup discard, trigger resolution and creature death all emitted | all of `EC-*`, `CMB-3`, `CMB-5`, `CARD-2`, `DQ-7`, `INT-6` | `execute_move` builds a `List[str]` across nine branches and `environment.py:153` calls it without capturing the return; `resolve_stack`, `progress_phase_and_step` and `check_state_based_actions` mutate state and emit nothing |
| **E-RWD** | reward emitted **per term, never pre-summed**; a terminal transition appended for **every seat**, including when the opponent's move ends the game; the terminal outcome **and its reason** propagated back to every decision of that game | `RWD-1..4`, `PH-4`, `CAL-1..4`, `CLS-3` label harvest | 13 terms summed at `environment.py:211`; `train.py:302` accumulates only in the student branch and `:317` discards the frozen branch's reward; `train.py:359-377` computes `game_result` and never writes it into the buffer |
| **E-SEAT** | per-seat keying throughout. Never `p1_*` / `p2_*` | everything, in the priority format | `environment.py:117-118,156-162,177,213-228` hardcodes two players and fixed `p1_*`/`p2_*` info keys |
| **E-CARD** | `colorIdentity`, `manaValue`, `types`, `subtypes`, `keywords`, `producedMana`, `loyalty` as real columns; **`cmc` actually written onto the card entity** | `MANA-2..8`, `COL-1..4`, `CMB-5`, `CARD-4`, `DFT-*`, `GEN-3` | 43 MTGJSON fields discarded at ingest; the `(setCode, number)` join back is **397/397 clean**, so this is one offline script. Loyalty is misfiled into `toughness` on all 29 planeswalkers (`power='0'`), so every P/T metric counts them as 0/N creatures. `state_converter.py:120` reads `props.get('cmc')` which `card_data_loader._process_db_row` never writes: **feature slot 2 of every board token in every observation is a constant 0.0, so the model cannot see mana value at all** |
| **E-MANA** | mana accounting events: produced by source and by colour, **spent per spell**, floated at end of step, lands left untapped at end of turn, colour-screw events, life and alternative costs paid | `MANA-2`, `MANA-4`, `MANA-7`, `COL-1`, `TMP-3`, `CARD-3`, `CARD-5`, `VAR-8`, `INT-2` | none of it exists. `environment.py:208` folds a mana delta straight into a reward; `state_converter.py:155-162` counts untapped lands assuming one mana each. `MTG_bot/docs/BENCHMARKS.md:16` promises `avg_mana_efficiency = mana_spent / mana_available` and **neither numerator nor denominator exists anywhere** |
| **E-ID** | `scryfallOracleId` as the stable card key; **card-id and vocabulary-id namespaces separated**; a card-DB content hash stamped in every run header | `EC-6`, `VAR-8`, `DFT-7`, `GEN-1..3`, every per-card and per-colour series | `card_id` is an autoincrement rowid dropped and rebuilt on re-ingest; `Entity.type_id` holds a card id for cards and a `game_vocabulary.id` for zones and players, and **60 of 86 vocabulary ids fall inside the 1-397 card range** (id 1 = "Creature", id 2 = "Play Land Action", id 5 = "Pass Turn Action"). `scryfallOracleId` is present for all 397 cards and all 20 tokens in `M21.json` and is discarded |
| **E-DECK** | decklists persisted per seat as data, in the replay header: the 99 plus the declared commander, plus the archetype recipe id | `MANA-3`, `MANA-5`, `COL-1..4`, `CARD-4`, `CMD-1`, `DFT-5..8` | **there is no `deck_cards` join table**; the DB has `cards`, `game_vocabulary`, `users`, `decks` and nowhere to put a list. And `game_initializer.py:81-88` pops `working_deck[0]` as the commander **before** shuffling at `:90`, over a list `deck_generator.py:196` already shuffled, so **the commander is a uniformly random card, frequently a basic land** |
| **E-SLATE** | per-decision emission of the **pre-curation** menu, per-field masks, support sizes, forced flags, and dependency classes | `DQ-11` denominator, `CLS-5`, `RWD-5`, Rail C's NTD | `train.py:166-198` curates and records only a positional map at `:200-205` |
| **E-ACT** | structured `ATTACK_SET` naming a defender, and `BLOCK_ASSIGN` as one object rather than N pairwise clicks | `CMB-1`, `CMB-2`, `CMB-6`, `CMD-3`, and `SYS-1`'s comparability | the engine emits one `DeclareBlockerAction` per (blocker, attacker) pair; `DeclareAttackerAction` has `player_id, card_id` only, so there is no "whom do you attack", which in a pod **is** the politics signal |
| **E-PRIO** | real priority for non-active players, and a stack the model can act on | all of §8.6, `INT-1..6` | the defending player is given a decision only at Declare Blockers; instants are offered only inside the active player's own main-phase branch. The stack lives on `Engine`, not in the graph, so every current snapshot is structurally incomplete |
| **E-MULL** | `MULLIGAN_TAKE` / `MULLIGAN_KEEP:CARD_TO_BOTTOM` as real decisions | `MUL-1..4` | `grep "def mulligan"` returns nothing while `main.py:262` calls `engine.mulligan(player_id)` |
| **E-CMD** | commander tax, recast, commander damage, poison, command zone contents in the keyframe | `CMD-1..4` | `grep -i "commander_tax\|commander_damage\|poison"` over `MTG_bot/**.py` returns **zero hits** |
| **E-SNAP** | self-contained position serialise / restore **including the stack** | `DQ-1`, `DQ-2`, `VAR-5`, `VAR-6`, `PZL-4`, `DQ-6` | the stack is on `Engine`, not the graph |
| **E-MU** | make / unmake with an undo journal at 10-50 us | `DQ-3..6`, `DQ-8`, `DQ-12`, `CLS-2`, `CMB-7`, `PZL-4`, the whole oracle ladder | the only copy mechanism is `copy.deepcopy(graph)` at 6.0 ms; `DESIGN_TRAINING.md` §5 names make/unmake as the blocker and puts one O2 evaluation at ~20 hours |
| **E-LEAGUE** | `RandomAgent`, `GreedyAgent`, `RuleBasedAgent`, a checkpoint league, and an Elo system | `ST-1..7`, `CAL-2` (needs a fixed-strength opponent), `CAL-5`, `VAR-9`, `VAR-10`, `GEN-2` | `MTG_bot/docs/TESTING_STRATEGY.md:15-18` promises the first three plus Elo; grep finds **zero** of them. `docs/BACKLOG.md` names the self-play league as the single highest-value backlog item |
| **E-HEAD** | **model work, not instrumentation, and pre-registered as a change:** a separate categorical win-probability head over `{seat wins} + {draw}` with stop-gradient into the trunk, and a supervised decoder on the belief vector | `CAL-1..5`, `CLS-3`, `VAR-10` | the current value head regresses a shaped, unbounded return; the belief vector has **no supervision anywhere** and is unpacked at `train.py:221` and never referenced again |
| **E-STORE** | a local, append-only metric store; a run manifest; `metrics/registry.yaml`; the review directory. Every row stamped `run_id, git_sha, card_db_content_hash, config_hash, seed, generation, checkpoint_id, metric_schema_version, environment_contract_epoch` | **all of it** | `TrainingLogger.save_report()` is `pass`; `log_metrics` returns immediately without W&B; `logs/training_stats/` does not exist; `TrainingLogger.card_stats` and `episode_history` are declared and written by nothing. **No metric has ever been written to disk from this checkout** |

---

## 16. The day-one subset

At E0, with `E-SEED`, `E-DEC`, `E-EVT`, `E-RWD`, `E-SEAT`, `E-CARD`, `E-MANA`, `E-ID`, `E-DECK`,
`E-SLATE`, `E-STORE` and `E-LEAGUE` in place and nothing else, the following is live on the first
training run. Everything else prints `n/a (epoch)`.

**Gates:** `EC-1, EC-3, EC-5, EC-6, EC-7, EC-8, EC-9`, `VAL-1, VAL-2, VAL-5`, Rail L invariants.
**Health:** `PH-1, PH-3, PH-4, PH-5, PH-6, PH-7`, `RWD-1..5`.
**Strength:** `ST-1, ST-2, ST-3, ST-4, ST-5`.
**Calibration:** `CLS-1, CLS-4, CLS-5, CLS-6` (and `CAL-*` only if `E-HEAD` was pre-registered).
**Tendencies:** `MANA-1..8`, `COL-1..3`, `CMB-1..6`, `TMP-1..4`, `CARD-1..5`.
**Deckbuilding:** `DFT-5, DFT-7, DFT-8`, and `DFT-1, DFT-3` if the draft head is wired.
**Variability:** `VAR-1, VAR-2, VAR-4, VAR-7, VAR-8`.
**Decision quality:** `DQ-11` (front page), `DQ-9, DQ-10, DQ-13`, `DQ-7` as a flagged screen,
`DQ-1` and `DQ-2` once `E-SNAP` lands.
**Systems:** `SYS-1..5`.
**Puzzles:** `PZL-1, PZL-3` on a rebuilt corpus.

That is roughly two thirds of the catalogue, and it includes all six confirmatory metrics except
`CMB-1`'s Commander-specific pivots.

---

## 17. Null-favourable register

The standing list, rendered into every report. **The next person who adds a metric must check it
against this register before it ships.** That is the register's job.

| Metric | Null (always pass) | Uniform random | Mandatory pairing |
|---|---|---|---|
| `MANA-7` wasted mana | perfect (never taps, never floats) | poor | gate on `produced >= 3 * turns`, publish with `MANA-2` |
| `CARD-1` hand component | maximal (never casts) | poor | publish the two components separately |
| `CMB-6` attack participation | 0 | - | 2-D scatter with `CMB-4`; the conditional difference is the metric |
| `TMP-4` game length | maximal | long | publish `EC-5` beside it; never aggregate over non-wins |
| `VAR-1` raw entropy | 0 | **maximal** | normalise by `log|A|`, restrict to `|A| >= 2`, pair with `VAR-2` and `VAR-3` |
| `VAR-4`, `VAR-5`, `VAR-7` diversity | 0 | **maximal** | report as `(Elo, diversity)`; pair with `VAR-2` or `VAR-6` |
| `DQ-7` blunder rate | **excellent (~0)** | poor | never alone; always with `DQ-12` missed gain |
| `CAL-1` plain Brier / `CAL-3` ECE | good (a constant predictor is calibrated) | poor | **always print `CAL-2` resolution** |
| raw PR-AUC | - | equals prevalence | report `PR_lift`, which is 0 for random |
| `CLS-3` belief AP on the full pool | - | 2.8e-4 base rate flatters everything | report S3 only, with `AP_null`, lift, and the board-masked ablation |
| top-1 agreement, unrestricted | high (agrees on forced and 55%-pass decisions) | low | restrict to NTD/EDC, report per class |
| `PH-3` clip fraction / KL low | frozen policy: `r = 1`, both 0 | - | pair with `PH-1` and `ST-2`; low is only good if something is changing |
| loss going down | value head collapsing to a constant does it | - | split policy and value loss; gate on `PH-4 EV_outcome` |
| `SYS-1` decisions per game | large | has a value | descriptive, never quality |
| `DFT-2` signal correlation alone | - | follows the packs by construction | report as the pair with `switch_turn` |
| `GEN-1` rho falling | weight decay achieves it for free | - | pair with `GEN-2`; close the second-embedding leak first |
| `ST-8` win rate vs self | ~50% | ~50% | **deleted** |
| `thinking/*_avg_passes` | measures an untrained argmax hitting class 9 | - | **deleted** until `DQ-9` shows non-zero churn |
| existing puzzle scores | **0.900 / 1.000** | ~0.9 | **deleted**; `PZL-1` rules 1-5 replace them |

Drafter rows, added 2026-09-10 with [`DESIGN_DRAFTER.md`](DESIGN_DRAFTER.md) §7:

| Metric | Null (always pass) | Uniform random | Mandatory pairing |
|---|---|---|---|
| `n_hat` measured nicheness | - | **maximal**, a random legal pile is maximally unusual | never alone. Publish the triple with `DFT-12` intent recoverability and `DFT-10` the price curve. Random scores (max, ~0, ~0) |
| `DFT-11` output variety | 0 | **maximal** | condition on every sample clearing the same quality quantile. A random drafter then produces zero admissible samples, so the metric is 0 or undefined rather than maximal |
| `conflation_alarm` | 0 | 0 | a null scores 0 too, so it is only meaningful beside a positive knob-response diagonal |
| archive cell coverage | 0 | **maximal** | null-zero per cell against best-of-m random decks landing in that same cell. For a random drafter the elite is the null, so the score is ~0 while coverage is maximal |

**The rule that generalises, and the one to apply to any metric not on this list:** *any metric
whose numerator can be satisfied by not acting must be published paired with a metric whose
numerator can only be satisfied by acting well.* And more generally, when you are about to measure a
rate, ask what the same rate looks like conditioned on the thing that should change it, and measure
the difference instead.

---

## 18. Honest limitations

Stated plainly, because a protocol that hides its weak points is a protocol that will be trusted
where it should not be.

1. **We do not know how to measure "plays like a human" and we are not going to try.** No public
   per-decision Commander corpus exists. The only path to a human reference is a blinded elicitation
   panel over ~200 stratified high-stakes decisions costing about 3 human-hours per generation. Its
   load-bearing output is `agreement(human, reference)`, which validates **the oracle**, not the
   policy: that is the one number in this document that is not self-referential. `agreement(human,
   policy)` is a distribution check and **must never become an objective**, because optimising it
   caps the bot at human level.
2. **Every oracle-referenced metric is partly self-referential.** `DQ-3` and `DQ-4` are measured
   against a reference built from checkpoints of the same project, so they systematically understate
   exactly the errors the policy cannot see. `VAL-4` bounds the understatement; it does not remove
   it.
3. **Imperfect information means a perfect-information oracle over-measures regret.** A `cheating
   oracle gap` (O2 with perfect information minus O2 determinized from the belief) is the honest
   correction and is also interesting in its own right: it says what fraction of the game is
   guessing, and therefore how much a belief head can possibly buy. It is T3 and needs a
   determinization sampler that needs decklists that need `E-DECK`.
4. **The combat family is scoped, not exact.** `combat_scope_v1` excludes trample, deathtouch,
   menace and multi-block precisely because the general problem is NP-hard. `scope_coverage` is
   published on every combat row, and if it falls below 0.5 the family is not a headline. The
   temptation to quietly relax the scope and keep the headline is the failure mode to guard against.
5. **`EC-4` assumes trigger conditions are pure predicates.** If the rebuild keeps conditions as
   imperative handler code, missed triggers cannot be measured as specified and the fallback
   (differential replay against a second implementation) is a much larger project. Decide this in
   the rebuild, not afterwards.
6. **Elo needs 400 games per pairing for a +/- 35 CI**, and much of what this catalogue wants to
   compare is smaller than 35 Elo. The paired instruments (`DQ-1`, `DQ-2`) exist because of that,
   and they are 5x cheaper, not 100x.
7. **Archetype and colour are confounded** in the current deck generator and will stay confounded
   until it learns. Until then, per-colour metrics measure the sampler as much as the policy, and
   the colour x archetype grid is the only honest presentation.
8. **We do not yet know the baseline distribution of any threshold in this document.** Every number
   marked `[guess]` is a placeholder awaiting the first calibration window (Rail K). Treating them
   as alarms before that will halt runs on noise, which is a fast way to make the protocol something
   people route around.
9. **Two thirds of this catalogue is dark at E0** and roughly a third stays dark until E1 and E2.
   That is a fact about the engine, not a defect in the protocol, but it means the first several
   reviews will be thinner than this document looks.
