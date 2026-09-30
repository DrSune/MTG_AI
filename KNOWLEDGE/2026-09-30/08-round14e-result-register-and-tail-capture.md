# Round 14e — B-9 result-register at resolution, B-17 activation-tail capture (exempted idiom), POWER_GE/CMC_LE (2026-09-30)

Mission (binding adjudication, option (a)): (1) B-17 activation-tailing capture WITH the
empty-cost OPT(CAST) permission idiom exempted; (2) B-9 result-referent-at-cast semantics
(producer-writes, per-resolution, faces-driven); (3) POWER_GE + CMC_LE world preds. Then
re-measure. Order executed: 3 → 2 → 1.

## B-9 — the result register is a PRODUCER slot inside every effect execution (design, faces-first)

The 14d wall (8/11 engine30) read the closed `result` referent at CAST resolution and the
register only existed inside a trigger firing (`binding.py` binds event/result = the event
subject). The corpus sweep of EVERY `referent='result'` reader with its preceding atoms
(11 readers, 8 result-readers) drove the producer set — every face's LAST write before the
read is the anaphoric antecedent:

| face | read | preceding atoms | producer that answers it |
|---|---|---|---|
| Feat of Resistance (SpellAbility Seq) | GRANT.target | PUT_COUNTER(target) | PUT_COUNTER (new 14e) |
| Basri, Devoted Paladin +2 / Basri Ket | GRANT.target | PUT_COUNTER(target) | PUT_COUNTER |
| Seasoned Hallowblade (captured tail, see B-17) | GRANT.target | TAP(target=IS_SOURCE) | TAP (new 14e) |
| Traitorous Greed | GRANT.target | GAIN_CONTROL, UNTAP | UNTAP (verb GAIN_CONTROL itself stays unimplemented — the card still dies there, honest) |
| Liliana, Waker of the Dead emblem | GRANT.target | MOVE_ZONE | MOVE_ZONE (new 14e; the ACTION's object is the honest antecedent, not the firing's event subject) |
| Kitesail Freebooter / Duress | EXILE / DISCARD | REVEAL, CHOOSE | CHOOSE (14c, unchanged) |
| Necromentia | EXILE.target | SEARCH | SEARCH (14c, unchanged) |

Design, three sentences: **producers set** = SEARCH/CHOOSE (14c) ∪ {TAP, UNTAP, PUT_COUNTER,
MOVE_ZONE} (14e) write the handles they acted on into `ctx.bindings["result"]` after acting;
**register scope** = per effect execution — `Executor._ctx` copies a fresh bindings dict per
execute/apply_effect/`_cast_ctx`, so one resolution's writes never leak into the next (proved
by pin: re-running the captured GRANT step in a fresh execution raises); **read semantics**
= unchanged slot read (`resolve_selector` referent branch), with an unset register STILL a
loud `NotImplementedError` naming the referent and "no producer atom wrote one in this
execution" — a missing antecedent is flagged, never a guessed empty population. The raise
message was rewritten because the old wording ("only resolves inside a trigger firing") had
become false. `event` stays firing-only (no producer has an event outside one).

**Residual face, named honestly (3/30 engine30): Chandra, Heart of Fire `#4`.** The
B4-cast-them-this-turn permission row is a SEPARATE free-cost ActivatedAbility whose CAST
atom reads `referent='result'` ("cast THEM"); activating the permission on a LATER turn
finds no register because the exile ran in the [−9]'s resolution — this is a CROSS-resolution
anaphora ("cards exiled this way"), a different relation than this round's per-resolution
register. The engine already models exactly this relation as `IS_EXILED_WITH_SOURCE` (14d,
and Chandra's [+1] permission compiles THAT filter); the fix is B4-template fidelity (emit
the predicate, not the referent) = a golden-moving FIDELITY class with its own audit —
NOT forced here (this round's goldens moved only via the B-17 capture audit).

## B-3 preds — POWER_GE + CMC_LE (world-evaluable, no journal)

POWER_GE joins the live-P/T family (`effective_pt` — layers folded, same as POWER_LE;
characteristic absent = False: a land is not "a creature with power 4 or greater"). CMC_LE
reads IDENTITY mana value with the convention quantity.py's QProp CMC/MANA_VALUE field
already uses: `identity.cmc or 0` — a synthetic token has mv 0 (CR-true, established, not
invented here); QX thresholds ride the cast's declared X (14c CR 601.2f), unbound outside a
cast still loud. Faces: Legion's Judgment/Turret Ogre/Drowsing Tyrannodon/Garruk's Uprising/
Furious Rise/Ornery Dilophosaur/Leafkin Avenger (POWER_GE); Eliminate/Idol of Endurance/Ugin
(CMC_LE). The 14d census trio (2+1 crashes) is GONE.

## B-17 — activation-tailing capture WITH the OPT(CAST)-permission exemption (compiler, audited re-baseline)

`_activation_trailing_idx` mirrors the loyalty/trigger chain discipline (only unparsed slots
and rule reminders are transparent; `[`-bullets never captured; loyalty-costed abilities
return None — their tails belong to the R11-1 chain; effect-less cost-carriers are a hard
boundary) — a bare EffectOutcome sentence whose nearest meaningful predecessor is a plain
ActivatedAbility now merges into that ability (may-rule + the 14b-1 de-dup guard, mandatory
append for these three tails). **Exemption**: `_is_cast_permission_row` detects the template
B4 idiom — ActivatedAbility with EMPTY cost whose whole effect is `OptionalEffect(Atom(CAST,
cost=Cost()))` — and the backward scan sees THROUGH it: a permission never owns a tail
(Chandra's "Add six {R}." stays card-level, status quo, one transparent skip per compile
recorded by the instrumented sweep), while a tail printed after a permission that follows a
PLAIN activation captures onto that activation (synthesized pin — no M21 card needs the
crossing yet).

Inventory-first (instrumented sweep of the REAL matcher, `/tmp/opencode/inventory_r14e_b17.py`:
305 cards, 66 tails reached the matcher, **3 captures**: Tavern Swindler (Seq(FLIP_COIN;
IF(FLIP_WON)→GAIN_LIFE)), Seasoned Hallowblade (Seq(TAP; GRANT(result))), Waker of Waves
(Seq(LOOK_AT; Seq(MOVE ONE_OF; MOVE REST)))). No new boundary ambiguity beyond the exempted
idiom → the 14d STOP does NOT re-fire. Goldens re-baselined and audited (r11 protocol):
pre-refresh snapshot `/tmp/golden_pre_r14e_2026-09-30`, diff == inventory SET-EQUAL
(Swindler, Hallowblade, Waker), every diff keys ⊆ {abilities}; PC-1 0.9869 / PC-2 0.9922 /
PC-3 0 / PC-4 0-diff **EXACT** post-refresh (capture is post-template, coverage untouched).
Swindler + Hallowblade lose their accidental SpellAbility node → they join the B-1
not-castable set (playable_engine 88→86 — the crash MOVED exactly as the ruling predicted);
their activations are now correct and pinned (library e2e AMENDED: the single activation row
runs flip → gate → +6 life in ONE resolution, "Swindler gains 6 life on won flip" in-engine;
games B-9 pin flipped to the Feat-of-Resistance cast + Hallowblade activation + unset-read
raises + not_a_spell-cast leg). Waker's static −1/−0 MODIFY_PT stays on its SpellAbility
(pre-existing static-family miscompile, T8-era, untouched — flagged for its own round).

## Re-measure (14d → 14e)

cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}`
+ `--seeds 30 --pool engine` (reports /tmp/opencode/r14e_*.json)

| run | 14d | 14e |
|---|---|---|
| all 10s | 8/10, 52.6t, cov 46, 2 crashes | **9/10, 55.1t, cov 45, 1027 acts, 1 crash** (FIGHT) |
| engine 10s | 7/10, 53.5t, cov 46, 2 crashes | **9/10, 59.9t, cov 48, 1212 acts, 0 crashes** (1 natural "game over") |
| castable 10s | 1/10, 30.6t, cov 43, 7 crashes | **5/10, 53.6t, cov 57, 1637 acts, 3 crashes** (EachPlayer 2, KEYWORD_HAS 1) |
| engine 30s | 18/30 (60.0%), 48.5t, cov 60, 3004 acts | **26/30 (86.7%), 58.6t, cov 61 = 22.8%, 3753 acts, 3 crashes** |

PC-7 v1.2 → **v1.3: 86.7% engine survival**. Engine-pool wall census (11 → 3 crashes): the
ONLY remaining class is the B-9 cross-resolution permission-anaphora face (Chandra #4,
seeds 23/25/29). Plainly: the engine pool's remaining wall is NOT flagged-verb plays or
arc-3 combat — it is that one named residual class (flagged deaths live in `all`: FIGHT/
Primal Might; `castable` stays honestly crash-heavy: EachPlayer/Goremand — a 12e node, and
KEYWORD_HAS/Run Afoul — a NEW world-pred face of the same small-fix family as POWER_GE/
CMC_LE, next round). Combat itself is still unreached: mean 58.6 turns against the 60-cap
means games end by attrition (draw-empty losses appear), so arc-3 remains an untested
surface, not a measured wall.

## Gates

Core **2013 passed** (2007 + 6 new: 3 pred pins + 3 matcher pins; 3 frozen pins AMENDED in
place with dated markers — the triangle: compiler chain test, Swindler library e2e,
CMC_LE-legality probe). PC-1/2/3/4 **EXACT** (goldens moved only via the capture audit);
PC-7 engine_supported **286/305 EXACT**; pyright 0 errors (edited scope; repo 524→524);
ruff delta 0 (per-file findings identical to HEAD); replay determinism green
(ReplayDeterminismTest + every amended pin fingerprint-safe). Edited (UNCOMMITTED):
compiler.py, quantity.py, verbs.py, selectors.py, test_compiler.py, test_executor_games.py,
test_executor_library.py, test_executor_legality.py, 3 goldens + this doc + ledger /03 +
INDEX/NUMBERS.
