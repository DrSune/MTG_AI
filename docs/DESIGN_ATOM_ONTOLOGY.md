# ATOM ONTOLOGY — canonical composition of atomized card subcomponents

> **Note, 2026-11-06.** Still binding. `tools/audit/atom_sortdelta.py` and `tools/measure_grammar.py`,
> cited as evidence instruments below, were deleted on 2026-11-05 (`git show dbd6e9d:<path>`); their
> reports stay in `reports/`. Line citations are to the commit of each round.

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
ability   := Triggered(event, condition?, effect, once_per_event?)  # absent: once per occurrence (CR 603.2c)
           | Activated(cost, effect, condition?, timing)
           | Static(effect, condition?) | Spell(kind, effect, additional_costs*)
           | Replacement(event, condition?, action) | Keyword
           | EtBState(tapped, counters*, condition?, effect?)  # "As ~ enters" (CR 614.1c); effect: CHOOSE_NAME only, until tested
           | CostModifier | Kicker | BackFace
effect    := Atom(verb, role→value pairs)                 # ONE operation = ONE Atom (T1)
           | Seq(steps 2+)                               # TIME: printed order (O2)
           | Choose(count, options 2+)                   # MENU: printed order
           | OptionalEffect(inner) | Conditional(pred, then, else?)
           | Repeat(count, inner) | EachPlayer(ref, effect) | DelayedTrigger(...)
value     := Quantity | Selector | Filter | Zone | Duration | PtDelta | TokenSpec | EmblemSpec | LiteralName
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
Runtime scan: **27 container fields** = 26 `tuple[` + 1 `frozenset[`
(`CardRecord.color_identity`), 80 classes, zero unclassified (R5-11 added `TokenSpec.colors`;
round 6, pending, `EmblemSpec.abilities`).

| class.field | annotation | CLASSIFY | canonical form |
|---|---|---|---|
| Seq.steps | tuple[Effect,…] | **TIME** | printed order preserved, never tool-sorted; Seq[1] forbidden (corpus 0) |
| Choose.options | tuple[Effect,…] | **MENU** | printed order (identity); same-menu/diff-order cross-card pairs ⇒ WARN + MANUAL review (ledger D7: census §B detects flat/nesting only, no menu-order matcher — none observed in 546 cards; build the matcher when a pair actually occurs) |
| CardRecord.abilities / BackFace.abilities / TokenSpec.abilities / EmblemSpec.abilities | tuple[Ability,…] | **IDENTITY** | printed order |
| CardRecord.types/subtypes/supertypes/colors, color_identity(frozenset) | tuple/frozenset | **IDENTITY** | oracle-printed data, membership tests; no sort (fidelity; to_dict sorts color_identity) |
| AtomArgs.pairs | tuple[(role,value),…] | **SET-ENFORCED** | role-sorted at construction — ALREADY ENFORCED :2541 (measured: sorted on every card) |
| FAnd.children / FOr.children | tuple[Filter,…] | **SET-R1a** | construction sort by canonical_json(child) + same-class flatten + single-child unwrap (eval purity gate-verified binding.py:219–236) |
| CardRecord.keywords | tuple[KeywordAbility,…] | **SET-R1a** | grant-membership order-free (keyword_of scans; same-timestamp layers re-order by layer rules) — sort (v3→v4 gate A2: field was MISSING from v3) |
| TokenSpec.types/subtypes/keywords | tuple | **SET-R1a** | COMPILER-EMITTED data, not oracle print (v4 gate A4: canonicalize, not declare divergence) — sort |
| TokenSpec.colors | tuple[str,…] | **SET-R1a** | R5-11 (replaces the scalar `color`): the token's colour set, WUBRG letters sorted in WUBRG order (CR 105.1), omitted when colourless |
| FAtom.colors | tuple[str,…] | **SET-R1a** | filter membership only — sort |
| EtBState.initial_counters | tuple[(CounterKind,Quantity),…] | **SET-R1a** | counter dict keyed by kind; sort |
| Cost.parts | tuple[CostPart,…] | **SET-R1b** | payment order-free but planning order-keyed (:721 min-clamp, :755 hybrid append, failure-string, witness digest) ⇒ sort ONLY after planning-determinization |
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
| F9 | the CR 609.4 policy family | MANA_POLICY, DAMAGE_ASSIGN_POLICY, ATTACK_POLICY (round 4) | fold candidate: before a fourth policy verb (nine "as though it had flash" cards wait), decide one POLICY verb with a scope enum |
| F10 | CR 110.5 status-change events | TapStateEvent, PhasingEvent (round 4; one card) | one family: fold when a third status event appears |

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

| registered | branching | cards | volume |
|---|---|---|---|
| 2026-11-12, gate round 5 | MOVE_ZONE x `arrange` ("RANDOM": "put the rest on the bottom of your library in a random order"; absent = the owner arranges, CR 401.4), accepted only where `ability_tree.orders_a_library` holds | M21 Garruk's Harbinger (compiler, B5b-rest-bottom-random); M20 Drawn from Dreams and Brightwood Tracker (records) | **low-volume**: 1 compiled card, 2 records (NUMBERS.md 2026-11-12); 54 cards of the 19 sets print "in a random order", most still unparsed |
| 2026-11-12, gate round 6 | Conditional `then:DelayedTrigger` ("<step>. When you do, Y": the "if you do" gate, CR 118.12, around a reflexive trigger, CR 603.12), accepted only where `ability_tree._reflexive_misplaced` holds (§11 R6-1) | M21 Tolarian Kraken (compiler, B2b-do-tap-or-untap); M20 Cavalier of Night and Sorin, Imperious Bloodlord (records) | **low-volume**: 1 compiled card, 2 records (NUMBERS.md 2026-11-12, trigger timing); 22 reflexive sentences on 21 cards of the 19 sets, 19 unparsed |
| 2026-11-12, gate round 6 | DelayedTrigger `reflexive` (`duration` and `event` both absent, no `condition`, no `once_per_event`) | the same three | the same; `reports/ontology_census_2026-11-12_triggertiming_post_full.json` |
| 2026-11-12, gate round 7 (pending) | GET_EMBLEM x `emblem` (EmblemSpec: the emblem's abilities) x `controller` (who gets it: YOU, ALL_OPPONENTS, TARGET_OPPONENT; CR 114.2) | M21 Basri Ket, Garruk, Unleashed, Liliana, Waker of the Dead, M19 Ajani, Adversary of Tyrants (compiler, `compiler._emblem_sentences`); M20 Mu Yanling, Sky Dancer and FDN Vivien Reid (records) | 6 trees, all `controller` YOU; 24 emblem texts in the 19 sets (26 entries), 20 of the 26 sentences that make one unparsed (NUMBERS.md 2026-11-13) |
| 2026-11-12, gate round 7 (pending) | MOVE_ZONE x `cards` ALL over the top of a library: the cards of the open look window that pass the filter ("put all Goblin cards revealed this way into your hand"), the window's REST after it | M20 Goblin Ringleader (record) | **low-volume**: 1 record; 4 cards print "all ... revealed this way ... and the rest" (ORI Sylvan Messenger, M14 Garruk, Caller of Beasts, KHM Alrund unparsed) |

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
- R5 round 3 (adversarial, 2026-10-30): **NO-GO as written / FIX-THEN-GO**
  (`scratchpad/adv3/report.md`, findings carried into the lanes).
  - GO, now being implemented in lane `engine/r5b-go-items`:
    - R5-9 (Teferi, Timeless Voyager stays weaker, D16);
    - R5-11 (`TokenSpec.colors`);
    - R5-7, with 605.1a exact and the census fixed;
    - R5-10, with a closed `string_value` vocabulary and a visible counter-window mode ask;
    - `Choose(QAtLeast(1))`;
    - Double Vision's ordinal.
  - Fix, then a short round 4:
    - R5-2: singleton-source twins; live zone-scoped sources (611.2c); a target and X channel on
      effect casts; 608.2g needs pending frames drained after every resolution site; a cost-path
      token grammar; the duration checker in each Ability `__post_init__`;
    - R5-5: copiable values must feed the legend rule;
    - R5-8: D15 is also stronger inside the end step; provenance by last-known incarnation;
      DurationUntilEndOfNextTurn is defined by the controller's next turn;
    - R5-12: Dragonfire must use CreatureDiesEvent; every replacement consult site to be listed;
      a 616 policy; riders live on the permission entry.
  - R5-13 (FIRST_MATCH): REJECTED. Redesign as `REVEAL.until`.
  - The blast radius must be generated by a script.
- R5 round 4 (adversarial, 2026-11-12; one reviewer on the three branches of the card backlog's
  wave 1, based on c8c94c2): **FIX-THEN-GO, no FATAL.**
  - **GO:**
    - `EtBState.effect`, "As ~ enters" (CR 614.1c, 614.12a), for Runed Halo. It is the only
      compiled "As ~ enters" in 19 sets; about 40 are unparsed.
      - It is restricted to CHOOSE_NAME until another card brings its own tests.
      - The choice is made at the atom boundary just after the move. That cannot be observed for
        the Halo; accepted.
    - The removal of a trigger with no legal player target (CR 603.3d), with the CR 608.2b
      re-check. Eight triggers reach that branch, all printing "target player/opponent".
    - `Verb.ATTACK_POLICY` (CR 609.4, 702.3b) for Drowsing Tyrannodon (6 cards print the clause).
    - `REVEAL.until` (round 3's redesign of FIRST_MATCH), and the referent Selector for "its
      controller". That Selector is byte-identical to the majority form on five verified cards.
  - **FIX-THEN-GO, fixed before the merge:**
    - `once_per_event` (R5-14). The validator refused only False and a damage event with no
      source. So the flag on an IS_SOURCE or IS_ATTACHED_TO_SOURCE attack trigger was a second
      byte form, and on non-combat damage it was a flag nothing groups. Both are refused now.
      Granted triggers are checked as they queue, and the "forgot the flag" mutant is critical.
    - Teferi's -8: IS_RESULT is allowed only in Filter roles that cannot take a referent
      Selector, and raises without a register. GAIN_CONTROL refuses a duration the control
      registry cannot expire.
  - **R5-9 / D16 superseded (accepted).** Round 3's revisit condition, a second "can't phase in"
    card, was not met: there is 1 in 19 sets. The reversal stands on four arguments:
    1. The old tree was a phantom prevention over ZoneChange(COMMAND→BATTLEFIELD): familiar but
       false tokens on a card in a trained set (AGENTS §10-§11).
    2. "Can't untap" and "can't phase in" now share atoms in the same canonical order. Both use
       the Frost Breath family's PREVENT_EFFECT(condition, StatusEvent(filter), duration).
    3. IS_RESULT is the filter spelling of the gated `result` anaphora (R5-2 v3), not a duplicate
       of the CR 607 linked set IS_EXILED_WITH_SOURCE.
    4. DurationUntilEndOfNextTurn is R5-8's duration, approved in round 3 and defined by its
       controller's next turn.
  - **D18 stays OPEN.** "Its controller" has two encodings. Massacre Wurm is the last
    TARGET_PLAYER antecedent, and its fold to `Selector(referent="event")` is scheduled in
    BACKLOG. Until then, MAPPER_GUIDE says "its controller" and "that player" are a referent
    Selector, never TARGET_PLAYER, and a conformance test flags TARGET_PLAYER on a card whose text
    names no target player.
  - **Blast radius** (generated by script; it matches the authors):
    - R5-14 changes six trees: M21 Feline Sovereign, Basri Ket*, Tide Skimmer* and Mangara; FDN
      Battlesong Berserker and Ancestor Dragon*. The starred cards were verified and are
      re-verified before any run pins this code.
    - Branch 2 changes three: Transmogrify, Teferi, Timeless Voyager and Drowsing Tyrannodon.
    - Branch 3 changes one: Runed Halo.
    - Verified cards that play differently with unchanged bytes:
      - the Falconer Adept and Skyknight Vanguard tokens get no declare row (CR 508.4), and
        Makeshift Battalion counts only declared attackers;
      - Vito, Kitesail Freebooter, Teferi's Tutelage and Sage's Row Denizen fall under the 603.3d
        removal and the 608.2b re-check.
    - Replay fingerprints of games with those tokens shift.
- R5 round 5 (adversarial, 2026-11-12; one reviewer on 31c7c2f0, MOVE_ZONE `arrange`):
  **FIX-THEN-GO.**
  - **Upheld:** the name `arrange`; its home on MOVE_ZONE (not a Zone field); the one value
    "RANDOM"; and absent = the owner arranges (CR 401.4: "in any order" restates the rule, as
    `once_per_event` absent is CR 603.2c's default). "In a random order" is the commoner wording
    (54 cards of the 19 sets to 22), but the absent value is the rule's.
  - **MAJOR, fixed:**
    - M1. The validator accepted `arrange` where it means nothing, a second encoding (round 4
      refused the same for `once_per_event`): on a one-card TARGET move, the designation lane
      (`target`, which never reads it), the mill lane (`pop_order` TOP) and a library with no
      position. One predicate, `ability_tree.orders_a_library`: a library TOP or BOTTOM; the
      objects on `cards` (the hand lane's `from` HAND included); no `pop_order`; a selector that
      can hold several cards (REST or ALL, a count that allows two, or a referent). It refuses the
      role in `Atom.__post_init__`, and G3's library-order mutants use it (they had left out
      referents, which the executor orders). The move of a one-card look's result (Garruk, Savage
      Herald's +1) is a dead role for G3 (`gates._one_card_result_moves`). Tests:
      `test_arrange_is_random_only_and_only_where_several_cards_go_into_a_library`, one refusal
      per case; `test_gates.py::test_library_order_mutants_only_where_several_cards_go_to_a_library`.
    - M2. G3's critical "zone LIBRARY->GRAVEYARD" mutant of every RANDOM move was stillborn, so
      the three random cards lost it: the swap now drops `arrange` with the library. Test:
      `test_a_random_order_keeps_its_zone_mutant` (Garruk's Harbinger).
    - M4. The network could not see which end it orders (AGENTS §10). The rig parses
      `arrange:<owner>:<END>:<n>` into AskContext (`picked` = n, `end`), and one appended glob
      column, `features.G_TOP`, reads 1 for the top (model.load zero-fills it; ASK_KINDS and every
      other column keep their index). Test: `test_an_arrange_ask_says_which_end_of_the_library`.
    - M3. Tale's End's spec pack activated Brightwood Tracker, whose record is no longer applied:
      re-verified on main on another activated ability (tale's_end_5, Soulmender).
  - **MINOR, fixed before any network trains on the kind:**
    - m1: asked top first at both ends, as the trigger ask asks first what resolves next and
      mulligan_bottom's first pick ends highest; m2: identical cards (one oracle id) are one
      option, as the trigger ask's copies are; m3: owners asked in APNAP order (CR 101.4).
    - m4: a tripwire. A move whose cards its controller picked from a look at another player's
      library or hand raises (Agonizing Memories: by its text the controller orders them, not the
      owner); no card in the 19 sets does it.
    - m6: tests for the hand lane (Cavalier of Gales), a two-owner move, that RANDOM permutes, and
      the router's context line. m9: each RANDOM move draws its own stream (one tag shuffled two
      moves of one operation alike); the pool numbers corrected to main's (M21 270 -> 269, M20
      257 -> 255, FDN 175).
    - m5: D19 registered in ATOM_DIVERGENCES (no position means both "on the bottom" and "shuffle
      into"), no code. m7, m8 (re-probing Anticipate, Stormwing Entity and Track Down; re-writing
      the two M20 records through `cardtool try --write`) are the coordinator's re-verification.
  - **Blast radius** (by script): 3 of 5,678 trees change, all verified and all "in a random
    order" (M21 Garruk's Harbinger, M20 Drawn from Dreams, Brightwood Tracker), and wait for
    re-verification. Behaviour: an `arrange` ask on See the Truth, Anticipate, Cavalier of Gales and
    Goblin Ringleader ("in any order"), and on a scry of two or more that keeps two in one group
    (verified: Stormwing Entity, Track Down).
- R6 round 6 (adversarial, 2026-11-12; one reviewer on f0e40d80 and c4139ff8, trigger timing,
  §11): **FIX-THEN-GO**, nothing FATAL: R6-1's shape and R6-2's rule stand, with these fixes
  (branch `worktree-agent-aa162b11b742a5790`, main bc0d4606 merged first, 989707d7).
  - **MAJOR, fixed:**
    - M1. `_reflexive_misplaced` checked only "the then_effect of some Conditional". It accepted a
      gate on TYPE_EQ, CONTROLLER_COUNT_GE or FNot(MAY_DONE); a MAY_DONE gate with no step before
      it; the gate under EachPlayer (run by the reviewer: the reflexive trigger was queued under
      player:1 and "you gain 3 life" went to the opponent, as the executor rotates ctx.controller
      under EachPlayer while CR 603.7e gives it the resolving ability's controller); under Repeat;
      in a static ability's effect, which never resolves. Now a reflexive trigger stands only as
      the then_effect of exactly Conditional(FAtom(MAY_DONE)) after a step of a Seq, in the
      effect of a spell, activated, triggered or delayed ability (granted, token and reflexive
      ones too), with no EachPlayer or Repeat between, and never in a static, replacement,
      enters-with or emblem ability (`ability_tree._reflexive_misplaced`; "when you don't" waits
      for a card). Tests in `MTG_bot/core/test_executor_trigger_timing.py`:
      `test_a_reflexive_trigger_anywhere_else_is_refused` (15 cases; 989707d7 accepts 13 of
      them), `test_an_emblem_record_holds_no_reflexive_trigger`, and
      `test_a_reflexive_trigger_stands_where_it_means_one_thing` for the accepted shapes.
    - M2. `check_trigger_timing` was one-sided: more conditions than intervening "if"s, and a
      compiled sentence starting "When you do" with no reflexive node. It missed an intervening
      "if" written into the event filter, a reflexive node on a card that prints none, and "when
      they do" or "when ... this way". `trigger_timing_faults` now compares, over the compiled
      sentences and both ways, reflexive triggers with reflexive sentences
      (`ontology_conformance.REFLEXIVE_WORDING`, which census.py imports) and trigger conditions
      with intervening "if"s. The reverse fixtures are in `test_trigger_timing_scan_has_teeth`;
      989707d7's check returns nothing for each (`reports/trigger_timing_2026-11-12/base_runs.txt`).
      A qualifier joined into an intervening "if"'s condition keeps the counts equal: the census
      finds no such sentence in the 19 sets (BACKLOG).
    - M3. No canonical slot for a qualifier that reads no subject: TURN_OF and
      CONTROLLER_COUNT_GE ignore the handle (`quantity.py`) and `_match_cast` reads `actor` and
      `filter` alike, so `CastSpellEvent(actor=FAnd(YOU, TURN_OF OPPONENT))` played as
      `filter=TURN_OF OPPONENT`; six event classes have two or more filter slots. The slot is now
      named per event class (§11 R6-2), `ontology_conformance.check_qualifier_slots` refuses a
      subject-free predicate in any other slot (`test_a_subject_free_qualifier_has_one_slot`),
      and ATOM_DIVERGENCES D20 registers the class. The 6 uses in the 19 sets are all in `filter`.
  - **MINOR, fixed:** m2, `verbs._v_trigger_additional` re-queues a trigger with the original's
    carried state (`test_an_extra_copy_of_a_reflexive_trigger_reads_the_same_resolution`). m3,
    one list of gate wordings, `compiler._DO_GATES` ("If you do,", "If you do so,", "When you do,",
    "When you do so,"), the continuation prefixes carrying the last two with their commas, so
    "When you do so," is a reflexive trigger and "When you do this, ..." no continuation
    (`test_compile_when_you_do_so_is_the_same_reflexive_trigger`, `test_do_prefix_registered`;
    the 19 sets print only "When you do,"). m5, the counts (21 cards, 22 sentences), the §5 rows,
    the `fire_reflexive` docstring (it carries the binding, not the sacrificed creature's last
    known power) and the test module's docstring (one Mangara test passes on the base). m6, the
    two selfplay tests' seeds pinned (simulator 22, search 42). m9, the one-shot note in §11.
  - **MINOR, in the BACKLOG:** m1, a reflexive trigger cannot read its creator's target (IKO Back
    for More); m4, the matcher reads event-filter qualifiers without the `layers.recompute()`
    that `_queue` runs before a condition (CR 603.10); m7, a reflexive trigger on the stack
    encodes as ability index -1 (`features._ability_index`); m8, no G3 operator moves a
    qualifier into the condition.
  - **Blast radius of these fixes** (989707d7 -> the branch, `tree_dump.py` and `tree_diff.py`):
    0 trees changed, compiler or record; 0 verified cards leaving or joining; the six record packs
    moved from `known_bugs/` to `tools/scenarios/mapped/<SET>/`, where the suite plays them on the
    records. Verified pools on the merged tree (deckable, `get_supply("verified", <set>)`): M21
    264, M20 253, FDN 173 (main bc0d4606: 269, 255, 175).
- R5 round 7 (proposed 2026-11-12, branch `worktree-agent-a68bbb5431c425326`, main 76f46aff
  merged; awaiting the adversarial gate):
  - **The emblem rides its maker.** `GET_EMBLEM(emblem=EmblemSpec(abilities), controller=who)`
    replaces C19's role-less marker and `CardRecord.emblem` (an emblem's MTGJSON entry attached by
    name at pool compile). The compiler compiles the quote as the emblem's own text; a quote that
    does not compile leaves its sentence unparsed. `EmblemAbility` (unused) and `CardRecord.emblem`
    are deleted: one encoding. Each GET_EMBLEM makes a new emblem (CR 114.2; the executor's
    one-per-(owner, emblem) table did nothing on a second: pack
    `basri_ket_two_emblems_both_trigger` fails on main 76f46aff, one Soldier for two emblems).
  - **Who gets it is the `controller` role**, as LOSE_LIFE's is in "each opponent loses 2 life":
    a single-atom player verb names its player there. An EachPlayer around the GET_EMBLEM would
    run too (it rotates the controller), but EachPlayer is for an effect each player goes through
    on their own (Transmogrify's "that player puts that card onto the battlefield, then shuffles",
    Liliana, Waker of the Dead's "each opponent who can't loses 3 life"), and functionally
    identical wordings land in the same atoms (the owner directive, Status above).
  - **ALL over the top of a library reads the open look window**, as ONE_OF and REST do, and
    leaves the window to the REST after it (Goblin Ringleader).
  - No new verb, role value class beyond EmblemSpec, or field classification beyond
    `EmblemSpec.abilities` (IDENTITY).
  - Pre-gate review (one fresh-eyes reviewer on 09f6078e and 720c13a6, 2026-11-13), fixed in
    effadcc9: FDN Vivien Reid's -8 had lost the emblem its entry's record attached (the emblem
    is now in her record); a search's exact count over another player's hidden zone, and an
    emblem's choices, were not asked; the bench called every NONE "no block". Logged in the
    BACKLOG: "any number" over a menu the engine cannot ask takes all of it (not live).
- BINDING STATE: rounds 1–6 complete; round 7 proposed; further ontology changes require a
  NEW gated round (any R-item that reclassifies a field or opens a normalization is Type-1).

## 10. Round R5 — durations, permissions, copies (v3 after gate round 2, 2026-10-29; gate round 3 pending)

Owner, 2026-10-29: "Fix the remaining M21 pool to be castable and playable, and mapped properly",
and on B-60c: go ahead "if you have good arguments for the design ruling, and an adversarial pass
doesnt break it". Gate rounds 1 and 2 are logged in §9. **Every census count here comes from
`tools/audit/r5_census.py`** (regex screen over the 19 set files, unique names;
`reports/r5_census_2026-10-29.json`).

### Status (updated 2026-10-30 07:00; implementation lives on branch `cards/integration`)
| Item | State |
|---|---|
| R5-1 `duration` on MOVE_ZONE (B-60c) | **implemented** (lane r5a; FIX-THEN-GO in rounds 1 and 2, every round-2 fix applied): return registry `returns.py`, journal-provenance 400.7, 610.3a-d, returns through replacements, Aura host choice |
| R5-6 `actor` on TargetingEvent | **implemented** (lane r5a) |
| R5-7 `AbilityActivatedEvent` + `is_mana_ability` (605.1a) | **implemented** (lane r5b, round 3 GO). The B-90 payment witness skips locked mana abilities and journals its activations (lane vfix, B-109) |
| R5-9 Teferi, Timeless Voyager stays weaker | **superseded by round 4** (2026-11-12, accepted; §9): Teferi plays as printed with `PhasingEvent`, `FAtomPred.IS_RESULT` (Filter roles that take no referent Selector; raises without a register) and R5-8's `DurationUntilEndOfNextTurn` (1cac720, fixes 844c315) |
| R5-10 `STACK_KIND_EQ` + counter-window mode ask | **implemented** (lane r5b) |
| R5-11 `TokenSpec.colors` | **implemented** (lane r5b) |
| `Choose(QAtLeast(1))`, fitting cast ordinal | **implemented** (lane r5b) |
| R5-2, R5-5, R5-8, R5-12 | fix, then gate round 4 (round 3 findings in §9) |
| R5-13 FIRST_MATCH | rejected in round 3; `REVEAL.until` **implemented, round 4 GO** (1cac720, fixes 844c315): count = the revealed cards that pass `until`; `until=FAnd(())` and an unbounded count with `until` refused. Transmogrify's "that creature's controller" is the majority referent Selector, and `EachPlayer.ref` takes it |
| `Verb.ATTACK_POLICY` (scope `AS_NO_DEFENDER`, CR 609.4; BACKLOG B-80) | **implemented, round 4 GO** (1cac720): Drowsing Tyrannodon keeps defender and attacks as though it had none; ledger F9 |
| R5-14 once-per-event vs once-per-object triggers (B-103, B-102, V14) | **implemented, round 4 FIX-THEN-GO** (6f020b8, fixes 3ece400): `once_per_event` (True or absent) on TriggeredAbility and DelayedTrigger; absent = once per occurrence (CR 603.2c); refused where the subject does not gather occurrences (IS_SOURCE, IS_ATTACHED_TO_SOURCE), on non-combat damage and with no dealer; checked as triggers queue |
| `EtBState.effect` ("As ~ enters", CR 614.1c, 614.12a) | **implemented, round 4 GO** (deaba91, fixes e6f9358): Runed Halo; CHOOSE_NAME only until another card brings tests; the choice is made at the atom boundary just after the move, unobservable for the Halo (accepted) |
| R5-15 `ControllerRef.TARGET_OPPONENT` (lane vfix2, an identity fix) | implemented; post-hoc check in round 4 |
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
BACKLOG B-75. **Superseded 2026-11-12** (1cac720): the clause is
`PREVENT_EFFECT(condition=IS_RESULT, event=PhasingEvent(phased_in=True, filter=IS_RESULT),
duration=DurationUntilEndOfNextTurn)`, consulted by the untap step's phasing; D16 is closed.

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

## 11. Round R6 — when a trigger's parts are read (2026-11-12; gate round 6 FIX-THEN-GO, fixed: §9)

Two faults found by verification wave 1 (KNOWLEDGE/2026-11-12/201 §6), one cause each; the
evidence, censuses and blast-radius scripts are in `reports/trigger_timing_2026-11-12/`.

**R6-1 Reflexive triggers (CR 603.12): one IR change.**
- **Cause.** The IR had no reflexive trigger, so "You may X. When you do, Y" compiled as X and Y in
  one ability (Tolarian Kraken: Y inside X's OptionalEffect; Sorin, Imperious Bloodlord and
  Cavalier of Night records: the "If you do" gate or one optional). Every designation walker reads
  the whole effect, so Y's target was chosen with the ability's own, before X.
- **Shape.** `DelayedTrigger` with `duration` and `event` both absent is the reflexive trigger
  (both present: a delayed trigger, unchanged bytes). Its `condition` and `once_per_event` are
  absent. "<step>. When you do, Y" (or "When you do so, Y") =
  `Seq(<step>, Conditional(MAY_DONE, DelayedTrigger(duration=None, event=None, condition=None,
  effect=Y)))`, the "If you do" gate (CR 118.12) around a reflexive trigger. Serialization omits
  both keys.
- **Where it stands** (`ability_tree._reflexive_misplaced`; `CardRecord` refuses it anywhere
  else, gate round 6 M1): the `then_effect` of exactly `Conditional(pred=FAtom(MAY_DONE))` (not
  FNot(MAY_DONE): "when you don't" waits for a card), standing after the step it is about in a
  Seq (with no step before it, MAY_DONE would read an older offer); in the effect of an ability
  that resolves: a spell, an activated, triggered or delayed ability, a granted or token one, or
  a reflexive one after a step of its own; with no EachPlayer between (the executor runs
  EachPlayer's effect under each player as controller, while the reflexive trigger's is the
  resolving ability's, CR 603.7e; refused until the executor passes it) and no Repeat. Never in a
  static, replacement or "as ~ enters" ability, which never resolves, nor in an emblem's (its
  triggered ability resolves, but no emblem of the 19 sets has a reflexive trigger to test it).
- **A one-shot delayed trigger** ("the next time ...", CR 603.7b; none is built, BACKLOG) takes
  a Duration value of its own when it comes, never `duration=None` beside an event: that shape is
  refused, `duration=None` meaning only the reflexive trigger, which has no event either.
- **Engine.** At the gate it triggers (`TriggerBinder.fire_reflexive`): queued like any trigger,
  put on the stack at the next priority point in APNAP order, its targets chosen then (603.3d:
  none legal, removed); its source and controller are the resolving ability's (603.7d-e); it
  reads that resolution's bindings, X and event register, not its designation. Every
  designation walker (`binding._designation_slots`, `query.spell_target_slots`,
  `activation_target_slots`, `optional_offer`) reads only the ability's own nodes
  (`ability_tree.own_nodes`: a delayed, reflexive or granted ability, or a token's, designates
  for itself). That also fixes M20 Sorin, Vampire Lord's -8, whose activation asked the target
  of the ability it grants.
- **Census.** 22 reflexive sentences on 21 cards in the 19 sets (Wildborn Preserver is in FDN
  and ELD; THB Pharika's Spawn's "When it enters this way" is its own enters trigger, not one);
  3 trees hold one (Tolarian Kraken by the compiler, Cavalier of Night and Sorin, Imperious
  Bloodlord by record); the other 19 sentences are unparsed. Two new branchings (M21, §5),
  registered by
  `reports/ontology_census_2026-11-12_triggertiming_post_full.json`: Conditional `then:
  DelayedTrigger`, DelayedTrigger `reflexive`.
- **Rejected.** (a) A new node `ReflexiveTrigger(effect)`: CR 603.12 makes reflexive triggers
  delayed triggers with two exceptions, so a second class would duplicate DelayedTrigger. (b) The
  gate in the node (`condition=MAY_DONE`): `condition` is CR 603.4's intervening "if", read again
  on resolution, so one field would carry two meanings. (c) Keep `Conditional(MAY_DONE, Y)` and
  choose Y's targets late in the engine: "if you do" and "when you do" would share bytes and play
  differently (a response window, targets after the action). (d) A delayed trigger on a real
  event of the action: most actions (pay, discard, reveal) have no event spec, and "this
  resolution" would need a new duration.

**R6-2 The condition is only an intervening "if" (CR 603.4): an encoding rule, no new field.**
- **Cause.** `condition` is the intervening "if", read as the event occurs and again as the
  ability resolves; templates and the MAPPER_GUIDE put event qualifiers there too, so they were
  re-read on resolution: Tide Skimmer's "with two or more creatures with flying", Makeshift
  Battalion's "and at least two other creatures attack", Mazemind Tome's and Nine Lives' state
  thresholds (CR 603.8), Sanctum of All's "while you control six or more Shrines", Brineborn
  Cutthroat's "during an opponent's turn". Each one's ruling (where it has one) says it is not
  re-read.
- **Rule.** A qualifier that is part of the trigger event is a conjunct of the event's subject
  filter, read once as the event is matched. A qualifier that reads no subject (TURN_OF,
  CONTROLLER_COUNT_GE/GT, ZONE_COUNT_GE, NAME_PARTITION_COUNT_GE, ATTACK_AGAINST_COUNT_GE,
  DIED_THIS_TURN, EVENT_THIS_TURN, CARDS_DRAWN_THIS_TURN_GE, LIFE_GAINED_THIS_TURN_GE,
  LIFE_LEAD_OVER_START_GE, INSTANT_OR_SORCERY_CAST_THIS_TURN, FLIP_WON, MAY_DONE:
  `ontology_conformance.SUBJECT_FREE`) reads the same in any slot, so it has one slot per event
  class (`ontology_conformance.qualifier_slot`, gate round 6 M3):

  | event | the slot |
  |---|---|
  | ZoneChangeEvent | `subject` |
  | an event with a `filter` (CastSpell, DeclareAttackers, DeclareBlockers, CounterPlaced, CreatureDies, BecomesBlocked, TapState, Phasing, AbilityTrigger, DamageDealt, Targeting, Countered) | `filter` |
  | AbilityActivatedEvent | `source` |
  | TurnPhase, CardDrawn, LifeGained, LifeLost and Sacrifice events | `actor` |
  | StepEvent | none (no qualifier) |

  `ontology_conformance.check_qualifier_slots` refuses one in any other slot (ATOM_DIVERGENCES
  D20); the 6 in the 19 sets are all in `filter`. `ontology_conformance.check_trigger_timing`
  compares, over the sentences that compiled and both ways, trigger conditions with intervening
  "if"s, and reflexive triggers with reflexive sentences (`REFLEXIVE_WORDING`).
- **Mangara, the Diplomat is not in this class.** Its Oracle text, "Whenever an opponent attacks
  with creatures, if two or more of those creatures are attacking you and/or planeswalkers you
  control", prints an intervening "if": the re-read is right. Its ruling counts an attacker that
  left the battlefield by what it was attacking before it left: `ATTACK_AGAINST_COUNT_GE` now
  counts the triggering declaration's attackers, a departed one by its last known attack
  (`quantity.LastKnown.attacking`). No tree changes.
- **Rejected.** A second trigger field read once (`event_condition`), or a flag making the
  condition read once: two fields, or one field with two meanings, for what the event filter
  already says. A per-event count field (`DeclareAttackersEvent.count`): one field per event kind
  and qualifier, and "this creature and at least two others" would still not fit it.

**Blast radius** (by script over the 19 sets, `reports/trigger_timing_2026-11-12/`):
- trees changed: 8 compiler trees (M21 Tolarian Kraken, Tide Skimmer, Makeshift Battalion,
  Mazemind Tome, Nine Lives, Sanctum of All; WAR Makeshift Battalion; FDN Mazemind Tome), and 4
  records (M20 Cavalier of Night, Sorin, Imperious Bloodlord; M20 and FDN Brineborn Cutthroat);
  6 M21 goldens;
- verified cards out of the verified pool until re-verified (9): M21 Tide Skimmer, Makeshift
  Battalion, Mazemind Tome, Nine Lives, Sanctum of All; M20 Cavalier of Night, Brineborn
  Cutthroat; FDN Mazemind Tome, Brineborn Cutthroat. Stamps M21 270 -> 265, M20 257 -> 255, FDN
  175 -> 173 against b776cf74; verified deckable pools on the tree merged with main bc0d4606
  (`get_supply("verified", <set>)`): M21 269 -> 264, M20 255 -> 253, FDN 175 -> 173;
- verified cards that play differently with unchanged bytes: M20 Sorin, Vampire Lord (its -8 asks
  no target and grants to each Vampire you control); unverified, M21 Mangara (an attacker that
  left still counts);
- 300 seeded heuristic games (100 each, M21, M20, FDN), decks from the cards verified before and
  after: byte-identical digests, 0 crashes.
