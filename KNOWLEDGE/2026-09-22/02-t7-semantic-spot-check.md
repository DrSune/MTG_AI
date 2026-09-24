# 2026-09-22 · 02 — T7 semantic spot-check (compiled trees vs real Magic)

**Method:** stratified sample of 27 fully/partially-parsed pool cards (vanilla,
vanilla+keyword, composite keywords, ETB tutors, combat triggers, statics,
equipment+counters, 5 planeswalkers+emblems, lands, X-costs, additional-cost
spells, replacement-adjacent). Compiled golden trees (canonical JSON) rendered
to compact form (`/tmp/opencode/t7_review_compact.txt` — tool: ad-hoc renderer,
2 renderer field bugs found+fixed before review: `OptionalEffect.inner`,
`Choose.options`-are-plain-effects, `PtDelta.magnitude`, cost `amount`).

## VERDICT: no semantic POISONING found in the sampled trees.
Every encoded ability says what the card says. No template encodes the wrong
target, wrong controller, wrong count, or wrong duration in the sample.
Findings are (a) honest gaps (UNPARSED, correctly flagged), (b) two narrow
encoding approximations, (c) one false-UNCOVERED candidate, (d) grammar-round-2
candidates.

## Correct (spot-checked, no issue)
Bloodfell Caves (all 3 abilities incl. `CHOOSE[1 of: ADD_MANA(B) | ADD_MANA(R)]`),
Feline Sovereign static (other-cats +1/+1 + protection from Dogs, `NOT(IS_SOURCE)`
right), Malefic Scythe (ETB soul counter via `EtBState`; `IS_ATTACHED_TO_SOURCE`
death trigger; equip), Teferi Timeless Voyager ([+1]/[−3] top-of-owner-library
with `LIBRARY(OWNER,TOP)` exact; [−8] phase-out of target player's creatures),
Basri Devoted Paladin ([+1], [−6] +2/+2+flying EOT), Nine Lives (counter-trigger
+ `LOSE_GAME` on leave-BBF; documented state-based simplification acceptable),
Scavenging Ooze (base activate), Thrill of Possibility (draw 2), Sanguine
Indulgence (return up to 2 creature cards), Sanctum (tap target, cost correct),
Sparkhunter (both activates + protection), Vryn Wingmare
(`CostModifier(NOT(TYPE_EQ(Creature)), ANY, +1 generic)` — `controller_ref=ANY`,
NOT a bug: my renderer had read the wrong field name), Alpine Houndmaster
(BOTH abilities exact incl. `+COUNT(other attacking creatures)` — a strong
data point), Discontinuity (END_TURN), Liliana Waker ([−3] `-PROP(cards in your
graveyard)` — exact), Ugin [+2] any-target damage.

## (a) Honest gaps — correctly UNPARSED, no wrong encoding
Composite-keyword line (Baneslayer Angel: "Flying, first strike, lifelink,
protection from Demons and from Dragons" — the WHOLE line unparsed, even the
vanilla keywords), anaphoric modal branches ("It gains vigilance…", "That
permanent loses indestructible…", "Round up each time"), turn-scoped loyalty
triggers, emblems-with-embedded-trigger (×3), "choose a card name" + dynamic
protection (Runed Halo), damage-prevention replacements (Nine Lives first line,
Scavenging Ooze continuation), "equipped creature gets +1/+1 per soul counter".
All in the registered UNCOVERED sets — honest.

## (b) Narrow approximations (tolerable, must be honored downstream)
1. **Goremand / EachPlayer rebinding:** "each opponent sacrifices a creature"
   encodes `EACH_PLAYER(ALL_OPPONENTS): SACRIFICE(... CONTROLLER_IS(YOU) ...)`
   relying on the documented convention that inside `EachPlayer`, `YOU`
   rebinds to the iterated player. The tree text alone says "a creature YOU
   control" — **the executor and the model MUST implement the rebinding**.
   Record as a binding contract (PITFALLS).
2. **Chandra's Firemaw tutor:** multi-zone search (library+graveyard) is
   correct, but the follow-up move is encoded as `LIBRARY(YOU, TOP) → HAND`
   ("that card" is approximated as top-of-library). Lossy when the card came
   from the graveyard. Same class: "put that card onto the battlefield
   TAPPED" (Solemn Simulacrum / Fabled Passage) — `MOVE_ZONE`/`SEARCH` have NO
   tap-state role (`_VERB_ROLES`: MOVE_ZONE={cards,destination}; SEARCH=
   {cards,destination,controller}), so "tapped" is silently dropped.

## (c) False-UNCOVERED candidate
- **Ugin [−X]** ("Exile each permanent with mana value X or less that's one or
  more colors"): b5c says "No X-threshold multicolor EXILE-each construct", but
  `CMC_LE(QX)` + `COLOR_COUNT_GE(2)` + `EXILE(ALL, BATTLEFIELD)` all exist
  post-T3. Verify by construction before accepting the UNCOVERED (likely
  coverable → round-2 template, no grammar change).
- Related report sloppiness: the b5c agent's round-2 report listed 6 remaining
  UNCOVERED loyalty lines without naming [−X]; the module on disk is the
  ground truth (still UNCOVERED). Reports must be re-verified against modules.

## (d) Grammar-round-2 candidates (each ≥3 shapes or named cross-set)
1. **Life/draw-this-turn THRESHOLD PREDICATES** `FAtomPred.LIFE_GAINED_THIS_TURN_GE`
   / `CARDS_DRAWN_THIS_TURN_GE` (count slot): QThisTurn is a Quantity but
   trigger conditions are Filters — "if you gained N or more life this turn"
   (B2a ×3: Griffin/each-opponent-loses/return-from-grave; B4: cost-reduction
   conditional; Indulging Patrician = same shape) — 4-5 shapes + named
   mechanic. (Round-1 added the Quantity but not the predicate — the b2a
   agent's UNCOVERED reason states exactly this.)
2. **Conditional cost modifier** — `CostModifier.condition: Filter|None`
   ("This spell costs {N} less to cast if you've gained N or more life this
   turn", B4 #147/#149; Discontinuity "During your turn, … costs less" is the
   turn-scoped variant) — 3 shapes + named mechanic. (Unconditional
   CostModifier landed round-2 already; the b4 UNCOVERED reason "No MODIFY_COST
   verb" is stale for these two — the missing piece is the CONDITION.)
3. **Additional cast cost** — `SpellAbility.additional_costs`
   ("As an additional cost to cast this spell, sacrifice a creature / discard a
   card" — Goremand, Sparkhunter Masticore, Thrill of Possibility, Village
   Rites; 4 shapes, hugely common cross-set; largest addressable chunk of the
   164-entry unparsed queue per the T5 handoff).
4. **Tap-state on zone entry** — optional `tapped_on_enter` role on
   MOVE_ZONE/SEARCH ("put that card onto the battlefield tapped" — Solemn
   Simulacrum, Fabled Passage, the "…then shuffle" search family; named
   mechanic, recurring).
5. **PC-6 orphan: PHASE_IN** — wire a template (Teferi "they can't phase in
   until the end of your next turn" via PREVENT_EFFECT(PHASE_IN) +
   DurationUntilNextTurn — verify composition) or deprecate the verb.

## Also (compiler-level, not grammar)
- **"If you search your library this way, shuffle."** ×6 (largest single
  unparsed family: Liliana's Scorn, Chandra's Firemaw, +4): generic MTG
  boilerplate for optional searches — extend the continuation rule to attach
  `SHUFFLE(LIBRARY)` to the preceding SEARCH in the same ability.
- **Ugin [−10] template FILTER BUG (real, in a COVERED shape):** "put up to
  seven permanent cards from your hand" encodes filter `FAnd()` = ANY card —
  missing the permanent-card restriction (creature/enchantment/artifact/land/
  planeswalker). Fix the b5c template filter.

## Next (sequencing)
1. Grammar round 2 (items d1-d5) — one `ultra`/`coder` task, additive-only,
   fingerprint-stability pinned.
2. Round-3 template wave per bucket for the newly-coverable shapes (+ Ugin [−X]
   verify + Ugin [−10] filter fix + "if you search this way" continuation rule
   as a separate compiler task).
3. Re-run `tools/measure_grammar.py` → new PC-1/PC-2.
4. T8 per-card translation for the residual (~150 shapes) — the (a) list is
   the triage input; T7's anti-poisoning gate repeats per card per the
   per-card protocol §3 (adversarial pass).
