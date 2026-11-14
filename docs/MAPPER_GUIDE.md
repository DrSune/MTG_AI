# Mapper and verifier guide (card onboarding)

How agents map a card onto existing components and how another agent proves it plays right.
The plan, the gates and the reasons are in `docs/PLAN_CARD_ONBOARDING.md`. Run every command from
the repository root (the card-record loader is on `main` since 2026-11-05):

```bash
cd /home/sune/Desktop/MTG_AI
export TORCH_DISABLE_NATIVE_JIT=1 PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
$PY tools/cards/cardtool.py --help
```

## Rules for both roles
1. **Existing components only.** Build the tree from IR nodes that already exist. If the card needs
   something no node expresses, record `needs-atom` and name the missing piece. Never write
   something close but different.
2. **The text is the spec.**
   - Every clause of the printed text must be in the tree.
   - Nothing may be in the tree that the text does not say.
   - A missing drawback, a widened target or a lost "until end of turn" is the kind of bug an RL
     policy finds and abuses.
3. **Never edit code** under `MTG_bot/` or `tools/`. Mappers write drafts in their own scratch
   directory and records only through `cardtool.py write` and `needs-atom`. Verifiers write verdicts
   and spec packs in their own scratch directory.
4. **A mapper never verifies their own cards.**
5. Use `/usr/bin/grep`, `/usr/bin/find` and `/usr/bin/sort` (the plain names are broken wrappers on
   this box).
6. **Inspect cards only through `cardtool.py`.** Do not read `.cache/` files or build supplies with
   your own scripts.
   - Calibration cards are masked in the tools, not on disk, so reading around the tools spoils
     the calibration.
   - If you ever see a calibration answer by accident, say so in your report, as mapper A did.

## Common mistakes, most frequent first (KNOWLEDGE/2026-11-14/207)
Counts are faults found by the card waves (189 causes, 2026-10-29 to 11-13) and planted faults (75
answer keys); G0's lints (`tools/cards/lints.py`) flag the ones marked *lint* at `try`.
1. **Who.** Every `controller`, `CONTROLLER_IS`, zone owner and event actor: "you" against "an
   opponent", "each opponent", "that player", "its controller" (17 faults, 29 of 75 plants).
   "That player" after "target opponent" reads that binding. *lint players*
2. **Numbers.** Every amount, count and P/T change: "a card" is 1, "draw two cards, then discard
   a card" holds 2 and 1 (29 of 75 plants). *lint amounts*
3. **The tree is right, the engine plays it wrong** (14 of the 26 WRONG verdicts since 11-05:
   "any number", "any order", graveyard abilities). Judge the trace, never the tree's looks.
4. **Targets and counts.** TARGET against ALL ("creatures you control" is ALL), "up to N"
   (`QAtMost`, zero allowed), "any number" (`QUnbounded` CHOOSE), "another" (`FNot(IS_SOURCE)`),
   "all X revealed" is no choice (20 faults).
5. **A compiled sentence misread or dropped** (18 faults). Read each sentence's tree in `show`
   before keeping `compiled`; a permanent's text never sits on its cast carrier. *lint carrier,
   players (a dropped instruction)*
6. **Zones and owners.** "Its owner's" hand or library; an ability that works from the graveyard;
   what a card left behind (15 faults).
7. **Order and timing.** "In any order" (no `arrange`) against "in a random order" (`RANDOM`);
   an intervening "if" is the condition, any other qualifier is in the event's filter; modes are
   chosen at cast (13 faults).
8. **Once or each.** "One or more ..." and "whenever you attack" carry `once_per_event`;
   "whenever a creature attacks" is once per creature (11 faults).
9. **Costs.** Every printed cost part on its ActivatedAbility ({U}, {T}, a sacrifice, `Equip {3}`);
   a permission is a static, never a free activation (10 faults, 6 plants). *lint costs*
10. **Durations.** "Until end of turn" on every atom it covers; "until ~ leaves" is the move's
    `duration` (9 faults; 4 of G3's survivors).
11. **"May".** "You may" is `OptionalEffect`; "any number" needs none; "if you do" is
    `Conditional(MAY_DONE)` (5 faults).

Verifiers: a NOT_EXERCISED clause needs a pack; supporting cards in a pack must be verified;
make each pack fail a wrong expectation once; run `cardtool survivors` before reporting.

## Mapper workflow
1. `cardtool.py show SET "Card"` prints:
   - the printed card;
   - each sentence's parse: a template id, `reminder`, or `UNPARSED`;
   - the compiled tree as Python.

   Keep what the compiler got right, and map only the UNPARSED sentences.
2. For each UNPARSED sentence, find the structure:
   - `cardtool.py parse "wording"` shows what the compiler builds for any wording. Try equivalent
     wordings: when one parses, its tree is canonical by construction, so use it. `~` stands for
     the card name with `--name`.
   - `cardtool.py similar "sentence" -k 8` shows the parsed sentences of all 19 sets that are
     worded most like it, each with its tree. Adapt the closest one.
3. Write the draft, a Python file:
   ```python
   new_trigger = TriggeredAbility(event=..., condition=None, effect=A(Verb.X, {...}))
   abilities = [new_trigger, *compiled]   # `compiled`: the compiler's abilities, kept as they are
   # keywords = [...]                     # only if the keywords change; default: compiled_keywords
   ```
   - `A(Verb.X, {"role": value})` builds an atom. The IR checks every role, so a wrong role
     raises at once.
   - **Ability order** follows the compiler:
     - abilities in printed order;
     - then the spell's `SpellAbility`. For an instant or sorcery, that holds the effect, a `Seq` of
       steps in printed order. For a permanent, it is an effect-less carrier.
   - **Permanent spells.** The compiler gives every enchantment,
     artifact and planeswalker its cast carrier (B-49). Keep the one in `compiled` and never append
     a second: G0 fails a card with two SpellAbility nodes. Only for a card the compiler refuses
     outright (no `compiled` tree) do you add `SpellAbility(kind=SpellKind.ENCHANTMENT|ARTIFACT|
     PLANESWALKER)` yourself, last.
4. `cardtool.py try SET "Card" draft.py --out trace.txt` validates the draft, runs G0, plays the card
   (G1) and writes the trace. Read the trace yourself: does each clause happen, on the right
   objects, with the right numbers, at the right time? Fix and repeat.
5. Write `clauses.json`: every printed sentence (reminder text in parentheses may be left out) with
   the tree path that implements it, for example
   `[{"clause": "Flying", "ir": "keywords[0]"}, {"clause": "When ...", "ir": "abilities[0]"}]`.
6. `cardtool.py write SET "Card" draft.py --clauses clauses.json --author <your id>`. It refuses on a
   G0 failure or an engine error. The record is unverified until a verifier passes it.
7. Cannot be expressed: `cardtool.py needs-atom SET "Card" --missing "<the missing piece, precisely>"
   --author <id>`.
8. **The tree is right but the engine plays it wrong.** Packs and traces show this often (B-50..B-63
   in `docs/BACKLOG.md`).
   - **Weaker than printed** (an effect that never happens, a trigger that never fires): write the
     record and report the engine issue with the variant or the pack. The verifier will mark that
     clause WRONG, so the card is not verified until the engine is fixed.
   - **Stronger than printed** (a duration that never ends, a cost that is not paid, extra
     triggers): do NOT write it. Run
     `needs-atom SET "Card" --missing "ENGINE: <the bug, and the pack that shows it>"`. An RL policy
     must never get the card while the bug lives.
   - Examples: regenerate, landwalk, a cost reduction per X, "can't be countered", copy a spell.
   - Say which clause and why no node fits.

## Conventions the compiler uses (check them with `parse`)
- **"this creature", "~", "this enchantment".**
  `Selector(count=QConst(value=1), mode=SelectorMode.CHOOSE, filter=FAtom(pred=FAtomPred.IS_SOURCE),
  zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),))`.
- **"target creature".** A `Selector` with `mode=SelectorMode.TARGET` and a `TYPE_EQ 'Creature'`
  filter. "you control" or "an opponent controls" adds `FAtom(pred=FAtomPred.CONTROLLER_IS,
  who=ControllerRef.YOU|OPPONENT)` in an `FAnd`.
  - See `parse "Destroy target creature an opponent controls."`.
- **"you may ..."** is `OptionalEffect(inner=...)`.
- **"Whenever this creature becomes the target of a spell or ability an opponent controls"**
  (ontology R5-6) is `TargetingEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE),
  actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT))`: `filter` reads the
  targeted object, `actor` the controller of the targeting spell or ability. See `parse "Whenever
  this creature becomes the target of a spell or ability an opponent controls, create a 1/1 green
  Elf Warrior creature token."`.
- **"Can't be the target of spells or abilities your opponents control"** stays the HEXPROOF
  keyword (CR 702.11), never a `PREVENT_EFFECT` over a `TargetingEvent`, with or without `actor`.
- **"until end of turn"** is `duration=DurationEot()`. A static effect is `DurationPermanent()`, or
  the static ability itself.
- **"Exile X until this <permanent> leaves the battlefield"** (ontology R5-1, CR 610.3) is one
  `MOVE_ZONE` with `destination=Zone(EXILE, OWNER)` and `duration=DurationUntilLeaves()`; the
  engine returns X to the zone it came from when the source leaves. See `parse "When this
  enchantment enters, exile target creature an opponent controls until this enchantment leaves
  the battlefield."`. Never add a separate "when this leaves, return it" trigger: that is the older
  Oblivion Ring wording and plays differently (CR 610.3a/b). A MOVE_ZONE duration may only be
  `DurationUntilLeaves`, `DurationEot` or `DurationUntilNextTurn`.
- **"At the beginning of your end step / upkeep".**
  `TurnPhaseEvent(phase=Phase.END_TURN|UPKEEP, actor=FAtom(pred=FAtomPred.CONTROLLER_IS,
  who=ControllerRef.YOU))`.
  - "each" or "the" end step has no actor: `parse` Liliana's Scrounger's sentence.
- **Building blocks that parse:**
  - "When this creature enters" and "When this creature dies": `parse "When this creature enters,
    draw a card."` and `parse "When this creature dies, draw a card."`.
  - Activated abilities: `parse "{2}, {T}: Draw a card."`.
- **Numbers.** `QConst(value=N)`. X is `QX()`. "up to N" is `QAtMost`. Use the IR's own quantity
  nodes, never a Python number in place of a quantity.
  - "N for each X" is `QBin(MUL, QConst(N), QCount(...))`.
  - "Any number of" is a CHOOSE `Selector` with `count=QUnbounded()` (Necromentia, Siege Striker,
    Battalion Foot Soldier, Cavalier of Flame's "discard any number of cards"). The engine asks it
    pick by pick, each ask with a NONE stop, as it asks "up to N": every number from zero to all
    of them (CR 107.1c). "That many" after it counts the cards actually moved.
- **"Whenever you attack" and "one or more creatures you control attack".** A
  `DeclareAttackersEvent` with filter `FAnd(CONTROLLER_IS YOU, TYPE_EQ 'Creature')`, no
  condition, and `once_per_event=True` on the `TriggeredAbility` (or `DelayedTrigger`): it
  triggers once per declaration (CR 508.3d, 603.2c). "Attack with two or more ..." is the same
  plus its count in the event's filter (Tide Skimmer: `CONTROLLER_COUNT_GE` over your attacking
  flyers, a conjunct of `DeclareAttackersEvent.filter`). It is part of the trigger event, read
  once as the attackers are declared, so it is never the condition (below).
  - "Whenever a creature you control [with X] attacks" has no `once_per_event`: it triggers once
    for each such attacker, and that attacker is the event, "it" (CR 508.3a).
  - "Whenever one or more <creatures> you control deal combat damage to a player" is a
    `DamageDealtEvent(combat=True, source=<creatures>)` with `once_per_event=True`: once per combat
    damage step for each player they damaged (CR 510.2; Feline Sovereign). The flag gathers the
    dealers `source` names, so it needs one: "this creature is dealt damage" is already one event
    per step and is never flagged.
  - "Whenever one or more <objects> enter" (or "leave your graveyard") is the
    `ZoneChangeEvent` with `once_per_event=True`: one trigger for the objects one event moves,
    the tokens one effect creates or the cards one instruction or one state-based-action check
    moves (CR 603.2c; a draw is one card at a time, CR 121.2). See `parse` on Woodland Champion's
    and Desecrated Tomb's sentences.
  - On a flagged declaration or zone change the event register holds every object the event
    gathered (`ability_tree.gathers_objects`). "They" and "those creatures" are
    `Selector(referent='event')`, the same referent form as "it" (Angelic Guardian: `parse` it);
    the engine acts on those still there (not one that changed zones since, CR 400.7, nor one
    moved into a hand or a library, nor a token off the battlefield). "That many" is
    `QProp('event', THAT_MANY_COUNT)`: every object gathered, those that left since included
    (Woodland Champion's ruling). "The greatest power among them" is
    `QProp(Selector(referent='event'), POWER, MAX)` (SUM for "their total power"): every object
    gathered, read as it last existed once it left (CR 608.2h). There is no "it" among several
    objects: under the flag the IR refuses another QProp of 'event' ("its power"), "attached to
    it", "until it leaves", "it deals", and an intervening "if" that tests the object (the
    condition may only count or read the turn: `ability_tree.SUBJECT_FREE`). Anywhere, "its
    power" is `QProp('event', POWER)`, never a FIRST over `Selector(referent='event')`, and "that
    many" is THAT_MANY_COUNT, never a QCount of a referent Selector. A gathered combat damage
    event keeps its one subject, the player (Feline Sovereign's "that player").
  - "For each creature card exiled this way" counts some of the objects an instruction acted on:
    `QCount(Selector(referent='result', filter=TYPE_EQ 'Creature'))`, a referent count with a
    filter (over a gathered event's `event`, every object gathered: CR 608.2h). The IR refuses
    the two other spellings: an unfiltered referent count (THAT_MANY_COUNT's "that many") and
    `IS_RESULT` in a selector's filter (the referent's second form).
  - "One or more creatures die" (or "are put into a graveyard from the battlefield") is a
    `CreatureDiesEvent`: the IR refuses the flag on the zone change from the battlefield to a
    graveyard over creatures, its second encoding (divergence D24), and the binder does not
    gather a dies event yet (below).
  - The IR refuses the flag where it changes nothing (`ability_tree.gathers_occurrences`): on
    "this creature" or "equipped creature" (one attacker, dealer or moved object per event), on
    damage that is not only combat damage (`combat` False or None), and with no dealer named.
  - The engine groups these three events. A `once_per_event` trigger on any other event ("one or
    more creatures die", a CreatureDiesEvent; a sacrifice) refuses to bind, and these shapes have
    no encoding yet: one trigger per attacked object ("attacks a planeswalker you control with
    one or more creatures"), the recipients gathered ("one or more creatures you control are
    dealt damage"), and "one or more ... deal damage" that may be noncombat. Report them as
    `needs-atom`.
- **Cards put into a library together.** "...and the rest on the bottom of your library in any
  order" is a `MOVE_ZONE` with no `arrange` role: the engine asks the owner the order (CR 401.4).
  "...in a random order" adds `'arrange': 'RANDOM'`. See `parse "Put the rest on the bottom of
  your library in a random order."`. The IR takes the role only where the move can put several
  cards into a library's TOP or BOTTOM through `cards` (`ability_tree.orders_a_library`): never on
  a one-card move, a `target` move, a mill, or a library with no position.
- **All of the revealed cards.** "Put all Goblin cards revealed this way into your hand and the rest
  on the bottom of your library in any order" (Goblin Ringleader) is no choice: a `MOVE_ZONE` whose
  `cards` is an `ALL` Selector (count `QUnbounded()`) over `Zone(LIBRARY, YOU, position=TOP)`
  filtered to the kind, then See the Truth's `REST` over the same zone for "the rest". While the
  REVEAL's (or LOOK_AT's) window is open, the top of the library is the revealed cards, for ALL as
  for ONE_OF and REST. "Put one of them" is the `ONE_OF` choice; never write "all" as a ONE_OF.
- **SEARCH.** Leave out the `controller` role. The executor never reads it (the searched zone comes from
  the `cards` selector), and the compiler is split 14/15 on writing it (divergence D12).
- **Colours.** "Green or white" is an `FOr` of `COLOR_HAS`, never `COLOR_IN`. `COLOR_IN` is a
  subset test, so a multicoloured spell would fail it (B-54).
- **A colour or a creature type chosen as the permanent enters** (ontology R9). "As this creature
  enters, choose a color." is `EtBState(effect=A(Verb.CHOOSE_NAME, {'quality': 'COLOR'}))`
  (`'CREATURE_TYPE'` for "choose a creature type"); Runed Halo's card name is the same atom with no
  `quality`. "Of the chosen color|type" is `FAtom(pred=FAtomPred.NAME_CHOSEN, string_value='COLOR'
  |'CREATURE_TYPE')` where the filter goes: a cast trigger's `filter`, an anthem's selector, a
  look's pick (`parse` each B17 wording). The IR refuses a quality anywhere but as an EtBState's
  own effect (a colour chosen and read at once by a spell is `Choose` over the five, Feat of
  Resistance's "the color of your choice"), a read with no choice of its quality on the same card
  (names included), a choice nothing on the card reads (map its reader too, or record
  needs-atom), a choice in a static ability (it never runs), and a read inside a token's, an
  emblem's or a granted ability, which belongs to another object (a granted PROTECTION quality
  excepted). An EtBState with an `effect` holds nothing else: "This land enters tapped. As it
  enters, choose a color." is `EtBState(tapped=True)` and `EtBState(effect=...)`, two nodes; a
  gate (`condition`) or counters beside the effect are refused. An EtBState gate may read the
  choice: every choice is made first. "The chosen type" is a creature type: a
  card that chose a card type or a basic land type is a needs-atom, and so are mana of the chosen
  colour, "is the chosen type" and a spend restriction to it (BACKLOG).
- **Carriers.**
  - An Aura's carrier is `SpellAbility(kind=SpellKind.ENCHANTMENT)`.
  - An Equipment's carrier is `SpellAbility(kind=SpellKind.ARTIFACT)`.
- **Emblems.** "[−8]: You get an emblem with "<text>"" is the loyalty ability's
  `A(Verb.GET_EMBLEM, {'controller': ControllerRef.YOU, 'emblem': EmblemSpec(abilities=(...,))})`.
  - `abilities` are the emblem's own, written as any card's text would be (Mu Yanling, Sky
    Dancer's "Islands you control have '{T}: Draw a card.'" is a `StaticAbility` granting the
    activated ability); their "you" is the emblem's owner (CR 114.2). Triggered, static and
    replacement abilities only: the engine runs nothing else from the command zone.
  - `controller` is who gets it, and only these three are accepted: `YOU`, `ALL_OPPONENTS` for
    "each opponent gets", `TARGET_OPPONENT` for "target opponent gets" (a target of the loyalty
    ability). An EachPlayer around the GET_EMBLEM is refused (one encoding; other player verbs
    still differ, ATOM_DIVERGENCES D21). Another recipient (ORI Chandra, Roaring Flame's "each
    player dealt damage this way") is needs-atom until it comes with its tests. Each GET_EMBLEM
    makes a new emblem.
  - The quote's text compiles by itself when its sentences parse (`parse` the quoted text alone).
    An emblem's own MTGJSON entry is not used: never write a record for it.
- **Enchant.** The Enchant restriction rides on the keyword:
  `KeywordAbility(keyword=Keyword.ENCHANT, params=(<filter>,))`, for example the filter
  `FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature')`. The engine reads it to decide what the
  Aura may enchant (CR 303.4a). An Aura record without it can enchant any permanent (B-65), which is
  stronger than printed.
- **Equip**: the compiled equip already carries
  `timing=ActivationWindow.SORCERY` (B-60). Keep it.
- **The condition is only an intervening "if"** (CR 603.4: "When/Whenever/At <event>, if
  <condition>, <effect>"). The engine reads it as the event occurs and again as the ability
  resolves. Anything else that qualifies the trigger is part of its event and goes in the
  event's filter, which is read once: "with two or more creatures" (Tide Skimmer), "this
  creature and at least two other creatures attack" (Makeshift Battalion), "during an
  opponent's turn" (Brineborn Cutthroat), "while you control six or more Shrines" (Sanctum of
  All), and a state trigger's threshold, "When there are four or more page counters on this
  artifact" (Mazemind Tome, CR 603.8). A count or turn test that does not read the subject
  (TURN_OF, CONTROLLER_COUNT_GE, ...: `ontology_conformance.SUBJECT_FREE`) has one slot per event:
  `subject` on a ZoneChangeEvent, `filter` on an event that has one, `source` on an
  AbilityActivatedEvent, else `actor` (TurnPhase, CardDrawn, LifeGained, LifeLost and Sacrifice
  events). Not `actor` beside a `filter`: `CastSpellEvent(filter=FAtom(TURN_OF, who=OPPONENT),
  actor=<you>)` for Brineborn Cutthroat. `tools/audit/test_ontology_conformance.py` flags one in
  another slot, and a card whose trigger conditions and intervening "if"s differ in number
  (either way).
- **"You may X. When you do, Y"** (a reflexive trigger, CR 603.12) is
  `Seq(OptionalEffect(X), Conditional(MAY_DONE, DelayedTrigger(duration=None, event=None,
  condition=None, effect=Y)))`: the "If you do" gate around a DelayedTrigger with no duration
  and no event. Y triggers as the resolution reaches the gate and goes on the stack afterwards,
  choosing its targets then: never write it as "If you do" (Y inline), which chooses Y's targets
  with the ability's own (Sorin, Imperious Bloodlord's sacrificed Vampire was offered as its
  target). A mandatory "X. When you do, Y" is gated the same way, and "When you do so, Y" is the
  same trigger. The reflexive trigger stands only as the `then_effect` of exactly
  `Conditional(MAY_DONE)` (not its FNot), after X in the Seq, in the effect of a spell, activated,
  triggered or delayed ability (a granted or token one too), with no EachPlayer or Repeat between,
  and never in a static, replacement, "as ~ enters" or emblem ability: the IR refuses it anywhere
  else. An ability designates only its own targets: a delayed, reflexive or granted ability
  chooses its own. The checker counts reflexive triggers against reflexive sentences ("when you
  do", "when they do", "when ... this way") both ways.
- **Ability words** (Threshold, Raid, Morbid, Landfall, Battalion) are not keywords and have no
  rules meaning (CR 207.2c). Write the trigger: its intervening "if" (Raid, Threshold, Morbid)
  is the condition, its event qualifier (Battalion's "and at least two other creatures attack")
  is in the event's filter. G0 ignores ability words (`gates.ABILITY_WORDS`), so it neither
  fails nor warns on them.
- **Keyword actions** written as the merged MOVE atom satisfy G0 through its `journal_kind`: a mill
  (`journal_kind='MILL'`, `pop_order='TOP'`) satisfies a printed "Mill".
- **More shapes the compiler uses** (mapper B, FDN round 1):
  - "permanent" is `IS_PERMANENT`; "nonland permanent" is `FAnd(IS_PERMANENT, FNot(TYPE_EQ Land))`.
  - "a spell" (any) is `CastSpellEvent(filter=FAnd(()))`.
  - "during an opponent's turn" is part of the trigger event: `FAtom(TURN_OF, who=OPPONENT)` in
    the event's filter (`CastSpellEvent(filter=FAtom(TURN_OF, who=OPPONENT), actor=...)`), never
    the condition.
  - "your second card each turn" is `CardDrawnEvent(ordinal=2)`. "Whenever you gain|lose life
    for the first time each turn" is `LifeGainedEvent|LifeLostEvent(actor=<you>, ordinal=1)`;
    "... during each of your turns" adds `FAtom(TURN_OF, who=YOU)` to the `actor`. Never an
    ordinal in EVENT_THIS_TURN, a replacement or PREVENT_EFFECT's `event`: the IR refuses it there.
  - "as long as you have N or more life" is `FAtom(LIFE_TOTAL_GE, who=YOU, count=QConst(N))` in
    the static's condition; "N or less life" is `FNot` of it at N + 1, never another predicate.
    "At least N life more than your starting life total" is LIFE_LEAD_OVER_START_GE, a different
    meaning (Commander starts at 40). `who` is YOU and nothing else (the IR refuses any other): a
    card that reads another player's life total ("if target opponent has 10 or less life", "an
    opponent has N or less life") is a needs-atom, and its card brings the slot's next value
    with its tests.
  - "If you would gain life, you gain that much life plus N instead" is a ReplacementAbility over
    `LifeGainedEvent(actor=<you>)` whose action gains `QBin(ADD, QProp('event', AMOUNT),
    QConst(N))`: `parse` it.
  - "equipped creature" is `IS_ATTACHED_TO_SOURCE` in triggers, plus `TYPE_EQ 'Creature'` in statics.
  - Tribal nouns ("target Pirate", "Goblins you control") are `SUBTYPE_EQ` plus `TYPE_EQ 'Creature'`.
  - A filter with one part is written bare: no one-part `FAnd`.
  - "You may X. If you do, Y" is `Seq(OptionalEffect(X), Conditional(MAY_DONE, Y))`, and a
    mandatory "X. If you do, Y" is `Seq(X, Conditional(MAY_DONE, Y))`: MAY_DONE asks whether the
    step before it was done (CR 118.12), whichever form it had.
  - "search your library and/or graveyard for ..." is a `Choose(QConst(1), ...)` over the zone
    sets, in this order: both zones, the library only, the graveyard only. "If you search your
    library this way, shuffle." adds a SHUFFLE only to the options that search the library. See
    `parse` on any named tutor, or `templates.and_or_zone_search`.
  - **"its controller" and "that player" are a referent Selector, never TARGET_PLAYER.** The
    referent names the object in scope: `referent='target'` for a target's controller ("Exile
    target creature. Its controller ..."), `referent='event'` for the triggering object's (Gloom
    Sower's "that creature's controller"). Put it in the `controller` role, or make it
    `EachPlayer.ref` when that player then acts in their own zones (Transmogrify's "That player puts
    that card onto the battlefield, then shuffles the rest into their library"). TARGET_PLAYER and
    TARGET_OPPONENT are targets (CR 115.1): in a spell or an activation they open a player target
    the card does not print. `tools/audit/test_ontology_conformance.py` flags a card that names
    one while its text says neither "target player" nor "target opponent" (ATOM_DIVERGENCES D18).
    After "up to one target" the same Selector stands: with no target chosen, "its controller"
    names nobody and the instruction does nothing (CR 608.2b; M20 Cavalier of Dawn's Golem).
  - "N damage to that creature's controller" has no encoding yet: a second TARGET selector over
    the PLAYER zone is a target slot of its own, so the caster would pick who takes the damage.
    Mark such a card needs-atom (M20 Chandra's Outrage). (Under review: BACKLOG, "N damage to that
    creature's controller".)
  - **A trigger with several "target" words** designates them in turn, as a spell does
    (Drakuseth, Maw of Flames). "Each of up to two other targets" (any targets) is a QAtMost(2)
    TARGET slot whose filter is `FAnd(IS_ANY_TARGET, <the any-target FOr>)`: the "another target"
    mark (templates_b5c); players still join it.
  - **Hexproof on a player** (CR 702.11c): `parse "You have hexproof."` (a static, Runed Halo's
    player grant) and `parse "You and permanents you control gain hexproof from blue and from black
    until end of turn."` (one grant over the battlefield and your player zone).
  - **"Reveal cards from the top of your library until you reveal a creature card. Put that card
    into your hand and the rest on the bottom of your library in a random order."**: `parse` each
    sentence (REVEAL `until`, then the `result` to hand and REST to the bottom, RANDOM). Behind
    "you may", the whole dig is optional, since the second sentence moves only what the first
    revealed (FDN Spinner of Souls).
  - Equip carries `timing=ActivationWindow.SORCERY` ("Equip only as a sorcery"). The compiler's
    equip template writes it (B-60, fixed); keep it in a hand-written tree.
- **Tool tips.**
  - `parse` refuses a masked wording, so try a sibling wording (`{W} or {U}` instead of
    `{G} or {U}`).
  - Card names with a comma do not work with `--name`; write "this creature" instead.
  - Test spec packs against your unwritten draft with
    `cardtool.py runpack SET pack.json --card "Card" --draft draft.py`.
  - Pack runner rules (it fails a pack that breaks the first two, since 2026-11-05):
    - Every `expect` lane must be one the runner reads (the docstring of `tools/run_scenarios.py`
      lists them); a mistyped lane used to pass silently.
    - Every decision word must be offered by the ask it answers. A pack key resolves to its
      handle; write `player:N` for a player; `first-legal` takes the first offered word.
    - Make each pack fail against a deliberately wrong draft before you rely on it.
  - Pack runner behaviour worth knowing:
    - The opening `begin_turn` is turn 1 of a two-player game, so seat 0 skips its draw step
      (CR 103.8a) and nothing is drawn at setup: declare a card in hand if the pack needs it there.
      Six filler "Library N" cards go on top of the pack's own unless
      `"world": {"library_top": true}`.
    - Three things a pack can do since 2026-11-13, each refusing what it cannot apply (the
      runner docstring has the details):
      - respond while a combat trigger waits: `"respond_to_triggers": {"DECLARE_ATTACKERS":
        [steps]}` on a combat step runs the steps with the attack triggers on the stack;
      - play with three or more players: `"world": {"players": 3}` (nobody skips the first
        draw, CR 103.8c; every seat a pack names must exist);
      - cast a card from another zone: `{"op": "test_permission_cast", "key": k, "from":
        "graveyard"}`, as though a permission let you, at the card's own timing and full cost.
        The CAST row records the zone (`"kick_rows": {k: {"from": "graveyard"}}`).
    - `end_turn` does not begin the next turn; `advance_turn` does.
    - Leaving `damage` out of `expect` asserts that no damage is marked anywhere.
    - To expect a refusal, put `"expect_raise": "<substring of the error>"` on the step.
    - A `cast` step needs `key` (and takes `controller`); an `activate` step takes `seat`.
    - Use `start_tapped` to make a setup card start tapped (the older `tapped` key is ignored,
      B-63).
    - A card with an upkeep trigger placed on the battlefield fires during the opening turn: start
      it in hand and `enter` it. A synthetic `"type": "Planeswalker"` card takes damage marks
      instead of losing loyalty: use a real planeswalker from the pool.
  - Token records can be probed and written (since 2026-11-06: G0 asks a token for no cast
    carrier, e17ae22, and the probe skips the from-hand stimulus for tokens, 79c5c84). Games build
    a token from the creating card's TokenSpec, so a token record serves only the scenario runner's
    by-name lane (KNOWLEDGE/2026-11-05/184 §14). An emblem lives in its maker's GET_EMBLEM.
  - During a calibration round, `parse` hides a few exact wordings (digits are normalised, so
    every numeric sibling is hidden too). Try a different wording, or `similar`. The same sentence
    on another card or set may still show; if you see a hidden wording's tree, say so.

## Verifier workflow (gate G2)
Packets are made by the orchestrator: `cardtool.py packet SET "Card" --out DIR --id ID`. A packet
holds:
- the printed card;
- the tree the engine runs;
- the G1 trace: every variant the engine played on the standard board.

The standard board:
- **Your side:** you_bear 2/2, you_giant 4/4, you_relic (artifact), you_charm (enchantment). In
  hand: you_spare 3/3 and you_trick. In the graveyard: you_fallen 2/2 and you_used.
- **Opponent:** the same, with an opp_ prefix.
- **Also:** basic lands, 9 mana of each colour each, 20 life each.

Some packets are **planted**: the tree carries a deliberate fault. You are scored on catching them,
so judge every packet on its own.

For each printed clause:
- **OK:** the trace shows it happening exactly as printed: right objects, right numbers, right
  timing, and only the legal choices offered (check the target slots the probe lists).
- **WRONG:** the trace or the tree contradicts the text. Say how. A choice the text gives a player
  that the engine never asks ("any number", "in any order") is WRONG: it alters legal options. A
  fixed order where the text says "random order" is information only, so OK (B-81 ruling, KNOWLEDGE
  2026-11-05/184 §10); an order the engine asks where the text says "random order" is WRONG.
- **NOT_EXERCISED:** nothing in the trace shows the clause (a trigger whose event the board cannot
  produce, a condition never true). Write a spec pack for it (below).

Do not pass a clause because the tree "looks right". The trace is what the engine does.

**The packet is the evidence.**
- Do not run `show`, `probe` or `try` on the card. They read the live tree, and a planted packet's
  tree differs from it by design.
- `parse` and `similar` (how the compiler expresses a wording) and `runpack` are fine.
- A spec pack runs against the live tree, so a passing pack never overrides a contradiction you can
  see in the packet.

Write the verdict JSON:
```json
{"id": "<packet id>", "verdict": "OK" | "WRONG", "probe_sha": "<the sha printed in the packet>",
 "clauses": [{"clause": "...", "status": "OK|WRONG|NOT_EXERCISED", "evidence": "<variant label and event>", "issue": ""}],
 "packs": ["<path to each spec pack you wrote>"]}
```

**Last step: G3's survivors, before you report.** For each card you judged OK, once its verdict
file is written, run `cardtool.py survivors SET "Card" --verdict v.json`.
- The first run locks the judgments: it writes their sha256 into the verdict's `lock` and into
  `locks.jsonl` beside it. Never change a status, an issue or the verdict after that: `survivors`
  and `verify` refuse a verdict whose judgments changed since its lock, and the ledger keeps the
  first lock.
- It lists the critical mutants that none of the verdict's packs tells apart from the card, each
  with the kind of pack that did in earlier waves. Write those packs from the printed text, add
  them to `packs` (evidence may grow), and run it again until it lists nothing.
- In waves 1-1e, 30 of the 72 cards judged OK needed this as a second trip, with the coordinator
  sending each survivor back by message.

## Spec packs (gate G4)
A scenario pack (format: the docstring of `tools/run_scenarios.py`) sets up the needed board, does
the step, and states the expected outcome from the printed text. Put `"set": "<SET>"` at the top
level.
- Write the expectation from the text, never from the trace.
- Check it with `cardtool.py runpack SET pack.json`, which runs it against the tree under review.
  `tools/run_scenarios.py` sees verified trees only.
- The orchestrator's `cardtool.py verify` runs your packs again, against the tree and against every
  critical mutant the probe could not tell apart. A pack that kills none of them adds nothing.
