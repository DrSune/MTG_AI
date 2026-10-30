# Mapper and verifier guide (card onboarding)

How agents map a card onto existing components and how another agent proves it plays right.
The plan, the gates and the reasons are in `docs/PLAN_CARD_ONBOARDING.md`. Run every command from
the worktree that carries the card-record loader (branch `cards/mapping`):

```bash
cd /home/sune/Desktop/MTG_AI-sets
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
   - **Permanent spells.** On branch `cards/integration` the compiler gives every enchantment,
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
- **"Whenever you attack" and "one or more creatures you control attack".** A
  `DeclareAttackersEvent` with filter `FAnd(CONTROLLER_IS YOU, TYPE_EQ 'Creature')` and no
  condition. The binder fires it once per declaration (CR 603.2).
- **SEARCH.** Leave out the `controller` role. The executor never reads it (the searched zone comes from
  the `cards` selector), and the compiler is split 14/15 on writing it (divergence D12).
- **Colours.** "Green or white" is an `FOr` of `COLOR_HAS`, never `COLOR_IN`. `COLOR_IN` is a
  subset test, so a multicoloured spell would fail it (B-54).
- **Carriers.**
  - An Aura's carrier is `SpellAbility(kind=SpellKind.ENCHANTMENT)`.
  - An Equipment's carrier is `SpellAbility(kind=SpellKind.ARTIFACT)`.
  - An emblem record takes bare abilities: no carrier and no `EmblemAbility` wrapper.
- **Enchant** (on `cards/integration`). The Enchant restriction rides on the keyword:
  `KeywordAbility(keyword=Keyword.ENCHANT, params=(<filter>,))`, for example the filter
  `FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature')`. The engine reads it to decide what the
  Aura may enchant (CR 303.4a). An Aura record without it can enchant any permanent (B-65), which is
  stronger than printed.
- **Equip** (on `cards/integration`): the compiled equip already carries
  `timing=ActivationWindow.SORCERY` (B-60). Keep it.
- **Ability words** (Threshold, Raid, Morbid, Landfall, Battalion) are not keywords and have no
  rules meaning (CR 207.2c). Write the trigger and its condition. G0 ignores ability words
  (`gates.ABILITY_WORDS`), so it neither fails nor warns on them.
- **Keyword actions** written as the merged MOVE atom satisfy G0 through its `journal_kind`: a mill
  (`journal_kind='MILL'`, `pop_order='TOP'`) satisfies a printed "Mill".
- **More shapes the compiler uses** (mapper B, FDN round 1):
  - "permanent" is `IS_PERMANENT`; "nonland permanent" is `FAnd(IS_PERMANENT, FNot(TYPE_EQ Land))`.
  - "a spell" (any) is `CastSpellEvent(filter=FAnd(()))`.
  - "during an opponent's turn" is the condition `FAtom(TURN_OF, who=OPPONENT)`.
  - "your second card each turn" is `CardDrawnEvent(ordinal=2)`.
  - "equipped creature" is `IS_ATTACHED_TO_SOURCE` in triggers, plus `TYPE_EQ 'Creature'` in statics.
  - Tribal nouns ("target Pirate", "Goblins you control") are `SUBTYPE_EQ` plus `TYPE_EQ 'Creature'`.
  - A filter with one part is written bare: no one-part `FAnd`.
  - "You may X. If you do, Y" is `Seq(OptionalEffect(X), Conditional(MAY_DONE, Y))`.
  - "its controller" is a `referent='target'` selector in the `controller` role.
  - Equip carries `timing=ActivationWindow.SORCERY` ("Equip only as a sorcery"). The compiler's
    equip template drops it (B-60), so add it.
- **Tool tips.**
  - `parse` refuses a masked wording, so try a sibling wording (`{W} or {U}` instead of
    `{G} or {U}`).
  - Card names with a comma do not work with `--name`; write "this creature" instead.
  - Test spec packs against your unwritten draft with
    `cardtool.py runpack SET pack.json --card "Card" --draft draft.py`.
  - Pack runner quirks:
    - The runner's opening `begin_turn` draws seat 0's top library card, so the last library card
      a pack lists ends up in hand.
    - A `cast` step needs `key` (and takes `controller`); an `activate` step takes `seat`.
    - Use `start_tapped` to make a setup card start tapped. The older `tapped` key is ignored
      (B-63).
  - During a calibration round, `parse` hides a few exact wordings. Try a sibling wording, or
    `similar`.

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
- **WRONG:** the trace or the tree contradicts the text. Say how.
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

## Spec packs (gate G4)
A scenario pack (format: the docstring of `tools/run_scenarios.py`) sets up the needed board, does
the step, and states the expected outcome from the printed text. Put `"set": "<SET>"` at the top
level.
- Write the expectation from the text, never from the trace.
- Check it with `cardtool.py runpack SET pack.json`, which runs it against the tree under review.
  `tools/run_scenarios.py` sees verified trees only.
- The orchestrator's `cardtool.py verify` runs your packs again, against the tree and against every
  critical mutant the probe could not tell apart. A pack that kills none of them adds nothing.
