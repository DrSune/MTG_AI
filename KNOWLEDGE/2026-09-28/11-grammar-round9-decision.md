# 2026-09-28 · 11 — Grammar round 9 BINDING spec (hard tail: windows, mana policy, delayed triggers, embedded IR)

Status: BINDING. Analyst draft (session ses_f15ee8f49ffemej97EjhpNWq0b) + orchestrator anchor
re-verify at HEAD 7efde7a: ActivatedAbility L2259 has condition (r3/T3r4) NO timing slot;
TokenSpec.abilities: tuple[Ability,…] L1672 IR-typed but filled EMPTY at all 21 template sites
⇒ embedded-IR rows need NO nested compile (H3 refuted); QAgg={FIRST,MAX,MIN,SUM} L333 (no
distinct-count); "When you do" prefix already registered compiler L138 (queued since r8-A).
Queue 21/21; PC-1 287/305 PC-2 618/639; suite 1521; orphans 1. Conventions C1–C19 in force.
Phase plan (autonomy /04): 9-A grammar → 9-B batch (13 rows) → measure → knowledge → commit.

## 9-A grammar items (additive; tests → test_ability_tree_r10.py [offset rule]; compiler touches = R9-9 only)

- R9-1 ActivationWindow enum {SORCERY, INSTANT} + ActivatedAbility.timing: ActivationWindow|None=None
  trailing; _SPECS += ("timing","opt:enum-kind" — mirror existing enum-field tag form); _OMIT_IF_EMPTY
  ActivatedAbility += "timing". C20.
- R9-2 FAtomPred.LIFE_LEAD_OVER_START_GE {count} (Speaker; executor reads life-total delta from
  start; rule row {count}-only like CARDS_DRAWN-style).
- R9-3 Verb.MANA_POLICY roles {scope: True, filter: False} — scope = string-pair vocabulary
  ("THIS_MANA" Vodalian / "ALL_YOURS" Orrery-spend; C21; carry via AtomArgs pairs, no new _SPECS
  field per R8-5 dealer/recipient precedent; filter over CastSpellEvent shape like IS_INSTANT…
  — executor-deferred orphan OK).
- R9-4 Step.UNTAP member + PREVENT_EFFECT roles += "step": False + DurationUntilNextStep(step,
  owner_scoped: bool) dataclass into Duration union + _DURATION_TAGS (Frost Breath; registers r6
  item-3 closure).
- R9-5 DelayedTrigger(duration: Duration [REQUIRED], event: EventSpec, condition: Filter|None,
  effect: Effect) into Effect union + _SPECS + _EFFECT_TAGS; C22: lives inside creator's effect,
  never standalone Ability (Subira).
- R9-6 QDistinctColorCount(selector: Selector) dataclass → Quantity union + _SPECS +
  _QUANTITY_TAGS + _Q_CLASSES/_DATACLASSES registration (Orrery draw-per-color; QAgg has no
  distinct-count — verified).
- R9-7 Verb.GRANT_ACTIVATION roles {filter: True, window: False} (Teferi NAME_CONTAINS("Teferi")
  gate — closes 8-C withdrawal; window reuses R9-1 enum).
- R9-8 REVEAL roles += duration: False (Snoop "Play with the top card … revealed" as
  DurationPermanent continuous state — top-of-library implicit per LOOK_AT convention /10).
- R9-9 compiler `_merge_do_continuation` (Kraken): "When you do" where prior effect =
  OptionalEffect(PAY-atom) → INJECT the parsed optional INSIDE the prior OptionalEffect
  (search-shuffle twin at ~compiler 680; _merge_otherwise r7 twin shape). Any other prior →
  existing C13 fallback. C24: sibling append FORBIDDEN (would fabricate an independent optional).

## Conventions (new, binding)

- C20 timing slot only on ActivatedAbility; SORCERY = own main phase + empty stack.
- C21 MANA_POLICY scope THIS_MANA (event-anchored to the ability's ADD_MANA) vs ALL_YOURS
  (DurationPermanent permission).
- C22 DelayedTrigger = effect node inside creator; duration mandatory.
- C23 embedded quotes: vocabulary-covered quoted text → template pattern-locks hand-built IR
  literals into TokenSpec.abilities; quote text NEVER serialized as payload; uncovered quotes
  (Herald [−7] damage-assignment) stay queued; emblems remain C19 marker-only.
- C24 "When you do" = inner injection only; never sibling append.

## 9-B batch (13 rows; bucket ownership = binding, verify keys at dispatch)

b5a 3: Steward (timing=SORCERY), Speaker (timing + LIFE_LEAD cond — DROWSING also b5a), Drowsing
(StaticAbility(cond, LOSE_ABILITY kw=DEFENDER, DurationWhileCondition) — fidelity argument:
defender's only M21-relevant rules effect is the can't-attack; coincide; C11-class docstring note).
b2a 1: Pursued Whale (CREATE_TOKEN, TokenSpec(abilities=(StaticAbility(PREVENT block w/
target-self), Atom(MANDATE_ATTACK)),…)) — C23; b2a-pin caution.
b2b 1: Kraken (template for s2 + R9-9 merge).
b3 1: Orrery "{5},{T}: Draw … each color among permanents" (DRAW QDistinctColorCount(Selector(
ALL, permanent, YOU))).
b4 3: Orrery-spend (MANA_POLICY ALL_YOURS DurationPermanent), Teferi (GRANT_ACTIVATION),
Enthralling (StaticAbility(PREVENT_EFFECT(event=TargetingEvent(cond=IS_UNTAPPED…)),…)) —
riskiest row; C11-class note "choice-restriction ≈ owner-scoped targeting prevention"; fallback =
WITHDRAW if PC-3/semantics disagree.
b5b 2: Vodalian (MANA_POLICY THIS_MANA, filter instant-or-sorcery), Snoop "Play with the top card
of your library revealed." (REVEAL+DurationPermanent — PC-2 only; Snoop card stays queued for
grant-all-abilities).
b5c 2: Frost Breath s2 (PREVENT(TapState UNTAP step-scope) over referent-target — real card
"Tap up to two…" verified, plural matches), Subira s2 (DelayedTrigger(EOT,
DamageDealtEvent(combat, source=power≤2 creature, to=player), effect=DRAW)).
Also: repair stale b5a UNCOVERED reasons @1896-1903 ("no condition slot" — shipped r4; real gap
was sorcery-speed — now R9-1).

DEFER → R10 (named, 8 shapes): Transmogrify ×2 (RepeatUntil + CardRevealed — control-flow loop,
1 card); Chrome same-name (exists-quantifier over name partition); Mangara attacked-relation
(preds ×2); Snoop grant-all-abilities (dynamic ability-set introspection); Waker "who can't"
(couldn't-perform pred over action history); Sanctum additional-trigger (AbilityTriggeredEvent +
duplication semantics); Herald [−7] quoted damage-assignment (assignment-rule vocabulary absent).

## PC-3 risk pairs (analyst D4, binding pre-checks)

"Until end of turn, whenever" vs "…you may" (discriminator 'whenever', order-first) ·
"Spend this mana only…" vs "spend mana as though…" · "Activate only as a sorcery" vs Speaker
compound (longest-match first) · "each color among" vs THIS_WAY "for each" tails ·
When-you-do merge gated to prior=Optional(PAY) only · Frost "Those" target-register vs result ·
REVEAL role addition validation-only.

## Predictions

9-A: suite 1521+N, goldens byte-identical, PC-1/2 unchanged. 9-B: PC-1 287→298/305 (0.9770; 11
FULL: Steward, Speaker, Drowsing, Vodalian, Orrery, Frost, Kraken, Subira, Teferi, Enthralling,
Whale), PC-2 618→631/639 (+13), queue 21→8 (named above), orphans stay 1 (MANA_POLICY +
GRANT_ACTIVATION consumed same round — orphan-in/orphan-out per MANDATE_BLOCK precedent).
