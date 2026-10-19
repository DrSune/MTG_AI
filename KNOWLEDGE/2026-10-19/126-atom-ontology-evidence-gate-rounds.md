# 126 — Atom ontology: evidence census + gate rounds 1–2 (binding-spec pipeline)

Date: 2026-10-19. Owner directive (same day): build an ONTOLOGY of the atomized
subcomponents — fewest atoms covering everything, functionally-identical wordings →
SAME atoms in SAME canonical order, discovered-branching map, drawn composition tree;
iterate adversarial rounds until findings are immaterial. Spec lives at
`docs/DESIGN_ATOM_ONTOLOGY.md` (binding after round-3 gate; staging copy
`/tmp/opencode/staging/DESIGN_ATOM_ONTOLOGY.md` until then).

## Evidence (admissible: numbers + producing command)
- Command: `.venv/bin/python tools/audit/ontology_shape_census.py` (2026-10-19;
  custom recursive serializer — `walk()` deliberately avoided, PITFALLS list-skip law).
  Output: `reports/ontology_census_2026-10-19.json` (sections A–D, committed).
- Volumes: **546 cards** (M21 293/305 with abilities, 0 shape gaps; ZNR 253/282, 1 gap),
  **1,168 abilities**, **469 distinct STRUCT signatures**, **21 fusion-candidate
  clusters** (>1 STRICT variant under one STRUCT), Selector branching map **40
  branchings** (modes: CHOOSE 174 / TARGET 141 / ALL 132 / ONE_OF 25 / REST 10),
  `Seq[≥2]`=126, `Seq[1]`=0 (phantom ban empirically holds), 31 verbs carry
  target/filter roles (MODIFY_PT×79, MOVE_ZONE×66, GRANT_ABILITY×61), 2 single-child
  FAnd wrapper anomalies (Dauntless Survivor, Negate), 2 FAnd child-ORDER divergent
  groups (Capture Sphere/Cunning Geysermage/Skyclave Pick-Axe vs Nissa of Shadowed
  Boughs; Cliffhaven Kitesail/Light of Promise/Malefic Scythe vs Stonework
  Packbeast/Tajuru Paragon/Veteran Adventurer), 0 same-cluster order variants.
- Reading: same-STRUCT clusters with enum-only STRICT variance (SpellKind×5,
  Keyword×19, PtDelta-direction) are GOOD generalization (§9 shared atoms), not
  fusion targets. The fusion targets are FIELD-level duplicates from the E1 taxonomy
  inventory: direction×7, choose-family×4 modes, cost↔effect twins, damage events×2
  (ability_tree.py cites in spec §4).
- E1 ordering facts: AtomArgs.pairs role-sorted at construction (ability_tree.py:2541
  — the canonicalization precedent); canonical_json :4670 sorts dict KEYS only (list
  order survives — order drift is real); NO model-facing IR serializer exists yet
  (card_embedder.py:23-51 stub; strategic_brain serializes the LEGACY rule_engine) —
  so canonical IR governs identity/goldens today and the model tokenizer later.

## Gate round 1 (adversarial, same day) — verdict FIX-THEN-GO
F1 FATAL `zone`/`zones` twin fields (additive union, Selector docstring :1180) fork
same-wording bytes; F2 CR cites corrected (601.2c/602.2b/603.3a) + O2 re-grounded
(independent Seq steps are trigger-QUEUE-INVISIBLE — CR 603.3b APNAP — so swap-pairs
are functional dups logged in the divergence ledger, NOT tool-normalized); F3 identity
law downgraded to byte-equal ⇒ sufficient same-function PROXY + known-divergence
ledger; F4 Cost.parts: payment order-free (PAYMENT_ORDER legality.py:138) but PLANNING
order-keyed (discount min-clamp :721, hybrid_demands :755, failure-string, witness
digest) → parts-sort split into gated R1b behind planning-determinization; F5 exact
pre/post byte-delta predictions + evidence commit-residency + NUMBERS.md (this file);
F6 checker redesigned: V1′ field-coverage audit (vacuous sorted-check replaced),
walk() banned, V3′ heuristic; F7 census artifacts committed (this commit); F8 V2′
phantom-menu (Choose count==len ⇒ ALL) + V4′ silent-CHOOSE emission freeze (174×
blindness suspect, AGENTS §10, audit in R3).

## Gate round 2 (adversarial, same day) — verdict FIX-THEN-GO
F1→F7 verification: F2/F3/F4 RESOLVED; F5/F6/F8 PARTIAL; F1 NOT-FIXED-WORSE and F7
NOT-FIXED at review time (paper claim — executed by this very commit per law).
- **A1 FATAL (verified in code)**: the engine BRANCHES ON PRIMARY `sel.zone` in ≥4
  rules lanes — selectors.py:428-430 (r19b ONE_OF/REST window needs primary
  LIBRARY+TOP; alphabetical fold would demote LIBRARY and resurrect the
  hover-the-pile bug), selectors.py:484 (16a PLAYER-side CARD→controller re-point;
  Brash Taunter canonical PLAYER∪BATTLEFIELD would fold to primary BATTLEFIELD =
  silent rules change), selectors.py:705/:754 (player_side, exiled-merge),
  verbs.py:247-249 (firemaw top-draw guard). **N5 fold REJECTED.** Replacement:
  gated **R0 = schema fold to ONE `zones: tuple[Zone,…]` set field**, consumer
  migration to union iteration, primary-keyed lanes rewritten as ∃-predicates,
  C2 referent neutral-zone convention preserved, sort key = canonical_json (Zone is
  not orderable — `sorted()` TypeError trap). Sequenced AFTER the live sibling
  executor wave (layers/query fix) per coordination law.
- A3: V3′ must exclude ALL/referent modes (legal identical-Selector repeats), ship
  synthetic TP fixtures — corpus has 0 true positives (biased prior, Archetype 1).
- A4: V4′ freeze must count NEW CHOOSE nodes in COMPILED-IR diffs (compiler.py:1242/
  1280/1292 generic lanes emit CHOOSE without the token in template source).
- A5: R1a byte-delta set MEASURED (not upper-bounded) + PC-6 before/after measured
  before binding (PC-6 currently orphans/max-share — node census shifts under
  flatten). A2: divergence ledger gains row: un-distributed FOr[FAnd,FAnd].
- Expected round-3 residue per gate: enforceability bookkeeping only — zero new
  FATAL/Major classes IF fixes 1–3 are executed (they are, by R0 + checker spec).

## Standing decisions from these rounds
1. Ordering classes {TIME, SET, MENU, IDENTITY, OPERATOR} exhaustive over every IR
   tuple field; full table generated from `dataclasses.fields()` (V1′ baseline =
   every field listed, day-1 ERROR count 0 — generated, not hand-copied).
2. O2 printed-order law stands on value-dependence + identity, NOT trigger-queue.
3. Zone twin-field schema fold is a TYPE-1 pre-R1a round (R0), engine-visible.
4. Emission freeze on NEW SelectorMode.CHOOSE until the R3 blindness audit.

## Gate round 3 (adversarial, same day) — verdict FIX-THEN-GO, one material class
Verified r2-fixes 2/4/5/7/8 executed; **F7 RECURRED** (R1a JSON + table generator
lived in /tmp while the spec cited them) — executed again, v4-committed:
`tools/audit/atom_field_table.py` (V1′ SINGLE SOURCE — detection rule: annotation
contains tuple[|frozenset[|list[; runtime scan 25 container fields = 24 tuple + 1
frozenset (CardRecord.color_identity); 0 unclassified, 0 stale, exit 0; emits the
markdown table AND the checker's importable CLASSIFY dict — doc/code drift becomes
mechanically impossible), `tools/audit/atom_sortdelta.py` →
`reports/atom_sortdelta_2026-10-19.json`.
**A2 FATAL**: v3 §3 table MISSED CardRecord.keywords (TokenSpec.keywords row copied,
CardRecord's dropped in manual merge — lesson: NEVER hand-merge a generated table)
and left the detection rule unspecified (24-vs-25 counting dispute). v4 fixes both.
**A3 MAJOR**: SpellAbility.additional_costs folds into the SAME order-keyed payment
planner (legality.py:1272 kicker fold — verified in code) and CostManaHybrid.colors
keys hybrid_demands (:755/:887) — both RECLASSIFIED SET-R1b (sorting them in R1a was
a landmine masked by corpus Δ0). **A1**: R0 migration surface enumerated — positional
Selector build compiler.py:1050 (silent arg mis-slot risk), ~64 zone= constructors,
binding.py:759 synthesized selector, ~111 test asserts, lane-body selectors.py:445
matched-zone controller EXTRACTION (∃-test-then-reuse = silent rules change),
offer-order diffs (query.py:1127) belong in R0 pre-registration. **A4**:
TokenSpec.{types,subtypes,keywords} are compiler-EMITTED (not oracle print) →
SET-R1a canonicalize, divergence claim dropped. **PC-6 instrument law**: gate metric
= tools/measure_grammar.py (PRE committed: M21 orphans 1/max .1168 ADD_MANA; ZNR 26/
.1547 MODIFY_PT); census measure_pool (4/26) demoted to proxy.
**N-v4 MEASURED** (atom_sortdelta_2026-10-19.json): M21 122/305 + ZNR 80/281 records
change under N (fand_order 117+72, or_order 9+6, fand_flatten_single 0+2, kwds_sort
2+0 [Basri's Lieutenant, Sporeweb Weaver], fatom_colors_sort 1+0 [Quirion Dryad]);
122 M21 goldens flagged (all have golden files); idempotence + leaf-multiset content
preservation PASS; 0 exceptions. Round-3 expectation: round-4 residue bookkeeping
only if fixes land on disk — they are, in this commit.

## Binding V1′ table (module-generated, tools/audit/atom_field_table.py, 2026-10-19, exit 0):
| class | field | annotation | CLASSIFY |
|---|---|---|---|
| AtomArgs | pairs | `tuple[tuple[str, object], ...]` | SET-ENFORCED |
| BackFace | abilities | `tuple[Ability, ...]` | IDENTITY |
| CardRecord | abilities | `tuple[Ability, ...]` | IDENTITY |
| CardRecord | color_identity | `frozenset[str]` | IDENTITY |
| CardRecord | colors | `tuple[str, ...]` | IDENTITY |
| CardRecord | keywords | `tuple[KeywordAbility, ...]` | SET-R1a |
| CardRecord | subtypes | `tuple[str, ...]` | IDENTITY |
| CardRecord | supertypes | `tuple[str, ...]` | IDENTITY |
| CardRecord | types | `tuple[str, ...]` | IDENTITY |
| Choose | options | `tuple[Effect, ...]` | MENU |
| Cost | parts | `tuple[CostPart, ...]` | SET-R1b |
| CostManaHybrid | colors | `tuple[str, str]` | SET-R1b |
| CostModifier | extra_deltas | `tuple[CostDelta, ...]` | OPERATOR-AUDIT |
| EtBState | initial_counters | `tuple[tuple[CounterKind, Quantity], ...]` | SET-R1a |
| FAnd | children | `tuple[Filter, ...]` | SET-R1a |
| FAtom | colors | `tuple[str, ...]` | SET-R1a |
| FOr | children | `tuple[Filter, ...]` | SET-R1a |
| KeywordAbility | params | `tuple[Quantity | Filter | Cost, ...]` | OPERATOR |
| Selector | zones | `tuple[Zone, ...]` | SET-R0 |
| Seq | steps | `tuple[Effect, ...]` | TIME |
| SpellAbility | additional_costs | `tuple[Cost, ...]` | SET-R1b |
| TokenSpec | abilities | `tuple[Ability, ...]` | IDENTITY |
| TokenSpec | keywords | `tuple[Keyword, ...]` | SET-R1a |
| TokenSpec | subtypes | `tuple[str, ...]` | SET-R1a |
| TokenSpec | types | `tuple[str, ...]` | SET-R1a |
