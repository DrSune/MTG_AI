# 100 — ZND-1e vertical slice: compiled kicker mechanics become PLAYABLE (journal-carried kick, cast/cost lane, honest engine gate, 4 real ZNR packs)

Date: 2026-10-18 (engine lane, follows /95 binding spec + /98 deviations). Grammar
frozen: zero changes to ability_tree.py, templates_b6 patterns, compiler fold region
(1492-1531). M21 goldens + compile outputs byte-unchanged (PC-4 0 diffs, 305 files).

## What landed
1. **Carrier = the journal.** CAST rows are now 6-tuples
   `(caster, ordinal, spell_kind, from_zone, x_value, kicked)`; `SpellObject.kicked`
   rides cast->stack->resolve; WAS_KICKED (quantity `_eval_atom`) reads the LAST CAST
   row of the judged handle in the turn window — no row -> False (never guess).
   One encoding serves all three reader lanes: spell-on-stack Conditional
   (Into the Roil), TriggeredAbility.condition / event filter (Roost both arms,
   binder judges `event.subject`), gated EtBState (Cragplate, via ctx_for+eval_filter).
   All three unpack sites updated (binding._match_cast, quantity x2, test).
2. **Cast/cost lane.** `spell_castable(kicked=)`: kicker cost joins the CR 601.2f
   fold; refusal reasons `cast:not_a_kicker` / `cast:kicker_with_x_unsupported`.
   `legal_casts` enumerates EVERY kicker card BOTH ways (CR 601.2b choice; §10 —
   the decision is visible on the query surface with its true cost). CastOption
   gains `kicked`. Runner cast step gains `"kicked"`.
3. **Kicker-head carrier (compiler, outside the forbidden fold):** a
   noncreature/non-land head with a KickerAbility but no SpellAbility (no effect
   sentence — Roost of Drakes: kicker head + two triggers only) gets an effect-less
   `SpellAbility(kind)` carrier (Goremand precedent). Before: `cast:not_a_spell`,
   the card's kick was unexercisable. M21 byte-safe: zero KickerAbility nodes in M21.
4. **Honest engine gate (compiler, §8/§10):** KickerAbility cost containing X and
   gated EtBState with non-QConst counters are UNSUPPORTED (no producer wires the
   kick choice to an X declaration — deferred /95). WAS_KICKED itself is now
   supported (lane delivered).

## Numbers (commands below, 2026-10-18)
- ZNR engine-supported **268 -> 267** (metas census), engine deckable **268 -> 267**.
  Flipped by the honest gate: **Thieving Skydiver ONLY** (X-kicker {X}; its kick
  effect is unparsed anyway — the flip is correct, not a regression of play).
  Cmd: get_supply("all","ZNR") + re-run of the gate predicate over all trees
  (before = after UNION predicate-hits).
- Scenario packs: **402/402** (`tools/run_scenarios.py`; 398 M21 unchanged + 4 new
  real-ZNR packs, per-set supply routed by pack `"set"` key).
- Core suite: **2579 passed** (`pytest MTG_bot/core -q`). New: ShapeGapSupplyExclusion
  Test (3), KickerLaneTest (4: carrier shape, kicked fold 4U-vs-shortage,
  not_a_kicker refusal, legal_casts both-ways), Roost golden amended to include the
  carrier (hand-certified goldens pin compile output — ZND-1e INTENTIONALLY changes
  this card's shape, documented in the test docstring).
- M21 pins hold: engine_ids 301, deckable 281, metas 285, gaps (); report diff vs
  /tmp/opencode/grammar_m21_prechange.json = PC-5 timing runs + git_head only.

## CR 603.2 law exercised (pack znr_roost_of_drakes_kick)
Kicked Roost's OWN cast fires only the ETB trigger (1 Drake): the "whenever you
cast a kicked spell" ability was not on the battlefield when its own spell was
cast. The pack's Drake count 2 (not 3) is a POSITIVE test of 603.2 — 3 would be
the always-fires bug. Kicked Roil then fires the cast trigger (2nd Drake).
Un-kicked 2nd Roost: both arms silent (falsifies always-fires encodings).

## Kitesail designation (§10 blindness check passes)
znr_kitesail_cleric_kick: kicked ETB -> QAtMost(2) TARGET TAP designates through
the ask channel (pack keys as answers, 18b lane); the un-kicked cast produces NO
ask at all (step runs on the quiet provider, which RAISES on any unprimed ask —
the lane itself falsifies a phantom choice). Mana lanes: Kitesail total cost
{W}+{2}{W} = 4 mana (2 generic + 2 white) — pack math.

## Deferred (registered, not silent)
- **Ask-lane "kick?" decision PRESENTATION**: the model-facing ask that offers
  kick at cast time is NOT built; the play lane carries the choice as a cast
  parameter and legal_casts shows both priced rows. Ask-lane = model lane task.
- cast_card (effect-side cast) stays non-kicked (no kick choice exists there).
- Blink/re-entry: WAS_KICKED reads the turn window's last CAST row — a blinked
  kicked permanent re-ETBs True where CR says False (window heuristic; named,
  single-row simplification, revisit when the first real blink pack lands).
- Thieving Skydiver X-kicker support: needs the X-declaration producer (/95).
