# 2026-10-05 · 03 — Puzzle corpus & training-feasibility memo (HEAD 4dbe864)

Role: puzzle & training-feasibility research. Answers the owner's four questions:
(1) corpus quality + extension, (2) real-game import feasibility/payoff,
(3) self-play warmup, (4) tie to D8–D10 eval gates. All local numbers measured
today at HEAD 4dbe864 unless a source file is cited. Web findings are snippet-only.

## 0. Measured inventory (2026-10-05)

| Fact | Value | Command |
|---|---|---|
| Executor packs | **339** (339/339 green per NUMBERS 2026-10-05 H5) | `ls tools/scenarios/ \| wc -l` |
| Packs with `decisions` key (gold-line answers) | **121** (131 decision entries; 120 packs non-empty) | `grep -l '"decisions"' tools/scenarios/*.json \| wc -l` |
| Pure-assertion packs (no decisions) | **218** | 339 − 121 |
| Branch packs (negative-control family) | **15** files, 7 cards × branch{01..03} ± `_twin`; branch swaps the ask/line and `expect` shifts per-seat (e.g. heart_of_fire base expects seat-0 life, branch01 expects seat-1) | `ls tools/scenarios/ \| grep -c branch` + pair diff |
| Two-sided asserts | **all 339** carry an `expect` dict with per-seat `life` keys + zone/power/counters/keywords | python key scan |
| Legacy corpus | **131** files: L1 = 50 generalized + 6 lethal + 50 lethal_bulk; L2 = 25 generalized | `find MTG_bot/scenarios/M21 -name '*.json' \| wc -l` |
| Legacy quality (METRICS §10) | 17 distinct `setup` blocks; 3 card ids carry 128/131; `p2_attacking_creatures` authored but never instantiated | docs/METRICS.md §10 |
| Benchmarker flaw (confirmed) | `benchmarker.py:82-108` never reads `p2_attacking_creatures`/`p1_mana`; `:156-163` proximity = fraction of starting life → do-nothing scores **1.000** on all 25 L1 survival puzzles (and 0.900 on L2); `:116` caps at 5 steps, `deterministic=True` → suite evaluates a different model than the one that plays | reports/AUDIT_2026_09_10.md §"do-nothing"; docs/METRICS.md §10 |
| Legacy runner | imports frozen `MTG_bot.rule_engine` (scenario_runner.py:10-12) → legacy puzzles are NOT executor-native | grep imports |
| Punish-inaction today | **0 of 339 packs**: all five counter cards excluded_by_flag ⇒ zero response windows (R17-1 constraint 4) | KNOWLEDGE/2026-10-05/04-rulings-r17.md |

## 1. Executor-native puzzle ladder (Q1)

**L1-ready AS-IS: strictly 0.** The PZL rebuild (METRICS §10) requires per-puzzle
`null_score/random_score/oracle_score/oracle_line` certificates, a binary terminal
goal, punish-inaction, and ≥1 trap — no pack carries a `null_score` field, so by
rule 3 "a scenario file without a `null_score` field does not load". But the
corpus is far closer than the legacy suite:

- **121 decision-key packs are L1-ready cores.** They already encode
  (position → scripted gold answers → two-sided terminal asserts), i.e. exactly
  `(state, menu, gold action, binary outcome)`. Wrapping each in a certificate
  harness is mechanical work, not authoring.
- **218 assertion-only packs** are rule/arc regression tests, not puzzles; keep
  them as engine regression, do not count them toward the ladder.
- **Branch/twin packs are the seed of trap items**: same card, different branch,
  divergent `expect` = a built-in "plausible-but-wrong action looks fine"
  discriminator (PZL rule 5) already validated green.

**What decision-ask extraction adds.** Run each pack with the R17-1 rig-side
provider intercepting asks: capture one puzzle item per ask =
(prompt state, legal menu, gold answer, expect block). This (a) turns scripted
answers into real unscripted asks (PASS-fallback + WINDOW_PASS journaling make
null scoring = always-PASS representable); (b) makes null/random scoring
automatic (null = PASS every ask, random = uniform menu pick); (c) scores binary:
replay policy pick, resolve scripted tail, diff `expect` per PZL rule 1
(same-episode difference, no proximity — `_calculate_proximity` deleted, not
patched).

**Punish-inaction gap.** No current pack threatens the candidate. Path: R17-1
unblocks it — script the opponent's attack as pack steps, leave the block/answer
window as an unscripted ask with PASS fallback; PASS ⇒ scripted attack line kills
⇒ binary fail. This is the executor-native redo of the legacy survival puzzle
whose threat was authored but never instantiated; the executor instantiates it.
Counter-card stack puzzles must wait for the counter-flag arc.

**Concept tags (H12).** Tag every item with per-concept tags (combat_math,
sequencing, layers, mana, stack_response). This is the "partly LOST" half of H12
and the direct input to PZL-3's per-concept θ (MTG is not unidimensional;
METRICS §10 PZL-3 requires per-concept theta and residual checks). Tags also
let cards hot-swap across sets (tied-rank-1 goal).

**Procedural extension.** Re-implement the legacy generator intent
(PROCEDURAL_SCENARIOS.md: set-first hierarchy, categories lethal/board_clear/
setup/combat, L1 tactical → L2 sequencing → L3 probabilistic) against the
*executor pack schema*, emitting packs that already carry the decisions/expect
shape. Generation ≠ validation: every generated item still needs the
null/random(200 rollouts)/oracle certificate pass, with
`random_score > 0.05` rejected at build. IRT (PZL-3) then auto-retires dead
items (METRICS predicts "almost all" of the legacy 131 retire on first fit —
retire legacy, do not migrate it). **PZL-4 oracle-mining** (mine self-play
positions with stakes>0.10, sharpness>0.05, random<5%/200, ≤8-action line) is
the endgame grower; it guarantees the null-zero property by construction but
inherits oracle bias — puzzles are for regression/skill-tracking, never a
ceiling (state in corpus header).

## 2. Real-game import: feasibility & payoff (Q2)

| Source | License | Granularity | M21-relevant | Auto-translatable → executor | Est. manual min/game | Optimality signal |
|---|---|---|---|---|---|---|
| 17Lands public datasets | free site download; bulk export via tracker tools; redistribution restricted (verify ToS) | game rows (decklist, opening hand, draws, win/loss) + **pick rows only** — no play actions | partial: 17Lands replay data "usually back to early 2021"; M21 rotated Sep 2021 → thin tail | decklist→world-init ~90%; **play actions: 0% (absent)** | ~0 (bulk) | outcome + field rank only |
| Sokolov & Zechner drafting data (IEEE DataPort "Magic: The Gathering Drafting Data"; used by arXiv:2009.00655) | academic dataset, license on page (verify) | **pick-level** (pack→pick) | set-era overlap ~yes | picks only; no play | ~0 | pick-order reference, capped at human level |
| MTGO `.log` replay | WotC client logs; personal use | line-text: casts, mana taps, attackers, blockers, targets (community format — verify on a sample) | **yes** — M21 was on MTGO Jul 2020→Sep 2021 (Draftsim author drafts M21 on MTGO) | ~40-60%: only compiled-card subset + log→executor-op mapping; mana-tap granularity exceeds our ask model | 20–40 (parse gaps + gold-line verify) | player skill unknown (no rank in log) |
| MTGArena academic match dataset (Kazienko group, Wroclaw) — **verify existence/format, snippet search missed it today** | academic | match/turn-level actions, rank field reported | Arena era: likely yes | unknown | unknown | rank = quality strata |
| Arena client logs (own/owner recordings) | personal | per-message, targets included | yes | highest fidelity to our card subset | 10–20 | one human |
| Own recorded play | ours | exact | exact | n/a | n/a | honest label: 1 player |

**Optimality honesty (binding).** Human top ≠ optimal, and METRICS DFT-4 already
rules: *"reference bias caps the model at reference level; never an objective"*;
*"computing an AUC against a self-generated label would be theatre"*. Imports
can serve as (a) eval/imitation-agreement sets, (b) position seeds for oracle
scoring, (c) D8-style opponent-noise models — **never as a teacher.**

**Verdict.** Import does **not** beat hand-building for the L1→L3 ladder:
(i) every imported position still needs the same null/random/oracle certificate
pass — the import saves none of the expensive part, only the authoring part
that the 121 decision packs + procedural generation already supply; (ii)
translation lands on our compiled-card subset (~40-60% of log lines map to
executor ops, MTGO estimate — measure in POC); (iii) ladder items are
worst-case by design (punish-inaction, traps) while human games average
exactly those positions away — top players avoid the blunder setups our ladder
must contain. Import pays off **later and elsewhere**: draft-pick references
(DFT-4/DFT-5 gates), mined-position corpora once PZL-4 machinery exists
(import and mining share the oracle-scoring pipeline), and calibrated noisy
opponents for D8. Trigger: revisit play-level import only when oracle-mining
exists AND a 20-game MTGO-M21 POC measures ≥60% auto-translation.

## 3. Self-play warmup (Q3)

The worry is real and already measured on the legacy stack: do-nothing scored
1.000/0.900 because the metric never read the threat; the shaping reward paid
do-nothing +0.00 while an active policy paid −5.36/200 steps (AUDIT 2026-09-10)
— careless exploration had no gradient to sort out. The fix is not more
exploration, it is the certificate ladder:

1. **L1 (now):** single-ask executor puzzles with null-cert = 0, random-cert
   ≤0.05 enforced at build, punish-inaction via R17-1 windows, binary terminal.
   A careless policy fails loudly and every item contributes to the PZL-3 solve
   matrix (θ with standard error tells us whether exploration is producing
   skill before we ever play a game).
2. **L2 (response-window arc lands):** multi-ask sequencing + threat-assessment
   puzzles (window arc adds stack/interaction items; branch/twin packs become
   trap items). PZL-2 pass-budget sweep measures reasoning-pass value here.
3. **Self-play / PZL-4 mining ONLY after D8/D9/D10 gates are standing** (see §4).
   Before that, self-play vs the current unmasked omniscient surface is actively
   counterproductive: **58 opponent-hidden target candidates in 12 games**
   (E3, all Volcanic Geyser `zone=ANY` selectors) means self-play rewards
   E3-style leak exploitation over Magic skill; D9 shows fixed-seed eval can pay
   0.900 vs 0.500 unseen (raw +0.400 memorization); D8 shows vs-random headlines
   inflate 0.820 → 0.590 robust (gap 0.230). A warmup policy trained and
   measured through those gates learns to monetize artifacts.

**Two-sentence answer:** Puzzles get the policy on-track by replacing dense-but-
ambiguous shaping with per-item binary certificates whose null/random scores are
measured at build, so the first gradient-bearing signal exists from episode one
and IRT θ tracks progress without any games. Self-play stays benched until
D8 (robust-opponent band), D9 (rotated seeds) and D10 (masked-target ablation,
0-hidden-candidates regression gate per R17-2) all stand, because unmasked
self-omniscient eval would train the leak before the skill.

## 4. Gate compliance of this ladder (Q4)

Adopted standing law (04-rulings-r17.md + 01-exploit-transfer-audit.md):
- **D8**: ladder-adjacent duel headlines report robust WR over eps∈[0.5,1.0],
  never vs-pure-random alone (flag gap>0.10, fail >0.20).
- **D9**: puzzle solve-matrix and duel evals rotate seeds; fixed-vs-unseen delta
  reported; puzzle *items* are deterministic so D9 applies to their random
  rollouts (random_score over 200 rollouts must itself use rotated seeds).
- **D10**: every puzzle's oracle/null/random certificates are computed under
  **masked** target surfaces; masked_target_probe stays a standing gate
  (expect 0 hidden candidates after geyser-sweep); any positive full-vs-masked
  delta on a ladder-trained policy = disqualify, not a bonus.
- **D11 + seat-swap**: combat-ladder gains must survive blocker randomization;
  duel measurements seat-swapped (E7 seat bias 0.530).
Certificates computed pre-D10-fix are suspect for the handful of `zone=ANY`
cards — recompute after the geyser-sweep arc, before pinning baseline θ.

## 5. Recommended pipeline order (effort = T-shirt estimates, mine)

| # | Step | Depends on | Effort |
|---|---|---|---|
| 1 | Decision-ask extractor over the 121 packs + certificate harness (null = PASS-all, random = 200 uniform rotated-seed rollouts, oracle = scripted gold line; reject random>0.05) | R17-1 provider (approved) | **S–M (1–2 d)** |
| 2 | Ladder wrapper: binary terminal from `expect` diff; concept tags (H12); PZL-1 triple + PZL-3 IRT solve-matrix plumbing (IRT fit itself "costs seconds") | 1 | **M (2–4 d)** |
| 3 | Punish-inaction family: scripted opponent attack steps + unscripted block windows | R17-1 arc shipped | **M (arc-gated)** |
| 4 | Procedural generator on the executor schema (set-first, categories per PROCEDURAL_SCENARIOS.md) with build-time certificate pass | 1–2 | **M–L (1–2 wk)** |
| 5 | Draft-side import (17Lands game+pick rows; IEEE DataPort picks) for DFT-4/DFT-5 gates only | none | **S (days)** |
| 6 | MTGO-M21 log POC: 20 games, measure auto-translate % + manual min/game; go/no-go at ≥60% auto | PZL-4 oracle machinery | **M** |
| 7 | Self-play + PZL-4 mining (oracle bias stated in corpus header) | D8/D9/D10 standing + geyser-sweep complete + E3 clean | **E3-era** |

Legacy verdict: retire the 131-file frozen-engine suite via first IRT fit
(predicted to retire ~all of it); do not migrate the benchmarker — rebuild
natively on the executor, which is the validated engine.
