# 131 — ZND-2g BINDING SPEC: face playability (owner law /130: "treat them how they work in real life") + pay-3-life lane

Date: 2026-10-19. **SPEC-AMENDED** after adversarial spec-gate (SPEC-NO-GO, 7 findings A1-A7);
re-gate required before dispatch. Owner ruling /130 §1 makes real-world CR-712 semantics the law
for this world. Wave structure changed by the gate (was 2 waves → 3) and D5's construct was found
not to exist — the honest path is a runtime wave, not a compile-time kludge.

## Ground truth (this world, executed)
36 ZNR MDFCs; ALL 36 backs are LANDS (deck-reachability CONFIRMED executed: deckable=267 includes
36/36 MDFCs, 36/36 surface in 200 seeded build_deck runs — no special fuzz mode needed, /131
census). Fronts: 23 spells, 8 creatures, 6 lands. Face sentences encoded since ZND-2f (`BackFace`;
61/71 compile; pay-3-life pair 5 cards/10 sentences residual). Engine today: front-only; back-face
CAST refused loud (`FaceCastAbsentError` /117); compile-side walk-consumers skip BackFace (/106).

## Real-world rules adopted (owner /130), gate fact-checked (A1 corrected R4)
R1. From hand, main phase, land play available: PLAY any LAND FACE of an MDFC (front or back; a
    both-faces-lands dual offers a genuine choice of which face enters). Land-play counter spent.
R2. CASTING touches only the front face (backs are lands; no compiled card grants land-casting).
    The /117 typed cast-refusal for land faces STAYS.
R3. A battlefield permanent has ONE ACTIVE FACE (the face it entered with); only its abilities run.
R4'. **(A1 + re-gate (iii))** The active face binds the permanent's **battlefield CHARACTERISTICS**,
    not merely its ability list: **type line, supertypes, P/T, COLORS, CMC, and name-for-search**
    are read from the ACTIVE FACE's compiled record, never the front. A back-land played from a
    creature-front MDFC is a LAND with NO P/T — cannot attack/block, `is_land` true, colored-mana
    identity/CMC reads return the LAND's values. The implementer MUST work the read-site appendix
    below (≥25 sites) — the two named originally are not the surface. Notably
    `quantity.py:737-750` is the LANDFALL runtime filter reading front `type_line` (templates_b7.py
    :120-137 builds the event): a back-played land MISSES landfall unless routed — landfall routing
    is a W1 acceptance item, not a follow-up.
R5. Off-battlefield (hand/library/GY/exile): card-identity predicates follow FRONT characteristics
    (name, type, HAS_KICKER /113, CMC). Active-face law binds ONLY on the battlefield.

## Design decisions (binding; gate-corrected)
D1'. **(A2)** Active face is RUNTIME state stored on the battlefield permanent record. The state
    FINGERPRINT (`state.py:266-273` `_stable_str` = oracle_id|name|tapped|counters) gains a face
    component CONDITIONALLY — present only when the card is a face-played MDFC — so two worlds that
    differ only in active face do NOT collide. Encoding is UNTOUCHED (serialize_card/golden/encoder
    bytes unchanged ⇒ M21 0-diff + corpus re-encode 0-diff hold). The active face rides the
    permanent + its ZONE_CHANGE as an **additive present-only trailing slot**, read with the
    existing len-tolerant `is_combat`-style convention; the implementer MUST update the 8
    zone_move unpack sites (`binding.py:1018,1057`; `quantity.py:1290,1337,1502,1751`;
    `executor/__init__.py:1013-1015`) so an added slot never crashes a frozen-era replay. FROZEN
    corpora (M21, episodes_v2, mtg_bot.db r20-era) contain no faces ⇒ byte-identical replay is the
    acceptance gate, not an assumption. **(ii) NORMALIZATION PIN (re-gate round 2 break #3):**
    the in-code field is `active_face ∈ {FRONT, BACK}`, NEVER None (single-faced and front-played
    default to FRONT). The fingerprint suffix is emitted iff the permanent is MDFC-backed AND the
    active face could be ambiguous — probe-proven requirement: a face=FRONT-marked record must hash
    EXACTLY as today (FRONT ≡ absent in the hash) so frozen bytes hold, while BACK must always
    suffix, and same-name dual faces must hash apart (a unit pin enumerates all three cases).
D2. PLAY LANE: the existing play-land surface gains per-legal-land-face candidates. Spell/creature-
    front (30) ⇒ ONE candidate (back land); both-lands dual (6) ⇒ TWO (front-land + back-land), the
    choice being the model-visible decision tracing to the BackFace node (§10). ONE candidate ⇒ no
    extra ask. Naming: `<card>:<face>` suffix, serializer-safe + unit-pinned.
D3'. **(A3)** COMPILE-SIDE folds stay FRONT-ONLY, unconditionally: `produces_mana`
    (`games.compile_supply:283-296`, deck-build time, no battlefield), `engine_support`
    (`compiler.py:2261-2302`), coverage PC-6/PC-8, HAS_KICKER (/113). **W1 touches NO compiler
    file.** The `test_backface.py:318-330` source-pins on literal `skip=BackFace` stay green. The
    active-face law is RUNTIME-ONLY (permanent characteristics + ability resolution).
D4. Entering-replacements fire for the played face (ZND-1e reused): "This land enters tapped"
    (25 faces) applies; pay-3-life applies after W3 (interim: D6).
D5'. **(A4) split into a compile wave + a runtime wave.** The construct does not exist today: no
    `IF_YOU_DONT`, no paid-at-ETB flag (`EtBState` `ability_tree.py:3091` takes a static Filter;
    the `kicked` paid-flag precedent `stack.py:123,730` is cast-time only). W2 (compile) folds the
    10 sentences into an EtBState-family node with an OPTIONAL-lifetime-payment gate shape; W3
    (runtime) implements the may-declaration ask, the payment journal row, the entering-replacement
    branch reading the paid flag, and the forced-tapped branch when unpaid. ANTI-SATISFICING
    GUARD (archetype 2): folding as an UNCONDITIONAL `EtBState(tapped=True)` would hit "exactly +10
    rows" while silently mis-semantizing all 5 cards (they'd enter tapped even when paid). W2's
    node MUST carry the conditional structure; a compile-only +10 with no W3 is a regression, not
    a win — therefore **W2 and W3 are one logical unit; W2 alone does not ship the 5 cards'
    correctness.**
D6'. **(A6)** W1 interim (before W3): a face-played pay-3-life back-land enters **FORCED TAPPED**
  (can't-pay⇒tapped is the conservative truth; entering untapped would hand random/teacher a
    rules-free advantage that pollutes BC data). Loud NUMBERS ledger line "pay3life forced-tapped
    until W3", removed by W3's commit.
D5a. **(A5)** The optional-payment ask is gated by `life >= 3` (`legality.py:41-46` already
    established `life >= amount`), NOT `life > 0`. life==3 is payable (pays to 0, enters untapped);
    life<3 ⇒ no ask, forced tapped (CR 118.1a / 119.3: can't pay life you don't have).
D7'. **(A7)** New candidate tokens UNK-degrade safely in the frozen clones (`bc_data_v2.py:383-430`,
    `ab_duel.py:355`) BUT UNK tokens remain scorable ⇒ "no misclick surface" is UNPROVEN. Before the
    /130 R1 duels that run frozen `bsh_S3a_s3_best` against ZNR decks, ship a **frozen-policy
    action-trace A/B pin**: same deck/seed with vs without face-play candidates present, assert the
    frozen policy's chosen action + scoring are unchanged (it must neither select nor be scored on
    a candidate it cannot represent). This is a W1 deliverable.

## Wave structure (gate-imposed round 2: W2+D6' interaction)
- W1 (executor/runtime, NO compiler): D1'-D4, D6'-forced-tapped, D7' pin + packs (back-land enters
  tapped; dual face-choice from hand; landfall fires on back face via read-site routing (iii);
  front-vs-back ability+characteristic scoping; cast-a-land refusal stays). Green standalone;
  31/36 fully correct, 5 pay-3-life forced-tapped (D6').
- W2+W3 = **ONE logical commit** (amendment (i), re-gate round 2 break #1: `_apply_etb_state`
  (executor/__init__.py:1047-1095) keys binder.records by FRONT oracle_id (faces share it) and
  evaluates node.condition via `eval_filter` which RAISES on unimplemented preds — a gate-bearing
  W2 node landing before W3 crashes/wrong-stamps EVERY ETB of all 36 cards, front casts included).
  Binding: either (a) W2 ships with the gate node INERT (`condition=None, tapped=True` = D6'
  semantics — register +10 but behavior unchanged) AND W3 flips it live in its own gated commit, or
  (b) W2+W3 land as a single commit. Variant (a) preferred (smaller commits, truth-law visible at
  W2); the W1+W2 overlap window's forced-tapped interim is owned by the NODE ITSELF (inert =
  unconditional tapped), not by a W1 field — D6' ledger line matches behavior automatically.
- Order: W1 ∥ W2(inert), then W3 (live gate; same files as W1). Each commit preceded by an
  adversarial diff-gate.

## Acceptance (per wave; executed, numbers pasted)
M21 PC-4 0-diff; corpus re-encode 0-diff; single-faced ZNR byte-identical; frozen replay
byte-identical (D1' A2 proof); full suite green; packs all green (+ new); fuzz BOTH eras 300+ 0
signatures (face-playable, MDFCs reach decks — census above); replay determinism green; D7'
frozen-policy A/B pin; §10 audit (static trace ↔ dynamic ask per new ask); pyright 0 new, ruff Δ0.

## Non-goals
transform/leaves-battlefield face changes (no compiled card); copying; face-play from non-hand
zones (no compiled card); day/night (absent in world); casting back faces (R2); command-zone.

## D7' procedure pin (re-gate (iv)): NO bespoke pack — existing rig: seeded `build_deck` (deckable
267 incl. 36/36 MDFCs) + seeded 7-card draw (`games.py:1089`) + `ab_duel.allocate_seeds` disjoint
banks (`duel_seeds.json`); seed-scan procedure: iterate seeds until one draws an MDFC to hand with
a land play available pre-action, pin (seed, deck-id, draw-index) as constants in the test, run the
frozen policy A/B (candidates present vs masked), assert identical chosen action + score.

## READ-SITE APPENDIX (re-gate round 2 break #2) — battlefield-permanent characteristic reads to
route through ACTIVE FACE (W1 checklist; verify each takes a battlefield permanent, not a
compile-side record; `games.py:294` and `stack.py:234` are compile/cast-side — OUT of scope, they
gate deck-legality/cast-legality on front and MUST NOT gate D2 face-plays):
quantity.py:331, 353, 458, 720, 737-750 (LANDFALL), 762, 826, 835, 856, 870, 906, 918, 1248, 1474,
1502*, 1290*, 1337*, 1751* (*=zone_move len-tolerant unpacks, D1'); stack.py:234 (out of D2 scope
— cast-side, keep front); durations.py:291; layers.py:937; executor/__init__.py:1013-1015* , 1139,
1170, 2021, 2095; games.py:542, 760, 794, 861, 1031, 1107; verbs.py:1546; events.py:523-537 + DIES
snapshot. The implementer treats this list as a floor, not a ceiling: grep-verify `type_line|
is_land|is_creature|\.power|\.toughness|cmc|color_identity` over battlefield-typed args completes
the surface; every routed site gets a unit pin only for the BACK-active case (FRONT-active must be
byte-identical by construction).
