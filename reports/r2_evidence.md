# R2 EVIDENCE — F4 damage-event fold census + F1 direction-residual re-audit

Date: 2026-10-20. READ-ONLY round vs repo (writes: /tmp/opencode only).
Census: `.venv/bin/python /tmp/opencode/mk_r2_census.py` → `/tmp/opencode/r2_census.json`
Byte-delta: `.venv/bin/python /tmp/opencode/mk_sortdelta_r2.py` → `/tmp/opencode/r2_sortdelta.json`
Both reuse the committed compile pass (ingest_pool + build_full_registry +
_compile_pool_tolerant; walk() NOT used per PITFALLS). M21 305 compiled / ZNR 281 (+1 gap) — census denominators match /126.

---

## PART A — F4 DAMAGE-EVENT FOLD CENSUS: **REAL FOLDABLE DIVERGENCE — CONFIRMED**

**Population (compiled IR, both pools): 13 damage-event nodes on 13 cards.**
- CombatDamageEvent (CDE): M21 2 (Jeskai Elder, Feline Sovereign) + ZNR 1
  (Nimble Trapfinder, inside the party-granted embedded TriggeredAbility).
- DamageDealtEvent (DDE): M21 10, ZNR 0. Ledger "6×" understates the mixed
  surface; the truth is 3 CDE + 10 DDE across two classes.

Every node carries the same 5-key FAtom serialization (pred as
`{"name":…,"tag":"FAtomPred"}`, who as `{"name":…,"tag":"ControllerRef"}`);
full per-node bytes in r2_census.json partA.nodes. Controller-direction inside
damage events is ONLY ever FAtom(CONTROLLER_IS) (e.g. Pyreling/Incinerator
`source:CONTROLLER_IS YOU`, PackLeader/Feline filter parts) — no second axis.

### The fold case — two concrete divergence pairs (wording × bytes)

**Pair 1 (convergence PROVEN, byte-exact):**
- Jeskai Elder (M21) & Nimble Trapfinder (ZNR):
  `CDE{filter: FAtom(IS_SOURCE)}` — wording "Whenever this creature deals
  combat damage to a player".
- Garruk's Harbinger (M21):
  `DDE{amount:QUnbounded, combat:true, filter:FAnd(()), source:FAtom(IS_SOURCE)}`
  — wording "Whenever this creature deals combat damage to a player or
  planeswalker".
  Same event semantics (dealer=IS_SOURCE × combat-damage specialization) land
  in TWO DIFFERENT ATOMS purely by wording. Post-fold, Jeskai's event bytes ==
  Harbinger's bytes VERBATIM (`convergence.byte_equal: true` in
  r2_sortdelta.json) — the F4 claim demonstrated end-to-end.

**Pair 2 (dealer-restricted combat trigger, split across classes):**
- Feline Sovereign (M21):
  `CDE{filter: FAnd[CONTROLLER_IS YOU, SUBTYPE_EQ Cat, …]}` — "one or more
  Cats you control deal combat damage to a player".
- Subira, Tulzidi Caravanner (M21):
  `DDE{amount:QUnbounded, combat:true, filter:FAnd(()), source:FAnd[CONTROLLER_IS YOU, creature, PT≤2]}`
  — "a creature you control with power 2 or less deals combat damage to a
  player". Identical {dealer-filter × combat} shape, different class.

Wording-bucket census (r2_census.json): the "combat active-deal" bucket holds
7 nodes / 6 distinct byte forms spanning BOTH classes.

### Why DDE is the fold target (not CDE) — executor evidence
- CDE has NO recipient axis: the KIND_COMBAT_DAMAGE lane
  (binding.py:875-881) evaluates the dealer filter ONLY. The Jeskai Elder
  template ADMITS the loss: "Lossy: 'to a player' is dropped —
  CombatDamageEvent.filter … exposes no recipient field (doc-05 row #2)"
  (templates_b2b.py:1703-1709).
- DDE carries all four axes (amount / filter=RECIPIENT / source=dealer /
  combat) and the 16c lane `_match_damage` (binding.py:1088-1119) fully
  consumes them (DAMAGE row carries dealer as `cause` + combat flag).
- The fold's canonical recipient is the grammar's OWN universal marker:
  `_is_universal = FAnd(())` (binding.py:177), already emitted by
  Harbinger/Subira/Fiary-Emancipation compiled trees (5 DDEs with
  combat=ABSENT, 3 with combat=true, 2 with combat=false in M21).

### NOT divergence (truthful negatives)
- Passive "is dealt damage" reads (Brash Taunter, Sporeweb Weaver:
  DDE amount=QProp(event,AMOUNT,FIRST), filter=IS_SOURCE) — recipient-side,
  no CDE analogue, single encoding.
- Noncombat scoped pair Chandra's Pyreling / Chandra's Incinerator compile to
  the SAME DDE bytes (combat=False, filter=OPPONENT_OF YOU,
  source=CONTROLLER_IS YOU) — n=2, 1 byte form (r2_census wording bucket
  confirms); Hooded Blightfang adds the planeswalker-recipient read via the
  filter lane (SUPERTYPE_EQ Planeswalker) — DDE doing its job.
- Replacement shapes (Nine Lives, Fiery Emancipation, Pack Leader) are
  recipient/anti-scope reads — DDE-only, already canonical.

---

## PART B — F1 DIRECTION RESIDUAL RE-AUDIT: **ZERO-RESIDUAL** (live encodings)

Independent re-audit (not trusting /65's claim):
1. **Event direction = ONE encoding.** All 6 actor-bearing event classes
   (Cast/TurnPhase/CardDrawn/LifeGained/Sacrifice/LoyaltyActivated) use
   `actor: Filter` fed by FAtom(CONTROLLER_IS) exclusively: M21 43/43
   non-null actors CONTROLLER_IS (41 YOU / 2 OPPONENT), ZNR 16/16; the one
   `TurnPhaseEvent:null` is "any actor" = absence, not a rival encoding.
   Zero OTHER-shaped actor found by census (r2_census.json partB.actor_field).
2. **CONTROLLER_IS is the sole in-filter direction predicate.** Compiled host
   census M21: FAnd.children 117, event.actor 43, FNot.inner 4,
   DamageDealtEvent.source 3, FOr.children 2, DamageDealtEvent.filter 1,
   Selector.filter 2, AtomArgs.pairs 2; ZNR: FAnd.children 86 + actor 16.
   No competing direction pred anywhere.
3. **The one ControllerRef-carrying EVENT field is dead.** StepEvent.controller
   exists in the IR, but compiled population is **0/0** across 586 cards and
   the executor declares StepEvent in `_UNSUPPORTED_EVENTS` — "the executor …
   emits TapState/phase events, not StepEvents" (binding.py:159-162; 3
   non-test consuming lines: import + table + comment). Dormant field, not a
   surviving duplicate. Optional advisory: dead-class cleanup, NOT a merge.
4. **Zone.controller is a DISTINCT axis, verified.** Every BATTLEFIELD+
   {YOU|OPPONENT} zone in the corpus is a movement endpoint: M21 to_zone 67 /
   cost `pairs` 12 / from_zone 2; ZNR to_zone 53 — and **ZERO Selector menu
   filters key on battlefield controller direction** (menus use
   BATTLEFIELD/ANY + CONTROLLER_IS, e.g. sacrifice-a-creature-you-control).
   Zone-ownership/destination direction ≠ permanent-control direction. The
   ControllerRef VALUE vocabulary (YOU/OPPONENT/TARGET_PLAYER/OWNER/ANY) is
   shared VALUES of one encoding family (FAtom `who`, Zone `controller`),
   not two encodings.
5. **QProp.referent** = quantity-reference axis ("event"/"source" refs, e.g.
   QProp(event,AMOUNT)); **EachPlayer.ref** = player-enumeration axis. Neither
   carries you/opponent control direction. F1 row's distinctness claim holds.
6. Consumer counts (grep): CONTROLLER_IS — 148 compiler non-test lines,
   27 executor non-test lines, 154 lines across 38 test files.
   StepEvent — 3 non-test lines. F1 = **NO-OP with evidence**.

---

## PART C — BYTE-DELTA PRE-REGISTRATION (executed)

Rule measured: `CDE{F} → DDE(amount=QUnbounded, filter=FAnd(()), source=F,
combat=True)`. MEASURED (r2_sortdelta.json):
- Changed set EXACT: M21 **2/305** {Feline Sovereign, Jeskai Elder} + ZNR
  **1/281** {Nimble Trapfinder}; 3 folds fired, 0 exceptions.
- Goldens flagged: **2** M21 files (of 305) — exact oids in JSON.
- Idempotence: PASS (fold∘fold = fold, zero second-pass firings).
- Content: PASS — dealer-filter subtree moves VERBATIM (FAtoms keyed by full
  bytes); the only multiset gains are the declared canonical shell
  {&lt;DamageDealtEvent&gt;,&lt;QUnbounded&gt;,&lt;FAnd&gt;} per fold; zero losses.
- Convergence: post-fold Jeskai event bytes == untouched Harbinger bytes
  byte-equal (true).

---

## VERDICT + RECOMMENDATION

**R2 = FOLD WAVE (confirmed divergence), small and closed**: 3 IR nodes /
3 cards + class deletion. F1 rides as no-op-with-evidence (zero residual).

**Engine-lane DEFER REQUIRED — R2 is NOT pure compiler/IR.** Named items:
1. **Feed-parity verification**: every COMBAT_DAMAGE journal row (dealer-keyed,
   group-deduped, binding.py:875 lane, events.py feeds) must have an
   equivalent KIND_DAMAGE row (dealer=`cause`, `is_combat` flag) so the folded
   DDE fires identically — executor law, EXECUTE-verified, not paper.
2. **Lane deletion**: binding.py CDE import/subscriber (:58,:875),
   replacements.py CDE matcher consumption (:54,:105), events.py feed; then
   ability_tree class removal (7 IR sites) + templates_b2b.py:1709/:1956 and
   templates_b8.py:625 emission redirects + 2 M21 golden re-baselines + 5 test
   files.
3. **DEFER SEPARATELY (rules change, not the fold)**: recipient fidelity —
   "to a player" is unencoded on all three CDE cards TODAY (Jeskai template
   self-declares LOSSY); the byte-fold PRESERVES today's behavior via the
   universal FAnd(()); making it faithful is an engine-visible trigger-timing
   fix on its own gate (likely the D9 empty-FAnd fold unification must be
   settled first — three fold sites disagree on FAnd(()) per D9).
