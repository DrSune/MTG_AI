# 2026-09-28 — Grammar Round-7-B (R7-B: no-grammar top-ups): results

Follow-up to `03-grammar-round7-decision.md` §3 B-table + `04-owner-decisions.md`.
All 9 B-table row groups (13 sentences) landed with **zero grammar changes** — every construct
already existed at HEAD `dfbaf1d`. Pre-snapshot: `/tmp/golden_pre_r7b_2026-09-28/` (flat, 305 files).

## Headline numbers (`.venv/bin/python tools/measure_grammar.py --set M21 [--refresh-goldens]`)

| Metric | pre-batch | post-batch | note |
| --- | --- | --- | --- |
| PC-1 card_coverage | 262/305 | **274/305** (0.8984) | +12 full cards — 13 sentences over 12 cards (Tavern Swindler carries 2 queued rows) |
| PC-2 sentence_coverage | 586/639 | **599/639** (0.9374) | **+13 = exactly the batch**, zero overshoot |
| PC-3 ambiguity | 0 | **0** | verified pre- AND post-refresh; every new pattern globally 1-match |
| PC-4 golden_stability | 12 diffs pre-refresh | **0** | exactly **12** golden files changed (293 byte-identical); 10 `abilities`-key, **2 `keywords`-key** (Baneslayer Angel, Sporeweb Weaver — a `KeywordOutcome` folds into the card-level `keywords` array, not `abilities`; the r7-A `emblem`-key precedent generalized: audit rule = abilities/emblem/keywords **payload** only) |
| PC-6 orphan verbs | 2 (FLIP_COIN, PHASE_IN) | **1 (PHASE_IN)** | FLIP_COIN consumed by `B5c-flip-cost` the round it became template-usable; standing 1 (executor-deferred, owner-ratified) |
| PC-8 targetable | 87/305 | 88/305 | +1 (Hunter's Edge s2's new TARGET selector) |
| unparsed queue | 53 shapes / 53 occ | **40 / 40** | exactly −13 / −13, **0 new shapes** (`pre \ post` set-diff); `/tmp/opencode/r7b/queue_post_r7b.txt` |
| pytest MTG_bot/core | 1434 | **1448 passed, 0 failed** | +14 batch tests (b5b 11, b5c 3, b2b 1, minus/plus count-table flips); golden verify zero-diff again |
| pyright (3 templates + 3 tests + gen_buckets) | — | **0 errors** | the two new test classes needed bare `assert isinstance` narrowing (86 → 0); template modules clean first pass |
| ruff (same files, default rules) | — | **delta 0** | one self-introduced I001 (b5c import order) fixed via `ruff --fix --select I001` in-session (/06 precedent); 7 residual TRY004 = HEAD's pre-existing house pattern in b5b test helpers; `ruff format` clean |

## Where each row landed (bucket-JSON ownership, verified against /tmp/opencode/phase1_buckets/)

Module inventory after batch (templates / UNCOVERED): **b2b 58/3** (was 57/4), **b5b 69/12**
(was 62/21), **b5c 79/11** (was 76/14). +11 templates for 13 sentences: two tids each carry two
concrete sentences (`B5b-keyword-list-params`, `B5b-its-controller-token`).

- **templates_b5b.py (7)**: `B5b-keyword-list-params` (Baneslayer Angel → PROTECTION param
  `FOr(SUBTYPE_EQ Demon, SUBTYPE_EQ Dragon)`; Sporeweb Weaver → HEXPROOF param
  `FAtom(COLOR_HAS, color="U")`. Emits ONLY the parameterized member — the bare members arrive
  via `raw.keywords` and the compiler `kw_set` dedup merges. Scryfall artifact, verbatim:
  Sporeweb's keyword field also lists bare "Hexproof", so the card keeps a second
  parameterless HEXPROOF), `B5b-if-died-two-tokens` (Fungal Rebirth s2 —
  Conditional(DIED_THIS_TURN, CREATE_TOKEN); C14 "two" word-pinned `QConst(2)`; "green"
  dropped, C-2), `B5b-would-damage-incarnation` (Nine Lives — ReplacementAbility over
  DamageDealtEvent; `source=None` IS the printed universal "a source"; PUT_COUNTER
  INCARNATION×1 on the self enchantment), `B5b-flip-won` (Tavern Swindler s2 —
  Conditional(FAtom(FLIP_WON, who=YOU), GAIN_LIFE 6)), `B5b-choice-of-grants` (Alchemist's
  Gift — Seq(MODIFY_PT, **Choose(1-of-2)** deathtouch|lifelink grants, grant target
  `referent="target"`), `B5b-its-controller-token` (Angelic Ascension Angel 4/4 flying +
  Secure the Scene Soldier 1/1; "white" dropped C-2 verbatim; creating player implicit —
  CREATE_TOKEN has no controller role, exact Necromentia s3 precedent),
  `B5b-its-controller-loses-life` (Liliana, Death Mage [−3] s2 — LOSE_LIFE whose **controller
  role carries a referent="target" Selector**: the controller-of-the-selected-object executor
  convention, Gloom-Sower precedent).
- **templates_b5c.py (3)**: `B5c-flip-cost` (Tavern Swindler s1 — ActivatedAbility
  Cost(CostTap, CostLife 3) + role-less Verb.FLIP_COIN atom),
  `B5c-then-if-lands-untap` (Fabled Passage s2 — "Then " continuation;
  Conditional(CONTROLLER_COUNT_GE(Land, QConst(4) word-pinned "four"), UNTAP);
  **referent="result"**, see deviation 1), `B5c-damage-equal-power` (Hunter's Edge s2 —
  "Then " continuation; DEAL_DAMAGE target = new TARGET creature-you-don't-control, amount =
  `QProp("target", POWER)`).
- **templates_b2b.py (1)**: `B2b-blocks-flying-pump` (Snarespinner — **first production TRIGGER
  use of the R6-4 `DeclareBlockersEvent.blocked` slot** (previously prevention-only);
  `blocked=FAtom(KEYWORD_HAS, FLYING)` per Shacklegeist; blocker rides the primary filter as
  IS_SOURCE, b4 cant-block shape; +2/+0 → power-role only). The stale b2b UNCOVERED diagnosis
  ("filter/subject are both over the blocker") is superseded and pruned.

## C16 decision-surface ledger (binding)

| row | decisions kept open | forced |
| --- | --- | --- |
| 1 keyword lists | none | all (static grants) |
| 2 Fungal Rebirth | none | all |
| 3 Nine Lives | none | all |
| 4a flip-cost | **coin flip** (Verb.FLIP_COIN, the stochastic vertex) | activation/costs |
| 4b flip-won | gate reads FLIP_WON (who=YOU) | gain 6 |
| 5 Alchemist's Gift | **keyword choice** Choose(1, {deathtouch, lifelink}) + creature target (TARGET selector) | +1/+1, EOT |
| 6 Fabled Passage | none new (board-count gate; register-bound untap) | all |
| 7 Snarespinner | none | all |
| 8 Hunter's Edge | **damage target** (new TARGET selector) | dealer+amount are board-dynamic QProp |
| 9 its-controller ×3 | none | all (creator implicit, lossy-not-defaulted, verbatim) |

No row introduced a defaulted choice; `up to`-shaped C-1 collapse does not apply to any R7-B
sentence.

## Deviations from the decision doc (all deliberate, verified, recorded in builder docstrings)

1. **Fabled Passage referent = `"result"`, not the doc sketch's `"target"`** — verified against
   the landed golden: s1 is a SEARCH atom with **no TARGET selector**, so "that land" names the
   card the previous sentence searched-and-moved = the R7-1 result register. The only
   antecedent that exists today (C12).
2. **Non-continuation second sentences assemble card-level** — Tavern Swindler s2
   ("If you win the flip…") and Death Mage [−3] s2 ("Its controller loses 2 life.") carry no
   continuation prefix, so the type-fold wraps them into a SpellAbility(CREATURE /
   PLANESWALKER); rules-wise both belong inside the preceding ActivatedAbility. The FLIP_WON
   gate / referent="target" selector keep the binding machine-visible; an executor-side
   association note ships in each docstring (same assembly artifact class the compiler already
   accepts for other multi-sentence activations).
3. **Nine Lives prevent-clause has no PREVENT atom** — `PREVENT_EFFECT` is the duration-scoped
   restriction verb, not a replacement step; per the landed r5 convention (Containment Priest /
   Scorching Dragonfire / Conclave Mentor) the ReplacementAbility subsumes prevention and the
   action is just PUT_COUNTER. "to you" is dropped from the damaged-recipient filter — **no
   player-identity FAtomPred exists** (the b2b noncombat-damage rows drop the recipient the
   same way). R8 grammar candidate: a player-recipient predicate.
4. **Keyword-list rows emit only the unbuildable parameterized member** (mission's "the
   compiler already builds the rest bare" mechanism) — full coverage comes from the
   compiler's `(keyword, params)`-keyed dedup merge.
5. **DEAL_DAMAGE has no source role** (role table: target+amount only) — the dealer ("that
   creature") is the amount-QProp's referent object, executor-side (r8 canonical, same shape
   as the r7-A Primal-Might FIGHT attacker).

## Pins (tools/gen_buckets.py)

- **No pin changed** for R7-B: none of the three modules feeds the gen_buckets partition
  (B2b is derived trigger-minus-B2a; B5 thirds are coverage-independent). Dated note added at
  `expected_keys`. All 8 bucket JSONs regenerate **byte-identical** (`cmp` vs
  `/tmp/opencode/phase1_buckets_pre_r7b/`).
- UNCOVERED prunes are module+test-pinned: b5b 21→12, b5c 14→11, b2b 4→3.
- Test count-table flips: b5b tids 62→69 / COVERED 70→79 / SHAPES 91 stable; b5c 76→79 /
  COVERED 77→80 / UNCOVERED 14→11; b2b TEMPLATES 57→58, EXPECTED 58→59, covered 58→59,
  matched occurrences 72→73. Fungal Rebirth e2e flipped from "covered+uncov" to all-covered.

## Pitfalls confirmed / added this batch

- **CONFIRMED (from /06)**: module docstring header counts go stale when appending ("57
  templates" / "TEMPLATES — 76 entries" again); `assert isinstance` narrowing for Pyright;
  referent-selector pins (CHOOSE + QConst(1) + neutral zone); SHAPES flip scripts must match
  the file's double-quote literal style.
- **NEW — golden audit key**: keyword-covered rows land in the golden **`keywords`** key, not
  `abilities` (Baneslayer/Sporeweb). Audit rule is "abilities / emblem / **keywords** payload
  only" going forward.
- **NEW — `LOSE_LIFE.controller` accepts a referent Selector** (controller-of-the-object,
  Gloom-Sower event-reference shape); `CREATE_TOKEN` does **not** take a controller role —
  asymmetric, easy to get wrong.
- **NEW — `_VERB_ROLES` is validated strictly** (missing-required AND extra-role both raise):
  build AtomArgs against the table, not the doc sketch.
