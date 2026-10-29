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
- BINDING STATE: rounds 1–4 complete; further ontology changes require a NEW gated
  round (any R-item that reclassifies a field or opens a normalization is Type-1).

## 10. Round R5 — durations, permissions, copies (v2 after gate round 1, 2026-10-29; gate round 2 pending)

Owner, 2026-10-29: "Fix the remaining M21 pool to be castable and playable, and mapped properly",
and on B-60c: go ahead "if you have good arguments for the design ruling, and an adversarial pass
doesnt break it". Gate round 1 broke v1 in places (§9, R5 round 1). This is v2. Census counts are
regex counts over the oracle text of the 19 set files, unique card names. Items that are engine or
compiler work on existing components are listed at the end, with their lanes.

### R5-1 `duration` on MOVE_ZONE, and `DurationUntil(event)` (B-60c; CR 610.3)
- **Cards.** Kitesail Freebooter and Idol of Endurance (M21); Banishing Light, Prayer of Binding,
  Stasis Snare (FDN); 19 cards in 12 sets. Today the templates drop "until …", so Freebooter's exile is
  permanent.
- **New node `DurationUntil(event: EventSpec)`** replaces `DurationUntilLeaves`. That is a fusion, and it
  changes no golden, because no template builds `DurationUntilLeaves`.
  - "Until ~ leaves the battlefield" = `DurationUntil(ZoneChangeEvent(BATTLEFIELD → ANY, subject=IS_SOURCE))`.
  - Expiry uses the same event matcher triggers use.
  - Phasing is not a zone change (702.26d), so it never ends the duration.
- **`MOVE_ZONE.duration` accepts only durations that end on an event:** `DurationUntil`, `DurationEot`,
  `DurationUntilNextTurn`. Construction rejects `DurationPermanent`, which is a twin of leaving the role
  out, and `DurationWhileCondition`, which can revive and would move the object again.
- **Executor: a return registry,** a new piece of state that is part of the replay fingerprint. One row
  per moved object: its zone-entry clock, previous zone, owner and duration.
  - When the duration ends, each row whose object is still in the destination zone with the same entry
    clock returns to its previous zone. The check uses journal provenance, because Handles are stable
    across zones (`identity.py:46`) while CR 400.7 makes a moved card a new object.
  - Returns caused by the same events are one simultaneous batch, inside the zone-change handling
    (610.3d).
  - An object returning to the battlefield comes back under its owner's control (610.3c).
- **610.3a/b.** At resolution, if a matching event is in the journal after the ability triggered or the
  spell was cast, nothing moves. This is a journal-clock comparison, as WAS_KICKED does.
- **A returning Aura.** Its owner chooses what it enchants among the legal objects (303.4f). If there is
  none, it stays in exile (303.4g). That is a new, visible decision asked of the owner. "As ~ enters"
  choices on return are asked the same way.
- **Gap ledger:** Calix, Destiny's Hand, whose anchor is a second target.

### R5-2 Permissions are a verb of their own: PERMIT_CAST
- **Why a separate verb (gate finding).** A missing duration means Permanent for P/T and grant records
  (`duration_tag(None)`). "CAST without duration = cast now" would make CAST the only verb where absent
  is not Permanent, and a mapper who writes `DurationPermanent` out of habit would turn a cast-now into
  a lasting permission. Separate verbs give the two meanings different bytes.
- **CAST (one-shot, 608.2g, meaning unchanged).** Roles:
  - `source`;
  - `additional` (Cost, 601.2f);
  - `alternative` (Cost, 118.9; an empty Cost means without paying its mana cost);
  - `lands` (True only).
- **PERMIT_CAST.** Roles:
  - `source` (Selector: a register, a linked set, or zone + filter);
  - `additional`, `alternative`, `lands` (as on CAST);
  - `count` (Quantity: how many casts the permission allows; absent means each designated object once);
  - `duration`: required in a resolving effect (611.2a); absent in a static ability, which lasts while
    the ability functions (611.3a).
- **Costs.**
  - CAST's `cost` migrates to `additional` or `alternative`, which are separate axes (601.2f, 118.9).
  - `CostDeltaWaiveMana` is deleted: no golden uses it, and it duplicated the empty Cost.
  - Today `stack.py:1088` treats a non-empty cost as the whole cost. Demonic Embrace would then be cast
    without paying {1}{B}{B}.
- **Where a static permission functions.** A card's own "you may cast this card from [zone]" functions
  everywhere (113.6f): Demonic Embrace. A permission over other objects functions where the static
  ability does, on the battlefield: Snoop, Radha.
- **A permission is never wrapped in OptionalEffect.** The cast option is the "may"; a wrap would be a
  phantom ask.
- **Executor.**
  - A permission registry, part of state, the fingerprint and the observation, expiry included.
  - CastOption gains a discriminator (which permission, which cost path), so two ways to cast one card
    are two options. Example: Volcanic Geyser under Chandra's −8, pay and choose X, or free with X = 0
    (107.3b).
  - The count is consumed per cast.
  - Land plays through a permission obey 305.1, 305.2b and 305.3; `land_playable` takes the zone from
    the permission.
- **Repair the one-shot lane** (gate scratch packs). A spell cast during resolution must:
  - choose its targets (601.2c);
  - pay its additional costs;
  - use X = 0 when no mana cost is paid (107.3b);
  - journal each draw once;
  - see replacement effects.
- **Retire every free activated row in M21:** Snoop, Radha, Demonic Embrace, Furious Rise, Idol and
  Chandra, Heart of Fire. Azusa, Basri's Aegis and Liliana's Scorn are compiler fixes in lane F.
- **"Look at the top card of your library any time"** (Radha and 6 more) = `StaticAbility(LOOK_AT(top,
  YOU))`. It is continuous by 611.3a, and the per-seat view shows that card to its controller. No new
  verb.
- **Encodings.**
  - Chandra, Heart of Fire's +1 exiles the top three with MOVE_ZONE `pop_order`, not a TARGET selector.
  - Her −9 searches one Selector over graveyard and library (§7), not two SEARCH atoms that overwrite
    `result`.
- **Gap ledger:** "until the end of your next turn" (8 cards, none in M21) needs a next-turn anchor.

### R5-3 `lands` (CR 305) — merged into R5-2
- Only True is allowed; absent means cast only. A one-shot "play that card" on a land is ignored when
  305.2b or 305.3 forbid it. A bool role set to False is rejected at construction, because it validates
  yet gives different bytes from leaving it out.

### R5-4 `new_targets` on COPY (True only; CR 707.10c)
- **The ask.** For each target, the copy's controller keeps it or picks a new legal one.
  - It is asked only when another legal target exists; otherwise it would be a phantom.
  - The new set of targets is validated as a whole.
  - Copy targets journal TARGETING events, so Warden and ward see them.
- **Copies of permanent spells** become tokens as they resolve (707.10f, 608.3f). The executor supports
  this when a pool card needs it; Double Vision copies instants and sorceries only.

### R5-5 Copies are a value: `CopyOf(source: Selector, exceptions: tuple = ())`
- CREATE_TOKEN's `tokens` accepts a TokenSpec or a CopyOf; there is no exactly-one-of rule.
- The "enters as a copy" family (Clone and 13 more) will use the same value, so there is one copy
  encoding (§9).
- `source` may select any zone: three token-copy cards copy a card in a graveyard.
- Exceptions ("except it has haste") are needed by 9 of 22 token-copy cards, none in M21. They go in the
  gap ledger until a pool card needs them.

### R5-6 `actor` on TargetingEvent — GO in round 1
- **Mapper rule:** "can't be the target of spells or abilities your opponents control" stays HEXPROOF
  (702.11), never `PREVENT_EFFECT(TargetingEvent(actor))`.

### R5-7 `AbilityActivatedEvent(source: Filter, kind: AbilityKind, actor: Filter | None = None)`, fusing LoyaltyActivatedEvent
- **`kind` ∈ {ANY, NON_MANA, LOYALTY}, required.** 4 cards say "unless they're mana abilities" and 7 lock
  every ability, so a forgotten flag must not silently weaken a lock.
- **`source`** filters the object whose ability is activated, in any zone (Pithing Needle–style locks
  reach cycling).
- **Loyalty abilities are activated, non-mana abilities (605.1a),** so Faith's Fetters on a planeswalker
  locks them.
- **A lock of kind ANY also binds mana abilities,** so payment planning (TAP_ALL_MANA) must respect it.
- **Cost:** one golden changes (Keral Keep Disciples).

### R5-8 Furious Rise, exactly (v1's approximation is rejected)
- **Mapping.** `PERMIT_CAST(source=result, lands=True, duration=DurationUntil(ZoneChangeEvent(ANY →
  EXILE, subject=FAtom(EXILED_BY_SOURCE))))`.
- **New predicate `EXILED_BY_SOURCE`.** True for an object whose current stay in exile began with a move
  made by an ability of this ability's source (linked abilities, 607.2a). After 400.7 the card is a new
  object and no longer counts.
  - Census: 20 cards in 12 sets use linked-exile wording ("exiled with ~", "the exiled card").
  - Idol of Endurance's permission uses it in its `source` selector.

### R5-9 `duration` on PHASE_OUT (Teferi, Timeless Voyager)
- **Mapping.** "They phase out. Until the end of your next turn, they can't phase in" =
  `PHASE_OUT(target, duration=DurationUntilNextTurn)`. The permanent stays phased out until the duration
  has ended, then phases in at its controller's next untap step.
- **Why `DurationUntilNextTurn` is exact here.** A permanent phases in only during its controller's untap
  step, and none of the opponent's untap steps falls between the start and the end of your turn, extra
  turns included.
- **What it replaces.** The `_phase_in_prevention_effect` builtin, whose `ZoneChangeEvent(COMMAND →
  BATTLEFIELD)` can never match once phasing is a status (702.26d). No new event class.

### R5-10 Stack objects say what they are: predicate `STACK_KIND_EQ` (SPELL | ACTIVATED | TRIGGERED)
- **Problem.** Sublime Epiphany's "counter target spell" and "counter target activated or triggered
  ability" compile byte-identical today, and "counter target spell" also accepts abilities. 39 cards
  counter spells.
- **Mapping.** Every stack selector (counter, copy) carries the kind. The "counter target spell" goldens
  change by one FAtom each.

### R5-11 Copiable color: `TokenSpec.color: str` becomes `colors: tuple[str, ...]` (B-75)
- Multicolor tokens, such as the blue and red Weird, have no encoding today. The fidelity lane measured
  150 of 152 compiled token colors right.

### Rejected or ledgered
- **v1 R5-8** (`DurationUntilNextStep(END)`) is rejected: there is no END step, END has no expiry tick,
  and the approximation was stronger than printed with Strionic Resonator.
- **Snoop's "has all activated abilities of that card"** is a single card in 19 sets. It is mapped as
  dropped (weaker), divergence D16. Its current REVEAL-grant compile is removed.

### Engine and compiler work on existing components (same round)
- **Resolving replacement effects with a duration** = `GRANT_ABILITY(target, ReplacementAbility(…),
  duration)`. GRANT_ABILITY accepts a ReplacementAbility (`ability_tree.py:3413`).
  - Scorching Dragonfire: the creature or planeswalker gains "if this would die, exile it instead"
    until end of turn.
  - Chandra, Flame's Catalyst's −2: the cast spell gains "if this would be put into a graveyard, exile it
    instead".
  - 22 cards in the census.
  - Divergence D17: an effect that removes all abilities would also remove the granted replacement.
- **"Choose one or more"** = `Choose(count=QAtLeast(1))`, not QUnbounded.
- **Double Vision's "first instant or sorcery spell each turn":** the ordinal counts only the casts that
  match the filter (`events.py:390`, `binding.py:1022`).
- **Legend rule** (704.5j, a visible choice), every free-row compile, the 25 verification findings, and
  phasing as a status: lanes vfix, vfix2, vfix3, fidelity and phasing (see BACKLOG).
