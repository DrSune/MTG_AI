# 2026-09-28 · 03 — Grammar round 7 spec (family-2 anaphora + full-queue residual)

Status: BINDING (orchestrator-verified 2026-09-28). §1 anchors independently re-checked at HEAD
0726e93: `_QPROP_STR_REFERENTS=("source","controller","target","event")` L526; `Conditional.
else_effect` EXISTS L1917 (R7-3 "Otherwise" = zero IR grammar delta, compiler merge only);
`GAIN_CONTROL` role-less L2706 (duration role added by R7-2); NO Verb.FIGHT (grep empty);
_CONTINUATION_PREFIXES compiler L124 (note: "If it " prefix already merges "If it WAS…").
ORCHESTRATOR AMENDMENT (binding): R7-3 "When you do" — the trigger must bind to the EVENT of the
antecedent's optional action (e.g. Tolarian Kraken: if its s1 is "you may draw a card" →
CardDrawnEvent scoped to that ability), NOT a blanket AbilityActivatedEvent. Implementer verifies
the real M21 card text; if no clean event binding exists, WITHDRAW the row to queue (1 shape).
Batch dispatch plan (owner autonomy grant 04): grammar phase → R7-A batch (30 core rows) →
R7-B batch (9 top-ups) as three sequential delegations, each with its own measure + goldens
re-baseline audit; commits land autonomously at round end (no owner gate).
Ground truth from analyst draft preserved below verbatim (Status was GROUNDED DRAFT; verified).
Ground: live queue `/tmp/queue_post_r6.txt` — 85 shapes / 87 occurrences, PC-1 241/305,
PC-2 552/639 (552+87=639 ✓ occurrence-denominated). Precedents: 2026-09-28/01 (r6),
/02 (r6 results), 2026-09-24/05 (r4 anaphora conventions). Conventions C1–C11 in force.
Invariants: additions only — no `split_sentences` change, 639 denominator frozen, no
existing enum-semantics or field-order changes. Serialization pitfall (PITFALLS 2026-09-28):
no new optional fields are introduced by any item below, so the `_OMIT_IF_EMPTY` trap is
avoided by construction.

## 0. Triage (all 85 shapes; taxonomy defined hereby)

- **A — this round, needs new grammar**: 34 shapes / 36 occurrences (the 2 duplicated
  shapes each occur 2×).
- **B — this round, template-only** (grammar already exists, no template): 13 shapes.
- **C — deferred, already-registered families** (r6 §Deferred): 10 shapes —
  Conspicuous Snoop ability-grant · Drowsing Tyrannodon as-though · Sanctum of All
  additional-trigger · Garruk Herald [−7] as-though · Mangara set-quantity/attacked-rel ·
  Enthralling Hold target-legality · Chromatic Orrery as-though mana · Frost Breath
  next-untap scope (Step.UNTAP, r6 item 3) · Chrome Replicator same-name-as-one-another ·
  Pursued Whale quoted-token-abilities.
- **D — deferred, families registered this round**: 27 shapes —
  (D1 cast-timing) Liliana's Steward · Speaker of the Heavens · (D2 mana-restriction)
  Vodalian Arcanist · (D3 top-library ops) Snoop play-revealed · Radha look/play-top ·
  (D4 permission may-cast/play) Chandra Flame's Catalyst · Chandra Heart of Fire ×2 ·
  Teferi loyalty-any-turn · Furious Rise · Azusa · Idol activated · (D5 emblem verb)
  Basri [−6] · Garruk Unleashed [−7] · Liliana [−7] + Waker "Each opponent who can't"
  back-ref = 4 · (D6 comparative-count) Garruk Unleashed "Then if an opponent controls
  more creatures than you" (no comparison FAtomPred exists — grep verified) ·
  (D7 quantity-algebra) Invigorating Surge "double the number of counters" ·
  (D8 token-enters-tapped-and-attacking) Basri Ket [−2] · (D9 rounding math) Peer into
  the Abyss ×2 · (D10 duration-scoped delayed trigger) Subira · (D11 for-each-distinct-
  attribute) Orrery draw-per-color · (D12 cost-per-each) Sanctum of Tranquil Light ·
  (D13 where-X-is-redefinition) Chandra's Incinerator · (D14 reveal-until dig)
  Transmogrify ×2 — NOTE bucket assigns these two to B5b but no reveal/until machinery
  exists (no CardRevealed event class; event classes 1021–1369 checked); flag for
  bucket refresh.
- **E — ingest artifact**: 1 shape — `It gains haste."` (Liliana, Waker of the Dead):
  raw M21.json text ends `…under your control. It gains haste."` — stray closing quote of
  the emblem quote; clean emblem text lives in tokens[]. Row stays queued; do NOT touch
  splitting (denominator frozen).

## 1. Grammar items (all additive to `ability_tree.py` + `compiler.py`)

| ID | Delta (verified anchors) | Motivating shapes | Byte-stability |
|---|---|---|---|
| R7-1 | Referent vocabulary extension: `_QPROP_STR_REFERENTS` (526) `+= ("result",)` = "the card(s) the previous sentence acted on (revealed/chosen/exiled/moved)". Compiler keeps a per-ability *result register*; templates annotate, continuation pass binds. Plus `Verb.CHOOSE` (pick from set, records result) and `FAtomPred.IS_ATTACHED_TO` {referent} (Turn to Slag) | "It gains …", "You choose … from it" (Duress/Kitesail), "That player discards that card", "Untap that creature", "If it('s/was) …", "Then it fights", See-the-Truth "those cards", Scavenging Ooze "If it was…" | bare-string vocabulary — serialization already emits plain strings (3286–3293); no tree emits "result" pre-batch → goldens byte-identical |
| R7-2 | `DurationUntilLeaves` dataclass after 994 + `Duration` union member (1007–1009); `_VERB_ROLES[GAIN_CONTROL]` (2706) `+= {duration: False}` | Kitesail "until this creature leaves the battlefield", Idol ETB, Traitorous Greed s1 | new union member; role table is not serialized (r6 R6-3 precedent) |
| R7-3 | Compiler: `_CONTINUATION_PREFIXES` (124–132) `+= ("Otherwise", "When you do")`. "Otherwise" → new merge strategy: set `else_effect` (exists, 1917, opt-tagged, omit-if-None) on the previous Conditional; fall back to the default OptionalEffect-seq merge (887–892) when prev is not a Conditional. "When you do" → new `AbilityActivatedEvent` (event classes 1021–1369 have none) + TriggeredAbility gated on it | Garruk Savage Herald "Otherwise", Tolarian Kraken | prefix list + new event enum member; previously-unparsed sentences only |
| R7-4 | `Verb.CHOOSE_NAME` {name_filter} + `FAtomPred.NAME_CHOSEN` (no slots) for "cards with that name" / "the chosen card name" | Runed Halo pair, Necromentia 3-sentence chain | new enum members only |
| R7-5 | `QPropField.THIS_WAY_COUNT` (referent "event"; validation pattern per docstring 244–256) | "for each creature tapped this way" (Siege Striker), "for each card exiled … this way" (Necromentia s3) | new enum member |
| R7-6 | `QPropField.THAT_MANY_COUNT` (count selected by the preceding up-to-X choice in the same ability) | Kinetic Augur "discard up to two … draw that many" | new enum member |
| R7-7 | `SelectorMode` `+= (ONE_OF, REST)` (modes at ~667–746; validation 728 accepts vocabulary automatically) | Waker of Waves, See the Truth, Garruk's Harbinger, Cultivate | new enum members |
| R7-8 | `Verb.FIGHT` + `_VERB_ROLES` row {target: True} (attacker = source/IT referent). Executor deferred per MANDATE_BLOCK orphan precedent (PC-6 unaffected) | Brash Taunter, Primal Might — keyword FIGHT today exists only as `FAtomPred`/`Keyword` (437), no Verb | new enum + role row |
| R7-9 | (a) `Verb.LOSE_ABILITY` mirroring `GRANT_ABILITY` roles {target, ability, duration} (2679); (b) relax QProp `COUNTER_COUNT` referent validation (244–246: today event-only) to admit `source`; counter-kind slot detail to be checked by implementer against QProp fields | Soul Sear "loses indestructible", Malefic Scythe "for each soul counter on this Equipment" (SOUL kind exists 396, HAS_COUNTER 315) | new members; validation relaxation adds no output to existing trees |

## 2. Binding conventions (new)

- **C12**: anaphora binds ONLY to structured referents (`Selector.referent` strings /
  result register). IR must never encode English antecedent substrings. The result
  register is compiler-assembly state, not tree content.
- **C13**: "Otherwise" without a preceding Conditional in the same text compiles via the
  legacy default continuation merge (OptionalEffect seq) — never a parse failure.
- **C14**: spelled-out numbers stay word-pinned as QConst in template rows (standing
  rule; e.g. "create two", "any number").

## 3. Template batch (bucket = unique JSON-key owner, `/tmp/opencode/phase1_buckets`)

### R7-A core (grammar-dependent)

| tid | mod | shape → card | IR sketch | dep |
|---|---|---|---|---|
| B5b-it-gains-kw-eot | b5b | "It gains indestructible EOT" (Basri Ket, Seasoned Hallowblade) · "…haste EOT" (Traitorous) · "…vigilance EOT" (Basri Devoted Paladin) | GRANT_ABILITY(target=result/IT, KeywordAbility(KW), DurationEot) | R7-1 |
| B5b-it-gains-haste | b5b | "It gains haste." (Liliana emblem) | GRANT_ABILITY(…, no duration) | R7-1 |
| B5b-it-gains-protection-choice | b5b | Feat of Resistance | GRANT KeywordAbility(PROTECTION, Filter from Choose(color-options)) on IT | R7-1 |
| B4-you-choose-from-it | b4 | "You choose a noncreature, nonland card from it." (Duress, Kitesail) | Verb.CHOOSE(Selector(¬TYPE_EQ creature, ¬TYPE_EQ land), from=result-library) | R7-1 |
| B5b-that-player-discards | b5b | Duress s3 | DISCARD(target=prior target player, cards={result}) | R7-1 |
| B5a-exile-that-until-leaves | b5a | Kitesail s3 | EXILE(result, DurationUntilLeaves(source)) | R7-1/2 |
| B5b-gain-control-eot | b5b | Traitorous s1 | GAIN_CONTROL(target, DurationEot) | R7-2 |
| B5c-untap-that-creature | b5c | Traitorous s2 | UNTAP(THAT creature = result) | R7-1 |
| B5b-if-it-type-then | b5b | Garruk s2 "If it's a creature card, put it into your hand" · Track Down "If it's a creature or land card, draw a card" | Conditional(FAtom(TYPE_EQ/…, ref=result), …) | R7-1 |
| B5b-otherwise-bottom | b5b | Garruk s3 | else_effect on preceding Conditional | R7-3 |
| B5a-etb-choose-name | b5a | Runed Halo s1 | TriggeredAbility(ETB, CHOOSE_NAME) | R7-4 |
| B5a-choose-name-not-basic | b5a | Necromentia s1 | CHOOSE_NAME(filter ¬SUPERTYPE_EQ Basic) | R7-4 |
| B4-protection-chosen-name | b4 | Runed Halo s2 | StaticAbility(GRANT KeywordAbility(PROTECTION, Filter(NAME_CHOSEN))) | R7-4 |
| B5b-search-name-exile | b5b | Necromentia s2 (search GY+hand+library, any number, that name) | CHOOSE(up-to-any, zones, NAME_CHOSEN)+EXILE(result set) | R7-4/1 |
| B5b-token-per-exiled-this-way | b5b | Necromentia s3 | CREATE_TOKEN(count=QProp(THIS_WAY_COUNT,event)×2/2) | R7-5 |
| B4-per-tapped-this-way | b4 | Siege Striker | MODIFY_PT(+1/+1 per QProp(THIS_WAY_COUNT), EOT) | R7-5 |
| B5a-equipped-per-soul-counter | b5a | Malefic Scythe | StaticAbility(MODIFY_PT per QProp(COUNTER_COUNT, source, SOUL)) | R7-9b |
| B5b-loses-kw-eot | b5b | Soul Sear | LOSE_ABILITY(THAT permanent, KeywordAbility(INDESTRUCTIBLE), EOT) | R7-9a |
| B2a-draw-that-many | b2a | Kinetic Augur ETB | Seq(choose-¬discard-up-to-2, DRAW(QProp(THAT_MANY_COUNT))) | R7-6 |
| B2a-etb-exile-until-leaves | b2a | Idol of Endurance ETB | EXILE(all GY creature cards CMC_LE 3, DurationUntilLeaves) | R7-2 |
| B2b-when-you-do | b2b | Tolarian Kraken | TriggeredAbility(AbilityActivatedEvent, OptionalEffect(Choose(tap,untap))) | R7-3 |
| B5b-one-of-other | b5b | Waker of Waves | Seq(MOVE(ONE_OF result→hand), MOVE(OTHER/REST→GY)) | R7-7 |
| B5b-one-of-rest-bottom | b5b | See the Truth s1 | MOVE(ONE_OF→hand) + MOVE(REST→bottom, any order) | R7-7 |
| B5b-rest-bottom-random | b5b | Garruk's Harbinger s1 | MOVE(REST→bottom, random order) | R7-7 |
| B4-reveal-one-from-among | b4 | Garruk's Harbinger s2 (creature or Garruk PW → hand) | OptionalEffect(MOVE(ONE_OF(set)→hand, reveal)); NAME_CONTAINS "Garruk" ✓ | R7-7 |
| B5b-search-one-other-shuffle | b5b | Cultivate | search up-to-2 basic lands → MOVE(ONE_OF tapped→BF) + MOVE(OTHER→hand) + shuffle (search-shuffle built-in ✓) | R7-7 |
| B5b-cast-elsewhere-instead | b5b | See the Truth s2 | Conditional(FAtom(CAST_THIS_TURN_FROM ¬hand ✓354), MOVE(each of result set→hand) replacement) | R7-1 |
| B3-fights-target | b3 | Brash Taunter | Activated → Verb.FIGHT | R7-8 |
| B5c-then-it-fights | b5c | Primal Might | "Then " continuation ✓ + FIGHT(attacker=IT) | R7-1/8 |
| B5a-destroy-equipped | b5a | Turn to Slag | DESTROY(Selector(Equipment, FAtom(IS_ATTACHED_TO, referent))) | R7-1 |

### R7-B top-ups (no grammar)

| tid | mod | shape → card | IR sketch |
|---|---|---|---|
| B5b-keyword-list-params | b5b | Baneslayer Angel · Sporeweb Weaver | KeywordAbility list w/ PROTECTION+HEXPROOF Filter params (param-extraction; `_KEYWORDS_BARE_UNBUILDABLE` incl. PROTECTION) |
| B5b-if-died-two-tokens | b5b | Fungal Rebirth | Conditional(FAtom(DIED_THIS_TURN ✓325), CREATE_TOKEN(QConst 2 word-pinned)) |
| B5b-would-damage-incarnation | b5b | Nine Lives | ReplacementAbility(✓2131) DamageDealt→you: Seq(PREVENT, PUT_COUNTER(INCARNATION ✓393)) |
| B5c-flip-cost + B5b-flip-won | b5c/b5b | Tavern Swindler ×2 | CostLife ✓ + Flip; Conditional(FLIP_WON ✓340, gain 6) |
| B5b-choice-of-grants | b5b | Alchemist's Gift | Seq(MODIFY_PT, Choose(1,{GRANT deathtouch, GRANT lifelink}), EOT) (Choose ✓1877) |
| B5c-then-if-lands-untap | b5c | Fabled Passage | Seq(…, Conditional(CONTROLLER_COUNT_GE(land,4), UNTAP(target ✓R4))) |
| B2b-blocks-flying-pump | b2b | Snarespinner | TriggeredAbility(DeclareBlockersEvent(blocked=KEYWORD_HAS flying) ✓R6-4, MODIFY_PT EOT) |
| B5c-damage-equal-power | b5c | Hunter's Edge | Seq(…, DAMAGE(source=target, amount=QProp(POWER,target) ✓248)) |
| B5b-its-controller-×3 | b5b | Angelic Ascension · Secure the Scene · Liliana, Death Mage | controller-referent ✓2621 Gloom-Sower precedent + CREATE_TOKEN / LOSE_LIFE |

39 rows / 47 shapes / 49 occurrences. Not full-card: Basri Ket, Garruk Savage Herald,
Idol of Endurance, Subira (residual rows stay queued).

## 4. PC-3 risk pairs (double-match candidates; re-gate must measure 0)

- "It gains KW EOT" vs r6 B4-during-turn-grant-kw (Radha) — disjoint by "During your
  turn" prefix vs "It gains" subject.
- "Otherwise" prefix vs existing Conditional templates (Garruk-while b4, Gnarled Sage
  b5a:283) — new prefix cannot capture existing sentences (prefix literal-match).
- "that card/that player" matchers vs Subira self/target pair (r6 precedent) and R4
  target-referent templates — result-ref fires only when result register is set.
- THIS_WAY_COUNT matcher vs search-shuffle built-in (compiler 887) — disjoint tails.
- NAME_CHOSEN vs NAME_EQ/NAME_CONTAINS — distinct predicates, literal-vs-chosen.

## 5. Predictions (queue is truth; ± bands are noise, not failure)

- Grammar phase: suite 1333 → 1333+N (new tests in `test_ability_tree_r8.py` — offset
  rule confirmed: r6 grammar shipped in r7 file); **goldens byte-identical**, 0 diffs.
- Batch phase: PC-2 552 → **596–601/639** (+49 covered occurrences); PC-1 241 →
  **~262–276/305** (35 full cards; emblem-token accounting = noise); queue 85/87 →
  **38/38**; exactly 39 goldens re-baselined (abilities-key-only audit vs pre-round copy).
- PC-3 = 0 and full suite green are hard gates before golden refresh.
