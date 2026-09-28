# 2026-09-28 — Grammar Round-6 TEMPLATE BATCH: results

Follow-up to `01-grammar-round6-decision.md`. All 13 binding decision-doc rows landed;
every acceptance gate in the batch mission passed.

## Headline numbers (`.venv/bin/python tools/measure_grammar.py --set M21 [--refresh-goldens]`)

| Metric | pre-batch | post-batch | note |
| --- | --- | --- | --- |
| PC-1 card_coverage | 231/305 | **241/305** (0.7902) | +10 (band 240-243; Thieves' Guild/Ghostly/Radha cards still carry other unparsed lines) |
| PC-2 sentence_coverage | 539/639 | **552/639** (0.8639) | +13, exactly the batch |
| PC-3 ambiguity | 0 | **0** | hard gate held; global 1-match verified for all 13 |
| PC-4 golden_stability | 13 diffs pre-refresh | **0** | exactly 13 files changed, all abilities-key-only vs `/tmp/golden_pre_r6_2026-09-27/`; 292 byte-identical |
| PC-6 orphan verbs | 09-27 report: FLIP_COIN, PHASE_IN (before the R6-5 enum existed; after the uncommitted grammar-phase enum bump it was 3 incl. MANDATE_BLOCK) | **2 (FLIP_COIN, PHASE_IN)** | MANDATE_BLOCK consumed by Canopy Stalker `B4-must-block`; back to the standing 2 |
| PC-8 targetable | 86/305 | 86/305 | stable |
| unparsed queue | 98 shapes / 100 occ | **85 / 87** | all 13 sentences absent (`/tmp/queue_post_r6.txt`) |
| pytest MTG_bot/core | 1320 + expected golden fail | **1333 passed, 0 failed** | golden verify zero-diff again |

## Where each row landed (bucket-JSON ownership won over doc tid prefixes)

- **templates_b4.py** (4): `B4-cant-be-blocked-aslong-drawn` (Tome Anima), `B4-must-block`
  (Canopy Stalker), `B4-block-only-flying` (Shacklegeist), `B4-enters-with-x-counters`
  (Wildwood Scourge).
- **templates_b5a.py** (6): `B5a-aslong-opp-gy-count` (Thieves' Guild), `B5a-radha-first-strike`,
  `B5a-during-turn-cost-reduce` (Discontinuity), `B5a-enchant-no-untap` (Capture Sphere),
  `B5a-enchant-cant-attack-block` (Faith's Fetters), `B5a-discard-cant-be-blocked`
  (Ghostly Pilferer).
- **templates_b5b.py** (2): `B5b-gadrak-cant-attack-unless-artifacts`,
  `B5b-set-pt-power-gy-instant-sorcery` (Kinetic Augur).
- **templates_b3.py** (1): `B3-target-cant-be-blocked` (Subira {1} activation).
- Module inventory after batch: b4 34/13, b5a 51/12, b5b 47/39, b3 27/3 (templates/UNCOVERED).

## Deviations from the decision doc (all deliberate, recorded)

1. **b5b, not b4, owns Gadrak + Kinetic Augur** — their shape-keys live in `B5b.json`; the doc's
   `B4-` tid prefixes were analyst guesses. b2a received zero rows (A6-expected).
2. **templates_b2b.py untouched** — its forward-reference comment (~line 2540,
   "Round-5 grammar item: DeclareBlockersEvent.blocked" written before the grammar phase landed)
   is now stale trivia, but editing b2b would violate the A6 edit allowlist. Left as-is; this
   note is the correction.
3. **Subira refinement** — the sketch's `blocked=IS_ANY_TARGET` alone would let a power>2 creature
   be blocked while the PREVENT still fires; the builder puts
   `FAnd(IS_ANY_TARGET, POWER_LE 2)` inside `blocked` (faithful to "another target creature with
   power 2 or less can't be blocked"). Documented in the builder docstring.
4. **Wildwood Scourge** M21 text has no "where X is" clause; QX() resolves at the PUT_COUNTER
   quantity exactly as Runed Halo's QX precedent (C2 referent="event" convention).
5. Lossy C11 captures (Faith's Fetters drops the "activated mana abilities" clause; Capture Sphere
   drops the untap-step scope) are documented in their builder docstrings.

## Pitfall confirmed again

Word-pinned counts: numeric **words** are not captured by the number regex — "two"/"eight"/"four"
sentences hardcode QConst via the Gnarled-Sage house precedent (Tome Anima 2, Thieves' Guild 8,
Gadrak 4). +N/+N and {N} digits *are* captured.

## Pins bumped (tools/gen_buckets.py, dated `2026-09-28 r6-batch`)

- B4 pattern keys 30→34 (UNCOVERED prune 17→13, bucket stays 47/63).
- B3 pattern keys 44→45 (UNCOVERED prune 4→3, bucket stays 48/55).
- All 8 bucket JSONs regenerate **byte-identical** (`/tmp/opencode/phase1_buckets*/` cmp) —
  partition invariant intact.

## Quality gates

pyright (4 modules + 4 tests + gen_buckets): 0 errors / 0 warnings.
ruff (same files): **delta 0** vs HEAD after converting 4 new isinstance-guards to
`assert isinstance` style + `ruff --fix --select I001` on the 4 import blocks.
