# 2026-09-29 · 02 — Grammar round 10 BINDING spec (final residual: 4 tractable + 4 permanent-defer)

Status: BINDING. Analyst draft (ses_f154d39bbffeHKC829riMbjZhJ) + orchestrator anchor-verify at
HEAD 901e8cc: ActivationGateOutcome (templates.py:104-114) carries ONLY `condition`; compiler
attach @1290-1309 finds nearest preceding unconditional ActivatedAbility (StateCorruptionError
if none) → Steward tractable by adding a window slot + slot-disjoint attach (H1 ✓). DeclareAttackersEvent
@1404 has filter/subject but NO attacked slot (H3 ✓). FAtom inner_filter/count slots exist
(L1080/1084) → Chrome partition pred self-contained (H2 ✓). MANA_POLICY scope-tuple precedent
(atom-arg, no _SPECS field) → Herald damage-policy twin (H4 ✓). PC-1 297/305, PC-2 630/639
(stretch met), queue 9. Conventions C1–C24 in force.
Phases (autonomy /04): 10-A grammar → 10-B batch (4 rows) → measure → knowledge → commit.

## 10-A grammar items (additive; tests → test_ability_tree_r11.py [offset rule]; compiler = R10-1 only)

- R10-1 Steward activation-timing gate: ActivationGateOutcome (templates.py:104) += `window:
  ActivationWindow|None=None`, condition becomes optional (None|Filter); __post_init__ rejects
  both-None; compiler gate-collect (L1131) + attach (L1290): slot-disjoint apply — if window set
  require ab.timing is None then replace(ab, timing=window); if condition set require ab.condition
  is None then set condition (existing). A gate setting both (Speaker's compound) attaches BOTH.
  Reuse R9-1 ActivationWindow (no new grammar). C25: gate slot-disjoint attach; window slot only
  on ActivatedAbility (C20). b5a pattern `^Activate only as a sorcery\.$` (standalone tail — NOT
  matched as an ability, so no B5c double-match).
- R10-2 Chrome name-partition count: FAtomPred.NAME_PARTITION_COUNT_GE {inner_filter, count}
  (enum tail; _FATOM_RULES required==allowed=={inner_filter,count}, twin of CONTROLLER_COUNT_GE
  @~2932). C26 semantics: max size of an exact-name group over inner_filter-matched objects the
  owner controls ≥ count; executor grouping, not a vocabulary change. Docstring: Chrome Replicator.
- R10-3 Mangara attacked-relation: DeclareAttackersEvent (L1404) += trailing `attacked: Filter|None
  =None` (twin of DeclareBlockersEvent.blocked R6-4: _SPECS ("attacked","opt:filter") +
  _OMIT_IF_EMPTY DeclareAttackersEvent += "attacked"; filter narrows the ATTACKED object per
  attacker). + FAtomPred.ATTACK_AGAINST_COUNT_GE {count, inner_filter}: count the triggering
  event's subject attackers whose attacked object passes inner_filter ≥ count (reads declared-
  attackers list; LIFE_LEAD vocabulary-first precedent). Mangara inner_filter = FOr(CONTROLLER_IS
  YOU ... / planeswalker-you) — implementer composes from existing preds.
- R10-4 Herald damage-assignment policy: Verb.DAMAGE_ASSIGN_POLICY + roles {scope:True, filter:
  False} with closed _DAMAGE_ASSIGN_SCOPES=("AS_UNBLOCKED",) (MANA_POLICY twin — AtomArgs-carried,
  NO new _SPECS field; scope validated in AtomArgs like _MANA_POLICY_SCOPES). C27: "You may …"
  → the granted StaticAbility holds OptionalEffect(Atom(DAMAGE_ASSIGN_POLICY, scope=AS_UNBLOCKED))
  (may-vertex preserved C15); quote never serialized (C23). Batch builds via GRANT_ABILITY.

## 10-B batch (4 rows; bucket ownership = binding)

- B5a-activate-sorcery-gate (b5a): Steward gate tail → ActivatedAbility.timing=SORCERY (Steward
  s1 sacrifice already covered B5c — verify the gate finds the preceding ActivatedAbility across
  the sentence boundary; if s1 lands in a different ability grouping, report the attach order).
  PC-3: `^Activate only as a sorcery\.$` vs Speaker `^Activate only if …and only as a sorcery.`
  (disjoint anchors — Speaker has the `if` clause).
- B2a-etb-same-name-token (b2a): Chrome "When this creature enters, if you control two or more
  nonland, nontoken permanents with the same name as one another, create a 4/4 colorless Construct
  artifact creature token." — TriggeredAbility(ETB, Conditional(NAME_PARTITION_COUNT_GE(
  FAnd(FNot TYPE_EQ Land, FNot IS_TOKEN), 2), CREATE_TOKEN(4/4 colorless Construct artifact)).
  Prune the b2a UNCOVERED entry citing "no pairwise name-equality predicate" (@2569-2572).
- B2b-attackers-against-me-draw (b2b): Mangara "Whenever an opponent attacks with creatures, if
  two or more of those creatures are attacking you and/or planeswalkers you control, draw a card."
  — TriggeredAbility(DeclareAttackersEvent(attacked=FOr(...)), Conditional(
  ATTACK_AGAINST_COUNT_GE(2, …), DRAW(1))).
- B5c-herald-as-unblocked-grant (b5c): Garruk Savage Herald [−7] "...creatures you control gain
  \"…assign its combat damage as though it weren't blocked.\"" — LoyaltyActivated + GRANT_ABILITY
  (target=creatures-you-control, ability=StaticAbility(OptionalEffect(Atom(DAMAGE_ASSIGN_POLICY,
  scope=AS_UNBLOCKED))), duration=DurationEot). C23 literal; quote-closing-regex PITFALL (dump-
  exact, `\.` not `\."\.$` — the quote ends inside).

## PERMANENT-DEFER close-out (the remaining 5 queue shapes — recorded, defensible, expected-permanent)

| Shape | Reason | Phase-2/future unlock |
|---|---|---|
| Conspicuous Snoop "all activated abilities of that card" | grant set of a RUNTIME card-referent is not compile-time data; no node holds a dynamic ability-set | dynamic ability introspection + grant-by-reference (executor) |
| Liliana Waker "Each opponent who can't loses 3 life" | legality snapshot of a PRIOR mandatory action ("can't discard"); state shortcut provably mis-fires on exactly-1-card opponents (evaluates post-discard) | executor action-history |
| Sanctum of All "triggers an additional time" | no AbilityTriggeredEvent + trigger-duplication = trigger-pipeline semantics | executor trigger-stack |
| Transmogrify ×2 (reveal-until / the-rest) | Repeat is count-only (no predicate exit); no CardRevealedEvent; no set-complement referent for "the rest" | RepeatUntil control-flow (executor loop) |

These 5 are NOT forced: encoding any would default a decision or fake a rule (violates C15). The
honest ceiling with additive vocabulary is 301/305; the last 4 cards require Phase-2 executor
machinery and are the FIRST consumers when T6 (core/executor.py) lands.

## Predictions

10-A: suite 1629+N, goldens byte-identical (all new fields omit-when-None / enum-only / atom-arg),
PC-1/2 unchanged. 10-B: PC-1 297→301/305 (0.9868; Steward+Chrome+Mangara+Herald FULL — each card's
other sentences already covered), PC-2 630→635/639 (+5), queue 9→5 (the named permanent-defers
only), orphans stay 1 (DAMAGE_ASSIGN_POLICY consumed same round). PC-3 0 hard gate;
if any of the 4 double-matches or fails to assemble, WITHDRAW that row (queue shows it) — do not
force.
