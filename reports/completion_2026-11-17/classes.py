"""The census's judgments, as data: the missing pieces (packages), the rulings, and each card's
need class where it is not (b). census.py reads this module; KNOWLEDGE/2026-11-17/209 explains it.

Need classes (the brief of 2026-11-17):
  a  only a blind verification: the card compiles (or is mapped) whole;
  b  a record mapped from existing atoms (docs/MAPPER_GUIDE.md); the default for a partly
     compiled card that no package names;
  c  a new or generalised component (a package below of kind "c": an IR change, so a gate round);
  d  an engine or compiler fault (kind "d": no IR change; a fresh-eyes review, no gate round);
  e  a refusal or an out-of-scope label.
A card that needs several packages is (c) if any is (c), else (d). Kind "r" is a ruling: an
encoding decision over existing atoms, no IR change, made by the coordinator and written into
MAPPER_GUIDE before the mapping batch that needs it; its cards stay (b).

Each package's ``patterns`` are regexes over a printing's UNPARSED sentences (case-insensitive).
census.py runs them over the 19 sets: over M21, M20 and FDN to check the hand assignments below
(a hit on a card the table does not give the package is printed for review), and over the other
16 sets for the reach.
"""

# id: (kind, title, CR, nearest existing atoms, what to build, patterns)
PACKAGES = {
    "PERMIT": ("c", "Permission to cast or play a card from another zone: flashback, impulse "
               "draw ('you may play that card this turn'), casting from a graveyard or the top "
               "of a library, free casts",
               "601.2, 601.3, 305.1, 702.34a, 113.6f, 118.9, 611.3a, 400.7",
               "CAST (one-shot), ADD_LAND_PLAY, GRANT_ACTIVATION, IS_EXILED_WITH_SOURCE, "
               "DurationUntilEndOfNextTurn, the result register",
               "R5-2 PERMIT_CAST (source, alternative, count, lands, duration), R5-3 play_lands, "
               "R5-8 provenance: designed in DESIGN_ATOM_ONTOLOGY §10, never built",
               [r"\bflashback\b", r"\bescape\s*[—-]", r"you may (cast|play) (that card|those cards|them|it|"
                r"this card|the exiled card|cards exiled|spells(?! as though)|creature spells|lands|"
                r"artifact spells|target|an? (?!additional land))", r"may play (that card|it|them|those cards|lands)",
                r"cast [^.]* from (your|a|their) graveyard", r"without paying (its|their) mana costs?",
                r"gains flashback", r"(cast|play) [^.]*from (the top of your library|exile)",
                r"until the end of your next turn, you may play"]),
    "COPY_PERM": ("c", "Copies of permanents: a token that's a copy, 'becomes a copy', 'enters as "
                  "a copy' (with exceptions)",
                  "707.2, 707.9, 613.1a, 111.10? (token copy), 706",
                  "Verb.COPY (in the IR, no executor handler), CREATE_TOKEN, TokenSpec, the result register",
                  "R5-5 CopyOf(source, exceptions) and layer-1 copiable values (§10), never built",
                  [r"token that's a copy of", r"becomes? a copy of", r"as a copy of", r"tokens? that are copies",
                   r"copy of (target|another|that|it|enchanted|this|any) (creature|permanent|artifact|nonland)"]),
    "COPY_SPELL": ("c", "Copies of spells and abilities on the stack",
                   "707.10, 707.10c (new targets), 112.1",
                   "Verb.COPY, COUNTER_SPELL's stack targets, STACK_KIND_EQ, stack abilities (B-110)",
                   "R5-5's stack half: a copy is never cast (no CAST row), new targets asked",
                   [r"copy (that|target|it|this|the next) ?(instant |sorcery )?(spell|ability)",
                    r"copy (it|that spell) for each", r"copy that spell", r"copies of that spell"]),
    "WARD": ("c", "Ward: counter a spell or ability that targets it unless its controller pays",
             "702.21a, 118.12, 701.5 (counter)",
             "TargetingEvent(filter, actor), COUNTER_SPELL(unless), stack abilities (B-110), Keyword",
             "a WARD keyword with a cost parameter (mana or life), its trigger built by the engine",
             [r"\bward\b", r"counter (it|that spell|that spell or ability) unless (its controller|that player) pays"]),
    "SURVEIL": ("c", "Surveil N", "701.25 (keyword action)",
                "Verb.SCRY (its sibling), LOOK_AT, MOVE_ZONE ONE_OF/REST",
                "SCRY's twin: look at N, any number into the graveyard, the rest on top in any order "
                "(one verb, or SCRY with a destination role: the gate decides)",
                [r"\bsurveil\b"]),
    "DELAYED_MEMORY": ("c", "Delayed triggers that remember their objects: 'return it at the "
                       "beginning of the next end step', 'sacrifice them'",
                       "603.7a-c, 603.7e, 400.7",
                       "DelayedTrigger, the reflexive trigger's carried bindings (fire_reflexive), result",
                       "a DelayedTrigger whose effect reads the scheduling resolution's objects, one-shot "
                       "('the next end step'); BACKLOG 'a delayed trigger that remembers the objects it is about'",
                       [r"next end step", r"at end of combat, (sacrifice|exile|return|destroy)",
                        r"beginning of (your|the) next upkeep, (return|sacrifice)"]),
    "ENTERS_WITH": ("c", "Entering modified: a moved object enters with counters, tapped and "
                    "attacking, or as another type; other objects enter tapped or with extra counters",
                    "614.1c, 614.12, 122.6, 508.4",
                    "EtBState (self only), MOVE_ZONE tapped_on_enter, TokenSpec.enters_attacking, "
                    "GRANT_TYPE, ReplacementAbility over ZoneChangeEvent (the enter lane)",
                    "an entering-state role on MOVE_ZONE (counters, attacking), and an 'enters with' "
                    "replacement for other objects",
                    [r"onto the battlefield[^.]* with (a|an|one|two|three|four|five|x|\w+) [^.]*counters? on (it|them)",
                     r"enters? with an additional", r"enter (the battlefield )?tapped\b(?! and attacking)[^.]*$",
                     r"tapped and attacking", r"with one fewer"]),
    "BECOMES": ("c", "'Becomes' effects: a noncreature becomes a creature (creature lands, "
                "Gideons, Vehicles and crew), and characteristics overwritten (set colour, set "
                "creature types, 'loses all other card types', a new name)",
                "613.1b-f, 613.4b, 205.1b, 105.3, 702.122 (crew)",
                "GRANT_TYPE (adds type words), SET_PT (base P/T), LOSE_ABILITY, GRANT_ABILITY, COLOR_HAS, DurationEot",
                "one characteristic-setting atom (types replaced or added, colours set; layers 4 and 5) beside "
                "SET_PT and LOSE_ABILITY, creature-ness of a noncreature, and the CREW keyword",
                [r"\bcrew \d", r"it's still a (land|planeswalker)", r"that's still a planeswalker",
                 r"becomes an? [^.]*\d+/\d+ [^.]*creature", r"becomes an? (artifact |legendary )?creature",
                 r"have it become an? [^.]*creature", r"is an? creature with base power",
                 r"loses all (other )?(card types and )?abilities and (is|becomes)",
                 r"becomes? the colou?r", r"becomes an? (white|blue|black|red|green|colorless) ",
                 r"is an? (colorless|white|blue|black|red|green|green and white)[^.]* (creature|land)",
                 r"\bbecomes an? (\d+/\d+ )?(?-i:[A-Z][a-z]+(?: [A-Z][a-z]+)*)(?! in addition)"
                 r"( with base power| and gains|\.| until end of turn)", r"loses all other card types"]),
    "ONCE": ("c", "Activate only once (each turn); this ability triggers only once each turn",
             "602.5b, 603.2h? (limits), 606.3",
             "AbilityActivatedEvent (no ability identity), EVENT_THIS_TURN, ActivatedAbility.condition",
             "an ability-identity slot (or a per-ability count limit) read by activation legality and "
             "the trigger binder",
             [r"activate (this ability )?only once", r"triggers only once each turn"]),
    "DAMAGEDBY": ("c", "History: dealt damage by this creature this turn",
                  "120.1, 603.10?",
                  "EVENT_THIS_TURN, SUBJECT_OF_EVENT_THIS_TURN, DamageDealtEvent (refused per dealer today)",
                  "the history atoms grouped by dealer ('a damage threshold counts per recipient, never per dealer')",
                  [r"dealt damage by [^.]*this turn", r"was dealt (combat )?damage by"]),
    "COUNTS": ("c", "Counts and totals of what happened: 'for each creature destroyed this way', "
               "'life lost this way', 'if at least one ... this way', 'total power 8 or greater'",
               "608.2c, 609.3, 107.3?",
               "QCount(Selector(referent='result', filter)) (round 10), THAT_MANY_COUNT, QProp SUM, CONTROLLER_COUNT_GE",
               "the result register written by DESTROY, the mill lane, SACRIFICE and an EachPlayer, a "
               "'life lost this way' amount, and a predicate comparing a quantity with a threshold",
               [r"(destroyed|milled|sacrificed|put into (a|your|their) graveyards?|discarded|lost) this way",
                r"life lost this way", r"if (at least one|one or more|four or more|you sacrificed|you return)[^.]*this way",
                r"total power (\d+|\w+) or greater", r"have total power"]),
    "DISTINCT": ("c", "Distinct values among a set: names, mana values, mana costs, and picks "
                 "'with different names'",
                 "201.2, 202.1, 202.3",
                 "QDistinctColorCount, NAME_PARTITION_COUNT_GE, QCount",
                 "one distinct-count quantity over a selector by a property, and a 'different names' pick",
                 [r"different (names|mana values?|mana costs?)"]),
    "SAMENAME": ("c", "A name equal to another object's name", "201.2, 201.3",
                 "NAME_EQ (a literal only), NAME_CHOSEN",
                 "NAME_EQ against a referent or a filter",
                 [r"same name as", r"with that name"]),
    "TARGETS": ("c", "A predicate over what a spell or ability targets: 'a spell that targets X', "
                "'becomes the target of a spell', 'costs less if it targets'",
                "115.1, 115.10?, 601.2c, 601.2f",
                "TARGETS_SOURCE, TargetingEvent(filter, actor), STACK_KIND_EQ, CostModifier.condition",
                "a targets predicate with a filter (and TargetingEvent's targeting object), read after "
                "targets are chosen (601.2f)",
                [r"(spell|ability) that targets", r"becomes the target of a spell(?! or ability)",
                 r"if it targets", r"whenever you (become|becomes) the target",
                 r"and/or at least one permanent you control becomes the target"]),
    "LEYLINE": ("c", "Opening-hand actions: 'begin the game with it on the battlefield'",
                "103.6a, 103.6",
                "games.py's setup (no hook), EtBState",
                "a pregame action read from the opening hand (an ability that works there, 113.6?)",
                [r"in your opening hand"]),
    "FLASHPERM": ("c", "Cast as though it had flash", "601.3e?, 702.8, 609.4",
                  "MANA_POLICY, DAMAGE_ASSIGN_POLICY, ATTACK_POLICY, GRANT_ACTIVATION, Keyword.FLASH",
                  "ledger F9's decision first: one POLICY verb with a scope enum before a fourth policy verb",
                  [r"as though (it|they) had flash"]),
    "ALTCOST": ("c", "Alternative costs and costs with two forms: 'rather than pay this spell's "
                "mana cost', 'sacrifice a creature or pay {3}{B}'",
                "118.9, 601.2b, 601.2f",
                "SpellAbility.additional_costs, KickerAbility, CostModifier(CostDeltaWaiveMana)",
                "an alternative-cost node offered at cast (R5-2's 'alternative' role is the permission's twin)",
                [r"rather than pay", r"as an additional cost to cast this spell, [^.]* or (pay|discard|sacrifice|exile|reveal)"]),
    "OTHERCHOOSER": ("c", "A choice another player makes: 'unless they ...', 'any opponent may', "
                     "the owner's top or bottom, an opponent's pile",
                     "101.4, 608.2d?, 700.2?",
                     "Choose, EachPlayer(ref), OptionalEffect, PAY",
                     "a chooser on Choose (or EachPlayer over the affected player) with the options "
                     "that player can take",
                     [r"unless (that player|they|he or she|any player|an opponent|target opponent) "
                      r"(sacrifices?|discards?|pays? \d+ life|reveals?|puts?|returns?|exiles?|has them)",
                      r"\bany (opponent|player) may\b", r"owner puts it on (their choice of )?the top or bottom",
                      r"(an opponent|target opponent) chooses (one of|a pile)", r"\bpiles?\b"]),
    "COUNTERKIND": ("c", "Counter kinds the IR lacks (stun, incubation, divinity, wish, revival, "
                    "bait, fellowship, stash, ...), a count of one kind, doubling counters",
                    "122.1, 122.1d (stun), 122.6",
                    "CounterKind (7 kinds), PUT_COUNTER, REMOVE_COUNTER, CostRemoveCounter, HAS_COUNTER, "
                    "QProp COUNTER_COUNT (kind-blind)",
                    "CounterKind members with their cards, the stun rule, a kind on COUNTER_COUNT",
                    [r"\b(stun|incubation|divinity|wish|revival|bait|fellowship|stash|time|fade|age|quest|ki|level|"
                     r"shield|oil|study|fate|verse|hatchling|ice|feather|growth|luck|arrow|hour|depletion|storage|"
                     r"gold|foreshadow|pressure|brick|egg|corpse|eon|plague|net|rust|spore|strife|trap|velocity|"
                     r"vitality|wage|isolation|landmark|mine|muster|omen|pin|pupa|silver|blood|bounty|bribery|"
                     r"carrion|coin|credit|crystal|death|delay|despair|devotion|doom|dream|echo|elixir|energy|"
                     r"experience|flame|flood|fungus|fuse|gem|glyph|harmony|healing|hit|hope|hunger|infection|"
                     r"intervention|javelin|judgment|knowledge|manifestation|matrix|mining|mire|music|night|pain|"
                     r"paralyzation|petal|phylactery|polyp|prey|reprieve|ritual|rope|shell|shred|sleep|sleight|"
                     r"slumber|soot|spite|suspect|tower|training|unity|valor|vow|void|wind|wreck|book|dreamstone|"
                     r"enlightened|exalted|keyword|lore) counters?\b", r"double the number of"]),
    "POISON": ("c", "Poison counters on players", "122.1f, 704.5c, 702.90 (infect)",
               "none (players hold no counters in the IR)",
               "player counters of the poison kind and the ten-poison state-based action",
               [r"poison counters?", r"\binfect\b", r"\btoxic\b"]),
    "HANDSIZE": ("c", "Maximum hand size", "402.2, 514.1",
                 "executor.MAX_HAND_SIZE (read by cleanup only)",
                 "a player's maximum hand size as a static and 'for the rest of the game' (BACKLOG B-96)",
                 [r"maximum hand size"]),
    "GAMEEND": ("c", "Game results: 'you win the game', 'can't lose the game', a named player loses",
                "104.2, 104.3, 104.3e?",
                "Verb.LOSE_GAME (no player role)",
                "a player role on LOSE_GAME, a win, and the can't-lose prohibition",
                [r"wins? the game", r"can't lose the game", r"can't win the game",
                 r"(that|target|each) (player|opponent) loses the game"]),
    "PROHIBIT": ("c", "Prohibitions no engine lane consults: can't gain life, can't cast more than "
                 "one spell, can't cast from zones, can't enter from zones",
                 "101.2, 119.7, 601.2?",
                 "PREVENT_EFFECT (consumers: damage, untap, attack, block, activation, counters, draw)",
                 "consumers in cast legality, the life lane and the zone-change lane",
                 [r"can't gain life", r"can't cast more than", r"can't cast spells from",
                  r"can't enter the battlefield", r"spells[^.]* can't be cast"]),
    "MANARIDER": ("c", "Mana with a rider or a history: spend on activations, 'when that mana is "
                  "spent', any type, kept across steps, tapping a creature for mana",
                  "106.4, 106.6, 106.11?, 605.1b",
                  "MANA_POLICY(scope THIS_MANA, filter), ADD_MANA",
                  "a use axis on MANA_POLICY, mana provenance events, and a pool that persists",
                  [r"spend this mana only to [^.]*activate", r"(when|if) that mana is spent", r"mana of any type",
                   r"don't lose this mana", r"tap a (creature|permanent|land) for mana", r"spend mana as though"]),
    "CHOSEN": ("c", "Reads of a chosen quality round 9 left out: mana of the chosen colour, 'is the "
               "chosen type', a spend restriction to the chosen type",
               "607.2d, 106.1?, 205.1",
               "CHOOSE_NAME(quality), NAME_CHOSEN, ADD_MANA, GRANT_TYPE, MANA_POLICY",
               "ADD_MANA reading the choice, GRANT_TYPE of the chosen value, MANA_POLICY over it "
               "(BACKLOG 'A quality chosen as a permanent enters: the cards one piece away')",
               [r"mana of the chosen colou?r", r"is the chosen (type|colou?r)", r"of the chosen type or activate",
                r"for each [^.]*of the chosen type"]),
    "CHANGELING": ("c", "Changeling and 'all creature types'", "702.73a, 205.3m",
                   "SUBTYPE_EQ, GRANT_TYPE, Supply.creature_types",
                   "a CHANGELING keyword read by every creature-type test",
                   [r"\bchangeling\b", r"(all|every) creature types?"]),
    "DOUBLING": ("c", "Doubling replacements: tokens, counters, damage", "614.1a, 616.1",
                 "ReplacementAbility over LifeGainedEvent with QBin (Angel of Vitality), "
                 "replacements_for_damage, replacement_for_counter_placement",
                 "replacement actions for created tokens and placed counters, damage multiplied, "
                 "with the 616.1 order asked",
                 [r"double that damage", r"twice that many", r"deals? double"]),
    "DISCARD": ("c", "Discard as an event: 'whenever you discard', a discard replaced",
                "701.8, 614.1a",
                "MOVE_ZONE hand -> graveyard (27 trees), Verb.DISCARD (1), ZoneChangeEvent(HAND -> GRAVEYARD)",
                "a DiscardEvent and B-48's one discard encoding (BACKLOG 'Whenever you discard a card')",
                [r"whenever (you|a player|an opponent|one or more players?|each opponent) discards?",
                 r"causes you to discard", r"would discard"]),
    "SPLIT": ("c", "Divided damage and distributed counters among targets", "601.2d",
              "DEAL_DAMAGE, PUT_COUNTER, TARGET selectors",
              "a division chosen as targets are announced, at least one to each",
              [r"divided (as you choose|evenly)", r"distribute [^.]*counters? among"]),
    "REDIRECT": ("c", "Change the target of a spell or ability", "115.7",
                 "COUNTER_SPELL's stack targets, the designation",
                 "a verb that re-designates a stack object's target",
                 [r"change the target", r"choose new targets for target"]),
    "EXTRACOMBAT": ("c", "An additional combat phase; 'attacks for the first time each turn'",
                    "500.8, 506.1",
                    "DeclareAttackersEvent (no ordinal), EXTRA_TURN",
                    "an extra combat phase and an attack ordinal",
                    [r"additional combat phase", r"attacks for the first time each turn"]),
    "ATTACKED": ("c", "The player or planeswalker a creature attacks", "506.2, 508.1b",
                 "DeclareAttackersEvent.attacked, ATTACK_AGAINST_COUNT_GE, DEFENDING_PLAYER",
                 "a referent for the attacked object, kept if the attacker leaves combat",
                 [r"(player or planeswalker|planeswalker or player|player, planeswalker, or battle) it's attacking"]),
    "OWNER": ("c", "Ownership in filters: 'permanents you don't own'", "108.3",
              "CONTROLLER_IS, Zone(..., OWNER)",
              "an owner predicate",
              [r"you don't own", r"you own but don't control"]),
    "LURE": ("c", "Lure: all creatures able to block it do so", "509.1c",
             "MANDATE_BLOCK (one requirement, met by one blocker)",
             "a requirement on every able blocker, and the declaration's requirement count",
             [r"able to block [^.]* do so", r"must be blocked by all"]),
    "ALONE": ("c", "Can't attack or block alone", "506.5",
              "PREVENT_EFFECT over declarations; BATTALION's group size",
              "a group-size test on the declaration",
              [r"\b(attack|block|attack or block) alone\b"]),
    "DURCONTROL": ("c", "'For as long as you control <source>'", "611.2b",
                   "DurationUntilLeaves, DurationWhileCondition",
                   "a terminal duration ending at a control change",
                   [r"for as long as you control"]),
    "SETLIFE": ("c", "A life total becomes N", "119.5",
                "GAIN_LIFE, LOSE_LIFE",
                "a set-life atom gaining or losing the difference as one event",
                [r"life total become", r"exchange life totals"]),
    "LIFEOTHER": ("c", "Another player's life total in a condition", "119.?",
                  "LIFE_TOTAL_GE (who YOU only since round 8)",
                  "LIFE_TOTAL_GE.who's next value, with its card's tests",
                  [r"(target player|that player|an opponent|target opponent|each opponent|any player) has "
                   r"(exactly )?(\d+|ten|half)[^.]* life", r"has exactly \d+ life"]),
    "SHUFFLEIN": ("c", "'Shuffle into its owner's library': divergence D19's fold",
                  "401.4, 701.24 (shuffle)",
                  "MOVE_ZONE to Zone(LIBRARY) with no position, SHUFFLE, `arrange`",
                  "'on the bottom' written as BOTTOM and a shuffle-in with no order asked (D19)",
                  [r"shuffle (your|their|his or her|its owner's) graveyard into", r"shuffle (it|this card|them) into",
                   r"shuffles? [^.]* into (its|their) owner'?s?'? librar"]),
    "ZONEREPLACE": ("d", "Replacements of a move into a graveyard from anywhere: the zone-change "
                    "replacement lane is consulted at battlefield entries and deaths only",
                    "614.1a, 614.6",
                    "ReplacementAbility over ZoneChangeEvent (Containment Priest's enter lane), replacement_for_death",
                    "every move into a graveyard (resolution, discard, mill, state-based actions) consults it",
                    [r"would be put into (a|your|an opponent's|their) graveyard from anywhere"]),
    "ANYTARGETS": ("c", "'Any number of target X'", "115.1, 601.2c",
                   "Selector(mode=TARGET) refuses QUnbounded; CHOOSE QUnbounded",
                   "an unbounded TARGET count, asked pick by pick with a stop",
                   [r"any number of target"]),
    "TARGETLINK": ("c", "Targets constrained by each other: controlled by different players, from "
                   "a single graveyard, a target player then cards in that player's graveyard, "
                   "two target players each acting",
                   "115.3, 601.2c",
                   "several TARGET slots, EachPlayer(ref referent)",
                   "a constraint across target slots",
                   [r"controlled by different players", r"from a single graveyard", r"two target players",
                    r"target cards from (their|that player's) graveyard"]),
    "COSTREF": ("c", "The objects a cost was paid with: 'the sacrificed creature's power'",
                "601.2h, 608.2h",
                "the result register (effects only), a reflexive trigger's carried bindings",
                "a register for the objects a cost moved, read by last known information",
                [r"sacrificed (creature|permanent|artifact|land)'s", r"the (sacrificed|exiled|discarded) (creature|card)'s"]),
    "PAYX": ("c", "'You may pay {X}' inside a resolving ability", "107.1b, 107.3a?, 118.?",
             "Verb.PAY, QX, reflexive triggers", "X chosen as the payment is made and read after it",
             [r"pay \{X\}"]),
    "DRAWSTEP": ("c", "Draw-step triggers", "504.1, 504.2",
                 "TurnPhaseEvent(phase) (no DRAW phase), StepEvent (no trigger listens)",
                 "a DRAW value for the turn-phase event",
                 [r"draw step"]),
    "TOUGHCMP": ("c", "Toughness-only comparisons ('with toughness 4 or greater')", "208.?",
                 "POWER_LE/GE (power only), PT_LE/GE (both components)",
                 "TOUGHNESS_LE/GE, POWER_LE/GE's twins",
                 [r"toughness (\d+|x) or (greater|less)", r"toughness (less|greater) than"]),
    "GRANTOR": ("c", "A granted ability that names the object granting it ('Equipped creature has "
                "\"{1}, {T}, Tap Fishing Pole: Put a bait counter on Fishing Pole.\"')", "113.10?, 611.3?",
                "GRANT_ABILITY; IS_SOURCE in a granted ability is the grantee (round 9's refusal 4)",
                "a referent for the granting object inside a granted ability", []),
    "TOKENLEGEND": ("c","Legendary tokens: TokenSpec has no supertypes, so the legend rule never "
                    "sees one", "111.4, 704.5j", "TokenSpec (no supertypes field), the legend rule (executor)",
                    "a supertypes field on TokenSpec", [r"create [^.]*, a legendary [^.]*token"]),
    "SACSUBJECT": ("c", "'When you sacrifice this Aura': SacrificeEvent names no subject", "701.21, 603.6c",
                   "SacrificeEvent(actor), ZoneChangeEvent(BATTLEFIELD -> GRAVEYARD) (which a destroy also fires)",
                   "a subject filter on SacrificeEvent", [r"when(ever)? you sacrifice (this|~|it)"]),
    "EACHTYPE": ("c", "Choose a permanent of each permanent type, sacrifice the rest", "205.2a, 701.21",
                 "SACRIFICE, Choose", "a choice over the types of permanents",
                 [r"of each (permanent|card) type and sacrifices"]),
    "MODEMEMORY": ("c", "Modes remembered across resolutions: 'choose one that hasn't been chosen'",
                   "700.2", "Choose", "a per-object record of modes chosen",
                   [r"hasn't been chosen"]),
    "RESOLVEDCOUNT": ("c", "'If this is the second time this ability has resolved this turn'",
                      "603.?", "EVENT_THIS_TURN", "a count of one ability's resolutions",
                      [r"time this ability has resolved"]),
    "EXCESS": ("c", "Excess damage", "120.4a?", "DEAL_DAMAGE, QProp AMOUNT",
               "the damage beyond lethal as a quantity", [r"excess damage"]),
    "PARTITION": ("c", "One look window split into per-kind picks: 'an Angel card, a Demon card, "
                  "and/or a Dragon card'", "608.2c",
                  "ONE_OF/REST, ALL over the window", "a pick of at most one card per kind",
                  [r"and/or an? [A-Z]\w+ card from among"]),
    "TRIGGERCAUSE": ("c", "Triggers caused by a permanent entering trigger again (Panharmonicon)",
                     "603.2", "AbilityTriggerEvent, TRIGGER_ADDITIONAL (Sanctum of All)",
                     "the triggering event's kind on AbilityTriggerEvent",
                     [r"causes a triggered ability", r"triggers an additional time"]),
    "NAMEDLOCK": ("c", "'As this enters, look at an opponent's hand, then choose a card name', and "
                  "a lock on the named sources",
                  "614.12a, 602.5?, 605.1a",
                  "EtBState(effect=CHOOSE_NAME), NAME_CHOSEN, PREVENT_EFFECT over AbilityActivatedEvent(NON_MANA)",
                  "an EtBState effect beyond CHOOSE_NAME, and the lock keyed by the chosen name (B-109)",
                  [r"sources with the chosen name", r"look at an opponent's hand, then choose"]),
    "REPLACE": ("c", "Resolving replacement effects bound to an object, from a permanent's ability "
                "or a permission cast ('if it would die this turn, exile it instead' on a "
                "planeswalker; B-99's rider)",
                "614.1a, 614.12?, 608.2g",
                "the card-level ReplacementAbility of instants and sorceries (B-77), replacement_for_death",
                "R5-12 Verb.REPLACE (§10), never built",
                [r"if that (spell|card) would be put into (your|a) graveyard"]),
    "ABILITIESOF": ("c", "Has all activated abilities of another card", "613.1f",
                    "GRANT_ABILITY (a fixed ability)", "a grant of another object's abilities",
                    [r"has all activated abilities of"]),
    "DAMAGEASSIGN": ("c", "Assign combat damage equal to toughness", "510.1a, 510.1c?",
                     "DAMAGE_ASSIGN_POLICY (scope AS_UNBLOCKED only)", "a second scope value",
                     [r"assigns? combat damage equal to its toughness"]),
    "DELAYEDNEXT": ("c", "One-shot delayed triggers on the next event: 'when you next cast an "
                    "instant or sorcery spell this turn'", "603.7c",
                    "DelayedTrigger, CastSpellEvent, AbilityActivatedEvent",
                    "a DelayedTrigger that fires once on its event and lapses at end of turn",
                    [r"when you next cast", r"the next time (you|a|an)"]),
    "SEETHETRUTH": ("d", "A look's 'instead' clause compiles as an extra step (See the Truth)",
                    "608.2c, 614.1a?", "Conditional(else)", "the compiler's look templates choose "
                    "between the two outcomes (BACKLOG 'See the Truth's ... branch compiles wrong')",
                    [r"cast from anywhere other than your hand"]),
    "GIVECONTROL": ("d", "Control given to another player: GAIN_CONTROL's executor raises on any "
                    "controller but YOU", "611.2, 108.4?",
                    "GAIN_CONTROL(controller, duration, target), the executor's control overlay",
                    "the overlay for a named recipient (\"target opponent gains control\"; \"an opponent\" "
                    "is a choice in multiplayer)",
                    [r"(target opponent|an opponent|that player|target player|its owner|each opponent) gains control of",
                     r"exchange control"]),
    "EACHPLAYERTARGET": ("d","A trigger's 'target player sacrifices': the trigger designation "
                         "scan does not read EachPlayer.ref", "603.3d, 701.21",
                         "EachPlayer(ref=TARGET_PLAYER), SACRIFICE (Run Afoul's spell shape)",
                         "binding._designated_player_refs reads EachPlayer.ref (Gatekeeper's note)",
                         [r"^(when|whenever|at)\b[^.]*, (if [^,]*, )?target (player|opponent) sacrifices"]),
    # ------------------------------------------------------------------ rulings (no IR change)
    "R_TWOEVENTS": ("r", "Ruling: 'When this enters or dies/attacks' is one TriggeredAbility per "
                    "event, in printed order (no template or record has the shape)",
                    "603.1, 603.2", "TriggeredAbility, ZoneChangeEvent, CreatureDiesEvent, DeclareAttackersEvent",
                    "a MAPPER_GUIDE line", [r"enters or (dies|attacks|leaves)"]),
    "R_ITSCONTROLLER": ("r", "Ruling: 'N damage to that creature's controller' is the verified M20 "
                        "Chandra, Flame's Fury form (ALL over Zone(PLAYER) with CONTROLLER_IS a "
                        "referent); MAPPER_GUIDE's 'no encoding yet' line is stale",
                        "115.1, 608.2h", "DEAL_DAMAGE, Selector(referent='target'), CONTROLLER_IS",
                        "BACKLOG 'N damage to that creature's controller: two answers, one of them stale'",
                        [r"damage to (that creature's|that permanent's|its|that spell's|that artifact's|that land's) controller"]),
    "R_FOOD": ("r", "Ruling: the canonical Food TokenSpec (Artifact - Food, '{2}, {T}, Sacrifice "
               "this token: You gain 3 life.'), and whether Treasure's keyword marker is its model",
               "111.10b", "TokenSpec, ActivatedAbility, CostSacrifice, GAIN_LIFE; Treasure's TokenSpec (Gadrak)",
               "one TokenSpec form for every Food card; better a compiler template", [r"\bFood\b"]),
}

# What a card in the three sets needs, where it is not (b) or where a (b) card needs a ruling or
# carries a risk. "SET|Name" -> (class, [package ids], note). Every key must name a card that is
# not verified; census.py refuses an unknown key.
CARDS = {
    # ------------------------------------------------------------------ M21 (10 compiled)
    "M21|Chandra, Flame's Catalyst": ("c", ["PERMIT", "REPLACE"],
        "-8's 'Until end of turn, you may cast spells from your hand without paying their mana costs' "
        "is suppressed (KNOWN-GAP, engine-unsupported); -2's rider is R5-12's example"),
    "M21|Chandra, Heart of Fire": ("c", ["PERMIT"], "'you may play cards exiled this way' and 'You may "
        "cast them this turn' suppressed (KNOWN-GAP, engine-unsupported)"),
    "M21|Conspicuous Snoop": ("c", ["PERMIT", "ABILITIESOF"], "cast from the top as a free activation "
        "(the lint's 'free activation', stronger than printed); 'has all activated abilities of that card'"),
    "M21|Demonic Embrace": ("c", ["PERMIT"], "cast from the graveyard with extra costs refused (KNOWN-GAP)"),
    "M21|Double Vision": ("c", ["COPY_SPELL"], "COPY has no executor handler: engine-unsupported"),
    "M21|Furious Rise": ("c", ["PERMIT"], "'You may play that card until ...' suppressed; R5-8's card (D15)"),
    "M21|Mangara, the Diplomat": ("a", [], "compiled whole; G3's inner-filter survivor differs only when an "
        "attacked planeswalker changes control while the trigger waits (S5): a pack-runner op or an "
        "equivalence rule (BACKLOG 'G3 survivors no 2-seat same-set pack can kill')"),
    "M21|Radha, Heart of Keld": ("c", ["PERMIT"], "play lands from the top as a free activation (lint): "
        "R5-3 play_lands"),
    "M21|See the Truth": ("d", ["SEETHETRUTH"], "the cast-from-elsewhere branch gives one card, not three "
        "(known_bugs pack); unreachable in games until a permission casts it"),
    "M21|Sublime Epiphany": ("c", ["COPY_PERM"], "mode 4 'Create a token that's a copy of target creature "
        "you control': COPY unsupported, engine-unsupported"),
    # ------------------------------------------------------------------ M20 (52)
    "M20|Barkhide Troll": ("a", [], "record re-mapped by round 11; waits for blind G2"),
    "M20|Hanged Executioner": ("a", [], "record re-mapped by round 11 (the compiler's tree); waits for blind G2"),
    "M20|Bloodsoaked Altar": ("b", [], "refused by the compiler (the sorcery gate finds no ability to "
        "attach to); every part exists: CostTap, CostLife, CostDiscard, CostSacrifice, CREATE_TOKEN, SORCERY timing"),
    "M20|Diviner's Lockbox": ("b", [], "refused (the same gate fault); CHOOSE_NAME at resolution (Necromentia's "
        "form), REVEAL the top card, Conditional on NAME_CHOSEN, SACRIFICE, DRAW 3"),
    "M20|Leyline of Abundance": ("c", ["LEYLINE", "MANARIDER"], "opening hand; 'Whenever you tap a creature "
        "for mana, add an additional {G}' (a triggered mana ability, 605.1b)"),
    "M20|Kethis, the Hidden Hand": ("c", ["PERMIT"], "cost expressible since round 11; the graveyard play permission"),
    "M20|Rienne, Angel of Rebirth": ("c", ["DELAYED_MEMORY"], "'return it to its owner's hand at the beginning "
        "of the next end step'"),
    "M20|Loxodon Lifechanter": ("c", ["SETLIFE"], "'have your life total become the total toughness ...'"),
    "M20|Frilled Sandwalla": ("c", ["ONCE"], "'Activate only once each turn': without it the pump repeats"),
    "M20|Gargos, Vicious Watcher": ("c", ["TARGETS"], "'becomes the target of a spell' (not abilities)"),
    "M20|Loyal Pegasus": ("c", ["ALONE"], "'can't attack or block alone'"),
    "M20|Flood of Tears": ("c", ["COUNTS"], "'If you return four or more nontoken permanents you control this way'"),
    "M20|Vivien, Arkbow Ranger": ("c", ["SPLIT"], "+1 distributes two counters; the -5's 'outside the game' "
        "needs a label (Labels)"),
    "M20|Season of Growth": ("c", ["TARGETS"], "'cast a spell that targets a creature you control'"),
    "M20|Renowned Weaponsmith": ("c", ["MANARIDER"], "'Spend this mana only to cast artifact spells or "
        "activate abilities of artifacts'"),
    "M20|Chandra's Outrage": ("b", ["R_ITSCONTROLLER"], "needs-atom note stale: the verified Chandra, Flame's "
        "Fury form encodes '2 damage to that creature's controller'"),
    "M20|Leyline of Sanctity": ("c", ["LEYLINE"], "'You have hexproof' compiles since 2026-11-13"),
    "M20|Leyline of Combustion": ("c", ["LEYLINE", "TARGETS"], "once per targeting spell over you and your "
        "permanents; 'that player' is the targeting object's controller"),
    "M20|Agent of Treachery": ("c", ["OWNER"], "'permanents you don't own'"),
    "M20|Scorch Spitter": ("c", ["ATTACKED"], "'the player or planeswalker it's attacking'"),
    "M20|Rule of Law": ("c", ["PROHIBIT"], "'can't cast more than one spell each turn'"),
    "M20|Scuttlemutt": ("c", ["BECOMES"], "'becomes the color or colors of your choice'"),
    "M20|Chandra, Acolyte of Flame": ("c", ["DELAYED_MEMORY", "REPLACE"], "0: 'Sacrifice them at the beginning "
        "of the next end step'; -2's cast is the existing one-shot CAST (M21 Chandra, Flame's Catalyst's compiled "
        "-2), its rider is B-99 (the spell resolves into the graveyard)"),
    "M20|Kaalia, Zenith Seeker": ("c", ["PARTITION"], "one Angel, one Demon and one Dragon from one look"),
    "M20|Glint-Horn Buccaneer": ("c", ["DISCARD"], "'Whenever you discard a card'"),
    "M20|Gorging Vulture": ("c", ["COUNTS"], "'for each creature card milled this way': the mill writes no result"),
    "M20|Scheming Symmetry": ("c", ["TARGETLINK"], "'Choose two target players. Each of them searches'"),
    "M20|Grafdigger's Cage": ("c", ["PROHIBIT"], "can't enter from graveyards or libraries; can't cast from them"),
    "M20|Prized Unicorn": ("c", ["LURE"], ""),
    "M20|Chandra, Awakened Inferno": ("c", ["REPLACE"], "-X's 'would die this turn, exile it instead' from a "
        "planeswalker ability"),
    "M20|Legion's End": ("c", ["SAMENAME"], ""),
    "M20|Yarok, the Desecrated": ("c", ["TRIGGERCAUSE"], ""),
    "M20|Mystic Forge": ("c", ["PERMIT"], "BACKLOG says re-map it (its cast can be countered since 851d652), "
        "but the cast-from-the-top permission is a free activation, which the costs lint refuses"),
    "M20|Repeated Reverberation": ("c", ["COPY_SPELL", "DELAYEDNEXT"], ""),
    "M20|Embodiment of Agonies": ("c", ["DISTINCT"], "different mana costs"),
    "M20|Leyline of Anticipation": ("c", ["LEYLINE", "FLASHPERM"], ""),
    "M20|Field of the Dead": ("c", ["DISTINCT"], "lands with different names"),
    "M20|Dungeon Geists": ("c", ["DURCONTROL"], ""),
    "M20|Sephara, Sky's Blade": ("c", ["ALTCOST"], ""),
    "M20|Thunderkin Awakener": ("c", ["DELAYED_MEMORY", "ENTERS_WITH", "TOUGHCMP"], "toughness less than "
        "its toughness; returned tapped and attacking; sacrificed at the next end step"),
    "M20|Shared Summons": ("c", ["DISTINCT"], "two creature cards with different names"),
    "M20|Masterful Replication": ("c", ["COPY_PERM"], "'becomes a copy of that artifact until end of turn'"),
    "M20|Loaming Shaman": ("c", ["ANYTARGETS", "TARGETLINK"], ""),
    "M20|Pattern Matcher": ("c", ["SAMENAME"], ""),
    "M20|Chandra's Regulator": ("c", ["COPY_SPELL"], "copy a loyalty ability"),
    "M20|Unholy Indenture": ("c", ["ENTERS_WITH"], "'return ... with a +1/+1 counter on it'"),
    "M20|Gauntlets of Light": ("c", ["DAMAGEASSIGN"], ""),
    "M20|Cerulean Drake": ("c", ["TARGETS"], "'Counter target spell that targets you'"),
    "M20|Aether Gust": ("c", ["OTHERCHOOSER"], "its owner chooses top or bottom"),
    "M20|Golos, Tireless Pilgrim": ("c", ["PERMIT"], "'You may play them this turn without paying'"),
    "M20|Leyline of the Void": ("c", ["LEYLINE", "ZONEREPLACE"], ""),
    "M20|Atemsis, All-Seeing": ("c", ["DISTINCT", "GAMEEND"], "six different mana values; 'that player loses the game'"),
    # ------------------------------------------------------------------ FDN: blind verification
    "FDN|Joraga Invocation": ("a", [], "record; refused once for a forced blocker, fixed 62a1ae2: back to G2"),
    "FDN|Stromkirk Bloodthief": ("a", [], "record, unverified"),
    "FDN|Sphinx of the Final Word": ("a", [], "compiles whole"),
    "FDN|Suspicious Shambler": ("a", [], "compiles whole since round 11"),
    # ------------------------------------------------------------------ FDN: needs-atom records
    "FDN|High Fae Trickster": ("c", ["FLASHPERM"], ""),
    "FDN|Extravagant Replication": ("c", ["COPY_PERM"], ""),
    "FDN|Gatekeeper of Malakir": ("d", ["EACHPLAYERTARGET"], "Run Afoul's shape in a trigger crashes the probe"),
    "FDN|Giant Cindermaw": ("c", ["PROHIBIT"], "'Players can't gain life'"),
    "FDN|Painful Quandary": ("c", ["OTHERCHOOSER"], "'loses 5 life unless they discard a card'"),
    "FDN|Luminous Rebuke": ("c", ["TARGETS"], "'costs {3} less to cast if it targets a tapped creature' "
        "(the cost is determined after targets, 601.2f)"),
    "FDN|Pyromancer's Goggles": ("c", ["MANARIDER", "COPY_SPELL"], ""),
    # ------------------------------------------------------------------ FDN: refused by the compiler
    "FDN|Banner of Kinship": ("c", ["CHOSEN", "COUNTERKIND"], "fellowship counters; an anthem per counter of one kind"),
    "FDN|Cultivator's Caravan": ("c", ["BECOMES"], "Vehicle: crew"),
    "FDN|Ravenous Amulet": ("b", [], "refused by the sorcery-gate fault; soul counters exist (CounterKind.SOUL); "
        "COUNTER_COUNT is kind-blind but only soul counters go on it"),
    "FDN|Secluded Courtyard": ("c", ["CHOSEN", "MANARIDER"], "spend restriction to the chosen type, activations included"),
    "FDN|Tinybones, Bauble Burglar": ("c", ["DISCARD", "PERMIT", "COUNTERKIND", "OWNER", "MANARIDER"], "stash counters; "
        "play cards you don't own from exile; mana of any type"),
    # ------------------------------------------------------------------ FDN: partly compiled, (c)/(d)
    "FDN|Abyssal Harvester": ("c", ["COPY_PERM"], "token copy 'except it's a Nightmare'"),
    "FDN|Adaptive Automaton": ("c", ["CHOSEN"], "'is the chosen type in addition'"),
    "FDN|Aurelia, the Warleader": ("c", ["EXTRACOMBAT"], ""),
    "FDN|Authority of the Consuls": ("c", ["ENTERS_WITH"], "'Creatures your opponents control enter tapped'"),
    "FDN|Ayli, Eternal Pilgrim": ("c", ["COSTREF"], "'life equal to the sacrificed creature's toughness'; the "
        "starting-life gate is Speaker of the Heavens' verified form"),
    "FDN|Biogenic Upgrade": ("c", ["SPLIT", "COUNTERKIND"], "distribute, then double the +1/+1 counters"),
    "FDN|Blasphemous Edict": ("c", ["ALTCOST"], ""),
    "FDN|Bolt Bend": ("c", ["REDIRECT"], ""),
    "FDN|Bulk Up": ("c", ["PERMIT"], "flashback; 'Double target creature's power' maps (+X/+0, X its power)"),
    "FDN|Cackling Prowler": ("c", ["WARD"], ""),
    "FDN|Carnelian Orb of Dragonkind": ("c", ["MANARIDER"], "'If that mana is spent on a Dragon creature spell'"),
    "FDN|Cephalid Inkmage": ("c", ["SURVEIL"], ""),
    "FDN|Chandra, Flameshaper": ("c", ["PERMIT", "COPY_PERM", "SPLIT", "ANYTARGETS"], "+2 impulse; +1 token copy with haste and a sacrifice trigger; -4 divided among any number of targets"),
    "FDN|Charming Prince": ("c", ["DELAYED_MEMORY"], "mode 3's return at the next end step; the compiled tree "
        "holds an orphaned cast carrier (BACKLOG)"),
    "FDN|Crawling Barrens": ("c", ["BECOMES"], ""),
    "FDN|Curator of Destinies": ("c", ["OTHERCHOOSER"], "an opponent chooses a pile"),
    "FDN|Darksteel Colossus": ("c", ["ZONEREPLACE", "SHUFFLEIN"], ""),
    "FDN|Deadly Brew": ("c", ["COUNTS"], "'If you sacrificed a permanent this way' after each player sacrifices"),
    "FDN|Demonic Pact": ("c", ["MODEMEMORY"], ""),
    "FDN|Desecration Demon": ("c", ["OTHERCHOOSER"], "'any opponent may sacrifice a creature'"),
    "FDN|Dictate of Kruphix": ("c", ["DRAWSTEP"], ""),
    "FDN|Divine Resilience": ("c", ["ANYTARGETS"], "kicked: 'any number of target creatures you control'"),
    "FDN|Doubling Season": ("c", ["DOUBLING"], ""),
    "FDN|Drake Hatcher": ("c", ["COUNTERKIND"], "incubation counters"),
    "FDN|Dread Summons": ("c", ["COUNTS"], "'For each creature card put into a graveyard this way'"),
    "FDN|Eaten Alive": ("c", ["ALTCOST"], "an additional cost with two forms"),
    "FDN|Eaten by Piranhas": ("c", ["BECOMES"], "'is a black Skeleton creature with base power and toughness 1/1'"),
    "FDN|Electroduplicate": ("c", ["COPY_PERM", "PERMIT"], ""),
    "FDN|Etali, Primal Storm": ("c", ["PERMIT"], "cast any number from exile without paying (608.2g)"),
    "FDN|Exemplar of Light": ("c", ["ONCE"], "'This ability triggers only once each turn'"),
    "FDN|Exsanguinate": ("c", ["COUNTS"], "'life lost this way'"),
    "FDN|Feldon's Cane": ("c", ["SHUFFLEIN"], "the cost parses since round 11"),
    "FDN|Finale of Revelation": ("c", ["HANDSIZE", "SHUFFLEIN"], "the X >= 10 branch"),
    "FDN|Fishing Pole": ("c", ["COUNTERKIND", "GRANTOR"], "bait counters; the granted ability taps and counts "
        "on the Equipment that grants it"),
    "FDN|Fumigate": ("c", ["COUNTS"], "'for each creature destroyed this way'"),
    "FDN|Fynn, the Fangbearer": ("c", ["POISON"], ""),
    "FDN|Giada, Font of Hope": ("c", ["ENTERS_WITH"], "other Angels enter with additional counters; the spend "
        "restriction maps (MANA_POLICY THIS_MANA)"),
    "FDN|Goblin Negotiation": ("c", ["EXCESS"], ""),
    "FDN|Grappling Kraken": ("c", ["COUNTERKIND"], "stun counters (and their untap rule, 122.1d)"),
    "FDN|Gratuitous Violence": ("c", ["DOUBLING"], ""),
    "FDN|Harbinger of the Tides": ("c", ["FLASHPERM"], "'as though it had flash if you pay {2} more'"),
    "FDN|Herald of Eternal Dawn": ("c", ["GAMEEND"], "'You can't lose the game'"),
    "FDN|Heraldic Banner": ("c", ["CHOSEN"], "mana of the chosen colour"),
    "FDN|Hidetsugu's Second Rite": ("c", ["LIFEOTHER"], "'If target player has exactly 10 life'"),
    "FDN|Homunculus Horde": ("c", ["COPY_PERM"], ""),
    "FDN|Imprisoned in the Moon": ("c", ["BECOMES"], ""),
    "FDN|Infernal Vessel": ("c", ["ENTERS_WITH"], "returned with two counters, a Demon in addition"),
    "FDN|Inspiration from Beyond": ("c", ["PERMIT"], "flashback"),
    "FDN|Kellan, Planar Trailblazer": ("c", ["BECOMES", "PERMIT"], "becomes a Detective/Rogue; 'You may play that card this turn'"),
    "FDN|Koma, World-Eater": ("c", ["WARD"], ""),
    "FDN|Kykar, Zephyr Awakener": ("c", ["DELAYED_MEMORY"], ""),
    "FDN|Leyline Axe": ("c", ["LEYLINE"], ""),
    "FDN|Lightshell Duo": ("c", ["SURVEIL"], ""),
    "FDN|Liliana, Dreadhorde General": ("c", ["EACHTYPE"], "-9"),
    "FDN|Lunar Insight": ("c", ["DISTINCT"], "different mana values"),
    "FDN|Maelstrom Pulse": ("c", ["SAMENAME"], ""),
    "FDN|Maze's End": ("c", ["DISTINCT", "GAMEEND"], "Gates with different names; 'you win the game'; the cost "
        "'Return this land to its owner's hand' is no cost part either"),
    "FDN|Mild-Mannered Librarian": ("c", ["BECOMES", "ONCE"], "'becomes a Werewolf'; 'Activate only once'"),
    "FDN|Mossborn Hydra": ("c", ["COUNTERKIND"], "double the +1/+1 counters (a count of one kind)"),
    "FDN|Muldrotha, the Gravetide": ("c", ["PERMIT"], ""),
    "FDN|Myojin of Night's Reach": ("c", ["COUNTERKIND"], "divinity counters"),
    "FDN|Mystical Teachings": ("c", ["PERMIT"], "flashback"),
    "FDN|Nine-Lives Familiar": ("c", ["COUNTERKIND", "DELAYED_MEMORY", "ENTERS_WITH"], "revival counters"),
    "FDN|Niv-Mizzet, Visionary": ("c", ["HANDSIZE"], ""),
    "FDN|Omniscience": ("c", ["PERMIT"], "free casts from hand: R5-2's 'alternative' (the suppressed sentence "
        "of M21 Chandra, Flame's Catalyst)"),
    "FDN|Ovika, Enigma Goliath": ("c", ["WARD"], "ward with a life payment"),
    "FDN|Perforating Artist": ("c", ["OTHERCHOOSER"], ""),
    "FDN|Predator Ooze": ("c", ["DAMAGEDBY"], ""),
    "FDN|Progenitus": ("c", ["ZONEREPLACE", "SHUFFLEIN"], "'Protection from everything' is a PROTECTION parameter "
        "no card has had"),
    "FDN|Quilled Greatwurm": ("c", ["PERMIT"], "cast from the graveyard by removing six counters from among creatures "
        "(a removal cost the IR refuses today)"),
    "FDN|Ramos, Dragon Engine": ("c", ["ONCE"], "the colour count maps (QDistinctColorCount of the event's spell)"),
    "FDN|Redcap Gutter-Dweller": ("c", ["PERMIT"], ""),
    "FDN|Revenge of the Rats": ("c", ["PERMIT"], "flashback"),
    "FDN|Rite of Replication": ("c", ["COPY_PERM"], ""),
    "FDN|Run Away Together": ("c", ["TARGETLINK"], ""),
    "FDN|Rune-Sealed Wall": ("c", ["SURVEIL"], ""),
    "FDN|Savage Ventmaw": ("c", ["MANARIDER"], "'you don't lose this mana'"),
    "FDN|Self-Reflection": ("c", ["COPY_PERM", "PERMIT"], ""),
    "FDN|Sire of Seven Deaths": ("c", ["WARD"], ""),
    "FDN|Sorcerous Spyglass": ("c", ["NAMEDLOCK"], ""),
    "FDN|Soul-Shackled Zombie": ("c", ["TARGETLINK", "COUNTS"], ""),
    "FDN|Soulstone Sanctuary": ("c", ["BECOMES", "CHANGELING"], ""),
    "FDN|Sphinx of Forgotten Lore": ("c", ["PERMIT"], "grants flashback"),
    "FDN|Steel Hellkite": ("c", ["DAMAGEDBY", "ONCE"], ""),
    "FDN|Strongbox Raider": ("c", ["PERMIT"], ""),
    "FDN|Surrak, the Hunt Caller": ("c", ["COUNTS"], "'total power 8 or greater'"),
    "FDN|Taurean Mauler": ("c", ["CHANGELING"], ""),
    "FDN|Teach by Example": ("c", ["COPY_SPELL", "DELAYEDNEXT"], ""),
    "FDN|Think Twice": ("c", ["PERMIT"], "flashback"),
    "FDN|Thousand-Year Storm": ("c", ["COPY_SPELL"], ""),
    "FDN|Three Tree Mascot": ("c", ["CHANGELING", "ONCE"], "a creature type chosen at resolution: ledger F13's decision"),
    "FDN|Tolarian Terror": ("c", ["WARD"], ""),
    "FDN|Tribute to Hunger": ("c", ["COUNTS"], "'that creature's toughness': the sacrificed creature (SACRIFICE writes no result)"),
    "FDN|Twinflame Tyrant": ("c", ["DOUBLING"], ""),
    "FDN|Uncharted Haven": ("c", ["CHOSEN"], "mana of the chosen colour; B17 does not read 'As it enters'"),
    "FDN|Uncharted Voyage": ("c", ["OTHERCHOOSER", "SURVEIL"], ""),
    "FDN|Undying Malice": ("c", ["ENTERS_WITH"], ""),
    "FDN|Valkyrie's Call": ("c", ["ENTERS_WITH"], ""),
    "FDN|Valorous Stance": ("c", ["TOUGHCMP"], "'with toughness 4 or greater'"),
    "FDN|Vanguard Seraph": ("c", ["SURVEIL"], ""),
    "FDN|Venom Connoisseur": ("c", ["RESOLVEDCOUNT"], ""),
    "FDN|Vizier of the Menagerie": ("c", ["PERMIT", "MANARIDER"], ""),
    "FDN|Wary Thespian": ("c", ["SURVEIL", "R_TWOEVENTS"], "'enters or dies' is also the R_TWOEVENTS ruling"),
    "FDN|Wildborn Preserver": ("c", ["PAYX"], ""),
    "FDN|Wilt-Leaf Liege": ("c", ["DISCARD"], "discard replaced by putting it onto the battlefield"),
    "FDN|Wishclaw Talisman": ("c", ["COUNTERKIND", "GIVECONTROL"], "wish counters; 'An opponent gains control of "
        "this artifact' (the executor refuses control for anyone but YOU); 'Activate only during your turn' maps"),
    "FDN|Witness Protection": ("c", ["BECOMES"], "a new name too"),
    "FDN|Zimone, Paradox Sculptor": ("c", ["COUNTERKIND"], "double each kind of counter"),
    "FDN|Zul Ashur, Lich Lord": ("c", ["WARD", "PERMIT"], ""),
    "FDN|Dryad Militant": ("d", ["ZONEREPLACE"], "the replacement shape exists (Leyline of the Void's note); the "
        "lane is not consulted for every move into a graveyard"),
    "FDN|Kiora, the Rising Tide": ("c", ["TOKENLEGEND"], "Scion of the Deep is a legendary token; minted with no "
        "supertypes it escapes the legend rule (stronger than printed). The loot maps"),
    "FDN|Ordeal of Nylea": ("c", ["SACSUBJECT"], "'When you sacrifice this Aura': a zone change would also fire on "
        "a destroy (stronger than printed)"),
    # ------------------------------------------------------------------ FDN: (b) with a ruling or a risk
    "FDN|Crow of Dark Tidings": ("b", ["R_TWOEVENTS"], ""),
    "FDN|Dreadwing Scavenger": ("b", ["R_TWOEVENTS"], ""),
    "FDN|Bake into a Pie": ("b", ["R_FOOD"], ""),
    "FDN|Cat Collector": ("b", ["R_FOOD"], ""),
    "FDN|Eager Trufflesnout": ("b", ["R_FOOD"], ""),
    "FDN|Midnight Snack": ("b", ["R_FOOD"], "X = QThisTurn LIFE_GAINED"),
    "FDN|Elspeth's Smite": ("b", [], "the existing card-level death replacement of an instant (Scorching "
        "Dragonfire's verified form, B-77); re-bakes if R5-12 lands"),
    "FDN|Fiery Annihilation": ("b", [], "Scorching Dragonfire's form (B-77), plus IS_ATTACHED_TO a referent; "
        "re-bakes if R5-12 lands"),
    "FDN|Harmless Offering": ("d", ["GIVECONTROL"], "'Target opponent gains control of target permanent you "
        "control': GAIN_CONTROL's executor raises NotImplementedError on a controller other than YOU"),
    "FDN|Angelic Destiny": ("b", [], "risk: 'return this card to its owner's hand' after its own Aura went to the "
        "graveyard with the creature (a look-back trigger moving its source card)"),
    "FDN|Hare Apparent": ("b", [], "the deck-construction sentence has no tree (Labels)"),
    "FDN|Hoarding Dragon": ("b", [], "risk: the dies trigger reads the linked exile (IS_EXILED_WITH_SOURCE) after its "
        "source left; check the trace"),
    "FDN|Good-Fortune Unicorn": ("b", [], "risk: FDN round 1's verifier saw its trigger place no counter (BACKLOG, "
        "not investigated)"),
    "FDN|Scrawling Crawler": ("b", [], "risk: 'that player' of a CardDrawnEvent is the drawer; check the referent"),
    "FDN|Apothecary Stomper": ("b", [], "the compiled tree holds an orphaned cast carrier (BACKLOG); the record replaces it"),
    "FDN|Prayer of Binding": ("b", [], "orphaned cast carrier (BACKLOG); R5-1's exile-until-leaves form"),
    "FDN|Wardens of the Cycle": ("b", [], "orphaned cast carrier (BACKLOG)"),
}

# Out-of-scope labels: a card or a sentence the engine will not model, with the reason.
LABELS = {
    "M20|Vivien, Arkbow Ranger": ("sentence", "the -5's 'reveal a creature card you own from outside the game': "
        "CR 400.11 outside-the-game cards (a sideboard) are not modelled; in the trained formats a player "
        "has none, so the ability reveals nothing. Labelled for good only if the owner rules that self-play "
        "and Commander games have no sideboard; the +1 still needs SPLIT"),
    "FDN|Hare Apparent": ("sentence", "'A deck can have any number of cards named Hare Apparent.' is a "
        "deck-construction rule (CR 100.2a, 903.5b): no in-game tree; the drafter and build_deck must honour it. "
        "Labelled for good: G0's clause trace needs an accepted 'deck rule' clause path"),
}

# The order of work: (id, track, title, packages landed, card groups done, lanes, runs beside,
# conflicts). Track A is card work with no code (records, verdicts, rulings), B the ontology gate
# rounds (an IR change each, one merge per round, 207 §3), C engine, compiler and tool faults (no
# IR change: a fresh-eyes review, no gate). Lanes of B may be built in parallel worktrees when
# their files differ; their merges still go one round at a time.
ORDER = [
    ("A0", "A", "Blind verification of the (a) cards (one batch with 2 plants)", [], ["a"], 0,
     "everything", "none (Mangara's last survivor waits on C1's runner op)"),
    ("A1", "A", "Rulings R_FOOD, R_TWOEVENTS, R_ITSCONTROLLER into MAPPER_GUIDE (coordinator)",
     ["R_FOOD", "R_TWOEVENTS", "R_ITSCONTROLLER"], [], 0, "everything", "MAPPER_GUIDE text only"),
    ("A2", "A", "Mapping wave 1 (M1-M5, five mappers at once), then its blind verification", [],
     ["M1", "M2", "M3", "M4", "M5"], 0, "B and C throughout", "none: records only; the coordinator commits"),
    ("A3", "A", "Mapping wave 2 (M6-M8), given wave 1's lessons and faults, then its blind verification", [],
     ["M6", "M7", "M8"], 0, "B and C throughout", "none"),
    ("C1", "C", "Engine wave: See the Truth's 'instead' branch, a trigger's 'target player sacrifices', "
     "zone-change replacements from anywhere, control given to another player; the pack-runner op for "
     "Mangara's S5",
     ["SEETHETRUTH", "EACHPLAYERTARGET", "ZONEREPLACE", "GIVECONTROL"], [], 2, "A, B1",
     "replacements.py with B10 and B16; the control overlay"),
    ("B1", "B", "Round 12: the permission lane (R5-2 PERMIT_CAST, R5-3 play_lands, R5-8) and R5-12 REPLACE",
     ["PERMIT", "REPLACE"], [], 3, "A, C1; B2-B4 built beside it",
     "legality.py and stack.py with B6, B9, B11, B15"),
    ("B2", "B", "Round 13: 'becomes' effects and changeling (layer 4 and 5 setting, crew)",
     ["BECOMES", "CHANGELING"], [], 2, "B1's build", "layers.py with B3; types of entering objects with B10"),
    ("B3", "B", "Round 14: copies (R5-5 CopyOf: tokens, 'becomes a copy', spells and abilities)",
     ["COPY_PERM", "COPY_SPELL"], [], 2, "B4's build", "layers.py with B2 (merge B2 first); stack.py with B1"),
    ("B4", "B", "Round 15: counter kinds, counts of a kind, the stun rule, poison",
     ["COUNTERKIND", "POISON"], [], 1, "B1-B3 builds", "state-based actions with B12"),
    ("B5", "B", "Round 16: surveil and ward", ["SURVEIL", "WARD"], [], 2, "B4's build",
     "TargetingEvent triggers with B6"),
    ("B6", "B", "Round 17: the designation family: targets predicates, any number of targets, linked "
     "targets, division among targets, changing a target", ["TARGETS", "ANYTARGETS", "TARGETLINK", "SPLIT",
                                                          "REDIRECT"], [], 2, "B7's build",
     "query.py and binding.py with B8 and B17; the cost fold with B1"),
    ("B7", "B", "Round 18: choices another player makes", ["OTHERCHOOSER"], [], 1, "B6's build",
     "asks per seat (features.py) with any round adding an ask kind"),
    ("B8", "B", "Round 19: delayed triggers that remember their objects, and 'when you next'",
     ["DELAYED_MEMORY", "DELAYEDNEXT"], [], 1, "B9's build", "binding.py with B6 and B17"),
    ("B9", "B", "Round 20: registers: what an instruction or a cost acted on, and quantity thresholds",
     ["COUNTS", "COSTREF"], [], 1, "B8's build", "verbs.py registers with B10; pay_costs with B1"),
    ("B10", "B", "Round 21: entering modified (with counters, tapped and attacking; others enter tapped)",
     ["ENTERS_WITH"], [], 1, "B11's build", "MOVE_ZONE with B13; the replacements' enter lane with C1"),
    ("B11", "B", "Round 22: mana riders and the chosen colour's mana", ["MANARIDER", "CHOSEN"], [], 1,
     "B10's build", "payment in legality.py with B1 and B15"),
    ("B12", "B", "Round 23: game rules: win and can't lose, prohibitions, hand size, opening-hand actions",
     ["GAMEEND", "PROHIBIT", "HANDSIZE", "LEYLINE"], [], 2, "B13's build", "state-based actions with B4; setup"),
    ("B13", "B", "Round 24: libraries and names: D19's shuffle-in fold, same name, distinct values",
     ["SHUFFLEIN", "SAMENAME", "DISTINCT"], [], 1, "B12's build", "MOVE_ZONE with B10"),
    ("B14", "B", "Round 25: combat rules: lure, alone, damaged-by history, extra combat, the attacked "
     "object, damage by toughness", ["LURE", "ALONE", "DAMAGEDBY", "EXTRACOMBAT", "ATTACKED", "DAMAGEASSIGN"],
     [], 2, "B15's build", "combat declarations"),
    ("B15", "B", "Round 26: cast options: alternative costs and flash permissions (ledger F9's POLICY first)",
     ["ALTCOST", "FLASHPERM"], [], 1, "B14's build", "the cast lane after B1"),
    ("B16", "B", "Round 27: events and replacements: discard (B-48's fold) and doubling",
     ["DISCARD", "DOUBLING"], [], 2, "B17's build", "re-bakes 27 compiled discard trees; replacements.py with C1"),
    ("B17", "B", "Round 28: limits by ability identity: once each turn, resolution counts, trigger causes",
     ["ONCE", "RESOLVEDCOUNT", "TRIGGERCAUSE"], [], 1, "B16's build", "binding.py and activation legality"),
    ("B18", "B", "Round 29: small vocabulary: toughness tests, draw step, another player's life, legendary "
     "tokens, a sacrifice's subject, a granted ability's grantor, set life, 'for as long as you control', "
     "excess damage, pay X, owner",
     ["TOUGHCMP", "DRAWSTEP", "LIFEOTHER", "TOKENLEGEND", "SACSUBJECT", "GRANTOR", "SETLIFE", "DURCONTROL", "EXCESS",
      "PAYX", "OWNER"], [], 2, "B19's build", "one value or slot each; a round of ten small refusal sets"),
    ("B19", "B", "Round 30: one-card components (the owner's call after note 210)",
     ["EACHTYPE", "MODEMEMORY", "PARTITION", "NAMEDLOCK", "ABILITIESOF"], [], 2, "-",
     "each a component used by one or two printings"),
]
