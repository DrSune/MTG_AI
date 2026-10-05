# 15 — Eval granularity: corpus v2, zero no-discrimination offenders (2026-10-05)

Closes `14-eval-granularity-brief.md`. Tools-only batch: edits confined to
`tools/scenarios/`, `tools/audit/`, docs. Engine untouched (core suite re-run green).

## Definitions (binding for all numbers below)

- **E_active** := items with `null == 0 ∧ oracle == 1 ∧ 0.02 ≤ random ≤ 0.9 ∧
  not reclassified`. A certified item that *punishes inaction* AND is
  *skill-sensitive* (not solved by coin flips — upper bound 0.9 excludes the
  90%+ random-drift rows; lower bound 0.02 is the l1 ceiling's neighbour).
  Recomputed identically over BOTH corpora for the before/after table.
- **l1_ready** (harness gate, unchanged): `null == 0 ∧ oracle == 1 ∧
  random ≤ 0.05 ∧ candidates ≥ 2`. Binary may/target asks can never reach
  ≤ 0.05 (floor ≈ 1/vocab), so with mostly-binary vocabularies l1_ready stays
  low **by construction** — reported honestly, not gamed.
- **Reclassification**: pack- or step-level `eval_reclassification` field
  (reason mandatory), now also **item-level** via
  `{"by_ask_kind": {<ask_kind>: reason}}` (new this batch, pinned by 2 unit
  tests). Reclassified items keep measured scores in the corpus for
  auditability but leave the offender ledger and the ladder/E budget.

## Headline table (puzzle_cert 200 rollouts/item, same command both rows)

| metric | v1 (before) | v2 (after) |
|---|---|---|
| items extracted | 119 | 119 |
| **no_discrimination offenders** | **52** | **0** |
| punish_inaction | 67 | 104 |
| **E_active** | **66** | **103** |
| l1_ready | 4 | 4 |
| reclassified | 0 | 15 items / 14 packs |
| mean_random | 0.4979 | 0.409 |
| packs | 339→355 scanned | 355, `broken_packs = []` |

Measurement precision (agreement metric over E_active items, p≈0.5):
SE = √(p(1−p)/E): v1 0.0615 (3SE band 0.185) → v2 **0.0493** (3SE **0.148**).
The brief's anchored "E = 4" is the strict l1_ready lens; both lenses are
reported. Honest shortfall: l1_ready ≥ 40 is NOT reachable with binary ask
vocabularies — reaching it needs chained-ask ladders (0.5^k) or 20+-candidate
menus, which is a BUILD task (backlog A3), not a repair.

## What changed

1. **Scry family, 15 packs / 21 items** (first pass): gold scry target reordered
   so vocab[0] (null) diverges; exact library-order lanes falsify null.
2. **17 more packs repaired** (probe-verified mechanics, capture→verify→write):
   kitesail_dragon, crypt_lurker_skip (fire = lurker self-sac + draw),
   crypt_lurker_sac (Spare Goat first candidate, gold "1" discards Discardable),
   tolarian_kraken_tap (gold restored to TAP path — tapped lane is *positive
   evidence* for target/may items; see PITFALLS), sigiled_contender,
   rin_and_seri_cast_triggers, garruk_unleashed_x_rin_and_seri_inseparable
   (aurochs enters AFTER the census — census runs before Beast-token creation),
   necromentia (Abort added so null's name-answer "Abort" ≠ gold "Doom"),
   sanctum_of_all_search_skip (fire = search executes), fierce_empath,
   garruk_s_harbinger_branch01/02/03 (gold "card:4" + exact library lane),
   see_the_truth_branch02, duress, cultivate (gold "card:2" swaps the two land
   destinations), conspicuous_snoop (free-cast Goblin Arsonist; word "fire").
3. **Reclassification, 14 packs / 15 items** — structurally unevaluable asks
   declared with named reasons: 7 new pack-level (basri_ket_x_feat_of_resistance,
   feat_of_resistance, tampering_destroy_artifact, tempered_veteran, runed_halo,
   spellgorger_weird_noncreature, waker_of_waves_activation — each with a probe
   result proving the lane is blind, e.g. deal_damage bypasses protection;
   Tampering's option '1' is a blocker-prevention effect with no combat lane —
   probe: decisions ['1'] leaves the cog alive, so the options are distinct and
   gold cannot flip off vocab[0] without a new premise), 6 pre-existing twin declarations
   (Chandra ×4, Liliana twin, tolarian_kraken_skip_payment), 1 item-level
   (tolarian_kraken_tap's final choose: its gold call IS vocab[0], so a null
   replay equals gold by construction).
4. **Stale twin flags cleared** on crypt_lurker_skip + sanctum_of_all_search_skip:
   their fire-branch mechanics differ from the twins they pointed at, and after
   repair their items certify (null = 0) — keeping the flags would have hidden
   live evidence.

## Corpus + split artifacts

- `tools/audit/puzzle_corpus.json` — v2 (v1 backed up at `puzzle_corpus.v1.json`).
- `tools/audit/eval_split.json` — family-wise (card-name families, no family
  spans sides): 74 families, 30 eval, 75 train / 44 eval items. Rule:
  sorted-family index % 5 ∈ {0,1} → eval; deterministic, no RNG. eval l1_ready
  items = 0 (honest: only 4 l1 items exist, all landed train-side; the ladder
  today is graded on E_active agreement, not l1).

## Verification (exit gates, 2026-10-05)

- `.venv/bin/python tools/run_scenarios.py` → **355/355 packs passed**
- `.venv/bin/python -m pytest tools/audit -q` → **74 passed** (+2 new
  reclassification pins: pack-level exemption, by_ask_kind item granularity)
- `.venv/bin/python -m pytest MTG_bot/core -q` → **2391 passed, 2 subtests**
  (engine untouched)
- Cert: `items=119 l1_ready=4 punish_inaction=104 no_discrimination=0
  mean_random=0.409` in 17.7 s @ 200 rollouts.

Traps discovered → `KNOWLEDGE/PITFALLS.md` (decision word outside vocab
silently deletes the item; default-true lanes kill upstream discrimination;
stale twin flags mask repaired items).
