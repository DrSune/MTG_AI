# 90 — Causal board-encoder (owner concept): gate-revised verdicts — per-seat KV-replay experiment queued, public-zone age counters ADOPTED, perspective-mask becomes owner decision O1

Date: 2026-10-18. **v2 — adversarial gate ran same day; v1's D1 justification was broken and is
replaced; dispositions below.** All load-bearing claims re-verified by orchestrator greps/reads AND
independently by the gate. Trigger: owner conceptual input (post-/89, pre-FORK).

## Owner concept (paraphrased)
1. Build board understanding causally: append per-action deltas to a growing KV-cache; self-attend
   at each own-action window; unchanged facts stay cached.
2. Optionally after opponent turns: compare realized state against predicted state.
3. Board state must carry HISTORY: how long entities have been in their current zone.
4. Epistemics clause (owner's own): count ONLY what is knowable in the True North scenario —
   elapsed time of a card shuffled into an enemy library is unknowable forever. "Not on vibes."

## Verified substrate (2026-10-18, double-verified)
- **The training stream is ALREADY append-only**: `bc_data_v2.py::encode_episode_v2:360-391` builds
  `seq` by pure `append` per ask — past ask-blocks are frozen bytes. Frontier lineage: max_len 1024
  TOKENS, seq max 1024 / over_limit 0 (bsh_S3a_s1 report), median 871.
- Prefix stability at SERVE time is broken only by the budget drop-ladder (dup-block dedup,
  oldest-block drops, zone-lane collapse — `ab_duel.py:260-360`), i.e. only when the window is
  exceeded. A per-seat KV cache is valid wherever the ladder does not fire.
- **The obs substrate is OMNISCIENT**: packrec emits BOTH players' named hands;
  `packrec_v2.py:89` emits each library's real top-6 named entries (LIB_CAP=6); `ab_duel.py:266`:
  "the obs IS omniscient-v1 (both hands) … D10 masked ablation remains the disqualification gate".
- Age ground truth exists for PUBLIC zones: `events.py::EventJournal:301` (append-only, monotonic
  clock), `KIND_ZONE_CHANGE:51` per zone move (`record_atom:476-488`, fields = from/to/owner only —
  NO position, NO public/hidden flag); turn anchors = TURN_PHASE UPKEEP (`turn_window:440-444`).
  Summoning sickness already reads this journal (`legality.py::_controlled_since_turn_start:1569-1599`).
- **The journal has NO scry/shuffle event kinds** (grep zero hits); same-zone reorders emit no rows.
  Library *knowledge* tracking is therefore NOT derivable today — it needs new engine emissions.
- Cost reality (/79): 90.9 s/ask = 90.8 s CPU rollout forwards + 66 ms root + 31 ms engine stepping.

## O1 — OWNER DECISION (C4 finding): does encoding stay omniscient or become True North?
The age lane only fully makes sense relative to an observer; today's encoder ships hidden info the
model is *not* entitled to see (enemy hand names, library orders). Adding knowledge-labeled ages on
top of leaking lanes is the incoherent middle ground ("partial mask = learnable noise + shortcut via
the leaks"). Two coherent options:
- **O1-A (status quo+)**: keep omniscient obs; age lanes for PUBLIC zones only, all exact; drop the
  True-North labeling; D10 omniscience stays a known disqualification gate.
- **O1-B (recommended, Type-1)**: v3 = PERSPECTIVE-MASKED encoding (per-seat legal view) + full
  age/knowability design. Aligns the substrate with the owner's stated True North intent, closes the
  D10 disqualification (hidden-info leak) at its root, and lands at the only moment its cost is
  marginal: the ZNR-era fresh clone (playbook /88 step 4). Consequence stated honestly: M21-era
  parity/frontier numbers stay valid ONLY inside the labeled omniscient frame; cross-frame comparison
  is invalid (WR-probe admission law style).
Sub-lanes: hand-name/library-order masking (enemy), own-library order treated unknown after shuffle
(the shawner does not know it — physical fact), identity-tracked cards (scry/put-on-top/public
placement) knowable until any subsequent shuffle destroys it.

## D1 (v2) — KV-append: DEFER, corrected justification + cheap experiment FIRST
- v1 claimed the cache FORCES a snapshot→delta tokenizer rewrite (lineage-orphaning). **FALSE** —
  the stream is already append-only blocks; per-seat KV replay over the UNMUTATED format is a
  serving-side, lineage-preserving experiment. Delta-tokenizer is NOT a precondition.
- Batching and KV-replay are DISJOINT wins: batching buys throughput (parallelism); per-seat KV
  replay buys per-step FLOPs O(L)→O(Δ) on long horizons. Neither subsumes the other (v1 conflated).
- **Queued experiment (gate-open runbook, CPU-only, zero new machinery)**: per-seat KV replay over
  the existing format — extend max_len rather than drop-ladder when budget allows, cache blocks that
  are never mutated, invalidate from the first ladder-touched block; verify cached-vs-fresh forward
  parity on goldens before trusting it. Measure vs /79 baseline. Only if measured gain matters does
  the delta-encoding (delta tokenizer) question re-open, per §8 co-timing with ZNR atomics.
- Measurement honesty law (from gate): cap-reduction "exhaustion" verdicts are horizon-confounded —
  turn_cap 40→15 changes what the rollout measures; any lever-exhaustion claim must hold horizon
  fixed and vary the lever, not the reverse.

## D2 (v2) — History counters: ADOPTED, split into buildable layers
- **v3a (adopted, no engine change)**: PUBLIC-zone age lane — battlefield/stack/GY/exile
  `age=<turns since entry>` from journal at RECORD TIME (same code path train & serve; never
  post-hoc scans). Legality proves the pattern today. Drops phantom risk: STACK age is constant≈0 ⇒
  NO stack age lane (§10 phantom-token law). Pin ONE turn-clock convention (obs header `t` vs
  world.turn vs UPKEEP-scan) with unit tests across entry-during-opponent-turn boundaries (gate Q1).
- **v3b (new engine subtask, own budget)**: journal emissions for SCRY/SHUFFLE/LOOK + position
  fields on ZONE_CHANGE ⇒ unlocks library knowability rows. Changing journal bytes = engine
  fingerprint re-cert (frozen-law class) — budget it, don't sneak it.
- **v3c (rides O1-B)**: perspective-masked hand/library lanes with full knowability table
  (enemy per-card NEVER, except publicly-identity-tracked placements until next shuffle; own library
  NEVER after shuffle; own hand EXACT since add; opening-hand seeds symmetric by construction).
- **Sentinel law (unchanged, survives gate)**: `age:N | age:unk` — never 0-default, never a guess.
  unavailable ≠ unknown ≠ zero.
- **Honest costs (C5)**: v3 changes token arithmetic — digit lanes cost 1 token/digit; growth forces
  max_len extension + pos_emb widening (model-config change; `train_bc_v3` refuses over-limit
  corpora); age tokens defeat the drop-ladder's dedup rung; DAgger teacher rows + pi_mix distill rows
  are encoder-AND-model-keyed ⇒ v3 is an interactive rework loop, not one re-recording pass. Before
  ANY v3 commit: publish v3 stream stats IN TOKENS (digit lanes counted) on a ZNR-sized board;
  dual-encode v2/v3 on identical trajectories so encoder vs corpus vs new-set effects stay
  attributable (do NOT bundle three confounders into one ZNR day-1 run).
- Carrier: numeric lane via `numlane.py`; "dormant" (owner's word) maps to NO engine zone —
  owner question: exiled-face-down? phasing? (engine has neither today; answer shapes v3c).

## D3 — predicted-vs-realized world model: BACKLOG (survives gate)
Re-pose at admission: "next-diff-token LM head" is ill-posed against snapshot-BLOCK format; the
training-only aux loss (predict next ask-block's state tokens) is the form consistent with today's
encoding; costs a lineage either way.

## D4 (v2) — Rollout speed: /79 levers, batching measured (not assumed) before it gates anything,
horizon-decoupled exhaustion, then the D1 per-seat KV-replay experiment. KV-append remains NOT the
first lever; its status is now "cheap measurable experiment queued", not "architecturally impossible".

## Gate record
Adversarial (local-64k-xhigh) CONFIRMED five findings against v1: C1 (append-only stream — D1 premise
false), C2 (batching≠FLOPs), C3 (no scry/shuffle journal rows — library rows need engine emissions),
C4 (omniscient substrate — knowability table incoherent as scoped ⇒ O1), C5 (window arithmetic +
v3-cost honesty). All five dispositions applied above; orchestrator re-verified C1/C3/C4 at source
(bc_data_v2.py:360-391, events.py grep, packrec_v2.py:89, ab_duel.py:266). D2 public-zone half,
sentinel law, D3-as-backlog, D4 direction survive. D1's DEFER schedule stands on corrected grounds.
