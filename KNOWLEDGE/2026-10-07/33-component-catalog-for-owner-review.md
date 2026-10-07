# 33 — COMPONENT CATALOG for owner review (2026-10-07; counts = goldens containing the atom)

## Effect operations (Verb enum, 49) — the {what-happens} axis
HIGH volume (>=25 cards): DRAW 49, MODIFY_PT 50 ("give a creature +X/+Y" — YOUR example,
present), ADD_MANA 34, CHOOSE* 115(census artifact: matches SelectorMode strings too),
DEAL_DAMAGE 31, GAIN_LIFE 31 (healing), DESTROY 13/EXILE 19 (with MOVE_ZONE 29, SEARCH 17,
SHUFFLE 17, DISCARD 17), PUT_COUNTER 28, CREATE_TOKEN 24, GRANT_ABILITY 38, END_TURN 13,
PREVENT_EFFECT 14, SCRY 12, REVEAL 14.
MID (4-12): LOSE_LIFE 12, TAP 8, UNTAP 6, CAST 6, COUNTER_SPELL 5, REMOVE_COUNTER 1,
SET_PT 4, SACRIFICE 4, LOOK_AT 4, MILL 3, PAY 3, CHOOSE_NAME 2, ATTACH 2, GAIN_CONTROL 2,
COPY 2, FIGHT 2, LOSE_ABILITY 2, MANDATE_ATTACK 3, GRANT_TYPE 3, EXTRA_TURN 1, ADD_LAND_PLAY 1.
ZERO: PHASE_IN (engine boilerplate atom, no card).

## YOUR owner-list mapping
damage=DEAL_DAMAGE | healing=GAIN_LIFE | draw=DRAW | shuffle=SHUFFLE | "put at place X in
deck"=MOVE_ZONE(+position param) | graveyard = a ZoneKind (zone axis), not a verb — correct
separation | "give creature +X/+Y" = MODIFY_PT (largest verb) + PUT_COUNTER | OVERDRAW: does
not exist in MTG — drawing from empty library = you LOSE (LOSE_GAME 1 card + engine STALL
rule); the nearest real concept is "draw X when you could not" being un-card-legal.

## {when} events (17) — see /32 algebra: ZoneChange 70, TurnPhase 20, Attackers 13, Dies 11,
Damage 8, Cast 8, Drawn 7 MID; floor<=2: CombatDamage, Blockers, LifeGained, Targeting,
BecomesBlocked, Sacrifice, Loyalty; StepEvent dead. Direction axis split 7-field/10-filter
(E1 merge). Guard = orthogonal condition, CLEAN.

## Keywords (23) — modifiers, 15/23 multi-consumer: FLYING 40, SCRY 12(VERB TOO - double
encoding), VIGILANCE 11, LIFELINK 11, TRAMPLE 13, PROTECTION 6, HEXPROOF 6 (ZERO enforcement
- /32 E8 bug), PROWESS 7, FLASH 7, REACH 6, DEATHTOUCH 5, INDESTRUCTIBLE 7, MILL 3(VERB TOO),
HASTE 6, DEFENDER 4, FIGHT 2(VERB TOO), EQUIP 2, MENACE 2, FIRST/DOUBLE_STRIKE 4/2,
TREASURE 1 (zero consumer), BATTALION 1, ENCHANT 10.

## Selection & menu machinery (SelectorMode 6 + Quantity axes) — /30.
## Ask channel (17 surfaces, algebra in /30): may/target/one_of/scry/order/attack/block/...

## Preliminary orchestrator observations (pre-adversarial)
1. DOUBLE ENCODINGS (owner's "coded differently, conceptually same"): MILL, SCRY, FIGHT exist
   as BOTH Verb and Keyword. 2. COMPOSITE CANDIDATES: MILL is conceptually MOVE_ZONE(
   library->graveyard) — is it a distinct atom or derived? FIGHT = damage+targeting bundle.
3. Too-rare atoms to be learnable (owner volume law): REMOVE_COUNTER 1, EXTRA_TURN 1,
   ADD_LAND_PLAY 1, LOSE_GAME 1, PHASE_IN 0, ATTACH 2, COPY 2, GAIN_CONTROL 2.
4. CHOOSE-115 is a grep artifact (mode strings) — real node-Choose = 27 (/30).
5. MISSING candidates for later sets (not in M21): proliferate, kick/cast-cost modes,
   daybound, venture, experience — first-20-sets will drive rewrites per §8/§9.
