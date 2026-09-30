# 2026-09-30 · 09 — ROUND-14 CLOSE-OUT: the four final bundles; PC-7 v1 CONVERGED at 96.7%

Round 14f (final convergence batch): (1) the Chandra B4-row fidelity fix,
(2) KEYWORD_HAS, (3) EachPlayer, (4) the static-tail B-11-family inventory
(+ bounded fix). Order executed: 2 → 3 (executor-only) → 1 → 4 (audited,
inventory-first). Then the final PC-7 v1 re-measure.

## Bundle 2 — KEYWORD_HAS (B-21, executor)

The 14e census face (Run Afoul — "sacrifices a creature of their choice
WITH flying", castable seed 5). The pred's frozen vocabulary places it in
BOTH surfaces — selector filters AND gate positions (inventory: Run
Afoul's CHOOSE filter, Celestial Enforcer/Tide Skimmer conditions, Hooded
Blightfang's event filter+source, Portcullis Vine's COST-target gate,
Lofty Denial/Watcher of the Spheres cost-modifier conditions,
Snarespinner's blocked-with-flying) — and every position evaluates
through the ONE `eval_filter` entry. One branch in `_eval_atom` answers
all of them: the LIVE keyword oracle `layers.keyword_of` — printed
identity keywords ∪ live grants − live losses, rebuilt at every settle
(the 12d anthem oracle combat legality already calls). Bare ctx (no
registry) RAISES naming the pred — a printed-only guess would be
silent-wrong on a granted/stripped keyword (the IS_ATTACHED_TO_SOURCE
convention); a non-card handle is characteristic-absent False. Pin:
grant-flying flips membership IN-ENGINE.

## Bundle 3 — EachPlayer (B-20, executor)

Inventory: exactly 4 corpus faces, ALL compiled as `ALL_OPPONENTS` under
a TriggeredAbility — Goremand (per-opponent SACRIFICE), Keral Keep
Disciples (damage), Pursued Whale (creates a Pirate — engine-FLAGGED card,
MANDATE_ATTACK, so never dealt in engine pools), Thieves' Guild Enforcer
(mill). The templates' ruling (b2a/b2b): the inner effect is compiled
**YOU-relative** — Goremand's filter `CONTROLLER_IS YOU`, MILL's
controller role, `Zone(PLAYER,YOU)` — so the handler's single mechanism is
the **controller rotation**: one sub-execution per `players_for_ref`
seat, bindings carried (the spell's designations stay visible), the
per-op decision-POOL cursor forwarded across sub-contexts and written
back (one positional supply answers every station in ask order; the
vocabulary-addressed stream lanes are executor-owned). CR 800.2's
each-player convention starts at the APN and passes around the table —
seat-order iteration is the DOCUMENTED simplification (it coincides in
the duel), never a silent rule. `apply_effect`'s node gate + `_run_effect`
both wired; Repeat stays loud (no consumer).

## Bundle 1 — Chandra's B4 row (audited fidelity)

14e's residual, fixed at its named station: `B4-cast-them-this-turn`
emitted the per-resolution `referent='result'` register for a
CROSS-resolution anaphor ("them" = cards the [−9]'s own resolution
exiled; the permission activates LATER). The fidelity fix compiles the
relation the executor already models — `IS_EXILED_WITH_SOURCE` (R8-6;
world half + journalled-cause half), CHOOSE + QUnbounded +
Zone(EXILE, YOU): **Chandra's own [+1] play-permission row's shape, down
to the filter** (and the Idol of Endurance b3 twin). Inventory: exactly
1 card carries the sentence (set-equality premise pinned); documented
fidelity edge: the pred's frozen reading is SOURCE-scoped, not row-scoped
— both of her permissions read the union of her exiled-with population
(the [+1] golden's established semantics, not an invention). A fresh
resolution now answers from the journal where 14e's producer rule
correctly refused (pinned at the exact seam: cross-source population
stays CAUSE-scoped — an Idol's exiles are not Chandra's).

## Bundle 4 — static-tail B-11 family (inventory + bounded fix, audited)

Inventory-first across the 305: SpellAbility-carried STATIC-family atoms
(MODIFY_PT/GRANT_ABILITY/LOSE_ABILITY/GRANT_TYPE with NO duration role)
on PERMANENT cards → **exactly 1 card: Waker of Waves** (the broad
scan's other hits are instants/sorceries carrying DurationEot — legitimate
cast effects). Root cause is a template OUTLIER: `_build_modify_pt_static_
opponents` was the lone row of its family (static-you, grant-kw-static-you,
other-cats, other-dogs, other-creatures — ALL `AbilityOutcome(
StaticAbility)`) emitting a bare `EffectOutcome`, which the assembly
folded into the creature's SpellAbility and ran ONCE at cast. The fix is
the family's own wrapper; `layers.attach_card` consumes card-level
StaticAbility nodes as live anthem layers (the 12d recompute path), so
the corrected node is the executor's live-anthem path, and the card keeps
its captured activation (14e) untouched. Consequence, ruled precedent:
Waker loses the accidental SpellAbility → joins the B-1 not-castable set
(`playable_engine 86→85`, exactly the 14e Swindler/Hallowblade move).
**No new boundary ambiguity → no STOP re-fire.**

## Gates (14f)

Core **2022 passed** (2013 + 9 new: 6 `Round14fSurfaceTest` + 3
`TestRound14fFidelity`; 3 tests AMENDED in place with dated markers: the
static-opponents kind flip ×2, the unsupported-node flip — Repeat-only).
Goldens moved **ONLY via the two audits**: pre-snapshot
`/tmp/golden_pre_r14f_2026-09-30`, full regenerate, diff == inventory
SET-EQUAL (Chandra, Waker), every diff keys = {abilities}. PC-1 **0.9869**
/ PC-2 **0.9922** / PC-3 **0** / PC-4 **0-diff EXACT**; engine_supported
**286/305 EXACT** (no verb added); pyright **0** (edited scope); ruff
delta **0** (per-file findings identical to HEAD); replay determinism
green (ReplayDeterminismTest + every amended pin fingerprint-safe);
the three 14e crash seeds (`castable` 5/7/9, `engine` 23) replay
**crash-free to the cap**. No commit (uncommitted like every 14x round).

## PC-7 v1 — the journey (deck-pairs 1409, cap 60)

cmd: `.venv/bin/python -m MTG_bot.core.executor.games --seeds 10 --pool {all,engine,castable}`
+ `--seeds 30 --pool engine`

| round | engine 10s | engine 30s | crashes (engine30) | wall |
|---|---|---|---|---|
| 14a (v1) | **1/10 (10%)**, 17.4t | — (not yet run) | almost all games | B-4 positional channel |
| 14b-2 | 3/10, 38.8t | — | — | B-13 ONE_OF prompt |
| 14c (v1.1) | 6/10, 46.2t | **10/30 (33.3%)** | — | B-7 preds 13/22 |
| 14d (v1.2) | 7/10, 53.5t | **18/30 (60.0%)** | 11 | B-9 result-at-cast 8/11 |
| 14e (v1.3) | 9/10, 59.9t | **26/30 (86.7%)** | 3 | Chandra #4 only |
| **14f (final)** | **9/10, 59.9t, 0 crashes** | **29/30 (96.7%)**, **mean 60.0t**, 3843 acts, cov 58 = 21.7% | **0** | none (1 natural draw-loss, seed 0) |

10-seed pools final: all **9/10** (55.1t, cov 43, 1010 acts — 1 crash:
FIGHT/flagged verb, all-pool-only by construction); engine **9/10**
(59.9t, cov 44, 1187 acts, 0 crashes); castable **5→8/10** (57.4t,
cov 48, 1809 acts, **0 crashes** — 2 natural CR-121.3 draw-losses).

**PC-7 v1 VERDICT: CONVERGED.** The engine pool now plays 29/30 games to
the turn cap with ZERO exceptions; the single non-survivor is a natural
draw-from-empty LOSS (a game result, not an engine wall). Nothing in the
engine-supported surface asked for another executor fix — the honest
ceiling that remains is a SCOPE line, listed below.

## The bug ledger — final census (round 14 close)

**Fixed (22 rows):** F-1, F-2(B-2), F-3(B-8a) [14a]; B-4, B-5, B-8
[14b-2]; B-11 [14b-1]; B-13, B-14-at-cast, B-15, B-16, B-18 [14c];
B-7-family, B-19 [14d]; B-9 in-execution, B-17, POWER_GE, CMC_LE [14e];
**B-9 cross-resolution residual (Chandra #4), B-20 EachPlayer, B-21
KEYWORD_HAS, B-22 static-anthem outlier [14f]**.

**Fixed-partial (by design, flagged-not-guessed residuals):** B-7's
un demanded vocabulary members (TURN_OF, ZONE_COUNT_GE, …) stay loud;
QX unbound outside a cast stays loud (B-14's other half — CR-correct).

**Open (4 named):** **B-1** (P0, compiler — non-land deckable cards with
NO SpellAbility; re-measured **192** under the harness definition,
`playable_engine 85`; grew by the two RULED moves: Swindler+Hallowblade
14e, Waker 14f — the capture/categorization fixes were correct and the
accidental cast-nodes rightly died with them), **B-3** (P1 — one target
designation per op), **B-12** (P2 — no mana-pool emptying in the harness
world: survival reads optimistic), and the **flagged-verb family** (18
deckable cards stay out of the engine pool by design).

## The remaining honest wall (not a crash list — a scope line)

* **Flagged verbs (18 deckable cards, flag-not-degrade — they RAISE when
  played in `all` and are never dealt in `engine`):** COUNTER_SPELL
  (Cancel, Lofty Denial, Miscast, Rewind, Sublime Epiphany),
  GAIN_CONTROL (Enthralling Hold, Traitorous Greed — 12d state-freeze
  flag), PHASE_OUT (Teferi ×2), COPY (Double Vision, Sublime Epiphany),
  FIGHT (Primal Might — the one measured `all`-pool death, Brash Taunter
  also), MANDATE_ATTACK/MANDATE_BLOCK (Furor of the Bitten, Canopy
  Stalker, Pursued Whale), ATTACH (Malefic Scythe, Short Sword),
  EXTRA_TURN + DAMAGE_ASSIGN_POLICY (Teferi, Garruk Savage Herald).
* **Arc-3 combat is UNREACHED, not measured:** the harness's turn
  skeleton never attacks (no combat ops are exposed to the policy), and
  at mean **60.0t** every engine game ends by attrition at the cap (the
  draw-empty losses are its fingerprint). Combat (declare attackers/
  blockers, damage assignment, the live layers/replacements it will
  stress) remains an untested surface.

## What PC-7 v2 (full set incl. combat) requires

1. **B-1 — SpellAbility nodes for permanents** (192 cards): compiler +
   audited golden re-baseline; this is the castability ceiling every
   pool number has been reading under.
2. **Arc-3 turn structure** in the executor (combat phase steps, attacker/
   blocker declaration ops over the query surface, damage + the already-
   live replacements/anthem layers under real attacks) + combat-aware
   harness policy.
3. **Flagged-verb family** (list above) — GAIN_CONTROL/PHASE_OUT against
   the state.py freeze boundary, COUNTER_SPELL on the live stack,
   ATTACH as aura state, COPY, MANDATE_*, EXTRA_TURN.
4. **B-3** multi-designation casts and **B-12** mana-pool emptying
   (honest, un-optimistic survival).
5. Re-measure with combat in the act vocabulary and (per the /02 plan) a
   100-seed run — PC-7 stops being an engine-survival number and becomes
   a win/draw/loss distribution.
