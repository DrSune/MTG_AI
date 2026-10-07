# T4 — Blindness / Phantom audit (2026-10-07, P0)

Scope per `docs/T4_SPEC.md` §7 law and /35 brief: every atom gets
`atom | static form today | dynamic presentation today | verdict | T4 action`.
Volumes = goldens (/33) / fired asks v2 (/30 census). Decisive code refs spot-checked
today. Verdicts: **BLIND** (decision exists, encoding/ask hides an axis) ·
**PHANTOM** (encoding/ask presents a decision the engine doesn't need) · **CLEAN**.

## A. Verbs with a decision axis (16 of 49; the 33 pure-effect verbs are state deltas
whose only menu is the generic TARGET-designate wrapper audited as surface #target below)

| atom | static today | dynamic today | verdict | T4 action |
|---|---|---|---|---|
| CHOOSE-atom (115* grep-artifact; real selector-CHOOSE 170 g) | `CHOOSE{count,target:sel(CHOOSE)}` | 0 fired asks on silent-CHOOSE surfaces | **BLIND** | MERGE into PICK(k over legal-set) → ask channel (/30 ledger) |
| CHOOSE_NAME (2 g) | `CHOOSE_NAME{name_filter?}` | `name:` 2 asks | BLIND(minor) | name-vocab decision (SPEC §2.4) |
| SCRY (12 g / 29 asks) | `SCRY{controller,count}` | `scry:` top/bottom | **BLIND** within-group order pinned (verbs.py:1008-1018) | add `order:ASK` + order sub-ask (P1) |
| SEARCH (17 g) | `SEARCH{cards:sel(zone+filter),destination}` | ONE_OF 4 g/9 asks ASKING; CHOOSE-mode picks SILENT (Cultivate 2of2) | **BLIND subset** | flip QConst(k>1) search to k-of-n ask path (/31 machinery exists; T3 prereq-2 open) |
| LOOK_AT (4 g) | `LOOK_AT{controller,count}` | never asked | CLEAN (observation, no menu) | keep |
| PAY (3 g) | `PAY{cost}` | `pay:` 0 evals | BLIND(minor, vol floor) | merge into `whether`-family (/30) |
| ADD_MANA (34 g) | `ADD_MANA{controller,amount,color?}` | `mana:` 10 asks, **amount never askable**, colour fused | **BLIND** | NUMBER menu ask (SPEC §3) |
| CAST (6 g) | `CAST{source,cost?}` | stack/mana surfaces | CLEAN-ish | watch Snoop derived-menu (ledger L-21) |
| TAP / UNTAP (8/6 g) | `TAP{target,duration?}` | folded in silent CHOOSE | BLIND subset | inherits PICK merge |
| SACRIFICE (4 g / 6 asks) | `SACRIFICE{target}` | k-loop legality.py:1326-1338 | CLEAN minus NONE-stop exact-count only | keep; add fx_per_choice if printed |
| DISCARD (17 g) | `DISCARD{controller,cards}` (menu=hand filter often empty) | silent CHOOSE bucket | **BLIND** | PICK merge via MOVE wrapper (§6) |
| MANDATE_ATTACK/BLOCK (3 g) | `MANDATE_*{cards}` | see attack/block surfaces | see surfaces | POLICY class (SPEC §1) |
| COPY (2 g) | `COPY{source}` | new-targets UNCOVERED (b4) | COVERAGE (ledger L-13) | P2 |
| FIGHT (2 g) | `FIGHT{target}` | never asked | vol floor | decomposition candidate |
| FLIP_COIN / END_TURN (13 g) / LOSE_GAME (1 g) / EXTRA_TURN (1 g) / GET_EMBLEM / SHUFFLE (17 g) / END_TURN | scalar/no-menu atoms | never (engine resolves) | CLEAN (no decision exists) | keep |
| PHASE_IN (0 g) | boilerplate atom, no card | never | **PHANTOM** | keep engine-internal, never emit from compiler |

## B. Selector modes & resolvers

| mode | static | dynamic | verdict | action |
|---|---|---|---|---|
| TARGET (115 g / 34 asks) | selector zone+filter+count | `target:` k-loop binding.py:1393 (complete k-of-n, NONE-stop) | **CLEAN skeleton** | canonical PICK |
| ONE_OF (4 g / 9 asks) | sel ONE_OF count | `one_of:s:i of k` (k-of-n shipped /31) | CLEAN | extend to search-pick k>1 |
| CHOOSE | as A/CHOOSE | 0 asks | BLIND | merge→PICK |
| ALL | zero-op | never | CLEAN | keep |
| REST | auto-subtract | never | CLEAN | keep |
| RANDOM | no decision | never | CLEAN | keep |

## C. {when} events (17; volumes /33: ZoneChange 70, TurnPhase 20, Attackers 13, Dies 11,
Damage 8, Cast 8, Drawn 7; ≤2: CombatDamage, Blockers, LifeGained, Targeting,
BecomesBlocked, Sacrifice, Loyalty)

| event | own slots (extracted today) | verdict | action |
|---|---|---|---|
| DeclareAttackersEvent | filter, attacked | BLIND: no controller field; or-composed (Gargaroth) duplicated | event {kind-union} + E1 direction (P2) |
| DeclareBlockersEvent | filter, subject, blocked | same | same |
| LifeGainedEvent | controller only | **BLIND: no amount axis** (life-total triggers unaskable) | +amount slot (P2) |
| DamageDealtEvent | amount, filter, source, combat | CLEANest (has amount+source) | canonical for direction merge |
| CastSpellEvent | filter, controller, from_zone, ordinal, from_zone_not | CLEAN | — |
| ZoneChangeEvent | from_zone, to_zone, subject | CLEAN | — |
| TurnPhaseEvent | phase, controller | CLEAN | — |
| CardDrawnEvent | controller, ordinal | CLEAN | — |
| CounterPlacedEvent | counter_kind, filter, count | CLEAN | — |
| CreatureDiesEvent / CombatDamageEvent / BecomesBlockedEvent / TargetingEvent / LoyaltyActivatedEvent / SacrificeEvent | filter (+controller) | direction split: 7 events w/ controller field vs 10 via CONTROLLER_IS-in-filter | **E1 merge: ONE direction axis** (ledger L-8) |
| StepEvent | phase, step, controller | **PHANTOM — dead** (0 consumers) | delete at T4 (P2) |
| PlayLandEvent | **does not exist** | landfall un-encodable | future-set exposure (ledger L-7) |

## D. Keywords (23; volumes = goldens /33; enforcement: EXECUTED / DECL / ZERO)

FLYING 40 EXECUTED(block legality) · MODIFY-family n/a · SCRY 12 EXECUTED but **Verb+Keyword
double encoding** · VIGILANCE 11 EXEC · LIFELINK 11 EXEC · TRAMPLE 13 EXEC (trample ask 0
evals — distribution decision exists yet never exercised: BLIND-eval) · PROWESS 7 DECL ·
FLASH 7 EXEC-ish · REACH 6 EXEC · HEXPROOF 6 **ZERO enforcement** (E8 latent bug) ·
PROTECTION 6 DECL · MILL 3 double encoding · DEFENDER 4 EXEC · HASTE 6 EXEC · FIGHT 2
double encoding · DEATHTOUCH 5 EXEC · FIRST/DOUBLE_STRIKE 4/2 EXEC · EQUIP 2 **duplicated**
with ATTACH activated ability (Scythe golden verified) · INDESTRUCTIBLE 7 EXEC · TREASURE 1
zero consumer · BATTALION 1 · MENACE 2 EXEC · ENCHANT 10.
Actions: HEXPROOF executor rule P1 (pure enforcement, no grammar change); MILL/SCRY/FIGHT
keyword→verb canonical-form merge ledger L-20; EQUIP = derived-from-ATTACH (phantom remove).

## E. Quantity tags (13)

QConst/QAtMost/QAtLeast/QUnbounded unified in ONE `count_semantics` helper (/36) = CLEAN.
QX (askable X, X_VALUE lane) CLEAN. QProp{field,referent,agg} CLEAN (THAT_MANY/COUNTER_COUNT
verified). QBin/QBinOp CLEAN (Scythe derived PT). QAgg/QCount/QDistinctColorCount/QPropField
internal — CLEAN. Residual: "zero" spelled 4 ways (NONE token / skip / empty option-set /
no-ask) — one encoding in P1 (ledger L-21a).

## F. Ask surfaces (17 SITE_KINDS, bc_data.py; census goldens/asks /30)

| site | vol | verdict | action |
|---|---|---|---|
| may 42/42 | CLEAN (every may asks) | keep `whether` skeleton |
| target 115/34 | CLEAN k-of-n | canonical |
| one_of 4/9 | CLEAN (+i of k /31) | extend to search-pick k>1 |
| choose (node) 27/30 | CLEAN except Sublime min-1 loss | pick-k-of-branches qty fix |
| scry 12/29 | BLIND order | order sub-ask P1 |
| order 0 evals | reinvents vocab str(i) | merge into target-k-loop (/30) |
| attack 13/2 | **BLIND: N binars, no set declaration** | attacker-set PICK P1 |
| block 8/0 | eval floor | same shape as attack (CR 508/509 keep-separate) |
| mana 10 | **BLIND amount** | NUMBER lane P1 |
| name 2 | vol floor | open name-vocab |
| cw 0 evals / counter 0 evals | SAME atom, two impls (stack.py:677 vs 824) | MERGE one window atom |
| pay 0 evals | vol floor | whether-family |
| trample 0 evals | decision unexercised | pack seeding item |
| policy / quantity / draw / roll | 0 evals / engine lanes | keep, monitor |
| sacrifice 6 (via legality) | CLEAN | keep |

## Totals (auditable counts in this table set)
BLIND rows: 10 (silent-PICK family, scry order, mana amount, attack set, discard menu,
search-k-pick, LifeGained amount, Gargaroth union, trample-unexercised, zero-spelling) ·
PHANTOM rows: 4 (StepEvent, PHASE_IN compiler-side, EQUIP double, cw/counter twin) ·
everything else CLEAN or volume-floored.
