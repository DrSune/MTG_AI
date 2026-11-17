# 210 — Component sharing review: are the components shared as much as they can be?

**The owner (2026-11-17):** "A review of whether our components are optimal to ensure shared learning
is maximized, is also warranted. The remaining cards are likely complex, so optimizing their sharing
of existing components is beneficial both for the components count and learning."

Why it matters: King goal 1b (an unseen card built from practised primitives plays well on day one)
and the owner's learning vision (generalise through components, never memorise names). A component on
many cards is learned from many games; one on one or two cards is learned from almost none; two
encodings of one meaning split the evidence between them. K1b measured the payoff: cards whose atoms
all appear on training cards gained +0.241 from volume (KNOWLEDGE/2026-10-27/166).

Analysis only: no IR, code or record changed. Scripts and outputs: `reports/component_review_2026-11-17/`
(`run_all.sh` regenerates every number below; the README there maps scripts to sections). Base:
main b1d61997 (R11 merged, the reprint wave stamped). r28's v2 checkpoint was read once, on the CPU.

## 0. The numbers first

| | verified M21+M20+FDN | every compiled tree, 19 sets |
|---|---|---|
| cards (one row per oracle id) | 651 | 4,314 |
| distinct component tokens | 610 | 857 |
| tokens per card: mean / median / p90 / max | 72 / 63 / 135 / 326 | 29 / 12 / 71 / 326 |
| cards past `max_ir` = 128 (tokens cut) | **79, 12%** (3,736) | 116, 2.7% (5,640) |
| tokens on 1-2 cards | 208, 34% of the vocabulary (0.7% of uses) | 311, 36% |
| share of a card's bag that is `@field` keys | 39% | 31% |
| share taken by tokens on half or more of the cards | **58%** | |
| cards with 2+ different number tokens (unbound in the bag) | 38% | 16% |
| cards with 2+ abilities (mixed in one bag) | 25% | 8% |

- **The compiler is consistent per wording.** Among the 1,959 sentences of the 19 sets that a template
  parses on its own (626 slot shapes: numbers, colours, card types and the card's own name freed), no
  two sentences one slot word apart get two encodings, except colourless mana (a value the script did
  not free) and a template that writes the card's own name (§2.2). Whole cards with the same text up to
  slot words differ only where they should (instant against sorcery, a back face).
- **The duplicates are across templates and records.** 14 classes that the divergence ledger, the
  BACKLOG and the IR's own conventions name are still open (§2.1), and the review finds four more: "this creature" as an effect's object (57 trees in a second
  form), the number of cards in a zone, a planeswalker type written as a name, and a card's own name
  inside its tree. With the over-specific families, folding them touches 258 trees.
- **The tail is over-specific predicates.** 24 of the 76 rare non-value components are a composition
  of existing tokens (11) or an existing token plus a parameter (13): mostly the threshold comparators
  and the turn-history predicates, which B-44 named in October and which still stand (§1.4, §3).
- **The largest sharing losses are on the network side.** The card is a mean over its tokens: 58% of
  the mean is tokens most cards carry, numbers do not say what they count, 12% of verified cards are
  cut at 128 tokens (33 verbs lost outright, emblems and ultimates among them), and "Elf" in a lord's
  filter is a different token from "Elf" on an Elf's face (52 such values, on 396 verified cards).
- **The remaining cards mostly need templates, not components.** Of the 389 unverified cards of M21,
  M20 and FDN, 235 (60%) need only templates over existing components (or only a verification); 43
  parameters bring that to 314 (81%), three engine lanes to 324, and four new components (copy, a play
  permission, flashback, the opening hand) to 357 (92%). 146 of them print a form one of the IR
  proposals folds.

## 1. The vocabulary as the network sees it

### 1.1 What the network reads
`features.card_tokens` (features.py:202) is the face (`type:`, `sub:`, a mana-value bucket `mv:`)
plus `ir_tokens` (features.py:211): a pre-order walk of the tree's `to_dict` that emits every tag
(`Atom`, `Selector`), enum value (`Verb.DESTROY`), field key (`@filter`), role (`role:target`),
string (`str:Creature`), bool and number. Numbers are tokens only: `num:0` to `num:5`, `num:6+`,
`num:neg`, one token per bucket in every role. `CardTable` keeps the first 128 ids; the model embeds
each id (`ir_emb`) and takes the mean (`card_table_emb`, model.py:98), added to the name embedding and
the live state (`card_f`: P/T, damage, counters, keyword flags for 20 keywords, colours, types).

### 1.2 Sizes and the histogram (`vocab.txt`)
Cards per token, verified (651 cards, 610 tokens): 1 card 146 tokens, 2: 62, 3-5: 88, 6-10: 61,
11-20: 65, 21-50: 71, 51-100: 43, 101-500: 63, 501+: 11. Over the 19 sets (857 tokens): 252, 59, 92,
93, 73, 86, 55, 97, 50. 247 tokens of the 19 sets are on no verified card (121 face values, 114
strings); 555 compiled cards hold one.

### 1.3 The live network's table (`checkpoint_table.txt`, r28 v2: d 512, 8 layers)
611 card rows, 590 component tokens, 58.9 tokens a row, 61 rows at 128. 58 rows differ from today's
compile (a `--refresh-table` rebuilds them). Seven component rows are exactly zero: added after the
start and never trained. Embedding norm by how many rows carry the token: median 0.59 on one row,
0.63 on two, 0.67-0.70 on 3-100 rows, 0.56 on 101 or more (an untouched N(0, 0.02) row is 0.45, a
row `extend_cards` added starts at 0). The one-card tokens sit nearest their starting scale among the
informative ones; the most common tokens, mostly boilerplate, are the smallest.

### 1.4 The tokens 1-2 verified cards use (`rare_classify.txt`)
208 tokens: 76 components and 132 values.

| what they are | n | could be shared? |
|---|---|---|
| composition of existing tokens | 11 | yes: CARDS_DRAWN_THIS_TURN_GE, CAST_THIS_TURN_FROM, ENTERED_THIS_TURN_FROM, INSTANT_OR_SORCERY_CAST_THIS_TURN, NOT_FIRST_DRAW_THIS_STEP, QThisTurn and its kind (EVENT_THIS_TURN over an existing event); CONTROLLER_COUNT_GT; QPropField.CARDS_IN_HAND / CARDS_IN_GRAVEYARD (a QCount over the zone); BecomesBlockedEvent (a candidate: DeclareBlockersEvent with `blocked`, once per creature, CR 509.3c, needs a CR reading) |
| an existing token + a parameter | 13 | yes: CMC_GE, POWER_LE, COLOR_COUNT_GE, LIFE_TOTAL_GE, LIFE_LEAD_OVER_START_GE, NAME_PARTITION_COUNT_GE (one quantity comparison); ATTACK_POLICY, DAMAGE_ASSIGN_POLICY, GRANT_ACTIVATION, MANDATE_BLOCK (a scope); QDistinctColorCount (a property slot); PhasingEvent (ledger F10); IS_ATTACHED_TO (the general form of the frequent IS_ATTACHED_TO_SOURCE) |
| a distinct rules action or value | 40 | keep: EXTRA_TURN, END_TURN, LOSE_GAME, FLIP_COIN, PHASE_OUT, TRIGGER_ADDITIONAL, ADD_LAND_PLAY, REMOVE_COUNTER, events, durations, counter kinds, cost deltas |
| a field or role that goes with its node | 12 | goes with its node |
| a face type or subtype | 72 | 28 have a filter twin (`str:`), shared under N3 |
| a type or subtype in a filter | 29 | all have a face twin, shared under N3 |
| a card name | 21 | references (I5, N2) |
| a scope or quality value; other | 10 | values of existing verbs |

So **24 of the 76 rare components (32%)** fold into existing ones, and 57 of the 132 rare values
would share an embedding with a twin they already have.

## 2. Duplicated meaning (`duplicates.txt`)

### 2.1 The ledger's open classes, measured
Trees are distinct oracle ids of the 19 sets with records applied; stamps are verified home stamps
(M21, M20, FDN) plus reprint stamps.

| class | side A (trees, stamps) | side B (trees, stamps) | CR reading | fold |
|---|---|---|---|---|
| D12 SEARCH.controller | left out: 18 (17+1) | written: 11 (8+6) | the searched zone is the selector's (CR 701.19); the role is never read | drop the role: 11 trees |
| D13 a cost victim's mode | CHOOSE: 71 | TARGET: 3 (2+0), ALL: 1 (1+0) | costs never target (CR 601.2c, 601.2h) | CHOOSE: 4 trees |
| D14 Planeswalker | TYPE_EQ: 112 | SUPERTYPE_EQ: 2 (2+0: Hooded Blightfang, Liliana's Scrounger) | a card type, CR 300.1 | TYPE_EQ: 2 |
| D18 "its controller" | referent Selector | TARGET_PLAYER with no printed target: 1 (2+0, Massacre Wurm) | not a target, CR 115.1 | referent: 1 |
| D19 library, no position | BOTTOM 12 | no position: 2 (2+0) | two meanings, one form | BOTTOM: 2 |
| D21 "each opponent <verb>s" | plural controller: 18 | EachPlayer around one atom: 9 (8+1) | one instruction, CR 101.4 | 5 rewritten |
| D22 "as long as" | static condition: 18 | DurationWhileCondition: 5 (5+0) | CR 611.3a | condition: 5 |
| D23 one static's grants | sorted: 3 | printed order: 5 (1+0) | one timestamp, CR 613.7 | sort: 5 |
| D25 "this" in a cost | IS_SOURCE alone: 18 | FAnd(CONTROLLER_IS YOU, IS_SOURCE): 19 (22+9) | the activator controls the source, CR 602.2 | IS_SOURCE: 19 |
| B-42 MOVE_ZONE's objects | `cards`: 135 | `target`: 61 (32+9), every move to exile but one | one role, one meaning | `cards`: 61 |
| B-44 turn history | EVENT_THIS_TURN 24, SUBJECT_OF_ 5 | legacy predicates: 27 (25+0) | the same journal question, except per-individual thresholds in multiplayer and DIED_THIS_TURN's fallback (B-44) | 27 |
| B-48 discard | MOVE_ZONE hand to graveyard: 37 | Verb.DISCARD: 1 (0+0, Coralhelm Chronicler) | CR 701.8a; the trigger needs a DiscardEvent anyway | drop the verb: 1 |
| "N or less" | FNot(GE): Gadrak, Liliana (and LIFE_TOTAL_GE's convention) | POWER_LE 5, CMC_LE 7 (8+0) | integers: N or less = not N+1 or more | I1 |
| F13 a colour chosen at resolution | CHOOSE_NAME(COLOR) as it enters: 4 | Choose over five: 2 (2+0: Gods Willing, Feat of Resistance) | the same choice (CR 607.2d) by context | with Crippling Fear |

### 2.2 New classes found (to register as D27-D30 by the round that folds them)
- **D27 "this <permanent>" as an effect's object.** CHOOSE + QConst(1) + IS_SOURCE in 181 trees (82
  home + 19 reprint stamps), every verb on the source (ATTACH 102 atoms, PUT_COUNTER 41, MODIFY_PT 34,
  GRANT_ABILITY 18...); ALL + QConst(1) + FAnd(CONTROLLER_IS YOU, IS_SOURCE) in 52 (15 + 7): the
  activated self-pump ("{R}: this creature gets +1/+0", "... gains flying"; M20/FDN Shivan Dragon,
  Hellkite Punisher), 55 atoms, where the triggered and static wordings of the same pump use the first
  form (52 atoms); CHOOSE + FAnd(...) in 5 (4 + 0). The ALL form looks like an anthem ("creatures you
  control get") in the bag, and it is not quite the same rule: `CONTROLLER_IS YOU` is judged against the ability's controller at
  resolution (selectors.py:206), so a pump whose source changed control in response does nothing,
  where the printed "this creature gets +1/+0" applies to the creature (only its controller may
  activate it, CR 602.2, but the text asks for no control at resolution). A corner case, but the
  majority form is the printed one.
- **D28 the number of cards in a zone.** QProp(controller, CARDS_IN_HAND / CARDS_IN_GRAVEYARD) on M21
  Jolrael and Liliana, Waker of the Dead (2 stamps), QCount over a zone selector elsewhere (M21 Peer
  into the Abyss's library, 10 counts over your graveyard). QPropField.CARDS_IN_LIBRARY and CMC are
  unused twins.
- **D29 a planeswalker type written as a name.** "A Garruk planeswalker" is a subtype (CR 205.3j):
  SUBTYPE_EQ on 5 trees (5 stamps: Chandra's Embercat, Keral Keep Disciples, Predatory Wurm, Vivien's
  Crocodile, Celestial Messenger), NAME_CONTAINS on 5 (4 stamps: Adherent of Hope, Garruk's Harbinger,
  Historian of Zhalfir, Liliana's Scrounger; ZNR Nissa of Shadowed Boughs). Same play in the 19 sets,
  different bytes, and only SUBTYPE_EQ shares its value with the face token `sub:Garruk`.
- **D30 a card's own name in its tree.** "Cards named ~" as NAME_EQ with the card's name: 6 trees
  (6 + 2 stamps: Frantic Inventory, Battalion Foot Soldier, Faerie Miscreant, Growth Cycle, Pack
  Mastiff, Undead Servant). The party template (B8-party-class-signature) writes FAnd(IS_SOURCE,
  NAME_CONTAINS <own name>) on 3 ZNR trees: the name check repeats IS_SOURCE and splits the three
  cards' trees. A name token is learned from one card by construction.

## 3. Over-specific atoms (`inventory.txt`)
- **Threshold comparators**: POWER_GE 17 trees, POWER_LE 5, CMC_LE 7, CMC_GE 1, COLOR_COUNT_GE 2,
  LIFE_TOTAL_GE 3, LIFE_LEAD_OVER_START_GE 2, CONTROLLER_COUNT_GE 29, CONTROLLER_COUNT_GT 1,
  ZONE_COUNT_GE 5, NAME_PARTITION_COUNT_GE 1, and the unused PT_LE, PT_GE, CONTROLLER_COUNT_LE. Each
  is "a quantity of the subject or of the board, at least N": QProp (POWER, TOUGHNESS, MANA_VALUE,
  LIFE) and QCount already name the quantities. The remaining cards need toughness (Valorous Stance,
  Thunderkin Awakener), total power (Surrak), the starting life (Ayli, Elenda; ledger F11) and another
  player's life (Hidetsugu's Second Rite): four more predicates without a general comparison, none
  with one.
- **Turn history**: DIED_THIS_TURN 10, LIFE_GAINED_THIS_TURN_GE 4, MOVED_TO_ZONE_THIS_TURN 4,
  CARDS_DRAWN_THIS_TURN_GE 2, CAST_THIS_TURN_FROM 2, NOT_FIRST_DRAW_THIS_STEP 2,
  ENTERED_THIS_TURN_FROM 1, INSTANT_OR_SORCERY_CAST_THIS_TURN 1, ATTACK_AGAINST_COUNT_GE 1 and
  QThisTurn 1, beside the general EVENT_THIS_TURN (24) and SUBJECT_OF_EVENT_THIS_TURN (5) that B-44
  says should replace them. WAS_CAST_THIS_TURN stays (B-44: only it follows the spell, CR 400.7c).
- **One-case nodes the remaining cards need general**: TARGETS_SOURCE (4 trees) tests one object;
  five remaining cards need "a spell that targets you / a creature you control / a tapped creature".
  QDistinctColorCount (2) counts colours; six need distinct mana values, costs or names.
- **Policies**: MANA_POLICY 3, DAMAGE_ASSIGN_POLICY 1, ATTACK_POLICY 1 (ledger F9: one POLICY verb
  with a scope before a fourth), MANDATE_BLOCK 2 beside MANDATE_ATTACK 5. Waiting: "as though it had
  flash" (3 cards), toughness damage (Gauntlets of Light), lure (Prized Unicorn).
- **The other direction**: IS_ATTACHED_TO_SOURCE (125 trees) is IS_ATTACHED_TO (3) with the source as
  its referent. The frequent one is the special case; folding it re-bakes 35 stamps for little
  sharing (it is well trained). Not recommended now.
- **Dead enum members**: 28 members no tree uses. Some wait legitimately (QPropField.TOUGHNESS,
  QBinOp.SUB, SelectorMode.RANDOM, IS_BLOCKING, which "attacking or blocking" needs). Others are second
  encodings in waiting a mapper can pick: Verb.EXILE and Verb.MILL (MOVE_ZONE's), Keyword.MILL and
  Keyword.SCRY (keyword actions, not abilities), Keyword.BATTALION (an ability word),
  QPropField.CMC (MANA_VALUE's twin, CR 202.3), PT_LE, PT_GE, CONTROLLER_COUNT_LE,
  ThisTurnKind.CARDS_DRAWN and LIFE_GAINED. Removing them changes no tree.
- **What is fine**: the 13 verbs on 1-2 cards are mostly distinct rules actions (extra turn, end the
  turn, lose the game, flip a coin, phase out, an additional trigger); the frequent verbs and the
  selector already carry the sharing ("destroy | exile | bounce | tap | pump" over one Selector shape).

## 4. Structure the network cannot share (`network.txt`, `proposals.txt`, `pool_check.txt`)
- **"Destroy target creature" and "destroy target artifact" share 28 of 30 tokens** (M20 Murder, M10
  Shatter): they differ in `str:Creature` / `str:Artifact` and the mana-value bucket. So "destroy" and
  "target" are shared. But 18 of the 30 are field keys or carrier tags (`@args`, `AtomArgs`,
  `Selector`, `@zones`), and the distinguishing token is 1/30 of the mean. A token's embedding gets
  its card's gradient in proportion to its share, so a verb on a 72-token card learns at 1/72 of it.
- **Dilution**: field keys are 39% of a verified card's bag; 72 tokens are exact copies of another
  (the same count on every compiled card: `@args = @verb = Atom = AtomArgs`, 2,642 uses each;
  `@mode = @zones = Selector`, 1,708), 16% of a verified bag. Without the 80 field keys and 38 copies a
  verified card is 41 tokens (median 36), and only 6 verified cards pass 128 (79 today).
- **Numbers are tokens, not values, in the components** (values only in the live state and the
  options). One `num:2` serves damage, cards, counters and P/T, and the bag does not say which
  number goes with which role: 38% of verified cards carry two or more. The one exact collision:
  10E Holy Strength (+1/+2) and Unholy Strength (+2/+1) are the same bag. Among verified cards the 647
  distinct meanings give 647 distinct bags (also truncated, also as means), so the loss is resolution,
  not identity. `num:6+` merges every number from 6 up.
- **Ability structure is not visible**: 25% of verified cards have two or more abilities; which
  trigger a token belongs to is lost. K1b found no gain from parent>child pairs (-0.024
  [-0.059, +0.033]) and K1c a flat transformer over the IR worse than the bag (-0.083
  [-0.132, -0.007]) at up to 556 cards (KNOWLEDGE/2026-10-27/166), so structure is a measured bet, not
  a known loss.
- **Truncation**: 79 verified cards (12%) lose 3,736 tokens. Keywords come last (`{"abilities",
  "keywords"}`), so 36 lose keyword tokens (20 keywords also have a `card_f` flag; EQUIP does not).
  33 verb-card pairs are lost outright: Basri Ket's, Garruk, Unleashed's and Liliana, Waker of the
  Dead's GET_EMBLEM, Garruk, Savage Herald's DAMAGE_ASSIGN_POLICY, Sanctum of All's
  TRIGGER_ADDITIONAL, Feline Sovereign's DESTROY, Niambi's DRAW. Long trees come from expansions:
  Gods Willing's colour menu repeats its subtree five times (232 tokens), Goldmane Griffin's "library
  and/or graveyard" three times (187), and every Equipment's Equip reminder is a 56-token activated
  ability.
- **Names inside components**: a back face's name is tokenised (`@face_name str:<name>`, 87 trees of
  the 19 sets, none verified), against `ir_tokens`' own docstring; D30's own names; 11 verified trees
  name another card (Goldmane Griffin's "Ajani, Inspiring Leader").
- **One value, two tokens**: a face's `sub:Elf` and a filter's `str:Elf` are different embeddings,
  so an Elf lord's filter and an Elf's face share nothing. 52 values are both (Creature, Elf,
  Goblin, Dragon, Garruk...), and 396 verified cards (61%) name one in a filter. R9-2 chose the face
  token for a chosen creature type for this reason (C_CHOSEN). `SpellKind.CREATURE` beside
  `type:Creature` on 610 cards is a third token for one fact.

## 5. The remaining cards (`remaining.txt`)
389 unverified cards (FDN 311 partly compiled, 7 needs-atom, 5 refused, 4 others; M20 48 needs-atom,
4 others; M21 10 compiled), 618 unparsed sentences on 366 of them. 16 have no unparsed sentence and
need only a verification (12 compiled whole, 4 mapped); the 7 refused are classed by their refusal
(4 activation gates whose ability did not parse, 2 readers of a chosen creature type, 1 Vehicle's
crew). Each sentence was classed by a lexicon (`remaining.RULES`, from the needs-atom notes and the
IR's vocabulary), and the 429 left as "templates only" were read once by hand. It is an estimate;
note 209 (the census) has per-card needs.

| a sentence needs | sentences | cards whose worst need it is |
|---|---|---|
| templates over existing components (or nothing) | 429 (69%) | 235 |
| an existing component + a parameter (43 distinct) | 101 (16%) | 79 |
| an engine lane on an IR shape that exists (3) | 12 (2%) | 10 |
| a new component (28 distinct) | 75 (12%) | 65 |

Cards whole: templates only 235; with the 43 parameters 314; with the three lanes 324; with the four
largest new components 357 (copy of a spell, ability or permanent: 13 cards waiting; a play
permission for exiled cards: 10; flashback: 8; the opening hand: 6); the other 24 new components
are one to three cards each (alternative costs, punishers, piles, SET_LIFE, SET_COLOR, an extra
combat, crew...). The largest parameters: ward and surveil (6 each, both compositions of existing
atoms), distinct counts (6), "the same name as" (5), a targets(filter) predicate (5), "activate only
once each turn" (5). 11 of the 43 parameters fall under I1, I5, I6 and I9 below. 146 remaining cards
print a form an IR proposal folds: mapped first, they would be mapped twice.

## 6. Proposals

### 6.1 Network side: how cards are tokenised and encoded (no IR change, no stamp re-bakes)
No ontology round; each is a network change checked as R9-2 checked its columns (old checkpoint,
tokens, logits and values bitwise on recorded decisions) with a fresh-eyes review.

| # | change | gain | old checkpoints |
|---|---|---|---|
| **N1** | Pool by a count matrix: `card_emb = (C @ ir_emb) / n`, C the per-row token counts, no `max_ir` cut | 79 verified cards (12%) get their 3,736 cut tokens back, 33 lost verbs among them; the pool writes 0.31M values a forward where the gather moves 40M (611 x 128 x 512) | **the same function on every row within 128**: max diff 1.1e-8 against `card_table_emb` on r28 v2; 77 long rows change (+37 a refresh changes anyway) |
| **N2** | Token hygiene in `ir_tokens`: skip `face_name`; write the card's own name as `str:~` | 87 back faces lose a one-card token; "cards named ~" is one token on 6 verified cards (more with Hare Apparent) | changes only those rows |
| **N3** | One value, one vector: a value table shared by `type:X`, `sub:X`, `str:X` and `SpellKind.X`, added to each token's embedding, initialised at zero (every row, padding too) | an Elf lord's filter and every Elf's face share "Elf"; 52 values, 396 verified cards (1,125 over the 19 sets); an unseen lord matches its tribe on day one | identical at load (the term is zero), as C_CHOSEN's masked term |
| **N4** | Bound tokens: each token's embedding plus a zero-initialised MLP of (token, its field or role, its verb, its ability index, a number's value) | numbers bound to their roles (38% of cards), tokens to their abilities (25%), Holy and Unholy Strength told apart | identical at load (zero output layer) |
| **N5** | Less boilerplate: learned per-token pool weights (zero-initialised log weights), or at the next fresh network the slim stream (field keys and copies dropped: 72 -> 41 tokens a card) | the 58% common mass stops drowning the informative tokens | weights: identical at load; slim stream: a fresh network |

N1 and N2 are corrections. N3 is the direct answer to "share": it costs nothing until trained. N4
and N5 are bets: K1b/K1c found no gain from structure at 556 cards, so they go in as zero-initialised
terms measured on the policy (the capacity probe's supervised fits, 194, or a run), never as a
replacement of the bag.

### 6.2 IR side: how cards are encoded as trees (Type-1, one gated ontology round each)
Trees: distinct oracle ids of the 19 sets that change. Stamps: verified home + reprint stamps that
re-bake and wait for re-verification. Remaining: unverified M21/M20/FDN cards with an unparsed
sentence that needs the form (`proposals.txt`).

| # | change | tokens | examples per token | trees | stamps | remaining |
|---|---|---|---|---|---|---|
| **I0** | Remove the dead second encodings: Verb.EXILE, MILL; Keyword.MILL, SCRY, BATTALION; QPropField.CMC; PT_LE, PT_GE, CONTROLLER_COUNT_LE; ThisTurnKind.CARDS_DRAWN, LIFE_GAINED | 11 enum members, none a token today | | 0 | 0 | 0 |
| **I1** | One quantity comparison: a predicate "quantity at least quantity" (QProp, QCount, QDistinct, life; FNot for "or less") for the 11 comparators, with F11's starting life | -11, +1 | 1-29 (median 3) -> 66 | 66 | 46 + 5 | 36 |
| **I2** | Turn history on EVENT_THIS_TURN / SUBJECT_OF_EVENT_THIS_TURN (B-44, with its two decisions) | -9, and QThisTurn with its kind | 1-10 -> about 50 | 27 | 25 + 0 | 18 |
| **I3** | One form for "this <permanent>": CHOOSE + IS_SOURCE in effects and costs (D25, D27) | 0; 76 trees join the majority form | | 76 | 41 + 16 | 57 |
| **I4** | One role for MOVE_ZONE's objects (B-42): the exile family's `target` -> `cards` | 0; 61 trees join 135 | | 61 | 32 + 9 | 17 |
| **I5** | Names by referent or type: NAME_EQ takes a referent ("named ~", "the same name as"), NAME_CONTAINS -> SUBTYPE_EQ (D29, D30); drop the party template's name check | -1 (NAME_CONTAINS) | | 14 | 10 + 2 | 7 |
| **I6** | One POLICY verb with a scope (F9), one MANDATE verb | -4, +1 | 1-3 -> 5 (+3 waiting) | 8 | 6 + 1 | 10 |
| **I7** | "Choose a colour" at resolution as CHOOSE_NAME(COLOR) + its read (F13; lifts refusal 5) | 0; Gods Willing 232 -> about 70 tokens | | 2 | 2 + 0 | 1 |
| **I8** | The ledger's small folds in one round: D12, D13, D14, D18, D19, D21, D22, D23, B-48 | -1 (Verb.DISCARD) | | 36 | 27 + 7 | 22 |
| **I9** | Three one-case nodes made general: TARGETS(filter), QDistinct(property), zone counts as QCount (D28) | -4, +2 | TARGETS 4 (+5 waiting), QDistinct 2 (+6) | 8 | 8 + 0 | 12 |

I1 to I9 together: 258 trees, 161 home + 30 reprint stamps (of 1,144), 14 unverified home trees, 146
remaining cards (`proposals.txt`, bundles). The network input changes only for the re-baked cards: a
new token joins the table at zero (`CardTable.refresh`, `extend_cards`), a folded token's row goes
unused, and every other card computes what it did. In bulk a re-verification costs about 3
agent-minutes a card (207 §4). Not proposed: folding IS_ATTACHED_TO_SOURCE (125 trees), the cost
twins (F3, ruled), the CHOOSE_NAME rename (F12: a label, the network reads ids), turning the 40 kept
rare components into anything.

## 7. The recommended order
1. **Now, independent of the card work: N1 and N2** (one network change, the bitwise check on r28's
   checkpoint, a fresh-eyes review). N1 is a correction with no cost; N2 removes one-card tokens.
   I0 rides with the first gated round: it changes no tree, and stops a mapper minting a second form.
2. **Before the remaining cards are mapped or templated** (so they are mapped once, onto the shared
   form; PLAN_COMPONENT_TRAINING step 0.4 asked for the fold "before the big training run"):
   - **R12 = I1 + I9**: the comparison and the general nodes (73 trees, 53 + 5 stamps, 46 remaining
     cards). The largest token reduction (-15, +3) and the remaining cards' commonest parameters.
   - **R13 = I2 + I5 + I6**: turn history, names, policies (47 trees, 39 + 3 stamps, 34 remaining).
   - **R14 = I3 + I4**: the template-level forms (today's activated-pump and exile templates emit the
     second forms) before the templates for the 72 remaining cards that print these wordings are
     written (134 trees, 69 + 23 stamps).
   Re-verify each round's stamps before the next, in the blind-verifier waves of 207 §3.
3. **Then N3** (value sharing) at the next table refresh, measured by the capacity probe's fits or a
   run: it is where "Elf", "Creature" and "Garruk" become one vector across face, filter and choice.
4. **After the mapping wave: I8** (the small folds) and **I7** with Crippling Fear (F13's own
   decision), then **N4 and N5** as measured bets.

The new components of §5 (copy, the play permission, flashback, the opening hand) are separate gated
rounds; each should take the shared forms above as it lands (a flashback permission is a CAST with a
duration and an alternative cost, not a new cast verb; surveil is SCRY with a graveyard pile).

## 8. N1 and N2 built (2026-11-17)

Built in b364fe6b, on main 32e804ec; §0-§7 are unchanged. Evidence: `reports/n1n2_2026-11-17/`
(its README maps scripts to numbers and holds the commands). r28's v2 was read only, on the CPU: a
probe run held the GPU while this was measured.

### 8.1 What changed
- **N1.** A table row holds every token of its card: `CardTable.max_ir` and the cut are gone
  (`features.py` `from_records`, `extend`, `refresh`). `CardTable.ir_counts()` (features.py:370) is
  the [rows, vocabulary] count matrix (padding never counts). The network's buffer `ir_counts`
  replaces `ir_table` (model.py:51): it is still built from the table at every load, never saved.
  `card_table_emb` (model.py:98) computes `(counts @ ir_emb) / row length`. Under autocast it stays
  in fp32, as the gather did, then casts to the weights' dtype. `extend_cards`, `build`, `load`, the
  trainer process, the simulator and the workers read the table as before.
- **N2.** `ir_tokens` (features.py:220) writes no card name. The census walk over every compiled
  tree found these name paths:
  - a back face's `@face_name` (87 trees): left out, since the `BackFace` tag still marks the face;
  - NAME_EQ with the card's own name (7 trees), and the party template's NAME_CONTAINS with it
    (3): `str:~`;
  - NAME_EQ naming another card (14 cards): `str:<name>`;
  - `LiteralName`, which no tree holds yet: the same rule, where it used to become
    `LiteralName.<name>`.

  TokenSpec names were already skipped. A NAME_CONTAINS fragment that names no card stays: "a
  Garruk planeswalker" (D29) keeps `str:Garruk`, which SUBTYPE_EQ shares. `card_tokens` passes the
  card's name and its faces' names as its own.
- **Old checkpoints are read as saved, not converted.** An old table's JSON still holds rows cut at
  128 and `"max_ir": 128`. `from_json` ignores the key, and the pool reads those rows.
  `--refresh-table` rebuilds them whole and free of names. There is one pooling path.

### 8.2 Before and after, on the cards (`census.txt`)
The base commit's `card_tokens` (read from git) against the new one, on the review's populations:

| | verified M21+M20+FDN (651) | every compiled tree, 19 sets (4,314) |
|---|---|---|
| cards past 128 tokens | 79 (12.1%) -> 0 | 116 (2.7%) -> 0 |
| tokens the cut took | 3,736 -> 0 | 5,638 -> 0 |
| verb / keyword a card lost outright (card-component pairs) | 33 / 39 -> 0 | 44 / 75 -> 0 |
| cards with a name token | 17 (6 own, 11 another card's) -> 0 | 110 (87 back faces, 9 own, 14 another's) -> 0 |
| distinct tokens | 610 -> 594 | 857 -> 747 |

The two tokenisations differ only at the name tokens; the script asserts it card by card. No
name is left, apart from the basic land types (`str:Island`), which are subtypes (CR 205.3i).

### 8.3 r28's v2, old code against new (`compare.txt`, CPU fp32)
- **v2's own table, read as saved.**
  - Component vectors: max |diff| 1.12e-8. 13 of 613 rows are bitwise equal.
  - 1,027 real decisions from 6 seeded heuristic games (M21, M20): encodings are bitwise equal;
    logits max |diff| 1.43e-5 (median 1.9e-6); values 1.8e-6; 19 decisions bitwise; greedy choice
    unchanged in all 1,027.
  - 6 seeded games that v2 plays greedily (self-play and against the heuristic, 697 decisions):
    the same games, decision for decision; max |dlogit| 2.0e-5.
  - Not bitwise: the count matrix adds in another order than the gather did, about 1e-8 per vector
    and about 1e-5 on a logit after 8 layers. Getting bitwise would mean keeping the [N, 128, d]
    gather. That costs about 8x the pool's time (53 against 6.5 ms forward on 2 threads beside the
    run, `precision_check.txt`), and its cost grows with the longest card.
- **Refreshed as r28 and r29 build the table** (`--refresh-table --extend-sets M20 --mix-sets M20`).
  - 82 of 613 rows have different tokens:
    - 77 were past 128 and are whole now. They had lost 35 verb-card pairs: 3 emblems (Basri Ket;
      Garruk, Unleashed; Liliana, Waker of the Dead), DAMAGE_ASSIGN_POLICY, TRIGGER_ADDITIONAL,
      DESTROY, DRAW, and others.
    - 17 held a card name.
    - 12 are both.
  - On v2's weights the changed rows move |dv| / |v| = 16% at the median (quartiles 12-29%). The
    largest move is 51% (Rin and Seri, Inseparable, 128 -> 221 tokens); the smallest is 0%
    (Battalion Foot Soldier, whose old and new name tokens both start at zero).
  - The name rows move 11% at the median. `str:~` and `str:<name>` join at zero, as every new
    token does.
  - The other 531 rows move at most 1.12e-8.
  - Decisions with no changed card visible (76 of 1,027): max |dlogit| 1.07e-5, no greedy change.
  - Decisions with one (951): median |dlogit| 0.031, max 1.40; |dvalue| up to 0.040; 4 greedy
    choices differ (0.4%).
  - The 6 played games were still identical.
- **bf16** (`precision_check.txt`). Under the trainer's autocast the pool stays fp32. Old against
  new on 256 decisions is within bf16's own rounding:
  - autocast: max |dlogit| 0.063, against 0.087 for the old code's autocast against fp32;
  - the bf16 inference copy: 0.19 against 0.19;
  - greedy choices equal in 255 and 254 of 256 (252 between the old code's bf16 and fp32).

  So on the GPU's bf16 paths, an old checkpoint plays as it did up to bf16's rounding, and no
  closer.

### 8.4 The seven zero rows
They are component embeddings, not card rows. No card row of v2 is empty or pools to zero, except
padding and the unknown card.

| token | the cards that carry it |
|---|---|
| `str:ACTIVATED`, `str:TRIGGERED` | Sublime Epiphany |
| `sub:Advisor` | Kethis, the Hidden Hand |
| `sub:Vivien` | Vivien, Arkbow Ranger; Vivien, Nature's Avenger |
| `sub:Scarecrow` | Scuttlemutt |
| `sub:Octopus` | Octoprophet |
| `sub:Troll` | Barkhide Troll |

- **How they joined.** Each token entered the table at zero (`extend_cards`). The `sub:` rows came
  with r19's `--extend-sets M20`, which added 50 tokens (540 -> 590). The `str:` pair was already
  zero in r18's init.
- **Why they stayed zero.** Their cards are castable, so they have rows, but none was verified
  when r19-r28 dealt from `--pool verified`:
  - Sublime Epiphany has no record;
  - Kethis, Vivien, Arkbow Ranger and Scuttlemutt are needs-atom;
  - Vivien, Nature's Avenger, Octoprophet and Barkhide Troll were verified or mapped after r28
    started.

  No game dealt them and no quality choice named them, so no gradient reached the rows, and AdamW
  leaves a zero row with no gradient at zero.
- **Verdict: meant, not a bug.** Zero is the designed start of a new component: a neutral term
  until a card that has it is played. The rows train once their cards are dealt. A refresh now also
  puts the `str:` pair on Tale's End, which is verified.
- **A related cut artifact, gone with N1.** 8 of v2's 590 tokens are in no row at all, because
  they only ever stood past 128: `@right_inner_filter`, `AbilityTriggerEvent`,
  `FAtomPred.COLOR_IN`, `LoyaltyActivatedEvent`, `QPropField.TOUGHNESS`,
  `Verb.DAMAGE_ASSIGN_POLICY`, `Verb.TRIGGER_ADDITIONAL` and `str:AS_UNBLOCKED`. Their embeddings
  are untrained in v2. Five are at the initial scale (norm 0.42-0.44); three were trained in an
  earlier run (0.59-0.81). A refresh puts them back in their cards' means.

### 8.5 Tests (`tools/selfplay/test_selfplay.py`)
- `test_a_card_past_128_tokens_keeps_its_last_ones`: Basri Ket's GET_EMBLEM, token 138. Fails on
  32e804ec, where the row is short by 88 tokens.
- `test_no_card_name_is_a_component_token`: fails on 32e804ec, where the M21 vocabulary holds
  `str:Alpine Watchdog`, `str:Frantic Inventory` and others.
- `test_a_checkpoint_from_before_n1_is_read_as_saved_and_plays_as_before`:
  - an old-format checkpoint pools to the old gather-and-mean (< 1e-6);
  - a seeded game takes the same decisions and values both ways;
  - a new checkpoint holds whole rows and no `max_ir`, and loads to the same outputs bitwise.

  The old-checkpoint half passes on 32e804ec too. The zero rows need no test, because nothing was
  fixed.

### 8.6 For the next run
- From an old checkpoint without `--refresh-table`, a run computes what it did, to fp32 summation
  order.
- With it (r29's flags), the long cards are whole and the name cards read `str:~` and
  `str:<name>`. Those are 82 of v2's rows, in addition to the rows the recompile changes anyway.
- r29's pinned worktree keeps its own code, so this changes r29 only if it is rebased.
- A table refreshed by the base commit's code holds name tokens (from v2, `str:Battalion Foot
  Soldier`), so its vocabulary is not a prefix of one this code refreshes from the same init.
  `Learner._load_net` refuses such an opponent, as it must. Start from the old run's own
  checkpoint instead.
- The BACKLOG's observation-caps scaffold no longer lists the 128-token cut.
