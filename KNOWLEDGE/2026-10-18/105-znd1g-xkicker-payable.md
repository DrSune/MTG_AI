# 105 — ZND-1g: X-valued kicker PAYABLE (cost lane delivered; Thieving Skydiver verdict stays honestly flipped-NO — effect gap registered)

Date: 2026-10-18 (engine lane, follows /100 ZND-1e + /103 ZND-1f). Grammar and
compiler FROZEN for this wave: zero changes to compiler.py, templates_*,
coverage.py (sibling ZND-2 live on the compiler surface). M21 PC-4 0 diffs.

## The resolving card (the spec, verbatim from ingested ZNR record)
> "Kicker {X}. X can't be 0. (You may pay an additional {X} as you cast this spell.)"

Printed cost {1}{U} carries NO X → the kicker's {X} is the spell's ONLY X.
CR 107.4a: ONE declared value per object, feeding the cost and the (uncompiled)
ETB "mana value X or less" filter alike. **The cast's `x` IS the kicker's
announcement — no separate kicker-X declaration slot.** (A card with BOTH
spell-X and kicker-X would share the same single announcement under the same
CR; the engine's single `x` parameter is already that law.)

## What landed (executor cost lane only)
1. **`legality.spell_castable`**: the `cast:kicker_with_x_unsupported` refusal
   is GONE — a kicker cost containing {X} joins the CR 601.2f fold exactly like
   a non-X kicker; the cast's `x` binds {X} (zero-floor `x = 0` default already
   covered by the standing X-lane code path).
2. **`stack.cast` X landing**: the 14c zero-floor derivation is kicker-aware —
   a kicked cast whose KICKER carries X and no explicit x declares X=0, so the
   SpellObject frame AND the journalled CAST row's x_value match what the plan
   paid (the Primal Might bug, cost-side). Un-kicked cast of an X-kicker card
   keeps x_value None: no X is in the total cost, no declaration is owed.
3. **`legal_casts`**: the X-kicker kicked row rides the ZND-1e both-ways lane —
   at the X=0 witness the kick row is priced at BASE cost, so BOTH rows show
   even on a base-priced pool (C15: the choice is visible); caller `x=k` folds
   {X}=k into the kicked row's price; an unaffordable k disappears the row as
   an ordinary `cost:mana_generic` SHORTAGE (never a raise).
4. **Adopted X-law (edge gate)**: **X=0 kick IS legal** — the engine's standing
   X-lane precedent is CR 107.1 zero-floor (spell_castable: "X=0 is legal… the
   SURFACE enumerates at 0"), so a kick with X=0 pays {0} and marks kicked.
   The printed **"X can't be 0." is UNPARSED** (the frozen Quantity grammar has
   no X-bound-constraint atom) — the engine cannot enforce a constraint it
   cannot see; enforced silently anywhere would be the bigger lie. Pinned by
   `XKickerLaneTest.test_x_kicker_zero_floor_is_a_legal_kick`.
5. **`run_scenarios.py` kick_rows expect lane**: reads the LAST CAST journal row
   per key (the same 6-tuple WAS_KICKED consumes: kicked flag + declared X);
   a never-cast key FAILS loudly. Journal-backed expects follow the 16b
   `attackers` precedent.
6. **WAS_KICKED under X-kicker (deliverable 4)**: the window read needs no
   change (kicked column is row-positional) — proven: X=2 kicked cast journals
   `(caster, ord, CREATURE, hand, 2, True)` and `eval_filter(WAS_KICKED)` reads
   True for the handle (`test_was_kicked_window_sees_the_x_kicked_cast`).

## The flip: NO — effect gap REGISTERED (this is the deliverable-2 verdict)
Thieving Skydiver's compiled tree is cost + FLYING + KickerAbility({X}) +
SpellAbility carrier — **three sentences UNPARSED**:
- "X can't be 0." → missing shape: an X-DECLARATION CONSTRAINT atom (bound on
  the declaration axis, orthogonal per §9).
- "When this creature enters, if it was kicked, gain control of target artifact
  with mana value X or less." → missing shape: WAS_KICKED-gated ETB trigger
  with a TARGET menu filtered by **mana-value ≤ X** (QX inside a selector
  filter quantity — no producer today; WAS_KICKED conditioning itself IS
  supported lanes-wise, the X-bound menu is the blocker).
- "If that artifact is an Equipment, attach it to this creature." → missing
  shape: mid-resolution SUBTYPE-conditional tail effect (ATTACH lane exists —
  ZND-2 equip — but no "if TARGET is a <subtype>" judge on the effect axis).
Compiler.py NOT touched (coordination rule: flip not happening ⇒ not required).
Consequence: the ZND-1e gate's X-kicker clause keeps the card UNSUPPORTED —
correct verdict, STALE PREMISE in its comment ("no producer wires the kick
choice to an X declaration" — a producer now exists). Re-ground that comment
in the wave that lands the effect templates (b6/b7 lane, owner: ZND-2
surface): flip criterion = card's compiled tree carries a WAS_KICKED consumer
whose verbs + QX-filter shapes all pass the engine fold. Census unchanged
(executor-only diff): ZNR engine-supported stays **267**.

## Numbers (commands below, 2026-10-18)
- Packs **403 → 404** (`tools/run_scenarios.py`), new `znr_thieving_skydiver_xkick`
  (kick X=2 pays {1}{U}+{2}=4U, marks kicked, journals x=2; un-kicked cast pays
  2, kicks False, x None; 8−4−2=2 mana math pinned; effect lane NOT exercised —
  settled vanilla body is the honest unsupported shape). Double-run identical.
- Unit: `XKickerLaneTest` 5 tests (fold prices declared X; X=0 legal-kick law;
  too-big X = shortage not raise; legal_casts both-ways + disappears-at-x=3;
  WAS_KICKED window read). Core+tools: **2860 passed + 36 subtests**
  (`pytest MTG_bot/core tools -q`, no split needed — sibling committed cleanly).
- M21 PC-4 **0 diffs** (305 files); report delta = `generated`/`git_head` +
  PC-5 timing only.
- pyright **0 new** (6 pre-existing run_scenarios `got =` re-assignment errors
  reproduce identically at HEAD); ruff **delta 0** (TRY004 legality:1553 +
  PERF102/BLE001 run_scenarios all pre-existing, line-shifted).

## Near-miss (see PITFALLS)
Used `git stash` once to get a pre-change ruff baseline WHILE THE SIBLING WAVE
WAS LIVE; the sibling committed mid-window. Pop applied with no conflict and
nothing was lost (verified: sibling files in HEAD, my edits present, 404/404),
but a shared-tree stash can silently absorb a sibling's uncommitted work.
Correct recipe: `git show HEAD:<file> > /tmp/...` per file, never tree-level
stash during a live wave.
