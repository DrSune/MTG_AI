# 27 — FoR false premise, 14-pack triage, FAIL-REGISTERED convention (2026-10-07)

## 1. The "CONFIRMED FoR engine bug" (doc 26) is SUPERSEDED — it was a false premise
Doc 26 claimed FoR prints "prevent the next damage of the chosen colour to you" and its
golden lacking PREVENT was an engine-vs-printed-text bug. **The printed text of both
printings is** "Put a +1/+1 counter on target creature you control. It gains protection
from the color of your choice until end of turn." (M21 #19 `MTG_bot/data/M21.json`, KTK #10;
externally verified). The golden `M21/2038f505` (PUT_COUNTER then Choose-of-5
GRANT_ABILITY PROTECTION EoT) is CORRECT. Adding PREVENT would have CREATED a bug.
Lesson recorded in PITFALLS: an audit "CONFIRMED" that was written without the card's
oracle text is a hypothesis, not evidence.

## 2. What IS confirmed: the executor's PROTECTION keyword implements ONE facet only
`layers.protections_of` has exactly one consumer — `block_pair_blocked_reason`
(`executor/legality.py:1634-1686`). CR 702.16c's dealt-damage / can't-target / can't-enchant
facets are unimplemented (DEAL_DAMAGE consults only `ctx.replacements`/PREVENT_EFFECT).
Root cause behind BOTH runed_halo's measured bypass AND FoR's unobservable damage facet.
This is an **executor semantics gap**, not compiler-expressible — registered, not patched
(executor frozen this batch).

## 3. FoR ladder-ified via the observable block-legality facet (4 un-reclassifications)
- `feat_of_resistance.json`: gold colour **U ("1"≠vocab[0])**; blue FoR on adv; blue 1/3
  Vodalian Arcanist `not_asked_to_block` (legality.py:1694 — protection legal against
  nothing is never asked). Wrong-colour twin `feat_of_resistance_blocked_twin.json` shows
  WHITE (the null pick) blocks and deals damage. Null punished on both lanes.
- `basri_ket_x_feat_of_resistance.json`: same block-legality lane, reclass removed.
- `waker_of_waves_activation.json`: the old "no lane exists" reason was FALSE — the
  graveyard lane (run_scenarios.py:826-829) discriminates: gold line now `card:7` keeps
  Library 5 (null pick `card:6` drops it, fails gy lane).
- `spellgorger_weird_noncreature.json`: the old "ask never exposed" reason was FALSE —
  Goremand's printed "sacrifice a creature" cost DOES surface a sacrifice ask; gold now
  pays with Fodder (`card:1`); null auto-pays Weird (`card:0`) and fails the zone lane.

## 4. The 14 reclassification packs — triage verdicts (all now fail_registered, none deleted)
| verdict | packs | evidence |
|---|---|---|
| true-no-decision (7) | chandra_flame_s_catalyst_branch0{1,2}_twin, chandra_heart_of_fire_branch0{1,2}_twin, liliana_s_devotee_branch01_twin, tolarian_kraken_skip_payment | "skip" ∈ PASS_WORDS (puzzle_cert.py:75-85) so null replay IS the gold decline line; branch-coverage twins — fire branches certified by siblings (ladder-ready) |
| null-degenerate-observable (3) | tampering_destroy_artifact, tempered_veteran, tolarian_kraken_tap (choose kind only) | real decisions whose premise pins option = vocab[0]; certifiable by twins (tampering option-1 via not_asked_to_block lane; kraken untap-premise twin) — TODO. tempered_veteran's life branch ALREADY certified by new `trufflesnout_etb_life_twin.json` (gold '1', null punished) |
| engine-semantics-gap (1) | runed_halo | golden correct per print; §1/§2 executor PROTECTION damage facet missing → no lane can observe the name choose |
Trufflesnout ETB golden (M21/8a15841a) is a modal Choose(PUT_COUNTER|GAIN_LIFE 4) +
single-candidate inner target (selectors.py:438 auto-fill) — the old "token target"
reason conflated the two.

## 5. FAIL-REGISTERED convention (owner 2026-10-07) — implemented
- `puzzle_cert.py`: items gain `fail_registered` + `fail_verdict`; summary gains
  `fail_registered` + `fail_registered_by_verdict`; printed in main; CORPUS_NOTES.
- `run_scenarios.py::_triage_check`: any `eval_reclassification` (pack- or step-level,
  incl. by_ask_kind) MUST carry `verdict ∈ {true-no-decision, engine-semantics-gap,
  null-degenerate-observable}` + non-empty reason; bare strings FAIL the gate. Silent
  reclassification can no longer reappear.
- Tests: `test_fail_registered_verdict_is_counted_not_deleted`,
  `test_untriaged_reclassification_fails_the_runner_gate` (tools/audit, 76 passed).

## 6. Commands & gates (2026-10-07)
- `tools/run_scenarios.py` → **373/373** (new: trufflesnout_etb_life_twin)
- `pytest MTG_bot/core -q` → **2391 passed + 2 subtests**; `tools/training` → **77**; `tools/audit` → **76**
- `tools/audit/puzzle_cert.py` (200 rollouts, 25.5s) → items **155**, l1_ready **16**,
  punish_inaction **144**, no_discrimination **0**, offenders **0**, fail_registered **11**
  = {true-no-decision 7, null-degenerate-observable 3, engine-semantics-gap 1}, mean_random 0.3447.
