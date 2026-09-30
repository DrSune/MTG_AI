# 13 — Round 16b: the COMBAT skeleton ships (BINDING /11 §16b)

Date: 2026-10-01. Plan: `11-round16-combat-plan.md`; predecessor: 12 (16a).
Scope delivered: COMBAT phase (declare asks → damage steps → end), the
DeclareAttackersEvent/CombatDamageEvent/TurnPhase-COMBAT binder feeds,
IS_ATTACKING + ATTACK_AGAINST_COUNT_GE, MANDATE_ATTACK dispatch +
"mandate" layers, the 16b legality section, combat wired into the game
loop, 6 validation packs, catalog repinned, 2 replays. No commits (working
tree); goldens/grammar/state.py untouched.

## Rulings and shapes (what the code now IS)

1. **Combat step** (`Executor.combat_step(seat)`): TURN_PHASE COMBAT
   marker → settle → declare window (`_op_seq` bumps = declare-group id) →
   per-creature **binary asks** `("ATTACK","DECLINE")` site
   `attack:<card>:<turn>`, Handle-sorted (C16), **mandated vocab narrows
   to `("ATTACK",)`** (C15 — the engine never offers an illegal word);
   whole-set re-check + mandate-inclusion check are **RuntimeError
   invariants** (asks mutate nothing, so a violation is an engine bug);
   tap commit (VIGILANCE skips, CR 702.53a) journalled as TAP_STATE rows
   BEFORE one DECLARE_ATTACKERS row per attacker (`data=(group,)`).
   Damage: FS/DS split (CR 702.7/8) — wave = ONE op boundary, per-dealer
   ctx (16a attribution), `KIND_COMBAT_DAMAGE` rows `data=(power,
   defender)`, 0-power never dealt (CR 120.7, no row); marks die only at
   cleanup. Ends: settle (SBA pass), attack record clears, phase
   `"SECOND_MAIN"` (executor-side string — the frozen Phase enum has no
   member; legality gates correctly stop first-main activations).
2. **No blockers v1** (16c): every attacker unblocked, damage to
   defending player; `combat_losses` counted apart from crashes in
   GameOutcome/report/table. R16-1: uninterrupted, SBA honesty at settles.
3. **Sickness** = journal read (`_controlled_since_turn_start`): last
   UPKEEP marker, battlefield-entry rows after it, no marker = whole log,
   no rows = ready. Haste bypasses; **tapped creatures attack** (tap is
   not a cost). `legal_attackers` = the ask enumeration;
   `mandated_attackers` = dispatched ledger ∪ live `"mandate"` layers.
4. **Binder** (CR 603.2): DeclareAttackers nodes dedup per
   (source, node, group) — Tide Skimmer/Mangara fire ONCE per declaration
   although every attacker emits its own row (pinned: 2 rows → 1 draw).
5. **layers**: `_new_static` SPLITS a StaticAbility Seq — MANDATE atoms
   become `"mandate"` layers (selector = the atom's cards role), rest
   stays a generic static (Furor = both halves; leave = both die, pinned).

## Discoveries that corrected the plan (all verified against compiled IR)

- **CONTROLLER_IS could not see player handles** (quantity.py returned
  False for non-cards) — Mangara's `attacked=FOr(CONTROLLER_IS YOU …)`
  could NEVER match a player attack. Fixed: a player handle answers for
  itself via the selector coordinate oracle. Without this the 16b
  flagship condition was dead code. (Doc /13's R10-3 reading, unblocked.)
- **The Whale's mandate rides the TokenSpec, not the trigger**: compiled
  ETB = `EachPlayer→CREATE_TOKEN` only; "attack if able"/"can't block"
  are the PIRATE's own statics, and token handles never get binder
  records (pre-existing `_lifecycle` gap). So the dispatch handler has
  **no M21 carrier** — the gate counts carriers via `walk` (which sees
  nested token specs), hence Furor+Whale+Pirate still flip 288→291 with
  MANDATE in V2. Token-record registration = 16c gate #1.
- **The compiler drops Falconer Adept's "that's tapped and attacking"**
  (both TokenSpec flags `None`; only Basri Ket's Soldier carries
  `enters_attacking=True` — the R8-4 exemplar). Executor honors the flag
  (join_attack, CR 508.1i); the drop is a compiler-fidelity item, pinned
  as-is in test + pack (bird enters plain, deals no phantom damage).
- **QProp THIS_WAY_COUNT** (Siege Striker's "+1/+1 per creature tapped
  this way") was the next headwall the moment its attack trigger became
  bindable: implemented as the per-resolution tap register (fresh-ctx
  discipline; skipped may-tap → magnitude 0, CR-correct with the answer).
- Historian of Zhalfir compiles **3/3** with an attack trigger — pack
  expectation set from the IR, not from printed memory.

## Numbers (commands in NUMBERS.md)

Core **2054** passed (+20 `test_executor_combat.py`, 3 amended pins);
packs **9/9**; engine30 **0 crashes**, 28/30, 2 games end BY COMBAT
(seeds 19, 24 — replays s19/s24); all10 crash set unchanged (GAIN_CONTROL
sole survivor); catalog: 10/10 diverge at the first COMBAT boundary, ALL
new outcomes clean → repin 6343 entries, compare 0/10; determinism
byte-identical; PC-6/PC-8 unchanged documented FAILs (PC-8 stayed
0.3213 — its combat-legality fraction waits for 16c blockers); PC-7
291/305, 41 verbs. V2 40→41, engine gate 288→291 EXACT flip set =
Furor, Pursued Whale, Pirate (deckable 271 unchanged).

## 16c queue (this round's residue, named)

DeclareBlockersEvent + BecomesBlockedEvent (the raise-list half, incl.
Elder Gargaroth); Harbinger's DamageDealt source+combat scope; token-
record binder registration (unlocks Pirate statics + hoisted mandates);
planeswalker attack assignment + trample + damage-order (need blockers);
Falconer enters-tapped/attacking compiler fidelity.
