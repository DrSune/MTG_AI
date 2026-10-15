# 85 — PLATEAU FORK (owner memo): every in-regime lever now falsified with numbers; three roads remain, all Type-1

Date: 2026-10-15. Frontier unchanged: bsh_S3a_s1 (teacher 0.4256, champ-parity 0.4649@400g, live-UNK 0.0007).
## Falsification ledger (each: what, number, caveat)
1. VOLUME: 5.9x live-shadow data -> 0.3594 (in/below band). Gradient-pass-matched both sides (adversarial-verified); single seed. (/80, /83-superseded §)
2. TOKENS (digit-lanes cure): scratch 0.4308 band-top not decisive; no premium vs containment. NUMTOK stays OFF (gates byte-identical). (/78)
3. IMPROVEMENT LABELS: first pass INVALID (adversarial: UCB-visit noise, 73% idx0). Legit re-test (value-gold pipeline, 20/20 games, monitors clean): at 9.2% dose -> mirror 0.4872 [0.418,0.557], teacher 0.4051 = no harm, no gain. Bigger-dose escalation deliberately NOT run: value-gap>0.05 asks are 9%, adv 0.039+-0.005 is real-but-tiny; expected value low, cost 5h+.
## What the plateau IS (honest mechanism story)
Everything learned so far lives 0.36-0.43 vs greedy-teacher at 200g resolution (+-0.035). Expert-class imitation saturates at ~expert strength (learning theory as usual). The teacher itself (hand heuristic, no look-ahead beyond 1) is the ceiling everyone hugs. Breaking it needs a BETTER LEARNING TARGET (RL from outcomes) or evidence more CAPACITY extracts from the same targets (untestable engine-on: GPU law).
## The three roads (Type-1: owner picks)
R1 CAPACITY WINDOW: 2-3h engine-down -> S4-35M (+ batch-10 dense-arm 55M?) on champ_big, 3 seeds, duels. If flat: capacity dead cheaply. If rises: era re-anchors upward at scale. ~1 GPU-night; no new machinery.
R2 RL-FROM-OUTCOME: policy-gradient on win/lose over self-play (or teacher-anchored) — machinery: outcome-labeled trajectories exist (gameplay_eval games), need advantage baseline + PPO-lite or REINFORCE w/ KL-to-frontier (guard against collapse class). Honest cost: 3-5 days incl. eval loops; GPU reality: self-play rollouts CPU-only engine-on (fine: rollout = policy forward, replay speed 500x — the substrate law /68-70 supports it). Risk: variance, collapse, and the eval-resolution problem (needs ~1000g to see +0.03).
R3 FREEZE & PIVOT: declare bsh_S3a_s1 frontier (parity w/ champ, drift-clean, era-safe), redirect to GENERALIZATION program (the actual moat): ZNR integration (awaiting your verified source), batch10 (new set, §8 atomics re-eval — the tokenizer law is where our engine has unique value), and hardening the clone pipeline so every future set ships its own shadow clone in a day.
## My recommendation
R3 + opportunistic R1: R1 costs almost nothing when an engine-down window exists anyway (it is a measurement, not a commitment); R2 is the only road to >expert play but at real days-cost with variance risk — worth authorizing ONLY if WR becomes the project's top KPI. R3 matches True North (unseen-card generalization), which plateau-chasing has been stealing hours from.
## Standing ops laws now in force (from this arc, all in PITFALLS)
P0 memory: single-CUDA-worker rule + per-process fraction + systemd-run MemoryMax scopes (owner). budget-min = POOL semantics. WR-probe admission on every cited ckpt. best.pt = pre-final caveat. Selfwake/pkill self-match traps (/proc scans: exclude $$ AND parent shell — three incidents).
