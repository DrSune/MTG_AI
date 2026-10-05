# 2026-10-05 · 09 — Training-setup design: decision-stream BPTT on the executor (HEAD cb25acd)

Role: training-setup designer (design-only — this doc is the deliverable; production untouched).
Answers: observation/sequence schema, BPTT rollplan + owner-theory operationalization, memory
scenarios S1–S3, reward/verification, batch plan 0→4.

**Honesty law (standing, today):** NO training has run on the validated executor. Nothing here
is a performance claim; every number cited is measured (with command) or explicitly labelled
estimate/legacy. Eval claims are scripted-floor numbers only until the D8–D11 gauntlet (B4)
stands.

## 0. Anchors (measured / read today)

| Fact | Value | Source |
|---|---|---|
| Decision interface | `DecisionStream.take(vocab, what)`; provider lane `(vocab, what) -> answer`; `ask_log` records `(what, answer)` in ask order; seed pins whole decision history | MTG_bot/core/executor/decisions.py (14b/B-4 channel) |
| Ask site tags | `may:<src>`, `scry:<p>:<n>`, `choose:<src>:<digest>`, `name:<src>`, `cw:<seat>:<dig>`, `counter:<seat>:<dig>`, `pay:<payer>:<dig>` | decisions.py docs, stack.py:677/824, verbs.py:1864 |
| Candidate ordering | EVERY vocab/candidate list is **Handle-sorted**, PASS-first for windows | stack.py:541/567/649, quantity.py:15, selectors.py:287-383 |
| Game shape | mean **33.52 turns**, 47/53 decisive, 0 crash classes, 100 seeds | NUMBERS.md (`python -m MTG_bot.core.executor.games --seeds 100 ...`, reports/games_2026-10-04.json) |
| BCS instrument | 305 cards, per-card `bcs` 0–70 (mean 14.12, median 13, 192 cards ≥10); heat top: Basri Ket 70, Garruk's Unleashed 54, Siege Striker 53 | tools/audit/bcs.json (python stats scan) |
| Machine (17:5x measured) | 121 GiB unified total; **9.1 GiB free** while qwen-vLLM holds ~100 GiB; 20 CPUs; ~273 GB/s BW shared CPU+GPU; ~125 TFLOPS dense bf16 peak / ~50 achieved (est.) | owner briefing + docs/DESIGN_TRAINING.md §"one number" |
| Env throughput, executor | **NO MEASURED NUMBER EXISTS — MEASURE-FIRST stands.** Instrument landed mid-design: `tools/training/collector.py` (412 lines, uncommitted) wraps the provider lane; episode rows `{ask_id, vocab-tag, candidates (canonical order), chosen_idx, clock, seat}` = §1 schema exactly; `--bench` reports games/turns/**decisions_per_sec** per worker count — run it (batch 0). Legacy anchor: 7.7 ms/op-step = 52.1 steps/s/worker, 833/s @16 — rule_engine era, does NOT transfer (executor adds journal + ask channel + catalog) | collector.py:43/343-366; docs/DESIGN_TRAINING.md §4 |
| BPTT memory arithmetic | step-level gradient checkpointing = **0.14 MB/decision**, +33% compute, full-game BPTT feasible w/ ~200× headroom; recompute must be dropout-frozen/RNG-preserved | docs/DESIGN_TRAINING.md §3 (mitigation (c)) — architecture-agnostic, carries |

Legacy strategic_brain verdict (headings-only review): **frozen** — `environment.py:MTGEnv`
wraps rule_engine (do not run); `benchmarker.py` proximity metric is the proven-fatal flaw
(do-nothing=1.000, METRICS §10). TRANSFERS: the pointer-scorer concept (`ActionPointerHead` =
score a descriptor list, never a per-card softmax — same law as DESIGN_TEACHER §4.3) and
embedding-table hygiene. Everything else rebuilds natively on the executor.

## 1. Observation & sequence schema (the training interface is already built)

The executor's ask-time provider IS the environment API. One **decision step** =

    (site, obs_tokens, candidate_tokens) -> action_id ∈ [0, |vocab|)

- **site** = the `what` tag: `may:` / `scry:` / `choose:` / `name:` / `cw:` / `counter:` /
  `pay:`. Embed as a small vocabulary (≤16 tag classes + digest bucket as a scalar feature).
  The digest (`site_digest`, sha1-12, cross-run stable) identifies the site kind without leaking
  the payload.
- **obs_tokens** = caller-side serialization of the visible state at the ask moment
  (life, mana pool, permanents as Handle tokens × {tapped, PT, counters, keywords}, stack rows,
  hand as Handle multiset, turn/phase). v1 = omniscient-v1 surface (matches the engine as-is);
  **masked view (C2) is a drop-in replacement of the same schema with hidden zones deleted** —
  which is exactly why C2 is specced before any RL, not after.
- **candidate_tokens** = the vocab tuple as delivered. **Handle-sort is FREE permutation
  control**: the engine guarantees one canonical order, so training never needs augmentation
  for order-robustness — but the model must be **permutation-equivariant over candidates**
  (shared pointer scoring head, no positional embedding inside the candidate span) so the
  score is a function of content, not rank. Position-identity leakage (rank-sorted vocab) is a
  D10-class audit: shuffle-invariance unit test on the scorer at batch 1.
- **answer** = index into vocab (pointer, never vocab-size softmax; vocab is dynamic-sized).
  PASS is `vocab[0]` in window asks by construction — pass-learning is position-free via the
  token's embedding.

**Episode = ordered sequence of one seat's decision steps** (both seats generated by their own
policies/opponents; the stream records `(site, vocab, chosen_idx, reward-lane deltas)`).
`ask_log` gives the exact sequence with zero new machinery; determinism (seed ⇒ identical
decision history — the replay pin relies on it) makes episodes reproducible and cheap to replay
offline.

**Sizes (estimates, batch 0 measures):** 33.52 turns/game measured. Decisions: ~30–80 asks/game
across both seats (10–20/player scripted-line estimate from the brief; ETB may-offers,
designations, Rung-1/2 windows push the tail up). Obs ≈ 60–150 tokens/step at Handle-vocab
(305-card vocab + tag/numeric tokens, ~1.5–2k entries total); candidate span 2–20. Episode ≈
2.5–10k tokens; pad to buckets {2k, 4k, 8k}. A full 100-game corpus is <1 GB of token ids —
**episodes are a disk artifact, not a RAM-resident pool** (this choice defuses S1).

## 2. BPTT rollplan and the owner's theory, operationalized

**Policy:** decoder-style causal transformer over the decision-step sequence: obs tokens →
hidden state → pointer over candidate embeddings + PASS bias. Losses, in order of use:
1. **BC/CE on taken actions** (certified gold lines: the 121 decision packs + wave-7 window
   packs via the /03 extractor) — batches 1–2, zero reward involved.
2. **Advantage-weighted CE** on self-generated streams (REINFORCE-with-baseline / AWRE-style:
   CE × Â clipped) — batch 3+, once the gauntlet stands. No PPO machinery until needed.
3. Value head (win/loss regression) optional from batch 3; only shaping source = journaled
   damage/life lanes (§4).

**Full vs chunked BPTT is NOT a memory question at this scale — it is the experiment.** Step-level
gradient checkpointing (DESIGN_TRAINING §3(c): store only recurrent/summary state + raw step
inputs, recompute the forward in backward; dropout frozen in the recomputed region) costs
~0.14 MB/decision — a 10k-token episode is ~MB-scale. Two-player M21 games are ~50–100
decisions, nowhere near the 512-decision full-BPTT break point computed for the old
Commander-sized trunk. So:
- **S1 default = FULL-EPISODE BPTT** (trivially affordable; the owner's theory is honored from
  day one at low cost).
- **Chunked-truncated (K = 32, carried state) = the control arm** at every later scale where
  streaming rollouts make full-episode awkward (S2+ on-policy RL).

**The owner's theory, stated falsifiably:** *niche decks = rare, long-chain payoffs (high-BCS
cards: branch-heavy, delayed triggers, anaphora, entanglement — the BCS primitives p1–p9 are
exactly a taxonomy of long credit chains); bootstrapped credit (TD/GAE over chunked horizons,
or K-truncated BPTT) blurs credit across long gaps; backprop through the whole rollout
preserves it.* Testable prediction: full-BPTT beats chunked **specifically on high-BCS slices**
and nowhere else — an INTERACTION, not a main effect.

**Operationalization (all instruments already exist):**
- **Curriculum sampling:** episode/deck weight ∝ f(deck BCS) — deck BCS = max and mean over its
  cards' `bcs` (bcs.json, 305 cards). Oversample high-BCS decks in TRAINING only.
- **Per-BCS-slice EVAL splits:** quartiles of the deck-BCS distribution (≈ mean 14.1 / median
  13 give natural cuts at the distribution's 25/50/75 pct); report **PZL-3 IRT θ (± SE) per
  slice** + D8-band winrate per slice. Tags (H12 concept tags: sequencing, stack_response,
  layers) give the mechanism-level secondary read.
- **THE theory experiment (batch 4):** arms {full-episode, K=32, K=8} — identical data stream,
  optimizer steps, seeds; primary pre-registered metric =
  Δθ_high-BCS(full) − Δθ_high-BCS(chunked), with the same contrast on low-BCS as placebo.
  TD/GAE is run as a third control (the "bootstrapping blurs it" half of the theory).

## 3. Memory scenarios S1–S3 (the model ladder) and the honest pool story

AdamW/fp32-mixed: optimizer+grad+master ≈ 10·params bytes (bf16 compute), activations ruled out
as constraint by §2's 0.14 MB/decision. Worker cost dominates the small scenarios: ~16 spawn
(no-fork, no-CUDA, OMP=1) env-worker processes, each a compiled-supply + Python engine copy
(~150–400 MB; share compiled IR via a read-only blob mmap where possible).

| Scenario | Free RAM | Model | Train batch | Notes |
|---|---|---|---|---|
| **S1 coexist (now)** | **~9.1 GiB** | **40–80M params** (d=512, L=6–8, 8h) ≈ 1.3–2 GB optimizer set + full-episode ckpt'd activations (batch 16–32 games, <1 GB) | 8–12 env workers (~3–4 GB) | **MVP today, no engine-reservation change.** S1 SHAPE DECISION (§6): 50M pointer-transformer, full-episode BPTT, offline episodes from disk |
| **S2 owner lowers reservation** | 40–70 GiB | **0.5–1.5B** (1.5B ≈ 15 GB set; 2B fits 70 only) | 16 workers + rollout pool 15–30 GB (packed token-id episodes + frozen opponent checkpoints) | self-play league of frozen scripted+learned opponents starts here (D3-gated) |
| **S3 engine paused** | ~110 GiB | **3–4B** (4B ≈ 40 GB set) + batch 128–256 games | big pool + league + big vocab embeddings | batch-4 theory experiment runs here for throughput, not necessity — §2 shows 300M suffices to TEST the theory |

**The honest pool sentence:** with a Python environment, GiB is not the sampling bottleneck —
**env-steps/second × wall-clock is.** A rollout pool bigger than `measured_steps_per_sec ×
hours` is a spreadsheet fantasy; memory only buys pool after throughput is paid for. At the
legacy rule_engine anchor (52 steps/s/worker, 16 workers — NOT executor-valid) a 33.5-turn ×
~60-ask game ≈ 3–5k env steps ⇒ **10–15 games/hour** worst-case; if the executor's journal +
ask channel halve that, 5–8 games/h is the ceiling on 16 cores. Consequence designed-in:
- **Batches 1–2 are OFFLINE** (episode files recorded once, trained many epochs — BC does not
  need on-policy). This decouples the trainer from throughput entirely and makes S1 work TODAY
  at 9 GiB, exactly the owner's "use the machine" spirit without touching the engine reservation.
- On-policy RL (batch 3+) is where the pool matters: size it from the batch-0 number, keep the
  pool = replay ring of ~2–5k episodes (GB-scale, trivial in RAM) — and say plainly: **pool
  depth beyond env throughput buys nothing; CPU throughput is the tax on every ambition here.**
- The 273 GB/s shared-bandwidth law (DESIGN_TRAINING): heavy Python rollout traffic competes
  with training matmul for bandwidth; worker count is tuned (8 vs 16) at batch 0 for net
  games/hour, not maxed.

## 4. Reward & verification — the anti-hacking is the eval design

- **Batches 1–2: no reward at all.** Supervised CE on certified gold lines (121 packs + window
  packs; certificates per /03: null = PASS-all, random = 200 rotated-seed uniform rollouts,
  reject item at random > 0.05). A policy that cannot beat a measured floor here has no
  gradient story worth scaling — and nothing learned here can be reward-hacked because nothing
  is rewarded.
- **Batch 3+: terminal win/loss ±1 (draw 0)**; shaping ONLY from journaled, two-sided visible
  lanes (damage / life delta rows — the same lanes the 339 packs' `expect` blocks assert;
  WINDOW_PASS rows visible per R17-1). No shaping from proximity, hidden zones, or any
  non-journaled quantity (the benchmarker's corpse stays buried: do-nothing scored 1.000 under
  such a metric).
- **Adoption gate = the SAME gauntlet the bugcatch arc built** (D8–D11, 04-rulings standing
  law): D8 robust winrate over opponent-noise band eps∈[0.5,1.0] as HEADLINE (never vs-pure-
  random — that inflated 0.820→0.590); D9 rotated eval seeds, fixed-vs-unseen delta reported
  (raw +0.400 memorization is the measured failure mode); **D10 masked-observation ablation —
  positive full-vs-masked delta DISQUALIFIES, not bonuses** (58/116 hidden-candidate E3 census
  is why); D11 blocker-randomization; seat-swap every duel number (E7 0.530 seat bias).
  Puzzle ladder PZL-3 IRT **θ ± SE** is the skill metric independent of any opponent model.
- **C2 sequencing law:** RL batches train on the MASKED view and report masked-vs-full parity;
  a trained policy on the omniscient-v1 surface before C2 parity is training the leak before
  the skill (D3 bar, verbatim). Trained-policy claims may only cite the gauntlet runner (B4),
  exit-code-honest like measure_bugcatch.
- B1's scripted window-competence policy (overcost-counter / save-trade burn) is the seeded
  opponent pool for early self-play — scripted competence before learned competence.

## 5. Batch plan 0→4 (each: gate + what a NULL result means)

| # | What | Acceptance gate | Null result ⇒ |
|---|---|---|---|
| **0 Measure-first** | collector.py smoke (provider lane records (site, vocab, pick) episodes; determinism check seed→identical ask_log); env-steps/s per core × {4,8,16} workers vs learner contention; asks/game + tokens/step histograms | throughput + size numbers in NUMBERS.md with command; smoke test green (sibling batch's collector joins here) | executor ≥5× slower than legacy anchor ⇒ re-plan ALL batches around record-once/replay-forever + demand the engine fast-path (one-legal-action auto-resolve lever, DESIGN_TRAINING §4) |
| **1 S1 MVP** | 50M pointer-transformer, full-episode BPTT, BC on extracted gold lines; vs null/random certified floors | held-out puzzle θ beats random-cert floor by > 3 SE; shuffle-invariance unit test passes; suite unchanged (tools-only) | BC can't beat floors ⇒ observation schema or extraction is broken (omniscient-v1 or vocab handling) — fix C2/extractor, do NOT scale, do NOT hire more parameters |
| **2 BCS curriculum** | BCS-weighted deck sampling; per-slice eval splits; niche-oversampled pool | high-BCS slice θ rises vs batch-1 baseline at UNSEEN seeds (D9 discipline) with low-BCS slice Δθ ≈ 0 (no cannibalism) | oversampling can't move niche slices ⇒ limitation is representation (embeddings/candidate scorer), not data mix — redirect budget to architecture, log to PITFALLS |
| **3 S2 + gates standing** | 0.5–1.5B; masked-view training (C2 parity first); D8–D11 runner in CI (B4); scripted-pool self-play (D3 unbarred only by B4∧C2) | gauntlet pass: D8 robust headline > scripted floor band; D9 fixed-vs-unseen delta within noise; D10 masked-delta = 0; D11 survives; θ ordering matches Elo-vs-scripted-pool (C4 check) | trained policy beats floor only vs pure random ⇒ memorization, ladder was not carrying skill; revert to batch-2 loop, no S3 spend |
| **4 Theory test (S3)** | full-episode vs K=32 vs K=8 (+TD/GAE control) on the SAME data/compute; high-BCS interaction as sole pre-registered metric | pre-registered Δθ interaction CI excludes 0 on high-BCS slice AND placebo contrast ≈ 0 AND gauntlet Δ unchanged ⇒ owner's theory SUPPORTED at measured magnitude | full ≈ chunked on every slice ⇒ **BPTT-through-time theory falsified for this task at this scale** — adopt chunked (cheaper), record the negative honestly in NUMBERS; "we tested the owner's hypothesis on the machine's own terms" is a win either way |

Ordering law honored: batch 1 is Tier-A-adjacent (zero new machinery beyond the /03 extractor);
each later batch names its prerequisite; nothing waits on S3 — S2/S3 are throughput rentals,
not correctness prerequisites, and the theory experiment is affordable at 300M in S2 if the
owner won't pause the engine.

## 6. Decisions taken (this doc is the ruling until superseded)

1. **S1 shape: 50M-param causal decision-stream transformer (d=512, L=8, 8 heads,
   F.scaled_dot_product_attention), pointer scorer over Handle-sorted candidates + PASS bias,
   full-episode BPTT with step-level gradient checkpointing, offline episodes from disk
   (BC), AdamW fp32-mixed.** Fits 9.1 GiB with room; theory-honoring from day one.
2. Training interface = the DecisionStream provider lane, nothing else; episodes are ask_log
   artifacts; Handle-sort is the permutation law; scorer must pass a shuffle-invariance test.
3. The theory is ONE pre-registered interaction contrast (§2), instrumented by bcs.json slices
   + IRT θ — not a vibe, and testable without ever pausing the coding engine if S2 suffices.
4. No RL before certified floors exist and the gauntlet runner stands; no claims beyond
   scripted-floor gaps (today's honesty law, restated so this doc cannot age into a lie).
