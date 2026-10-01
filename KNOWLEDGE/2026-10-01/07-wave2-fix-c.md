# 07 — Wave 2 fix-batch 19c (cast declaration lane; engine editable)

Scope: the nine fix-B DEFER-19c suspects (duress, mind_rot, necromentia,
hunters_edge, experimental_overload, peer_into_the_abyss, return_to_nature,
rookie_mistake, wildwood_scourge) + verify capture_sphere's engine side after
fix-B's harness-side enchant-op rebuild. Every fix is flag-not-degrade,
seed/deterministic-order clean, and pinned by
`MTG_bot/core/test_executor_r19c.py` (16 tests). No state.py, no compiler,
no golden edits; nothing committed.

## The five fixes

1. **Positional multi-slot designation** (`stack.py`). A spell with TWO
   TARGET selectors (Hunters' Edge, Return to Nature, Rookie Mistake) used to
   collapse both atoms into one shared role and raise
   `count_below_min:0<2`-style shape errors. `cast()` now builds a POSITIONAL
   ask — one candidate list per TARGET atom — and stores the answer per atom
   in a repr-keyed `ExecCtx.slot_designations` shadow next to the legacy flat
   `designated_targets` (single-slot lanes read the flat field, byte-
   unchanged). `_plan_cast_designation` returns
   `(designated_targets, slot_designations, remaining_decisions, modes)`;
   atoms re-evaluate under their OWN designation (split response: the two
   `DAMAGE 1` atoms each burn their designated creature, verified 1/2-split
   in r19c). Under-supply stays loud with the count shape. Trigger
   designation (18b) is untouched — this is the cast lane only.

2. **Self-clauses + forced auto-designation** (`stack.py`).
   Experimental Overload's `EXILE ... TARGET (self)` had an EMPTY candidate
   population (the source isn't a legal self-target under the 12c query), so
   the cast plan now marks an IS_SOURCE-source selector `auto_skip`
   (`_validate_positional(skip=...)`) — the atom resolves via its own
   `referent: self`, never through designation (CR 115.4: "each/all/targets"
   with no legal targets does nothing extra; here the anaphora is the whole
   clause). Symmetrically, a population of EXACTLY ONE legal candidate is
   force-designated without an ask (lone-opponent TARGET_PLAYER — Duress/
   Mind Rot/Necromentia's discard-half; one-candidate TARGET) — CR 115.4's
   forced auto-fill, the trigger lane's §1.4 rule lifted into the cast plan.
   A REAL choice stays loud (`count_below_min`) — never guessed. Designation
   is validated BEFORE the stack push and CR 601.2c-rechecked at resolution.

3. **Mode declaration + Choose aliases** (`stack.py`, `verbs.py`). A spell
   with modes (Rookie Mistake) declares its mode at CAST time (CR 601.2b):
   the answer rides `ExecCtx.prechosen_modes` and resolution POPS it — the
   mode is never re-billed (witness-pinned: second visit raises if the pop
   didn't happen; undeclared mode → loud "must declare its mode").
   `_v_choose` grew an ADDITIVE handle-alias vocab (index tokens `'0','1'`
   still answer byte-identically; `card:N` tokens are appended), so a pack
   can name its choice by handle; digest unchanged, nonsense answers stay
   loud.

4. **Decision-lane fall-through** (`quantity.py:take_decision`). A stream
   answer whose vocab word is not in the REQUESTED vocab used to raise after
   the pool word was already consumed. Now a non-matching word is NOT
   consumed — the decision falls through to the stream/provider lanes and the
   original raise shape is preserved (a misrouted answer can no longer eat a
   queued decision). This is what lets one may-offer ("fire","skip") and one
   choose-ask share a DecisionStream keyed on (vocab, what).

5. **Enchant op fires triggers** (`tools/run_scenarios.py`). After the
   journalled aura re-entry the runner now calls `fire_triggers()` — Capture
   Sphere's ETB finally sees its host (fix-B's `attach_aura` rebuild was
   half the story; the trigger never fired without the explicit sweep).
   Pack prov for its "may discard" goes through the may-offer vocab
   (`"fire"`), not the retired `vocab[0]` index convention.

## Catalog attribution (why seed 8 diverged, then 0)

Pre-repin `compare` (pool=engine, seeds=10, deck_pairs_seed=1409, turns=60):
seed 8, entry 159 — old `ZONE_CHANGE card:81|card:15|DISCARD` vs new
`card:15 CAST`, downstream clock shift, both games end "turn cap 60 reached
(no loser)". Attribution: `RandomPolicy.choose` (games.py:383-403) answers
UNIFORMLY over the requested vocab; fix #3's additive `card:N` aliases change
which answer the SAME rng draw maps to — policy behavior change, not an
engine regression (same reconcile-then-repin discipline as fix-A/fix-B).
Repinned: 10 games / **6144 entries** → compare **0/10 diverge**.

## Dispositions (9 deferred + capture_sphere)

- **FIXED + promoted (8)**: duress, mind_rot, necromentia, hunters_edge,
  experimental_overload, return_to_nature, rookie_mistake, capture_sphere →
  `tools/scenarios/`. Promoted packs had `status: suspect` + `finding`
  STRIPPED per this batch's mandate (plain `mv`, not `git mv` — no commits).
  ⚠ Convention mismatch to settle next batch: fix-A stripped, fix-B kept
  verbatim, 19c stripped.
- **STOP — compiler campaign (2, stay in suspects)**. Root causes written
  into the packs' findings; the executor side is proven alive by r19c
  analogues:
  - **peer_into_the_abyss**: the M21 golden for "target opponent draws two
    cards and loses 2 life" contains ZERO LOSE_LIFE atoms — the spell
    compiled to DRAW-only, so the pack's life delta is unsatisfiable at IR
    level. The engine half works (lone-opponent TARGET_PLAYER auto-
    designation + DRAW resolve; r19c pins the exact shape).
  - **wildwood_scourge**: an X-cost permanent's record has 0 SpellAbility
    nodes (no cast lane at all) and enters-with-X compiled as a
    TriggeredAbility reading QX — the `QX has no declared X` raise is
    CORRECT engine behavior. Needs SpellAbility synthesis + X declaration
    on the compile side.
- **Out of scope for 19c (3, stay)**: tampering_no_block and transmogrify
  (fix-B STOPs, IR-shape gaps unchanged); secure_the_scene (fix-B's
  PASS-as-STOP disposition preserved — and it still PASSES, hence the 1/5).

## Gates (2026-10-01, HEAD 8b4b6b9 + this batch, re-verified at doc time)

- scenarios: **148/148** (`tools/run_scenarios.py`; 140 + 8 promotions)
- suspects dir: **1/5 fail-only** (`--dir tools/audit/suspects` — secure_the_
  scene PASS; peer/wildwood STOPped above; tampering `damage marks expected
  {}, got {'card:2': 1}` + `blocked[atk] expected [], got ['wall']` and
  transmogrify `battlefield_pt[Library 5] expected 1, got 0` stay fix-B STOPs)
- unit: **2168 passed + 4 subtests, 0 failed** (`pytest MTG_bot/core -q`) —
  2152 baseline + 16 new in `test_executor_r19c.py`; ONE AMENDED pin in
  `test_executor_stack.py` (multi-target ask now asserts the count-shape
  ValueError instead of the old silent path).
- PC gate: PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 — EXACT vs T5/fix-A/
  fix-B (compiler frozen); PC-5 0.242ms; PC-6 (1 orphan / 0.0934) and PC-8
  0.3213 unchanged baseline FAILs; engine gate **297/305, V2 45 verbs
  UNCHANGED**.
- traces: seed-8 diff attributed → repin **6144 entries/10 games** →
  compare **0/10**.
- pyright on the touched scope: **0 new errors**; the **6 pre-existing**
  Counter-inference errors in `tools/run_scenarios.py` (~:426/:528/:532/:537)
  verified pre-existing at HEAD.
- ruff **Δ0** vs HEAD across all six touched/added files: the two lint hits
  this batch temporarily introduced (`stack.py` UP037, r19c I001) were
  auto-fixed and re-greened; quantity.py UP007 + run_scenarios.py BLE001 are
  pre-existing at HEAD.

Test-harness facts learned (authoring r19c): `card_id()` has NO `types`
parameter (TYPE_EQ is a data-only type_line word match); `StackCase` has no
`self.zone()` (use `world.players[seat].zone(ZONE_HAND).entries`); the p0
baseline hand CONTAINS the synthesized spell (assert `hand0_before - 1`);
a may-offer's TARGET selectors still count as cast slots, so packs cast with
`targets=()` and let the forced-auto-fill lane take both slots.
