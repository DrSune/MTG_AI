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
   G0 refuses an `ir` that names no `abilities[i]` or `keywords[i]` of the draft, except the two
   labels (Rulings, "Labelled sentences").
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
- **"you may ..."** is `OptionalEffect(inner=...)`, except "you may play/cast ... from ..." (a
  permission: "Playing a card from another zone" below).
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
- **Exile and remove-counter costs** (ontology R11, DESIGN_ATOM_ONTOLOGY §15). In a cost, "Exile
  this creature" is `CostExile(target=<this creature>)`, the "this creature" selector above;
  "Exile this card from your graveyard" the same selector over `Zone(GRAVEYARD, YOU)` (the ability
  then works only from the graveyard, CR 113.6m); "Exile two creature cards from your graveyard"
  `CostExile(Selector(QConst(2), CHOOSE, TYPE_EQ 'Creature', zones=(Zone(GRAVEYARD, YOU),)))`,
  with `FNot(IS_SOURCE)` for "other". "Remove a +1/+1 counter from this creature" is
  `CostRemoveCounter(counter_kind=CounterKind.PLUS_1_PLUS_1, target=<this creature>)`, `count`
  for "two". `parse` the printed sentence: the frame B13-activated-cost-item builds them before
  any clause that parses alone. Never write the exile or the removal as a step of the effect: a
  cost is paid as the ability is activated, all of it or not at all, and stays paid when the
  ability does nothing (CR 601.2h, 602.2b, 118.3, 608.2b). The IR refuses a TARGET or referent
  selector in them (costs never target, divergence D13), X, "all", "any number", LOYALTY (that is
  CostLoyalty) and a kind the payer picks ("Remove a counter from ...", WAR Soul Diviner): such a
  card is a needs-atom until its piece comes with tests. It also takes one form for each meaning
  and only the payer's objects: the source is `IS_SOURCE` alone with `QConst(1)` (never
  `FAnd(CONTROLLER_IS YOU, IS_SOURCE)` or a `Zone(BATTLEFIELD, YOU)` zone, divergence D25),
  another permanent says `CONTROLLER_IS YOU` in its filter over `Zone(BATTLEFIELD, ANY)`, a card
  comes from `Zone(GRAVEYARD, YOU)` or `Zone(HAND, YOU)`, one zone per selector; and one cost holds
  one `CostExile` and one `CostRemoveCounter` of a kind (divergence D26).
- **Playing a card from another zone** (ontology R13, DESIGN_ATOM_ONTOLOGY §17; `parse` the
  sentence first: templates_b19 reads most wordings). "You may play/cast X from Z" is
  `Verb.PERMIT`, never a CAST and never a free activation:
  - `source` names the cards and the zone: `Selector(QUnbounded(), ALL, <filter>, zones=(Z,))`
    with Z your graveyard, exile, the top of your library (`ZonePosition.TOP`) or your hand; a
    TARGET over a graveyard or exile ("target instant card in your graveyard ... this turn"); or
    "them", "that card", "cards exiled this way": the `result` selector with no filter.
  - "play" is `lands=True`; "cast" leaves `lands` out. "Play lands" is `lands=True` over
    `TYPE_EQ 'Land'`.
  - "without paying its mana cost" is `alternative=Cost()`; another cost instead of the mana cost
    ("for its flashback cost") `alternative=<that cost>`; "by paying 3 life and discarding a card
    in addition to paying its other costs" `additional=<those parts>`.
  - "a creature spell" (one play) is `count=QConst(1)`; "this turn" `DurationEot()`, "until the
    end of your next turn" `DurationUntilEndOfNextTurn()`, "for as long as it remains exiled"
    `DurationPermanent()`.
  - In a static ability (Conspicuous Snoop, Omniscience, "you may cast this card from your
    graveyard") the PERMIT has no duration and no count, and lasts while the static functions. A
    card's own permission names its card with `FAtom(IS_SOURCE)` in a static only, never over your
    hand (a cost to cast it from your hand is its spell's alternative cost, CR 118.9: needs-atom).
    In a spell or an activated, loyalty or triggered ability (Chandra, Heart of Fire's [+1], Golos)
    the duration is required, and the cards are designated (TARGET, or `result`): an ALL over its
    own card would cover the card again once it moves and comes back (CR 400.7).
  - "Play lands and cast X from Z" is one PERMIT with `lands=True` over `FOr(Land, X)`; a cast
    permission never filters `FNot(Land)` (a land is never cast anyway).
  - Never under `OptionalEffect`: the "you may" is the permission's use.
  - "If that spell would be put into your graveyard, exile it instead" and flashback's exile are
    the cast verb's `replace` role, `ability_tree.spell_rider(Zone(GRAVEYARD, YOU))` or
    `spell_rider(Zone(ANY, ANY))`, never a ReplacementAbility of the card.
  - "You may cast target ... card from your graveyard" with no duration is the one-shot
    `OptionalEffect(CAST(...))`: the card is cast as the ability resolves (CR 608.2g; Chandra,
    Flame's Catalyst's [-2]); with "this turn" it is a PERMIT over the target (Jace, Telepath
    Unbound's [-3]). "Flashback {cost}" is the card's own static PERMIT with `alternative` and
    `spell_rider(Zone(ANY, ANY))` (B19-flashback).
- **Copies** (the copy round B3, DESIGN_ATOM_ONTOLOGY §18; `parse` first: templates_b20 reads
  "create a token that's a copy of", "copy target instant or sorcery spell", Thousand-Year Storm's
  count and "You may choose new targets"). What is copied is one `CopyOf(source, ...)`; where the
  copy goes is the verb:
  - "Create a token that's a copy of X" is `CREATE_TOKEN(tokens=CopyOf(X), count=QConst(n))`,
    never a COPY. X is one object: "this creature" `Selector(QConst(1), CHOOSE,
    FAtom(IS_SOURCE), zones=(BATTLEFIELD,))`, a TARGET of one, "it" (`referent="result"`: the
    card an instruction before it moved, Abyssal Harvester) or "that creature" (`"event"`).
    Never `referent="source"`: "this" is the CHOOSE of IS_SOURCE.
  - "Except ..." goes in the CopyOf: "it's a Nightmare in addition to its other types"
    `subtypes=("Nightmare",)`; "it has haste" `keywords=(Keyword.HASTE,)` (bare keyword
    abilities, `ability_tree.COPY_EXCEPTION_KEYWORDS`); "it has '<ability>'" `abilities=(...)`
    (a triggered, activated or static ability). Any other exception is needs-atom (BACKLOG, "The
    copy lane still blocked").
  - "Copy that spell|ability" (a cast or activation trigger) is `COPY(source=CopyOf(<event
    referent>))`; "copy target instant or sorcery spell" `COPY(source=CopyOf(TARGET over the
    stack))`. "You may choose new targets for the copy" is `new_targets=True` on that COPY, never
    a sentence of its own; "copy it twice" `count=QConst(2)` (absent is one). No exception, no
    duration: a copy on the stack lasts until it leaves it.
  - "Each other artifact you control becomes a copy of that artifact until end of turn" is
    `COPY(source=CopyOf(<that artifact>), cards=<the permanents, over the battlefield>,
    duration=DurationEot())`: the permanents that become copies are `cards`, never `target`.
  - "For each other instant and sorcery spell you've cast before it this turn" is
    `QBin(SUB, QProp("event", ORDINAL), QConst(1))` in a cast trigger's effect; never in its
    condition (an intervening "if" on the ordinal is `CastSpellEvent.ordinal`).
  - "All other <objects>" after an instruction that made or moved one is
    `FNot(FAtom(IS_RESULT))` in the moved objects' filter, in a later step of the Seq.
- **"Whenever you attack" and "one or more creatures you control attack".** A
  `DeclareAttackersEvent` with filter `FAnd(CONTROLLER_IS YOU, TYPE_EQ 'Creature')`, no
  condition, and `once_per_event=True` on the `TriggeredAbility` (or `DelayedTrigger`): it
  triggers once per declaration (CR 508.3d, 603.2c). "Attack with two or more ..." is the same
  plus its count in the event's filter (Tide Skimmer: `at_least(2, quantity=number_you_control(
  <attacking flyers>))`, a conjunct of `DeclareAttackersEvent.filter`). It is part of the trigger event, read
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
  (TURN_OF, a comparison of a `quantity`, ...: `ability_tree.reads_no_subject`) has one slot per event:
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
  - **Every "N or more", "N or less", "more than", "at least" is the one comparison** (ontology
    round R12), `FAtom(QTY_GE, count=N, field=... | quantity=...)`; write it with the draft's
    builders `at_least(N, field=... | quantity=...)` and `at_most(N, ...)`. "N or less" is `at_most`,
    `FNot` of the comparison at N + 1, and nothing else (CR 107.1: the numbers are integers; "more
    than N" is `at_least(N + 1)`). The IR refuses every other spelling: a pick (`QAtMost`) as the
    count, a number on the measured side, a comparison of something that is no number.
    - The judged object's own characteristic is `field`: "creature with power 2 or less" is
      `FAnd(TYPE_EQ Creature, at_most(2, field=POWER))`; also TOUGHNESS, MANA_VALUE and COLOR (its
      number of colours: "multicolored" is `at_least(2, field=COLOR)`, "one or more colors" 1).
    - A measure of the game is `quantity`: "you control three or more creatures" is
      `at_least(3, quantity=number_you_control(<creature>))`; "you control a creature with power 4
      or greater" `at_least(1, quantity=number_you_control(FAnd(<creature>, at_least(4,
      field=POWER))))`; "there are seven or more cards in your graveyard" `at_least(7,
      quantity=number_in(Zone(GRAVEYARD, YOU)))`; "the number of cards in your hand" is
      `number_in(Zone(HAND, YOU))`, never a QProp field (divergence D28); "creatures you control have
      total power 8 or greater" a `QProp(<your creatures>, POWER, SUM)` (a total only: "the
      greatest power" is the count of the creatures that pass the comparison); a population on
      the battlefield is `Zone(BATTLEFIELD, ANY)`, its controller a CONTROLLER_IS in the filter; "N different names / mana
      values / colours among ..." `QDistinct(<selector>, NAME | MANA_VALUE | COLOR)`.
    - "you have N or more life" is `at_least(N, quantity=QProp('controller', LIFE))`; relative to
      the starting life total (CR 103.4: 40 in Commander) it adds `QProp('controller',
      STARTING_LIFE)`: "at least N life more than your starting life total" is `at_least(QBin(ADD,
      <starting life>, QConst(N)), quantity=<life>)` (`compiler.conditions.life_over_start`).
    - "an opponent has eight or more cards in their graveyard" is `at_least(8,
      quantity=number_in(Zone(GRAVEYARD, YOU)), who=OPPONENT)`: "your" graveyard read for each
      opponent in turn, true when one has it. `who` is OPPONENT, over a count of "your" zone, and
      nothing else: a card that reads another player's life or a target player's zone is a
      needs-atom, and brings its slot with its tests.
    - "more <X> than <Y>" (Garruk, Unleashed's "an opponent controls more creatures than you")
      measures the larger side: `at_least(QBin(ADD, <Y>, QConst(1)), quantity=<X>)`, and "<Y> is
      fewer than <X>" is the same tree: the IR refuses the negation of a comparison of two
      measures, a sum written "1 + N", a threshold of 0 and, with `who`, a threshold that is not a
      number.
  - "a spell that targets <filter>" is `FAtom(TARGETS, inner_filter=<filter>)`: one of the
    spell's targets passes it (CR 115.1, 601.2c); "that targets this creature" is
    `inner_filter=IS_SOURCE`. "Becomes the target of a spell or ability" is the targeting event,
    not TARGETS.
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
  - "N damage to that creature's controller": see "That creature's controller" under Rulings.
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
      - play through a card's real permission (ontology R13): the `act` op's words
        `land:<key>` and `cast:<key>[:via:<source key>]`, the `via` when the permission changes
        the cost or adds a rider (flashback is `cast:<key>:via:<key>`).
    - Since 2026-11-17 (KNOWLEDGE/2026-11-17/212 §3, the tool guards):
      - A step's words answer its asks in order; once they are used up the next ask raises with
        its words (a kickback ask takes PASS), so `expect_raise` can pin an ask after a may-offer.
        In a combat step an ask no map or word claims (a trigger's target, the order of two
        triggers) raises too. A held cast resolves in a later step, whose words answer it.
      - Refused: `activate` of a mana ability (pay with it: `"tap": true` or `act`) and
        `hold_triggers` (use `"hold": true`).
      - New: `"controlled_by": N` on a battlefield card (seat N controls what another seat owns),
        the `revealed` lane (whose cards a REVEAL showed), the `tap` op (a tap by another effect;
        its key may be an effect-made object's handle, `"card:14"`).
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

## Rulings (KNOWLEDGE/2026-11-17/209 §3, §5)
One form each where the IR had the pieces but no convention. G0's lints of the same names refuse
the other forms (`tools/cards/lints.py`). Worked drafts, packs and traces:
`reports/rulings_2026-11-17/`.

### Food tokens (R_FOOD)
"Create a Food token" (28 printings by 209's count) makes the one Food, `templates.food_token()`
(CR 111.10b). Food is an artifact type (CR 205.3g), so it is the token's subtype, which
SUBTYPE_EQ reads ("Sacrifice a Food"), never a keyword: Treasure's `Keyword.TREASURE` marker is
not the model (BACKLOG). Its sacrifice is `IS_SOURCE` alone, as Treasure's is (the form D25's
fold keeps). Copy it exactly; "two Food tokens" is `count` 2:
```python
# R_FOOD
FOOD = TokenSpec(
    name='Food', type_line='Artifact — Food', types=('Artifact',), subtypes=('Food',),
    power=None, toughness=None, keywords=(),
    abilities=(ActivatedAbility(
        cost=Cost(parts=(CostManaGeneric(amount=QConst(value=2)), CostTap(), CostSacrifice(
            target=Selector(
                count=QConst(value=1), mode=SelectorMode.CHOOSE,
                filter=FAtom(pred=FAtomPred.IS_SOURCE),
                zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),))))),
        effect=A(Verb.GAIN_LIFE, {'amount': QConst(value=3), 'controller': ControllerRef.YOU})),),
)
create_food = A(Verb.CREATE_TOKEN, {'count': QConst(value=1), 'tokens': FOOD})
```
Why one: the binder keys a token's abilities by its name (`verbs.token_oracle_id`), so a second
Food spec in a game plays as whichever was made first. MTGJSON's "Food" keyword is met by the
token's subtype, and the `amounts` lint does not read its 3 (reminder text).

### One trigger, two events (R_TWOEVENTS)
"When this creature enters or dies, X" (and "enters or attacks": 18 printings in the 19 sets) is
two TriggeredAbility nodes, adjacent in printed order, with one condition and byte-equal effects:
the compiler's own "When this creature enters" event, then `CreatureDiesEvent(IS_SOURCE)` (never
a zone change, D24) or `DeclareAttackersEvent(IS_SOURCE)`. It is the form the compiler gives M21
Elder Gargaroth's "attacks or blocks" (verified), which the lint reads too. With `effect` the
printed effect's tree:
```python
# R_TWOEVENTS
enters = TriggeredAbility(event=ZoneChangeEvent(
    from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    subject=FAtom(pred=FAtomPred.IS_SOURCE)), condition=None, effect=effect)
dies = TriggeredAbility(event=CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
                        condition=None, effect=effect)
abilities = [enters, dies, *compiled]
```
Why not one ability with an either-event: an ability triggers once each time its event occurs
(CR 603.2c), and no one event is both an entering and a dying, so each event triggers exactly one
of the two; once per event holds either way. The halves are read at different times, the enters
one after the event (CR 603.6a), the dies one looking back (CR 603.10a), and the binder matches
each event class with its own matcher (`binding._match_node`: the zone change against the
permanent that arrived, CreatureDiesEvent against the was-snapshot). Two abilities reuse both;
an either-event is a new EventSpec, an IR change. The rules count one ability (CR 113.2c), the
tree two: nothing in the 19 sets tells them apart (none of these cards triggers "only once each
turn"; losing all abilities loses both).

### That creature's controller (R_ITSCONTROLLER)
"Its controller" and "that creature's controller" are the referent Selector of the object in
scope: `referent='target'` for the ability's own target, `'event'` for the triggering object (the
dying, attacking or blocking creature; a damage event's recipient). A player verb takes it in
`controller` (or `EachPlayer.ref`, above). DEAL_DAMAGE has no player role, so "N damage to that
creature's controller" (10 printings: Chandra's Outrage, Cryoclasm, Impending Doom's `'event'`,
...) reads the same Selector through CONTROLLER_IS over the players, M20 Chandra, Flame's Fury's
verified -2:
```python
# R_ITSCONTROLLER
its_controller = Selector(
    count=QUnbounded(), mode=SelectorMode.ALL,
    filter=FAtom(pred=FAtomPred.CONTROLLER_IS, who=Selector(
        count=QConst(value=1), mode=SelectorMode.CHOOSE, filter=FAnd(children=()),
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),), referent='target')),
    zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.ANY),))
two_to_its_controller = A(Verb.DEAL_DAMAGE, {'amount': QConst(value=2), 'target': its_controller})
```
That player is not targeted (CR 115.1), and the object is read as it last existed (CR 608.2h), as
the `controller` role reads it (`selectors.controller_matches`, 2026-11-17: Smash to
Smithereens' damage hit a stolen artifact's owner). Never a TARGET slot over the players (the
caster would choose), the `recipient` role, TARGET_PLAYER (D18), a referent in `target` (the
creature again) or an EachPlayer around the damage. In a damage trigger (KNOWLEDGE 203) the
dealer stands only for a TARGET_PLAYER read with no printed target and is lifted for every other
effect, so `'target'` names only the trigger's printed target and `'event'` the damaged object:
the dealer's or a targeting spell's controller (M12 Belltower Sphinx's "that source's
controller", ELD Bonecrusher Giant's "that spell's controller") has no referent, needs-atom. The
`its_controller` lint also refuses a `'target'` referent read as a player in an ability that
chooses no target.

### Labelled sentences
Two sentences have no tree, by the coordinator's ruling (209 §5). Their clause takes a label in
place of a tree path, which G0 accepts on those sentences only; every other clause's `ir` names
an `abilities[i]` or `keywords[i]` the draft has.
- `"ir": "deck rule"`: a card's own deck-construction rule, "A deck can have any number of cards
  named ~." (FDN Hare Apparent; DOM Rat Colony, Relentless Rats, M14 Shadowborn Apostle) or "...
  up to seven ..." (ELD Seven Dwarves): the card overrides the copy limit (CR 100.2a, 101.1). It
  means nothing in a game; the deck builders read it off the printed sentence
  (`games.deck_rule_copies`, `CardMeta.max_copies`: stress, coherent, package and drafted decks,
  and the opponent simulator's copy mask).
- `"ir": "inert"`: M20 Vivien, Arkbow Ranger's "[−5]: You may reveal a creature card you own from
  outside the game and put it into your hand." Self-play and Commander give a player no
  sideboard, so it reveals nothing (CR 400.11). The record leaves the -5 out (`lints.INERT`, which
  the `costs` lint reads): the IR holds no ability without an effect (a no-op is not a node), and
  one would be an IR change for an activation that only removes 5 loyalty (what that buys in the
  19 sets: a planeswalker-death trigger or M15 The Chain Veil's demand, none in M20). The card
  waits on SPLIT for its +1.

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
- A clause the record labels `deck rule` or `inert` (Rulings, "Labelled sentences") has no tree
  to judge: OK when the label fits the sentence; G0 refuses the labels anywhere else.

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
  first lock. (It reads the live tree, as `runpack` does; that is why it locks first.)
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
- **Take the game's own path** (the menu with `act`, a cast paid with `"tap": true`, a real
  attack with `combat`), never a runner shortcut where the game has a path, and use the printed
  card for the property under test: printed flying, not flying an effect granted. The "loses
  flying" packs used granted flying and missed the layer fault on printed flying; Leafkin Druid's
  packs activated a mana ability no game activates (the runner now refuses that step).
- **An effect that makes an event other cards watch** (counters put, tokens made, life gained,
  a card exiled with something) gets a pack with a watcher that reacts to it: Wildwood Scourge
  never saw counters an entering creature got, because every pack checked the counters, none the
  event (KNOWLEDGE/2026-11-17/212 §3).
- **To act in response to a trigger**, put `"hold": true` on the step that causes it: the trigger
  then waits on the stack for the next steps. Without it the trigger resolves first and the later
  step tests nothing (mapper M6 got a false pass this way).
- Check it with `cardtool.py runpack SET pack.json`, which runs it against the tree under review.
  `tools/run_scenarios.py` sees verified trees only.
- The orchestrator's `cardtool.py verify` runs your packs again, against the tree and against every
  critical mutant the probe could not tell apart. A pack that kills none of them adds nothing.
