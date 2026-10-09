# 60 — Gameplay eval v2: full-agent seats; the v1 null was partly an artifact; BC loses to a greedy heuristic once both seats actually play

Date: 2026-10-09. Command: `.venv/bin/python tools/eval/gameplay_eval_v2.py --games 200 --workers 4 --device cpu`
-> `tools/eval/gameplay_eval_v2.json`; gate `.venv/bin/python -m pytest tools/eval -q` = 11 passed.
File: `tools/eval/gameplay_eval_v2.py`. Follows 57 (v1 null). NO commits.

## Mechanism finding (investigated before implementing)
1. **The engine DOES ask the act-side combat decisions** through the same provider
   lane v1 billed as ask-only: `attack:<card>:<turn>` ATTACK/DECLINE
   (`Executor._declare_attackers`, executor/__init__.py:~1452);
   `block:<card>:<turn>` = attacker-handle tokens + NONE (`_declare_blockers` :1514);
   `policy:`/`order:`/`trample:` damage splits (`_combat_damage` :1678);
   `cw:<seat>:<digest>` combat instants (RUNG-2, stack.open_combat_window :652).
   All via `offer_or_autopick` (offers.py:47; len==1 forced = journal-only, no ask).
2. **v1's bug**: its provider routed EVERY ask by `world.active_player`
   (gameplay_eval.py:139). During combat the active player is the ATTACKER ->
   all defender-side asks (blocks, defender cw, defender splits) were answered
   by the OPPONENT's policy. The defensive lane never existed in v1 -> one
   concrete cause of the v1 zero-leverage reading being, in part, an ARTIFACT.
3. **The genuinely scripted layer is the RIG, not the engine**: main-phase act
   batch (play land / cast what / activate / pass) is chosen by
   `RandomPolicy.take_acts`/`pick_spell`/`select_targets` (games.py:586/490/442)
   with driver rng. NAMED GAP: `query.legal_casts has no ask-site producer` —
   no main-phase priority window exists in the engine. v2 fixes it rig-side:
   `PolicyActDriver` asks the seat policy over the declarative menu
   `PASS + land/cast/activation handles` (handle tokens ground to card rows;
   `site:?` token — off-distribution for BC, reported). RESIDUAL driver
   heuristics (not hidden): mana auto-tapped in full (no tap-amount ask exists);
   multi-slot target rows keep parent rng; zero-candidate slots fixed (crash).

## Coverage (v2 asks answered per lane, engine lane 9,279 + rig-side act/target)
attack 1,230-1,644 | block 190-414 | cw 3-23 | order 9-50 | trample 8-11 |
act 4,159-6,141 | target 207-288 per lane; seat attributed by site-tag handle ->
`controller_of` (fallback active for generic may/scry/choose = correct v1 lane).
0 illegal actions across **39,303** recorded policy answers (engine gate intact).

## Results (seeds 1-200, seat-swapped, pool=engine 285, CPU, 1,979 s, 0 illegal)
| matchup | W | D | L | crash | wr(dec) | CI95 | dmgdiff | lead@7 | lead7->win |
|---|---|---|---|---|---|---|---|---|---|
| mirror S3_s1 vs S3_s3 | 86 | 2 | 103 | 9 | 0.455 | [0.386,0.526] | -1.14 | 0.377 | 0.788 |
| S3_s1 vs TEACHER-v2 heuristic | 75 | 0 | 117 | 8 | **0.391** | [0.324,0.461] | **-3.71** | 0.375 | 0.849 |

- **BC S3_s1 loses SIGNIFICANTLY to a deterministic hand-coded greedy
  heuristic** (CI entirely < 0.5; loses from both seats: 35W-61L seat0,
  40W-56L seat1). Mirror twins indistinguishable (expected for same-data twins,
  and now measured over REAL played combat).
- Leverage proxy: out-damage differential at round 7 predicts the winner
  79-85% — metric is outcome-sensitive (largely structural: damage causes wins);
  the independent evidence is NEGATIVE dmgdiff with NEGATIVE wr in both lanes.
- Behavioral profile (BC vs heuristic): attack DECLINE 0% vs 15%; block NONE
  0% vs 52% (BC blocks the first candidate 83-87%); combat-window PASS 69-83%;
  act PASS 8-9%; agree_heur act 41-44%, attack 84-88%, scry/order/trample ~0.

## Crashes 17/400 = 4.25% — ALL engine/encoding defects, policy only picks legal rows
`quantity.py:839` HAS_COUNTER assert (missing count/kind in encoded atom) x13;
`quantity.py:331` QX-no-declared-X x2; `quantity.py:341` QThisTurn(NONCOMBAT_DAMAGE)
x1; `stack.py:1016` ValueError CAST-cannot-pay x1 = **query/execution
inconsistency: legal_casts offered a row cast_card could not pay for**.
5 seeds crash in BOTH lanes (deal-deterministic); remaining 12 = policy-timed
arrival at the same engine defects (defect upstream, trigger timing not).

## Caveats / self-adversarial (full adversarial-gate DISPATCH DEFERRED: subagent
depth limit — orchestrator must re-gate the C2 conclusion before it grounds)
- BC-vs-heuristic is a **pipeline** comparison: BC starved by 90.5% observation
  sequence-truncation (26,384/29,167 BC-lane asks; obs stream > max_len=1024,
  ab_duel.py:263; heuristic
  needs no tokens) -> C2 says the CURRENT interface+policy loses, not that the
  learned policy is untrained-bad. Truncation ceiling is the top suspect + candidate
  fix (compact obs encoding / larger max_len) for T5-G v3.
- Wilson on decisive-only; exclusions are shared-deal (5 seeds both lanes) ->
  near-symmetric, policy-neutral.
- Heuristic is both opponent and agreement probe -> teacher-lane agree=1.0 by
  construction (ignore that column).
- Teacher's rules ignore evasion/reach; menus are engine-legality-narrowed, so
  it can never be illegal — its strength bound is preference quality only.
