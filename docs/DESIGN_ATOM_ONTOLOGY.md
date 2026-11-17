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
           | EtBState(tapped, counters*, condition?, effect?)  # "As ~ enters" (CR 614.1c); effect: CHOOSE_NAME only (a card name, or its quality a colour or a creature type: R9), until tested
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
gate round 7, `EmblemSpec.abilities`).

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
| QBin.left/right, Conditional.then/else, ordinals (CardDrawn, CastSpell, LifeGained, LifeLost), DelayedTrigger slots | scalars/named fields | **OPERATOR** | position IS semantics (field names, not order) |

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
| F3 | cost↔effect twins | Cost{Sacrifice,Discard,Tap,PutCounter} vs Verb atoms; since R11 also CostExile and CostRemoveCounter beside MOVE_ZONE to exile and REMOVE_COUNTER | **RULED R11 2026-11-14 (§15; gate round 11 FIX-THEN-GO, the ruling kept): not a fusion, the parts stay a closed union.** A cost part is paid while the ability is activated (CR 601.2h by 602.2b), before anyone can respond (117.3c), all of it or the ability is not activated (118.3, 601.2h), and it stays paid when the ability does nothing (608.2b); a verb atom is what a resolving ability does, as much as it can (608.2, 609.3). §9's similar-effects test fails. The fold's reach, measured: 572 trees of the 19 sets change bytes, 164 verified (with {T} kept a part, 85 and 49; `reports/cost_twins_2026-11-14/census_base.txt` §3) |
| F4 | damage events | CombatDamageEvent vs DamageDealtEvent(combat=T/F), 13 nodes/13 cards | **LANDED R2 /140+142 2026-10-20**: CDE extinct (3 nodes folded, class deleted, journal :2129 preserved); D13 split-over-fire ACCEPTED pin, ZND-8 dedup ticket |
| F5 | optional | OptionalEffect 28× vs Kicker vs QAtMost | OptionalEffect = the may-axis; Kicker = cost-side sugar; review at R3 |
| F6 | count/X family | all in use | NOT duplicates; ZND-1g one-X law stands |
| F7 | life polarity | LifeLost verb-only | symmetric event on first card need |
| F8 | phantom menu | Choose(count==len) | V2′: must be encoded ALL |
| F9 | the CR 609.4 policy family | MANA_POLICY, DAMAGE_ASSIGN_POLICY, ATTACK_POLICY (round 4) | fold candidate: before a fourth policy verb (nine "as though it had flash" cards wait), decide one POLICY verb with a scope enum |
| F10 | CR 110.5 status-change events | TapStateEvent, PhasingEvent (round 4; one card) | one family: fold when a third status event appears |
| F11 | life thresholds | LIFE_TOTAL_GE (R8-1, the life total now: 7 sentences) vs LIFE_LEAD_OVER_START_GE (the lead over the starting life total: 11 sentences on 10 cards) | **not one meaning** (§12): they differ wherever the starting life is not 20 (CR 103.4: Commander 40, two-player Brawl 25), as Angel of Vitality's ruling says. Fold candidate only when a starting-life quantity lands (Torgaar's and Resolute Archangel's "your starting life total" need one): then LIFE_LEAD_OVER_START_GE(N) = LIFE_TOTAL_GE(QBin(ADD, <starting life>, N)), one predicate fewer |
| F12 | the chosen-quality pair's names | CHOOSE_NAME and NAME_CHOSEN name a card name but carry any chosen quality since R9 (§13): the role `quality` (COLOR, CREATURE_TYPE; absent, a card name) and NAME_CHOSEN's `string_value`, its quality slot for good (FAtom slots mean what their predicate says, `_FATOM_RULES`; within NAME_CHOSEN the slot has the one meaning, the quality read) | **rename deferred** (§13 R9-3, upheld at gate round 9): a quality-neutral pair (CHOOSE_QUALITY / QUALITY_CHOSEN) re-bakes M21 Runed Halo's verified tree and Necromentia's, for a label: the network reads a token as an id, not as English. The rename is a pure relabel (the role and the slot stay). Fold with the next round that re-bakes Runed Halo's tree, or with the third quality (a card type, IKO Umori; a basic land type, M10 Convincing Mirage), re-verifying Runed Halo |
| F13 | a chosen colour or creature type, by when it is chosen | since R9, "choose a colour" has two forms by context: at resolution, `Choose` over five effects, one per colour (M21 Feat of Resistance and M20 Gods Willing, verified; M12 Stave Off; THB Alseid of Life's Bounty), and as a permanent enters, CHOOSE_NAME(COLOR) read later by NAME_CHOSEN. KHM Crippling Fear and Haunting Voyage choose a creature type at resolution and read it in the same resolution, which needs CHOOSE_NAME(CREATURE_TYPE) outside an EtBState: refused today (§13 R9-1, refusal 5) | **decision at the round that maps Crippling Fear** (Type-1, with F2's choose axis): either lift refusal 5 for a choice read within its own resolution, and fold the colour `Choose` into CHOOSE_NAME(COLOR) + read (one form for "choose a colour"; re-bakes Feat of Resistance's and Gods Willing's verified trees), or keep `Choose` over a fixed menu for colours and give a resolution-time creature type its own encoding. Until then: as a permanent enters, CHOOSE_NAME(quality); at resolution, a colour is `Choose` over five (V4' freeze holds) |

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
| 2026-11-13, gate round 7 | GET_EMBLEM x `emblem` (EmblemSpec: the emblem's abilities) x `controller` (who gets it, CR 114.2: YOU, ALL_OPPONENTS or TARGET_OPPONENT only, `ability_tree.EMBLEM_RECIPIENTS`; never under EachPlayer) | M21 Basri Ket, Garruk, Unleashed, Liliana, Waker of the Dead, M19 Ajani, Adversary of Tyrants (compiler, `compiler._emblem_sentences`); M20 Mu Yanling, Sky Dancer and FDN Vivien Reid (records) | 6 trees, all `controller` YOU; 24 emblem texts in the 19 sets (26 entries), 20 of the 26 sentences that make one unparsed (NUMBERS.md 2026-11-13) |
| 2026-11-13, gate round 7 | MOVE_ZONE x `cards` ALL over the top of a library: the cards of the open look window that pass the filter ("put all Goblin cards revealed this way into your hand"), the window's REST after it | M20 Goblin Ringleader (record); since 2026-11-17 M21 See the Truth (compiler, B5b-cast-elsewhere-instead: "put each of those cards into your hand instead", no filter, the then-arm of its "instead" Conditional) | **low-volume**: 1 record, 1 compiled tree; 4 cards print "all ... revealed this way ... and the rest" (ORI Sylvan Messenger, M14 Garruk, Caller of Beasts, KHM Alrund unparsed) |
| 2026-11-13, gate round 9 (GO) | EtBState `effect` CHOOSE_NAME x `quality` (COLOR, CREATURE_TYPE; `ability_tree.CHOSEN_QUALITIES`): "As this permanent enters, choose a color\|creature type" (§13 R9-1); accepted only as an unconditioned EtBState's own effect (`ability_tree.chosen_quality_fault`) | compiler B17-etb-choose-quality: 20 printings of 17 cards (M20 Diamond Knight and Icon of Ancestry by record, the compiler's tree) | 11 trees: 6 whole (M20 Diamond Knight, Icon of Ancestry; FDN and M19 Diamond Mare; ORI Prism Ring; KHM Rally the Ranks), 5 partly; the 9 whose reader does not compile are refused (NUMBERS.md 2026-11-13, `reports/chosen_quality_2026-11-13/census.txt`) |
| 2026-11-13, gate round 9 (GO) | FAtom NAME_CHOSEN x `string_value` (the same vocabulary): in a CastSpellEvent `filter` (B17-cast-chosen-counter, frame B13-cast-chosen), an anthem's ALL selector (B17-chosen-anthem), a look's ONE_OF pick (B17-reveal-chosen-type); read only on the object that chose it (CR 607.2d) | cast: M20 Diamond Knight, FDN and M19 Diamond Mare, ORI Prism Ring; anthem: M20 Icon of Ancestry, KHM Rally the Ranks, M15 Obelisk of Urd, ELD and FDN Heraldic Banner, M12 and FDN Adaptive Automaton ("Other"); pick: M20 Icon of Ancestry | cast 4 trees, anthem 7, pick 1 (**low-volume**); 17 more "of the chosen" sentences on 15 printings unread: 14 need a piece (BACKLOG), and KHM Crippling Fear's, Alrund's and IKO Umori's choose at resolution or a card type |
| 2026-11-13, gate round 10 (FIX-THEN-GO, §14) | TriggeredAbility `once_per_event` x ZoneChangeEvent ("whenever one or more <objects> enter / leave <zone>": one trigger for the objects one event moves, CR 603.2c), accepted only where `ability_tree.gathers_occurrences` holds (not on a self or attached subject) | M20 Woodland Champion (compiler, B2b-tokens-enter-that-many-counters; record re-mapped), M19 Desecrated Tomb (compiler, B13-one-or-more-leave-graveyard) | **low-volume**: 2 trees; 4 zone-change "one or more" sentences in the 19 sets (THB Devourer of Memory's clause and KHM Elvish Warmaster's sentence unparsed), none in M21 or FDN (NUMBERS.md 2026-11-13, round 10) |
| 2026-11-13, gate round 10 (FIX-THEN-GO, §14) | Selector(referent="event") under a trigger that gathers objects (`ability_tree.gathers_objects`: a flagged declaration or zone change): every object the event gathered ("they"), the same C2 bytes as "it" | M20 Angelic Guardian (compiler, B2b-attackers-gain-keyword-eot; record re-mapped) | **low-volume**: 1 tree; the census's M21 and ZNR hold none |
| 2026-11-14, gate round 11 (FIX-THEN-GO, §15) | Cost.parts x CostExile, one per cost (`target`: a CHOOSE selector, a literal count, one zone: `Zone(BATTLEFIELD, ANY)` for the source or a permanent the payer controls, the payer's graveyard or hand; the source is `IS_SOURCE` alone, count 1): the source on the battlefield; the source in your graveyard (the ability then works there, CR 113.6m); N [other] [<type>] cards from your graveyard | compiler B13-activated-cost-item: M20 Hanged Executioner (record re-mapped), M11 Brittle Effigy, ELD Inquisitive Puppet; FDN Suspicious Shambler, M15 Soul of Zendikar; DOM Fungal Plots, KHM Egon's back face | 7 trees (5 whole); 50 printed exile cost items in the 19 sets, 22 of them THB escape (`reports/cost_twins_2026-11-14/census.txt`) |
| 2026-11-14, gate round 11 (FIX-THEN-GO, §15) | Cost.parts x CostRemoveCounter, one per kind per cost (`counter_kind` but LOYALTY, `target` the source or a permanent the payer controls, a literal `count`) | M20 Barkhide Troll (record); compiler: ELD Steelbane Hydra, Tome of Legends, M12 Pentavus, M19 Transmogrifying Wand, ZNR Throne of Makindi | 6 trees (2 whole); 25 printed remove-counter cost items |
| 2026-11-17, gate round 13 (pending, §17) | Verb.PERMIT x `source` (ALL over your graveyard, exile, library top or hand; TARGET over a graveyard or exile; the `result` register whole, no filter) x `lands` (True or absent) x `alternative` / `additional` (Costs) x `replace` (`spell_riders()`) x `count` (a literal, resolving only) x `duration` (Eot, UntilEndOfNextTurn, Permanent; required when resolving, absent in a static) | templates_b19 (15 templates): M21 Conspicuous Snoop, Radha, Heart of Keld, Demonic Embrace, both Chandras, Idol of Endurance (b3); FDN Omniscience, Think Twice and the flashback cards, Sphinx of Forgotten Lore, Zul Ashur; records: M20 Golos, Mystic Forge | 33 PERMIT atoms in the 19 sets, records applied (`reports/permit_2026-11-17/`); low volume: `count` 1 (Idol of Endurance), `additional` 1 (Demonic Embrace) |
| 2026-11-17, gate round 13 (pending, §17) | Verb.CAST x `alternative` / `additional` (the old `cost` role split) x `replace` (the rider) | M21 Chandra, Flame's Catalyst's [-2]; ZNR Coveted Prize (b8) | 2 CAST atoms |

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
- R7 round 7 (adversarial, 2026-11-13; one reviewer on d9a8a996, the M20 faults of verification
  wave 1, branch `worktree-agent-a68bbb5431c425326`): **FIX-THEN-GO**, nothing FATAL. Upheld:
  EmblemSpec on GET_EMBLEM (the fewest components: `CardRecord.emblem` and `EmblemAbility` go), a
  new emblem per GET_EMBLEM (CR 114.2; Chandra, Awakened Inferno's ruling), "any number" asked
  with a NONE stop (CR 107.1c), the hand put as `choose:`, the blast radius, the merge.
  - **The change.** `GET_EMBLEM(emblem=EmblemSpec(abilities), controller=who)` replaces C19's
    role-less marker and `CardRecord.emblem` (an emblem's MTGJSON entry attached by name at pool
    compile). The compiler compiles the quote as the emblem's own text; a quote that does not
    compile leaves its sentence unparsed. Each GET_EMBLEM makes a new emblem (the executor's
    one-per-(owner, emblem) table did nothing on a second: pack
    `basri_ket_two_emblems_both_trigger` fails on main 76f46aff). ALL over the top of a library
    reads the open look window, as ONE_OF and REST do, and leaves the rest to REST (Goblin
    Ringleader). No new verb; one field classified, `EmblemSpec.abilities` (IDENTITY).
  - **MAJOR, fixed:**
    - M1. `EachPlayer(ALL_OPPONENTS, GET_EMBLEM(controller=YOU))` built and played as
      `GET_EMBLEM(controller=ALL_OPPONENTS)` does: a second encoding. `EachPlayer.__post_init__`
      refuses a GET_EMBLEM among its own nodes (a granted ability's stays that ability's);
      `test_ability_tree.py::test_each_opponent_gets_an_emblem_has_one_encoding`.
    - M2. GET_EMBLEM's `controller` took every ControllerRef and any player Selector: OWNER
      raised at run time, OPPONENT gave every opponent one with three seats, DEFENDING_PLAYER
      nobody outside combat, a "controller" or "source" referent was a second YOU, an ALL over
      the players a second ANY, and a DEAL_DAMAGE `result` (ORI Chandra, Roaring Flame's natural
      mapping) gave nobody one, as it lists permanents. `Atom.__post_init__` allows
      `ability_tree.EMBLEM_RECIPIENTS` only (YOU, ALL_OPPONENTS, TARGET_OPPONENT, what the 19 sets
      print); another comes with its card.
      `test_get_emblem_refuses_every_other_recipient` (9 cases).
    - M3. An emblem's ReplacementAbility crashed GET_EMBLEM (the replacement registry asked the
      emblem for its controller as of a card), and would never have applied (its liveness gate
      read the battlefield). `ReplacementRegistry.attach_source` takes the emblem's owner as the
      record's controller and `_source_alive` keeps an emblem's records live (CR 114.4): fixed, not
      narrowed, since DOM Jaya Ballard's emblem has one ("If a spell cast this way would be put into
      your graveyard, exile it instead").
      `test_executor_permissions.py::TestEmblems::test_an_emblems_replacement_reads_its_owner_as_you`
      and `..._the_opponent_as_you`.
    - M4. The proposal's "a single-atom player verb names its player in the `controller` role"
      is false for the corpus: DRAW, LOOK_AT/REVEAL, ADD_MANA and the mill lane read one player
      (`selectors.role_player`), CREATE_TOKEN refuses more than one, so verified cards wrap single
      atoms in EachPlayer. The rule is GET_EMBLEM's own: who gets the emblem is its
      `controller`, as LOSE_LIFE's, GAIN_LIFE's and the hand lane's plural `controller` names
      each player they act on; the corpus's two encodings of "each opponent <verb>s" are
      divergence D21 (ATOM_DIVERGENCES), the fold scheduled in the BACKLOG.
  - **MINOR, fixed:** m1, Siege Striker's "you may" around its "any number" tap played as a
    stop at once: B2b-siege-striker drops the OptionalEffect (its tree changes; it leaves the
    verified pool until re-verified); m4, refusal tests for an EmblemSpec holding a spell, an
    "as ~ enters" state, a keyword, a cost modifier or a back face; m5, the §3 count's round; m7,
    executor tests of the recipients with three seats (`TestEmblemRecipients`).
  - **MINOR, in the BACKLOG:** m2, an ALL over the top of a library writes the look window's
    partition state on every read, counts included; m3, ALL's count has two meanings; m4, a
    GET_EMBLEM in a static ability's effect is accepted and never runs; m6, the network does
    not see a player's emblems; m8, `compile_supply` counts an emblem's verbs as its maker's.
  - Pre-gate review (one fresh-eyes reviewer on 09f6078e and 720c13a6), fixed in effadcc9:
    FDN Vivien Reid's -8 had lost the emblem its entry's record attached; a search's exact count
    over another player's hidden zone, and an emblem's choices, were not asked; the bench called
    every NONE "no block". Logged: "any number" over a menu the engine cannot ask takes all of it
    (not live).
- R8 round 8 (adversarial, 2026-11-13; one reviewer on 0be3db11, the life family, §12, branch
  `worktree-agent-aa99e614a0d6abc56`): **FIX-THEN-GO**, nothing FATAL. Upheld in the reviewer's
  own runs: the CR reading (one loss is one source's damage at once, or one effect's or payment's
  loss, CR 120.3a, 119.3, 119.4; the payment case; a loss before the permanent arrived uses up the
  turn), the `ordinal` design (counted at match time, nothing stamped on the journal),
  LIFE_TOTAL_GE beside LIFE_LEAD_OVER_START_GE (F11 deferred), the one-tree B14 claim, and the
  blast radius (11 trees, 0 verified in or out, 300/300 replays).
  - **The change.** `FAtomPred.LIFE_TOTAL_GE(who, count)` (R8-1); `ordinal` on LifeGainedEvent
    and LifeLostEvent (R8-2); a replaced gain's amount published to the replacement's action
    (R8-3). One new FAtom predicate, one field on two event classes (OPERATOR, §3), no verb.
  - **MAJOR, fixed:**
    - M1. `LIFE_TOTAL_GE.who` admitted three byte forms of one meaning: TARGET_PLAYER,
      TARGET_OPPONENT and Selector(referent="target") read the same "target" binding (D18 in a new
      slot), and a TARGET_* in a filter never designates (the designation scans read only
      CONTROLLER_IS), so "if target opponent has 10 or less life" would have reached resolution
      with no target chosen. Every compiled use is YOU and no card of the 19 sets reads another
      player's life total: `FAtom.__post_init__` refuses any `who` but YOU, and another value
      comes back only with a card and its tests. 0be3db11 built TARGET_PLAYER, TARGET_OPPONENT and
      the referents target, event and result; the branch builds YOU only.
      `test_executor_life_family.py::test_life_total_refuses_what_has_no_meaning` (13 `who` forms
      refused; they fail on 0be3db11).
  - **MINOR, fixed:**
    - m1. PREVENT_EFFECT's `event` role took an event with an ordinal, which no prevention lane
      reads: `AtomArgs` refuses it. `test_an_ordinal_is_read_only_by_a_trigger` (resolving and
      static, the four ordinal classes; they fail on 0be3db11).
    - m2. The round is R8 (the emblem branch merged as round 7): §12 and R8-1..3, F11, the NUMBERS
      header, the BACKLOG, the test module, the three M20 records' notes.
    - m4. The lifelink BACKLOG entry completed: outside combat a life-gain replacement makes each
      per-target gain its own boundary, so the rows do not merge (a lifelinker dealing 1 to each of
      two creatures beside Angel of Vitality and Ajani's Pridemate: 24 life where the rules give
      23, 2 rows, 2 counters), and the newly whole trees inheriting the fault are named, none to be
      stamped verified before the fix: FDN Drogskol Reaver, M14 Archangel of Thune, Twinblade
      Paladin and Angel of Vitality (M20, FDN).
    - m5. "As long as" on a self static has two encodings: the static's `condition` (14 statics,
      B14's among them) and a DurationWhileCondition on the atom, in five verified trees where the
      review named two (M21 Predatory Wurm, Sigiled Contender; the M20 records Celestial Messenger,
      Vivien's Crocodile, Unchained Berserker). Divergence D22, the fold scheduled in the BACKLOG.
    - m6. B14's keyword grants followed printed order: they are sorted (one static's effects share
      a timestamp, CR 613.7). 0 trees change: no B14 static in the 19 sets grants two keywords. Six
      trees of other templates keep printed order: divergence D23, folded with D22.
      `test_a_static_grants_its_keywords_in_one_order` (fails on 0be3db11).
    - nit. §12's reason for rejecting a once-each-turn flag is now the one-representation rule:
      "the Nth event this turn" is already `ordinal`.
  - Blast radius of the fixes (the merge f8dc201d against them, 19 sets, every record applied): 0
    trees changed, 0 verified cards in or out (M21 271, M20 261, FDN 177). The branch against
    main 8f7b3774: the same 11 trees, 8 whole.
  - **The lifelink fault, fixed in its own commit** (the reviewer's instruction; §12 R8-4): one
    lifelink source's damage dealt at once is one life-gain event whatever the number of
    recipients, several sources several. Cause: the gain was made per recipient, per target in
    `verbs._v_deal_damage` and per (dealer, recipient) atom in `Executor._damage_wave`, and a
    life-gain replacement made each per-target gain its own boundary. Fix: one gain per atom,
    and per combat dealer in its last atom. The reviewer's three cases are tests failing on
    46aa2f3e, with two packs.
    Blast radius: no tree changes; in 1,500 seeded games on the verified pools, 17 combat damage
    steps (17 games) had a lifelink dealer with two or more recipients and now journal one gain
    row; play differs in 3 games, where M21 Vito, Thorn of the Dusk Rose and FDN Ajani's Pridemate
    and Marauding Blight-Priest trigger once instead of once per recipient. Same winners, 0
    crashes.
- R9 round 9 (adversarial, 2026-11-13; one reviewer on 469018ed, a quality chosen as a permanent
  enters, §13, branch `worktree-agent-a22ab085e5a636947`): **GO**, nothing FATAL or MAJOR. Upheld
  in the reviewer's own runs: the CR reading (614.12a, 607.2d, colourless refused, the last known
  choice per 113.7a and 608.2h), the fewest components, `string_value` with one meaning within
  NAME_CHOSEN, the rename deferred (F12), the bitwise claim on r28's checkpoint (260 decisions,
  fp32 and bf16), the load paths, the ask kind grown from `other`, the blast radius, 210/210
  replays, and a clean merge with main. The round merges before round 10.
  - **The change.** `Verb.CHOOSE_NAME` takes an optional closed role `quality` (COLOR,
    CREATURE_TYPE; absent, a card name), `FAtomPred.NAME_CHOSEN` reads it back in `string_value`
    (one role, one slot vocabulary, no verb, predicate or field). `chosen_quality_fault` refuses
    per object (CR 607.2d) a read without its choice, an unread choice, two choices of one
    quality, a read on another object (a PROTECTION quality judged in the granter's
    coordinates), a quality chosen outside an EtBState's own effect, and a choice in a static;
    EtBState keeps an effect in a node of its own. Engine: choices keyed (source, quality), kept
    in the source's last known information; WUBRG and the pool's creature types; every choice
    before any gate or entering counter (CR 614.12a). Compiler: B17's four templates and frame
    B13-cast-chosen. Network: the ask kind `quality` (grown from `other`), C_CHOSEN and O_VALUE
    masked at 0.
  - **Rejected:** a verb and a predicate per quality; a NAME value; the policies' `scope` role; a
    new FAtom field; granted triggers made by an enters trigger; a missing choice read as False;
    CR 205.3m's whole list as the menu; the rename now (F12).
  - **Blast radius** (on main 8db1834f and the merged branch): 20 trees changed, all unverified
    (6 whole, 5 partial, 9 refused); 0 verified in or out (M21 275, M20 273, FDN 183); Runed Halo
    and Necromentia byte-identical; 300/300 replays identical, 0 crashes; soak 800 games, 0
    crashes; old networks bitwise exact; `state_fingerprint` bytes differ on states holding a card
    name's choice (m3). The pre-gate review (3 MAJOR, 3 MINOR) is in §13.
  - **MINOR, fixed:**
    - m2. The creature-type menu (CR 205.3e/m: any creature type) missed the types a pool's
      cards grant: `Supply.creature_types` adds GRANT_TYPE's creature types
      (`quantity.granted_creature_types`; M21 Riddleform's Sphinx, M21 73 -> 74).
      `test_a_creature_type_is_one_of_the_format_pools`. Both menus, round 4's `name_pool` too,
      are registered scaffolds (BACKLOG "Scaffolds to remove").
    - m3. Declared in §13's blast radius: `state_fingerprint` folds `(s, 'None', n)` for a card
      name's choice where main folded `(s, n)`.
    - m4. F12: `string_value` is NAME_CHOSEN's quality slot for good, so the rename is a pure
      relabel; F12 placed after F11.
    - m5. Registered as F13: "choose a colour" has two forms by context (a resolution-time
      `Choose` over five, CHOOSE_NAME(COLOR) as a permanent enters), and KHM Crippling Fear and
      Haunting Voyage need a resolution-time creature type, which refusal 5 forbids; decided by
      the round that maps them.
    - m6. The canonical form of "This land enters tapped. As it enters, choose a color." (KHM
      Shimmerdrift Vale, FDN Uncharted Haven) is two EtBState nodes: EtBState refuses an effect
      beside a tapped flag, counters or a gate (it subsumes round 9's pre-gate refusal of a
      choice under a gate). `test_an_as_enters_effect_stands_in_its_own_node`; 0 trees change.
    - m7. `simulator.load` did not grow an older checkpoint (runs/window1/sim.pt: 30 ask rows,
      22 global columns; gate B's queue loads it with `--search-sim`), on main too: it grows
      the view network as `model.load` does (`model.upgraded`, shared), and `Data.load` widens
      each view shard to this code's widths. `test_an_older_simulator_and_its_view_shards_load`
      (red on main 8db1834f and on 92aca048).
    - m8. Tests added: a granted PROTECTION reading the chosen colour, before and after its
      granter left; a creature-type read through a GRANT_TYPE overlay; card-level refusals for
      a printed non-protection keyword's parameter and for a back face; the bench's `quality`
      prompt, colour labels and leak flag.
  - **NITs:** n1 fixed (a read with no source raised AttributeError, not NotImplementedError:
    the last-known fallback needs a source); n2 (C_CHOSEN holds one value per permanent), n3 (a
    tripwire: colours are the printed ones) and n4 (a tripwire: a copy that entered without
    choosing reads False, per the rulings, when copies land) in the BACKLOG.
- R10 round 10 (adversarial, 2026-11-13; one reviewer on 88b7f7e8, one or more objects moved at
  once, §14, branch `worktree-agent-ac4c978225fb5b805`): **FIX-THEN-GO**, nothing FATAL. Upheld in
  the reviewer's own runs: the CR reading (one atom boundary is one event for a wrath, one
  effect's tokens and a state-based sweep; two instructions are two events; "that many" counts
  the departed objects, Woodland Champion's and Basri Ket's rulings), `gathered` replacing
  `declare_attackers` with no change in play (Basri Ket, Feline Sovereign and Ancestor Dragon
  identical; 90 seeded games identical), not refusing the flag where nothing reads the set
  (Desecrated Tomb), the blast radius (3 trees, 0 verified in or out) and a clean merge with main.
  - **The change** (kept by the gate). `once_per_event` on a ZoneChangeEvent gathers the objects
    one atom boundary moves (CR 603.2c; `GameEvent.batch`, outside the dump; a drawn card its
    own, CR 121.2); `gathers_occurrences` admits it where the subject is not the source or what
    it is attached to. On a flagged declaration or zone change (`gathers_objects`) the event
    register holds every object gathered: "they" is Selector(referent="event"), "that many"
    QProp("event", THAT_MANY_COUNT) through a `gathered` register that replaces round 4's
    `declare_attackers`, "among them" an aggregate or a filtered count over the referent. No new
    node, field or verb. Templates: B2b-tokens-enter-that-many-counters (Woodland Champion),
    B2b-attackers-gain-keyword-eot (Angelic Guardian), the frame B13-one-or-more-leave-graveyard
    (Desecrated Tomb); none for Elvish Warmaster, whose head without its once-each-turn limit
    loops. Rejected (§14): a new flag, field, node or referent; QCount of the referent for "that
    many"; the batch in the row's `data`; one event per op; gathering at `_put`; "that many"
    reading `event`; gathering a dies or a sacrifice event; every referent naming every bound
    object.
  - **Pre-gate review** (one fresh-eyes reviewer on 8b8c35b9, fixed in 88b7f7e8): FATAL, "that
    many" looked up an object first (M21 Basri Ket's -2, verified, crashed when its one attacker
    died in response); MAJOR, single-object reads of a gathered register were accepted (a FIRST
    over a referent Selector, a token's power, a subject-testing condition, "until it leaves",
    "it deals", FIGHT's foe, a bare Conditional): refused, or a run-time net; MINOR, D24; MINOR,
    the Warmaster frame (dropped).
  - **MAJOR, fixed:**
    - M1. A flagged leave trigger reading "the greatest power among them"
      (QProp(Selector(referent="event"), POWER, MAX or SUM), a form the IR keeps) crashed with
      KeyError when two tokens left in one atom: `pending_references` kept only the queuing
      row's object, so `_cease_tokens` removed the other while "they" still named it; and a
      departed creature card was read in its graveyard, without the counters it died with, not
      by its last known information (CR 608.2h). Fix: the pending references hold every gathered
      object; "they" are those the effect can act on (not one that changed zones since, CR
      400.7; not one moved into a hand or a library, the rule's exception reaching public zones
      only; not a token off the battlefield, CR 111.7, 111.8); "among them" and a filtered count
      of them read every object gathered (`quantity.read_population`), each by its last known
      information once it left (`departed_lki` finds its own departure row). Found beside it:
      MOVE_ZONE's own count clamp moved the first of "them" only (`verbs._v_move_zone`), fixed.
      Tests failing on de676db0 (88b7f7e8 with main merged): the two tokens with MAX (the
      KeyError) and with a filtered SUM, the two creature cards ([2] where the rules give 3, then
      one exiled of two), "they" not found in a hand, a count among them. The fix's first version
      also looked a gathered row up from a query, which has no event, and crashed 7 of 100 FDN
      replays (Battlesong Berserker's target among its attackers): caught by the replays before
      a commit, guarded, and pinned by a test on the real card.
  - **MINOR, fixed:**
    - m1. One instruction run once per player through EachPlayer is several events (CR 101.4
      makes it one): recorded in §14's limits and the BACKLOG with its fix (one batch for the
      sub-executions of one EachPlayer); `eachplayer_split.py` gains 1 twice where the rules
      give 2.
    - m2. A gathered holder leaving with its objects is all or nothing by handle order: added to
      the BACKLOG's row-order entry; `holder_leaves_with_them.py` gains nothing where CR 603.10a
      gives 3.
    - m3 (D24). `_check_once_per_event` refuses the flag on a zone change from the battlefield to
      a graveyard whose subject requires a creature, CreatureDiesEvent's meaning; 0 trees change.
      `test_one_or_more_creatures_dying_is_not_a_zone_change` (fails on de676db0).
    - m4. Tests pinning what 88b7f7e8 did: the CR 400.7 check of "they" on a zone change (it
      kills the mutant that drops the check, which only the declaration's pack did), a batch of
      matching and non-matching rows, two 0/0 tokens dying in the check after they enter
      ("that many" 2: the gather is not at `_put`).
    - m5. DESTROY against indestructible, fixed on main 8db1834f: the BACKLOG entry is closed,
      NUMBERS updated, and the pack `angelic_guardian_attackers_survive_a_wrath` (Planar
      Cleansing after the Guardian's trigger) added.
    - m6. A ZONE_CHANGE row without a batch raises in the journal (`EventJournal._emit`), and so
      does gathering one (`_occurrences`). `test_a_zone_change_without_a_batch_fails_loudly`
      (fails on de676db0).
    - G3 (merge condition 5). No dead-role or equivalence rule absorbs "each occurrence <-> once
      per event" on a zone-change trigger: the 20 verified stamps predate the mutant, a
      re-verification needs a pack moving two objects at once, and the probe stimulus stays a
      BACKLOG item (§14).
    - Nits. The census adds IKO Rielle, the Everwise (5 sentences, not 4). The flag on an
      IS_RESULT, IS_ANY_TARGET or referent FAtom subject stays: each can name several objects
      (§14). The QCount refusal is narrowed to an unfiltered referent count, so "for each
      creature card exiled this way" keeps its one encoding, a filtered referent count (IS_RESULT
      in a selector's filter is refused as the referent's second form); MAPPER_GUIDE names it.
    - The section is §14 (round 9 is §13).
  - **Blast radius of the fixes** (de676db0 against them, by script, 19 sets, every record
    applied): 0 trees changed, 0 verified cards in or out (M21 275, M20 273, FDN 183); 300
    seeded heuristic games (M21, M20, FDN) with identical replay digests and journal dumps, 0
    crashes; the soak (500 games dealing the round's trees) line for line the same, 0 crashes;
    G3 occurrence mutants 8 -> 28 as before; 19 of 19 engine mutants killed. Against
    30fabc4a: the same 3 trees as the round. Merged with main c164cd34 (round 9), against it:
    the round's 3 trees, 0 verified cards in or out, 300/300 identical replays, 0 crashes.
  - **Found, logged, not fixed here** (BACKLOG): permanents moving in one atom see each other's
    moves only in row order (CR 603.6a, 603.10a), a holder leaving with them included; one
    EachPlayer instruction is several events (CR 101.4); a per-object trigger's "it" follows an
    object that changed zones (CR 400.7); a referent over a several-object `result` or `target`
    register takes the first. Closed on main: DESTROY against an indestructible permanent
    (8db1834f).
- R11 round 11 (adversarial, 2026-11-14; one reviewer on f242ad43, the cost twins, §15, branch
  `worktree-agent-ab5f3aadf2f65ed6e` on 1d5e4164): **FIX-THEN-GO**, nothing FATAL, nothing MAJOR;
  ledger F3's "Keep" holds (`CostExile` and `CostRemoveCounter` join the cost union, no fold). The
  reviewer merged main 4da972f1 cleanly, green; their mutant battery killed 15 of 19.
  - **Merge conditions, fixed** (2026-11-17, with main 4da972f1 merged):
    - M1. §15 and NUMBERS restated for the merged tree. "CR 117.12" does not exist (rule 117 ends
      at 117.7): claim 4 rests on 117.3c and 601.2h, whose new first step pays the costs with no
      random element and no move from a library to a public zone first. The stamps: 1,144 = 736
      home stamps (M21 275, M20 277, FDN 184) and 408 reprint stamps in 17 sets (6 of them in
      FDN, 190 in all). 20 reprint stamps of 2026-11-14 (FDN homes) recorded 0 mutants made under
      the G3 bug, where §15 said no stamp did; not stamped again here, the coordinator runs their
      verify again after the merge (the reviewer's fixed G3 with their home packs uncovered no
      critical survivor).
    - M2. The IR accepted cost objects the payer does not control, and the plan paid with them (an
      exile of the opponent's creature or of a card from their hand, the removal of their
      counter), and forms that mean nothing or say one thing twice ("this creature" twice, the
      source over `Zone(BATTLEFIELD, YOU)`, D25's `FAnd(CONTROLLER_IS YOU, IS_SOURCE)`, two
      zones). `_check_cost_designation` now takes one zone of `Zone(BATTLEFIELD, ANY)`,
      `Zone(GRAVEYARD, YOU)`, `Zone(HAND, YOU)` (a removal the first), the source as
      `FAtom(IS_SOURCE)` alone with a count of 1, and another permanent only with
      `CONTROLLER_IS YOU`. No tree had another form (the 19 sets' tree dump byte-identical before
      and after); a refusal test per form.
    - M3. Two exile segments of one cost over one pool: a payable cost refused (the plan's greedy
      witness) and a partial payment through the asks. One cost holds at most one CostExile and
      one CostRemoveCounter of a kind (`Cost.__post_init__`); `_ask_cost_choices` raises on a
      segment the payer's earlier picks left short (every lane); divergence D26, beside D10. The
      plan's bookkeeping across two such segments, unreachable now, is gone.
    - M4. A frame test for "Remove three charge counters" (count 3: M17 lived). M9 (the payer's
      exile) is an equivalent mutant: the world files a card leaving for any zone but the
      battlefield under its owner; a stolen creature's own exile cost pins it. M11 and M14 are
      equivalent too (§15, "Gate round 11's mutants").
    - M5. A tripwire, `test_only_relic_amulet_gives_a_charge_counter_and_only_to_itself`: it
      fails when a tree of any set gives a charge counter another way, before ZNR Throne of
      Makindi's or M19 Transmogrifying Wand's partial tree could pay its cost.
    - Nits. "The owner's exile (CR 400.3)": exile is one shared zone (400.1), the world keeps
      owners' slices of it; §15's Rejected list gains the signed counter part; the source
      exclusion's strictness is noted (no card of the 19 sets has the shape).
  - **Blast radius of the fixes**: 0 trees changed (the tree dump of the 19 sets byte-identical
    before and after them on the merged tree). Against main 4da972f1: the round's 12 compiler and
    13 record trees, 0 verified cards in or out of 1,144; 600 seeded heuristic games (200 each,
    M21, M20, FDN; 275, 277 and 190 deckable): 600/600 identical replay digests, journal dumps and
    raw event logs, 0 crashes either side (`replay_4da972f1.txt`).
- R13 round 13 (adversarial, 2026-11-17; one reviewer on f01b303f, Verb.PERMIT, CAST's cost
  roles and the spell's rider, §17, branch `worktree-agent-a4af16b825120dda1` with main fdd1a021
  merged; a fresh-eyes review of the code diff before it: §17): **FIX-THEN-GO**. Fixed:
  - MAJOR: seven forms the IR accepted said nothing or what another form says
    (`gate13/ir_forms.py`): `lands` over the hand; a resolving PERMIT over ALL(IS_SOURCE), which
    played wrong (the card cast and back in the graveyard is a new object the population covers
    again, CR 400.7, castable again that turn); a cast PERMIT filtered FNot(Land); a lands-only
    and a cast PERMIT over one zone in one ability (one PERMIT with `lands`); a CAST of a TARGET in
    a library or a hand (CR 400.2); a card's own alternative cost from the hand as its own static
    PERMIT. Refused (`_cast_roles_fault`, `_cast_verb_misplaced`, `_split_play_fault`), one test
    each (`test_the_gate_13_forms_are_refused`). The last stays a SpellAbility piece, as §17 said:
    a spell's alternative cost (CR 118.9) applies wherever it is cast from, a permission over the
    hand only from the hand, so the two are not one meaning. MAPPER_GUIDE's own-permission rule
    says "a static, never over your hand".
  - MINOR: four surviving mutants that change play, each killed by a test: M6 (a static covering
    every zone), M7 (the opponent's permission yours), M8 (a counted play spent first), M10 (no
    rider on a fizzle).
  - Flashback's exile fired only on resolution, a fizzle and a counter; and, the same cause, a
    pre-existing EXPLOITABLE fault (a bug-hunt fault, KNOWLEDGE 212): an effect that moved a spell
    off the stack left its frame, so Unsubstantiate (M21, verified) on your own Shock returned the
    card to hand and the Shock still resolved. Every move of a spell off the stack now ends its
    frame and passes its rider (`verbs._off_the_stack`, `_spells_leave_the_stack`); a pack
    through the menu (`unsubstantiate_your_own_shock_never_resolves`, red on main) and
    `test_executor_off_the_stack.py` (exile, a library, a creature spell, both riders).
  - MINOR: BACKLOG's D32 deferral entry; Valakut Exploration's pools; §5's low-volume roles.
- BINDING STATE: rounds 1–11 complete; further ontology changes
  require a NEW gated round (any R-item that reclassifies a field or opens a normalization is
  Type-1).

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
| R5-2, R5-3, R5-12's rider | **built as ontology round R13** (§17, 2026-11-17): one verb, PERMIT, with `lands`; the rider a cast verb's `replace` role; gate round 13 pending |
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

## 12. Round R8 — the life family (2026-11-13; gate round 8 FIX-THEN-GO, fixed: §9)

The card backlog's wave 3, ranked first by its planning census: M20 Twinblade Paladin, Angel of
Vitality and Vengeful Warchief, with reach in M11, M14, ZNR and FDN. Census, blast-radius scripts
and base runs: `reports/life_family_2026-11-13/`. Tests: `MTG_bot/core/test_executor_life_family.py`.

**R8-1 `FAtomPred.LIFE_TOTAL_GE(who, count)`: your life total now is at least `count`
(CR 119.1).**
- Slots: `count` and `who`, both required (FAtom checks `count` itself, as EVENT_THIS_TURN's: the
  generic loop never checks it). A negative literal is refused by QConst.
- `who` is YOU, every compiled use; any other value is refused (gate round 8, M1). Another one
  comes back only with a card that prints it, and its tests:
  - over several players (OPPONENT, ANY, ALL_OPPONENTS, DEFENDING_PLAYER) the slot would need a
    quantifier, and "N or less life", which is FNot(LIFE_TOTAL_GE(N + 1)) and never a second
    predicate, would read "each of them" where "an opponent has N or less life" means one;
  - TARGET_PLAYER, TARGET_OPPONENT and a referent "target" read one binding, three byte forms of
    one meaning (D18 in a new slot), and a TARGET_* in a filter designates nothing: the
    designation scans read only CONTROLLER_IS, so "If target opponent has 10 or less life" would
    reach resolution with no target chosen;
  - the referents "source" and "controller" name you again (CR 113.8).
- It reads no subject: in `ontology_conformance.SUBJECT_FREE`, one qualifier slot per event class
  (§11 R6-2). Every compiled use is a static's condition.
- Compiler: `conditions.py` reads "you have N or more|less life" (the FNot rule in code). B14 reads
  "as long as <condition>, this creature gets +P/+T [and has <keywords>] | has <keywords>" either
  way round, one tree, Thieves' Guild Enforcer's effect byte for byte. Its keyword grants are
  sorted (gate round 8, m6): one static's effects share a timestamp (CR 613.7), so "flying and
  lifelink" and "lifelink and flying" are one tree. Other templates keep printed order (D23).
- Census: 7 sentences print an absolute threshold, 5 of them compile (Twinblade Paladin and Angel
  of Vitality in M20 and FDN, M11 Serra Ascendant). M13 Elderscale Wurm's two also need a damage
  floor and a set-life verb. 11 more sentences on 10 cards are relative to the starting life total.
- **Not a second encoding of LIFE_LEAD_OVER_START_GE.** That one reads the lead over the starting
  life total, which is 40 in Commander and 25 in two-player Brawl (CR 103.4). Angel of Vitality's
  ruling: "In formats where your life total doesn't start at 20, ... still applies if your life
  total is 25 or more." Fold candidate F11 (§4) when a starting-life quantity lands.
- Rejected:
  - LIFE_LEAD_OVER_START_GE(count - 20): wrong in Commander.
  - A comparison over QProp(controller, LIFE): QProp reads only the ability's controller, and a
    general "quantity >= quantity" atom would subsume a dozen *_GE predicates, a fold round of its
    own.
  - No `who` (LIFE_LEAD_OVER_START_GE's choice): kept, closed to YOU, so another player's life is
    a value of the slot when its card comes, not a second predicate.
  - A DurationWhileCondition on the atom: "as long as" is the static's condition. Five verified
    trees still write it on the atom (divergence D22, fold scheduled).

**R8-2 `ordinal` on LifeGainedEvent and LifeLostEvent (CR 603.2).**
- CardDrawnEvent.ordinal's contract, one helper for all four ordinals
  (`ability_tree._check_ordinal`): the Nth such event of that player this turn, an int >= 1; absent
  means every event. Serialization omits it when absent: no tree's bytes change.
- Only the trigger binder reads it (`binding._life_ordinal`). It counts at match time, over the
  row's own turn back to its upkeep marker, events from before the permanent arrived included
  (Vengeful Warchief's and Attended Healer's rulings). It stamps nothing on the journal: the rows,
  the journal dump and every replay fingerprint keep their bytes.
- A turn-history atom (EVENT_THIS_TURN, SUBJECT_OF_EVENT_THIS_TURN), a ReplacementAbility and an
  Atom's `event` role (PREVENT_EFFECT, gate round 8, m1) refuse an event with an ordinal, for all
  four classes. A history count says how much happened, so an ordinal there is a second byte
  form of the count or a reading no card prints. No replacement or prevention lane counts
  events. 0 trees of the 19 sets did any of it.
- **One event.**
  - A gain is one LIFE_GAINED row: one source causing it at once (CR 119.9). Two lifelinkers
    dealing combat damage together are two.
  - A loss is one LIFE_LOST row (an effect's loss or a payment, CR 119.3, 119.4), or one player
    DAMAGE row (one source's damage, CR 120.3a).
  - Several creatures that damage a player in one combat damage step are that many losses, dealt
    at once (CR 510.2), of which exactly one is the first: "the first time each turn" triggers
    once.
  - One lifelink source's damage dealt at once is one gain, whatever the number of recipients
    (CR 120.3f, 119.9 and the rulings): R8-4. Still a gap (BACKLOG): a lifelink source damaging
    its own controller leaves no row.
- Compiler: one life-trigger head, `templates_b9.LIFE_TRIGGER_RE` and `life_event`: "When|Whenever
  you gain|lose life [for the first time each turn | for the first time during each of your
  turns]". B9's +1/+1-counter template and the frame B13-life (any clause that parses alone) share
  it. "During each of your turns" puts TURN_OF YOU in `actor`, the event's one qualifier slot.
- Census: 6 sentences on 6 cards, 4 compile (M20 Vengeful Warchief; ZNR Attended Healer, Cleric
  of Life's Bond; FDN Cat Collector). FDN Vanguard Seraph needs surveil, ELD Deathless Knight its
  "return this card from your graveyard".
- Rejected:
  - A once-each-turn flag on the ability: "the Nth event this turn" already has one
    representation, `ordinal`; a flag would be a second (and it would also miss the rulings: a
    loss before the permanent arrived uses up the turn).
  - The trigger condition: read again on resolution (CR 603.4), and §11 R6-2 keeps qualifiers out
    of it.
  - EVENT_THIS_TURN in `actor`: it sums amounts and counts the row being matched, so a first loss
    of 3 cannot be told from a second.
  - Stamping the ordinal on the journal rows as CARD_DRAWN does: a player DAMAGE row's `data[1]` is
    its combat step, and every journal dump would change.

**R8-3 A replaced gain's amount (an engine fix, no IR change).**
- `verbs._v_gain_life` queues (record, player, amount). The executor's drain binds the player as
  `event` and publishes the amount as `event_amount`, so Angel of Vitality's GAIN_LIFE(QBin(ADD,
  QProp(event, AMOUNT), 1)) reads the replaced gain (CR 614.6), Conclave Mentor's shape on the life
  lane. Before, the action raised: no event register.
- A gain of 0 is no life-gain event, and nothing replaces it (CR 119.10).
- Two Angels chain through the CR 614.5 guard: +2, as their ruling says.
- Compiler: B5b "If you would gain life, you gain that much life plus N instead." (Angel of
  Vitality in M20 and FDN).
- Left out: "you gain twice that much life" (M13 Rhox Faithmender, ORI Alhammarret's Archive).
  Beside a "+1" it needs the CR 616.1 order choice, which the life lane does not ask (BACKLOG).

**R8-4 One lifelink source's damage dealt at once is one life-gain event (an engine fix, no IR
change; gate round 8 asked for it in its own commit).**
- The rule: damage dealt by a source with lifelink makes its controller gain that much life (CR
  120.3f, 702.15b). The rulings of Ajani's Pridemate, Angel of Vitality and Twinblade Paladin: a
  single lifelink creature dealing combat damage to several recipients at once (trample, two
  blockers) is one event, "the ability will apply only once"; each lifelink creature is a separate
  event.
- The cause: the gain was made per recipient. `verbs._v_deal_damage` gained after each player it
  damaged and `_deal_damage_to_card` after each card. Outside combat one atom's gains then merged
  in the journal's per-atom life diff (`EventJournal.record_atom`), unless a life-gain replacement
  consumed them: each per-target gain queued its own replacement, whose action the executor's
  drain runs as its own boundary, so Angel of Vitality added 1 per recipient and each gain was its
  own row. In combat `Executor._damage_wave` runs one DEAL_DAMAGE atom per (dealer, recipient),
  each its own boundary, so a trampler and its blocker made two rows. The per-atom life diff is
  not itself the cause: it writes one row per player per atom, and after the fix one atom holds a
  source's one gain (its own fault, a player damaged and gaining in one atom, is the BACKLOG's
  net-life entry).
- The fix: `_v_deal_damage` sums what one atom dealt to all its recipients and gains once, after
  them; `_deal_damage_to_card` returns the dealt amount and gains nothing; a fight gains per blow,
  each fighter its own source. In combat the wave gives a dealer's earlier atoms
  `ExecCtx.lifelink_held`, where each leaves what it dealt, and its last atom `lifelink_carried`,
  their sum: the dealer's one gain lands in its last atom's boundary, the row's shape unchanged
  (cause the dealer, verb DEAL_DAMAGE, or the replacement's GAIN_LIFE). A dealer with one
  recipient, a one-target atom and a fight run as before, event for event.
- Tests, each failing on 46aa2f3e (the round's fixes): a trampler over a 0/2, with and without
  Angel of Vitality; a lifelinker blocked by two 0/2s; one DEAL_DAMAGE of 1 to each of two
  creatures beside the Angel and Ajani's Pridemate (23 life, one row, one counter, no trigger
  order to ask); the controls, two lifelinkers at once and a double striker, pass on both
  (`test_executor_life_family.py`). Packs `mapped/FDN/ajanis_pridemate_one_gain_per_lifelink_source`
  (two lifelinkers, one of them trampling over a 0/2: 2 counters, 3 on 46aa2f3e) and
  `mapped/M20/angel_of_vitality_and_twinblade_one_gain_for_a_trampler` (26 life and 1 counter, 27
  and 2 on 46aa2f3e).
- Blast radius (`reports/life_family_2026-11-13/lifelink_blast_radius.txt`): no tree changes.
  1,500 seeded heuristic games on the verified pools (500 each; M21 271, M20 261, FDN 177
  deckable), 46aa2f3e against the fix: 17 combat damage steps, in 17 games, had a lifelink dealer
  with two or more recipients (M21 7, M20 1, FDN 9: Blood Glutton, Basri's Acolyte, Baneslayer
  Angel, Cavalier of Night, Ajani's Pridemate and FDN creatures granted lifelink). Their journals
  differ, the dealer's gains now one row; the other 1,483 journals are identical. Play differs in
  3 games, where a verified card reading life gain triggered once per recipient and now once: M21
  Vito, Thorn of the Dusk Rose; FDN Ajani's Pridemate and Marauding Blight-Priest (one game two
  turns longer, 13 -> 15). Same winners; 0 crashes either side.

**Blast radius** (by script over the 19 sets, `reports/life_family_2026-11-13/`):
- trees changed: 11, all unverified. M20 Twinblade Paladin, Angel of Vitality and Vengeful Warchief
  (needs-atom records re-mapped to the compiler's tree); FDN Twinblade Paladin, Angel of Vitality,
  Cat Collector and Drogskol Reaver; M11 Serra Ascendant; M14 Archangel of Thune; ZNR Attended
  Healer and Cleric of Life's Bond. 8 of them now compile whole.
- 0 verified cards leave or join the verified pool; the stamps match (M21 273, M20 261, FDN 177).
- Still-verified cards with unchanged bytes that read a touched path: the 8 with a life trigger
  and no ordinal, whose binder lane is unchanged for them.
- The V4′ CHOOSE baseline gains Cleric of Life's Bond's self-selector (IS_SOURCE, no decision). No
  new branching row (the uncapped census: one existing row's count, 83 -> 84).
- 300 seeded heuristic games (100 each, M21, M20, FDN), decks from the cards verified on both:
  300/300 identical digests, 0 crashes either side.
- Random-play soaks that deal the new trees (M20 with the unverified records, FDN, ZNR, M11; 700
  games): 0 crashes, 0 detector hits; each family card in those pools was cast in 2 to 33 games
  (not M14 Archangel of Thune, M14 deals no deck, nor FDN Cat Collector, still partly compiled).

## 13. Round R9 — a quality chosen as a permanent enters (2026-11-13; gate round 9 GO)

The card backlog's wave 3, second item: M20 Diamond Knight ("As this creature enters, choose a
color. Whenever you cast a spell of the chosen color, put a +1/+1 counter on this creature.") and
Icon of Ancestry ("As this artifact enters, choose a creature type. Creatures you control of the
chosen type get +1/+1. {3}, {T}: Look at the top three cards of your library. You may reveal a
creature card of the chosen type from among them ..."), needs-atom records since 2026-11-05.
Census, blast-radius scripts and base runs: `reports/chosen_quality_2026-11-13/`. Tests:
`MTG_bot/core/test_executor_chosen_quality.py`, `MTG_bot/core/compiler/test_templates_b17.py`, three
in `tools/selfplay/test_selfplay.py`, one in `tools/cards/test_gates.py`; packs in
`tools/scenarios/mapped/M20/` and `mapped/FDN/`.

**R9-1 One role and one slot on round 4's pair: no new verb, predicate or field.**
- The rules. "As [this permanent] enters, ..." is a replacement effect (CR 614.1c), and a choice it
  requires is made before the permanent enters (614.12a). "Choose a [value]" and "the chosen
  [value]" printed on one object are linked abilities: the second refers only to a choice made as
  a result of the first (607.2d). A colour is one of the five (105.1; colourless is none, 105.2c),
  a creature type one of 205.3m's.
- The IR. `Verb.CHOOSE_NAME` takes an optional `quality` role from the closed
  `ability_tree.CHOSEN_QUALITIES` = (COLOR, CREATURE_TYPE); `FAtomPred.NAME_CHOSEN` reads it back
  with the same vocabulary in its `string_value` (`_FATOM_STRING_VOCAB`, STACK_KIND_EQ's closed
  slot). Absent in both is a card name: Runed Halo's and Necromentia's bytes do not change, and
  there is no NAME token to be a second form of absent. An FAtom slot means what its predicate
  says (`_FATOM_RULES`): within NAME_CHOSEN `string_value` has the one meaning, the quality read,
  and it stays NAME_CHOSEN's quality slot for good, so the rename is a pure relabel (F12; the
  pre-gate review's point, settled at gate round 9).
- Refused as the tree is built (`ability_tree.chosen_quality_fault`, from CardRecord; the compiler
  raises it as a shape gap, StateCorruptionError, so a partly compiled card never stops a set):
  1. a value outside the vocabulary, in either place;
  2. `quality` on any other verb (the role table), and beside `name_filter`;
  3. a NAME_CHOSEN of a quality (a card name included) with no CHOOSE_NAME of that quality on its
     own object; a CHOOSE_NAME nothing on its object reads (a choice with no consequence, a
     phantom ask: a card whose reading sentence did not compile is a shape gap, not a card that
     asks a colour for nothing); two CHOOSE_NAMEs of one quality on one object;
  4. a read on another object: a token's, an emblem's or the back face's abilities, a granted
     ability (its source is the object it is granted to; CR 607.5 links a pair only granted
     together), a keyword's parameters (hexproof's quality is judged in the targeting source's
     coordinates); except a PROTECTION quality, which `legality.protected_from` judges in the
     coordinates of the ability that gives it (Runed Halo's own grant);
  5. a quality chosen anywhere but as an EtBState's own effect;
  6. a choice that may not be made while its reads can be asked: a CHOOSE_NAME in a static
     ability's effect (a static runs no choice; GET_EMBLEM's class there, BACKLOG), or under an
     EtBState's condition (skipped when it fails), which 7 refuses;
  7. (`EtBState` itself) an effect beside a tapped flag, counters or a gate in one node: the
     effect stands in its own node, so "This land enters tapped. As it enters, choose a color."
     (KHM Shimmerdrift Vale, FDN Uncharted Haven) is two EtBState nodes, the one canonical form
     (gate round 9, m6).
- Why 5. A colour chosen and read once by a resolving effect is already the menu of five (`Choose`
  over five grants: Feat of Resistance's and Gods Willing's "the color of your choice", verified),
  so CHOOSE_NAME(COLOR) there would be its second encoding. A resolving creature-type choice (KHM
  Crippling Fear, Haunting Voyage) has no encoding yet: its card brings one with its tests. A card
  name keeps both places (Necromentia chooses in a spell).
- The engine. `executor.name_choices` is keyed by (source, quality) and dropped when the source
  leaves (CR 400.7), its value kept in the source's last known information (`LastKnown.choices`):
  an ability whose source has left reads it there (CR 113.7a, 608.2h; Icon of Ancestry's look
  after a Disenchant in response, pack `icon_of_ancestry_reveals_by_its_last_known_choice`). The
  colour menu is W, U, B, R, G, asked as `quality:<source>:COLOR`. The creature-type menu is the
  format pool's (`Supply.creature_types`, set on the executor as `creature_type_pool` beside
  `name_pool`: the creature types of the deckable cards' type lines, of the creature tokens they
  make and of their type grants, M21's Saproling and FDN's Dog being no card's and M21's Sphinx
  only Riddleform's grant, less a face's artifact, enchantment and land types, CR 205.3d,
  205.3g-i: ELD Gingerbrute is a Food Golem), public, so it reveals no hidden card; a rig with no
  format names the world's, and the bench marks that ask leaky. CR 205.3e/m allow any creature
  type: cutting the menu to the pool's is a scaffold (BACKLOG "Scaffolds to remove", with round
  4's `name_pool`).
  NAME_CHOSEN COLOR reads the printed colours (no effect changes one), CREATURE_TYPE SUBTYPE_EQ's
  live words (the type line and GRANT_TYPE's overlay). A read with nothing chosen raises, as
  round 4's did.
- Choices before the entering state. `Executor._apply_etb_state` makes every "As this enters"
  choice before it judges any EtBState gate or counts any entering counter, in whatever order the
  abilities print: FDN Banner of Kinship's "enters with a fellowship counter ... for each creature
  you control of the chosen type" will be counted after its choice (the card still waits for its
  pieces; the test builds the shape with the counters printed first), and a gate may read the
  choice. A permanent a pack or the probe puts on the battlefield has made its
  choice before the opening turn reads it (`ScenarioRunner._as_entered`; the probe's own case
  moved there): Icon of Ancestry's anthem is read at once, where Runed Halo's quality was read
  only when protection was asked.
- The compiler (`templates_b17`, frame B13-cast-chosen): "As this artifact|creature|enchantment|land
  enters, choose a color|creature type." (20 printings of 17 cards); "Whenever you cast a spell of
  the chosen color|type, put a +1/+1 counter on this creature." and, through the frame, the same
  head with any clause that parses alone ("you gain 1 life"); "[Other] creatures you control of
  the chosen type|color get +P/+T."; "You may reveal a creature card of the chosen type from among
  them and put it into your hand." (Garruk's Harbinger's shape, `templates_b4.reveal_one_from_among`).
  "The chosen type" is a creature type: on a card that chose another kind of type the read has no
  choice of its quality, a shape gap (no such card compiles). Not matched: "As it enters, choose a
  color." (FDN Uncharted Haven: "it" has no context in a template) and a face named in full (KHM
  The Ringhart Crest).
- Census (`census.txt`): 22 printings of 19 cards choose a colour (10) or a creature type (12) as
  they enter; B17 reads the choice on 20. Whole now: M20 Diamond Knight and Icon of Ancestry, FDN
  and M19 Diamond Mare, ORI Prism Ring, KHM Rally the Ranks. Partly, with a reader: ELD and FDN
  Heraldic Banner, M12 and FDN Adaptive Automaton, M15 Obelisk of Urd. Refused (shape gaps), since
  no reader of their choice compiles: 10E Story Circle and Voice of All, FDN Banner of Kinship and
  Secluded Courtyard, KHM Bloodline Pretender, Realmwalker, Reflections of Littjara and
  Shimmerdrift Vale, M14 Door of Destinies; on the base they were partial, dealt in the all and
  castable pools with the choice unparsed (Secluded Courtyard's any-colour mana unrestricted,
  stronger than printed). Each is a piece short (BACKLOG). Card names chosen as a permanent
  enters: Runed Halo compiles; Pithing Needle, Phyrexian Revoker, Alpine Moon and Sorcerous
  Spyglass do not.
- Rejected:
  - a verb and a predicate per quality (CHOOSE_COLOR / COLOR_CHOSEN, CHOOSE_CREATURE_TYPE /
    TYPE_CHOSEN): four components for one operation over three menus (AGENTS §9);
  - a NAME value: two byte forms of a card name;
  - the policies' `scope` role: one role name, two meanings;
  - a new FAtom field: STACK_KIND_EQ's closed string slot already carries a vocabulary;
  - five granted triggers made by an enters trigger (the 2026-11-05 needs-atom's emulation): a
    trigger is not "as enters", and every read (statics, triggers, mana) would fork five ways;
  - a missing choice read as False (the rulings' "no type was chosen: it does nothing"): every
    entry makes the choice, a source that left answers from its last known information, and the
    IR refuses every read the engine judges elsewhere and every choice that may go unmade, so a
    missing choice is an engine fault, raised; a copy that entered without choosing has no card
    here;
  - CR 205.3m's whole list (about 300) as the menu: the types no card or token of the pool has are
    equal null picks for every as-enters card of the 19 sets, and the menu could never be the
    network's; a symmetric card ("all creatures of the chosen type get -1/-1") would need one null
    option (BACKLOG).

**R9-2 What the network sees (AGENTS §10).**
- The ask: a new kind, `quality`, appended to `features.ASK_KINDS` (no index moves) and started on
  load as `other`, as a kind never encoded before is: the `name` row never trained, since every
  name ask goes to the fallback (`actor.NetAgent.decide`). Each option carries its value in a new
  option column, `O_VALUE`: the component token the trees name it by (`features.value_token`: a
  colour is its COLOR_HAS and ADD_MANA value `str:W`, a creature type the face token `sub:Elf` its
  cards carry), embedded with the card-component embedding (`ir_emb`), so "Elf" in the menu is the
  vector in every Elf card's component bag. Colour options are also the option types W to G, as
  the mana ask's are; the search's option classes key the value too (`search.option_classes`).
- The board: a permanent's chosen colour or creature type in a new card column, `C_CHOSEN` (the
  same token), added to the card's embedding. 0 is none, a zero term: `PolicyValueNet.value_emb`
  masks the padding row, which `_init` and every checkpoint hold at random values. So an old
  checkpoint computes what it computed before on every observation without a choice (no parameter
  added, `model.load` unchanged): bitwise, tokens, logits and values on 64 decisions of three FDN
  games, a random net with non-zero output layers, base against branch
  (`reports/chosen_quality_2026-11-13/old_net_*.py`). An encoding recorded before the columns
  existed (a ceiling window's `--search-record` shards, a simulator's views) reads as one with none
  (`model.widened`; `simulator.Data.load` widens each view shard). A checkpoint older than an ask
  kind or a feature column loads grown, the policy network's (`model.load`) and the simulator's
  view network (`simulator.load`) by the same rules (`model.upgraded`): runs/window1/sim.pt, 30
  ask rows and 22 global columns, which gate B's queue loads with `--search-sim` (gate round 9,
  m7; it failed on main too).
- Not seen: a chosen card name (it has no component token; the `name` ask stays the fallback's),
  and a creature-type menu wider than MAX_OPTIONS (64): in the M20 (69) and M21 (74) pools Icon of
  Ancestry's choice is the fallback's (`HeuristicAgent._quality`: the type its own visible cards
  most share), under the observation caps' scaffold. FDN's 47 fit; a colour menu always does.

**R9-3 The rename: deferred (ledger F12).** CHOOSE_QUALITY / QUALITY_CHOSEN would say what the
pair now does. Against now: it re-bakes M21 Runed Halo's verified tree (and Necromentia's), which
then leave the verified pool until re-verified, for a label: the network reads `Verb.CHOOSE_NAME`
as an id, not as English, and the meaning is in the role. Deferred, the blast radius stays purely
additive (no verified tree changes, so the replays measure the engine change alone). Fold it with
the next round that re-bakes Runed Halo, or with a third quality (a card type: IKO Umori; a basic
land type: M10 Convincing Mirage), re-verifying both.

**Blast radius** (by script over the 19 sets, base dafdd5ff;
`reports/chosen_quality_2026-11-13/blast_radius.txt`):
- trees changed: 20 compiler trees, all unverified, and 20 with records applied (the two M20
  needs-atom records re-mapped to the compiler's tree through `cardtool write`): 6 now compile
  whole, 5 parse more sentences, 9 are refused (above).
- verified cards: 0 leave, 0 join; the stamps match (M21 275, M20 270, FDN 180 against
  dafdd5ff; M21 275, M20 273, FDN 183 on the branch merged with main 8db1834f, against it: the
  same 20 trees, and 300/300 replays identical, 0 crashes, decks from 275, 273 and 183 cards).
- Still-verified cards with unchanged bytes on a touched path: M21 Runed Halo (its choice and
  read, keyed (source, None)) and Necromentia (its read); 7 with entering counters (M21 Malefic
  Scythe, Wildwood Scourge; M20 Squad Captain, Voracious Hydra; FDN Gnarlid Colony, Goblin
  Boarders, Wildwood Scourge), two of them gated by their kicker (Gnarlid Colony, Goblin
  Boarders), through the entry hook whose gate and counter passes are the old loops, after the
  choices.
- 300 seeded heuristic games (100 each, M21, M20, FDN), decks from the cards verified on both:
  300/300 identical digests, 0 crashes either side, on 92aca048 and again on the final code.
- `Executor.state_fingerprint` (`__init__.py:3519`) folds the choices as (source, quality,
  value), `(s, 'None', n)` for a card name where main folded `(s, n)`: a state holding Runed
  Halo's or Necromentia's choice has other fingerprint bytes than on main (a state without one
  does not). The replay digests (`preflight._digest`) do not fold the fingerprint and are
  unchanged.
- G3 (`gates.mutants`) on the choosers: Runed Halo keeps its 1 live mutant. Necromentia has 12
  where the base had 13: dropping its choice step leaves reads with no choice, refused now, a
  mutant the base killed only by the read raising. The single-reader anthems gain the widen that
  drops the read and the choice together (Rally the Ranks 6, Obelisk of Urd 8, Heraldic Banner 6,
  Adaptive Automaton 7, each one more than on 92aca048).
- Random-play soaks dealing the new trees (800 games: M20 compiled with the unverified records 200,
  FDN compiled 200, FDN, KHM, ORI and M19 castable 100 each): 0 crashes. Every family card in
  those pools was cast, in 4 to 28 games, its choice made by random answers. Detector hits: 2 in
  one M20 game (D5 folds Omnath's counters across its two lives, BACKLOG) and 7 in four FDN games
  (D3 and D5 classes that come up on the base's FDN pool too), in no game that cast a family card
  (`soak_coverage.txt`). Rerun on the final code: the same casts and hits, 0 crashes.
- The conformance checker's pools (M21, ZNR) hold no new tree: no V4′ CHOOSE emission, no V5′
  drift beyond the baseline's.

**Pre-gate review** (one fresh-eyes reviewer on 92aca048; nothing FATAL), fixed on the branch,
each fix with a test or pack that fails on 92aca048 (`reports/chosen_quality_2026-11-13/review_runs.txt`):
- M1, an ability whose source left raised at its read (Icon of Ancestry's look after a Disenchant
  in response): the choice is kept in the source's last known information (R9-1's engine). A
  source that left and came back still answers with its new choice, as for every LKI read
  (BACKLOG: "An ability whose source left and came back").
- M2, the new terms added `ir_emb`'s random padding row to every card and option token, so old
  checkpoints did not compute what they did (the reviewer measured r28's last value move from
  -0.114 to +0.009 on one ask): masked (R9-2).
- M3, G3 lost the "drop the chosen type" widen on every single-reader anthem: stillborn, as a
  choice nothing reads is refused. The widen drops the choice with its last read
  (`gates._without_unread_choices`, as the zone swap drops `arrange`).
- m1, three accepted forms the engine could not honour: a choice under an EtBState's condition,
  a gate reading the choice (judged before it was made), a choice in a static. Refusal 6, and
  the hook makes every choice before judging any gate.
- m2, `search.option_classes` folded a creature-type menu into one class: it keys O_VALUE.
- m3, encodings recorded at the old widths (7 and 4) did not collate: `model.widened`.
- NITs: the ask grows from `other` (R9-2); ELD's menu held Food (R9-1's engine); the
  string_value reading (R9-1's IR, F12); Changeling's absence, G3's bare reads and Icon of
  Ancestry's 172 tokens (BACKLOG). Kept: `ScenarioRunner._as_entered` ignores EtBState conditions
  (no choice stands under one now), and `bench/test_router._arranged` places a chooser without a
  choice (its tests set the choice they read).

## 14. Round R10 — one or more objects moved at once (2026-11-13; gate round 10 FIX-THEN-GO, fixed)

The card backlog's wave 3, its third package (BACKLOG, "Card backlog wave 3: the plan"): M20
Woodland Champion ("Whenever one or more tokens you control enter, put that many +1/+1 counters
on this creature.") and Angelic Guardian ("Whenever one or more creatures you control attack, they
gain indestructible until end of turn."), both needs-atom records since 2026-11-05. Census,
scripts and base runs: `reports/one_or_more_2026-11-13/`. Tests:
`MTG_bot/core/test_executor_one_or_more.py`. Round 9 (§13, a chosen quality) merged first.

**The change: no new node, field or verb.**
- `TriggeredAbility.once_per_event` (and DelayedTrigger's) on a ZoneChangeEvent: one trigger for
  the objects one event moves (CR 603.2c: "it can trigger repeatedly if one event contains
  multiple occurrences"; the flag reads "one or more"). `ability_tree.gathers_occurrences`
  (ability_tree.py:3096) now answers True for a ZoneChangeEvent whose subject is absent or is not
  the source or what it is attached to, and `_check_once_per_event` (:3136) refuses the flag on a
  zone change of one object as it does on an attack or a damage event: flagged, "when this
  creature enters" would be a second byte form of the unflagged trigger.
- **One event** is one atom boundary: `GameEvent.batch` (executor/events.py:222), stamped by
  `EventJournal.record_atom` (:555) on every row it journals, the clock of the boundary's first
  row. A drawn card is its own (:572, CR 121.2). The field is outside `dump()`: replays and forks
  re-derive it, and no fingerprint, game log or journal dump changes.
- **The binder** (executor/binding.py): `_queue` (:811) queues one instance per ability per
  declaration or batch (the declare-group dedup, generalised), and the instance holds every object
  of the event its spec matches (`_occurrences`, :920), each judged by its own row, so a departed
  one by its last known information (CR 603.10a). `_check_trigger` binds a flagged ZoneChangeEvent;
  every other kind but an attack and combat damage is still refused.
- **The gathered register.** On a flagged declaration or zone change
  (`ability_tree.gathers_objects`, :3126) `_put` (:1648) binds the `event` register to all of
  them, and a `gathered` register to the same list, which replaces round 4's `declare_attackers`.
  - "They" is `Selector(referent="event")`, the one C2 referent form, now denoting every object
    the register binds (executor/selectors.py:705: a referent is bound, never chosen, so no count
    slices it; nor does MOVE_ZONE's count clamp, verbs.py:360, which made "exile them" move the
    first only until gate round 10). At resolution `resolve` (binding.py:1745) keeps those the
    effect can act on: not one that has changed zones since its row (a new object, CR 400.7);
    not one the event moved into a hand or a library (CR 400.7's exception for an ability that
    triggers on the move finds the new object only in a public zone); not a token off the
    battlefield (CR 111.7, 111.8: it can't be moved and ceases to exist). An attacker removed from
    combat is still one of them.
  - "Among them" (an aggregate QProp over `Selector(referent="event")`: "the greatest power among
    them", MAX; SUM) reads every object gathered, those no longer among "they" included, each by
    its last known information once it left (CR 608.2h; `quantity.read_population`, :682; a
    gathered object's own departure row answers in `departed_lki`, :508, on the zone change's own
    resolution only: a query, which carries the bindings but no event, reads the live object). The
    departed tokens stay in the world until the trigger resolves, as the first row's always did
    (`TriggerBinder.pending_references`, binding.py:1561). Gate round 10's MAJOR-1: 88b7f7e8 kept
    only the first row's token, and the read of the other raised KeyError; a creature card was
    read in the graveyard, without the counters it died with. The fix's first version looked the
    row up from a query too and crashed 7 of 100 FDN replays (Battlesong Berserker choosing its
    target among the attackers it gathered); the replays caught it before a commit, and
    `test_battlesong_berserker_targets_one_of_the_attackers_it_gathered` pins it.
  - "That many" is `QProp("event", THAT_MANY_COUNT)`: the `result` register first (Kinetic
    Augur's precedence), else `gathered` (executor/quantity.py:672), every object gathered, those
    that left included (Woodland Champion's ruling; Basri Ket's: "attacking nontoken creatures
    that leave combat before the triggered ability resolves are counted"). A single event writes no
    `gathered`, so "that many" with no antecedent still raises.
  - A gathered combat damage event keeps its one subject, the player dealt damage: Feline
    Sovereign's "that player", unchanged.
- **The IR refuses** (gate rounds 4-8's classes, met at construction):
  - the flag on a zone change of one object (above);
  - the flag on a creature put into a graveyard from the battlefield (`_check_once_per_event`):
    "one or more creatures die" is CreatureDiesEvent's (CR 700.4), the binder's to gather when a
    card needs it (gate round 10's MINOR-3, divergence D24; no tree changes);
  - a read of one object of a gathered register, which would take the first in handle order
    (`_check_gathered_reads`, ability_tree.py:3225; `_reads_one_event_object`, :3201): a QProp of
    "event" other than THAT_MANY_COUNT ("its power"), an FAtom referent "event" ("attached to
    it"), a DurationUntilLeaves of "event" ("until it leaves"), the event referent in a role a verb
    reads as one object (`_ONE_OBJECT_ROLES`, :3198: DEAL_DAMAGE's dealer, "it deals"; FIGHT's
    foe; verbs.py takes the first of several), in the effect, a token's power and toughness
    (resolved as the token is made), a reflexive trigger in it (it reads the same register) and
    the condition; and an
    intervening "if" that tests its subject (CR 603.4: judged on the event's one object, and a
    gathered event has none): a condition may hold only `ability_tree.SUBJECT_FREE` predicates
    (:3176, the R6-2 list, now in the IR; tools/audit imports it);
  - a FIRST over a referent Selector (QProp.__post_init__, :881): "its power" is the string
    referent's, the one encoding ("the greatest power among them", MAX, stands);
  - a QCount over a referent Selector with no filter (QCount.__post_init__, :799): "the number
    of them" has one encoding, THAT_MANY_COUNT, and the count of the Selector would differ from it
    once an object leaves. With a filter it is the one encoding of "for each creature card exiled
    this way" (some of them; IS_RESULT in a selector's filter is refused as the referent's second
    form), and over a gathered event it counts every object gathered, as "among them" reads them
    (`quantity.read_population`). The first version refused it whole, which removed that encoding
    from 8 unparsed sentences (gate round 10's nit); "source" and "controller" stay refused, one
    object each. No tree of the 19 sets had either form.
- **Executor nets** for what the IR cannot see: a singular referent read of an event register
  that holds several objects raises (quantity.py:470), and so does a bare Conditional after a
  sentence that names no object (executor/__init__.py:311; it was judged on the trigger's source).
  "That much", "this way" and "that many" read registers, not an object: `_REGISTER_FIELDS`
  (quantity.py:627) skips the object lookup, so a gathered event whose objects have all left
  still counts them (8b8c35b9 raised there and crashed M21 Basri Ket's -2 when its one attacker
  died in response; the round's fresh-eyes review found it). A zone change journalled without a
  batch raises (events.py `_emit`), and so does gathering one (`TriggerBinder._occurrences`):
  batch 0 would gather every such row of the game (gate round 10's MINOR-6; the one emit site
  stamps a batch today).
- **Compiler** (no new verb): B2b-tokens-enter-that-many-counters (templates_b2b.py:2227) and
  B2b-attackers-gain-keyword-eot (:2262, any bare keyword of B11's table: the grant of B5b's
  "it gains <keyword> until end of turn" over the event referent); the frame
  B13-one-or-more-leave-graveyard (Desecrated Tomb; compiler frames.py:154, `_once_per_event`
  :91). A pronoun keeps a frame's clause out as before. KHM Elvish Warmaster's "one or more
  other Elves you control enter" gets no frame: without its "This ability triggers only once each
  turn" its own Elf Warrior token triggers it again, a loop the card never makes, in every pool
  that deals partly compiled cards (the first draft had the frame: 201 firings in 100 KHM
  castable soak games, stopped by the tripwire).
- G3 (tools/cards/gates.py): the critical "each occurrence -> once per event" mutant is built
  inside the stillborn guard; it is stillborn where the effect reads one object of the event
  (Terror of the Peaks' "that creature's power").

**What counts as simultaneous (the gate's questions).**
- One resolving instruction is one event: the objects one atom moves (one CREATE_TOKEN's tokens,
  one MOVE_ZONE's, DESTROY's or mill's cards, one discard of several). Two instructions of one
  resolution are two events ("create a token, then create two": two triggers, 1 and 2).
- One state-based-action check is one event (CR 704.3: performed simultaneously, as a single
  event): `Executor._state_checks` journals each check as one boundary; the deaths after a
  combat damage step are one check, one event. A later check is another.
- Tokens one effect creates are one event (Raise the Alarm's two, Undead Servant's three).
- A wrath is one event; the dies triggers it causes each resolve on their own, and the tokens each
  creates are an event apiece (one "one or more tokens enter" trigger per resolution).
- A draw is one card at a time (CR 121.2): "draw two cards" is two events.
- Limits, logged in the BACKLOG, none printed or compiled in the 19 sets:
  - a permanent moving in the same atom as others sees their moves only in journal row order (CR
    603.6a "including the newcomers", 603.10a; per-object triggers too,
    `simultaneous_movers.py`); a gathered holder that leaves with its objects is all or nothing
    by handle order (a DESTROY of the Watchdog holding "one or more other creatures leave" and
    three creatures gives no trigger where CR 603.10a gives one, counting 3: gate round 10's
    MINOR-2);
  - one instruction run once per player through EachPlayer is several events (gate round 10's
    MINOR-1: `EachPlayer(ANY, SACRIFICE a creature)` against a flagged "one or more other
    creatures leave" gains 1 twice where CR 101.4 makes it one event, 2): every EachPlayer
    zone-change tree, one iteration with two players, several in Commander. The fix: one batch
    for the sub-executions of one EachPlayer;
  - a dies-window replacement's exile is its own boundary;
  - "one or more creatures die" waits for the binder to gather CreatureDiesEvent; its zone-change
    form is refused (divergence D24).
  - Fixed 2026-11-13 with no IR change (the first three, and the CR 400.7 "it" of a per-object
    trigger): the binder matches an event's rows together, its look-back triggers (CR 603.10a)
    before its moves are carried out and every other trigger after, with the layers brought up
    to date; one EachPlayer, and a replacement's action with the event it modified, are one
    batch (`EventJournal.one_event`); "it" and "they" are cut by one CR 400.7 check
    (`TriggerBinder._gone`). BACKLOG keeps what is left (an EachPlayer body still runs player by
    player).
- The flag stands on a subject that names objects through `IS_RESULT`, `IS_ANY_TARGET` or a
  referent FAtom (no tree has one; gate round 10's nit). Each can name several objects (the
  objects an instruction acted on, an ability's several targets, the Auras attached to a
  creature), so gathering them changes the play and is not a second encoding; refusing them
  would refuse a valid "when one or more of them".

**A gathered object that has since left** (CR 400.7). It is gathered as the event occurs. "That
many" counts it, "among them" reads it as it last existed (CR 608.2h); "they" does not touch it,
nor the new object it became if it came back (pack
`angelic_guardian_bounced_attacker_is_a_new_object`; for a zone change,
`test_they_leave_out_a_gathered_object_that_changed_zones_since`).

**What the network sees.** The card's tokens carry the flag (`@once_per_event bool:True`),
THAT_MANY_COUNT and the event referent. A trigger on the stack is its source's entity with its
ability index, depth and first target, not the number its event gathered, as no AMOUNT or
COUNTER_COUNT is shown today; the board shows part of it (a creature token that entered this
turn is sick). BACKLOG, "What the network sees" (features.py is another lane's).

**Rejected.**
- A new flag, field or node ("one or more", a gathered-zone-change event class): the flag is
  CR 603.2c's axis already, for declarations and damage; a second would be a second encoding.
- A new referent ("gathered", "those") or an ALL-mode referent Selector for "they": a second byte
  form beside the C2 referent, which under a single event would mean "it" again.
- `QCount(Selector(referent="event"))` for "that many": it counts the objects still there, the
  ruling counts those that left; refused instead.
- Refusing the flag where nothing reads the gathered set (asked for by the round's brief): the
  flag decides how many times the ability triggers (CR 603.2c) whether or not its effect reads
  the set. Desecrated Tomb's "create a 1/1 black Bat" reads nothing of it and is one Bat per
  event, not one per card (`test_desecrated_tomb_one_bat_per_event`); the refusal would refuse a
  printed card. What the flag cannot do without a set is refused: on one object's zone change
  (above) and on an event kind the binder does not group.
- The batch in the row's `data`: every ZONE_CHANGE row's dump bytes, every fingerprint and game
  log would change (round 8 rejected stamping the ordinal for the same reason).
- One event per op (`Executor._op_seq`): an op is a whole resolution, several instructions, so
  "create a token, then create two" would trigger once.
- Gathering at `_put`, as the declaration register did: a token that died in the check after its
  entry would no longer pass "a token you control" (CR 603.10 reads the event right after it).
- "That many" reading the `event` register: a single event's register is its one object, so a
  "that many" with no antecedent would read 1 instead of raising, and after the CR 400.7 check it
  would miss Woodland Champion's departed tokens.
- Gathering CreatureDiesEvent ("one or more creatures die") or a sacrifice: no card of the 19 sets
  prints one; the binder still refuses the flag there, and the IR the zone-change form of a death.
- Every referent naming every bound object (`result`, `target` too): it would change verified
  play (See the Truth's "each of those cards", BACKLOG) and needs its own audit.

**Census** (`census.py`, 19 sets): **5** zone-change "one or more" sentences on 5 cards, all
blocked on the base (Woodland Champion a needs-atom record; Elvish Warmaster, Desecrated Tomb,
Devourer of Memory and IKO Rielle, the Everwise unparsed), none in M21 or FDN; the first census
missed Rielle's verb-first "whenever you discard one or more cards" (gate round 10's nit). The
17 / 13 of the wave plan's sketch do not reproduce (it may have counted every "one or more"
trigger). Angelic Guardian is the attack class's (11 sentences, 8 blocked). After: Woodland
Champion, Angelic Guardian and Desecrated Tomb compile whole; Elvish Warmaster stays unparsed
(above); Devourer of Memory's clause has no template; Rielle's "for the first time each turn"
has no component.

**Blast radius** (by script over the 19 sets, 30fabc4a against the branch,
`reports/one_or_more_2026-11-13/blast_radius.txt`):
- trees changed: **3** compiler trees, the same 3 with records applied, all unverified, all now
  compiling whole: M20 Woodland Champion and Angelic Guardian (needs-atom records re-mapped to the
  compiler's trees) and M19 Desecrated Tomb. No M21 golden changes.
- verified cards out or in: **0** and **0**; the stamps match (M21 275, M20 273, FDN 183). Feline
  Sovereign and Basri Ket keep their bytes, and their packs (feline_sovereign*,
  basri_ket_minus2_counts_nontoken_attackers, basri_ket_minus_two*) pass unchanged.
- still-verified trees with unchanged bytes on a touched path: **40** (a flagged attack trigger:
  Basri Ket, Tide Skimmer, FDN Ancestor Dragon, Battlesong Berserker; an event referent Selector;
  THAT_MANY_COUNT; a per-object zone-change trigger).
- 300 seeded heuristic games (100 each, M21, M20, FDN), decks from the cards verified on both:
  **300/300 identical replay digests and 300/300 identical journal dumps**, 0 crashes either side;
  17 games queued a flagged trigger (M21 5, FDN 12).
- G3: verified trees with an "occurrence" mutant **8 -> 28**. The 20 per-object zone-change
  triggers over another object (M21 Garruk's Uprising, Thieves' Guild Enforcer, Watcher of the
  Spheres; M20 Bag of Holding, Bishop of Wings, Corpse Knight, Dread Presence, Griffin Protector,
  Impassioned Orator, Marauding Raptor, Omnath, Locus of the Roil, Risen Reef, Sage's Row
  Denizen, Starfield Mystic, Waterkin Shaman; FDN Adventuring Gear, Garruk's Uprising, Impact
  Tremors, Spitfire Lagac, Tatyova) gain the critical "each occurrence -> once per event" mutant.
  Their stamps stand (the tree sha is unchanged) and predate the mutant; a re-verification must
  kill it with a pack moving two objects at once (the probe has no such stimulus: BACKLOG). No
  dead-role or equivalence rule in `gates.mutants` absorbs it: one event of two objects triggers
  once or twice, a real difference (gate round 10's merge condition 5). Terror of the Peaks' is
  stillborn.
- Random-play soaks dealing the new trees (M20 compiled with the unverified records 200 games, M19
  compiled 200, KHM castable 100): 0 crashes; Woodland Champion cast in 12 games, Angelic Guardian
  in 4, Desecrated Tomb in 46; 11 gathered firings (the Guardian's with 1, 2, 3 and 6 attackers).
  2 detector hits, both in other cards' paths (`soak_coverage.txt`).
- Ontology conformance (M21, ZNR): PASS, errors 0, warns 7, V4′ new CHOOSE emissions 0, on both.
- Gate round 10's fixes (de676db0, 88b7f7e8 with main merged, against them): 0 trees changed, 0
  verified cards in or out; the 300 seeded games identical (digests and journal dumps), 0
  crashes; the soak line for line the same; 19 of 19 engine mutants killed (`mutants.txt`). The
  fixes' first version crashed 7 of 100 FDN games (above); `blast_radius.txt` keeps both runs.
- The branch merged with main c164cd34 (round 9 merged first), against c164cd34: the round's 3
  trees, 0 verified cards in or out (M21 275, M20 273, FDN 183), 300/300 identical replay
  digests and journal dumps, 0 crashes.

## 15. Round R11 — the cost twins: exile and remove-counter costs (2026-11-14; gate round 11 FIX-THEN-GO, fixed)

The card backlog's wave 3, its "Later" item (BACKLOG, "Card backlog wave 3: the plan"): M20 Hanged
Executioner ("{3}{W}, Exile this creature: Exile target creature.") and Barkhide Troll ("{1}, Remove
a +1/+1 counter from this creature: This creature gains hexproof until end of turn."), needs-atom
records since 2026-11-05 because the cost union had no part that exiles or removes counters, and
ledger F3, which waited on this ruling. Census, scripts and base runs:
`reports/cost_twins_2026-11-14/`. Tests: `MTG_bot/core/test_executor_cost_twins.py` (68 after
gate round 11), two in `tools/selfplay/test_selfplay.py`, one each in `tools/cards/test_gates.py`
and `test_lints.py`; packs in `tools/scenarios/mapped/M20/` (hanged_executioner_* 4,
barkhide_troll_* 7) and `tools/scenarios/` (suspicious_shambler_* 2, fungal_plots_* 2). Main
1db792e1 (the card-onboarding lessons, G0's lints) is merged; its commits touch no file under
`MTG_bot/`. After gate round 11, main 4da972f1 is merged too (its reprint stamps: below, "A bug
found in G3").

**The census** (`census.py`; the base 1d5e4164 in `census_base.txt`, the branch in `census.txt`).
- Printed costs that exile or remove counters, 19 sets (§1a): **75 items on 75 printings of 72
  names**: activated abilities 50, THB escape 22, additional costs 2 (KHM Weigh Down, ORI Skaab
  Goliath), an alternative cost 1 (KHM Stalwart Valkyrie). By shape: cards exiled from your
  graveyard 37 (22 of them escape), counters removed from the source 24, the source exiled from
  your graveyard 8, the source exiled from the battlefield 5, a counter removed from another
  object 1 (WAR Soul Diviner). None verified. On the base 69 were partly compiled, 3 needs-atom
  records (M20 Hanged Executioner, Barkhide Troll, Kethis, the Hidden Hand) and 3 refused (FDN
  Suspicious Shambler, KHM Littjara Glade-Warden, M19 Transmogrifying Wand). M21 prints none; M20
  3; FDN 6 (Drake Hatcher, Feldon's Cane, Myojin of Night's Reach, Ramos, Dragon Engine,
  Suspicious Shambler, Wishclaw Talisman). The wave plan's "16 cards in other sets" does not
  reproduce (it may have left out escape and the graveyard-exile costs).
- The existing twins, printed items (verified): sacrifice the source 138 (21), sacrifice another
  127 (11), discard another 43 (8), discard the source 46 (1; 45 are IKO cycling reminders), {T}
  901 (139), tap another 26 (1), put a counter 5 (4); life 15 (2) (§1).
- Compiled, records applied (§2, trees and verified): CostTap({T}) 522 (138), CostSacrifice of the
  source 37 (26) and of another 27 (11), CostDiscard of another 17 (8) and of the source 1 (1),
  CostPutCounter 2 (2), CostTap of another 1 (1); CostLife 2 (2), CostLoyalty 77 (19). The verb
  atoms they mirror (§2a): MOVE_ZONE to exile 72 (33), MOVE_ZONE from a hand to a graveyard 60
  (29), PUT_COUNTER 122 (57), TAP 53 (12), SACRIFICE 8 (8), REMOVE_COUNTER 1 (1). Where the parts
  sit (§2b): 755 in activated abilities, 31 in spells' additional costs (19 sacrifices, 12
  discards); no PAY or CAST cost of an effect holds a non-mana part.

**F3: the ruling (Type-1).**
- **Fold**: every cost part that mirrors a verb becomes that verb's atom inside `Cost.parts`
  (CostSacrifice a SACRIFICE atom, CostDiscard the MOVE_ZONE hand-to-graveyard shape, CostTap a
  TAP, CostPutCounter a PUT_COUNTER; the two new costs a MOVE_ZONE to exile and a REMOVE_COUNTER).
  Reach (`census_base.txt` §3): **572 trees of the 19 sets change bytes, 164 of them verified**
  (M21 63, M20 51, FDN 50), every one out of the verified pool until a blind review passes it
  again; with the {T} symbol kept a part, 85 trees and 49 verified (§3a lists them).
- **Keep**: the parts stay their own closed union, and `CostExile` and `CostRemoveCounter` join
  it. Reach: 13 trees, none verified (the blast radius below).
- **Recommended and built: Keep.** A cost part is not a duplicate of the verb atom it mirrors:
  1. It is paid before the ability exists as an activated ability: activating runs CR 601.2b-i
     (602.2b); the total cost is paid at 601.2h, and only at 601.2i has the ability been
     activated. Its effect happens when it resolves (608.2). A verb atom in a tree is what the
     resolving ability does.
  2. It is not an effect. A cost is an action or payment necessary to take another action (CR
     118.1); an effect is what a resolving spell or ability does (609.1). The action keeps its own
     rules either way: a sacrifice cost is a sacrifice (701.21a), an exile cost moves the card,
     so "leaves the battlefield" triggers see it.
  3. It is never paid partially: a cost without the resources to pay it fully can't be paid
     (118.3), and the payer may not pay part of it (601.2h). An effect does as much as it can
     (609.3): "remove a +1/+1 counter" with none there does nothing as an effect and makes the
     ability unactivatable as a cost. So a cost needs a "can it be paid in full" judge before
     anything is paid (`legality.build_payment_plan`), which no verb has.
  4. Nothing can respond to it, and it stays paid: no player receives priority while an ability is
     being activated (the activating player receives it afterwards, 117.3c), and an ability that
     does not resolve (608.2b: its targets illegal) refunds nothing. Hanged Executioner's exile, a
     cost, stays done when its target leaves; written as an effect step it would not happen, and
     the Executioner would stay to be used again
     (`test_hanged_executioner_stays_exiled_when_its_target_is_gone`).
  The round's brief also cited "CR 117.12", which does not exist (rule 117 ends at 117.7; gate
  round 11): claim 4 rests on 117.3c and 601.2h. 601.2h now opens with a first step: the costs
  with no random element and no move of a card from a library to a public zone are paid first, in
  any order, and the rest after them; partial payments are still not allowed. AGENTS §9's merge
  test (i), "similar practical effects (else the model conflates things it
  shouldn't)", fails: a cost gates the activation and is an unrespondable, unrefundable payment,
  an effect is a resolution-time event that can be stopped, and one token (`Verb.SACRIFICE`) would
  carry both. So F3's condition ("only if §9 similar-effects survives analysis") is not met, and F3
  is ruled not a fusion (§4). The fold would also move cost-only rules into the verbs: every
  designation walker and the CR 605.1a classifier read a tree's atoms (`ability_tree.own_nodes`),
  so a TARGET-mode selector in a cost atom would become a target slot (CR 601.2c chooses targets,
  601.2h pays costs; divergence D13 shows cost selectors already written TARGET), and the payment's
  rules would have to live in each verb (a sacrifice acts only on what you control, 701.21a, which
  the compiler's ANY zones leave to the plan; a spell's discard cost never discards the spell).

**R11-1 The two parts (`ability_tree.py`; no new verb, predicate or container field).**
- `CostExile(target)` (:2623): exile the selected objects as a cost. "Exile this creature" (the
  MAPPER_GUIDE "this creature" selector over `Zone(BATTLEFIELD, ANY)`), "Exile this card from your
  graveyard" (the same over `Zone(GRAVEYARD, YOU)`), "Exile two other creature cards from your
  graveyard" (`QConst(2)`, `FAnd(TYPE_EQ 'Creature', FNot(IS_SOURCE))`).
- `CostRemoveCounter(counter_kind, target, count=QConst(1))` (:2642): CostPutCounter's twin.
- `_check_cost_designation` (:2582) refuses, in both: a TARGET selector (costs never target: D13's
  folded form from the start) or a referent ("it"); any mode but CHOOSE (the payer chooses as they
  pay, 601.2h); a count other than a literal of 1 or more (X, "all", "any number"); a zone set
  other than one of `_COST_EXILE_ZONES` (:2567: `Zone(BATTLEFIELD, ANY)`, `Zone(GRAVEYARD, YOU)`,
  `Zone(HAND, YOU)`; no exile cost of the 19 sets takes another player's card, nor a library,
  stack or exile card) and, for removal, anything but `Zone(BATTLEFIELD, ANY)`. Gate round 11
  (M2) closed the forms that took the opponent's objects or said one thing two ways: a filter
  naming the source (an `IS_SOURCE` through an even number of negations) is `FAtom(IS_SOURCE)`
  alone with a count of 1 ("this creature" twice, D25's `FAnd(CONTROLLER_IS YOU, IS_SOURCE)` and
  the source over `Zone(BATTLEFIELD, YOU)` are refused); another permanent carries
  `CONTROLLER_IS YOU` as the filter or one of its conjuncts (an exile or a removal over any
  creature took the opponent's creature or counter, where the sacrifice lane keeps the payer's);
  a card in a hand or graveyard is in the payer's own. No tree of the 19 sets had another form:
  the dump of every card's trees is byte-identical before and after (`tree_dump.py`).
  `test_a_cost_takes_the_payers_own_objects_in_one_form` (7 forms, both parts),
  `test_an_exile_cost_takes_cards_from_the_payers_own_hand_or_graveyard`. Moved to
  `ability_tree` for this, `_filter_names_the_source` (the executor imports it from there).
  `CostRemoveCounter` also refuses LOYALTY (a loyalty ability's cost is CostLoyalty, CR 606.4: one
  spelling) and a `count` other than a literal of 1 or more. Each refused form waits for its card:
  X (M15 Cruel Sadist), "all" (ZNR Relic Amulet), "any number" (ORI Mage-Ring Network), a kind the
  payer chooses (WAR Soul Diviner's "a counter": `counter_kind` is required).
- One cost holds at most one `CostExile` and one `CostRemoveCounter` of a kind (`Cost.__post_init__`;
  gate round 11, M3): two segments over one pool need a matching that neither the plan's
  segment-by-segment witness nor the payer's segment-by-segment asks keeps (divergence D26, beside
  D10's hybrid pay). No printed cost of the 19 sets has two
  (`test_one_cost_holds_one_exile_and_one_removal_of_a_kind`).
- In the union (`CostPart`, :2712), `_COST_PART_CLASSES`, the schema (:5043) and the tags; to_dict
  and from_dict round-trip them (`test_the_two_cost_parts_round_trip_in_a_cost`).
  `_cost_moves_library_card` (:5727) counts CostExile for CR 605.1a (its zones exclude a library,
  so an exile cost never unmakes a mana ability: IKO Titans' Nest's "Exile a card from your
  graveyard: Add {C}" stays one, `test_an_exile_from_the_graveyard_keeps_a_mana_ability`).
- §3's table is unchanged (27 container fields, `atom_field_table.py` exit 0); `Cost.parts` stays
  SET-R1b, the new parts sorting with the others.
- The source has two byte forms in the existing cost parts: `FAnd(CONTROLLER_IS YOU, IS_SOURCE)`
  (37 parts, 22 verified trees) and `IS_SOURCE` alone (7 parts, 7 verified), the same play.
  Registered as divergence D25 (`self_forms.txt`); the new parts take MAPPER_GUIDE's form,
  `IS_SOURCE` alone.

**R11-2 The payment (`executor/legality.py`).**
- Can it be paid (CR 118.3, 601.2h): `build_payment_plan` (:694). CostExile (:1014) needs as many
  objects as its count among what its selector finds, and the source only when the cost names it
  ("Exile this card ..."; a spell's cost is planned with the spell still where it was cast from,
  as CostDiscard's exclusion says: `test_the_source_pays_an_exile_cost_only_when_the_cost_names_it`).
  That exclusion is stricter than the rules for an ability of a card in a graveyard or hand whose
  cost exiles "a card" from that same zone, which could pay with its own card; no card of the 19
  sets has one (a note at the branch). CostRemoveCounter (:1035) needs as many permanents its
  selector finds holding `count` counters of the kind. One part of each per cost (R11-1), so the
  witness's bookkeeping across segments of one lane, which the first build carried, is gone. The
  reasons: `cost:exile:insufficient_candidates:<n><<need>`,
  `cost:remove_counter:<KIND>:insufficient_candidates:<n><<need>`. `ability_playable` asks the plan,
  so the menu (`legal_activations`) offers only what can be paid, and `activate` refuses the rest
  before anything is paid.
- `PaymentPlan` (:336-340): `exile`, `exile_options` and `remove_counters` (each segment's pool,
  need, kind and count), kept out of the plan's repr: the stack's fingerprint row folds it
  (`stack.SpellStack.dump`), and what they paid is in the world, so every state holding a stack
  object keeps its fingerprint bytes (`fingerprint_check.py`: identical on base and branch;
  `test_a_plan_keeps_the_repr_the_stack_fingerprint_folds`).
- Paying it: `pay_costs` (:1745) runs mana, tap, removed counters (:1813), sacrifice, exile
  (:1853), discard, put counters, loyalty, life. The counters come off before a sacrifice or an
  exile takes their permanent: M13 Hellion Crucible's "Remove two pressure counters from this land
  and sacrifice it" pays in full only in that order (CR 601.2h's first step pays the costs with no
  random element and no move from a library to a public zone, both of these among them, in any
  order the payer chooses; `test_the_counters_come_off_before_their_permanent_is_sacrificed`). The
  exile is a MOVE_ZONE naming the owner's exile, journalled as a zone change. Exile is one zone
  all players share (CR 400.1); the world files each card in its owner's slice of it, and
  `selectors.move_destination` files a card leaving for any zone but the battlefield under its
  owner whatever player the destination names, so gate round 11's surviving mutant M9 (the
  payer's exile) plays the same: an equivalent mutant
  (`test_a_permanent_exiled_as_a_cost_goes_to_its_owners_exile`: a stolen creature's own exile
  cost files it under its owner). The removal is a REMOVE_COUNTER event (no journal row, as for
  loyalty; detector D3 exempts removals by construction).
- The asks: where a segment's pool is bigger than its need the payer chooses (601.2h) through
  `_ask_cost_choices` (:1708), the sacrifice lane's shape: `exile:<seat>:<source>:<digest>` and
  `remove_counter:<seat>:<source>:<digest>`, the Handle strings as the words. "This creature" and
  every segment with no real choice are filled without asking (AGENTS §10: no phantom ask).
  `test_the_payer_chooses_which_cards_a_cost_exiles`,
  `test_the_payer_chooses_the_permanent_a_cost_removes_counters_from` (no printed card of the 19
  sets removes a counter of a named kind from another object; the ask is tested on a built tree),
  pack `fungal_plots_the_payer_chooses_the_creature_card`. A segment that the payer's earlier
  picks of the same lane left short raises (gate round 11, M3; every lane): paying it would be a
  partial payment, and the plan said the cost could be paid in full
  (`test_a_segment_the_payers_picks_leave_short_raises`; D26).
- Where it works (CR 113.6m): `activation_zone` (:1159) reads a CostExile of the source (:1184):
  "Exile this card from your graveyard" works only there, and its owner activates it (FDN
  Suspicious Shambler; packs `suspicious_shambler_*`,
  `test_an_ability_that_exiles_its_card_from_the_graveyard_works_there`).
- The one plan and payment serve activations (`activate`), spells' additional costs
  (`stack.cast`) and PAY effects (`verbs._v_pay`).

**R11-3 The compiler.** The frame `B13-activated-cost-item` (frames.py:182) reads
`[<mana and {T}>, ]<item>: <clause>`, the item one of `templates_b3.COST_ITEM` (:100-107; built by
`cost_item`, :115, and `cost_with_item`, :141): "Exile this <artifact|creature|enchantment|land|
permanent>", "Exile this card from your graveyard", "Exile <N> [other] [artifact|creature|land]
card[s] from your graveyard", "Remove <N> <kind> counter[s] from this <permanent>" with the kinds
the IR has (+1/+1, -1/-1, charge, page, soul, incarnation). As every frame, it composes only a
clause that parses alone and holds no pronoun. "Remove three charge counters" is a count of 3
(`test_the_frame_reads_how_many_counters_a_cost_removes`: gate round 11's mutant M17 read every
count as 1 and lived). It is not a trigger frame (no intervening "if",
:191). `test_frames.py`'s differential is unchanged. G0's costs lint (`tools/cards/lints.py`,
merged from main) reads the two items part for part (`printed_cost`, `tree_cost`): the round's
trees pass, and a tree that drops the exile or the removal, or removes two counters where one is
printed (a mutant the probe cannot see), fails G0
(`test_lints.py::test_the_costs_lint_reads_exile_and_remove_counter_costs`); before, it skipped
any card printing one.

**R11-4 What the network sees (AGENTS §10).** Costs reach the network as their card's component
tokens (`features.card_tokens` over the tree: `CostExile`, `CostRemoveCounter`, `@counter_kind`,
`CounterKind.PLUS_1_PLUS_1`, the selectors' tokens), as every cost did. The two asks are two kinds
appended to `ASK_KINDS` (features.py:91), grown from "other" (`model.upgraded`): no tree held the
parts, so neither ask was encoded before. **No input column is added.** An old checkpoint computes
bitwise what it did: a random network saved by the base, loaded by the branch (32 ask rows grown to
34, the two new rows copies of "other"), on 64 decisions sampled from three FDN games of the
verified pool (act, act_second_main, attack, block, mulligan, mulligan_bottom, priority): the
branch's encodings equal the base's, and so do the tokens, logits and value
(`old_net_base.py`/`old_net_branch.py`, `old_net.txt`;
`test_the_cost_asks_are_appended_and_an_old_network_computes_what_it_did` pins the widths, CI 8,
CF 62, PF 18, GF 23, OI 5). The options of both asks are cards, entities like any (a graveyard's
offered cards always stay in the entity list, features.py:574). Not seen: which ability of a card
a cost belongs to (an act option is its card and ability index, as before), and a counter kind but
+1/+1, -1/-1 and loyalty (summed in F_COUNTERS). The bench (`protocol.SEAT_IN_TAG`, :81, prompts
:232-233) routes both; the heuristic exiles the card of lowest mana value (heuristic.py:569).

**The cards** (through `cardtool parse`, `try` and `write`; no `verified` block set):
- M20 Hanged Executioner: the compiler's tree, whole; its needs-atom record re-mapped to it (G0 0
  failures, G1 0 engine errors; G3 14 mutants, the probe kills 14).
- M20 Barkhide Troll: a record, `EtBState(initial_counters=((PLUS_1_PLUS_1, 1),))` (Shatterskull
  Charger's shape without its gate), then `{1}` and `CostRemoveCounter(PLUS_1_PLUS_1, <this
  creature>)` for B3-grant-kw-self's grant with HEXPROOF until end of turn (G0 0 failures, G1 0
  engine errors). The probe's board Troll holds no counter, so G1 shows the ability unpayable
  (`cost:remove_counter:PLUS_1_PLUS_1:insufficient_candidates:0<1`); of G3's 9 mutants the probe
  kills 2, and the 7 packs kill every critical survivor ({1} dropped or raised, two counters
  removed, the hexproof made permanent, the grant made the opponent's) and the widened grant
  (`g3_packs.txt`).
- FDN Suspicious Shambler: the compiler's tree, whole (it was refused).
- Still blocked in M21, M20 and FDN, each for another piece: M20 Kethis, the Hidden Hand (a
  graveyard play permission, R5-2/R5-3; its needs-atom note narrowed to it); FDN Feldon's Cane
  ("Shuffle your graveyard into your library": no template, and a MOVE_ZONE then SHUFFLE would ask
  an order the shuffle discards, divergence D19, a phantom ask); FDN Drake Hatcher, Myojin of
  Night's Reach, Ramos, Dragon Engine and Wishclaw Talisman (counter kinds the IR lacks, and other
  clauses). BACKLOG "The cost twins still blocked" has every card of the 19 sets.

**A bug found in G3 and fixed** (tools/cards/gates.py:554). `_without_unread_choices` compared every
EtBState with `EtBState(effect=a.effect)` before testing the effect; built with no effect that node
is refused (a no-op state), so every mutant of a card entering tapped or with counters was
stillborn and G3 built none (M20 Barkhide Troll 0 mutants; M21 Malefic Scythe 0, now 14). Since
774fa6b9 (2026-11-13, gate round 9's pre-gate fixes).
`tools/cards/test_gates.py::test_a_card_that_enters_tapped_or_with_counters_has_mutants` (red on
the base; `g3_etb_counts.py`). Restated for the tree merged with main 4da972f1, which holds 1,144
verified stamps (736 home stamps, M21 275, M20 277 and FDN 184, and 408 reprint stamps in 17 sets,
6 of them in FDN, which holds 190; `g3_etb_stamps.txt` reads every set): 91 verified trees hold
such a node. The 70 home stamps all predate the bug and record their real mutation counts. Of the
21 reprint stamps (`verify --reprint-of`, 2026-11-14, every one from an FDN home), **20 recorded 0
mutants made under the bug** where their home stamps record real counts: ELD Wind-Scarred Crag,
Thornwood Falls; IKO Swiftwater Cliffs, Blossoming Sands, Tranquil Cove, Bloodfell Caves, Rugged
Highlands, Jungle Hollow, Dismal Backwater, Wind-Scarred Crag, Scoured Barrens, Thornwood Falls;
THB Temples of Deceit, Abandon, Malice, Enlightenment and Plenty; WAR Orzhov and Simic Guildgates;
ZNR Gnarlid Colony. (M19 Diregraf Ghoul's 0 is its home's too, and the fixed G3's.) Gate round
11's reviewer ran the fixed G3 on them with their home packs: no critical survivor is uncovered.
They are not stamped again on this branch; the coordinator runs their verify again after the
merge.

**Tests and packs that fail on the base** (`base_runs.txt`): of the module's 46 tests, the 15
packs, the 2 selfplay tests and the G3 test, 58 fail on 1d5e4164 and 6 pass on both, controls (four
sentences the frame must leave unparsed; Unsummon unanswered returns the Troll, a test and a pack);
the lint test fails on main 1db792e1, where the lints came from. Required by the round's brief: a
cost that can't be paid
(`test_barkhide_troll_without_a_counter_cannot_activate`,
`test_hanged_executioner_cannot_pay_once_it_is_gone`, packs
`barkhide_troll_without_a_counter_cannot_pay`, `hanged_executioner_already_gone_cannot_pay_again`,
`fungal_plots_no_creature_card_cannot_pay`); the cost paid as the ability is activated, so removal
in response does not stop the effect (`test_hanged_executioner_is_exiled_as_its_ability_is_activated`,
`test_removal_in_response_cannot_reach_hanged_executioner`, packs
`hanged_executioner_exiled_as_it_is_activated`, `..._stays_exiled_when_its_target_is_bounced`; the
Troll's counter off at activation and its hexproof answering Unsummon,
`test_barkhide_troll_answers_a_bounce_with_hexproof`, pack
`barkhide_troll_hexproof_answers_unsummon`); two activations competing for one counter
(`test_two_activations_compete_for_the_trolls_counters`, packs
`barkhide_troll_one_counter_two_activations` and its falsifier
`barkhide_troll_two_counters_two_activations`). Gate round 11's tests, run on the merge commit
before its fixes (9c91ba1f): 19 fail for the faults themselves (13 of the 14 forms of
`test_a_cost_takes_the_payers_own_objects_in_one_form`, the 4 of
`test_an_exile_cost_takes_cards_from_the_payers_own_hand_or_graveyard`,
`test_one_cost_holds_one_exile_and_one_removal_of_a_kind`,
`test_a_segment_the_payers_picks_leave_short_raises`), 6 only for the refusal's new wording, and
three pass on both by design: the M17 killer, the M9 pin and the M5 tripwire.

**Blast radius** (by script over the 19 sets, base 1d5e4164; `blast_radius.txt`):
- trees changed: **12 compiler trees, 13 with records applied**, all unverified: M20 Hanged
  Executioner and Barkhide Troll (needs-atom records re-mapped), FDN Suspicious Shambler, M11
  Brittle Effigy, M12 Pentavus, M15 Soul of Zendikar, M19 Transmogrifying Wand, ELD Inquisitive
  Puppet, Steelbane Hydra and Tome of Legends, DOM Fungal Plots, ZNR Throne of Makindi, KHM Egon,
  God of Death's back face. 5 compile whole now (Hanged Executioner, Brittle Effigy, Inquisitive
  Puppet, Steelbane Hydra, Soul of Zendikar; Suspicious Shambler was refused). No M21 golden
  changes.
- verified cards whose trees changed: **0** (expected 0 for Keep); 0 leave, 0 join; the stamps
  match (M21 275, M20 277, FDN 184). Against main 4da972f1, with gate round 11's fixes: the same
  12 and 13 trees, 0 verified cards in or out of the 1,144 stamps (`blast_radius_4da972f1.txt`).
- still-verified trees with unchanged bytes on a touched path: 50: 49 hold a twin part, on the
  plan's and the payment's lanes (none holds both a counter part and a sacrifice or exile, the one
  case whose payment order changed), and M20 Sanitarium Skeleton and M21 Waker of Waves work off
  the battlefield (`activation_zone`). On the merged tree 64 (63 hold a twin part; the 408
  reprint stamps bring the others).
- **600 seeded heuristic games** (200 per verified pool: M21, M20, FDN; decks from the cards
  verified on both, 275, 277 and 184 deckable): **600/600 identical replay digests, journal dumps
  and raw event logs**, 0 crashes either side; 0 payments through the new parts (no verified tree
  holds one). **0 games' play differs**, so there is no first differing event to explain
  (`replay.py`, `replay_compare.py`); again 600/600 on the final commit 32ad5cb5, main merged;
  and 600/600 against main 4da972f1 with gate round 11's fixes (FDN 190 deckable with its 6
  reprint stamps; `replay_4da972f1.txt`).
- random-play soaks dealing the new trees (1,100 games: M20 compiled with the unverified records
  200, FDN compiled 200, ELD compiled 100, and castable pools of M11, M15, DOM, ZNR, M19, M12 and
  ELD, 100 each; `soak_coverage.txt`): **0 crashes**; payments through the new parts: Inquisitive
  Puppet 93, Fungal Plots 22, Steelbane Hydra 15, Brittle Effigy 13, Hanged Executioner 8,
  Suspicious Shambler 7, Barkhide Troll 2. 12 detector hits, none on a row of the round's cards:
  FDN Hungry Ghoul's counters after it returned from the graveyard (D3's presence model, 7 in a
  game that also cast the Shambler), FDN Scavenging Ooze (2), M15 Ajani's Pridemate (3 D5).
- ontology conformance (M21, ZNR): the V4′ CHOOSE baseline gains ZNR Throne of Makindi's one node,
  its CostRemoveCounter's source (IS_SOURCE, no decision: no ask, the payment's forced segment);
  then **PASS, errors 0, warns 7** (the base's 7).
- the partial trees: ZNR Throne of Makindi's two mana lack "Spend this mana only to cast kicked
  spells" and M19 Transmogrifying Wand's destroy lacks "Its controller creates a 2/4 white Ox
  creature token": stronger than printed the moment either pays its cost. Neither can: their
  charge counters come from their own unparsed sentences, and no compiled card of the 19 sets puts
  a charge counter on another permanent (`charge_sources.txt`: only ZNR Relic Amulet, on itself).
  A tripwire keeps it so (gate round 11, M5):
  `test_only_relic_amulet_gives_a_charge_counter_and_only_to_itself` fails the day a tree of any
  set, records applied, gives a charge counter another way (a PUT_COUNTER of the kind, or of no
  named kind, on anything but itself; a cost that puts one; a permanent entering with one); then
  the two cards need their missing sentences first, or to leave the pools.
  M12 Pentavus (a 0/0 whose counters are unparsed) and ELD Tome of Legends (its page counters
  unparsed) are inert, weaker. All four are dealt only by castable and all pools. The frame shares
  the B13-activated frame's gap (a composed ability whose drawback is a later sentence that does
  not parse): BACKLOG.

**Rejected.**
- The fold (above).
- One general part, `CostMoveZone(target, destination)`, for exile and discard (a sacrifice is its
  own action, 701.21a): with CostDiscard kept it is a second byte form of a discard cost; folding
  CostDiscard into it re-bakes 8 verified trees for one class fewer. A part per keyword action, as
  the union already has, stays.
- A `from` zone role on CostExile: the selector's zones already say where.
- One signed counter part for putting and removing, CostLoyalty's shape (a gate round 11 nit: the
  list left it out): CostLoyalty stays the grammar's one signed value (a planeswalker's costs are
  negative by definition); a sign would carry two payment rules (a put needs only its object, a
  removal needs the counters there, CR 118.3) and two asks; and CostPutCounter's 2 trees (both
  verified, M21 and FDN Mazemind Tome) would re-bake. A part per keyword action stays.
- A kind-less removal now (Soul Diviner, the one card): it needs a counter-kind ask with the kinds
  as option tokens (O_VALUE); it comes with its card. Likewise X, "all" and "any number".
- The exile written as a MOVE_ZONE step of the effect (the 2026-11-05 needs-atom note's own
  reason: a different ability, CR 602.2).

**Limits, logged** (BACKLOG): a cost's parts are judged against the board as it is before payment,
so a part that a later part of the same cost would make payable is not seen (a sacrifice whose card
an exile of the same cost then takes: no printed cost of the 19 sets has both); the partial trees
above; Feldon's Cane waits for D19's fold. After gate round 11: two exile parts, or two removals of
one kind, in one cost wait for a card and its matching (D26); an exile cost of an ability whose
card sits in the zone the cost exiles from never takes that card unless it names it (R11-2).

**Gate round 11's mutants** (the reviewer's battery, 15 of 19 killed on f242ad43). The four that
lived: M17 (every removal count read as 1) is killed now by
`test_the_frame_reads_how_many_counters_a_cost_removes`; M9 (the exile sent to the payer's exile),
M11 (the IR accepting a referent) and M14 (CR 605.1a no longer counting CostExile) are
equivalent. M9: the world files any card leaving for a zone but the battlefield under its owner
(R11-2). M11: a referent selector's zone set is `(Zone(ANY, ANY),)` (Selector's own check), which
the zone check refuses. M14: CostExile refuses a library zone, so `_cost_moves_library_card`'s
CostExile clause cannot fire today; it stays for the card whose exile cost takes a library card.
Re-run on 586fa91a with the gate's fixes each undone in turn (the source in one form, the payer's
permanents, one whole zone, one exile and one removal of a kind per cost, the raise on a short
segment): 5 of 5 killed, and M17 killed (`mutate_gate11.py`, `mutants_gate11.txt`).


## 17. Round R13 — PERMIT and REPLACE: playing a card from another zone (2026-11-17; gate round 13 FIX-THEN-GO, fixed)

KNOWLEDGE 209 §6-§7's first package for M21, M20 and FDN: "permission to cast or play a card from
another zone" (28 cards of the three sets, 19 needing only it; `reports/completion_2026-11-17/
worklist.json`), and the "exile it instead" paired with it. §10's R5-2 v3 (PERMIT_CAST), R5-3
(play_lands) and R5-12's rider were designed and never built; gate rounds 2-4's findings on them
stand and are met here. Branch `worktree-agent-a4af16b825120dda1`, main fdd1a021 merged (engine
wave C1 included).
Scripts and outputs: `reports/permit_2026-11-17/`.

**How plays were legal before (the root cause).** `legality.spell_castable` cast only from the
hand and `stack.land_playable` played only from the hand. A permission compiled as a free
activated ability whose `OptionalEffect(CAST)` cast the card as the ability resolved (Radha, Heart
of Keld; Conspicuous Snoop; Demonic Embrace's costed row): it cast at instant speed until a timing
patch (`query.permission_cast`), never played a land (B-100), needed a phantom screen
(`query.inert_row`) and kept the card out of the act menu. Duration permissions (both Chandras,
Furious Rise, Valakut Exploration) were suppressed at assembly; "If that spell would be put into
your graveyard, exile it instead" compiled as a static of the card over "any target" (B-99); the
CAST atom had no target channel and cast with X = 0.

**R13-1 `Verb.PERMIT`** (`ability_tree.py:184`; roles `_cast_roles_fault` :3363; placement
`permission_fault` :4203, `_cast_verb_misplaced` :4272). The seat may play the cards `source`
names from the zone it names (CR 601.3, 305.1).
- `source`: ALL over a zone (a population, read whenever a card would be played), TARGET over a
  graveyard or exile (designated as the ability resolves), or the `result` register whole (the
  cards the instruction before it moved, no filter). The zones: your graveyard, exile, the top of
  your library, your hand (with `alternative` only: the hand's own path is the rules', CR 117.1a).
- `lands`: True is "play" (lands are played, CR 305.1; spells cast); absent is "cast". A land is
  never cast (CR 305.9): a cast's filter names no land, and `lands` over cards that are never lands
  is refused.
- `alternative`: a Cost paid instead of the mana cost (CR 118.9; `Cost()` is "without paying its
  mana cost"); `additional`: a Cost added (CR 601.2f; never empty). Neither on lands only (a land
  play is a special action with no cost, CR 116.2a).
- `replace`: the spell's rider (R13-3). `count`: plays allowed (Idol of Endurance's "a creature
  spell"); never on a static, never as large as a designation (each designated card plays once,
  CR 400.7).
- `duration`: DurationEot, DurationUntilEndOfNextTurn, DurationPermanent ("for as long as it
  remains exiled": a designated object leaves the permission when it changes zones, CR 400.7).
- In a static ability it is the static's continuous effect, live while the static functions (CR
  604.2, 611.3a): a population, no duration, no count. A card's own permission (`IS_SOURCE`)
  functions from the zone it names (CR 113.6f): flashback (CR 702.34a), Demonic Embrace, Squee.
  In a resolving ability it is the effect the ability creates (CR 611.2a): the duration is
  required, and it outlives its source.
- Refused as second encodings: an OptionalEffect around it (the "you may" is the permission's
  use: a phantom ask), a granted static PERMIT ("each legendary card in your graveyard gains
  'You may play this card from your graveyard'" is a resolving PERMIT), EachPlayer or Repeat
  around it; since gate round 13 also `lands` over the hand, a cast filtered FNot(Land), a
  lands-only and a cast PERMIT over one zone in one ability (one PERMIT with `lands`), a resolving
  PERMIT over its own card as a population (it would cover the new object the card becomes, CR
  400.7), and a card's own permission over the hand (its spell's alternative cost, CR 118.9).

**R13-2 CAST, the one-shot cast** (CR 608.2g: cast while its ability resolves, ignoring timing).
Roles `source`, `alternative`, `additional`, `replace`: the old `cost` role (empty: a waiver; with
parts: added) split into the two PERMIT has, one meaning each. Refused: CAST in a static, in a free
activation (the old permission row), of its own card in an activation (the old Demonic Embrace
row, which CR 113.6m would make a graveyard activation at instant speed), of a land, of a permanent
or a spell, of a TARGET in a library or a hand (CR 400.2). `CostDeltaWaiveMana`, Omniscience's
second byte form, which the engine skipped, is retired: Omniscience is the static PERMIT over the
hand with `alternative=Cost()`.

**R13-3 REPLACE: the spell's rider** (`spell_rider` :3281). "If that spell would be put into your
graveyard, exile it instead" (CR 614.1a, 614.6) and flashback's "exile it instead of putting it
anywhere else any time it would leave the stack" are a cast verb's `replace` role, exactly the two
values `spell_riders()` returns. The engine applies the frame's rider wherever the spell leaves the
stack (`stack.exit_zone` :295: resolution, a fizzle; any effect's move of a spell, a counter or
Unsubstantiate's return included, through `verbs._off_the_stack`, which also ends the frame: gate
round 13), before engine wave C1's
replacements of the move from anywhere (`stack._put_off_the_stack`, `verbs._move_all`): every rider
exiles, so whichever the controller applies first (CR 616.1) the spell is exiled. A card-level
replacement of a zone change from the stack is refused (B-99's tree). No `Verb.REPLACE`: a rider
exists only on the spell its verb casts; R5-12's resolving replacements (Chandra, Awakened
Inferno's die-to-exile) stay their own piece.

**R13-4 The engine.**
- `executor/permits.py`: `paths` (:162), every way a seat may cast a card now, one per cost path
  (R5-2 v3 point 6; an uncounted permission first, then the older): live "permit" layer records (a
  static's from its source's statics, a resolving one's from `layers.register_permit` :454), then
  the card's own permissions; a designation drops an object that moved since it resolved
  (`returns.moved_since`, CR 400.7). A land's play is `land_path` (:231) over every permission,
  never lost to a cast permission sharing its cost path.
- The menu (`menu.py:113`): `land:<card>` from any permitted zone; `cast:<card>[:via:<source>]`,
  with `via` only for a path that is not plain (another cost, a rider). Timing is the card's
  (`legality.card_window_reason`): a permission changes where from and at what cost, never when
  (CR 601.3).
- A land played from another zone is the turn's land play (CR 305.2a; `stack.land_playable` :260,
  `play_land` :1316). A cast through a path (`stack.cast` :715) pays the path's cost
  (`legality.spell_castable` :1582; X is 0 unless the alternative has an X, CR 107.3b), uses one of
  its plays (`permits.use`) and journals the zone it came from.
- `stack.cast_card` (:1111), CAST's lane: asks the caster for X (:1255) and for each target (:1281)
  as the spell is cast (CR 601.2b-c), prices a target-dependent cost after its targets; the
  may-offer is offered only for a card whose targets can be chosen and whose cost can be paid
  (`query._cast_option_payable`).
- `verbs._v_permit` (:2000). The library pop (`pop_order` TOP) writes `result` (`verbs.py:245`):
  "exile the top three cards ... you may play them" reads all three.

**R13-5 What the network sees.** A permission's play is a land or cast row: the card's entity
carries the zone it is played from (the top of a library joins the entities as an offered card),
and `:via:<source>` points the option's second entity at the permission's source
(`tools/selfplay/features.py:464`). No new ask kind, option type or column; the bench names the
card (`bench/router.py`). Old checkpoints compute the same (below).

**CR basis**: 601.2a-i, 601.3, 305.1, 305.2a, 305.9, 116.2a, 117.1a, 113.6f, 113.6m, 118.9,
107.3b, 604.2, 608.2g, 611.2a, 611.2c, 611.3a, 400.7, 614.1a, 614.6, 702.34a.

**Rejected.**
- R5-2's PERMIT_CAST and R5-3's play_lands as two verbs: "play" is one permission over lands and
  spells (CR 305.1, 601.3; Chandra, Heart of Fire's "play cards exiled this way"), so one verb
  with `lands`.
- A `Verb.REPLACE` atom for the rider (R5-12's route): it would be a second encoding of the role, or
  a rider with no spell.
- A filter on the `result` register ("cast a creature spell from among them") and other registers:
  refused until a card brings them; the engine reads the register whole.
- "As though it had flash" in the same verb (KNOWLEDGE 209 §7): it changes when, not where; its
  round decides. A card's own optional alternative cost (M20 Sephara) is a SpellAbility piece.
- A set fixed at resolution for a resolving population (Kethis: "gains" changes characteristics,
  CR 611.2c): waits for its card.
- Keeping `CostDeltaWaiveMana`.

**Census** (19 sets, records applied): 33 PERMIT atoms (ALL over a graveyard 12,
over the top of a library 8, over the hand 4, over exile 1, over exile and a graveyard 1; the
`result` register 4; TARGET over a graveyard 3) and 2 CASTs (ZNR Coveted Prize's ONE_OF over the
hand with `alternative`; M21 Chandra, Flame's Catalyst's TARGET over the graveyard with the rider).

**Blast radius** (`tree_dump.py`, `tree_diff.py` against main 4739cfef, engine wave C1 included; the same against fba0ea20):
- 35 compiler trees change in 11 sets, and 2 M20 records are mapped (Golos, Tireless Pilgrim;
  Mystic Forge; unverified). 10 cards newly compile whole (10E and M19 Crucible of Worlds, DOM
  Squee, FDN Omniscience, Sphinx of Forgotten Lore, Think Twice, M12 and M14 Garruk's Horde, M13
  and M19 Omniscience); 26 have fewer unparsed sentences. 4 have one more, each a sentence that was
  wrong or suppressed: M21 and THB Furious Rise (an event-ended window, B-100), M20 Chandra,
  Acolyte of Flame and WAR Dreadhorde Arcanist (a rider whose cast sentence does not parse).
- Verified: M21 Idol of Endurance leaves (its tree changes: the activation's permission is a
  PERMIT); none joins; every other stamp matches (1,149 → 1,148).
- Deal pools: M21 engine and castable 280 → 283 (the two Chandras, Demonic Embrace; dropping them
  reproduces the stress-pile hash); M21 compiled loses Furious Rise; FDN compiled 193 → 196.
- 300 seeded heuristic games on the verified pools (100 each of M21, M20, FDN; 274, 279 and 193
  deckable, the stale Idol out on both sides): 300/300 identical replay digests, journal dumps and
  raw event logs, 0 crashes either side, no cast or land play through a permission (none dealt).
- Old networks: a checkpoint made under main and loaded under the branch reads 128 decisions of
  six M21 and FDN games (15 ask kinds) to bitwise-equal encodings, tokens, logits and values.
- Soak (`soak_coverage.py`: `tools/cards/soak.py`'s games and abuse screen, 1,100 random games:
  M21 300, FDN 200, M20 200 with the unverified records, ZNR, M19, DOM, M12 100 each): 0 crashes;
  permissions resolved 107 times, casts through a permission 70, land plays 40, riders 12;
  abuse screen: no repeatable activation, no trigger loop, two win-rate outliers, both low and
  neither a permission card (M21 Discontinuity, Spirit of Malevolence). D6 flagged a resolved
  permission live at game end over exiled cards (4 games): D6 now knows a resolved permission
  outlives its source and covers cards off the battlefield (CR 611.2a, 601.3; a test). With it,
  the M21 and FDN soaks' remaining hits (two replacement records for one damage event, a delayed
  trigger pending at the end, a mandate_block layer) are classes main fba0ea20's soak on the same seeds
  shows too (`soak_main_*.json`, `soak_branch_*.json`).

**Tests and packs.** `test_ability_tree_permit.py` (20 cases: accepted shapes, zones, durations,
static rules, roles, one encoding of "may play", refusals), `test_executor_permit.py` (18:
impulse until end of turn then gone, a resolving permission outliving its source, a card that
moves leaving it, the land drop, flashback and a countered flashback exiled, Chandra's recast with
its target and rider, Demonic Embrace's costs, a static ending with its source, timing, Idol's one
cast, Omniscience's two paths, the land path, X with an alternative cost), one each in
`test_selfplay.py`, `test_router.py`, `test_detectors.py`. Packs: 9 new (four that fail on main
for the brief's behaviours, Chandra's targeted recast out of `known_bugs`, four mapped M20), 14
rewritten from the old rows. The V4' CHOOSE baseline moves for exactly six cards and V5' registers
Idol's population over exile (`reports/ontology_census_2026-11-17_permit_post_full.json`).

**The fresh-eyes review** (one reviewer on the code diff, 2026-11-17): 3 MAJOR, 3 MINOR, 1 NIT,
all fixed but one MINOR. MAJOR: `CostDeltaWaiveMana` was a second encoding (retired); a referent
`source` was not checked (a filter on `result` ignored, a `source` register a crash: refused); roles
that limit or add nothing were accepted (`lands` over non-lands, a count as large as a designation,
a designation in a library or a hand, a CAST of a permanent: refused). MINOR: a cast permission
sharing a cost path hid a land play (`land_path` over every permission); the bench did not name a
card offered from the top of a library (named); Valakut Exploration plays stronger than printed in
the partial pools (logged, BACKLOG: its end-step sentence is the fix). NIT: an alternative cost
with X announces X (CR 107.3b).

**Limits, logged** (BACKLOG, "The permission lane still blocked"; "What the network sees"): Furious
Rise's event-ended window; Kethis's set fixed at resolution; another player's cards (Etali,
Tinybones); a permission shows only as the rows it offers; divergences D31 (the two forms of
"exile the top card") and D32 (permission-like atoms still wrapped in OptionalEffect).
