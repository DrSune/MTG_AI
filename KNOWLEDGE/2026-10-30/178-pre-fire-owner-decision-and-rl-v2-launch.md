# /178 — PRE-FIRE: owner decision /176 applied — RL v2 launched; era-boundary map

Date: 2026-10-30 (~17:15–17:45, pre-fire; window #6 still armed for 23:59).
Status: planning record; the owner decision it applies is `/176` (owner, 2026-10-29,
commit `9317f36`).

## 1. The owner-level regime decision was already made

`/176` (sibling entry, owner direction 2026-10-29, committed before this
morning's window-#6 arming) supersedes the A/B/C/D menu in `/174 §6`:
**RL v2 — small on-policy batches (G = 50 games/update, floor 20) with a value
head (GAE γ = 1, λ = 0.95, warm-started on recorded games), PPO clipped
objective (0.2) with Adam, opponent = frozen copy of the starting net,
decision batching (64–256 per forward), exploration = temperature-1 sampling
only.** Draft pre-registration: "RL works" = mirror ≥ 0.55 vs frozen start,
CI95 lo > 0.5 at n = 400 paired fresh seeds, within 100 iterations (5,000
games); per-iteration logging (policy/value loss, value explained variance
> 0, advantage mean/std, entropy, KL per update + cumulative, grad norms,
crash/draw rates); triage order (value explains nothing → fix; KL ≈ 0 →
pipeline no-op; mirror < 0.47 → inspect games). Full spec:
`docs/PLAN_COMPONENT_TRAINING.md` Step 4 "First make RL work" (lines 90–162).

Two consequences for the ladder:
- `/176`: "This replaces the steps ladder after tonight's window (#5, steps
  3), which stays as armed." The owner's intent was window #5 as the final
  ladder point. Window #6 (steps 4) was armed this morning under the then-
  binding `/173 §6` branch 2 (pre-registered before /176 was in context) and
  runs tonight as **one extra measured axis point** ({4}); the ladder ends
  after it as pre-committed, and the regime decision is already made — it is
  not deferred to the owner. Recorded so the axis {1: 0.5279, 2: 0.523,
  3: 0.518, 4: M4} is complete either way.
- `/176` + plan Step 4 §7: "The loop can be debugged on today's engine;
  anything trained there is thrown away. Real runs use the corrected engine
  after the era-boundary merge." — so RL v2 development now = offline
  mechanics + debug runs (discarded); strength claims begin only after the
  era merge + re-pin + re-baseline.

## 2. Era-boundary map — sibling `/177` package vs the pin surface

`/177` (2026-10-30, `cards/integration` 221e400, NOT merged) is the sibling's
side of the bundle: M21 campaign done (263/281 castable verified; 29%→17%
review error rate after fixes; suite 2 failed D3/D11 / 4583 passed; packs
668/668; soak 0 crashes). Its §2 "Consumers to update at the merge" lists —
all in pinned files the branch did NOT edit:
- `tools/training/ab_duel.py` + `collector.py`: every ask sent to
  `world.active_player`; opponents now decide discards/sacrifices/legend/
  Aura-hosts/cleanup-discard ⇒ must read `executor.decisions.asking_seat`.
  **This is the same seat-routing fix as my planned `/162 §3.1.4` seat-rig
  fix** (the probe evidence: asks routed to the wrong seat). The bundle
  converges: one seat-routing fix, three files (collector, ab_duel,
  gameplay_eval_v2 `resolve_seat`).
- `tools/eval/gameplay_eval_v2.py`: `resolve_seat` wrong for may/choose asks
  rotated by EachPlayer; act loop keeps acting after an effect ends the
  turn; heuristic never attacks a planeswalker. (All three are the known
  §3.1.4-era defects in the eval rig.)
- `bc_data` SITE_KINDS lacks `discard`, `legend`, `enchant`.
- New ask/state shapes at merge: attack menus list planeswalkers between
  ATTACK and DECLINE; act windows skip multi-target-slot activations
  (Garruk −2); negative life total (CR 119.3) as life tokens. ⇒ Tokenizer-
  level changes (law §8): the atomic structure must be re-evaluated at the
  re-baseline, not just re-collected.
- Re-pin steps (their list = mine): merge after a window ends → re-smoke in
  real mode → update `RL_PILOT_PIN` explicitly → re-certify puzzle corpus →
  re-baseline every probe.
`/175` (pool fidelity as the pilot plays it, `main`): 42 dead cards (B-49) in
every dealt deck (avg 7.9, 16.5% of nonlands) ⇒ noisier gradient; 98.6% of
games deal ≥1 stronger-than-printed card; mirror reading: bugs bias neither
side (symmetric rig), flat mirror better explained by update size than by
the environment; "the first probe after the merge measures it" (anchor vs
teacher, paired seeds, corrected engine).
Ordering unchanged: era merge + consumer fixes + re-baseline + re-collect
land AFTER the multi-seed/regime decision point — which /176 now fixes as:
debug the v2 loop on today's engine now, real runs after the merge.

## 3. RL v2 launch (PIN law: build beside the payload, adopt at the era boundary)

- Worktree created: `/home/sune/.local/share/opencode/worktree/30c75f/rl-v2`
  (main at `e345bbf`). The main tree stays untouched — window #6's pin wire
  requires tree fp `31b3b78c…` at 23:59 (verified PIN-MATCH at 17:10).
- The anchor checkpoint `tools/training/bsh_S3a_s1_best.pt` is **untracked**
  (not in git; exists only in the main working tree — the overlay-pin
  mechanism) ⇒ all v2 work references it by main-tree absolute path,
  read-only.
- Episode ask records carry the offline value-head input:
  `{what, vocab, idx, logp, obs: {turn, lives, active, seat, battlefield,
  hand, …}, choose}` — board state per decision is recorded, so the v2 core
  (obs encoder → value head, GAE, PPO update, warm-start, batching, logging)
  is buildable and unit-testable TONIGHT against `/tmp/opencode/rld_n1/
  episodes_iter1.jsonl` (1000g, SHA `2e09d72b…`) with zero engine use.
- Delegated (coder subagent, one-per-turn pacing): v2 trainer core in the
  worktree — value head on the shared encoder ("iteration-0 policy
  bit-identical to the anchor" property must be unit-tested), GAE(γ = 1,
  λ = 0.95), PPO clip 0.2 + Adam + 2–4 epochs + KL-early-stop 0.01 +
  gradient-clip safety net, decision batching (pad 64–256, masks verified),
  warm-start on the 1000g episodes (value explained variance must be > 0 —
  triage #1), per-iteration logging per the draft pre-registration, plus a
  worktree-local pre-registration file for the (discarded) debug runs.
- Tomorrow (post-harvest): on-policy debug loop — collection vs the frozen
  anchor (model-vs-model, `ab_duel` machinery; note the seat-routing
  consumers are still main-engine-wrong, so debug collection reuses v1's
  `active_player` routing and records it as a known gap to the era fix),
  5–10 iterations, all results discarded; then the FINAL pre-registration
  for post-merge runs and the era-boundary coordination with the sibling
  (their merge gate + my consumer fixes + re-pin + re-certify + re-baseline
  + re-collect + tokenizer re-evaluation per law §8).

## 4. Window #6 state at pre-fire

Armed 12:25:43 (steps-4 final ladder point; P2 = collect + audit + i3 repro
+ i4 + probe rld_i4 @200g 512002/1413). PIN-MATCH (17:10), no cancel file,
single driver, heartbeat live, engine up (gateway 200). Expected ~247 min
chain, done ~03:30. Harvest per `/174 §5` (hard gates: episodes
byte-identical 5th night, audit bit-identical, no ceiling breach, draws
< 5/200, 0 probe crashes, F5 rld_i4 ≥ 0.6132; soft watch: pass-4 grad on
1000g).
