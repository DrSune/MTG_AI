# ATOM ONTOLOGY — canonical composition of atomized card subcomponents

Status: **BINDING** (4 adversarial gate rounds 2026-10-19, round-4 GO; owner stop
condition met — see §9). Owner directive
2026-10-19: as FEW subcomponents as possible covering everything needed;
functionally-identical wordings MUST land in the SAME atoms in the SAME canonical
order; the combination tree must be standard and predictable. Evidence
(COMMIT-RESIDENT): `tools/audit/ontology_shape_census.py` →
`reports/ontology_census_2026-10-19.json` (546 cards / 1168 abilities / 469 shape
clusters / branching map) + `tools/audit/atom_field_table.py` (V1′ single source:
25-field CLASSIFY) + `tools/audit/atom_sortdelta.py` →
`reports/atom_sortdelta_2026-10-19.json` (R1a byte-delta evidence, N-v4) +
`KNOWLEDGE/2026-10-19/126-*` (digest, gate log, NUMBERS.md volumes). IR: `MTG_bot/core/ability_tree.py` (80 dataclass nodes).
Standing laws operated on, never restated: AGENTS §9 orthogonality, §10 visibility,
§11 zero-loss.

## 0. Consumers
1. **Translation agents (template authors)**: emit canonical shapes; §5 map is the
   menu of approved shapes; T1/O-laws below are diff-gate checklist items.
2. **Adversarial/diff gates**: checker §6 reports violations mechanically.
3. **Model-facing encoding (future)**: IR serialization IS the card tokenizer (§8);
   `canonical_json` (:4670) is the identity path.
4. **Engine**: frozen-IR value equality (goldens, dedup) requires canonicalization AT
   CONSTRUCTION — precedent `AtomArgs.pairs` role-sort (:2541).

## 1. The composition tree

```
card      := CardRecord(abilities+)                       # printed order kept (§3)
ability   := Triggered(event, condition?, effect)
           | Activated(cost, effect, condition?, timing)
           | Static(effect, condition?) | Spell(kind, effect, additional_costs*)
           | Replacement(event, condition?, action) | Keyword | EtBState
           | CostModifier | Emblem | Kicker | BackFace
effect    := Atom(verb, role→value pairs)                 # ONE operation = ONE Atom (T1)
           | Seq(steps 2+)                               # TIME: printed order (O2)
           | Choose(count, options 2+)                   # MENU: printed order
           | OptionalEffect(inner) | Conditional(pred, then, else?)
           | Repeat(count, inner) | EachPlayer(ref, effect) | DelayedTrigger(...)
value     := Quantity | Selector | Filter | Zone | Duration | PtDelta | TokenSpec | LiteralName
selector  := {mode, count, filter, zone∪zones → ONE set (R0), referent}
filter    := FAnd(children) | FOr(children) | FNot(inner) | FAtom(pred, slots)
event     := ZoneChange | CastSpell | … (18 classes, census §5)
quantity  := QConst | QX | QUnbounded | QCount(sel) | QPartyCount(sel)
           | QDistinctColorCount(sel) | QProp | QBin | QThisTurn | QAtLeast | QAtMost
```

Ability = fusion unit: **{when-event} × {gates} × {cost} × {operations}**; operation =
§9 axes {operation, menu, count, effect-of-each-choice} realized ONLY as the
Atom+Selector+Quantity triple — any second encoding is a §4 ledger item.

## 2. Wording-order fusion (owner example → law)

"Deal 2 damage to target creature" ≡ "Choose target creature, deal 2 damage to it":
designation occurs at ANNOUNCEMENT (CR 601.2c spells / 602.2b activated / 603.3a
triggered; 608.2a is a legality re-check only) — never a sequential step. Both
wordings → the SAME single Atom with alphabetical role pairs (:2541).
**T1 (template law)**: "target / each X that… / a creature" phrases become the ROLE
(Selector value) of the Atom they feed — never a standalone node, never a Seq step.
Grammar already type-rejects Selector-as-step (:2609); T1's live anti-pattern is the
SPLIT `Seq[Atom(TAP,{t}), Atom(DAMAGE,{t′})]` for ONE operation → checker V3′.

## 3. Ordering law — COMPLETE field-coverage table (V1′ baseline)

Detection rule (binding, single source `tools/audit/atom_field_table.py` — it
regenerates this table AND the checker's CLASSIFY dict, exiting nonzero on any
UNCLASSIFIED runtime field or STALE dict entry; `/126` carries the table rows):
a CONTAINER field = annotation contains `tuple[` | `frozenset[` | `list[`.
Runtime scan: **25 container fields** = 24 `tuple[` + 1 `frozenset[`
(`CardRecord.color_identity`), 80 classes, zero unclassified.

| class.field | annotation | CLASSIFY | canonical form |
|---|---|---|---|
| Seq.steps | tuple[Effect,…] | **TIME** | printed order preserved, never tool-sorted; Seq[1] forbidden (corpus 0) |
| Choose.options | tuple[Effect,…] | **MENU** | printed order (identity); same-menu/diff-order cross-card pairs ⇒ WARN + MANUAL review (ledger D7: census §B detects flat/nesting only, no menu-order matcher — none observed in 546 cards; build the matcher when a pair actually occurs) |
| CardRecord.abilities / BackFace.abilities / TokenSpec.abilities | tuple[Ability,…] | **IDENTITY** | printed order |
| CardRecord.types/subtypes/supertypes/colors, color_identity(frozenset) | tuple/frozenset | **IDENTITY** | oracle-printed data, membership tests; no sort (fidelity; to_dict sorts color_identity) |
| AtomArgs.pairs | tuple[(role,value),…] | **SET-ENFORCED** | role-sorted at construction — ALREADY ENFORCED :2541 (measured: sorted on every card) |
| FAnd.children / FOr.children | tuple[Filter,…] | **SET-R1a** | construction sort by canonical_json(child) + same-class flatten + single-child unwrap (eval purity gate-verified binding.py:219–236) |
| CardRecord.keywords | tuple[KeywordAbility,…] | **SET-R1a** | grant-membership order-free (keyword_of scans; same-timestamp layers re-order by layer rules) — sort (v3→v4 gate A2: field was MISSING from v3) |
| TokenSpec.types/subtypes/keywords | tuple | **SET-R1a** | COMPILER-EMITTED data, not oracle print (v4 gate A4: canonicalize, not declare divergence) — sort |
| FAtom.colors | tuple[str,…] | **SET-R1a** | filter membership only — sort |
| EtBState.initial_counters | tuple[(CounterKind,Quantity),…] | **SET-R1a** | counter dict keyed by kind; sort |
| Cost.parts | tuple[CostPart,…] | **SET-R1b** | payment order-free (PAYMENT_ORDER legality.py:138) but planning order-keyed (:721 min-clamp, :755 hybrid append, failure-string, witness digest) ⇒ sort ONLY after planning-determinization |
| SpellAbility.additional_costs | tuple[Cost,…] | **SET-R1b** (v4, gate A3) | folds into the SAME order-keyed planner (legality.py:1272 kicker fold → spell_cost → build_payment_plan); corpus Δ0 today only because no multi-entry case exists = untestable landmine if sorted in R1a |
| CostManaHybrid.colors | tuple[str,str] | **SET-R1b** (v4, gate A3) | hybrid_demands raw-tuple-keyed (legality.py:755/887) |
| Selector.zone + Selector.zones | Zone + tuple[Zone,…] | **SET-R0** | **R0 schema fold**: ONE `zones: tuple[Zone,…]` (heterogeneous Zone objects whole), construction sort by canonical_json (Zone is not orderable — bare sorted() TypeError trap), C2 referent convention keeps neutral `Zone(ANY,ANY)`; `Selector.zone` (scalar) deleted; ALL consumers set-iterate; PRIMARY-ZONE-KEYED LANES become ∃-predicates: selectors.py:428-430 (r19b TOP window — lane body :445 must extract the MATCHED LIBRARY+TOP zone's controller, not ∃-test-then-reuse), :484 (16a PLAYER re-point), :705/:754, verbs.py:247-249 (firemaw) |
| KeywordAbility.params | tuple[Quantity\|Filter\|Cost,…] | **OPERATOR** | positional (mode-specific arg slots) |
| CostModifier.extra_deltas | tuple[CostDelta,…] | **OPERATOR-AUDIT** | sum-order presumed free; R1b audit before any SET reclass |
| QBin.left/right, Conditional.then/else, ordinals (CardDrawn, CastSpell), DelayedTrigger slots | scalars/named fields | **OPERATOR** | position IS semantics (field names, not order) |

**O2 (time law)**: Seq order kept because later steps may DEPEND on earlier ones
("for each of those", mid-resolution QProp, later-step legality) and printed order is
card identity (§11). NOT justified by trigger queues: mid-resolution triggers wait
for the next priority pass, relative order = controller choice (CR 603.3b) — hence
independent-step swaps are functional dups with DIFFERENT IR → divergence ledger
(0 swap pairs observed; prior logged, not exploited).
**O3 (set law)**: SET fields sort AT CONSTRUCTION (frozen `__post_init__` +
object.__setattr__, :2541 precedent). No runtime rewriting; `N` below is exactly the
constructor set.

## 4. Fusion ledger (fewest-atoms program; Type-1 gated; one merge per round)

| id | concept | state | decision |
|---|---|---|---|
| F1 | controller direction | **RESOLVED 2026-10-10** (NUMBERS /65: event_direction_field 42/41→0 tripwire, controllers_is 173/121 sole encoding). Today's E1 "×7" was FIELD-LIST overcount. | residual re-audit (cheap, piggybacks R2): verify Zone.controller / QProp.referent / EachPlayer.ref are DISTINCT axes, not surviving direction duplicates |
| F2 | choose-family | Choose fixed-options 28×; SelectorMode.CHOOSE 174×; ONE_OF 25×; REST 10× | ONE axis {op,menu,count}; **emission freeze NOW** (V4′): no NEW compiled CHOOSE pending R3 blindness audit (AGENTS §10) |
| F3 | cost↔effect twins | Cost{Sacrifice,Discard,Tap,PutCounter} vs Verb atoms | R4+, only if §9 similar-effects survives analysis |
| F4 | damage events | CombatDamageEvent vs DamageDealtEvent(combat=T/F), 13 nodes/13 cards | **LANDED R2 /140+142 2026-10-20**: CDE extinct (3 nodes folded, class deleted, journal :2129 preserved); D13 split-over-fire ACCEPTED pin, ZND-8 dedup ticket |
| F5 | optional | OptionalEffect 28× vs Kicker vs QAtMost | OptionalEffect = the may-axis; Kicker = cost-side sugar; review at R3 |
| F6 | count/X family | all in use | NOT duplicates; ZND-1g one-X law stands |
| F7 | life polarity | LifeLost verb-only | symmetric event on first card need |
| F8 | phantom menu | Choose(count==len) | V2′: must be encoded ALL |

Enum-only STRICT variance clusters (SpellKind×5, Keyword×19, PtDelta-direction) =
GOOD generalization (§9) — never fusion targets.

## 5. Branching map (discovered branchings — commit-resident)

Baseline: `reports/ontology_census_2026-10-19.json` §C (Selector 40 branchings,
Choose 4, Conditional 6, OptionalEffect 3, EachPlayer 2, DelayedTrigger 1),
regenerable (`tools/audit/ontology_shape_census.py`, command in NUMBERS.md). Top:
`{choose}{unbounded}{bf ∧ FAnd[2]} ` all-of ×92; CHOOSE ×80; TARGET ×42+37;
`{may}{Atom}` ×28; fixed Choose[2] ×24; verb×role: MODIFY_PT×79, MOVE_ZONE×66,
GRANT_ABILITY×61 — "creature → {destroy|exile|bounce|tap|PT}" = verbs consuming the
SAME Selector shape, one branching per verb, no per-wording re-nesting (2 FAnd-wrapper
anomalies corpus-wide, erased by R1a flatten).
**Registration law**: new branching = map row (dated, card-cited) + NUMBERS.md count
IN THE SAME COMMIT; 1-card rows flagged low-volume (§9).

## 6. Identity + conformance

**Identity law**: byte-equal canonical IR under N := {role-sort :2541; FAnd/FOr
sort + same-class flatten + single-child unwrap; additional_costs + initial_counters
sort; FAtom/CostManaHybrid.colors sort} is a SUFFICIENT same-function proxy; NOT
necessary — semantic dups outside N live in `docs/ATOM_DIVERGENCES.md` (D1–D7: De
Morgan/FNot placement; QAtLeast(1)≡ALL-slot alias; independent Seq swaps RULED
non-fusion; un-distributed FOr[FAnd,FAnd]; zone-twin bytes pre-R0 CLOSED BY R0;
phantom wrappers CLOSED BY R1a; MENU-order RULED review-by-hand).
MEASURED (N-v4 rule set; gate evidence COMMIT-RESIDENT at
`reports/atom_sortdelta_2026-10-19.json`, regenerable via
`tools/audit/atom_sortdelta.py`): N-v4 changes **M21 122/305 + ZNR 80/281** record
bytes — per rule: fand_order 117+72, or_order 9+6, fand_flatten_single 0+2 (Dauntless
Survivor, Negate), kwds_sort 2+0 (Basri's Lieutenant, Sporeweb Weaver),
fatom_colors_sort 1+0 (Quirion Dryad), tokenspec/counters_sort 0. **122 M21 golden
files** flagged (exact list in JSON; every changed card has a golden, 0 missing).
Idempotence PASS both pools; content-preservation PASS (multiset-of-normalized-leaves
+ Atom-node invariants); zero `replace()` resistance; AtomArgs.pairs already sorted on
every card. **PC-6 instrument law (v4, gate P1-5)**: the gate metric is
`tools/measure_grammar.py` (gate metric; PRE re-anchored 2026-10-19 by the gate's own
re-run: M21 orphans **4** / max share **.1265 MOVE_ZONE**; ZNR orphans 26 / .1547
MODIFY_PT — the old M21 1/.1168 ADD_MANA row at NUMBERS:3043 is SUPERSEDED), R1a must
re-run MEASURE_GRAMMAR
pre/post; the census-side `measure_pool` census (4/26) is a PROXY, reported only as
supporting evidence (proxy invariance double-checked by independent verb-fold).

**Checker** `tools/audit/ontology_conformance.py` (read-only pool pass; NEVER via
`walk()` — `_walk_value` :4704 skips lists):
- V1′ FIELD-COVERAGE: the checker IMPORTS the CLASSIFY dict from
  `tools/audit/atom_field_table.py` (single source — same module regenerates the §3
  table); runtime scan per the detection rule (annotation contains `tuple[` |
  `frozenset[` | `list[`); UNCLASSIFIED container field ⇒ ERROR, STALE CLASSIFY entry
  (field gone) ⇒ ERROR — doc/code duplication is structurally impossible (the doc
  table is generated from the module). Detection includes frozenset BY RULE (the
  24-vs-25 counting dispute is closed by the rule, not the count).
- V2′ PHANTOM: Seq[1], single-child FAnd/FOr, Choose(count==len(options)) ⇒ ERROR.
- V3′ SPLIT heuristic (WARN only): two Seq steps carrying BYTE-IDENTICAL fresh
  TARGET-mode Selectors where a later step re-designates — canonical form uses the
  referent-bound selector (C2 convention :1180). EXCLUDES ALL/ONE_OF/REST/referent
  modes (legal identical repeats: independent designations, all-of loops); ships with
  SYNTHETIC TP fixtures (corpus has 0 TPs — unverifiable on this sample, gate A3).
- V4′ EMISSION FREEZE: counts NEW SelectorMode.CHOOSE nodes in the COMPILED-IR diff
  (not template source text — compiler.py:1242/1280/1292 generic lanes emit CHOOSE
  without the token appearing in a template diff, gate A4); whitelist file ships
  with the checker.
- V5′ MAP DRIFT: compiled shape without a §5 map row ⇒ WARN → registration law.

Gate law: template rounds carry checker Δ0 (V1′/V2′/V4′) + Δreview (V3′/V5′).

## 7. Worked examples

```
"Deal 2 damage to target creature" ≡ "Choose target creature, deal 2 damage to it"
  → Atom(DEAL_DAMAGE, {amount:QConst(2), target:Selector(TARGET,creature…)})  # ≡ bytes
"Search your library and graveyard for a land" ≡ "…your graveyard and library…"
  → PRE-R0: zone-key wording forks (NOT yet canonical — R0 fixes);
    POST-R0: Selector(zones=sorted{GRAVEYARD,LIBRARY} as Zone objects) byte-equal.
"Deal 3 damage to target creature, then draw a card" vs swapped wording
  → Seq[A,B] vs Seq[B,A]: DIFFERENT IR — independence undecidable at compile time;
    logged as KNOWN divergence class (O2), never tool-normalized.
"Destroy target creature. Draw a card." (one ability) vs two triggered abilities
  → different abilities (event differs) — ontology fuses WORDINGS, not mechanics.
```

## 8. Rollout (Type-1 gated; every prediction pre-registered MEASURED; deviation = finding)

- **R0 (gated, sequenced AFTER live sibling executor wave)**: zone∪zones → single
  `zones` schema fold. MIGRATION SURFACE (gate A1, enumerated): ~64 non-test
  `zone=` constructor sites; positional `Selector(count, mode, filter, zone)` at
  compiler.py:1050 (fold silently MIS-SLOTS args — must be edited in the same pass);
  engine-synthesized `Selector(zone=…)` at binding.py:759; ~111 test assertions on
  `.zone.kind/.controller/.position`; lane #1 body (selectors.py:445) must extract
  the MATCHED LIBRARY+TOP zone's controller (heterogeneous zones: an ∃-test that
  passes on a zone you then don't use is a silent rules change). Candidate
  ENUMERATION order changes for multi-zone selectors (query.py:1127 → offered slot
  order): R0 pre-registers OFFER-ORDER diffs in pack expectations, not only goldens.
  ∃-predicate rewrites: selectors.py:428-430/:484/:705/:754, verbs.py:247-249, each
  with an EXECUTOR-OBSERVED falsifier (r19b window, Taunter re-point, firemaw guard)
  per compiled≠executing law; golden re-baseline count MEASURED at R0 spec time
  (sortdelta rerun with the zone-fold rule).
- **R1a**: constructor sorts per §3 SET-R1a rows + checker V1′/V2′/V5′ + V4′ freeze.
  PRE-REGISTERED (measured N-v4, committed JSON): M21 **122** records + **122**
  golden files re-baseline (E1-merge/65 builder-recompute procedure, per-card
  audited, shared-regex law /115); ZNR **80**; PC-1/PC-2/PC-8 Δ0 (permutation-only
  N: idempotence + leaf-multiset invariants measured); PC-6 via `measure_grammar`
  instrument pre/post (gate metric; PRE: M21 1/.1168 ADD_MANA, ZNR 26/.1547
  MODIFY_PT); fuzz 40/40 + packs Δ0 expected (filter eval commutative).
- **R1b**: planning determinization (failure-string, witness digest, hybrid append) →
  THEN Cost.parts sort + KeyModifier.extra_deltas audit; pre-register offer/PC-2
  deltas at spec time.
- **R2**: F4 damage fold + F1 residual re-audit.
- **R3**: F2 silent-CHOOSE blindness audit (174 cards, §10) → freeze lift or redesign;
  **STATUS 2026-10-20: R0/R1a/R1b/R2/R3 ALL LANDED (/132,/127,/139,/142,/144). Remaining: R3b phantom-fold (L-A 161 nodes -> no-decision encoding, D12), R4 twins GATED on similar-effects census, up-to-N gap (QConst mis-encode), engine defers ZND-7/8/9**
  F5 optional review.
- **R4+**: F3 twins iff §9 similar-effects survives.
Census re-run = every round's exit gate (map drift Δ0); numbers → NUMBERS.md.

## 9. Gate log
- R1 (adversarial): FIX-THEN-GO — 8 findings; resolutions in v2 (see /126).
- R2 (adversarial): FIX-THEN-GO — N5 fold REJECTED (primary-zone lanes FATAL, all
  verified in code); evidence paper-claim executed; V3′ mode-exclusions + fixtures;
  V4′ compiled-IR scope; F1 corrected to RESOLVED-2026-10-10 (E1/65) — "direction×7"
  was a field-list overcount.
- R3 (adversarial): FIX-THEN-GO, residue = ONE material class (§3 table defect) +
  bookkeeping. Verified R2-fixes 2/4/5/7/8 executed; F7 RECURRED for the R1a
  evidence itself (JSON/generator in /tmp) → v4 commits `tools/audit/atom_field_table.py`
  + `tools/audit/atom_sortdelta.py` + `reports/atom_sortdelta_2026-10-19.json`;
  A2 FATAL: v3 table MISSED CardRecord.keywords + detection rule unspecified
  (24-vs-25 counting dispute) → v4: rule = annotation contains tuple[|frozenset[|
  list[; 25 fields; single-source module emits table + checker dict with drift-fail.
  A3 MAJOR: additional_costs + CostManaHybrid.colors are the SAME order-keyed
  planner (legality.py:1272 fold verified) → reclassified SET-R1b. A1: R0 migration
  surface enumerated (positional Selector@compiler.py:1050, 111 test asserts,
  lane-body :445 extraction, offer-order diffs). A4: TokenSpec containers → SET-R1a
  (compiler-emitted, canonicalize not diverge). PC-6 instrument law (measure_grammar
  = gate metric; measure_pool = proxy). N-v4 measured: M21 122 / ZNR 80, 122 goldens.
- R4 (adversarial): **GO** — all r3 fixes verified ON DISK (module run exit 0,
  doc↔module token agreement 25/25, JSON numbers match); keyword-sort safety proven
  by measured 0 same-name keyword groups in 586 cards + membership/any-veto consumer
  shapes (layers.py:974 sorted(set(names)), legality.py:1779/476); R0/R1a byte-delta
  separability holds (no R1a sort key embeds Selector.zone). Owner stop condition
  MET (no material class; residue bookkeeping). Advisories executed pre-binding:
  /126 carries the generated table (27 rows), DIVERGENCES ledger file created
  (D1–D7), PC-6 PRE re-anchored (M21 4/.1265 MOVE_ZONE), MENU WARN declared
  manual-review (D7, no phantom matcher cited).
- R5 round 1 (adversarial, 2026-10-29): **NO-GO as written / FIX-THEN-GO.**
  - GO with fixes: R5-1, R5-3, R5-4, R5-6. Redesign: R5-2, R5-5, R5-7. Rejected: R5-8.
  - Main findings:
    - absent duration is Permanent for other verbs, so CAST would be context-dependent;
    - Handles survive zone moves, so 400.7 needs journal provenance;
    - returning Auras need an enchant choice;
    - the one-shot cast lane is broken;
    - phasing breaks the can't-phase-in prevention;
    - copies need a value shared with the Clone family;
    - activation locks need a required kind;
    - the engine has no legend rule.
  - v2 in §10 answers every finding. Round 2 is pending.
- R5 round 2 (adversarial, 2026-10-29): **NO-GO as written.**
  - R5-1: FIX-THEN-GO for the second time. R5-3, R5-4, R5-6: GO.
  - Withdrawn: `DurationUntil(event)` (turn-structure twins, referent anchors); EXILED_BY_SOURCE,
    which duplicated IS_EXILED_WITH_SOURCE; PHASE_OUT `duration` (§9 ii, 610.4); the GRANT_ABILITY
    replacement route (grants are never read by replacements).
  - Required: 608.2g deferred resolution; a 605.1a classifier; a layer-1 copy; a pre-registered blast
    radius; a committed census generator.
  - R5-1 and R5-6 are implemented with the round-2 fixes. v3 in §10; round 3 is pending.
- BINDING STATE: rounds 1–4 complete; further ontology changes require a NEW gated
  round (any R-item that reclassifies a field or opens a normalization is Type-1).

## 10. Round R5 — durations, permissions, copies (v3 after gate round 2, 2026-10-29; gate round 3 pending)

Owner, 2026-10-29: "Fix the remaining M21 pool to be castable and playable, and mapped properly",
and on B-60c: go ahead "if you have good arguments for the design ruling, and an adversarial pass
doesnt break it". Gate rounds 1 and 2 are logged in §9. **Every census count here comes from
`tools/audit/r5_census.py`** (regex screen over the 19 set files, unique names;
`reports/r5_census_2026-10-29.json`).

### Status
| Item | State |
|---|---|
| R5-1 `duration` on MOVE_ZONE (B-60c) | FIX-THEN-GO in rounds 1 and 2; **in implementation** with every round-2 fix (lane `engine/r5a-until-leaves`) |
| R5-6 `actor` on TargetingEvent | GO in rounds 1 and 2; **in implementation** (same lane) |
| R5-3 `lands`, R5-4 `new_targets` | GO in round 2; they land with R5-2 and the COPY handler |
| R5-2, R5-5, R5-7, R5-8, R5-10, R5-11, R5-12 | v3 below, for gate round 3 |
| v2's `DurationUntil(event)`, `EXILED_BY_SOURCE`, PHASE_OUT `duration`, `GRANT_ABILITY(ReplacementAbility)` route | withdrawn (round 2) |

### R5-1 as implemented (for the record)
- **Role.** `MOVE_ZONE.duration` accepts only `DurationUntilLeaves`, `DurationEot` or
  `DurationUntilNextTurn`.
- **`DurationUntilLeaves` is kept**, meaning exactly "until the anchor leaves the battlefield". Phasing
  out does not end it (702.26d). A future "for as long as ~ remains" (611.2b) needs its own field,
  because phasing ends that one (702.26f).
- **Return registry.** It is part of state and the fingerprint, and it is visible in the per-seat view
  and the probe (§10).
- **400.7** is decided from journal provenance.
- **610.3a–d** are followed. Returns go through replacement effects (614). A returning Aura's owner
  chooses its host (303.4f/g).

### R5-2 v3 PERMIT_CAST, and the one-shot CAST lane
The v2 shape stands: CAST stays one-shot (608.2g), PERMIT_CAST is the permission. Its roles are
`source`, `additional`, `alternative`, `count`, `lands`, `duration`. Round 2's fixes:
1. **Canonical source.**
   - A non-target designation is `Selector(mode=ALL, count=QUnbounded)` by construction.
   - `count`, the number of casts allowed, is never QUnbounded. Absent means each designated object
     once.
   - Example: Idol is `count=QConst(1)`; Snoop has no count.
2. **One static convention, checked at the ability level.** A checker in the compiler and in
   `tools/audit` enforces it.
   - PERMIT_CAST and REVEAL inside static abilities, emblems and granted statics carry no duration:
     they last while the ability functions (611.3a). The 6 static REVEAL atoms drop
     `DurationPermanent` (6 goldens).
   - Inside spell, activated, triggered and delayed effects, PERMIT_CAST requires a duration.
3. **"For as long as it remains exiled"** (4 cards in 4 sets) is `DurationPermanent` on designated
   objects. An object's entry ends when the object leaves its zone (400.7). `DurationWhileCondition`
   is rejected inside permissions.
4. **Anaphora.**
   - "Cards exiled this way", "them" and "that card" are the ability's `result` register.
   - "Cards exiled with ~" is the linked set (`IS_EXILED_WITH_SOURCE`, R5-8).
   - Chandra, Heart of Fire's templates read the union of both today (`templates_b4.py:1130-1160`).
5. **Functioning zones.**
   - A card's own "you may cast this card from [zone]" functions everywhere (113.6f).
   - An emblem's permission functions in the command zone (113.6p).
   - Every other permission functions on the battlefield.
6. **Options.** A cast option is identified by (object, cost path). Several permissions offering the
   same cost path for the same object give one option, which consumes one use. No duplicate options
   (§10).
7. **608.2g.**
   - A spell cast while another resolves is put on the stack, and it resolves after the parent
     finishes. Today it resolves inline (`stack.py:1034-1166`).
   - It pays its additional costs (601.2f; lane vfix3), and X is 0 when no mana cost is paid (107.3b).
   - A rider such as Chandra, Flame's Catalyst's attaches to the spell object (R5-12).
8. **No permission-like atom is wrapped in OptionalEffect.** That covers PERMIT_CAST,
   GRANT_ACTIVATION and ADD_LAND_PLAY, so Teferi, Master of Time's wrap goes: it was a phantom ask.
9. **The free-row idiom is retired.** Lane F already has Azusa, Basri's Aegis and Liliana's Scorn.

### R5-5 v3 `CopyOf`, and layer-1 copy
- **Value.** `CopyOf(source: Selector, exceptions: tuple[CopyException, ...] = ())`, typed and
  classified in the §6 field table.
  - `CopyException` is an empty union for now: no M21 card needs one. 9 of the 21 token-copy cards do,
    and they go in the gap ledger.
  - The 9 "enters as a copy" cards will reuse the value.
- **Engine.**
  - Layer-1 copiable values (707.2, 613.1a).
  - The designation planner descends into values to find TARGET selectors (601.2c).
  - A copy is never cast: no CAST row, so Double Vision's ordinal and cast triggers do not count it
    (707.10).
  - An unchanged copy target still journals TARGETING.

### R5-7 v3 `AbilityActivatedEvent`, and one 605.1a classifier
- **One core predicate, `is_mana_ability`** (605.1a: no target, could add mana, not loyalty). Every
  driver uses it (`games.py`, `bench/router.py`).
- **`kind`** ∈ {ANY, NON_MANA, LOYALTY}, required. LOYALTY means the cost has a CostLoyalty part,
  including [0], which becomes expressible as `CostLoyalty(delta=0)`.
- **The prohibition gate sits in `ability_playable`.** A lock of kind ANY also binds the B-90 payment
  witness, which must skip locked mana abilities.
- **Journal.** One row per activation, mana included, so every replay fingerprint shifts once. That is
  declared in the blast radius.
- **Gap ledger:** boast.
- **Census:** 2 + 10 locks.

### R5-8 v3 Furious Rise, and provenance on the existing linked-exile predicate
- **Provenance.** The existing `FAtomPred.IS_EXILED_WITH_SOURCE` (`ability_tree.py:656`) gains it, and
  there is no new predicate. It is true when the object's current stay in exile began with a move made
  by an ability of this source, and the source is still the same object (its battlefield-entry clock,
  400.7).
  - Idol's permission uses it, and so do Rona and Valki.
  - Census: 20 cards in 15 sets.
  - Emblem sources (Tibalt, 607.1d) go in the gap ledger.
- **New duration `DurationUntilEndOfNextTurn`.** It expires in the cleanup step of the effect
  controller's next turn. Census: 8 cards in 7 sets, including Teferi, Timeless Voyager and Escape to
  the Wilds. It closes the "until the end of your next turn" ledger.
- **Furious Rise** = `PERMIT_CAST(source=result, lands=True, duration=DurationUntilEndOfNextTurn)`.
  This is an approximation, divergence D15.
  - The printed window ends when the next card is exiled, normally at your next end step, so it covers
    the same main phases.
  - It is weaker when the end-step condition fails, because the printed permission would continue.
  - It is stronger only when the trigger is copied, by Strionic Resonator, which is not in the pool.
  - A duration that ends on an event would be a single-card node (§9 ii).

### R5-9 v3 Teferi, Timeless Voyager stays weaker than printed
"They can't phase in" would need a phasing event used by one card in 19 sets (§9 ii). Its creatures
phase in at their controller's next untap step. That is weaker than printed, recorded as D16 and in
BACKLOG B-75.

### R5-10 v3 Stack objects say what they are
- **Encoding.** `FAtom(STACK_KIND_EQ, string_value ∈ {SPELL, ACTIVATED, TRIGGERED})`, a closed
  vocabulary in an existing slot.
- **Abilities never sit on the stack in this engine** (registered as an engine gap). A mode that
  targets an ability is unsatisfiable, so it is never offered.
- **"Counter target spell"** gets SPELL: 39 cards in 19 sets, which re-bake. Referent counters ("that
  spell or ability") are exempt.
- **Engine.** The counter window accepts Choose-based counterspells (`stack.py:572`), for Sublime
  Epiphany's mode 1.

### R5-11 v3 `TokenSpec.colors`
A sorted tuple, validated against {W, U, B, R, G}. Census: 7 multicolored-token cards. 27 M21
TokenSpecs re-bake.

### R5-12 Resolving replacement effects: `Verb.REPLACE` (replaces v2's GRANT route)
- **Shape.** `REPLACE(event: EventSpec whose subject is the designated object, instead: Effect,
  duration: Duration | absent)`.
  - At resolution it creates a replacement effect (614.1a) for its duration, bound to the designated
    object.
  - When that object changes zones the record is pruned (400.7). With the duration absent, that pruning
    is how it ends.
- **Mappings.**
  - Scorching Dragonfire = `Seq(DEAL_DAMAGE 3, REPLACE(ZoneChangeEvent(BATTLEFIELD → GRAVEYARD, subject
    = that target), instead=MOVE_ZONE(exile), duration=DurationEot))`.
  - Chandra, Flame's Catalyst's −2 rider = `REPLACE(ZoneChangeEvent(STACK → GRAVEYARD, subject = the
    cast spell), instead=MOVE_ZONE(exile))`.
- **One encoding.** The card-level ReplacementAbility of resolving text (`stack.py:927`) is retired.
- **Engine.** The replacement registry consults REPLACE records. DESTROY and SACRIFICE consult
  dies-replacements (B-72).
- **Census:** 11 resolving "exile it instead" cards in 7 sets.

### Engine work on existing components (same round)
- "Choose one or more" = `Choose(count=QAtLeast(1))`.
- Double Vision's ordinal counts only matching casts.
- Furious Rise's intervening-if becomes an existence check (lane vfix, V11).

### Blast radius, pre-registered
| Item | M21 goldens expected to change |
|---|---|
| R5-1 | 2 (Freebooter, Idol) |
| R5-2 | about 16: Snoop, Radha, Demonic Embrace, Furious Rise, Idol, both Chandras, 6 static REVEAL atoms, CAST cost-role rows |
| R5-5 | 1 (Sublime Epiphany) |
| R5-7 | Faith's Fetters, and Keral Keep Disciples (ORI) |
| R5-10 | the M21 counterspells |
| R5-11 | about 20 token makers |
| R5-12 | 2 |

- **Total:** about 50–70 of 305 M21 goldens. Every diff is proven field by field in its commit.
- **Fingerprint consumers that shift:** `bench/duel.py`, `tools/search`, traces, and the puzzle
  re-certification. That is an era-boundary change.
- **Packs to re-baseline in the same commits:** conspicuous_snoop, furious_rise_activation, idol, both
  kitesail packs, radha, demonic_embrace, faiths_fetters, warden.
- **Divergences to add to `docs/ATOM_DIVERGENCES.md` when the items land:**
  - D15: Furious Rise's window;
  - D16: Teferi, Timeless Voyager;
  - D17: Liliana, Waker of the Dead's check order (lane vfix2).
