# 2026-09-28 — Grammar Round-7 TEMPLATE BATCH (R7-A): results

Follow-up to `03-grammar-round7-decision.md` + `05-decision-surface-contract.md`.
All 29 committed R7-A row groups landed (the withdrawn `B2b-when-you-do` Kraken row was not
attempted); every acceptance gate in the batch mission passed.

## Headline numbers (`.venv/bin/python tools/measure_grammar.py --set M21 [--refresh-goldens]`)

| Metric | pre-batch | post-batch | note |
| --- | --- | --- | --- |
| PC-1 card_coverage | 241/305 | **262/305** (0.8590) | +21 (doc band 260-263 hit) |
| PC-2 sentence_coverage | 552/639 | **586/639** (0.9171) | **+34 = exactly the batch**, zero overshoot |
| PC-3 ambiguity | 0 | **0** | every new pattern verified globally 1-match |
| PC-4 golden_stability | 25 diffs pre-refresh | **0** | exactly 25 golden files changed (280 byte-identical); all diffs inside the `abilities` payload — the only nominally non-`abilities` key (`Liliana, Waker of the Dead` → `emblem`) is itself an emblem `abilities` change ("It gains haste." landed); audited vs `/tmp/golden_pre_r7_2026-09-28/` |
| PC-6 orphan verbs | 3 (FLIP_COIN, PHASE_IN, FIGHT) | **2 (FLIP_COIN, PHASE_IN)** | FIGHT consumed by `B3-fights-target` + `B5c-then-it-fights`; back to the standing 2 |
| PC-8 targetable | 86/305 | 87/305 | +1 |
| unparsed queue | 85 shapes / 87 occ | **53 / 53** | exactly −34 occurrences, −32 shapes, **0 new shapes** (regression check `pre \ post` diff); `/tmp/queue_r7_post.txt` |
| pytest MTG_bot/core | 1420 + expected golden fail | **1434 passed, 0 failed** | golden verify zero-diff again |
| pyright (6 templates + 6 tests + gen_buckets) | — | **0 errors** | 6 test files needed `assert isinstance` narrowing (116 → 0) |
| ruff (same files, default rules) | — | **delta 0, net −9** | HEAD `{F401:5, I001:8, ISC004:3, TRY004:28, UP035:1, UP037:1}` → `{F401:3, I001:2, ISC004:1, TRY004:28, UP035:1, UP037:1}`; `ruff format` applied (8 files) — HEAD copies were format-clean, so formatting is part of the gate |

## Where each row landed (bucket-JSON ownership won over doc tid prefixes)

Module inventory after batch (templates / UNCOVERED): **b2a 59/3, b3 28/2, b4 38/9,
b5a 56/7, b5b 62/21, b5c 76/14**. +29 templates total = exactly the 29 rows.

- **templates_b2a.py (2)**: `B2a-draw-that-many` (Kinetic Augur — C15 `CHOOSE`+QConst(2)
  discard, `QProp(event, THAT_MANY_COUNT)` draw), `B2a-etb-exile-until-leaves`
  (Idol of Endurance).
- **templates_b3.py (1)**: `B3-fights-target` (Brash Taunter — Verb.FIGHT effect, TARGET +
  `IS_ANY_TARGET` self-exclusion per Selfless Savior precedent).
- **templates_b4.py (4)**: `B4-you-choose-from-it` (Duress + Kitesail Freebooter — `Verb.CHOOSE`
  pool-target + count=1), `B4-protection-chosen-name` (Runed Halo s2 — GRANT_ABILITY PROTECTION
  w/ `NAME_CHOSEN` param), `B4-per-tapped-this-way` (Siege Striker — `QBin(MUL, QProp(event,
  THIS_WAY_COUNT))` PtDelta), `B4-reveal-one-from-among` (Garruk's Harbinger — Optional +
  Seq(REVEAL ONE_OF-top, MOVE_ZONE)).
- **templates_b5a.py (5)**: `B5a-exile-that-until-leaves` (Kitesail Freebooter),
  `B5a-etb-choose-name` (Runed Halo), `B5a-choose-name-not-basic` (Necromentia — CHOOSE_NAME +
  FNot(SUPERTYPE Basic ∧ TYPE Land)), `B5a-equipped-per-soul-counter` (Malefic Scythe —
  `QBin(MUL, QProp(source, COUNTER_COUNT))`, soul-counter kind dropped, C11 verbatim),
  `B5a-destroy-equipped` (Turn to Slag — `IS_ATTACHED_TO referent="target"`).
- **templates_b5b.py (15)**: `B5b-it-gains-kw-eot` (Basri Ket / Basri DP / Seasoned Hallowblade /
  Traitorous Greed), `B5b-it-gains-haste` (Liliana Waker **Emblem**),
  `B5b-it-gains-protection-choice` (Feat of Resistance — C15 five-way `Choose` node, NO default),
  `B5b-that-player-discards` (Duress — `ControllerRef.TARGET_PLAYER` + result-referent cards),
  `B5b-if-it-type-then` (Garruk Savage Herald + Track Down — `Conditional`),
  `B5b-otherwise-bottom` (Garruk Savage Herald — compiler `_merge_otherwise` → `else_effect`),
  `B5b-search-name-exile` (Necromentia s2 — SEARCH+EXILE, chosen-name filter),
  `B5b-token-per-exiled-this-way` (Necromentia s3 — QProp(event, THIS_WAY_COUNT) token qty),
  `B5b-loses-kw-eot` (Soul Sear — Verb.LOSE_ABILITY, target-referent "that permanent"),
  `B5b-one-of-other` (Waker of Waves — ONE_OF/REST partitions),
  `B5b-one-of-rest-bottom` (See the Truth — REST → bottom),
  `B5b-rest-bottom-random` (Garruk's Harbinger — REST bottom, "random order" lossy),
  `B5b-search-one-other-shuffle` (Cultivate — SEARCH/REVEAL/MOVE + SHUFFLE),
  `B5b-cast-elsewhere-instead` (See the Truth — CAST_THIS_TURN_FROM + "instead" Conditional),
  `B5b-gain-control-eot` (Traitorous Greed s1 — DurationEot).
- **templates_b5c.py (2)**: `B5c-untap-that-creature` (Traitorous Greed s2 — UNTAP +
  `referent="target"`), `B5c-then-it-fights` (Primal Might s2 — FIGHT, C15 `CHOOSE`+QConst(1)
  "up to one").

## Deviations from the decision doc (all deliberate, recorded)

1. **Doc tid prefixes vs bucket ownership** — several doc guesses moved: Kinetic Augur's
   "that many" draw → **b2a** (not b5b), Runed Halo split across **b4+b5a**, Traitorous Greed
   split across **b5b+b5c**, Brash Taunter fight → **b3**. The `phase1_buckets/*.json` truth won.
2. **Referent wiring** — anaphoric `it`/`that card`/`those cards` use `referent="result"`;
   anaphoric references to the *spell target* (`that creature` = Traitorous Greed s1 target,
   `that permanent` = Soul Sear, `that creature` = Turn to Slag's equipped check) use
   `referent="target"` (R4 vocabulary, binds today) instead of inventing an executor-side
   register hop. Every case is commented in its builder docstring.
3. **Lossy C11 captures** (verbatim notes in builder docstrings): Kitesail + Idol of Endurance
   drop "until … leaves the battlefield" (`_VERB_ROLES[EXILE]` has **no duration role** —
   round-7 added `DurationUntilLeaves` but wired it only to GAIN_CONTROL; **R8 grammar item**);
   "in a random order"/"in any order" ordering details dropped; Necromentia "black" token colour
   dropped (`TokenSpec` has no colour field); Malefic Scythe soul-counter **kind** dropped
   (`QProp` has no counter-kind slot); Cultivate "you may put that card onto the battlefield"
   reveal-count via `QUnbounded` REVEAL; Primal Might FIGHT has **no attacker role** (attacker =
   result-register object, executor-side per r8 canonical).
4. **C15 decision-surface pins** — `up to two/three/one` → `CHOOSE`+`QConst(n)` everywhere new
   (Kinetic Augur, Primal Might); protection-colour-of-your-choice → 5-option `Choose` node,
   never a defaulted colour; `may` → `OptionalEffect` (Harbinger reveal, Cultivate);
   name choices → `CHOOSE_NAME` (+`name_filter` for Necromentia); partitions → `ONE_OF`/`REST`;
   `if it's …/Otherwise` → `Conditional` + `else_effect` merge (verified end-to-end in the b5b
   tests).

## Pins bumped (tools/gen_buckets.py, dated `2026-09-28 r7-batch`)

- B2a pattern keys 57→59 (UNCOVERED prune 5→3, bucket stays 62/66).
- B3 pattern keys 45→46 (UNCOVERED prune 3→2, bucket stays 48/55).
- B4 pattern keys 34→38 (UNCOVERED prune 13→9, bucket stays 47/63).
- B5 modules don't affect bucket membership (residual split); b5a/b5b/b5c UNCOVERED prunes
  (12→7, 39→21, 16→14) are test-pinned only.
- All 8 bucket JSONs regenerate **byte-identical** to `/tmp/opencode/phase1_buckets_pre_r6/`
  (`cmp` on all 8) — pattern↔UNCOVERED swap preserved membership exactly.

## Pitfalls confirmed / added this batch

- `unittest.TestCase` already defines `_outcome`; a helper named `_outcome` in a TestCase
  subclass raises `TypeError: '_Outcome' object is not callable`. Use `_match_one`.
- b2a's EXPECTED table asserts the **Template.name**, not a free-text label — reuse the exact
  card name the builder ships.
- Referent selectors (C2) must pin `CHOOSE` + `QConst(1)` + neutral zone (`Zone(ANY, ANY)`,
  no `zones`) or validation fires.
- `self.assertIsInstance(...)` gives Pyright **no** narrowing — use bare `assert isinstance(...)`
  before `.pred/.field/.referent/.inner/.then_effect` on union-typed IR nodes (116 pyright
  errors → 0 across the three test files).
- FIGHT's single `target` role is the *opponent*; attacker is never a role (r8 canonical).
