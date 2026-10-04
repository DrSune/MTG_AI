# 12 — BUGCATCH: residual-bug hunting design (validation campaign)

Date: 2026-10-02 · Status: DESIGN (no code) · HEAD 85f1aaf
Owner charge: find bugs **at scale** in advanced cards (tokens, atomic subcomponents,
complex sequences) by measuring which areas, interactions, and sequence complexities
are most suspicious — then feed the existing author → suspect → adjudicate loop.

Grounded per the NUMBERS law: every number below carries its date + producing artifact;
every design choice cites a real ledger bug or an inspected corpus artifact.

## 0 · Corpus state at design time (evidence base)

- 262 green packs in `tools/scenarios/`, 12 suspect files (17 on disk incl. facets)
  all routed to the compiler campaign, 31 census residue (16 token/vanilla identities,
  COUNTER_SPELL ×5, Teferi PHASE_OUT ×2, Double Vision COPY, Treasure {T}/Sac gap,
  Forgotten Sentinel EtBState). Gates: packs 274→282, suite 2239→2271, 100-seed games
  0 crash classes. (2026-10-01, `26-wave5-closeout.md`.)
- Adjudication-complete 305/305 across five waves; r20a alone promoted 10/10 suspects,
  suite 2182+4 subtests, 100-seed 0 crash / 85 survived mean 57.4 turns.
  (2026-10-01, `NUMBERS.md:2632-2653`.)
- `tools/audit/coverage.json` (2026-10-01, `tools/audit/wave_builder.py --coverage`):
  per-card `profile.ability_node_classes`, `cost_nodes`, `keywords`, `families`
  (activated/etb/spell/static), `in_pack`, `in_suspect`, `status` for all 305 cards.
  **The substrate for everything below already exists and is machine-readable.**
- Journal rows are canonical `(clock, kind, subject, cause, cause_verb, data)` dumps
  (`MTG_bot/core/executor/events.py`), per-row sha256 fingerprinted by
  `tools/traces/catalog.py` over 10 engine-pool seeds, with `compare` locating the
  first divergence. Games corpus: `games.py --seeds 100 --pool all`, per-seed
  survived/crash/coverage_fired digest, `--repro <seed>` replays exactly one game.

## A · Bug-Primitive Complexity Score (BCS) — from the golden IR

Nine primitives, each one a **documented bug family** in the ledger, read directly off
`ability_tree.py` CardRecord nodes (vocabulary verified 2026-10-02 by grep):

| # | primitive | IR read | bug family it predicts |
|---|-----------|---------|------------------------|
| 1 | atomic ops | count of `Verb` atoms (DEAL_DAMAGE, CREATE_TOKEN, PUT_COUNTER, GRANT_ABILITY, …) | sequence-length mistakes (B-4, C2 atom-merge) |
| 2 | branch slots | slots under `FAnd/FOr/FNot/FAtom`, `Conditional`, `OptionalEffect`, `Choose`, `Repeat`, `EachPlayer` | Life Goes On died-branch, tampering entanglement, one_of/rest |
| 3 | role slots | TARGET / TARGET_PLAYER / COST slots (`activation_target_slots`) | 24a TARGET_PLAYER synthesis, TARGETS_SOURCE fold (23a) |
| 4 | quantifiers | `QX, QBin, QProp(QPropField), QCount, QAtLeast/AtMost, QThisTurn` incl. count-vs-power field choice | sanctum NAME_EQ census→0, ornery_dilophosaur, QX-at-ETB (23a etb_x) |
| 5 | token minting | `CREATE_TOKEN` + `TokenSpec` binder-registered statics | thallid self-dies spore, secure_the_scene token controller, Treasure {T} gap |
| 6 | replacement hooks | `ReplacementAbility` (damage/draw/counter/zone/PREVENT_EFFECT) | fiery_emancipation ×3, teferi draw, containment_priest, tampering can't-block (C5) |
| 7 | layers | distinct PT contributions: counter→PT folds, static grants, SET_PT vs MODIFY_PT | basris_solidarity counter→PT missing, trufflesnout counter-blind |
| 8 | triggers | `TriggeredAbility` + `DelayedTrigger` registrations | B-9/B-16 referent detach, self-dies ordering law (22a) |
| 9 | anaphora | IS_SOURCE/IS_TARGET/result/event referents, THAT_MANY_COUNT antecedents | hobblefiend role bleed, wildwood_scourge QX-at-ETB |

**Score**: `BCS = Σ wᵢ·primitiveᵢ`, weights *calibrated by fitting the ~45 fixed bugs*:
rebuild each fixed card's IR, check ≥2 of primitives 4–9 non-zero — the ledger's every
silent-semantic bug sits there, while the vanilla-identity residue sits at all-zero.
This is a falsifiable acceptance gate (Batch 1 below), not a guess. Artifact:
`tools/audit/bcs.py` → `tools/audit/bcs.json`, emitted next to coverage.json with the
same `meta` block discipline (built_by + date + command).

## B · Branch / path coverage per card

Inventory: every Conditional/Choose/Repeat/OptionalEffect branch of every card (from IR).
Evidence: a branch is *lit* if the green-pack journals or the 100-seed corpus contain the
branch's discriminating event signature (the journal row that can only appear on one side
of the branch — e.g. `CREATURE_DIES` with cause==the card's own creature for Life Goes On's
died-side; `CAST` data carrying a chosen mode for `Choose`).
Output: per-card **dark-branch list**. Precedents that prove the payoff:
- Life Goes On died-branch dark until a wave pack lit it — bug was on that branch.
- Fabled Passage: the branch pack only *earned* its keep once the expect lane was made
  falsifiable (a lane that cannot fail is not evidence — standing law).
- tampering: bug lived in branch *entanglement* (can't-block leaking across the union),
  invisible to per-branch singletons.
Rule: a dark branch on a card with BCS ≥ T is a mandatory suspect-pack candidate, never a
"probably fine". Metric: `branch_coverage = lit/declared`, corpus-wide and per card.

## C · Interaction coverage

Two failure classes the per-card corpus cannot see:

1. **Weak-tested pairs.** From the 100-seed reports, co-fire counts of cards appearing in
   the same game (`coverage_fired`, games.py:1015-1026). Green packs only test designed
   pairs; the random corpus tests *popular* pairs. High-BCS × high-BCS pairs with zero
   co-fire = untested risk.
2. **Verb-family collision classes** — each already has a real bug:
   - two PT layers (counter-fold × static grant): basris_solidarity, trufflesnout
   - replacement × replacement: containment_priest ETB × fiery damage rewrite
   - replacement × trigger ordering: self-dies law (ZONE_CHANGE precedes CREATURE_DIES, 22a)
   - grant × consumer-missing: r20a dead-keyword class (LIFELINK/PROWESS/BATTALION granted
     with no consumer — five packs **green on the silent bug**)
   - sacrifice × dies, token × anthem: Soldier-token controller bug, Treasure gap
   - X-census × name restriction: sanctum NAME_EQ family (C1: 13 atoms / 6 idiom / 4 sancta)
3. **Forced splices**: for each untested collision pair, either a two-card scenario splice
   (world block hostile lane) or a pinned deck-pair seed (catalog precedent seed 1409 form)
   so the pair must meet.
Metric: pair-coverage matrix, heat = BCS_a × BCS_b × collision-class weight × 1[untested].

## D · Oracle-free anomaly detectors over live journals

All run on journal rows (`events.py` KIND_* vocabulary), no card oracle needed. Each
carries an invariant, a cost, and an honest false-positive story:

| # | detector | invariant | FP story to engineer around |
|---|----------|-----------|------------------------------|
| D1 | life conservation | Σ life-lost == player damage + prevention deltas | replacements legitimately rewrite damage — sum on *post*-replacement journalled DAMAGE rows |
| D2 | mana conservation | mana added − spent == pool at phase end | empty-pool / mana-drain effects must be journalled as a verb or the lane stays exempt (Treasure {T} gap precedent) |
| D3 | counter conservation | PUT_COUNTER fires == counter movement + counter→PT folds | counters that cost resources (PUT_COUNTER cost) move before resolving |
| D4 | token ledger | token creation rows == binder-registered token permanents on battlefield, per controller | token *copies* and commander-copy tokens need their own register class |
| D5 | **independent layer recompute** | recompute effective PT from journal (counters, SET_PT, MODIFY_PT order, grants, keywords) and diff against battlefield assertions | the trufflesnout killer: a 2/2 assert can be green while counters are ignored — this detector catches the **green-on-silent-bug** class that r20a hit twice |
| D6 | lifecycle audit | no trigger registered-never-drained; no dead handle bound (IS_SOURCE bleed); no replacement fired >1× per event | delayed triggers legitimately expire — bound the window by clock |
| D7 | determinism replay | catalog per-row sha256 stable across engine touches; `compare` gives first-divergence line | benign repr/order churn is why repin exists — diff, then repin consciously |

Scan mode first: run D1–D6 offline over existing catalog journals + `--repro` replays of
the 100-seed corpus, **before** any new engine instrumentation. Acceptance (falsifiable,
per Batch 2): D5 re-detects the five r20a silent-bug cards and trufflesnout on pre-fix
replay.

## E · Feedback loop (this is the product)

`heat(card|pair) = BCS × dark_branch_count × interaction_heat × anomaly_hits`
→ ranked queue → **the existing loop consumes it unchanged**: author a suspect pack with
falsifiable expect lanes (schema verified: pack keys + `status` + `finding`,
`tools/audit/suspects/secure_the_scene.json`), re-run, adjudicate, promote to green or
fix the engine. **No dashboards.** Every heat item terminates as either a suspect pack or
a recorded falsification ("probed, cannot fail this way, no bug") — the Fabled-Passage
law. Adjudicated-dark cards feed back as weight updates in §A calibration.

## F · PC-style metrics + build plan

- **PC-11 complexity census**: BCS distribution over 305; gate: every card BCS ≥ T has
  `in_pack or in_suspect` (extends the census residue logic that closed wave 5).
- **PC-12 branch coverage**: corpus lit/declared ≥ 0.9; zero dark branches on BCS ≥ T cards.
- **PC-13 interaction coverage**: every collision-class pair with both ends BCS ≥ T is
  tested (pack or corpus co-fire).
- **PC-14 anomaly count over N-game stress**: `games --seeds N` + D1–D6; gate 0 anomalies,
  catalog repin clean.

Build order (leverage-first, each batch independently gated):

| batch | work | acceptance gate |
|-------|------|-----------------|
| B1 | `bcs.py` + branch inventory from existing coverage profiles — pure offline, zero engine | bcs.json emits; calibration reproduces known-bug membership (all ~45 have ≥2 risky primitives; vanilla residue has 0) |
| B2 | D1–D7 offline scan over existing catalog + repro replays | D5 re-detects r20a five-card silent-bug class on pre-fix replay |
| B3 | dark-branch + BCS≥T suspect-pack generation, adjudication | green-pack count rises; 100% of new suspects adjudicated (law: 305/305 discipline) |
| B4 | forced collision splices (scenario + deck-pair seeds) | PC-13 matrix full for BCS≥T pairs |
| B5 | PC-11..14 wired into the campaign gates | packs/suite rise, 0 crash classes, 0 anomalies at --seeds 100 |

The corpus is now a *measuring instrument* over itself: coverage.json already carries the
IR profiles, the catalog already fingerprints journals, the loop already adjudicates.
BUGCATCH only adds the score, the branch/pair diff, and the seven detectors — then lets
heat point the next five waves.
