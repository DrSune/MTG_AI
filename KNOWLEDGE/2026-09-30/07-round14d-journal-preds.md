# Round 14d — the B-7 journal family, B-19 stack runtime, B-17 inventory STOP (2026-09-30)

Mission: (1) B-7 filter-predicate family — journal-aware eval at ALL entry points +
implement the history preds the games hit; (2) B-19 Zone(STACK) runtime enumeration;
(3) B-17 activation-tail per the orchestrator ruling (inventory-first, STOP-guarded).

## The journal-is-state purity argument (design note, binding)

Queries were "pure" in the wrong sense: pure was read as AMNESIAC — a query context
carried the world but not the journal, so a predicate that reads history could not be
asked from `legal_targets`/`legal_activations` at all, and the 14c wall (13/22 crashes
were filter preds raising) was really a *wiring* gap plus a *vocabulary* gap. The
ruling: **purity is determinism, not amnesia.** The `EventJournal` is replayed state
(the 12b `dump()` folds it into the fingerprint, so replays re-derive it byte-identically);
reading it during a query is exactly as deterministic as reading `world.zone(...)`.
Consequences landed:

* `ExecCtx.journal` is bound at **every** construction site — `Executor._ctx`,
  `legality.ctx_for` (all 13 query/legality callers), `TriggerBinder._ctx`,
  `LayerRegistry._ctx` — the 13a FLIP_WON "bare-ctx" lesson generalized: a predicate
  the query must answer cannot live off a register the query does not carry.
* No half-preds: `journal is None` (bare unit-test contexts) raises naming the pred —
  the FLIP_WON/NAME_CHOSEN convention. An unanswered question is flagged, never a
  guessed False.
* `EventJournal.turn_window()` defines "this turn" = rows after the most recent
  begin-turn UPKEEP marker (the marker is emitted after the per-turn trackers reset;
  UNTAP-step TapState rows sit before it by 12d's ordering and no turn-history pred
  reads untaps; no marker yet = the whole log, the honest turn-less-world reading).

## B-7 preds implemented (pred → journal/world query → games-hit card)

| pred | query used | games-hit card(s) |
|---|---|---|
| CONTROLLER_COUNT_GE | WORLD count: battlefield population under `ctx.controller` passing `inner_filter` ≥ count (no journal — handle-free like FLIP_WON) | Fabled Passage ("if you control four or more lands"), Gadrak (artifacts) |
| MOVED_TO_ZONE_THIS_TURN | ZONE_CHANGE rows in the turn window, BOTH owner columns checked (the 12b snapshot keys zones by player) + `controller_matches(who, owner_after)` | Necromentia (count, handle-scoped), Barrin (gate, existential) |
| ENTERED_THIS_TURN_FROM | ZONE_CHANGE rows: subject==handle, to==battlefield, from==zone slot, this turn | Archfiend's Vessel (FOr twin — had to ship WITH CAST_THIS_TURN_FROM: FOr judges both children) |
| CAST_THIS_TURN_FROM | 13b CAST rows: subject==handle, `cast[3]` from_zone, `controller_matches(who, caster)` + zone-side | See the Truth (FNot(HAND)), Archfiend's Vessel |
| DIED_THIS_TURN | CREATURE_DIES rows (the C18 row carrying the was-snapshot) subject==handle | Gadrak's Treasure count family (9 goldens compile it) |
| IS_EXILED_WITH_SOURCE | WORLD half (in exile NOW) + HISTORY half over the WHOLE journal (an exile-with persists across turns): to==exile, cause==ctx.source | Idol of Endurance, Chandra Heart of Fire, Necromentia station |

The "WAS_TYPE (C18)" item in the evidence brief is **verified NOT to exist** in the
frozen `FAtomPred` vocabulary (no WAS_* member) — the C18 snapshot's consumers are the
CREATURE_DIES row lookup + the binder's event matcher; recorded so nobody invents one
(C12). The MOVED dual reading (per-candidate when the handle currently sits in the
pred's destination zone, existential otherwise) is documented at the branch; OWNER zone
slots in these preds stay a loud NotImplementedError (no corpus use).

## B-19 (fixed, ~10 lines)

`selectors.enumerate_zone` Zone(STACK) had no `ZONE_KIND_TO_STATE` entry → bare
`KeyError(ZoneKind.STACK)` at runtime (B-2's twin). Now enumerates the parked frames
through `stack.stack_zone` (F-2's shape — the SAME source legal_targets reads, §8.3
query/runtime identity; TOP = last entry = top frame). OWNER keeps the existing 12b
selector raise. Pinned test `test_new_zone_stack_runtime_enumeration_raises` AMENDED
green (real park→MoveZone→hand leg + the honest OWNER/empty-designation legs).

## B-17 — inventory proves the SCOPE-STOP (no compiler or golden changes)

Full 305-card instrumented sweep (`/tmp/opencode/inventory_r14d_b17.py`, spy-order
mismatches 0; printed text vs compiled tree per candidate):

| candidate | printed tail | compiled on SpellAbility | verdict |
|---|---|---|---|
| Tavern Swindler | "If you win the flip, you gain 6 life." | IF(FLIP_WON)→GAIN_LIFE(6) | clean activation tail — would fix |
| Waker of Waves | "Put one of them into your hand and the other into your graveyard." | Seq(MODIFY_PT; Seq(MOVE_ZONE×2)) (tail = the MOVEs) | clean tail — would fix |
| Seasoned Hallowblade | "It gains indestructible until end of turn." (printed IS an activation tail — Scryfall re-verified, the 14c premise of a "static-ish" SpellAbility effect holds only in the sense that the tail sits on it) | GRANT_ABILITY(..., referent='result') | ruling collision: the 14c ruling forbids capturing it, but ANY matcher shape that captures Swindler captures Hallowblade (same "It gains X" idiom 14b-1 already consumed for Liliana's emblem); and capture would NOT fix it — the GRANT reads the `result` referent, which still raises outside a firing (B-9). |
| Chandra, Heart of Fire | "Add six {R}." under the [−9] loyalty bullet | ADD_MANA | boundary AMBIGUOUS: the empty-cost `OPT(CAST)` permission idiom (template B4-cast-them-this-turn) sits between the loyalty bullet and its tail and breaks the r11 loyalty chain — the specified activated-matcher would mis-capture it under the CAST permission. |

**Ruling applied**: inventory carries a boundary-ambiguous card and a ruling-collision
card → the ruling's STOP condition fires. compiler.py, goldens and PC numbers untouched
(goldens move only via an audit that never ran); the eval-side FLIP_WON raise pins stay
as filed. Next-round adjudication queued: (a) exempt the documented empty-cost OPT(CAST)
permission idiom from the matcher AND re-adjudicate Hallowblade jointly with the B-9
`result`-referent work (a fix for one without the other moves the crash, not fixes it),
or (b) a per-card compiler-template exception list (ad-hoc, disfavoured).

## Re-measure (14c baseline → 14d)

cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}` + `--seeds 30 --pool engine` (reports /tmp/opencode/r14d_*.json)

| run | 14c | 14d |
|---|---|---|
| all 10s | 2/10, 35.9t, cov 41 | **8/10, 52.6t, cov 46**, 970 acts, 2 crashes |
| engine 10s | 6/10, 46.2t, cov 44 | **7/10, 53.5t, cov 46**, 1045 acts, 2 crashes |
| castable 10s | 0/10, 18.3t, cov 39 | **1/10, 30.6t, cov 43**, 907 acts, 7 crashes |
| engine 30s | 10/30 (33.3%), 34.9t, cov 51, 2021 acts | **18/30 (60.0%), 48.5t, cov 60, 3004 acts** |

PC-7 v1.1 → **v1.2: 60.0%** engine survival (22.5% coverage-fired of the 267 playable
engine cards, same convention as 14c's 19.1%). B-7-family (13/22) and B-19 (2/22)
classes are GONE from every pool.

## New headwall (named honestly, engine30 11 crashes / 30 games)

1. **B-9 residual, new face — 8/11 (73%)**: "selector referent 'result' only resolves
   inside a trigger firing" at **cast:Feat of Resistance** (the C2 referent-outside-
   firing family Hallowblade anchored; now the dominant wall as the games run 2× deeper).
2. **B-17 FLIP_WON-at-cast — 2/11** (Tavern Swindler; unchanged by the STOP above).
3. **Unimplemented WORLD preds — 1/11 engine30, 2/11 10-pools**: POWER_GE
   (Legion's Judgment line) and CMC_LE (Eliminate's target filter) raise at the same
   quantity.py site — world-evaluable twins of POWER_LE/PT_LE, next round's small fix
   (NOT hit in 14c's attribution; honestly out of this round's demanded list).
4. Verb FIGHT handler-less — 1 (all pool, Primal Might; ledger family).

## Gates

Core **2007 passed** (2001 + 6 new pins; 3 frozen pins AMENDED in place with dated
markers — the "triangle": b7 CONTROLLER_COUNT_GE, moved/cast stays-unimplemented,
zone-stack-runtime-keyError). PC-1 0.9869 / PC-2 0.9922 / PC-3 0 / PC-4 0-diff
**EXACT** (`tools/measure_grammar.py --set M21`) — goldens untouched by design (B-17
STOP). pyright 0 errors (edited scope; repo-wide delta 0 = 524→524); ruff delta 0;
replay determinism green (ReplayDeterminismTest + every amended pin fingerprint-safe).
Edited (UNCOMMITTED): events.py, quantity.py, selectors.py, legality.py, binding.py,
layers.py, `__init__.py`, test_executor_games.py + this doc + ledger /03 + INDEX/NUMBERS.
