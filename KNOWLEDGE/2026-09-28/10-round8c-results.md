# 2026-09-28 /10 — Grammar round 8-C: coverage batch (results)

Phase 8-C of `/08-grammar-round8-decision.md` (mission §8-C + analyst families D1/D5 of
`/03`). Consumes the R8-6/7/8/10/11 primitives landed in 8-A and pays down the coverage
queue. Zero grammar edits (`ability_tree.py`/`compiler.py` untouched); unexpressible rows
were withdrawn with named R9 items. No commit (owner gate).

## Headline numbers (see NUMBERS.md blocks, `tools/measure_grammar.py --set M21`)

| gate | pre | post | band/limit |
|---|---|---|---|
| PC-1 card_coverage | 274/305 | **287/305** (+13) | 285–292 ✓ |
| PC-2 sentence_coverage | 599/639 | **618/639** (+19 exact) | 617–622 ✓ |
| PC-3 ambiguity | 0 | **0** | hard ✓ |
| PC-4 golden_stability | 0 → 14 expected diffs | **0 verified** | hard ✓ |
| PC-6 orphans | 3 (GET_EMBLEM, ADD_LAND_PLAY, PHASE_IN) | **1 (PHASE_IN)** | →1 ✓ |
| unparsed queue | 40 | **21** | 19–21 ✓ |
| PC-8 targetable | 96/305 | 97/305 | standing FAIL (new TARGETs, allowed growth) |
| PC-5 / PC-9 / PC-10 | ok | ok / stable / exact | ✓ |

- Suite `MTG_bot/core` **1521 passed** (counts: b5c 79→84 tids & SHAPES 80/11→87/4;
  b5b 69→75, SHAPES 79/12→85/6; b4 38→43 templates, EXPECTED_KIND 39→44, UNCOVERED
  9→4; b3 28→29, UNCOVERED 2→1).
- pyright 0 errors on all touched files; ruff delta 0 (24 pre-existing TRY004 in
  `test_templates_b4.py` at HEAD — untouched).
- `tools/gen_buckets.py`: pins **B3 46→47, B4 38→43** (dated r8-C); all 8 bucket JSONs
  regenerate **byte-identical** (cmp) — b3/b4 clean pattern↔UNCOVERED swaps, b5 modules
  don't feed the partition.
- Golden audit vs `/tmp/golden_pre_r8c_2026-09-28`: exactly **14 files changed, diff-key
  set = {abilities} only** (⊆ abilities/keywords/emblem; emblem attaches byte-stable).

## Landed ledger (19 shapes / 17 templates / 14 cards)

| shape | tid | module | card | C16 decision surface | lossy note |
|---|---|---|---|---|---|
| `[−N]: You get an emblem with "…"` ×3 | `B5c-get-emblem` (ONE template) | b5c | Basri Ket / Liliana Waker / Garruk Unleashed | none (inner decisions live in the emblem's own tree) | none — C19 marker (GET_EMBLEM role-less, FLIP_COIN idiom; inner text NEVER in payload; attach = compile_pool two-pass) |
| `[−2]: Whenever one or more nontoken creatures attack…tapped and attacking` | `B5c-loyalty-soldier-attack-tokens` | b5c | Basri Ket | [−2] pay; attacker set (THAT_MANY_COUNT open) | none (r4-C3 self-grant + DurationEot; IS_TOKEN FNot filter; TokenSpec W + enters flags R8-2/4) |
| `Until end of turn, you may cast spells from your hand without paying…` | `B5c-waive-cast-from-hand` | b5c | Chandra, Flame's Catalyst | whether/which/how many from hand | duration (no CAST duration role); PW-sibling assembly note |
| `Until end of turn, you may play cards exiled this way.` | `B5c-play-cards-exiled-this-way` | b5c | Chandra, Heart of Fire | whether/which exiled cards | "play"→CAST (lands); duration |
| `This ability costs {1} less to activate for each Shrine you control.` | `B5c-shrine-activation-cost` | b5c | Sanctum of Tranquil Light | none | "to activate" scope = sibling-adjacency executor convention (R9: ability-scope filter) |
| `If it was a creature card, put a +1/+1 counter… and you gain 1 life.` | `B5b-if-was-creature-counter-gain` | b5b | Scavenging Ooze | none (type gate is game state) | none (C18 via if-it-type-then subject convention — see PITFALLS) |
| `Target player draws cards equal to half… and loses half their life.` | `B5b-peer-half-library` | b5b | Peer into the Abyss | target choice (s1 elsewhere) | **life-half loss dropped** — no life-total Quantity exists (R9: QPropField.LIFE); draw half = (n+1)//2 over QCount(LIBRARY, TARGET_PLAYER) |
| `Round up each time.` | `B5b-peer-round-up-each-time` | b5b | Peer into the Abyss | none | RuleReminder('rounding_directive') — rounding already baked into s1's (n+1)//2; Double Vision consumption precedent |
| `Put a +1/+1 counter…, then double the number of +1/+1 counters…` | `B5b-double-counters-target` | b5b | Invigorating Surge | target creature | none (step 2 adds QProp(target, COUNTER_COUNT) — the doubling; R8-11) |
| `Then if an opponent controls more creatures than you, put a loyalty counter on Garruk.` | `B5b-then-if-opponent-more-creatures` | b5b | Garruk, Unleashed | none | none (CONTROLLER_COUNT_GT dual-filter R8-9; merges into the [−2] ActivatedAbility via default continuation) |
| `It gains haste."` | `B5b-gains-haste-emblem-residue` | b5b | Liliana, Waker of the Dead | none | RuleReminder('emblem_text_payload_attached') — C19: grant already compiled inside the attached emblem (B5b-it-gains-haste); base-card re-grant would duplicate payload |
| `You may cast them this turn.` | `B4-cast-them-this-turn` | b4 | Chandra, Heart of Fire | whether/which exiled | duration; register selector QConst(1) pinned by C2 validation (plural executor-side); waiver Cost(()) |
| `You may look at the top card… any time, and you may play lands from the top…` | `B4-look-play-top-of-library` | b4 | Radha, Heart of Keld | look? play? (TWO independent Optionals in one Seq — C15) | LOOK_AT has no zone role (top implicit, Sasaya precedent); land-play→CAST |
| `You may play that card until you exile another card with this enchantment.` | `B4-play-that-card-until` | b4 | Furious Rise | whether to play | until-next-event duration dropped (R9); play→CAST; register QConst(1) |
| `You may play two additional lands on each of your turns.` | `B4-azusa-extra-land-plays` | b4 | Azusa, Lost but Seeking | whether to use extra plays | none (ADD_LAND_PLAY consumed — orphan→PHASE_IN only; "two" word-pin C14; DurationPermanent) |
| `This spell costs {X} less… noncombat damage dealt to your opponents this turn.` | `B4-noncombat-damage-cost-modifier` | b4 | Chandra's Incinerator | none | QThisTurn(NONCOMBAT_DAMAGE, ALL_OPPONENTS) — R8-10 grounding reads the referent dealt-BY, print is dealt-TO; no recipient quantity (R9 note in docstring) |
| `{1}{W}, {T}: Until end of turn, you may cast a creature spell from among cards exiled with this artifact without paying its mana cost.` | `B3-idol-cast-exiled-creature` | b3 | Idol of Endurance | activation; whether/which creature | duration; stale b3 UNCOVERED note (R8-6 shipped the predicate; waiver = Cost(())) |

**Full-card unlocks (PC-1 +13)**: Ooze, Peer, Invigorating Surge, Garruk Unleashed,
Basri Ket, Sanctum, Catalyst, Heart of Fire, Radha, Furious Rise, Azusa, Incinerator,
Idol. **Not** unlocked: Liliana Waker (`Each opponent who can't loses 3 life.` anaphoric
capability-inspection stays queued — R9), Teferi, Snoop, Kraken (withdrawals below).

## Withdrawals (3 shapes stay queued; named R9 items)

- `When you do, you may tap or untap target creature.` (Tolarian Kraken, b2b) — 8-C
  re-check: the default continuation merge appends the tap/untap as an INDEPENDENT
  sibling Optional (not gated on the antecedent "you may pay {1}") — C15 violation; no
  paid-cost predicate/payment-event class exists. **R9: do-continuation merge for
  optional PAY / PaidCostEvent.** b2b UNCOVERED reason updated with this verdict.
- `You may activate loyalty abilities of Teferi…` — no ACTIVATE-permission node exists
  anywhere in the vocabulary (CostModifier gates costs, ActivationGateOutcome gates its
  own ability); a NAME_EQ("Teferi") filter has nothing to attach to. **R9: loyalty-
  activation permission verb + activation-window widening.** b4 UNCOVERED reason updated.
- `Play with the top card of your library revealed.` (Snoop, B5b bucket — mission's
  b5c guess corrected by bucket truth) — REVEAL is an event verb (controller+count);
  no continuous zone-revealed state. **R9: continuous revealed-zone-state.**

## Mission corrections & deviations (documented, not silent)

1. **Bucket ownership beats mission tid guesses**: `It gains haste."` and Snoop topdeck
   are B5b-bucket keys (gen_buckets partition) → b5b module, not b5c.
2. **C2 validation** rejects a QUnbounded referent selector (construction-time) →
   cast-them carries QConst(1) + documented plural executor reading.
3. **C18**: TYPE_EQ cannot carry referent="result" (FAtom rules close the slot) → the
   landed if-it-type-then subject-register convention encodes it; semantics (value-at-
   antecedent snapshot) recorded in the builder docstring.
4. **Emblem pattern** cannot require the closing quote (Liliana's row is split without
   it) → `".+$`.
5. **Peer life-half** and **Incinerator dealt-to/by** landed partial-lossy per C11
   class (verbatim notes); **Sanctum "to activate"** scope is executor-adjacency —
   each is the closest honest encoding without grammar surgery.

## Skips & out-of-scope (unchanged in queue)

- Harbinger of the Hunt, topdeck permission — NOT in queue (landed r7-A as
  B4-reveal-one-from-among): skip recorded.
- F-MANA family (Vodalian restriction, Orrery color-flooding) — owner-registered R9.
- Remaining 21 shapes = 3 withdrawals + 18 registered-family rows (activation gates ×2,
  ability-grant family ×2 + Snoop topdeck counted above, anaphoric-capability ×1,
  additional-trigger ×1, Transmogrify ×2, Frost Breath, Pursued Whale, Chrome
  Replicator, Mangara, Enthralling, Savage Herald embedded-replacement, Orrery
  each-color draw, Subira delayed trigger, Vodalian, search-shuffle note row).

## R9 census (post-8-C queue, by family)

| family | shapes | notes |
|---|---|---|
| ability-introspection/grant | 4 | Snoop grant, topdeck state, Drowsing, "Each opponent who can't" |
| activation legality | 2 | Activate only as a sorcery / life-gate variant |
| mana policy (F-MANA) | 2 | Vodalian, Orrery flooding |
| embedded/delayed triggers | 2 | Savage Herald [−7] replacement text, Subira grant |
| additional-trigger | 1 | Sanctum of All |
| search-until / modal continuation | 2 | Transmogrify pair |
| set-comparison triggers | 3 | Chrome Replicator, Mangara, Frost Breath untap-prevention |
| targeting legality / copy retarget | 1 | Enthralling |
| distinct-color count | 1 | Orrery draw-per-color |
| PAY do-continuation | 1 | Kraken |
| loyalty-activation permission | 1 | Teferi |
| (bookkeeping) search-shuffle conditional shuffle | — | compiler built-in; UNCOVERED note |
