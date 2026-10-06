# 20 — Batch 3: capacity CONFIRMED, DAgger NULL, first Elo-positive policy (2026-10-06)

Pre-registered design (doc /16 + dispatch text): A/B capacity arms, filtered DAgger round
on the winner, Elo sanity with fresh seeds (D9), 3-SE gate on eval_families. All ran
engine-off via run_full_memory.sh. Report cards: bc3_{A,B}_report.json, dagger_report.json,
bc3_rollout_{stats,base}.json, elo_s3_sanity.json (all tools/training/).

## Numbers (commands: `.venv/bin/python -m tools.training.train_bc_v3 --arm {A,B,dagger} ...`
## via batch3_full.sh; elo: `python -m tools.training.elo random pass-floor
## tools/training/bc3_dagger_best.pt --games 120 --workers 6 --seed-start 90001`)
| arm | params | eval_families acc | margin vs floor | gate (>3 SE) |
|---|---|---|---|---|
| A (bc_s2 arch) | 35,124,226 | 0.6136 | +2.60 SE | FAIL |
| B (small) | **169,474** | **0.6591** | **+3.21 SE** | **PASS (first ever)** |
| dagger (B on 50/50 mix) | 169,538 | 0.6591 | +3.21 SE | pass but NULL (below) |

**Elo (fresh seed block 90001+, 120 g/pair):** bc3_dagger_best **+59.3 CI [6.8, 111.8]** —
first policy whose CI excludes random (wr vs random 0.567, vs pass-floor 0.517 head-to-head);
pass-floor +42.5 CI [-9.4, 90.9]. K=32, honest CI notes in the json.

## Verdicts per hypothesis
1. CAPACITY: CONFIRMED — the 207x-smaller model generalizes BETTER on unseen families.
   Standing consequence: all future BC arms stay small; 35M was an overfit machine.
2. EXPOSURE BIAS (DAgger): **NOT TESTED, effectively** — the mix trained (39/135 episodes
   source=dagger, best_loss 0.22696 vs 0.22618) but eval moved ZERO, and winner vs bc_s2
   CONTROL rollouts produced IDENTICAL stats (asks 153, points 47, correct 29, skips 3) —
   smoking gun: the rollout never diverged from scripted prefixes, so states were not
   model-visited. A true off-policy round needs divergence replay: after the model answers,
   CONTINUE from the model's chosen action; teacher labels only where gold stays legal;
   count diverged-and-dropped points honestly. New PITFALLS entry; redo queued as batch 4b.
3. Data_mix{'v2':101,'dagger':0} in dagger_report = stats bug in row-level source counting
   (episode-level tags are correct: 39 tagged). Cosmetic; noted, not fixed (minimal diff).

## INCIDENT: two drivers raced (2026-10-06 16:41-17:01)
The original coder-session driver survived its session's death and kept running; the
relaunch (setsid, after the 16:30 false-FAILED) started a SECOND driver. Final artifacts are
mutually consistent (winner=B logic, ckpt names, timestamps 16:43-17:01 all from the original)
and Elo ran at 17:01 after everything, but interleaving is unreconstructable. Fix shipped:
flock guard in batch3_full.sh (exit 9 on race). Also: the 16:55 self-wake fired 6 min BEFORE
true completion because the racing wrapper exited early — wake prompt read at 17:04 after
real completion, harvest unaffected. PITFALLS: engine-guard false FAILED (health window) vs
real driver liveness — check pgrep + ledger BEFORE relaunching; the false FAILED can be
true-but-recovered (engine came healthy after the window).

## Gates (same-turn, orchestrator-executed at 17:2x)
git: 0 files touched in engine/scenarios/audit/traces · pytest tools/training 66 passed ·
MTG_bot/core+audit 2465 passed + 2 subtests.

## Queue after this (NOT auto-started)
(a) true-divergence DAgger v2 (tests the still-open exposure-bias hypothesis); (b) eval
volume: A3 chained-ask ladders (n=44 eval items is the measurement ceiling for everything);
(c) volume for training: same-card families get more scripted gold points via packs.
