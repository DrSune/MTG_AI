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
- BINDING STATE: rounds 1–4 complete; further ontology changes require a NEW gated
  round (any R-item that reclassifies a field or opens a normalization is Type-1).

## 10. Round R5 — durations, permissions, copies (PROPOSAL 2026-10-29, gate pending)

Owner, 2026-10-29: "Fix the remaining M21 pool to be castable and playable, and mapped properly",
and on B-60c: "If you have good arguments for the design ruling, and an adversarial pass doesnt
break it, go ahead". On branch `cards/integration` 278 of M21's 285 cards are castable and fully
compiled. Seven are not (Chandra, Flame's Catalyst; Chandra, Heart of Fire; Double Vision; Sublime
Epiphany; Teferi, Master of Time; Teferi, Timeless Voyager; Ugin), and about 15 castable cards
compile through templates documented as lossy. R5 is the ontology part of closing that gap. The
executor-only parts (phasing, spell copies, an X lane for loyalty costs) need no ontology change and
are listed at the end. Census counts below are regex counts over the oracle text of the 19 set
files, unique card names.

### R5-1 `duration` on MOVE_ZONE (B-60c; CR 610.3)
- **Cards.** Kitesail Freebooter, Idol of Endurance (M21); Banishing Light, Prayer of Binding, Stasis
  Snare (FDN); Hieromancer's Cage (M19). 19 cards in 12 sets.
- **Today.** The templates drop "until … leaves the battlefield" (LOSSY C11,
  `templates_b5a.py:1333`, `templates_b2a.py:2107`). Freebooter's exile is permanent (stronger than
  printed); Idol's exiled creature cards never come back (weaker).
- **Proposal.** `_VERB_ROLES[MOVE_ZONE]` gains the optional role `duration` (any `Duration`).
- **Semantics** (CR 610.3). The move happens. The executor records each moved object (its new
  identity, its previous zone) under the duration in the `DurationLedger`. When the duration ends, a
  one-shot effect returns each recorded object that is still in the zone it was moved to:
  - it goes back to its previous zone; onto the battlefield under its owner's control (610.3c);
  - returns caused by simultaneous events are simultaneous (610.3d);
  - an object that left that zone meanwhile is a new object (400.7) and stays where it is; a token
    has ceased to exist (704.5d).
  If the duration already ended after the ability triggered or the spell was cast, and before the
  move, nothing moves (610.3a, 610.3b).
- **`DurationUntilLeaves` is fixed to mean exactly "until the anchor leaves the battlefield".** It
  ends when that object (the same object, 400.7) leaves the battlefield. Phasing out does not end it
  (702.26d: phasing is not a zone change). A "for as long as ~ remains on the battlefield" duration
  (611.2b) also ends on phasing out (702.26f), so it must not reuse this node unless the node gains a
  field for it. No compiled card uses `DurationUntilLeaves` today: no template constructs it, so
  fixing its meaning changes no golden.
- **Rejected.**
  - (B) An extra "when ~ leaves the battlefield, return the card" trigger. That is the older Oblivion
    Ring wording. It differs from "until" exactly in 610.3a/b: Oblivion Ring exiles forever if it
    leaves before its enters trigger resolves; the "until" cards exile nothing. Two meanings would
    get the same bytes, and one printed ability would compile to two.
  - (C) A new verb such as EXILE_UNTIL. It fuses operation and duration (AGENTS §9), and 14 verbs
    already carry `duration` as an independent axis.
- **Cost to the ontology.** Zero new node classes and zero new tokens: the role name and
  `DurationUntilLeaves` both exist. One new role binding. No new decision, so nothing blind and nothing
  phantom (§10).

### R5-2 The permission lane: what a CAST atom means
- **Cards (M21).**
  - Chandra, Heart of Fire's +1 and −9;
  - Chandra, Flame's Catalyst's −8;
  - Idol of Endurance's {1}{W},{T} ability;
  - Furious Rise, Conspicuous Snoop, Radha, Heart of Keld, Demonic Embrace.

  Across the 19 sets: 29 cards grant a cast/play permission with a duration, 30 let you play from
  another zone, 30 waive the mana cost.
- **Today: the "permission row" idiom**, a free `ActivatedAbility(cost=())` whose effect is
  `OptionalEffect(CAST)`. Its CAST runs while the activation resolves, and it goes wrong four ways:
  1. **It ignores timing (608.2g).** Snoop casts Goblin creatures from the top of the library at
     instant speed.
  2. **It is phantom (§10).** It sits in every action menu even when nothing can be cast; the Snoop
     probe shows "activate [1] … event: (none)".
  3. **It never ends.** Furious Rise's permission lasts forever.
  4. **It made both Chandras unsupported.** On integration the duration permissions are suppressed
     (B-49 follow-up #1, `compiler.py:876`), so neither Chandra can be dealt.
- **Proposal.** CAST gains the optional role `duration`. A CAST atom's meaning then follows the rule
  every duration-bearing verb already follows (MODIFY_PT, GRANT_ABILITY, …):
  - **In a resolving effect, without `duration`:** a one-shot instruction. The player casts it now,
    during resolution, ignoring timing (608.2g). This is today's `_v_cast` and is unchanged. Example:
    Chandra, Flame's Catalyst's −2.
  - **In a resolving effect, with `duration`:** a continuous effect (611.2a). It permits the player to
    cast the designated objects during the duration, at normal timing (601.3; sorcery timing unless
    the object has flash).
    - If `source` names particular objects (a register such as "cards exiled this way"), that set
      is fixed when the effect begins.
    - If `source` is a zone selector ("spells from your hand"), the effect modifies the rules and
      covers objects that arrive later (611.2c).
  - **In a `StaticAbility`:** a permission for as long as the ability functions (611.3a). Examples:
    Snoop, Radha, Demonic Embrace.
  - **The `cost` role keeps its meaning.** Absent: pay the printed cost. An empty `Cost`: without
    paying the mana cost, an alternative cost (118.9) with X = 0. A `Cost` with parts: additional
    costs (Demonic Embrace).
- **Executor.** A permission ledger holds entries {player, designated objects or zone selector, cost,
  `play_lands`, duration}.
  - `legal_casts` and the land lane offer the permitted objects from their zones, at legal times.
  - A cast through a permission is an ordinary cast (601.2), so cast triggers see it.
  - An entry stops covering an object once that object leaves its zone (400.7), and the whole entry
    expires with its duration.
  - "For as long as it remains exiled" (Valakut Exploration, ZNR) is therefore `DurationPermanent`
    on designated objects; no new duration is needed.
  - The permission-row idiom is retired.
- **Rejected.**
  - (B) A new verb PERMIT_CAST. It duplicates the operation axis "cast" for the difference that
    `duration` already encodes on every other verb (one-shot versus continuous), and doubles the
    vocabulary for casting.
  - (C) Keeping the free activation. It breaks timing and §10.

### R5-3 `play_lands` on CAST (CR 305.1, 305.2)
- "Play" means cast it if it is a spell, play it if it is a land. A land played this way is a
  special action and uses a land drop (305.2). Cards: Chandra, Heart of Fire's +1, Furious Rise,
  Radha.
- **Proposal.** CAST gains an optional bool role `play_lands`; absent means cast only. With it, a
  designated land can be played and is never cast. Example: Radha = `StaticAbility(CAST(source=top
  of library, filter Land, play_lands=True))`.
- **Rejected.**
  - A verb PLAY: it splits one operation over a one-bit difference (§9 (i)).
  - Filter-only: "you may cast that card" on a land is not playable, so "cast" and "play" differ
    even when the filters are equal.

### R5-4 `new_targets` on COPY (CR 707.10c)
- Double Vision's "You may choose new targets for the copy" is dropped today: the copy keeps the
  original's targets. Census: 26 copy-a-spell cards in 18 sets, most with this sentence.
- **Proposal.** COPY gains an optional bool role `new_targets`. When it is true, the copy's controller
  is asked once per target: keep it, or choose a new legal target (707.10c). The ask is visible, so
  nothing is blind (§10).

### R5-5 Token copies are CREATE_TOKEN, not COPY
- Sublime Epiphany's "Create a token that's a copy of target creature you control" compiles to
  `COPY(source=a battlefield creature)`. COPY then means two different operations, picked by the
  zone its source is in:
  - a copy of a spell on the stack (707.10), which is not cast and never enters;
  - a new token permanent (707.2, 111.1), which enters the battlefield, fires enters triggers, and
    is a token for every "token" rule.

  Census: 21 token-copy cards in 9 sets.
- **Proposal.** COPY keeps only spells and abilities on the stack. CREATE_TOKEN gains an optional
  role `copy_of` (Selector); exactly one of `tokens` or `copy_of` is required. Exceptions such as
  "except it has haste" are a later field, recorded when the first card needs it.
- **Why.** §9 (i): the two effects are not similar. Every CREATE_TOKEN consumer (token counts,
  "whenever a token enters", token-doubling replacements) then sees copy tokens.

### R5-6 `actor` on TargetingEvent
- Warden of the Woods' "a spell or ability an opponent controls" is dropped today, so the Warden
  draws two cards whenever its controller targets it: stronger than printed. Census: 11 cards in
  8 sets.
- **Proposal.** TargetingEvent gains an optional `actor` Filter over the controller of the targeting
  spell or ability. This is the single direction encoding (E1/65) that CastSpellEvent,
  CardDrawnEvent, LifeGainedEvent and LoyaltyActivatedEvent already use.

### R5-7 An activation event, for prohibitions
- Faith's Fetters' "its activated abilities can't be activated unless they're mana abilities" is
  dropped today (weaker than printed). Census: 12 cards in 11 sets.
- **Proposal.** A new event `AbilityActivatedEvent(filter, actor=None, mana=False)`. `filter` is
  over the permanent whose ability is activated; `mana=False` excludes mana abilities.
  `PREVENT_EFFECT` over it is the prohibition, and the legality layer stops offering those
  activations.
- Fusing LoyaltyActivatedEvent into it is fusion-ledger item F9, for a later round, so R5 rewrites
  no loyalty-trigger goldens.

### R5-8 Furious Rise's window: approximate, flagged
- "You may play that card until you exile another card with this enchantment" is the only such
  wording in the 19 sets (Furious Rise, M21, reprinted in THB). A duration class for one card fails
  §9 (ii), volume.
- **Proposal.** Map it as R5-2/R5-3 with `DurationUntilNextStep(END, owner_scoped=True)`, that is,
  until the beginning of your next end step. This is weaker than printed when the trigger's
  condition fails at that end step: the printed permission would continue. Recorded as divergence
  D15.

### Not ontology (executor and compiler work in the same round)
- Executor:
  - spell copies (707.10, 700.2g);
  - phasing (702.26), including indirect phasing (702.26g) and Teferi, Timeless Voyager's "can't
    phase in";
  - extra turns;
  - an X declaration on activation, for Ugin's −X (601.2b via 602.2b; 606.6);
  - "choose one or more" (700.2d);
  - countering an activated or triggered ability.
- Compiler mapping fixes onto existing components:
  - Peer into the Abyss's life loss (`QPropField.LIFE` exists);
  - token colors (`TokenSpec.color` exists);
  - the bare HEXPROOF that Sporeweb Weaver and Garruk's Harbinger carry beside "hexproof from
    [color]" (both are stronger than printed today).
- Every card whose tree changes is re-verified through the play-time gates
  (docs/PLAN_CARD_ONBOARDING.md).
