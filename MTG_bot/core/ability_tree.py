"""The typed ability-tree grammar: the ONE representation, TWO consumers.

docs/DESIGN_CARD_POOL.md step 1: the executor walks this tree and the
encoder reads the same tree. No second shape, no English anywhere: an
English substring is not structure, and a substring match fails silently.
Every node is a frozen dataclass, every validation fails loudly in
``__post_init__``, every node serializes to a tagged dict with a stable
string tag, so ``fingerprint`` is the golden-file key and ``walk`` is what
the executor and the EC-2 unhandled-node rate (docs/METRICS.md §3) walk
the tree with.

Design decisions (each pinned by tests in test_ability_tree*.py):

- **Quantity on every numeric field, without exception**: ``QConst`` (>= 0),
  ``QX``, ``QUnbounded`` ("any number" — Siege Striker, Necromentia),
  ``QAtLeast(n)`` / ``QAtMost(n)`` ("n or more" / "up to n"),
  ``QCount(selector)``, ``QProp(referent, field, agg)``, ``QBin``,
  ``QThisTurn`` and the distinct-count quantities. QProp's referent is
  ``Selector | "source" | "controller" | "target" | "event" | "result"``;
  "event" exists because Brash Taunter ("deals that much damage") and
  Garruk's Harbinger ("look at that many cards") reference the triggering
  event's amount. ``QBinOp.DIV`` is floor division unless the node carries
  a ``Rounding`` policy (Peer into the Abyss: "Round up each time").
  Negative quantities are rejected at construction: signed P/T
  adjustments go through :class:`PtDelta`; the single documented
  exception is ``CostLoyalty.delta`` (a -7 loyalty cost is negative by
  definition).
- **Filter = ``FAtom(pred, typed slots)``**: one atom class with a closed
  per-predicate slot table (``_FATOM_RULES``) instead of one class per
  predicate — smaller encoder tag space, arity and types still enforced.
  ``FAnd(())`` is the universal filter, so "any card" selectors exist.
- **``AtomArgs``** = frozen role -> typed value mapping, stored as ``pairs``
  sorted by role in ``__post_init__`` (stdlib has no hashable frozen dict;
  sorted pairs give value equality, hashability, and
  construction-order-independent canonical form).
- **Duration** = a union of frozen dataclasses, not an enum: an enum
  cannot carry the ``Filter`` that ``DurationWhileCondition`` needs.
- **Cost parts**: tap (``CostTap(target=None)`` = "tap the source" — every
  ``{T}:`` in the pool), generic/coloured/hybrid mana, life, sacrifice,
  discard, put-counter (Mazemind Tome's page-counter cost), loyalty (the
  only signed cost). Empty ``Cost()`` is a free activation.
- **Emblem**: ``CardRecord.emblem: Optional[CardRecord]`` — embedded in its
  planeswalker's record (Basri Ket's emblem). One-directional and
  validated: only a Planeswalker may carry an emblem; the emblem is an
  Emblem-typed token record that itself carries no emblem.
- **Selector.count by mode**: TARGET exact, CHOOSE up-to (``QUnbounded`` =
  any number), ALL ignores count (the compiler writes ``QConst(1)``),
  RANDOM exact; TARGET/RANDOM with ``QUnbounded`` are rejected.
- **Keyword enum**: "Hexproof from X" is HEXPROOF plus a Filter param
  (``_KEYWORD_PARAMS``), not a separate keyword.
- **Events**: structured EventSpecs; ETB is a ZoneChange from anywhere to
  the battlefield, never a substring.
- **Additive fields**: an optional field added to an existing node
  defaults to None (or ``()``) and serializes by OMITTING the key
  (``_OMIT_IF_EMPTY``), so every tree that does not use it keeps
  byte-identical canonical JSON.
- **No orphan guarantee**: a member may have no compiled card yet
  (``Verb.PHASE_IN``); the vocabulary is a hypothesis about the card pool,
  not a census of it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any, get_args

from MTG_bot.core.identity import validate_oracle_id

# The five magic colours. Colourless ("C") is only ever a value for the
# ADD_MANA "color" atom role; ColorSets are always drawn from WUBRG.
_COLORS = ("W", "U", "B", "R", "G")
_COLORLESS = "C"
# _ANY_COLOR: "mana of any one color" — the player adding it picks one
# colour at resolution. DISTINCT from _COLORLESS: "C" means colourless
# mana, "ANY" means a choice among WUBRG.
_ANY_COLOR = "ANY"
# _MANA_POLICY_SCOPES: the MANA_POLICY
# "scope" role vocabulary — THIS_MANA anchors the policy to the mana the
# ability itself added (Vodalian Arcanist's "Spend this mana only to
# cast instant or sorcery spells"), ALL_YOURS is a DurationPermanent
# permission over the player's whole mana pool (Orrery's "you may spend
# mana as though it were mana of any color"). Validated in
# AtomArgs.__post_init__ like the "color" role.
_MANA_POLICY_SCOPES = ("THIS_MANA", "ALL_YOURS")
# _DAMAGE_ASSIGN_SCOPES: the DAMAGE_ASSIGN_POLICY "scope" role vocabulary —
# AS_UNBLOCKED is the "assign its combat damage as though it weren't blocked"
# policy (Garruk, Savage Herald's [−7]). Like MANA_POLICY's, a closed
# vocabulary carried in AtomArgs, with no _SPECS field. AtomArgs validates
# against the union of all scope vocabularies; the per-verb vocabulary is
# enforced on the enclosing Atom (_SCOPE_VOCAB_BY_VERB).
_DAMAGE_ASSIGN_SCOPES = ("AS_UNBLOCKED",)
# _MOVE_JOURNAL_KINDS / _MOVE_POP_ORDERS: the closed vocabularies of the
# MOVE_ZONE atom's two string slots — journal_kind (the event kind the move
# is journalled as: "MILL" for a mill, "MOVE" for every other move) and
# pop_order (a mill takes from the TOP of the library, pinned explicitly so
# it never falls back to a selector-order resolution). AtomArgs vocab-checks
# both, like "color"/"scope"; no other verb uses these slots, so the
# AtomArgs-level check is complete.
_MOVE_JOURNAL_KINDS = ("MOVE", "MILL")
_MOVE_POP_ORDERS = ("TOP",)
# _STACK_KINDS: the closed string vocabulary of
# FAtomPred.STACK_KIND_EQ — the three kinds of stack object (CR 405.1: spells,
# activated abilities, triggered abilities).
_STACK_KINDS = ("ACTIVATED", "SPELL", "TRIGGERED")


# ---- Closed vocabularies (enums) ----


class Verb(Enum):
    """The closed verb vocabulary; each member's comment cites a card that
    needs it.

    The MILL/DISCARD/EXILE shapes compile to the one MOVE_ZONE atom
    (destination + optional from/journal_kind/pop_order slots); the three
    members stay in the enum, but the executor has no handler for them.
    """

    DEAL_DAMAGE = "DEAL_DAMAGE"  # Brash Taunter (deals that much damage to target player or creature)
    DESTROY = "DESTROY"  # Legion's Judgment, Eliminate
    EXILE = "EXILE"  # Angelic Ascension
    DRAW = "DRAW"  # Opt, Frantic Inventory
    MILL = "MILL"  # Carrion Grub ("mill four cards")
    GAIN_LIFE = "GAIN_LIFE"  # Faith's Fetters
    LOSE_LIFE = "LOSE_LIFE"  # Grim Tutor
    ADD_MANA = "ADD_MANA"  # Llanowar Visionary, Treasure token
    CREATE_TOKEN = "CREATE_TOKEN"  # Falconer Adept, Gadrak (Treasure tokens)
    PUT_COUNTER = "PUT_COUNTER"  # Basri's Lieutenant (+1/+1), Malefic Scythe (soul)
    REMOVE_COUNTER = "REMOVE_COUNTER"  # Pestilent Haze ("remove two loyalty counters")
    MODIFY_PT = "MODIFY_PT"  # Defiant Strike, Pestilent Haze (all creatures -2/-2)
    SET_PT = "SET_PT"  # Experimental Overload (Weird tokens' P/T), Tarmogoyf-class dynamic P/T
    GRANT_ABILITY = "GRANT_ABILITY"  # Riddleform (a 3/3 Sphinx creature with flying), Dub (first strike)
    GRANT_TYPE = (
        "GRANT_TYPE"  # Riddleform/Dub: "is a Knight in addition to its other types"
    )
    TAP = "TAP"  # Celestial Enforcer ("tap target creature")
    UNTAP = "UNTAP"  # Traitorous Greed ("untap that creature")
    MOVE_ZONE = "MOVE_ZONE"  # Sublime Epiphany (return to hand), Rise Again
    SEARCH = "SEARCH"  # Grim Tutor, Cultivate
    SHUFFLE = "SHUFFLE"  # Grim Tutor ("then shuffle"), Necromentia
    COUNTER_SPELL = "COUNTER_SPELL"  # Cancel, Lofty Denial
    COPY = "COPY"  # Double Vision ("copy that spell"); the executor has no handler for it
    SACRIFICE = "SACRIFICE"  # Goremand ("each opponent sacrifices a creature")
    DISCARD = "DISCARD"  # Teferi, Master of Time [+1] ("draw a card, then discard a card")
    SCRY = "SCRY"  # Opt ("scry 1"), Riddleform
    REVEAL = "REVEAL"  # Track Down, Garruk's Harbinger
    LOOK_AT = "LOOK_AT"  # See the Truth, Garruk's Harbinger
    ATTACH = "ATTACH"  # Short Sword / Malefic Scythe (Equip)
    GAIN_CONTROL = "GAIN_CONTROL"  # Traitorous Greed
    PREVENT_EFFECT = "PREVENT_EFFECT"  # Faith's Fetters ("can't attack or block"), hexproof/protection statics
    PHASE_IN = "PHASE_IN"  # no card in the pool uses it (PHASE_OUT's counterpart)
    PHASE_OUT = "PHASE_OUT"  # Teferi, Master of Time [-3]
    EXTRA_TURN = "EXTRA_TURN"  # Teferi, Master of Time [-10] ("take two extra turns")
    END_TURN = "END_TURN"  # Discontinuity ("end the turn")
    MANDATE_ATTACK = "MANDATE_ATTACK"  # Pirate token: "creatures you control attack each combat if able"
    MANDATE_BLOCK = "MANDATE_BLOCK"  # Canopy Stalker: "must be blocked if able"
    CAST = "CAST"  # cast a spell from a zone (top-of-library via Zone.position; graveyard recasts; cost waivers / extra costs)
    PAY = "PAY"  # pay a cost as an effect ("you may pay {2}", with an "if you do" continuation)
    LOSE_GAME = (
        "LOSE_GAME"  # "the player who cast this spell loses the game" (no roles)
    )
    FLIP_COIN = (
        "FLIP_COIN"  # "flip a coin" (no roles; outcome gated by FAtomPred.FLIP_WON)
    )
    # CHOOSE: "You choose a noncreature, nonland card from it" (Duress) —
    # the controller picks a set FROM the `target` selector's pool (the
    # anaphoric "it" of the preceding sentence, bound via
    # referent="result"); the choice is recorded as the ability's result
    # for later anaphora.
    CHOOSE = "CHOOSE"
    CHOOSE_NAME = "CHOOSE_NAME"  # "choose a name" (Runed Halo, Necromentia); read back by FAtomPred.NAME_CHOSEN
    FIGHT = (
        "FIGHT"  # "this creature fights another target creature" (Brash
        # Taunter), "it fights up to one target creature you don't control"
        # (Primal Might). Attacker = the source/IT referent, `target` = the
        # fighter.
    )
    LOSE_ABILITY = (
        "LOSE_ABILITY"  # "that permanent loses indestructible" (Soul
        # Sear) — mirrors GRANT_ABILITY's roles.
    )
    # GET_EMBLEM: "you get an emblem with '…'" (Teferi, Master of Time
    # [-X]). A MARKER verb with NO roles: the emblem payload is the
    # card-level emblem record that ``compile_pool`` attaches to its
    # planeswalker, so the quoted emblem text NEVER enters the ability IR.
    GET_EMBLEM = "GET_EMBLEM"
    # ADD_LAND_PLAY: "You may play two additional lands on each of your
    # turns" (Azusa, Lost but Seeking). `count` = the additional plays,
    # `duration` scopes the grant.
    ADD_LAND_PLAY = "ADD_LAND_PLAY"
    # MANA_POLICY: spend-restriction verbs — "Spend this mana only to cast
    # instant or sorcery spells" (Vodalian Arcanist; scope=THIS_MANA,
    # anchored to the ability's own ADD_MANA) and "you may spend mana as
    # though it were mana of any color" (Chromatic Orrery; scope=ALL_YOURS,
    # a DurationPermanent permission). `scope` is the closed
    # _MANA_POLICY_SCOPES pair; `filter` narrows the allowed spend (a
    # CastSpellEvent-shape Filter).
    MANA_POLICY = "MANA_POLICY"
    # GRANT_ACTIVATION: "You may activate loyalty abilities of [targets]
    # whenever you wish" (Teferi, Master of Time, gated by
    # NAME_CONTAINS("Teferi")). `filter` selects the ability-holders,
    # `window` is the optional ActivationWindow the extra activation joins.
    GRANT_ACTIVATION = "GRANT_ACTIVATION"
    # DAMAGE_ASSIGN_POLICY: combat-damage assignment policy — "You may have
    # this creature assign its combat damage as though it weren't
    # blocked." (Garruk, Savage Herald [−7], granted via GRANT_ABILITY over
    # creatures you control). `scope` is the closed _DAMAGE_ASSIGN_SCOPES
    # vocabulary; `filter` narrows the affected damage dealers. The "You
    # may" stays OUTSIDE the atom: the granted StaticAbility holds
    # OptionalEffect(Atom(DAMAGE_ASSIGN_POLICY, ...)).
    DAMAGE_ASSIGN_POLICY = "DAMAGE_ASSIGN_POLICY"
    # TRIGGER_ADDITIONAL (Sanctum of All "that ability triggers an
    # additional time"): the {count} axis of the extra-trigger family — the
    # AbilityTriggerEvent firing re-triggers the ability it matched
    # `count` more times. CR 603.2d: those extra triggers are created
    # WITHOUT a triggering event, so they never re-arm an
    # AbilityTriggerEvent (the executor marks and skips them). Shared
    # encoding for the whole pool family (Panharmonicon, a derived
    # self-count carrier): one verb, reusable count Quantity.
    TRIGGER_ADDITIONAL = "TRIGGER_ADDITIONAL"


class SelectorMode(Enum):
    """How a selector picks its objects (DESIGN_CARD_POOL: one Selector type
    used by targets, statics, counts, triggers, and search)."""

    # TARGET = exactly `count` objects for a concrete count; with a
    # QAtMost(n) count it is the legal designation of "up to n targets":
    # the player chooses 1..n, the effect resolves on 0..remaining
    # (executor clamp).
    TARGET = "TARGET"  # exactly `count` objects, chosen by the effect
    CHOOSE = "CHOOSE"  # up to `count` objects, chosen by a controller
    ALL = "ALL"  # every object in the zone matching the filter (count ignored)
    RANDOM = "RANDOM"  # exactly `count` objects, chosen at random
    # ONE_OF / REST split one selection: ONE_OF takes exactly one object
    # out of the selected set (Waker of Waves' "put one of them in your
    # hand"); REST is everything left after the ONE_OF pick ("the rest into
    # your graveyard", See the Truth) — count is ignored, mirroring ALL.
    ONE_OF = (
        "ONE_OF"  # exactly one of the selected set (needs a concrete count like TARGET)
    )
    REST = (
        "REST"  # everything remaining after the ONE_OF pick (count ignored, like ALL)
    )


class ZoneKind(Enum):
    """Where objects live. ANY = every zone (Necromentia searches "graveyard,
    hand, and library" with one Zone(ANY, opponent))."""

    LIBRARY = "LIBRARY"
    HAND = "HAND"
    BATTLEFIELD = "BATTLEFIELD"
    GRAVEYARD = "GRAVEYARD"
    EXILE = "EXILE"
    COMMAND = "COMMAND"  # commander zone (PHASE_IN lives here)
    STACK = "STACK"  # spells/abilities (COUNTER_SPELL targets here)
    PLAYER = "PLAYER"  # the player object itself — the only non-card target ("target player or players")
    ANY = "ANY"


class ZonePosition(Enum):
    """A position within a zone — the top or bottom of an ordered pile
    (library, graveyard, exile). ``Zone.position`` carries it: "the top
    card of your library", "put on top of its owner's library". None (the
    default) means the zone as a whole and serializes by omitting the
    key."""

    TOP = "TOP"
    BOTTOM = "BOTTOM"


class ControllerRef(Enum):
    """Whose zone. ANY = every controller's zones combined; in a two-player
    game that is both players, which is how "all graveyards" selectors read.
    OPPONENT is per-opponent in multiplayer (the executor evaluates each)."""

    YOU = "YOU"
    OPPONENT = "OPPONENT"
    TARGET_PLAYER = (
        "TARGET_PLAYER"  # "target player" — the spell's target, when it is a player (any player)
    )
    ANY = "ANY"
    ALL_OPPONENTS = "ALL_OPPONENTS"
    OWNER = "OWNER"  # "its owner" — owner-scoped zones ("return to its owner's hand")
    # "target opponent" — the same designated player as TARGET_PLAYER, restricted to an
    # opponent of the controller (CR 102.2, 102.3); "target player" may designate you.
    TARGET_OPPONENT = "TARGET_OPPONENT"
    # "defending player" — the player being attacked in the current combat
    # (CR 506.2). For an attacking creature's ability, or an ability that names an attacking
    # creature, it is the player that creature attacks or the controller of the planeswalker
    # it attacks (CR 508.5). Outside combat there is none, so the ref names no player.
    DEFENDING_PLAYER = "DEFENDING_PLAYER"


#: The refs naming the player a spell or ability designated: "target player" and
#: "target opponent" read the same binding and differ only in who may be designated.
DESIGNATED_PLAYER_REFS = frozenset({ControllerRef.TARGET_PLAYER, ControllerRef.TARGET_OPPONENT})


class QPropField(Enum):
    """Which property QProp reads from its referent. The player-count fields
    only make sense with the "controller" referent; AMOUNT, THIS_WAY_COUNT
    and THAT_MANY_COUNT only with "event"; COUNTER_COUNT with "event",
    "source" (SOUL counters on the source Equipment, Malefic Scythe) or
    "target" (counters on the chosen target, Invigorating Surge) — all
    validated in QProp.__post_init__."""

    POWER = "POWER"
    TOUGHNESS = "TOUGHNESS"
    CMC = "CMC"
    MANA_VALUE = "MANA_VALUE"
    CARDS_IN_HAND = "CARDS_IN_HAND"  # "the number of cards in your hand"
    CARDS_IN_LIBRARY = "CARDS_IN_LIBRARY"  # Peer into the Abyss
    CARDS_IN_GRAVEYARD = "CARDS_IN_GRAVEYARD"  # Liliana, Waker of the Dead [-3]
    LIFE = "LIFE"  # "half your life total" (Peer into the Abyss)
    AMOUNT = "AMOUNT"  # the triggering event's damage amount (Brash Taunter)
    COUNTER_COUNT = "COUNTER_COUNT"  # counters on the event, source or target (Conclave Mentor)
    THIS_WAY_COUNT = "THIS_WAY_COUNT"  # "for each creature tapped this way" (Siege Striker)
    # THAT_MANY_COUNT: the count chosen by the preceding up-to-X choice ("discard
    # up to two … draw that many", Kinetic Augur).
    THAT_MANY_COUNT = "THAT_MANY_COUNT"


class QAgg(Enum):
    """How a multi-object Selector referent collapses to one number. FIRST =
    "the (single) selected object's property"; MAX = Carrion Grub's
    "greatest power among creature cards in your graveyard"."""

    FIRST = "FIRST"
    MAX = "MAX"
    MIN = "MIN"
    SUM = "SUM"


class QBinOp(Enum):
    """Quantity arithmetic. DIV is floor division (//) unless the node
    carries a ``rounding`` policy (see Rounding); rounding is a field, not
    another operator, so the operator set stays closed. The
    (n + 1) // 2 round-up-half idiom stays valid."""

    ADD = "ADD"
    SUB = "SUB"
    MUL = "MUL"
    DIV = "DIV"
    MAX = "MAX"
    MIN = "MIN"


class Rounding(Enum):
    """The explicit rounding POLICY of a QBin DIV (Peer into the Abyss
    "Round up each time."). NONE is "the text states no rounding" (behaves
    as FLOOR, the operator's standing default); CEIL is the MTG rule
    rounding (CR 107.1a, always round up); FLOOR is an explicit "rounded
    down" text. The field rides QBin's DIV only — attaching it to any
    other op raises."""

    NONE = "NONE"
    CEIL = "CEIL"
    FLOOR = "FLOOR"


class ThisTurnKind(Enum):
    """What QThisTurn counts within the current turn — turn-scoped
    quantities ("the life you've gained this turn", "the cards an
    opponent has drawn this turn")."""

    LIFE_GAINED = "LIFE_GAINED"
    CARDS_DRAWN = "CARDS_DRAWN"
    # NONCOMBAT_DAMAGE: total noncombat damage
    # dealt by the referent this turn — Chandra's Incinerator "{X}, where
    # X is the total amount of noncombat damage dealt to your opponents
    # this turn."
    NONCOMBAT_DAMAGE = "NONCOMBAT_DAMAGE"


class FAtomPred(Enum):
    """Atomic filter predicates (the design's ~20; the pool pushed a few
    more). Each row of ``_FATOM_RULES`` names exactly which typed slots the
    predicate takes; anything else raises (see FAtom)."""

    TYPE_EQ = "TYPE_EQ"  # "Creature" in the object's types — Necromentia's search
    SUBTYPE_EQ = "SUBTYPE_EQ"  # "protection from Demons and from Dragons"
    SUPERTYPE_EQ = "SUPERTYPE_EQ"  # "Legendary" / "Basic"
    COLOR_HAS = "COLOR_HAS"  # "hexproof from black"
    COLOR_IN = "COLOR_IN"  # colours are a non-empty subset of the given set
    COLOR_COUNT_GE = (
        "COLOR_COUNT_GE"  # >= 2 = "protection from multicolored" (Basri's Lieutenant)
    )
    CMC_LE = "CMC_LE"  # mana-value thresholds
    CMC_GE = "CMC_GE"  # Fierce Empath: "creature card with mana value 6 or greater"
    PT_LE = "PT_LE"  # both components <= value (documented convention)
    PT_GE = "PT_GE"  # both components >= value
    KEYWORD_HAS = "KEYWORD_HAS"  # "has flying"
    NAME_EQ = "NAME_EQ"  # "cards named Frantic Inventory"
    IS_TAPPED = "IS_TAPPED"
    IS_UNTAPPED = "IS_UNTAPPED"  # Siege Striker
    IS_ATTACKING = "IS_ATTACKING"
    IS_BLOCKING = "IS_BLOCKING"
    HAS_COUNTER = "HAS_COUNTER"  # Basri's Lieutenant: "if it had a +1/+1 counter on it"
    CONTROLLER_IS = "CONTROLLER_IS"  # "target creature you control"
    CONTROLLER_COUNT_GE = (
        "CONTROLLER_COUNT_GE"  # Gadrak: "you control four or more artifacts"
    )
    CONTROLLER_COUNT_LE = "CONTROLLER_COUNT_LE"
    IS_SOURCE = "IS_SOURCE"  # the object is the source of the current ability
    IS_ANY_TARGET = "IS_ANY_TARGET"  # "another target" (Selfless Savior)
    IS_PERMANENT = "IS_PERMANENT"  # on the battlefield, vs a card in a zone
    IS_TOKEN = "IS_TOKEN"  # Gadrak: "nontoken creature that died this turn"
    DIED_THIS_TURN = "DIED_THIS_TURN"  # turn-scoped; Carrion Grub, Gadrak
    WAS_KICKED = (
        "WAS_KICKED"  # ZNR kicker: "if it/this spell was kicked"; evaluated
        # against the judged spell handle; no slots (precedent DIED_THIS_TURN)
    )
    IS_ATTACHED_TO_SOURCE = (
        "IS_ATTACHED_TO_SOURCE"  # Malefic Scythe's "equipped creature"
    )
    POWER_LE = "POWER_LE"  # power <= value (power-only; PT_LE compares both components)
    POWER_GE = "POWER_GE"  # power >= value ("a creature with power 3 or greater")
    NAME_CONTAINS = (
        "NAME_CONTAINS"  # name substring ("a Teferi planeswalker"); NAME_EQ stays exact
    )
    LIFE_GAINED_THIS_TURN_GE = (
        "LIFE_GAINED_THIS_TURN_GE"  # "if you gained N or more life this turn"
    )
    CARDS_DRAWN_THIS_TURN_GE = (
        "CARDS_DRAWN_THIS_TURN_GE"  # "if an opponent drew N or more cards this turn"
    )
    FLIP_WON = "FLIP_WON"  # "if you win the flip" (required who; Tavern Swindler)
    MAY_DONE = (
        "MAY_DONE"  # CR 611.1: the "If you do, X" tail — X executes only
        # when the action before it was done (CR 118.12): a "may" action the
        # player chose and carried out, or a mandatory one that actually
        # happened ("Exile it. If you do, ...").
        # One meaning, one encoding. Handle-free like FLIP_WON; answered from
        # the executor's per-resolution record (the may-offer outcome, or the
        # mandatory step's). No slots (precedent: TARGETS_SOURCE); never
        # re-asks.
    )
    INSTANT_OR_SORCERY_CAST_THIS_TURN = (
        "INSTANT_OR_SORCERY_CAST_THIS_TURN"  # "if you've cast an instant or
        # sorcery spell this turn" (Stormwing Entity; turn-scoped cast tracking;
        # required who)
    )
    TARGETS_SOURCE = (
        "TARGETS_SOURCE"  # "spells your opponents cast that target this creature"
        # — the spell targets the source object (Terror of the Peaks)
    )
    ENTERED_THIS_TURN_FROM = (
        "ENTERED_THIS_TURN_FROM"  # "if it entered from your graveyard"
        # (Archfiend's Vessel; required zone slot)
    )
    CAST_THIS_TURN_FROM = (
        "CAST_THIS_TURN_FROM"  # "or you cast it from your graveyard"
        # (Archfiend's Vessel; required zone + who)
    )
    MOVED_TO_ZONE_THIS_TURN = (
        "MOVED_TO_ZONE_THIS_TURN"  # "a permanent was put into your hand
        # from the battlefield this turn" (Barrin, Tolarian Archmage;
        # required from_zone + to_zone + who)
    )
    WAS_CAST_THIS_TURN = (
        "WAS_CAST_THIS_TURN"  # "it was cast this turn (by who)" (Containment
        # Priest; required who; turn-scoped cast tracking without a zone
        # constraint, unlike CAST_THIS_TURN_FROM)
    )
    NOT_FIRST_DRAW_THIS_STEP = (
        "NOT_FIRST_DRAW_THIS_STEP"  # "not the first card who draws in their
        # draw step" (Teferi's Ageless Insight; required who; evaluated
        # against the drawn card, CardDrawnEvent subject)
    )
    TURN_OF = (
        "TURN_OF"  # "it is <who>'s turn" — "During your turn, …" (Radha,
        # Heart of Keld; required who; the Phase enum carries no turn owner)
    )
    ZONE_COUNT_GE = (
        "ZONE_COUNT_GE"  # "<who> has >= count cards in their <zone>
        # matching inner_filter" (Thieves' Guild Enforcer; required who +
        # zone + inner_filter + count)
    )
    IS_ATTACHED_TO = (
        "IS_ATTACHED_TO"  # the object is attached to the referent object
        # ("Destroy target Equipment attached to that" — Turn to Slag;
        # required referent slot from _QPROP_STR_REFERENTS, e.g. "source")
    )
    NAME_CHOSEN = (
        "NAME_CHOSEN"  # the object's name is the one picked by
        # Verb.CHOOSE_NAME ("cards with that name" — Runed Halo). No slots
        # (precedent: IS_TAPPED).
    )
    IS_EXILED_WITH_SOURCE = (
        "IS_EXILED_WITH_SOURCE"  # the card is in exile AND was exiled by
        # the source object — "the exiled card" permission scoping (Horizon
        # Scholar's "card exiled with ~"). No slots (precedent: IS_TAPPED);
        # evaluated against the ability's source.
    )
    CONTROLLER_COUNT_GT = (
        "CONTROLLER_COUNT_GT"  # the referent controller controls MORE
        # objects matching inner_filter than matching right_inner_filter —
        # Garruk's "you control more creatures than any opponent";
        # dual-filter comparison, the second filter lives in the
        # right_inner_filter slot.
    )
    LIFE_LEAD_OVER_START_GE = (
        "LIFE_LEAD_OVER_START_GE"  # the referent
        # (a player) has gained a net life lead of at least `count` over
        # their starting life total — "if you gained at least 7 life more
        # than your starting life total this game" (Speaker of the Heavens
        # class). The executor reads current-life minus starting-life;
        # the count slot carries the threshold Quantity from the text
        # (the PRED carries slots only — the number is template-side).
    )
    NAME_PARTITION_COUNT_GE = (
        "NAME_PARTITION_COUNT_GE"  # the
        # maximum size of an EXACT-name group over the inner_filter-
        # matched objects the referent controls is >= `count` — "if you
        # control two or more nonland, nontoken permanents with the same
        # name as one another" (Chrome Anchor's Replicator gate). The
        # executor groups the matched objects by exact name and takes
        # the largest group; the PRED carries slots only (inner_filter,
        # count) — the threshold number is template-side.
    )
    ATTACK_AGAINST_COUNT_GE = (
        "ATTACK_AGAINST_COUNT_GE"  # count the
        # triggering event's subject attackers whose ATTACKED object
        # passes inner_filter >= `count` — "if two or more of those
        # creatures are attacking you and/or planeswalkers you control"
        # (Mangara, the Diplomat). The executor reads the
        # declared-attackers list off the DeclareAttackersEvent.
    )
    OPPONENT_OF = (
        "OPPONENT_OF"  # the subject IS a PLAYER who is an opponent of
        # ``who`` — the damage-DESTINATION test "…deals damage TO AN
        # OPPONENT" (Chandra's Pyreling). It rides the DamageDealtEvent
        # ``filter`` over the damaged object, so no event field is needed.
        # A card/permanent subject is FALSE (a permanent is not a player,
        # CR 109.5): damage to an opponent's CREATURE must not satisfy "to
        # an opponent". ``who`` is a ControllerRef or referent Selector
        # (CONTROLLER_IS precedent).
    )
    HAS_KICKER = (
        "HAS_KICKER"  # ZNR kicker: the card HAS a kicker cost (printed,
        # paid or not) — "a card with a kicker ability" menus (Coralhelm
        # Chronicler). No slots (precedent: WAS_KICKED). CR 608.2f:
        # distinct from WAS_KICKED.
    )
    STACK_KIND_EQ = (
        "STACK_KIND_EQ"  # what a stack object is — "counter
        # target SPELL" vs "counter target ACTIVATED or TRIGGERED ability"
        # (CR 405.1, 113.7a: abilities on the stack are not spells). The
        # required string_value is the closed vocabulary _STACK_KINDS
        # (SPELL / ACTIVATED / TRIGGERED); validated per predicate
        # (_FATOM_STRING_VOCAB).
    )
    # Turn history: ONE reading of "what happened this turn" for
    # every event the trigger vocabulary can describe. ``event`` is an
    # EventSpec, matched against the turn's journal rows exactly as a trigger
    # would match it; ``count`` is how much of it must have happened (rows, or
    # the amounts of life and damage rows), within one individual: the player
    # who lost or gained the life, drew the card or cast the spell, or the
    # object dealt the damage ("a player lost 4 or more life this turn").
    EVENT_THIS_TURN = (
        "EVENT_THIS_TURN"  # "if an opponent lost life this turn" (Savage
        # Gorger), "if you didn't cast a spell this turn" (FNot, Nightpack
        # Ambusher), "an opponent has cast a blue or black spell this turn"
        # (Veil of Summer). Required event + count.
    )
    SUBJECT_OF_EVENT_THIS_TURN = (
        "SUBJECT_OF_EVENT_THIS_TURN"  # the JUDGED object is the subject of
        # such an event this turn, as the object it is now (CR 400.7): "target
        # creature that was dealt damage this turn" (Ogre Siegebreaker,
        # Fathom Fleet Cutthroat). Required event + count.
    )


class CounterKind(Enum):
    """Counter types. Pool-verified kinds: +1/+1, incarnation (Nine Lives),
    loyalty (Pestilent Haze), page (Mazemind Tome), soul (Malefic Scythe).
    -1/-1 and charge are standard MTG kinds kept for pool-agnostic grammar."""

    PLUS_1_PLUS_1 = "PLUS_1_PLUS_1"
    MINUS_1_MINUS_1 = "MINUS_1_MINUS_1"
    CHARGE = "CHARGE"
    INCARNATION = "INCARNATION"
    LOYALTY = "LOYALTY"
    PAGE = "PAGE"
    SOUL = "SOUL"


class SpellKind(Enum):
    """SpellAbility kinds — the pool's card classes."""

    INSTANT = "INSTANT"
    SORCERY = "SORCERY"
    CREATURE = "CREATURE"
    ENCHANTMENT = "ENCHANTMENT"
    PLANESWALKER = "PLANESWALKER"
    LAND = "LAND"
    # A noncreature artifact is a permanent spell too (CR 301.1): it resolves onto the
    # battlefield, where a SORCERY would resolve to the graveyard.
    ARTIFACT = "ARTIFACT"


class Keyword(Enum):
    """The pool's keyword abilities. "Hexproof from" is HEXPROOF plus a
    Filter param on the KeywordAbility (Spine Megalodon), not a separate
    keyword.
    """

    FLYING = "FLYING"
    SCRY = "SCRY"  # param: Quantity ("scry 1")
    VIGILANCE = "VIGILANCE"
    LIFELINK = "LIFELINK"
    FLASH = "FLASH"
    ENCHANT = "ENCHANT"
    TRAMPLE = "TRAMPLE"
    PROWESS = "PROWESS"
    REACH = "REACH"
    HEXPROOF = "HEXPROOF"  # optional param: Filter ("hexproof from blue")
    PROTECTION = "PROTECTION"  # param: Filter ("protection from planeswalkers")
    MILL = "MILL"  # param: Quantity
    DEFENDER = "DEFENDER"
    HASTE = "HASTE"
    FIGHT = "FIGHT"
    DEATHTOUCH = "DEATHTOUCH"
    FIRST_STRIKE = "FIRST_STRIKE"
    DOUBLE_STRIKE = "DOUBLE_STRIKE"
    EQUIP = "EQUIP"
    INDESTRUCTIBLE = "INDESTRUCTIBLE"
    TREASURE = "TREASURE"  # the Treasure artifact-type keyword (Gadrak's tokens)
    BATTALION = "BATTALION"  # param: Quantity (Makeshift Battalion)
    MENACE = "MENACE"


class PtDirection(Enum):
    """Direction of a P/T adjustment (keeps every quantity non-negative)."""

    INCREASE = "INCREASE"
    DECREASE = "DECREASE"


class Phase(Enum):
    """TurnPhaseEvent phases, all observed in the pool.

    UPKEEP: "at the beginning of your upkeep" (Sanctum of All). FIRST_MAIN:
    "at the beginning of your first main phase" (Sanctum of Calm Waters).
    END_TURN: "at the beginning of your end step" (Gadrak). COMBAT: "at the
    beginning of combat on your turn" (the three emblems).
    """

    UPKEEP = "UPKEEP"
    FIRST_MAIN = "FIRST_MAIN"
    END_TURN = "END_TURN"
    COMBAT = "COMBAT"


class Step(Enum):
    """StepEvent sub-steps (finer than Phase). No trigger listens to a step:
    the executor's trigger binder rejects StepEvent. UNTAP is not a trigger
    step but a DURATION scope: Frost Breath's "can't untap during their
    controller's next untap step" (see DurationUntilNextStep)."""

    DECLARE_ATTACKERS = "DECLARE_ATTACKERS"
    DEALS_COMBAT_DAMAGE = "DEALS_COMBAT_DAMAGE"
    END_OF_COMBAT = "END_OF_COMBAT"
    UNTAP = "UNTAP"  # the untap step (Frost Breath)


class ActivationWindow(Enum):
    """When an activated ability may be activated. None on ActivatedAbility
    = the default window (play the activation any time you could cast an
    instant); SORCERY = only during the controller's own main phase with
    the stack empty ("Activate only as a sorcery"). The timing slot lives
    ONLY on ActivatedAbility."""

    SORCERY = "SORCERY"
    INSTANT = "INSTANT"


class AbilityKind(Enum):
    """Which activations an :class:`AbilityActivatedEvent` covers.
    Required on the event, never defaulted: "activated abilities
    can't be activated" (Arachnus Web) and "... unless they're mana
    abilities" (Faith's Fetters) are different locks, so an absent kind
    would be a silent pick of one of them.

    ANY = every activated ability; NON_MANA = every activated ability that
    is not a mana ability (CR 605.1a, decided by :func:`is_mana_ability`;
    a loyalty ability is never a mana ability, so a NON_MANA lock covers
    it); LOYALTY = an ability whose cost has a loyalty symbol (CR 606.2,
    :func:`is_loyalty_ability`, a [0] ability included)."""

    ANY = "ANY"
    NON_MANA = "NON_MANA"
    LOYALTY = "LOYALTY"


# ---- Quantity — "Quantity on every numeric field, without exception" ----


@dataclass(frozen=True)
class QConst:
    """A literal, non-negative quantity. Negative quantities are rejected:
    you cannot draw -2 cards, and signed adjustments have their own type
    (PtDelta)."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise ValueError(f"QConst: value must be an int, got {self.value!r}")
        if self.value < 0:
            raise ValueError(f"QConst: negative quantity rejected: {self.value}")


@dataclass(frozen=True)
class QX:
    """The X in the card's cost/effect ({X}{R}{R} costs, X-cost spells)."""


@dataclass(frozen=True)
class QUnbounded:
    """ "Any number of" — an unbounded CHOOSE selector (Siege Striker's "tap
    any number of untapped creatures you control", Necromentia's "any
    number of cards with that name")."""


@dataclass(frozen=True)
class QCount:
    """The number of objects a selector matches (Tarmogoyf-class P/T,
    Frantic Inventory's draw count, Gadrak's "for each nontoken creature
    that died this turn")."""

    selector: Selector

    def __post_init__(self) -> None:
        if not isinstance(self.selector, Selector):
            raise ValueError(
                f"QCount: selector must be a Selector, got {type(self.selector).__name__}"
            )


@dataclass(frozen=True)
class QPartyCount:
    """The number of creatures in YOUR party — the number of DISTINCT
    party classes (Cleric/Rogue/Warrior/Wizard) present among the objects
    a selector matches, 0..4 ("Your party consists of up to one each of
    Cleric, Rogue, Warrior, and Wizard"). Shaped like QDistinctColorCount,
    but the evaluator reads the LIVE type line (printed types plus
    GRANT_TYPE overlays, so class grants change the count), not frozen
    identity colors; different data sources, so the two stay separate.
    Templates pin the population (creatures you control) via the
    selector."""

    selector: Selector

    def __post_init__(self) -> None:
        if not isinstance(self.selector, Selector):
            raise ValueError(
                f"QPartyCount: selector must be a Selector, got {type(self.selector).__name__}"
            )


@dataclass(frozen=True)
class QDistinctColorCount:
    """The number of DISTINCT colors among the objects a selector matches —
    Chromatic Orrery's "{5},{T}: Draw a card for each color among
    permanents you control" (selector = ALL permanents). QAgg has no
    distinct-count aggregation, so this is its own Quantity node; the
    selector names the population it is counted over (QCount's shape)."""

    selector: Selector

    def __post_init__(self) -> None:
        if not isinstance(self.selector, Selector):
            raise ValueError(
                f"QDistinctColorCount: selector must be a Selector, got {type(self.selector).__name__}"
            )


# The closed anaphora referent vocabulary (structured strings, never
# English substrings). "result": the object(s) the previous sentence acted
# on — revealed / chosen / exiled / moved; the anaphoric "it / them / that
# card" binding resolved by the compiler's per-ability result register
# (compiler state, not part of the tree).
_QPROP_STR_REFERENTS = ("source", "controller", "target", "event", "result")


@dataclass(frozen=True)
class QProp:
    """A property of a referent.

    referent = Selector | "source" | "controller" | "target" | "event"
    | "result". field is
    validated against the referent: player-count fields need "controller",
    AMOUNT needs "event". With a Selector referent, `agg` collapses the
    (possibly many) selected objects; a string referent is singular, so agg
    must be FIRST.
    """

    referent: Selector | str
    field: QPropField
    agg: QAgg = QAgg.FIRST

    def __post_init__(self) -> None:
        if (
            not isinstance(self.referent, Selector)
            and self.referent not in _QPROP_STR_REFERENTS
        ):
            raise ValueError(
                f"QProp: referent must be a Selector or one of {_QPROP_STR_REFERENTS}, got {self.referent!r}"
            )
        if not isinstance(self.field, QPropField):
            raise ValueError(
                f"QProp: field must be a QPropField, got {type(self.field).__name__}"
            )
        if not isinstance(self.agg, QAgg):
            raise ValueError(
                f"QProp: agg must be a QAgg, got {type(self.agg).__name__}"
            )
        player_fields = (
            QPropField.CARDS_IN_HAND,
            QPropField.CARDS_IN_LIBRARY,
            QPropField.CARDS_IN_GRAVEYARD,
            QPropField.LIFE,
        )
        if self.field in player_fields and self.referent != "controller":
            raise ValueError(
                f"QProp: {self.field.name} requires the 'controller' referent"
            )
        event_fields = (
            QPropField.AMOUNT,
            QPropField.THIS_WAY_COUNT,
            QPropField.THAT_MANY_COUNT,
        )
        if self.field in event_fields and self.referent != "event":
            raise ValueError(f"QProp: {self.field.name} requires the 'event' referent")
        # COUNTER_COUNT: the event's counter count (Conclave Mentor), the
        # source permanent's (Malefic Scythe's "for each soul counter on
        # this Equipment") or a chosen target's ("double that many
        # counters", Invigorating Surge).
        if self.field is QPropField.COUNTER_COUNT and self.referent not in (
            "event",
            "source",
            "target",
        ):
            raise ValueError(
                "QProp: COUNTER_COUNT requires the 'event', 'source' or "
                "'target' referent"
            )
        if isinstance(self.referent, str) and self.agg is not QAgg.FIRST:
            raise ValueError(
                "QProp: a singular referent cannot aggregate (agg must be FIRST)"
            )


@dataclass(frozen=True)
class QBin:
    """Quantity arithmetic: ADD / SUB / MUL / DIV (floor) / MAX / MIN.

    DIV carries an optional ``rounding`` policy (see Rounding); None is
    omitted from the serialization, so a QBin without one keeps its golden
    bytes."""

    op: QBinOp
    left: Quantity
    right: Quantity
    rounding: "Rounding | None" = None

    def __post_init__(self) -> None:
        if not isinstance(self.op, QBinOp):
            raise ValueError(f"QBin: op must be a QBinOp, got {type(self.op).__name__}")
        for side in (self.left, self.right):
            if not _is_quantity(side):
                raise ValueError(
                    f"QBin: operand must be a Quantity, got {type(side).__name__}"
                )
        if self.rounding is not None:
            if not isinstance(self.rounding, Rounding):
                raise ValueError(
                    f"QBin: rounding must be a Rounding or None, got {self.rounding!r}"
                )
            if self.op is not QBinOp.DIV:
                raise ValueError(
                    f"QBin: rounding is only legal on DIV, got op={self.op.name}"
                )


@dataclass(frozen=True)
class QThisTurn:
    """A quantity scoped to the current turn: how much `kind` `referent`
    has accumulated this turn — QThisTurn(LIFE_GAINED, YOU) = "the life
    you've gained this turn", QThisTurn(CARDS_DRAWN, OPPONENT) = "the
    cards an opponent has drawn this turn"."""

    kind: ThisTurnKind
    referent: ControllerRef

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ThisTurnKind):
            raise ValueError(
                f"QThisTurn: kind must be a ThisTurnKind, got {self.kind!r}"
            )
        if not isinstance(self.referent, ControllerRef):
            raise ValueError(
                "QThisTurn: referent must be a ControllerRef, got "
                f"{type(self.referent).__name__}"
            )


@dataclass(frozen=True)
class QAtLeast:
    """A quantity meaning "at least n" (n >= 1): the minimum a variable
    amount must reach ("choose one or more", Sublime Epiphany), which
    ``QUnbounded()`` cannot express. n = 0 is redundant with the unbounded
    reading, so 0 and negatives are rejected."""

    n: int

    def __post_init__(self) -> None:
        if isinstance(self.n, bool) or not isinstance(self.n, int):
            raise ValueError(f"QAtLeast: n must be an int, got {self.n!r}")
        if self.n < 1:
            raise ValueError(f"QAtLeast: n must be >= 1, got {self.n}")


@dataclass(frozen=True)
class QAtMost:
    """A quantity meaning "up to n" (n >= 1). With a TARGET-mode Selector
    this is the legal designation of "up to n targets": the player may
    choose 1..n legal targets (they are still targeted), and the effect
    resolves on 0..n of them (the executor clamps when targets leave). A
    resolution-time "up to N" that is NOT targeted ("exile up to two cards
    this way") STAYS CHOOSE + QConst(N) — QAtMost is only for the targeted
    designation. n = 0 is a no-op, so 0 and negatives are rejected."""

    n: int

    def __post_init__(self) -> None:
        if isinstance(self.n, bool) or not isinstance(self.n, int):
            raise ValueError(f"QAtMost: n must be an int, got {self.n!r}")
        if self.n < 1:
            raise ValueError(f"QAtMost: n must be >= 1, got {self.n}")


Quantity = (
    QConst
    | QX
    | QUnbounded
    | QCount
    | QDistinctColorCount
    | QPartyCount
    | QProp
    | QBin
    | QThisTurn
    | QAtLeast
    | QAtMost
)


def count_semantics(count: Quantity, n_legal: int) -> tuple[bool, int]:
    """THE legality/count answer for one Quantity over a live population.

    Returns ``(announceable, effective_k)`` where ANNOUNCEABILITY is the
    full-size law of CR 601.2c — "the number of targets must be exactly
    the number stated" — and ``effective_k`` is the ask/designate ceiling
    the executor loop runs against. binding.py (TARGET), selectors.py
    (ONE_OF) and query.py (feasibility) all call THIS; a site may layer its
    resolve-time handling on top (mid-loop depletion resolves as much as
    possible, CR 608.2c) but may not re-decide the announce-time answer:

    * QConst(N)   — "N targets" EXACT: unannounceable with fewer than N
      legal objects. Clamping (asking over fewer) is WRONG here. k = N,
      never clamped.
    * QAtMost(N)  — "up to N": announceable iff at least one legal object
      exists (a nonempty TARGET slot must designate >= 1; an empty
      population designates nothing and resolves doing nothing, CR
      603.4). k = min(N, n_legal).
    * QAtLeast(N) — "N or more": announceable iff n_legal >= N; the loop
      takes the ceiling. k = n_legal.
    * QUnbounded  — "any number": always announceable (the EMPTY set is a
      legal choice). k = n_legal.

    QX/QCount/... must be RESOLVED by the caller to a QConst before this
    call — raising here is the loud flag, never a guess."""
    if isinstance(count, QConst):
        return n_legal >= count.value, count.value
    if isinstance(count, QAtMost):
        return n_legal >= 1, min(count.n, n_legal)
    if isinstance(count, QAtLeast):
        return n_legal >= count.n, n_legal
    if isinstance(count, QUnbounded):
        return True, n_legal
    raise NotImplementedError(
        f"count_semantics: unresolved quantity {count!r} — resolve QX-class"
        " counts to QConst at the call site before asking (flag, never guess)"
    )


# ---- Zones and the selector ----


@dataclass(frozen=True)
class Zone:
    """A (kind, controller) zone. ``position`` pins a slot inside an
    ordered pile (TOP/BOTTOM of a library/graveyard/exile — "the top
    card of your library", "put on top of its owner's library"); None is
    the zone as a whole and serializes by omitting the key."""

    kind: ZoneKind
    controller: ControllerRef
    position: ZonePosition | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ZoneKind):
            raise ValueError(f"Zone: kind must be a ZoneKind, got {self.kind!r}")
        if not isinstance(self.controller, ControllerRef):
            raise ValueError(
                f"Zone: controller must be a ControllerRef, got {self.controller!r}"
            )
        if self.position is not None and not isinstance(self.position, ZonePosition):
            raise ValueError(
                f"Zone: position must be a ZonePosition, got {self.position!r}"
            )


@dataclass(frozen=True)
class Selector:
    """The one selector type used by targets, statics, counts, triggers,
    and search (docs/DESIGN_CARD_POOL.md). count semantics by mode: TARGET
    exact (or 1..n designation / 0..remaining resolution with QAtMost),
    CHOOSE up-to (QUnbounded = any), ALL ignores count, RANDOM exact.
    ``zones`` IS the legal-zone SET — "target player or planeswalker" =
    PLAYER ∪ BATTLEFIELD, "library and graveyard" search = LIBRARY ∪
    GRAVEYARD, "target spell or creature" = STACK ∪ BATTLEFIELD, all
    spelled as zone SPECS kept WHOLE (kind + controller + position all
    carry meaning) in one tuple. The set is normalized AT CONSTRUCTION:
    non-empty, deduped and sorted by ``canonical_json`` (Zone is not
    orderable — a bare ``sorted()`` TypeErrors), so construction wording
    order is never observable and worded-order twins share one encoding.
    The field has no empty default: it always serializes.

    ``referent`` binds the selector to an object already in scope instead
    of searching: one of ``_QPROP_STR_REFERENTS`` — "source",
    "controller", "target", "event", "result" (the object(s) the previous
    sentence acted on) — the closed vocabulary shared with ``QProp``;
    "event" = the triggering event's subject object (cast → the cast
    spell; damage_dealt → the damaged recipient; becomes_blocked → the
    blocker; declare_attackers → the attacker; targeting → the new
    target). When set, the selector denotes the bound object and
    ``filter`` (if non-universal) acts as a type-check on it, not a fresh
    search. A referent selector must be ``mode=CHOOSE`` +
    ``count=QConst(1)`` + ``zones == (Zone(ANY, ANY),)`` exactly (a bound
    object is not chosen, and its zone is unknown at compile time);
    violations raise in ``__post_init__``. None (the default) serializes
    by omitting the key."""

    count: Quantity
    mode: SelectorMode
    filter: Filter
    zones: tuple[Zone, ...]
    referent: str | None = None

    def __post_init__(self) -> None:
        if not _is_quantity(self.count):
            raise ValueError(
                f"Selector: count must be a Quantity, got {type(self.count).__name__}"
            )
        if not isinstance(self.mode, SelectorMode):
            raise ValueError(
                f"Selector: mode must be a SelectorMode, got {self.mode!r}"
            )
        if not _is_filter(self.filter):
            raise ValueError(
                f"Selector: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if not isinstance(self.zones, tuple) or not all(
            isinstance(z, Zone) for z in self.zones
        ):
            raise ValueError("Selector: zones must be a tuple of Zone")
        if not self.zones:
            raise ValueError(
                "Selector: zones must be non-empty — the R0 zone-fold replaced "
                "the old zone+zones fields with the single zones SET field"
            )
        if len(self.zones) > 1:
            # Construction normalization (as in _set_sorted): dedup by
            # canonical_json, then sort by it — Zone is not natively
            # orderable, canonical_json is the ONE total order.
            unique: dict[str, Zone] = {}
            for z in self.zones:
                unique.setdefault(canonical_json(z), z)
            object.__setattr__(
                self,
                "zones",
                tuple(sorted(unique.values(), key=canonical_json)),
            )
        if self.mode in (
            SelectorMode.TARGET,
            SelectorMode.RANDOM,
            SelectorMode.ONE_OF,
        ) and isinstance(self.count, QUnbounded):
            raise ValueError(
                f"Selector: mode {self.mode.name} needs a concrete count, not QUnbounded"
            )
        if self.referent is not None:
            if self.referent not in _QPROP_STR_REFERENTS:
                raise ValueError(
                    f"Selector: referent must be one of _QPROP_STR_REFERENTS, got {self.referent!r}"
                )
            if self.mode is not SelectorMode.CHOOSE:
                raise ValueError(
                    f"Selector: referent convention C2 requires mode CHOOSE, got {self.mode.name}"
                )
            if not isinstance(self.count, QConst) or self.count.value != 1:
                raise ValueError(
                    f"Selector: referent convention C2 requires count QConst(1), got {self.count!r}"
                )
            if self.zones != (Zone(ZoneKind.ANY, ControllerRef.ANY),):
                raise ValueError(
                    "Selector: referent convention C2 requires the neutral "
                    f"zone set (Zone(ANY, ANY),), got {self.zones!r}"
                )


# ---- Filters ----


def _set_sorted(items):
    """Construction sort for set-valued fields: sort by ``canonical_json`` —
    the ONE total order over heterogeneous IR elements (``Zone``/enum/dataclass
    elements are not natively orderable, so a bare ``sorted()`` TypeErrors).
    Returns a tuple (``()`` for ``None``)."""
    if items is None:
        return ()
    items = tuple(items)
    if len(items) < 2:
        return items
    return tuple(sorted(items, key=canonical_json))


def _normalize_filter_children(cls, children):
    """Normalization of an ``FAnd``/``FOr`` child list: splice any
    same-class child (flatten), then sort by ``canonical_json``.

    A single-child node is KEPT: a node cannot replace itself inside its
    parent, so the unwrap lives at the COMPILER EMISSION site (the filter
    builders return the lone child) and the V2′ check of
    tools/audit/ontology_conformance.py rejects any new single-child
    emission. Empty children stay empty — ``FAnd(())``
    is the universal filter, ``FOr(())`` matches nothing (both meaningful).
    Splicing needs ``type(k) is cls`` (exact class, not ``isinstance``): a
    ``FAnd`` inside a ``FOr`` is a De Morgan shape, not a duplicate layer.
    """
    kids = list(children)
    while any(type(k) is cls for k in kids):
        kids = [x for k in kids for x in (list(k.children) if type(k) is cls else [k])]
    return _set_sorted(kids)


@dataclass(frozen=True)
class FAnd:
    """Conjunction. ``FAnd(())`` is the universal filter ("any card").

    Children are construction-normalized —
    same-class children spliced, then sorted by ``canonical_json`` — so the
    conjunction is order-free in its bytes (children are a SET; the filter
    evaluates as one AND)."""

    children: tuple[Filter, ...]

    def __post_init__(self) -> None:
        for child in self.children:
            if not _is_filter(child):
                raise ValueError(
                    f"FAnd: child must be a Filter, got {type(child).__name__}"
                )
        kids = _normalize_filter_children(FAnd, self.children)
        if kids != self.children:
            object.__setattr__(self, "children", kids)


@dataclass(frozen=True)
class FOr:
    """Disjunction. ``FOr(())`` is the empty filter (matches nothing).

    Children are construction-normalized like ``FAnd``'s."""

    children: tuple[Filter, ...]

    def __post_init__(self) -> None:
        for child in self.children:
            if not _is_filter(child):
                raise ValueError(
                    f"FOr: child must be a Filter, got {type(child).__name__}"
                )
        kids = _normalize_filter_children(FOr, self.children)
        if kids != self.children:
            object.__setattr__(self, "children", kids)


@dataclass(frozen=True)
class FNot:
    """Negation."""

    inner: Filter

    def __post_init__(self) -> None:
        if not _is_filter(self.inner):
            raise ValueError(
                f"FNot: inner must be a Filter, got {type(self.inner).__name__}"
            )


@dataclass(frozen=True)
class FAtom:
    """An atomic predicate with a closed, per-predicate slot table.

    Design choice (documented in the module docstring): ONE atom class with
    typed slots instead of one class per predicate — the encoder's tag
    space stays small while ``_FATOM_RULES[pred]`` still enforces which
    slots the predicate takes and value validation still runs: an
    unrequested non-default slot, or an invalid slot value, raises.

    Slots:
      string_value — type/subtype/supertype/name comparisons (data, not semantics)
      color        — a single WUBRG colour (COLOR_HAS)
      colors       — a WUBRG set (COLOR_IN)
      count        — Quantity threshold (CMC_LE/GE, PT_LE/GE, COLOR_COUNT_GE,
                     HAS_COUNTER, CONTROLLER_COUNT_GE/LE,
                     LIFE_GAINED_THIS_TURN_GE, CARDS_DRAWN_THIS_TURN_GE,
                     NAME_PARTITION_COUNT_GE, ATTACK_AGAINST_COUNT_GE);
                     a dynamic threshold (QProp/QBin/QCount) is as legal
                     as a literal
      counter_kind — CounterKind (HAS_COUNTER)
      keyword      — Keyword (KEYWORD_HAS)
      who          — ControllerRef | Selector (CONTROLLER_IS,
                     LIFE_GAINED_THIS_TURN_GE, CARDS_DRAWN_THIS_TURN_GE,
                     INSTANT_OR_SORCERY_CAST_THIS_TURN,
                     CAST_THIS_TURN_FROM, MOVED_TO_ZONE_THIS_TURN,
                     WAS_CAST_THIS_TURN, NOT_FIRST_DRAW_THIS_STEP):
                     you|opponent|target-player, or a referent Selector
      inner_filter — a nested Filter (CONTROLLER_COUNT_GE/LE,
                     NAME_PARTITION_COUNT_GE, ATTACK_AGAINST_COUNT_GE)
      zone         — Zone (ENTERED_THIS_TURN_FROM / CAST_THIS_TURN_FROM —
                     "entered from / cast from this zone this turn")
      from_zone,   — Zones (MOVED_TO_ZONE_THIS_TURN — "a permanent was
      to_zone        put into your hand from the battlefield this turn")
      referent     — a referent string from _QPROP_STR_REFERENTS
                     (IS_ATTACHED_TO: "attached to that/source"; same
                     vocabulary as Selector.referent)
      right_inner_filter — a SECOND nested Filter (CONTROLLER_COUNT_GT:
                     "controls more X than Y" — inner_filter counts one
                     side, right_inner_filter the other)
      event        — an EventSpec (EVENT_THIS_TURN /
                     SUBJECT_OF_EVENT_THIS_TURN: the event the turn's
                     journal is searched for)

    The last six slots are omitted from the serialization when None
    (``_OMIT_IF_EMPTY``); the others serialize their null / [] defaults.
    """

    pred: FAtomPred
    string_value: str | None = None
    color: str | None = None
    colors: tuple[str, ...] = ()
    count: Quantity | None = None
    counter_kind: CounterKind | None = None
    keyword: Keyword | None = None
    who: ControllerRef | Selector | None = None
    inner_filter: Filter | None = None
    zone: Zone | None = None
    from_zone: Zone | None = None
    to_zone: Zone | None = None
    referent: str | None = None
    right_inner_filter: Filter | None = None
    event: EventSpec | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pred, FAtomPred):
            raise ValueError(f"FAtom: pred must be a FAtomPred, got {self.pred!r}")
        if self.string_value is not None and (
            not isinstance(self.string_value, str) or not self.string_value.strip()
        ):
            raise ValueError(
                f"FAtom: string_value must be a non-empty str, got {self.string_value!r}"
            )
        if self.color is not None and self.color not in _COLORS:
            raise ValueError(
                f"FAtom: color must be one of {_COLORS}, got {self.color!r}"
            )
        if not isinstance(self.colors, tuple) or not all(
            isinstance(c, str) for c in self.colors
        ):
            raise ValueError("FAtom: colors must be a tuple of str")
        if any(c not in _COLORS for c in self.colors) or len(set(self.colors)) != len(
            self.colors
        ):
            raise ValueError(f"FAtom: colors must be distinct members of {_COLORS}")
        if self.count is not None and not _is_quantity(self.count):
            raise ValueError(f"FAtom: count must be a Quantity, got {self.count!r}")
        if self.counter_kind is not None and not isinstance(
            self.counter_kind, CounterKind
        ):
            raise ValueError(
                f"FAtom: counter_kind must be a CounterKind, got {type(self.counter_kind).__name__}"
            )
        if self.keyword is not None and not isinstance(self.keyword, Keyword):
            raise ValueError(
                f"FAtom: keyword must be a Keyword, got {type(self.keyword).__name__}"
            )
        if self.who is not None and not isinstance(self.who, (ControllerRef, Selector)):
            raise ValueError(
                f"FAtom: who must be a ControllerRef, got {type(self.who).__name__}"
            )
        if self.inner_filter is not None and not _is_filter(self.inner_filter):
            raise ValueError(
                f"FAtom: inner_filter must be a Filter, got {type(self.inner_filter).__name__}"
            )
        if self.right_inner_filter is not None and not _is_filter(
            self.right_inner_filter
        ):
            raise ValueError(
                "FAtom: right_inner_filter must be a Filter, got "
                f"{type(self.right_inner_filter).__name__}"
            )
        if self.zone is not None and not isinstance(self.zone, Zone):
            raise ValueError(
                f"FAtom: zone must be a Zone, got {type(self.zone).__name__}"
            )
        if self.from_zone is not None and not isinstance(self.from_zone, Zone):
            raise ValueError(
                f"FAtom: from_zone must be a Zone, got {type(self.from_zone).__name__}"
            )
        if self.to_zone is not None and not isinstance(self.to_zone, Zone):
            raise ValueError(f"FAtom: to_zone must be a Zone, got {self.to_zone!r}")
        if self.referent is not None and self.referent not in _QPROP_STR_REFERENTS:
            raise ValueError(
                f"FAtom: referent must be one of _QPROP_STR_REFERENTS, got {self.referent!r}"
            )
        if self.event is not None and not _is_event(self.event):
            raise ValueError(
                f"FAtom: event must be an EventSpec, got {type(self.event).__name__}"
            )

        vocab = _FATOM_STRING_VOCAB.get(self.pred)
        if vocab is not None and self.string_value is not None and self.string_value not in vocab:
            # A closed-vocabulary predicate's string_value is a token of
            # its vocabulary, never free text (TYPE_EQ/NAME_EQ stay open data).
            raise ValueError(
                f"FAtom: {self.pred.name} string_value must be one of {vocab}, "
                f"got {self.string_value!r}"
            )
        required, allowed = _FATOM_RULES[self.pred]
        for slot in (
            "string_value",
            "color",
            "colors",
            "count",
            "counter_kind",
            "keyword",
            "who",
            "inner_filter",
            "zone",
            "from_zone",
            "to_zone",
            "referent",
            "right_inner_filter",
            "event",
        ):
            value = getattr(self, slot)
            unset = value is None or (slot == "colors" and value == ())
            if not unset and slot not in allowed:
                raise ValueError(f"FAtom: {self.pred.name} does not take slot {slot!r}")
            if (
                slot in required
                and unset
                and slot
                in (
                    "string_value",
                    "color",
                    "colors",
                    "counter_kind",
                    "keyword",
                    "who",
                    "inner_filter",
                    "zone",
                    "from_zone",
                    "to_zone",
                    "referent",
                    "right_inner_filter",
                    "event",
                )
            ):
                raise ValueError(f"FAtom: {self.pred.name} requires slot {slot!r}")
        if self.pred is FAtomPred.COLOR_IN and not self.colors:
            raise ValueError("FAtom: COLOR_IN requires a non-empty colors tuple")
        if (
            self.pred is FAtomPred.COLOR_COUNT_GE
            and isinstance(self.count, QConst)
            and self.count.value < 1
        ):
            raise ValueError("FAtom: COLOR_COUNT_GE requires count >= 1")
        if (
            self.pred is FAtomPred.HAS_COUNTER
            and isinstance(self.count, QConst)
            and self.count.value < 1
        ):
            raise ValueError("FAtom: HAS_COUNTER requires count >= 1")
        if self.pred in (FAtomPred.EVENT_THIS_TURN, FAtomPred.SUBJECT_OF_EVENT_THIS_TURN):
            # Turn history: "at least once" is QConst(1), written out (the
            # generic loop above does not enforce the count slot).
            if self.count is None:
                raise ValueError(f"FAtom: {self.pred.name} requires slot 'count'")
            if isinstance(self.count, QConst) and self.count.value < 1:
                raise ValueError(f"FAtom: {self.pred.name} requires count >= 1")
            if isinstance(self.event, (StepEvent, AbilityTriggerEvent, CounteredEvent)) or (
                isinstance(self.event, DeclareBlockersEvent) and self.event.count is not None
            ):
                # no history to read: the first two are never journalled, a
                # countered spell has left the stack before its row could be
                # matched (a "spell" filter cannot be judged afterwards), and a
                # block row is one pair, so a blocker count cannot be read off it
                raise ValueError(
                    f"FAtom: {self.pred.name} cannot read {type(self.event).__name__} "
                    "(no journal history the matcher can judge)"
                )
            if isinstance(self.event, TapStateEvent) and not self.event.tapped:
                raise ValueError(
                    f"FAtom: {self.pred.name} cannot read untapping: the untap step "
                    "precedes the journal's turn window (journal.turn_window)"
                )
            if isinstance(self.event, DamageDealtEvent) and not isinstance(
                self.event.amount, QUnbounded
            ):
                raise ValueError(
                    f"FAtom: {self.pred.name} reads how much damage from its count; "
                    "the DamageDealtEvent amount must be QUnbounded"
                )
            if self.pred is FAtomPred.SUBJECT_OF_EVENT_THIS_TURN and isinstance(
                self.event, CastSpellEvent
            ):
                # the permanent a spell became has its cast before its entry (CR 400.7c)
                raise ValueError(
                    "FAtom: SUBJECT_OF_EVENT_THIS_TURN cannot read a cast: use "
                    "WAS_CAST_THIS_TURN, which follows a spell onto the battlefield"
                )
        if (
            self.pred is FAtomPred.CONTROLLER_IS
            and self.who
            not in (
                ControllerRef.YOU,
                ControllerRef.OPPONENT,
                ControllerRef.TARGET_PLAYER,
                ControllerRef.TARGET_OPPONENT,
                ControllerRef.DEFENDING_PLAYER,
            )
            and not (isinstance(self.who, Selector) and self.who.referent is not None)
        ):
            raise ValueError(
                "FAtom: CONTROLLER_IS who must be you, opponent, the target "
                "player, the defending player, or a referent Selector (grammar round 4)"
            )
        if self.pred is FAtomPred.OPPONENT_OF and not (
            isinstance(self.who, ControllerRef)
            or (isinstance(self.who, Selector) and self.who.referent is not None)
        ):
            raise ValueError(
                "FAtom: OPPONENT_OF who must be a ControllerRef or a referent "
                "Selector (grammar round 11, CONTROLLER_IS precedent)"
            )
        # COLOR_IN's colors are a membership SET — the wording order of
        # "green or white" must not reach the bytes.
        colors = _set_sorted(self.colors)
        if colors != self.colors:
            object.__setattr__(self, "colors", colors)


Filter = FAnd | FOr | FNot | FAtom


# ---------------------------------------------------------------------------
# Durations — a small union of frozen dataclasses. An enum cannot carry the
# Filter that WHILE_CONDITION needs; one dataclass with an optional filter
# would admit PERMANENT(filter=...). Decision documented in the module
# docstring.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DurationEot:
    """Until end of turn."""


@dataclass(frozen=True)
class DurationPermanent:
    """Until removed by another effect (the default for most effects)."""


@dataclass(frozen=True)
class DurationUntilNextTurn:
    """Until the controller's next turn (Teferi's phase-out)."""


@dataclass(frozen=True)
class DurationWhileCondition:
    """While a condition holds (continuous effects)."""

    filter: Filter

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"DurationWhileCondition: filter must be a Filter, got {type(self.filter).__name__}"
            )


@dataclass(frozen=True)
class DurationUntilNextStep:
    """Until the next occurrence of a named Step, optionally relative to
    an owner. Frost Breath's "Those creatures can't untap during their controller's
    next untap step" = PREVENT_EFFECT(TapStateEvent UNTAP,
    step=Step.UNTAP) under this duration; ``owner_scoped`` True binds the
    step to the affected object's controller ("THEIR controller's next
    untap step"), False to the active turn's step."""

    step: Step
    owner_scoped: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.step, Step):
            raise ValueError(
                f"DurationUntilNextStep: step must be a Step, got {type(self.step).__name__}"
            )
        if not isinstance(self.owner_scoped, bool):
            raise ValueError(
                f"DurationUntilNextStep: owner_scoped must be a bool, got {self.owner_scoped!r}"
            )


@dataclass(frozen=True)
class DurationUntilLeaves:
    """Until the referenced permanent leaves the battlefield (Kitesail
    Freebooter's "until this creature leaves the battlefield", Idol of
    Endurance's exile window). ``source`` names the anchored object as a
    referent string from ``_QPROP_STR_REFERENTS`` — default "source" =
    the object that owns the ability (a structured referent, never an
    English substring like "this creature").

    The meaning is exactly "until the anchor leaves the battlefield". It
    ends when that object (the same
    object, CR 400.7) leaves the battlefield. Phasing out does NOT end it:
    phasing is a status, not a zone change (CR 702.26d). A future "for as
    long as ~ remains on the battlefield" duration (CR 611.2b) does end when
    the object phases out (CR 702.26f), so it must not reuse this node; it
    needs its own node or a field here."""

    source: str = "source"

    def __post_init__(self) -> None:
        if self.source not in _QPROP_STR_REFERENTS:
            raise ValueError(
                f"DurationUntilLeaves: source must be one of _QPROP_STR_REFERENTS, got {self.source!r}"
            )


Duration = (
    DurationEot
    | DurationPermanent
    | DurationUntilNextTurn
    | DurationWhileCondition
    | DurationUntilNextStep
    | DurationUntilLeaves
)

#: CR 610.3: the durations a MOVE_ZONE "until …" may carry —
#: each ends on an event, after which the object returns to its previous zone.
_MOVE_ZONE_DURATIONS: tuple[type, ...] = (
    DurationUntilLeaves,
    DurationEot,
    DurationUntilNextTurn,
)


# ---------------------------------------------------------------------------
# EventSpec — structured, NEVER a substring (a substring match fails
# silently). Each event's filter selects the event's SUBJECT —
# the object the event is about: the spell cast, the creature that dealt
# damage / died / became blocked, the entering permanent, the damaged
# object, the targeted object.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneChangeEvent:
    """A permanent changed zones. ETB = from anywhere to the battlefield —
    a ZoneChange, never a substring. ``subject`` narrows
    WHICH zone change fires: None = any permanent, or a Filter over the
    changing permanent ("another creature you control enters")."""

    from_zone: Zone
    to_zone: Zone
    subject: Filter | None = None

    def __post_init__(self) -> None:
        for zone in (self.from_zone, self.to_zone):
            if not isinstance(zone, Zone):
                raise ValueError(
                    f"ZoneChangeEvent: zone must be a Zone, got {type(zone).__name__}"
                )
        if self.subject is not None and not _is_filter(self.subject):
            raise ValueError(
                f"ZoneChangeEvent: subject must be a Filter, got {type(self.subject).__name__}"
            )


@dataclass(frozen=True)
class CastSpellEvent:
    """A spell was cast (filter over the spell: type/subtype/name).
    ``actor`` = a Filter over the CASTING player (None = any — "an opponent
    casts" compiles as ``actor=FAtom(CONTROLLER_IS, OPPONENT)``),
    ``from_zone`` = the source zone (None = any), ``ordinal`` = the Nth
    cast by that caster this turn (None = every cast; 2 = "your second
    spell each turn"), ``from_zone_not`` = exclusion: the cast came from
    anywhere OTHER than this zone ("from anywhere other than their hand" —
    Ghostly Pilferer; mutually exclusive with ``from_zone``)."""

    filter: Filter
    actor: Filter | None = None
    from_zone: Zone | None = None
    ordinal: int | None = None
    from_zone_not: Zone | None = None

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"CastSpellEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if self.actor is not None and not _is_filter(self.actor):
            raise ValueError(
                "CastSpellEvent: actor must be a Filter, got "
                f"{type(self.actor).__name__}"
            )
        if self.from_zone is not None and not isinstance(self.from_zone, Zone):
            raise ValueError(
                f"CastSpellEvent: from_zone must be a Zone, got {type(self.from_zone).__name__}"
            )
        if self.ordinal is not None and (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or self.ordinal < 1
        ):
            raise ValueError(
                f"CastSpellEvent: ordinal must be an int >= 1, got {self.ordinal!r}"
            )
        if self.from_zone_not is not None and not isinstance(self.from_zone_not, Zone):
            raise ValueError(
                f"CastSpellEvent: from_zone_not must be a Zone, got {type(self.from_zone_not).__name__}"
            )
        if self.from_zone is not None and self.from_zone_not is not None:
            raise ValueError(
                "CastSpellEvent: from_zone and from_zone_not are mutually exclusive"
            )


@dataclass(frozen=True)
class DeclareAttackersEvent:
    """Attackers were declared (filter over the declared creature).
    ``attacked`` narrows the ATTACKED-side object per attacker — Mangara's
    "two or more of those creatures are attacking you and/or planeswalkers
    you control"; omitted from the tagged dict when None."""

    filter: Filter
    attacked: Filter | None = None

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"DeclareAttackersEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if self.attacked is not None and not _is_filter(self.attacked):
            raise ValueError(
                f"DeclareAttackersEvent: attacked must be a Filter, got {type(self.attacked).__name__}"
            )


@dataclass(frozen=True)
class DeclareBlockersEvent:
    """Blockers were declared (filter over the blocking creature) — the
    event "can't block" preventions attach to (the Pirate token).
    ``subject`` narrows WHICH declaration fires: None = any blocker, or a
    Filter over the blocking creature — mirroring ``ZoneChangeEvent.subject``.
    ``blocked`` narrows the BLOCKED-side creature — "can't be blocked" /
    "can block only creatures with flying" restrict the blocked participant
    (Tome Anima, Ghostly Pilferer).
    ``count`` is how many creatures block the ``blocked``
    creature: the event is that creature becoming blocked by ``count``
    creatures. "Can't be blocked by more than one creature" is a
    PREVENT_EFFECT over it with ``QAtLeast(2)``, a restriction on the
    number of blockers (CR 509.1b), not on any one blocker. Only that
    prevention reads it (no trigger does). All three are omitted from the
    tagged dict when None."""

    filter: Filter
    subject: Filter | None = None
    blocked: Filter | None = None
    count: Quantity | None = None

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"DeclareBlockersEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if self.subject is not None and not _is_filter(self.subject):
            raise ValueError(
                f"DeclareBlockersEvent: subject must be a Filter, got {type(self.subject).__name__}"
            )
        if self.blocked is not None and not _is_filter(self.blocked):
            raise ValueError(
                f"DeclareBlockersEvent: blocked must be a Filter, got {type(self.blocked).__name__}"
            )
        if self.count is not None and (not isinstance(self.count, QAtLeast) or self.blocked is None):
            # the count is the number of creatures blocking ONE blocked creature
            raise ValueError(
                "DeclareBlockersEvent: count must be a QAtLeast over a blocked creature"
            )


@dataclass(frozen=True)
class CounterPlacedEvent:
    """Counters of a kind were placed on the subject.

    `count` names the number placed ("one or more" = QAtLeast(1); "that
    many" = QProp("event", COUNTER_COUNT)); omitted when None."""

    counter_kind: CounterKind
    filter: Filter
    count: Quantity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.counter_kind, CounterKind):
            raise ValueError(
                f"CounterPlacedEvent: counter_kind must be a CounterKind, got {self.counter_kind!r}"
            )
        if not _is_filter(self.filter):
            raise ValueError(
                f"CounterPlacedEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if self.count is not None and not _is_quantity(self.count):
            raise ValueError(
                "CounterPlacedEvent: count must be a Quantity or None, got "
                f"{type(self.count).__name__}"
            )


@dataclass(frozen=True)
class CreatureDiesEvent:
    """A creature died (filter over the dying creature — Malefic Scythe's
    "equipped creature", Basri's Lieutenant)."""

    filter: Filter

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"CreatureDiesEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )


@dataclass(frozen=True)
class BecomesBlockedEvent:
    """A creature became blocked (filter over the blocker — Gloom Sower)."""

    filter: Filter

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"BecomesBlockedEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )


@dataclass(frozen=True)
class TapStateEvent:
    """A permanent's tapped state changed (filter over the permanent —
    Ghostly Pilferer's "becomes untapped"). `tapped` is the new state."""

    tapped: bool
    filter: Filter

    def __post_init__(self) -> None:
        if not isinstance(self.tapped, bool):
            raise ValueError(
                f"TapStateEvent: tapped must be a bool, got {self.tapped!r}"
            )
        if not _is_filter(self.filter):
            raise ValueError(
                f"TapStateEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )


@dataclass(frozen=True)
class AbilityTriggerEvent:
    """An ability TRIGGERED (Sanctum of All "whenever another Shrine you
    control's ability triggers"). Like every event class it has a subject
    filter, here evaluated over the TRIGGERING ability's source
    permanent ("another Shrine you control" = SUBTYPE_EQ + CONTROLLER_IS
    + FNot(IS_SOURCE)). The quantity axis rides the effect: the
    TRIGGER_ADDITIONAL verb's `count` (an "additional time" is +1, a
    "…for each category" self-repeat is a derived Quantity)."""

    filter: Filter

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"AbilityTriggerEvent: filter must be a Filter, got "
                f"{type(self.filter).__name__}"
            )


@dataclass(frozen=True)
class TurnPhaseEvent:
    """A turn phase began (see Phase for pool citations). The direction
    axis is the ``actor`` Filter, evaluated over the ACTIVE PLAYER of the
    journalled phase (None = any player's phase; "at the beginning of your
    end step" = ``actor=FAtom(CONTROLLER_IS, YOU)``)."""

    phase: Phase
    actor: Filter | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.phase, Phase):
            raise ValueError(
                f"TurnPhaseEvent: phase must be a Phase, got {self.phase!r}"
            )
        if self.actor is not None and not _is_filter(self.actor):
            raise ValueError(
                f"TurnPhaseEvent: actor must be a Filter, got {type(self.actor).__name__}"
            )


@dataclass(frozen=True)
class StepEvent:
    """A step within a phase began for `controller`."""

    phase: Phase
    step: Step
    controller: ControllerRef

    def __post_init__(self) -> None:
        if not isinstance(self.phase, Phase):
            raise ValueError(f"StepEvent: phase must be a Phase, got {self.phase!r}")
        if not isinstance(self.step, Step):
            raise ValueError(f"StepEvent: step must be a Step, got {self.step!r}")
        if not isinstance(self.controller, ControllerRef):
            raise ValueError("StepEvent: controller must be a ControllerRef")


@dataclass(frozen=True)
class DamageDealtEvent:
    """Damage was dealt to the subject (filter over the damaged object —
    Brash Taunter's "whenever this creature is dealt damage"). `amount`
    rides the event for QProp("event", AMOUNT). Optional
    scoping: ``source`` = a Filter over the damage SOURCE (None = any —
    "whenever this creature is dealt damage by a source you control"),
    ``combat`` = True/False to require combat / non-combat damage,
    None = either ("deals noncombat damage to an opponent")."""

    amount: Quantity
    filter: Filter
    source: Filter | None = None
    combat: bool | None = None

    def __post_init__(self) -> None:
        if not _is_quantity(self.amount):
            raise ValueError(
                f"DamageDealtEvent: amount must be a Quantity, got {type(self.amount).__name__}"
            )
        if not _is_filter(self.filter):
            raise ValueError(
                f"DamageDealtEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if self.source is not None and not _is_filter(self.source):
            raise ValueError(
                f"DamageDealtEvent: source must be a Filter, got {type(self.source).__name__}"
            )
        if self.combat is not None and not isinstance(self.combat, bool):
            raise ValueError(
                f"DamageDealtEvent: combat must be a bool, got {self.combat!r}"
            )


@dataclass(frozen=True)
class TargetingEvent:
    """The subject was targeted by a spell or ability (filter over the
    targeted object — Warden of the Woods; the event hexproof/protection
    preventions attach to).

    ``actor``: a Filter over the CONTROLLER of
    the targeting spell or ability, the player journalled on the TARGETING
    row (None = any). "Becomes the target of a spell or ability an opponent
    controls" is ``actor=FAtom(CONTROLLER_IS, OPPONENT)``: the same
    direction encoding as CastSpellEvent, CardDrawnEvent,
    LifeGainedEvent and AbilityActivatedEvent. "Can't be the target of
    spells or abilities your opponents control" is HEXPROOF (CR 702.11),
    never a PREVENT_EFFECT over this event."""

    filter: Filter
    actor: Filter | None = None

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"TargetingEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if self.actor is not None and not _is_filter(self.actor):
            raise ValueError(
                f"TargetingEvent: actor must be a Filter, got {type(self.actor).__name__}"
            )


@dataclass(frozen=True)
class CardDrawnEvent:
    """A card was drawn ("whenever you draw a card", "whenever an opponent
    draws a card"). The drawn card is the event subject — a
    TriggeredAbility `condition` Filter narrows it. ``ordinal`` = the Nth
    card drawn by that player this turn (None = every draw) — "whenever
    you draw your second card each turn" (Jolrael, Mwonvuli Recluse);
    mirrors CastSpellEvent.ordinal. Direction is the ``actor`` Filter,
    evaluated over the DRAWER journalled on the event row (None = any
    player's draw; "whenever you draw" = ``actor=FAtom(CONTROLLER_IS,
    YOU)``)."""

    actor: Filter | None = None
    ordinal: int | None = None

    def __post_init__(self) -> None:
        if self.actor is not None and not _is_filter(self.actor):
            raise ValueError(
                f"CardDrawnEvent: actor must be a Filter, got {type(self.actor).__name__}"
            )
        if self.ordinal is not None and (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or self.ordinal < 1
        ):
            raise ValueError(
                f"CardDrawnEvent: ordinal must be an int >= 1, got {self.ordinal!r}"
            )


@dataclass(frozen=True)
class LifeGainedEvent:
    """Life was gained ("whenever you gain life, target opponent loses that
    much life"). The ``actor`` Filter is evaluated over the GAINING PLAYER
    journalled as the event subject (None = any player; "whenever you gain
    life" = ``actor=FAtom(CONTROLLER_IS, YOU)``)."""

    actor: Filter | None = None

    def __post_init__(self) -> None:
        if self.actor is not None and not _is_filter(self.actor):
            raise ValueError(
                f"LifeGainedEvent: actor must be a Filter, got {type(self.actor).__name__}"
            )


@dataclass(frozen=True)
class LifeLostEvent:
    """A player lost life: "if an opponent lost life this turn"
    (Savage Gorger), "if a player lost 4 or more life this turn" (Knight of
    the Ebon Legion). The twin of :class:`LifeGainedEvent`: ``actor`` is
    evaluated over the LOSING player (None = any player). Damage dealt to a
    player makes that player lose that much life (CR 120.3a), and paying life
    is losing it (CR 119.4), so the journal's player DAMAGE rows and its
    LIFE_LOST rows are both this event."""

    actor: Filter | None = None

    def __post_init__(self) -> None:
        if self.actor is not None and not _is_filter(self.actor):
            raise ValueError(
                f"LifeLostEvent: actor must be a Filter, got {type(self.actor).__name__}"
            )


@dataclass(frozen=True)
class CounteredEvent:
    """A spell or ability was countered (CR 701.6a). ``filter``
    selects the countered object, the event's subject. Its consumer is
    PREVENT_EFFECT, "can't be countered", judged while the spell is still on
    the stack: "This spell can't be countered." (Shifting Ceratops; CR 113.6g,
    it functions on the stack), "Spells you control can't be countered this
    turn." (Veil of Summer). Such a spell may still be targeted by a
    counterspell; it is just not countered (CR 101.2). No trigger or history
    reads it (binding._UNSUPPORTED_EVENTS)."""

    filter: Filter

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"CounteredEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )


@dataclass(frozen=True)
class SacrificeEvent:
    """A permanent was sacrificed ("whenever you sacrifice a permanent").
    The sacrificed permanent is the event subject — a TriggeredAbility
    `condition` Filter narrows it (e.g. a creature filter). The ``actor``
    Filter is evaluated over the SACRIFICER = the journalled
    ``owner_before`` of the sacrifice move — whose sacrifice it is even
    under a control effect."""

    actor: Filter | None = None

    def __post_init__(self) -> None:
        if self.actor is not None and not _is_filter(self.actor):
            raise ValueError(
                f"SacrificeEvent: actor must be a Filter, got {type(self.actor).__name__}"
            )


@dataclass(frozen=True)
class AbilityActivatedEvent:
    """An activated ability was activated.

    - ``source`` (required) selects the object whose ability was activated:
      Keral Keep Disciples' "a Chandra planeswalker" (subtype Chandra + type
      Planeswalker), Faith's Fetters' enchanted permanent
      (IS_ATTACHED_TO_SOURCE).
    - ``kind`` (required, no default) says which activations count:
      :class:`AbilityKind` ANY / NON_MANA (CR 605.1a) / LOYALTY (CR 606.2).
    - ``actor`` is evaluated over the ACTIVATOR, journalled as the
      event's cause (CR 602.2: the activating player controls the ability).

    Two consumers read it: a TriggeredAbility ("whenever you activate a
    loyalty ability of a Chandra planeswalker") and PREVENT_EFFECT, the
    activation lock ("its activated abilities can't be activated unless
    they're mana abilities", CR 602.5), which legality's
    ``ability_playable`` consults before anything is paid."""

    source: Filter
    kind: AbilityKind
    actor: Filter | None = None

    def __post_init__(self) -> None:
        if not _is_filter(self.source):
            raise ValueError(
                f"AbilityActivatedEvent: source must be a Filter, got {type(self.source).__name__}"
            )
        if not isinstance(self.kind, AbilityKind):
            raise ValueError(  # noqa: TRY004 — the grammar's validation contract is ValueError
                f"AbilityActivatedEvent: kind must be an AbilityKind, got {self.kind!r}"
            )
        if self.actor is not None and not _is_filter(self.actor):
            raise ValueError(
                f"AbilityActivatedEvent: actor must be a Filter, got {type(self.actor).__name__}"
            )


EventSpec = (
    ZoneChangeEvent
    | CastSpellEvent
    | DeclareAttackersEvent
    | DeclareBlockersEvent
    | CounterPlacedEvent
    | CreatureDiesEvent
    | BecomesBlockedEvent
    | TapStateEvent
    | TurnPhaseEvent
    | StepEvent
    | DamageDealtEvent
    | TargetingEvent
    | CardDrawnEvent
    | LifeGainedEvent
    | LifeLostEvent
    | SacrificeEvent
    | AbilityActivatedEvent
    | CounteredEvent
)


# ---- Leaf value types used inside AtomArgs ----


@dataclass(frozen=True)
class LiteralName:
    """A structured card-name reference (Necromentia's "choose a card name",
    "cards named Frantic Inventory") — data, wrapped so it stays
    distinguishable from a raw string in serialization."""

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"LiteralName: name must be a non-empty str, got {self.name!r}"
            )


@dataclass(frozen=True)
class PtDelta:
    """A signed P/T adjustment expressed without negative quantities:
    direction + non-negative magnitude (Pestilent Haze's -2/-2)."""

    direction: PtDirection
    magnitude: Quantity

    def __post_init__(self) -> None:
        if not isinstance(self.direction, PtDirection):
            raise ValueError(
                f"PtDelta: direction must be a PtDirection, got {self.direction!r}"
            )
        if not _is_quantity(self.magnitude):
            raise ValueError(
                f"PtDelta: magnitude must be a Quantity, got {type(self.magnitude).__name__}"
            )


@dataclass(frozen=True)
class TokenSpec:
    """A nested card record for token creation (DESIGN_CARD_POOL: "token
    creation takes a nested card record, not a string"). Creatures require
    P/T Quantities (the Weird token's dynamic P/T is a SET_PT ability on
    the token, with power/toughness None); non-creatures forbid P/T."""

    name: str
    type_line: str
    types: tuple[str, ...]
    subtypes: tuple[str, ...]
    power: Quantity | None
    toughness: Quantity | None
    keywords: tuple[Keyword, ...]
    abilities: tuple[Ability, ...]
    # colors: the token's printed colour words, each a WUBRG letter, in
    # WUBRG order (CR 105.1) — "a 1/1 white Soldier" is ("W",), Experimental
    # Overload's "blue and red Weird" ("U", "R"), a colourless Treasure ().
    # enters_tapped / enters_attacking: "put those tokens onto the
    # battlefield tapped" and "…that's attacking" (Basri Ket [-2]). All three
    # serialize by OMITTING the key at their empty default (registered in
    # both _SPECS and _OMIT_IF_EMPTY).
    colors: tuple[str, ...] = ()
    enters_tapped: bool | None = None
    enters_attacking: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"TokenSpec: name must be a non-empty str, got {self.name!r}"
            )
        if not isinstance(self.type_line, str) or not self.type_line.strip():
            raise ValueError("TokenSpec: type_line must be a non-empty str")
        if not self.types:
            raise ValueError("TokenSpec: types must be non-empty")
        if "Creature" in self.types:
            if not _is_quantity(self.power) or not _is_quantity(self.toughness):
                raise ValueError(
                    "TokenSpec: creature tokens require power and toughness Quantities"
                )
        elif self.power is not None or self.toughness is not None:
            raise ValueError("TokenSpec: non-creature tokens cannot have P/T")
        for keyword in self.keywords:
            if not isinstance(keyword, Keyword):
                raise ValueError(
                    f"TokenSpec: keywords must be Keyword, got {type(keyword).__name__}"
                )
        for ability in self.abilities:
            if not _is_ability(ability):
                raise ValueError(
                    f"TokenSpec: abilities must be Ability, got {type(ability).__name__}"
                )
        if not isinstance(self.colors, tuple) or any(
            c not in _COLORS for c in self.colors
        ):
            raise ValueError(
                f"TokenSpec: colors must be a tuple of {_COLORS} letters, got {self.colors!r}"
            )
        if len(set(self.colors)) != len(self.colors):
            raise ValueError(f"TokenSpec: colors must be distinct, got {self.colors!r}")
        for flag in ("enters_tapped", "enters_attacking"):
            value = getattr(self, flag)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"TokenSpec: {flag} must be a bool, got {value!r}")
        # These three containers are COMPILER-EMITTED data, not oracle-printed card text (unlike
        # CardRecord.types/subtypes, which keep printed fidelity), so their
        # wording order is normalized at construction. `abilities` stays
        # IDENTITY (printed order).
        for fld in ("types", "subtypes", "keywords"):
            value = _set_sorted(getattr(self, fld))
            if value != getattr(self, fld):
                object.__setattr__(self, fld, value)
        # The colour set is canonical in WUBRG order (CR 105.1), the
        # order mana costs and colour identities print in, so "blue and red"
        # and "red and blue" are the same bytes.
        colors = tuple(sorted(self.colors, key=_COLORS.index))
        if colors != self.colors:
            object.__setattr__(self, "colors", colors)


# ---- Costs ----


@dataclass(frozen=True)
class CostTap:
    """Tap as a cost. ``target=None`` means "the source itself" — every
    ``{T}:`` activated ability in the pool."""

    target: Selector | None = None

    def __post_init__(self) -> None:
        if self.target is not None and not isinstance(self.target, Selector):
            raise ValueError(
                f"CostTap: target must be a Selector, got {type(self.target).__name__}"
            )


@dataclass(frozen=True)
class CostManaColor:
    """A specific colour of mana, `amount` of it ({R}, {2}{U}, {X} red...)."""

    color: str
    amount: Quantity

    def __post_init__(self) -> None:
        if self.color not in _COLORS:
            raise ValueError(
                f"CostManaColor: color must be one of {_COLORS}, got {self.color!r}"
            )
        if not _is_quantity(self.amount):
            raise ValueError(
                f"CostManaColor: amount must be a Quantity, got {type(self.amount).__name__}"
            )


@dataclass(frozen=True)
class CostManaGeneric:
    """Generic mana, `amount` of it ({1}, {X})."""

    amount: Quantity

    def __post_init__(self) -> None:
        if not _is_quantity(self.amount):
            raise ValueError(
                f"CostManaGeneric: amount must be a Quantity, got {type(self.amount).__name__}"
            )


@dataclass(frozen=True)
class CostManaHybrid:
    """Hybrid mana symbols ({W/U}); `amount` symbols, each payable with
    either colour."""

    colors: tuple[str, str]
    amount: Quantity

    def __post_init__(self) -> None:
        if len(self.colors) != 2 or any(c not in _COLORS for c in self.colors):
            raise ValueError(
                f"CostManaHybrid: colors must be two of {_COLORS}, got {self.colors!r}"
            )
        if self.colors[0] == self.colors[1]:
            raise ValueError(
                f"CostManaHybrid: hybrid colours must differ, got {self.colors!r}"
            )
        if not _is_quantity(self.amount):
            raise ValueError(
                f"CostManaHybrid: amount must be a Quantity, got {type(self.amount).__name__}"
            )
        # The colour pair is membership — sorted at construction so
        # {W/B} == {B/W} in the bytes. The hybrid_demands witness
        # (legality) prefers the FIRST tuple slot, so the sort makes that
        # preference alphabetical.
        ordered = _set_sorted(self.colors)
        if ordered != self.colors:
            object.__setattr__(self, "colors", ordered)


@dataclass(frozen=True)
class CostLife:
    """Lose `amount` life as a cost."""

    amount: Quantity

    def __post_init__(self) -> None:
        if not _is_quantity(self.amount):
            raise ValueError(
                f"CostLife: amount must be a Quantity, got {type(self.amount).__name__}"
            )


@dataclass(frozen=True)
class CostSacrifice:
    """Sacrifice the selected permanent(s) as a cost (Village Rites,
    Witch's Cauldron, Selfless Savior, the Treasure token)."""

    target: Selector

    def __post_init__(self) -> None:
        if not isinstance(self.target, Selector):
            raise ValueError(
                f"CostSacrifice: target must be a Selector, got {type(self.target).__name__}"
            )


@dataclass(frozen=True)
class CostDiscard:
    """Discard the selected card(s) as a cost (Sparkhunter Masticore's
    additional cost to cast)."""

    target: Selector

    def __post_init__(self) -> None:
        if not isinstance(self.target, Selector):
            raise ValueError(
                f"CostDiscard: target must be a Selector, got {type(self.target).__name__}"
            )


@dataclass(frozen=True)
class CostPutCounter:
    """Put counters on the selected object as a cost (Mazemind Tome:
    "{T}, put a page counter on this artifact")."""

    counter_kind: CounterKind
    target: Selector
    count: Quantity = QConst(1)

    def __post_init__(self) -> None:
        if not isinstance(self.counter_kind, CounterKind):
            raise ValueError(
                f"CostPutCounter: counter_kind must be a CounterKind, got {self.counter_kind!r}"
            )
        if not isinstance(self.target, Selector):
            raise ValueError(
                f"CostPutCounter: target must be a Selector, got {type(self.target).__name__}"
            )
        if not _is_quantity(self.count):
            raise ValueError(
                f"CostPutCounter: count must be a Quantity, got {type(self.count).__name__}"
            )


@dataclass(frozen=True)
class CostLoyalty:
    """A loyalty change as a cost — the ONLY signed value in the grammar,
    because planeswalker costs (-2, -7) are negative by definition.

    ``delta`` is a literal int or a Quantity (Ugin's "[−X]" — a DYNAMIC
    loyalty cost); a dynamic delta is still always a reduction (loyalty is
    never gained as a cost).

    ``delta=0`` is legal. A [0] ability is a loyalty ability (CR
    606.2: the symbol is in its cost) that adds and removes no counter
    (CR 606.4), so the once-per-turn clock and the main-phase window still
    apply. The int 0 is its only spelling: ``QConst(0)`` would mean "remove
    0", the same cost in other bytes, so it stays refused."""

    delta: int | Quantity

    def __post_init__(self) -> None:
        if isinstance(self.delta, bool):
            raise ValueError(
                f"CostLoyalty: delta must be an int or Quantity, got {self.delta!r}"
            )
        if isinstance(self.delta, int):
            pass  # any signed literal, [0] included (CR 606.2/606.4)
        elif _is_quantity(self.delta):
            if isinstance(self.delta, QConst) and self.delta.value == 0:
                raise ValueError(
                    "CostLoyalty: a [0] cost is the int 0, never QConst(0) "
                    "(one meaning, one spelling)"
                )
        else:
            raise ValueError(
                "CostLoyalty: delta must be an int or Quantity, got "
                f"{type(self.delta).__name__}"
            )


CostPart = (
    CostTap
    | CostManaColor
    | CostManaGeneric
    | CostManaHybrid
    | CostLife
    | CostSacrifice
    | CostDiscard
    | CostPutCounter
    | CostLoyalty
)


@dataclass(frozen=True)
class Cost:
    """An ability's cost. Empty parts = a free activation (legal MTG).

    Parts are canonically sorted AT CONSTRUCTION by ``canonical_json``
    (:func:`_set_sorted`). Payment is order-free in the rules, but the plan
    fold walks the parts LIST (failure-string precedence, the per-colour
    min-clamp trace, ``sacrifice_options`` order ⇒ the sacrifice ask
    sequence), so the construction-sort makes the canonical
    ``PaymentPlan`` a function of the parts MULTISET. Folded costs
    (``spell_cost``: printed ++ additional) pass through THIS constructor,
    so the kicker fold is sorted too. Duplicate parts ({W}{W}) are legal
    and the stable sort keeps them adjacent — Cost sorts, it never
    dedups."""

    parts: tuple[CostPart, ...] = ()

    def __post_init__(self) -> None:
        for part in self.parts:
            if not _is_cost_part(part):
                raise ValueError(
                    f"Cost: part must be a CostPart, got {type(part).__name__}"
                )
        ordered = _set_sorted(self.parts)
        if ordered != self.parts:
            object.__setattr__(self, "parts", ordered)


# Cost deltas — the signed cost changes a CostModifier applies ("cost {2}
# less to cast", "cost an additional 2 life to cast", "cost {2}{U} less",
# "cast without paying its mana cost"). `amount` is a
# Quantity, so X- and dynamic-amount deltas ("where X is the total power
# of creatures you control") are legal.


@dataclass(frozen=True)
class CostDeltaReduceGeneric:
    """Reduce the cost's generic-mana requirement by `amount`
    ("cost {2} less to cast")."""

    amount: Quantity

    def __post_init__(self) -> None:
        if not _is_quantity(self.amount):
            raise ValueError(
                "CostDeltaReduceGeneric: amount must be a Quantity, got "
                f"{type(self.amount).__name__}"
            )


@dataclass(frozen=True)
class CostDeltaIncreaseGeneric:
    """Increase the cost's generic-mana requirement by `amount`
    ("cost {2} more to cast")."""

    amount: Quantity

    def __post_init__(self) -> None:
        if not _is_quantity(self.amount):
            raise ValueError(
                "CostDeltaIncreaseGeneric: amount must be a Quantity, got "
                f"{type(self.amount).__name__}"
            )


@dataclass(frozen=True)
class CostDeltaReduceMana:
    """Reduce one `color` mana symbol in the cost by `amount`
    ("cost {2}{U} less to cast")."""

    color: str
    amount: Quantity

    def __post_init__(self) -> None:
        if self.color not in _COLORS:
            raise ValueError(
                f"CostDeltaReduceMana: color must be one of {_COLORS}, got {self.color!r}"
            )
        if not _is_quantity(self.amount):
            raise ValueError(
                "CostDeltaReduceMana: amount must be a Quantity, got "
                f"{type(self.amount).__name__}"
            )


@dataclass(frozen=True)
class CostDeltaIncreaseLife:
    """Add `amount` of life to the cost ("cost an additional 2 life to
    cast")."""

    amount: Quantity

    def __post_init__(self) -> None:
        if not _is_quantity(self.amount):
            raise ValueError(
                "CostDeltaIncreaseLife: amount must be a Quantity, got "
                f"{type(self.amount).__name__}"
            )


@dataclass(frozen=True)
class CostDeltaWaiveMana:
    """Waive the cost's mana component entirely ("you may cast spells from
    your hand without paying their mana costs")."""


CostDelta = (
    CostDeltaReduceGeneric
    | CostDeltaIncreaseGeneric
    | CostDeltaReduceMana
    | CostDeltaIncreaseLife
    | CostDeltaWaiveMana
)


# ---- Atom args and the Atom ----

# _SCOPE_VOCAB_BY_VERB: the per-verb "scope"
# role vocabulary. AtomArgs can only validate the union of all vocabu-
# laries (it carries no verb); the enclosing Atom rejects a scope value
# that belongs to a DIFFERENT verb's vocabulary here — e.g. a
# MANA_POLICY atom may not carry AS_UNBLOCKED.
_SCOPE_VOCAB_BY_VERB: dict[Verb, tuple[str, ...]] = {
    Verb.MANA_POLICY: _MANA_POLICY_SCOPES,
    Verb.DAMAGE_ASSIGN_POLICY: _DAMAGE_ASSIGN_SCOPES,
}


@dataclass(frozen=True)
class AtomArgs:
    """A frozen mapping of role name -> typed value for one Atom.

    Stored as ``pairs``: a tuple of ``(role, value)`` sorted by role in
    ``__post_init__`` — the stdlib has no hashable frozen dict, and sorted
    pairs make the node value-equal, hashable, and canonical regardless of
    the order the compiler (or a test) inserted the roles in. Every role is
    checked against the closed table ``_ROLE_TYPES``; unknown roles,
    duplicate roles, and wrong value types all raise.
    """

    pairs: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        roles = [role for role, _ in self.pairs]
        dupes = sorted({r for r in roles if roles.count(r) > 1})
        if dupes:
            raise ValueError(f"AtomArgs: duplicate roles {dupes}")
        for role, value in self.pairs:
            allowed = _ROLE_TYPES.get(role)
            if allowed is None:
                raise ValueError(f"AtomArgs: unknown role {role!r}")
            if not isinstance(value, allowed):
                raise ValueError(
                    f"AtomArgs: role {role!r} got {type(value).__name__}, expected one of "
                    + ", ".join(t.__name__ for t in allowed)
                )
            if role == "types" and not all(isinstance(x, str) for x in value):  # type: ignore[arg-type]
                raise ValueError(
                    "AtomArgs: role 'types' must be a tuple of card-type strings"
                )
            if role == "color" and value not in (*_COLORS, _COLORLESS, _ANY_COLOR):
                raise ValueError(
                    f"AtomArgs: role 'color' must be one of WUBRG/C/ANY, got {value!r}"
                )
            # scope: AtomArgs is verb-blind, so it validates against the
            # UNION of the per-verb scope vocabularies here; the enclosing
            # Atom enforces the verb's own vocabulary (_SCOPE_VOCAB_BY_VERB).
            if role == "scope" and value not in (
                *_MANA_POLICY_SCOPES,
                *_DAMAGE_ASSIGN_SCOPES,
            ):
                raise ValueError(
                    f"AtomArgs: role 'scope' must be one of "
                    f"{(*_MANA_POLICY_SCOPES, *_DAMAGE_ASSIGN_SCOPES)}, "
                    f"got {value!r}"
                )
            # MOVE_ZONE's closed string slots — single-verb vocabularies,
            # so the AtomArgs-level check is already exact (no
            # _SCOPE_VOCAB_BY_VERB twin needed).
            if role == "journal_kind" and value not in _MOVE_JOURNAL_KINDS:
                raise ValueError(
                    f"AtomArgs: role 'journal_kind' must be one of "
                    f"{_MOVE_JOURNAL_KINDS}, got {value!r}"
                )
            if role == "pop_order" and value not in _MOVE_POP_ORDERS:
                raise ValueError(
                    f"AtomArgs: role 'pop_order' must be one of "
                    f"{_MOVE_POP_ORDERS}, got {value!r}"
                )
        # The mill lane is defined by TOP-pop; a journal_kind="MILL" site
        # that forgets pop_order would silently fall through to the generic
        # MOVE lane (wrong bookkeeping).
        _jk = next((v for r, v in self.pairs if r == "journal_kind"), None)
        if _jk == "MILL":
            _po = next((v for r, v in self.pairs if r == "pop_order"), None)
            if _po != "TOP":
                raise ValueError(
                    "AtomArgs: journal_kind 'MILL' requires pop_order 'TOP' "
                    "(mill is top-of-library by rule CR 701.4a; omitting "
                    "pop_order would silently take the generic MOVE lane)"
                )
        object.__setattr__(self, "pairs", tuple(sorted(self.pairs, key=lambda p: p[0])))

    def get(self, role: str) -> object | None:
        """The value for `role`, or None — mapping ergonomics."""
        for r, v in self.pairs:
            if r == role:
                return v
        return None


@dataclass(frozen=True)
class Atom:
    """A verb + its typed args — the leaf of every effect. The verb's
    required/optional roles are validated against ``_VERB_ROLES``."""

    verb: Verb
    args: AtomArgs

    def __post_init__(self) -> None:
        if not isinstance(self.verb, Verb):
            raise ValueError(f"Atom: verb must be a Verb, got {self.verb!r}")
        if not isinstance(self.args, AtomArgs):
            raise ValueError(
                f"Atom: args must be an AtomArgs, got {type(self.args).__name__}"
            )
        roles = dict(self.args.pairs)
        table = _VERB_ROLES[self.verb]
        missing = sorted(r for r, req in table.items() if req and r not in roles)
        if missing:
            raise ValueError(f"Atom: {self.verb.name} missing required roles {missing}")
        extra = sorted(r for r in roles if r not in table)
        if extra:
            raise ValueError(f"Atom: {self.verb.name} does not take roles {extra}")
        if (
            self.verb in (Verb.MODIFY_PT, Verb.SET_PT)
            and "power" not in roles
            and "toughness" not in roles
        ):
            raise ValueError(
                f"Atom: {self.verb.name} needs at least one of power/toughness"
            )
        # MOVE_ZONE carries its objects on the cards, target or amount
        # axis — an atom with none would be a move of nothing.
        if self.verb is Verb.MOVE_ZONE and not roles.keys() & {
            "cards",
            "target",
            "amount",
        }:
            raise ValueError(
                f"Atom: {self.verb.name} needs one of the cards/target/"
                "amount object axes"
            )
        # CR 610.3: a zone move "until" something returns the
        # object when that event happens, so only durations that END ON AN
        # EVENT are accepted. DurationPermanent would be a twin of leaving the
        # role out (same meaning, different bytes), and
        # DurationWhileCondition can become true again, which would move the
        # object a second time.
        if self.verb is Verb.MOVE_ZONE and "duration" in roles:
            duration = roles["duration"]
            if not isinstance(duration, _MOVE_ZONE_DURATIONS):
                raise ValueError(
                    f"Atom: MOVE_ZONE duration must be one of "
                    f"{', '.join(t.__name__ for t in _MOVE_ZONE_DURATIONS)} (a "
                    f"duration that ends on an event, CR 610.3), got "
                    f"{type(duration).__name__}; DurationPermanent means the same as "
                    "leaving the role out, and DurationWhileCondition could start "
                    "again and move the object a second time"
                )
        # Per-verb scope vocabulary (AtomArgs validates the union
        # only; a cross-verb scope like MANA_POLICY/AS_UNBLOCKED is caught
        # here, at the verb's own level).
        vocab = _SCOPE_VOCAB_BY_VERB.get(self.verb)
        scope = roles.get("scope")
        if vocab is not None and scope is not None and scope not in vocab:
            raise ValueError(
                f"Atom: {self.verb.name} scope must be one of {vocab}, got {scope!r}"
            )


# ---- Effects ----


@dataclass(frozen=True)
class Seq:
    """Steps in order. Empty sequences are rejected: a no-op is not a node
    in the tree — the compiler emits nothing, not an empty Seq."""

    steps: tuple[Effect, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("Seq: steps must be non-empty")
        for step in self.steps:
            if not _is_effect(step):
                raise ValueError(
                    f"Seq: step must be an Effect, got {type(step).__name__}"
                )


@dataclass(frozen=True)
class Choose:
    """Pick `count` of the options (Tolarian Kraken's "tap or untap")."""

    count: Quantity
    options: tuple[Effect, ...]

    def __post_init__(self) -> None:
        if not _is_quantity(self.count):
            raise ValueError(
                f"Choose: count must be a Quantity, got {type(self.count).__name__}"
            )
        if not self.options:
            raise ValueError("Choose: options must be non-empty")
        for option in self.options:
            if not _is_effect(option):
                raise ValueError(
                    f"Choose: option must be an Effect, got {type(option).__name__}"
                )


@dataclass(frozen=True)
class OptionalEffect:
    """A step the controller may skip ("you may ...")."""

    inner: Effect

    def __post_init__(self) -> None:
        if not _is_effect(self.inner):
            raise ValueError(
                f"OptionalEffect: inner must be an Effect, got {type(self.inner).__name__}"
            )


@dataclass(frozen=True)
class Conditional:
    """If `pred` holds, then then_effect; else else_effect if present
    (Jeskai Elder: "if you do, discard a card")."""

    pred: Filter
    then_effect: Effect
    else_effect: Effect | None = None

    def __post_init__(self) -> None:
        if not _is_filter(self.pred):
            raise ValueError(
                f"Conditional: pred must be a Filter, got {type(self.pred).__name__}"
            )
        if not _is_effect(self.then_effect):
            raise ValueError(
                f"Conditional: then_effect must be an Effect, got {type(self.then_effect).__name__}"
            )
        if self.else_effect is not None and not _is_effect(self.else_effect):
            raise ValueError(
                f"Conditional: else_effect must be an Effect, got {type(self.else_effect).__name__}"
            )


@dataclass(frozen=True)
class Repeat:
    """Repeat `inner` `count` times (mill-four = MILL x 4)."""

    count: Quantity
    inner: Effect

    def __post_init__(self) -> None:
        if not _is_quantity(self.count):
            raise ValueError(
                f"Repeat: count must be a Quantity, got {type(self.count).__name__}"
            )
        if not _is_effect(self.inner):
            raise ValueError(
                f"Repeat: inner must be an Effect, got {type(self.inner).__name__}"
            )


@dataclass(frozen=True)
class EachPlayer:
    """Apply `effect` once per player denoted by `ref` ("each opponent
    creates a token / sacrifices a creature"). `ref` = the player set:
    ALL_OPPONENTS for "each opponent", OPPONENT/YOU for the singular
    per-player reading."""

    ref: ControllerRef
    effect: Effect

    def __post_init__(self) -> None:
        if not isinstance(self.ref, ControllerRef):
            raise ValueError(
                f"EachPlayer: ref must be a ControllerRef, got {type(self.ref).__name__}"
            )
        if not _is_effect(self.effect):
            raise ValueError(
                f"EachPlayer: effect must be an Effect, got {type(self.effect).__name__}"
            )


def _check_once_per_event(owner: str, event: object, value: object) -> None:
    """TriggeredAbility.once_per_event's one encoding: True or absent (never False), and only
    where it means something. "Is dealt damage" with no dealer named is already one event per
    recipient (CR 510.2), so the flag needs the `source` it gathers ("one or more Cats deal")."""
    if value is None:
        return
    if value is not True:
        raise ValueError(f"{owner}: once_per_event is True or absent, got {value!r}")
    if isinstance(event, DamageDealtEvent) and event.source is None:
        raise ValueError(
            f"{owner}: once_per_event on a DamageDealtEvent needs a source (the dealers it gathers)"
        )


@dataclass(frozen=True)
class DelayedTrigger:
    """A trigger created *inside* another effect, live only for `duration`.
    Subira Toralf's "When a creature you
    control enters this turn, ..." is an Atom effect that registers this
    node; the node itself is never a standalone Ability — the duration is
    REQUIRED because a delayed trigger without a lifetime window is just a
    TriggeredAbility. `condition` optionally gates the fired event, same
    convention as TriggeredAbility.condition, and `once_per_event` is
    TriggeredAbility.once_per_event (Basri Ket's "whenever one or more
    nontoken creatures attack this turn")."""

    duration: Duration
    event: EventSpec
    condition: Filter | None
    effect: Effect
    once_per_event: bool | None = None

    def __post_init__(self) -> None:
        if not _is_duration(self.duration):
            raise ValueError(
                f"DelayedTrigger: duration must be a Duration, got {type(self.duration).__name__}"
            )
        if not _is_event(self.event):
            raise ValueError(
                f"DelayedTrigger: event must be an EventSpec, got {type(self.event).__name__}"
            )
        if self.condition is not None and not _is_filter(self.condition):
            raise ValueError(
                f"DelayedTrigger: condition must be a Filter, got {type(self.condition).__name__}"
            )
        _check_once_per_event("DelayedTrigger", self.event, self.once_per_event)
        if not _is_effect(self.effect):
            raise ValueError(
                f"DelayedTrigger: effect must be an Effect, got {type(self.effect).__name__}"
            )


Effect = (
    Seq
    | Choose
    | OptionalEffect
    | Conditional
    | Repeat
    | EachPlayer
    | Atom
    | DelayedTrigger
)


# ---- Abilities ----


@dataclass(frozen=True)
class StaticAbility:
    """A continuous effect (anthems, "can't attack" preventions, equipped
    creature gets +1/+1 for each soul counter). `condition` optionally
    scopes WHEN the continuous effect applies ("As
    long as you've drawn two or more cards this turn, this creature gets
    +0/+2"); None = unconditional — same convention as
    TriggeredAbility.condition / CostModifier.condition (state predicate,
    no event subject)."""

    effect: Effect
    condition: Filter | None = None

    def __post_init__(self) -> None:
        if not _is_effect(self.effect):
            raise ValueError(
                f"StaticAbility: effect must be an Effect, got {type(self.effect).__name__}"
            )
        if self.condition is not None and not _is_filter(self.condition):
            raise ValueError(
                f"StaticAbility: condition must be a Filter, got {type(self.condition).__name__}"
            )


@dataclass(frozen=True)
class TriggeredAbility:
    """When/whenever `event` fires (and `condition` holds, if present),
    `effect` happens. `condition` is a Filter over the event's subject.

    ``once_per_event``: how often one event triggers the ability (CR 603.2c:
    once each time the event occurs, but repeatedly when one event holds
    several occurrences). Absent (None, omitted from the bytes): once for each
    occurrence `event` matches, its subject bound as the event: "whenever a
    creature you control attacks" triggers for each such attacker (CR 508.3a),
    "whenever another creature dies" for each one that died. True: once for
    the whole event, however many of its occurrences match: "whenever you
    attack" and "whenever one or more creatures you control attack" trigger
    once per declaration (CR 508.3d); "whenever one or more Cats you control
    deal combat damage to a player" once per combat damage step and player
    (CR 510.2), gathering the dealers its `source` names. Never False, and
    never on a DamageDealtEvent without a `source` ("is dealt damage" is
    already one event per recipient): one encoding for each meaning."""

    event: EventSpec
    condition: Filter | None
    effect: Effect
    once_per_event: bool | None = None

    def __post_init__(self) -> None:
        if not _is_event(self.event):
            raise ValueError(
                f"TriggeredAbility: event must be an EventSpec, got {type(self.event).__name__}"
            )
        if self.condition is not None and not _is_filter(self.condition):
            raise ValueError(
                f"TriggeredAbility: condition must be a Filter, got {type(self.condition).__name__}"
            )
        _check_once_per_event("TriggeredAbility", self.event, self.once_per_event)
        if not _is_effect(self.effect):
            raise ValueError(
                f"TriggeredAbility: effect must be an Effect, got {type(self.effect).__name__}"
            )


@dataclass(frozen=True)
class ActivatedAbility:
    """Cost: Effect — mana abilities, loyalty abilities, and Mazemind
    Tome's "{T}, put a page counter on this artifact: Scry 1". `condition`
    optionally gates activation ("Activate only if a creature died this
    turn"); None = unconditional — same convention as
    StaticAbility.condition (state predicate, no event subject). `timing`
    optionally pins WHEN the ability may be activated
    (ActivationWindow.SORCERY for "Activate only as a sorcery"); None =
    the default instant speed, and the key is omitted."""

    cost: Cost
    effect: Effect
    condition: Filter | None = None
    timing: ActivationWindow | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cost, Cost):
            raise ValueError(
                f"ActivatedAbility: cost must be a Cost, got {type(self.cost).__name__}"
            )
        if not _is_effect(self.effect):
            raise ValueError(
                f"ActivatedAbility: effect must be an Effect, got {type(self.effect).__name__}"
            )
        if self.condition is not None and not _is_filter(self.condition):
            raise ValueError(
                f"ActivatedAbility: condition must be a Filter, got {type(self.condition).__name__}"
            )
        if self.timing is not None and not isinstance(self.timing, ActivationWindow):
            raise ValueError(
                f"ActivatedAbility: timing must be an ActivationWindow, got {type(self.timing).__name__}"
            )


@dataclass(frozen=True)
class SpellAbility:
    """The card's own spell effect, keyed by card class. The printed mana
    cost stays on CardRecord; this is what casting the card does.

    ``additional_costs`` carries the "As an additional cost to cast this
    spell, ..." costs ON TOP of the printed cost (sacrifice a creature,
    discard a card, ...) — the printed cost itself still lives on
    CardRecord.

    ``effect`` is optional: a creature can be castable with additional
    costs and no resolvable effect sentence of its own (Goremand,
    Sparkhunter Masticore). The compiler then builds an effect-less
    SpellAbility (``effect=None``) purely to carry the additional costs.
    ``None`` serializes by omitting the ``"effect"`` key."""

    kind: SpellKind
    effect: Effect | None = None
    additional_costs: tuple[Cost, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SpellKind):
            raise ValueError(
                f"SpellAbility: kind must be a SpellKind, got {self.kind!r}"
            )
        if self.effect is not None and not _is_effect(self.effect):
            raise ValueError(
                f"SpellAbility: effect must be an Effect, got {type(self.effect).__name__}"
            )
        if not isinstance(self.additional_costs, tuple):
            raise ValueError(
                "SpellAbility: additional_costs must be a tuple of Cost, got "
                f"{type(self.additional_costs).__name__}"
            )
        for cost in self.additional_costs:
            if not isinstance(cost, Cost):
                raise ValueError(
                    "SpellAbility: additional_costs must hold Cost nodes, got "
                    f"{type(cost).__name__}"
                )
        # The entries fold into the SAME order-keyed planner (spell_cost
        # printed++additional -> build_payment_plan), so they are a SET —
        # sorted at construction; the runtime fold re-enters
        # Cost.__post_init__, so the total plan is order-free from both
        # ends.
        ordered = _set_sorted(self.additional_costs)
        if ordered != self.additional_costs:
            object.__setattr__(self, "additional_costs", ordered)


@dataclass(frozen=True)
class KeywordAbility:
    """A keyword with typed params; arity is validated per keyword via
    ``_KEYWORD_PARAMS``: Scry/Mill/Battalion take one Quantity, Protection
    takes one Filter, Hexproof takes none or one Filter, the rest take
    none. MTGJSON's "Hexproof from blue" is HEXPROOF + a Filter param."""

    keyword: Keyword
    params: tuple[Quantity | Filter | Cost, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.keyword, Keyword):
            raise ValueError(
                f"KeywordAbility: keyword must be a Keyword, got {self.keyword!r}"
            )
        signatures = _KEYWORD_PARAMS.get(self.keyword, ((),))
        if len(self.params) not in {len(sig) for sig in signatures}:
            raise ValueError(
                f"KeywordAbility: {self.keyword.name} takes params of arity "
                f"{sorted(len(sig) for sig in signatures)}, got {len(self.params)}"
            )
        for sig in signatures:
            if len(sig) == len(self.params) and all(
                isinstance(param, allowed) for param, allowed in zip(self.params, sig)
            ):
                return
        raise ValueError(
            f"KeywordAbility: {self.keyword.name} got invalid param types "
            f"{[type(p).__name__ for p in self.params]}"
        )


@dataclass(frozen=True)
class ReplacementAbility:
    """Replaces `event` (and `condition`, if present) with `action`.

    Shares EventSpec with triggers deliberately (DESIGN_CARD_POOL: the same
    predicate over the same typed event bus, differing only in whether it
    fires before or after — commander's command-zone replacement needs
    exactly this).
    """

    event: EventSpec
    condition: Filter | None
    action: Effect

    def __post_init__(self) -> None:
        if not _is_event(self.event):
            raise ValueError(
                f"ReplacementAbility: event must be an EventSpec, got {type(self.event).__name__}"
            )
        if self.condition is not None and not _is_filter(self.condition):
            raise ValueError(
                f"ReplacementAbility: condition must be a Filter, got {type(self.condition).__name__}"
            )
        if not _is_effect(self.action):
            raise ValueError(
                f"ReplacementAbility: action must be an Effect, got {type(self.action).__name__}"
            )


@dataclass(frozen=True)
class CostModifier:
    """A continuous cost-altering effect ("creature spells with flying you
    cast cost {2} less to cast", "cost an additional 2 life to cast", "cost
    {2}{U} less", "without paying its mana cost").

    A SIBLING Ability node, not a StaticAbility payload — a cost modifier
    is not an executable Effect step (StaticAbility wraps an Effect: things
    that HAPPEN), it declares its own payload exactly like StaticAbility
    declares `effect`. `filter` selects the affected spells/permanents,
    `controller_ref` scopes whose, `delta` is the signed cost change.
    `condition` optionally narrows WHEN the modifier applies ("This spell
    costs {2} less to cast if you've gained 2 or more life this turn");
    None = unconditional. `extra_deltas` carries further cost deltas beyond
    the single `delta` slot (Stormwing Entity's {2}{U} = generic 2 + 1
    blue); empty = single delta only. A Selector `controller_ref` means the
    controller of the selected object, and the modifier applies to costs
    that controller pays FOR the filtered object (Lofty Denial: the {1}
    becomes {4} under the condition, including `unless` payments)."""

    filter: Filter
    controller_ref: ControllerRef | Selector
    delta: CostDelta
    condition: Filter | None = None
    extra_deltas: tuple[CostDelta, ...] = ()

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"CostModifier: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if not isinstance(self.controller_ref, (ControllerRef, Selector)):
            raise ValueError(
                "CostModifier: controller_ref must be a ControllerRef or a "
                f"Selector, got {type(self.controller_ref).__name__}"
            )
        if not _is_cost_delta(self.delta):
            raise ValueError(
                f"CostModifier: delta must be a CostDelta, got {type(self.delta).__name__}"
            )
        if self.condition is not None and not _is_filter(self.condition):
            raise ValueError(
                "CostModifier: condition must be a Filter, got "
                f"{type(self.condition).__name__}"
            )
        for extra in self.extra_deltas:
            if not _is_cost_delta(extra):
                raise ValueError(
                    f"CostModifier: extra_deltas must be CostDelta, got {type(extra).__name__}"
                )
        # The planner folds deltas into pure += accumulators (commutative),
        # so extra_deltas is a SET — sorted at construction.
        ordered = _set_sorted(self.extra_deltas)
        if ordered != self.extra_deltas:
            object.__setattr__(self, "extra_deltas", ordered)


@dataclass(frozen=True)
class EtBState:
    """The entered state of a permanent: `tapped` ("this creature enters
    tapped") and/or `initial_counters` ("enters with 3 +1/+1 counters",
    "this Equipment enters with a soul counter"). An Ability node on the
    card record. Each counter entry is a (CounterKind, Quantity) pair;
    `initial_counters` is a set — sorted at construction (the kind keys
    the counter map, so wording order carries no semantics). A
    no-op state (untapped, no counters) is rejected — a no-op is not a
    node in the tree (Seq's rule)."""

    tapped: bool = False
    initial_counters: tuple[tuple[CounterKind, Quantity], ...] = ()
    # ZNR kicker: "if it was kicked, it enters with a +1/+1 counter" — an
    # optional gate on the entering state (omitted from the bytes when None).
    condition: Filter | None = None

    def __post_init__(self) -> None:
        if self.condition is not None and not isinstance(self.condition, Filter):
            raise ValueError(
                f"EtBState: condition must be a Filter or None, got {self.condition!r}"
            )
        if not isinstance(self.tapped, bool):
            raise ValueError(f"EtBState: tapped must be a bool, got {self.tapped!r}")
        if not isinstance(self.initial_counters, tuple):
            raise ValueError(
                "EtBState: initial_counters must be a tuple of (CounterKind, Quantity)"
            )
        for entry in self.initial_counters:
            if not (isinstance(entry, tuple) and len(entry) == 2):
                raise ValueError(
                    "EtBState: each counter entry must be a (CounterKind, Quantity) pair"
                )
            kind, count = entry
            if not isinstance(kind, CounterKind):
                raise ValueError(
                    f"EtBState: counter kind must be a CounterKind, got {kind!r}"
                )
            if not _is_quantity(count):
                raise ValueError(
                    "EtBState: counter count must be a Quantity, got "
                    f"{type(count).__name__}"
                )
        if not self.tapped and not self.initial_counters:
            raise ValueError(
                "EtBState: a no-op state is not a node (tapped or counters required)"
            )
        # The counters are a dict keyed by kind, so the (kind, quantity)
        # entries are a SET — sort at construction.
        counters = _set_sorted(self.initial_counters)
        if counters != self.initial_counters:
            object.__setattr__(self, "initial_counters", counters)


@dataclass(frozen=True)
class EmblemAbility:
    """An emblem's embedded ability — emblems carry triggered/static
    abilities of their own (the Basri Ket / Garruk / Liliana emblems)."""

    embedded: Ability

    def __post_init__(self) -> None:
        if not _is_ability(self.embedded):
            raise ValueError(
                f"EmblemAbility: embedded must be an Ability, got {type(self.embedded).__name__}"
            )


@dataclass(frozen=True)
class KickerAbility:
    """A kicker head sentence (ZNR): the optional extra cost a
    spell may be cast for. NOT a CostModifier — the printed cost is never
    raised; the extra cost is an optional alternative paid at cast time,
    whose payment is observed by the card's other components via
    ``FAtomPred.WAS_KICKED``. The kicker's effect arm is encoded as the
    spell's own conditional effect (compiler fold), never fused into this
    node: {cost-variant} and {effect} stay orthogonal axes."""

    cost: Cost

    def __post_init__(self) -> None:
        if not isinstance(self.cost, Cost):
            # ValueError, not TypeError: from_dict across this whole module
            # contracts on ValueError for malformed payloads; TRY004 would
            # break that caller-facing contract.
            raise ValueError(  # noqa: TRY004
                f"KickerAbility: cost must be a Cost, got {type(self.cost).__name__}"
            )


@dataclass(frozen=True)
class BackFace:
    """A card's own back face as an encoded ability-tree member.

    The face is part of the card's OWN component set: its sentences alter
    outcomes if the face ever enters, so they are encoded here rather than
    dropped. ``abilities`` is the same tolerant compile of the face's
    sentences through the same vocabulary — no new atoms. The ENGINE never
    runs this subtree: every ``walk()`` consumer gate (executor
    produces_mana, compiler engine_support, coverage verb histograms)
    skips it explicitly — a face ability is not a playable engine
    capability. The nested abilities are validated as Ability members; the
    face's own name is the printed face name, never the combined
    ``"A // B"`` name.
    """

    face_name: str
    abilities: tuple[Ability, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.face_name, str) or not self.face_name.strip():
            raise ValueError(
                f"BackFace: face_name must be a non-empty str, got {self.face_name!r}"
            )
        if not isinstance(self.abilities, tuple) or any(
            not isinstance(ab, get_args(Ability)) for ab in self.abilities
        ):
            raise ValueError("BackFace: abilities must be a tuple of Ability members")


Ability = (
    StaticAbility
    | TriggeredAbility
    | ActivatedAbility
    | SpellAbility
    | KeywordAbility
    | ReplacementAbility
    | CostModifier
    | EtBState
    | EmblemAbility
    | KickerAbility
    | BackFace
)


# ---- CardRecord — the root node ----


@dataclass(frozen=True)
class CardRecord:
    """The root node: one card (or token) as a typed ability tree.

    Fields are the structured ingest of DESIGN_CARD_POOL step 1 plus the
    compiled abilities. P/T are Optional[Quantity]: a creature with
    dynamic P/T (Tarmogoyf-class, the Weird token) carries None plus a
    SET_PT ability; a non-creature can never carry P/T. `loyalty` is the
    starting loyalty (an ability, not P/T). `emblem` embeds
    the card's emblem as a nested CardRecord; the link is one-directional
    (the emblem does not point back) and validated in __post_init__.
    """

    oracle_id: str
    name: str
    type_line: str
    types: tuple[str, ...]
    subtypes: tuple[str, ...]
    supertypes: tuple[str, ...]
    colors: tuple[str, ...]
    color_identity: frozenset[str]
    mana_cost: Cost | None
    mana_value: int
    power: Quantity | None
    toughness: Quantity | None
    loyalty: int | None
    keywords: tuple[KeywordAbility, ...]
    abilities: tuple[Ability, ...]
    is_token: bool
    emblem: CardRecord | None = None

    def __post_init__(self) -> None:
        validate_oracle_id(self.oracle_id)
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"CardRecord: name must be a non-empty str, got {self.name!r}"
            )
        if not isinstance(self.type_line, str) or not self.type_line.strip():
            raise ValueError("CardRecord: type_line must be a non-empty str")
        if not self.types:
            raise ValueError("CardRecord: types must be non-empty")
        if any(c not in _COLORS for c in self.colors):
            raise ValueError(
                f"CardRecord: colors must be drawn from {_COLORS}, got {self.colors!r}"
            )
        if any(c not in _COLORS for c in self.color_identity):
            raise ValueError(f"CardRecord: color_identity must be drawn from {_COLORS}")
        if (
            isinstance(self.mana_value, bool)
            or not isinstance(self.mana_value, int)
            or self.mana_value < 0
        ):
            raise ValueError(
                f"CardRecord: mana_value must be an int >= 0, got {self.mana_value!r}"
            )
        if self.loyalty is not None and (
            isinstance(self.loyalty, bool)
            or not isinstance(self.loyalty, int)
            or self.loyalty <= 0
        ):
            raise ValueError(
                f"CardRecord: loyalty must be a positive int, got {self.loyalty!r}"
            )
        if ("Planeswalker" in self.types) != (self.loyalty is not None):
            raise ValueError(
                "CardRecord: loyalty must be set exactly when the card is a Planeswalker"
            )
        if self.mana_cost is not None and not isinstance(self.mana_cost, Cost):
            raise ValueError(
                f"CardRecord: mana_cost must be a Cost, got {type(self.mana_cost).__name__}"
            )
        if self.power is not None and not _is_quantity(self.power):
            raise ValueError(
                f"CardRecord: power must be a Quantity, got {type(self.power).__name__}"
            )
        if self.toughness is not None and not _is_quantity(self.toughness):
            raise ValueError(
                f"CardRecord: toughness must be a Quantity, got {type(self.toughness).__name__}"
            )
        if "Creature" not in self.types and (
            self.power is not None or self.toughness is not None
        ):
            raise ValueError("CardRecord: non-creatures cannot have P/T")
        for keyword in self.keywords:
            if not isinstance(keyword, KeywordAbility):
                raise ValueError(
                    f"CardRecord: keywords must be KeywordAbility, got {type(keyword).__name__}"
                )
        for ability in self.abilities:
            if not _is_ability(ability):
                raise ValueError(
                    f"CardRecord: abilities must be Ability, got {type(ability).__name__}"
                )
        if not isinstance(self.is_token, bool):
            raise ValueError(
                f"CardRecord: is_token must be a bool, got {self.is_token!r}"
            )
        if self.emblem is not None:
            if not isinstance(self.emblem, CardRecord):
                raise ValueError(
                    f"CardRecord: emblem must be a CardRecord, got {type(self.emblem).__name__}"
                )
            if "Planeswalker" not in self.types:
                raise ValueError("CardRecord: only a Planeswalker may carry an emblem")
            if "Emblem" not in self.emblem.types or not self.emblem.is_token:
                raise ValueError(
                    "CardRecord: emblem must be an Emblem-typed token record"
                )
            if self.emblem.emblem is not None:
                raise ValueError("CardRecord: an emblem cannot carry an emblem")
        # Granted keywords are a membership SET — ``keyword_of`` scans and
        # same-timestamp layers re-order by layer rules (layers'
        # ``_rebuild_maps`` sorts them), so the wording order of "vigilance,
        # trample" must not reach the bytes. ``abilities`` keeps printed
        # order.
        keywords = _set_sorted(self.keywords)
        if keywords != self.keywords:
            object.__setattr__(self, "keywords", keywords)


# ---------------------------------------------------------------------------
# Validation tables + type guards.
# Referenced from __post_init__ methods above; resolved at call time, so
# they live after the classes they validate.
# ---------------------------------------------------------------------------

_Q_CLASSES = (
    QConst,
    QX,
    QUnbounded,
    QCount,
    QProp,
    QBin,
    QThisTurn,
    QAtLeast,
    QAtMost,
    QDistinctColorCount,
    QPartyCount,
)
_F_CLASSES = (FAnd, FOr, FNot, FAtom)
_E_CLASSES = (
    Seq,
    Choose,
    OptionalEffect,
    Conditional,
    Repeat,
    EachPlayer,
    Atom,
    DelayedTrigger,
)
_A_CLASSES = (
    StaticAbility,
    TriggeredAbility,
    ActivatedAbility,
    SpellAbility,
    KeywordAbility,
    ReplacementAbility,
    CostModifier,
    EtBState,
    EmblemAbility,
    KickerAbility,
    BackFace,
)
_EV_CLASSES = (
    ZoneChangeEvent,
    CastSpellEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    CounterPlacedEvent,
    CreatureDiesEvent,
    BecomesBlockedEvent,
    TapStateEvent,
    AbilityTriggerEvent,
    TurnPhaseEvent,
    StepEvent,
    DamageDealtEvent,
    TargetingEvent,
    CardDrawnEvent,
    LifeGainedEvent,
    LifeLostEvent,
    SacrificeEvent,
    AbilityActivatedEvent,
    CounteredEvent,
)
_D_CLASSES = (
    DurationEot,
    DurationPermanent,
    DurationUntilNextTurn,
    DurationWhileCondition,
    DurationUntilLeaves,
    DurationUntilNextStep,
)
_COST_PART_CLASSES = (
    CostTap,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostLife,
    CostSacrifice,
    CostDiscard,
    CostPutCounter,
    CostLoyalty,
)
_COST_DELTA_CLASSES = (
    CostDeltaReduceGeneric,
    CostDeltaIncreaseGeneric,
    CostDeltaReduceMana,
    CostDeltaIncreaseLife,
    CostDeltaWaiveMana,
)


def _is_quantity(value: object) -> bool:
    return isinstance(value, _Q_CLASSES)


def _is_filter(value: object) -> bool:
    return isinstance(value, _F_CLASSES)


def _is_effect(value: object) -> bool:
    return isinstance(value, _E_CLASSES)


def _is_ability(value: object) -> bool:
    return isinstance(value, _A_CLASSES)


def _is_event(value: object) -> bool:
    return isinstance(value, _EV_CLASSES)


def _is_duration(value: object) -> bool:
    return isinstance(value, _D_CLASSES)


def _is_cost_part(value: object) -> bool:
    return isinstance(value, _COST_PART_CLASSES)


def _is_cost_delta(value: object) -> bool:
    return isinstance(value, _COST_DELTA_CLASSES)


# FAtom predicate -> (required slots, allowed slots).
_FATOM_RULES: dict[FAtomPred, tuple[frozenset[str], frozenset[str]]] = {
    FAtomPred.TYPE_EQ: (frozenset({"string_value"}), frozenset({"string_value"})),
    FAtomPred.SUBTYPE_EQ: (frozenset({"string_value"}), frozenset({"string_value"})),
    FAtomPred.SUPERTYPE_EQ: (frozenset({"string_value"}), frozenset({"string_value"})),
    FAtomPred.NAME_EQ: (frozenset({"string_value"}), frozenset({"string_value"})),
    FAtomPred.COLOR_HAS: (frozenset({"color"}), frozenset({"color"})),
    FAtomPred.COLOR_IN: (frozenset({"colors"}), frozenset({"colors"})),
    FAtomPred.COLOR_COUNT_GE: (frozenset({"count"}), frozenset({"count"})),
    FAtomPred.CMC_LE: (frozenset({"count"}), frozenset({"count"})),
    FAtomPred.CMC_GE: (frozenset({"count"}), frozenset({"count"})),
    FAtomPred.PT_LE: (frozenset({"count"}), frozenset({"count"})),
    FAtomPred.PT_GE: (frozenset({"count"}), frozenset({"count"})),
    FAtomPred.KEYWORD_HAS: (frozenset({"keyword"}), frozenset({"keyword"})),
    FAtomPred.HAS_COUNTER: (
        frozenset({"counter_kind", "count"}),
        frozenset({"counter_kind", "count"}),
    ),
    FAtomPred.CONTROLLER_IS: (frozenset({"who"}), frozenset({"who"})),
    FAtomPred.CONTROLLER_COUNT_GE: (
        frozenset({"inner_filter", "count"}),
        frozenset({"inner_filter", "count"}),
    ),
    FAtomPred.CONTROLLER_COUNT_LE: (
        frozenset({"inner_filter", "count"}),
        frozenset({"inner_filter", "count"}),
    ),
    FAtomPred.IS_TAPPED: (frozenset(), frozenset()),
    FAtomPred.IS_UNTAPPED: (frozenset(), frozenset()),
    FAtomPred.IS_ATTACKING: (frozenset(), frozenset()),
    FAtomPred.IS_BLOCKING: (frozenset(), frozenset()),
    FAtomPred.IS_SOURCE: (frozenset(), frozenset()),
    FAtomPred.IS_ANY_TARGET: (frozenset(), frozenset()),
    FAtomPred.IS_PERMANENT: (frozenset(), frozenset()),
    FAtomPred.IS_TOKEN: (frozenset(), frozenset()),
    FAtomPred.DIED_THIS_TURN: (frozenset(), frozenset()),
    FAtomPred.WAS_KICKED: (frozenset(), frozenset()),
    FAtomPred.HAS_KICKER: (frozenset(), frozenset()),
    # STACK_KIND_EQ: string_value from _STACK_KINDS only (_FATOM_STRING_VOCAB).
    FAtomPred.STACK_KIND_EQ: (frozenset({"string_value"}), frozenset({"string_value"})),
    FAtomPred.IS_ATTACHED_TO_SOURCE: (frozenset(), frozenset()),
    FAtomPred.POWER_LE: (frozenset({"count"}), frozenset({"count"})),
    FAtomPred.POWER_GE: (frozenset({"count"}), frozenset({"count"})),
    FAtomPred.NAME_CONTAINS: (frozenset({"string_value"}), frozenset({"string_value"})),
    FAtomPred.LIFE_GAINED_THIS_TURN_GE: (
        frozenset({"count", "who"}),
        frozenset({"count", "who"}),
    ),
    FAtomPred.CARDS_DRAWN_THIS_TURN_GE: (
        frozenset({"count", "who"}),
        frozenset({"count", "who"}),
    ),
    # FLIP_WON: "if you win the flip" (required who). "If you LOSE the
    # flip" is FNot(FAtom(FLIP_WON, who=YOU)), never a separate predicate.
    FAtomPred.FLIP_WON: (frozenset({"who"}), frozenset({"who"})),
    FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN: (
        frozenset({"who"}),
        frozenset({"who"}),
    ),
    FAtomPred.TARGETS_SOURCE: (frozenset(), frozenset()),
    FAtomPred.MAY_DONE: (frozenset(), frozenset()),
    # ENTERED_THIS_TURN_FROM: zone = the zone the object entered from.
    FAtomPred.ENTERED_THIS_TURN_FROM: (
        frozenset({"zone"}),
        frozenset({"zone"}),
    ),
    # CAST_THIS_TURN_FROM: zone = the cast's source zone; who = the
    # player who cast it (a referent Selector is legal).
    FAtomPred.CAST_THIS_TURN_FROM: (
        frozenset({"zone", "who"}),
        frozenset({"zone", "who"}),
    ),
    # MOVED_TO_ZONE_THIS_TURN: from_zone / to_zone name the two zones;
    # who = the controller the move was relative to (a referent Selector
    # is legal).
    FAtomPred.MOVED_TO_ZONE_THIS_TURN: (
        frozenset({"from_zone", "to_zone", "who"}),
        frozenset({"from_zone", "to_zone", "who"}),
    ),
    # WAS_CAST_THIS_TURN: who = the player who cast it (a referent
    # Selector is legal); no zone slot.
    FAtomPred.WAS_CAST_THIS_TURN: (
        frozenset({"who"}),
        frozenset({"who"}),
    ),
    # NOT_FIRST_DRAW_THIS_STEP: who = the player drawing (a referent
    # Selector is legal).
    FAtomPred.NOT_FIRST_DRAW_THIS_STEP: (
        frozenset({"who"}),
        frozenset({"who"}),
    ),
    # TURN_OF: who = the turn owner (ControllerRef or referent Selector).
    FAtomPred.TURN_OF: (frozenset({"who"}), frozenset({"who"})),
    # ZONE_COUNT_GE: who = the player whose zone is counted; zone = the
    # zone counted; inner_filter = the cards counted; count = the
    # threshold Quantity.
    FAtomPred.ZONE_COUNT_GE: (
        frozenset({"who", "zone", "inner_filter", "count"}),
        frozenset({"who", "zone", "inner_filter", "count"}),
    ),
    FAtomPred.IS_ATTACHED_TO: (
        frozenset({"referent"}),
        frozenset({"referent"}),
    ),
    FAtomPred.NAME_CHOSEN: (frozenset(), frozenset()),
    FAtomPred.IS_EXILED_WITH_SOURCE: (frozenset(), frozenset()),
    # CONTROLLER_COUNT_GT: both filters are REQUIRED (the comparison has
    # no one-sided reading).
    FAtomPred.CONTROLLER_COUNT_GT: (
        frozenset({"inner_filter", "right_inner_filter"}),
        frozenset({"inner_filter", "right_inner_filter"}),
    ),
    # LIFE_LEAD_OVER_START_GE: count = the threshold; no who slot (the
    # predicate binds its subject player directly).
    FAtomPred.LIFE_LEAD_OVER_START_GE: (frozenset({"count"}), frozenset({"count"})),
    FAtomPred.NAME_PARTITION_COUNT_GE: (
        frozenset({"inner_filter", "count"}),
        frozenset({"inner_filter", "count"}),
    ),
    FAtomPred.ATTACK_AGAINST_COUNT_GE: (
        frozenset({"count", "inner_filter"}),
        frozenset({"count", "inner_filter"}),
    ),
    # OPPONENT_OF: who = the side the subject must NOT be on.
    FAtomPred.OPPONENT_OF: (frozenset({"who"}), frozenset({"who"})),
    # Turn history: the event searched for and how much of it
    # (count >= 1 and its presence are checked in FAtom.__post_init__).
    FAtomPred.EVENT_THIS_TURN: (
        frozenset({"event", "count"}),
        frozenset({"event", "count"}),
    ),
    FAtomPred.SUBJECT_OF_EVENT_THIS_TURN: (
        frozenset({"event", "count"}),
        frozenset({"event", "count"}),
    ),
}

# Per-predicate closed vocabularies for FAtom.string_value.
# A predicate listed here takes only these tokens; every other string_value
# predicate (TYPE_EQ, SUBTYPE_EQ, SUPERTYPE_EQ, NAME_EQ, NAME_CONTAINS) reads
# open card data (type, subtype and card names).
_FATOM_STRING_VOCAB: dict[FAtomPred, tuple[str, ...]] = {
    FAtomPred.STACK_KIND_EQ: _STACK_KINDS,
}


# Atom role -> allowed value types. "types" is a tuple of card-type strings
# (data); "color" is a WUBRG string, colourless "C" or "ANY" (validated in
# AtomArgs.__post_init__).
_ROLE_TYPES: dict[str, tuple[type, ...]] = {
    "target": (Selector,),
    "source": (Selector,),
    "cards": (Selector,),
    "equipment": (Selector,),
    # "controller" takes a referent Selector too: Gloom Sower's "its
    # controller loses life" =
    # controller=Selector(referent="event"); the executor derives the
    # controller of the bound object.
    "controller": (ControllerRef, Selector),
    "amount": _Q_CLASSES,
    "count": _Q_CLASSES,
    "power": (*_Q_CLASSES, PtDelta),
    "toughness": (*_Q_CLASSES, PtDelta),
    "destination": (Zone,),
    "zone": (Zone,),
    "tokens": (TokenSpec,),
    "card_spec": (LiteralName,),
    "duration": _D_CLASSES,
    "ability": _A_CLASSES,
    "types": (tuple,),
    "counter_kind": (CounterKind,),
    "event": _EV_CLASSES,
    "condition": _F_CLASSES,
    "color": (str,),
    "cost": (Cost,),  # PAY's cost role; CAST's optional extra-cost / waiver role
    "tapped_on_enter": (bool,),  # MOVE_ZONE/SEARCH: "put it on the battlefield tapped"
    "unless": (Cost,),  # COUNTER_SPELL's "unless its controller pays X" role
    # name_filter: CHOOSE_NAME's name restriction ("choose a nonbasic card
    # name", Necromentia); Filter-valued like GRANT_ABILITY's ability /
    # PREVENT_EFFECT's condition roles.
    "name_filter": _F_CLASSES,
    # dealer / recipient: DEAL_DAMAGE's optional damage-surface roles —
    # "you" as recipient ("damage to you", Nine Lives) or a player-identity
    # Filter naming a side. Widened like "controller": a referent, a
    # referent Selector, or a Filter.
    "dealer": (ControllerRef, Selector) + _F_CLASSES,
    "recipient": (ControllerRef, Selector) + _F_CLASSES,
    # filter: MANA_POLICY's / GRANT_ACTIVATION's shape restriction role —
    # "spells that cost {X} or less to cast" — Filter-valued like the
    # name_filter / condition roles above.
    "filter": _F_CLASSES,
    # scope: MANA_POLICY's / DAMAGE_ASSIGN_POLICY's closed string
    # vocabularies, validated in AtomArgs.__post_init__ and per verb in
    # Atom.__post_init__.
    "scope": (str,),
    # step: PREVENT_EFFECT's "during a target's next untap step" role
    # (Frost Breath) — same Step enum the StepEvent and
    # DurationUntilNextStep fields carry.
    "step": (Step,),
    # window: GRANT_ACTIVATION's optional timing role — which
    # ActivationWindow the extra activation joins (Teferi, Master of
    # Time's +2: "until end of turn" = the sorcery window).
    "window": (ActivationWindow,),
    # MOVE_ZONE's departure zone: the mill/discard shapes ENCODE their
    # source zone instead of leaning on the verb name; a move without
    # "from" takes the objects from wherever they are.
    "from": (Zone,),
    # "journal_kind" — the journalled event kind ("MILL", else the "MOVE"
    # default); closed vocabulary _MOVE_JOURNAL_KINDS.
    "journal_kind": (str,),
    # "pop_order" — mill's top-of-library pop, pinned explicitly (never a
    # selector-order resolution); "TOP" only.
    "pop_order": (str,),
}

# Verb -> {role: required?}. MODIFY_PT and SET_PT additionally require at
# least one of power/toughness (enforced in Atom.__post_init__). The optional
# "duration" role (Duration) marks the temporary-effect verbs: MODIFY_PT, SET_PT,
# GRANT_ABILITY, GRANT_TYPE, PREVENT_EFFECT ("until end of turn"), plus TAP /
# UNTAP (a tap or untap is a temporary effect) and MANDATE_ATTACK (a continuous
# "attacks each combat if able").
_VERB_ROLES: dict[Verb, dict[str, bool]] = {
    # dealer / recipient: optional damage-surface roles — "damage THAT
    # WOULD BE DEALT TO you" restrictions (Nine Lives) and explicit "to
    # you" recipients.
    Verb.DEAL_DAMAGE: {
        "target": True,
        "amount": True,
        "dealer": False,
        "recipient": False,
    },
    Verb.DESTROY: {"target": True},
    Verb.EXILE: {"target": True},
    Verb.DRAW: {"controller": True, "amount": True},
    Verb.MILL: {"controller": True, "amount": True},
    Verb.GAIN_LIFE: {"controller": True, "amount": True},
    Verb.LOSE_LIFE: {"controller": True, "amount": True},
    Verb.ADD_MANA: {"controller": True, "amount": True, "color": False},
    # CREATE_TOKEN's optional controller: the anaphoric "ITS CONTROLLER
    # creates a … token" creator (Secure the Scene); omitted = the
    # ability's controller. A ControllerRef or referent Selector, as for
    # LOSE_LIFE.
    Verb.CREATE_TOKEN: {"tokens": True, "count": False, "controller": False},
    # TRIGGER_ADDITIONAL (Sanctum of All): how many EXTRA times the matched ability
    # triggers — a full Quantity (QConst 1 for "an additional time", a
    # derived QBin/QCount for a per-category self-repeat).
    Verb.TRIGGER_ADDITIONAL: {"count": True},
    Verb.PUT_COUNTER: {"target": True, "counter_kind": True, "count": True},
    Verb.REMOVE_COUNTER: {"target": True, "counter_kind": True, "count": True},
    Verb.MODIFY_PT: {
        "target": True,
        "power": False,
        "toughness": False,
        "duration": False,
    },
    # SET_PT: power/toughness are each optional,
    # but at least one is required (Kinetic Augur defines only power —
    # "power is equal to the number of …"); the at-least-one check is
    # enforced in Atom.__post_init__ alongside MODIFY_PT's.
    Verb.SET_PT: {
        "target": True,
        "power": False,
        "toughness": False,
        "duration": False,
    },
    Verb.GRANT_ABILITY: {"target": True, "ability": True, "duration": False},
    Verb.GRANT_TYPE: {"target": True, "types": True, "duration": False},
    Verb.TAP: {"target": True, "duration": False},
    Verb.UNTAP: {"target": True, "duration": False},
    # MOVE_ZONE / SEARCH: the optional `tapped_on_enter` bool role marks the
    # entered state ("put that card onto the battlefield tapped"); the
    # value is wrapped in a "Bool" tag inside the pairs.
    # MOVE_ZONE is the ONE move atom. `destination` is the mandatory `to`;
    # the objects arrive on one of three axes: `cards` (a selector or
    # binding), `target` (the designation lane — the role key spell
    # designation shadowing looks for), or `controller`+`amount` with
    # `pop_order`="TOP" (a mill's library pop). `from` states the
    # departure zone where the shape knows it (mill/discard);
    # `journal_kind` carries the journal row kind. Axes stay orthogonal:
    # operation × menu × count × journal kind, no fused special-case verb.
    # duration (CR 610.3): "exile that card until
    # this creature leaves the battlefield". The move happens; when the
    # duration ends, a second one-shot effect returns the object to its
    # previous zone. Only durations that end on an event are accepted
    # (_MOVE_ZONE_DURATIONS, checked in Atom.__post_init__).
    Verb.MOVE_ZONE: {
        "destination": True,
        "cards": False,
        "target": False,
        "controller": False,
        "amount": False,
        "from": False,
        "journal_kind": False,
        "pop_order": False,
        "tapped_on_enter": False,
        "duration": False,
    },
    Verb.SEARCH: {
        "cards": True,
        "destination": True,
        "controller": False,
        "tapped_on_enter": False,
    },
    Verb.SHUFFLE: {"zone": True},
    Verb.COUNTER_SPELL: {"target": True, "unless": False},
    Verb.COPY: {"source": True},
    Verb.SACRIFICE: {"target": True},
    Verb.DISCARD: {"controller": True, "cards": True},
    Verb.SCRY: {"controller": True, "count": True},
    # REVEAL's duration: "Play with the top card of your library revealed"
    # is a continuous revealed state — DurationPermanent, top of library
    # implicit as for LOOK_AT.
    Verb.REVEAL: {"controller": True, "count": True, "duration": False},
    Verb.LOOK_AT: {"controller": True, "count": True},
    Verb.ATTACH: {"equipment": True, "target": True},
    # GAIN_CONTROL's duration: "gain control of target creature until end
    # of turn" (Traitorous Greed), "…until this creature leaves the
    # battlefield" pairs with DurationUntilLeaves.
    Verb.GAIN_CONTROL: {"target": True, "controller": True, "duration": False},
    # PREVENT_EFFECT's step: Frost Breath's "a target's next untap step" is
    # prevented during Step.UNTAP — the step slot names WHICH step the
    # prevention covers, paired with DurationUntilNextStep.
    Verb.PREVENT_EFFECT: {
        "condition": True,
        "event": True,
        "controller": False,
        "duration": False,
        "step": False,
    },
    Verb.PHASE_IN: {"cards": True, "controller": True},
    Verb.PHASE_OUT: {"target": True},
    Verb.EXTRA_TURN: {"count": True},
    Verb.END_TURN: {},
    Verb.MANDATE_ATTACK: {"cards": True, "controller": False, "duration": False},
    # MANDATE_BLOCK mirrors MANDATE_ATTACK exactly — "must be blocked if
    # able" (Canopy Stalker); subject-scoped.
    Verb.MANDATE_BLOCK: {"cards": True, "controller": False, "duration": False},
    # CAST: source is the Selector over the source zone (top-of-library via
    # Zone.position). The optional `cost` role carries the cost paid
    # BEYOND the spell's own — an empty Cost() is the cost-waiver reading
    # ("cast ... without paying its mana cost"); Cost(parts=(...)) are
    # additional costs ("by paying 2 life and discarding a card in
    # addition to its other costs").
    Verb.CAST: {"source": True, "cost": False},
    # PAY: pay a cost as an effect ("you may pay {2}", with "if you do").
    Verb.PAY: {"cost": True},
    # LOSE_GAME: no roles — the effect is the loss itself.
    Verb.LOSE_GAME: {},
    # FLIP_COIN: no roles — the coin is flipped; the outcome is read by
    # FAtomPred.FLIP_WON, never by an arg.
    Verb.FLIP_COIN: {},
    # CHOOSE: `target` is the pool chosen FROM (typically a
    # referent="result" Selector over the previous sentence's zone); the
    # pick records the ability's result register.
    Verb.CHOOSE: {"target": True, "count": False, "duration": False},
    # CHOOSE_NAME: "choose a name" (Runed Halo — no filter; Necromentia —
    # "a nonbasic card name", name_filter). The pick is read back by
    # FAtomPred.NAME_CHOSEN; the optional filter only narrows which names
    # are legal picks.
    Verb.CHOOSE_NAME: {"name_filter": False},
    # FIGHT: the attacker is the source/IT referent, never a role.
    Verb.FIGHT: {"target": True},
    # LOSE_ABILITY mirrors GRANT_ABILITY's roles exactly.
    Verb.LOSE_ABILITY: {"target": True, "ability": True, "duration": False},
    # GET_EMBLEM: NO roles (see the Verb member).
    Verb.GET_EMBLEM: {},
    # ADD_LAND_PLAY: `count` = the number of additional plays, `duration`
    # scopes the grant (DurationPermanent for "on each of your turns").
    Verb.ADD_LAND_PLAY: {"count": False, "duration": False},
    # MANA_POLICY: scope THIS_MANA restricts the mana the ability added
    # (Vodalian Arcanist); scope ALL_YOURS is a standing permission over
    # the player's mana (Chromatic Orrery), with a filter over the spells
    # it applies to.
    Verb.MANA_POLICY: {"scope": True, "filter": False},
    # GRANT_ACTIVATION: filter = the permanents whose abilities may be
    # activated (a NAME_CONTAINS("Teferi") gate); window = the
    # ActivationWindow the extra activation joins.
    Verb.GRANT_ACTIVATION: {"filter": True, "window": False},
    # DAMAGE_ASSIGN_POLICY: scope carries the closed _DAMAGE_ASSIGN_SCOPES
    # vocabulary (AS_UNBLOCKED); filter optionally narrows the affected
    # damage dealers.
    Verb.DAMAGE_ASSIGN_POLICY: {"scope": True, "filter": False},
}

# Keyword -> tuple of allowed param signatures; each signature is a tuple
# of per-position allowed type tuples (so the arity check and the
# isinstance check both read off the same structure).
_KEYWORD_PARAMS: dict[Keyword, tuple[tuple[tuple[type, ...], ...], ...]] = {
    Keyword.SCRY: ((_Q_CLASSES,),),
    Keyword.MILL: ((_Q_CLASSES,),),
    Keyword.BATTALION: ((_Q_CLASSES,),),
    Keyword.PROTECTION: ((_F_CLASSES,),),
    Keyword.HEXPROOF: ((), (_F_CLASSES,)),
    # "Enchant [object or player]" (CR 702.5a) carries what
    # the Aura may target and enchant; bare when the Enchant line did not parse.
    Keyword.ENCHANT: ((), (_F_CLASSES,)),
}


# ---------------------------------------------------------------------------
# Serialization — to_dict / from_dict / canonical_json / fingerprint.
#
# Stable encoding (golden files and fingerprints depend on it — never renumber):
#   dataclass   -> {"tag": <ClassName>, <field>: enc, ...}
#   Enum        -> {"tag": <EnumClassName>, "name": <MEMBER>}
#   frozenset   -> {"tag": "ColorSet", "items": <sorted list>}
#   tuple       -> plain JSON list (element type is known from the field
#                  spec at decode time)
#   str/int/bool/None -> bare JSON values
# Inside AtomArgs pairs, every value is always wrapped in a tag
# ("String" / "StringTuple" / "Bool" / enum tag / dataclass tag) so no
# information is lost inside the pairs tuple.
# ---------------------------------------------------------------------------

_ENUMS: dict[str, type[Enum]] = {
    "Verb": Verb,
    "SelectorMode": SelectorMode,
    "ZoneKind": ZoneKind,
    "ZonePosition": ZonePosition,
    "ControllerRef": ControllerRef,
    "QPropField": QPropField,
    "QAgg": QAgg,
    "QBinOp": QBinOp,
    "Rounding": Rounding,
    "ThisTurnKind": ThisTurnKind,
    "FAtomPred": FAtomPred,
    "CounterKind": CounterKind,
    "SpellKind": SpellKind,
    "Keyword": Keyword,
    "PtDirection": PtDirection,
    "Phase": Phase,
    "Step": Step,
    "ActivationWindow": ActivationWindow,
    "AbilityKind": AbilityKind,
}

_DATACLASSES: tuple[type, ...] = (
    QConst,
    QX,
    QUnbounded,
    QCount,
    QProp,
    QBin,
    QThisTurn,
    QAtLeast,
    QAtMost,
    QDistinctColorCount,
    QPartyCount,
    Zone,
    Selector,
    FAnd,
    FOr,
    FNot,
    FAtom,
    DurationEot,
    DurationPermanent,
    DurationUntilNextTurn,
    DurationWhileCondition,
    DurationUntilLeaves,
    DurationUntilNextStep,
    ZoneChangeEvent,
    CastSpellEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    CounterPlacedEvent,
    CreatureDiesEvent,
    BecomesBlockedEvent,
    TapStateEvent,
    AbilityTriggerEvent,
    TurnPhaseEvent,
    StepEvent,
    DamageDealtEvent,
    TargetingEvent,
    CardDrawnEvent,
    LifeGainedEvent,
    LifeLostEvent,
    SacrificeEvent,
    AbilityActivatedEvent,
    CounteredEvent,
    LiteralName,
    PtDelta,
    TokenSpec,
    CostTap,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostLife,
    CostSacrifice,
    CostDiscard,
    CostPutCounter,
    CostLoyalty,
    Cost,
    CostDeltaReduceGeneric,
    CostDeltaIncreaseGeneric,
    CostDeltaReduceMana,
    CostDeltaIncreaseLife,
    CostDeltaWaiveMana,
    AtomArgs,
    Atom,
    Seq,
    Choose,
    OptionalEffect,
    Conditional,
    Repeat,
    EachPlayer,
    DelayedTrigger,
    StaticAbility,
    TriggeredAbility,
    ActivatedAbility,
    SpellAbility,
    KeywordAbility,
    ReplacementAbility,
    CostModifier,
    EtBState,
    EmblemAbility,
    KickerAbility,
    BackFace,
    CardRecord,
)

_CLASS_BY_TAG: dict[str, type] = {c.__name__: c for c in _DATACLASSES}
_TAG: dict[type, str] = {c: c.__name__ for c in _DATACLASSES}

# tag -> ((field, converter), ...). A converter is a scalar (int, bool, str),
# opt:X, tup:X, enum:<Name>, one of the named cases in _decode (colorset,
# qprop_referent, atom_pairs, ...) or a union name in _UNION_CONVS.
_SPECS: dict[str, tuple[tuple[str, str], ...]] = {
    "QConst": (("value", "int"),),
    "QX": (),
    "QUnbounded": (),
    "QCount": (("selector", "selector"),),
    "QDistinctColorCount": (("selector", "selector"),),
    "QPartyCount": (("selector", "selector"),),
    "QProp": (
        ("referent", "qprop_referent"),
        ("field", "enum:QPropField"),
        ("agg", "enum:QAgg"),
    ),
    "QBin": (
        ("op", "enum:QBinOp"),
        ("left", "quantity"),
        ("right", "quantity"),
        ("rounding", "opt:enum:Rounding"),
    ),
    "QThisTurn": (("kind", "enum:ThisTurnKind"), ("referent", "enum:ControllerRef")),
    "QAtLeast": (("n", "int"),),
    "QAtMost": (("n", "int"),),
    "Zone": (
        ("kind", "enum:ZoneKind"),
        ("controller", "enum:ControllerRef"),
        ("position", "opt:enum:ZonePosition"),
    ),
    "Selector": (
        ("count", "quantity"),
        ("mode", "enum:SelectorMode"),
        ("filter", "filter"),
        # zones is never omitted: it has no empty default.
        ("zones", "tup:zone"),
        ("referent", "opt:referent_str"),
    ),
    "FAnd": (("children", "tup:filter"),),
    "FOr": (("children", "tup:filter"),),
    "FNot": (("inner", "filter"),),
    "FAtom": (
        ("pred", "enum:FAtomPred"),
        ("string_value", "opt:str"),
        ("color", "opt:str"),
        ("colors", "tup:str"),
        ("count", "opt:quantity"),
        ("counter_kind", "opt:enum:CounterKind"),
        ("keyword", "opt:enum:Keyword"),
        # who: a ControllerRef OR a tagged referent Selector dict.
        ("who", "opt:controller_ref_or_selector"),
        ("inner_filter", "opt:filter"),
        ("zone", "opt:zone"),
        ("from_zone", "opt:zone"),
        ("to_zone", "opt:zone"),
        ("referent", "opt:str"),
        ("right_inner_filter", "opt:filter"),
        ("event", "opt:event"),
    ),
    "DurationEot": (),
    "DurationPermanent": (),
    "DurationUntilNextTurn": (),
    "DurationWhileCondition": (("filter", "filter"),),
    # source: a referent string, serialized bare; its vocabulary is
    # validated in __post_init__ (so also on the from_dict path).
    "DurationUntilLeaves": (("source", "str"),),
    "DurationUntilNextStep": (("step", "enum:Step"), ("owner_scoped", "bool")),
    "ZoneChangeEvent": (
        ("from_zone", "zone"),
        ("to_zone", "zone"),
        ("subject", "opt:filter"),
    ),
    "CastSpellEvent": (
        ("filter", "filter"),
        ("actor", "opt:filter"),
        ("from_zone", "opt:zone"),
        ("ordinal", "opt:int"),
        ("from_zone_not", "opt:zone"),
    ),
    "DeclareAttackersEvent": (
        ("filter", "filter"),
        ("attacked", "opt:filter"),
    ),
    "DeclareBlockersEvent": (
        ("filter", "filter"),
        ("subject", "opt:filter"),
        ("blocked", "opt:filter"),
        ("count", "opt:quantity"),
    ),
    "CounterPlacedEvent": (
        ("counter_kind", "enum:CounterKind"),
        ("filter", "filter"),
        ("count", "opt:quantity"),
    ),
    "CreatureDiesEvent": (("filter", "filter"),),
    "BecomesBlockedEvent": (("filter", "filter"),),
    "TapStateEvent": (("tapped", "bool"), ("filter", "filter")),
    "AbilityTriggerEvent": (("filter", "filter"),),
    "TurnPhaseEvent": (("phase", "enum:Phase"), ("actor", "opt:filter")),
    "StepEvent": (
        ("phase", "enum:Phase"),
        ("step", "enum:Step"),
        ("controller", "enum:ControllerRef"),
    ),
    "DamageDealtEvent": (
        ("amount", "quantity"),
        ("filter", "filter"),
        ("source", "opt:filter"),
        ("combat", "opt:bool"),
    ),
    "TargetingEvent": (("filter", "filter"), ("actor", "opt:filter")),
    "CardDrawnEvent": (
        ("actor", "opt:filter"),
        ("ordinal", "opt:int"),
    ),
    "LifeGainedEvent": (("actor", "opt:filter"),),
    "LifeLostEvent": (("actor", "opt:filter"),),
    "SacrificeEvent": (("actor", "opt:filter"),),
    "AbilityActivatedEvent": (
        ("source", "filter"),
        ("kind", "enum:AbilityKind"),
        ("actor", "opt:filter"),
    ),
    "CounteredEvent": (("filter", "filter"),),
    "LiteralName": (("name", "str"),),
    "PtDelta": (("direction", "enum:PtDirection"), ("magnitude", "quantity")),
    "TokenSpec": (
        ("name", "str"),
        ("type_line", "str"),
        ("types", "tup:str"),
        ("subtypes", "tup:str"),
        ("power", "opt:quantity"),
        ("toughness", "opt:quantity"),
        ("keywords", "tup:enum:Keyword"),
        ("abilities", "tup:ability"),
        ("colors", "tup:str"),
        ("enters_tapped", "opt:bool"),
        ("enters_attacking", "opt:bool"),
    ),
    "CostTap": (("target", "opt:selector"),),
    "CostManaColor": (("color", "str"), ("amount", "quantity")),
    "CostManaGeneric": (("amount", "quantity"),),
    "CostManaHybrid": (("colors", "tup:str"), ("amount", "quantity")),
    "CostLife": (("amount", "quantity"),),
    "CostSacrifice": (("target", "selector"),),
    "CostDiscard": (("target", "selector"),),
    "CostPutCounter": (
        ("counter_kind", "enum:CounterKind"),
        ("target", "selector"),
        ("count", "quantity"),
    ),
    "CostLoyalty": (("delta", "loyalty_delta"),),
    "Cost": (("parts", "tup:cost_part"),),
    "CostDeltaReduceGeneric": (("amount", "quantity"),),
    "CostDeltaIncreaseGeneric": (("amount", "quantity"),),
    "CostDeltaReduceMana": (("color", "str"), ("amount", "quantity")),
    "CostDeltaIncreaseLife": (("amount", "quantity"),),
    "CostDeltaWaiveMana": (),
    "AtomArgs": (("pairs", "atom_pairs"),),
    "Atom": (("verb", "enum:Verb"), ("args", "atom_args")),
    "Seq": (("steps", "tup:effect"),),
    "Choose": (("count", "quantity"), ("options", "tup:effect")),
    "OptionalEffect": (("inner", "effect"),),
    "Conditional": (
        ("pred", "filter"),
        ("then_effect", "effect"),
        ("else_effect", "opt:effect"),
    ),
    "Repeat": (("count", "quantity"), ("inner", "effect")),
    "EachPlayer": (("ref", "enum:ControllerRef"), ("effect", "effect")),
    "DelayedTrigger": (
        ("duration", "duration"),
        ("event", "event"),
        ("condition", "opt:filter"),
        ("effect", "effect"),
        ("once_per_event", "opt:bool"),
    ),
    "StaticAbility": (("effect", "effect"), ("condition", "opt:filter")),
    "TriggeredAbility": (
        ("event", "event"),
        ("condition", "opt:filter"),
        ("effect", "effect"),
        ("once_per_event", "opt:bool"),
    ),
    "ActivatedAbility": (
        ("cost", "cost"),
        ("effect", "effect"),
        ("condition", "opt:filter"),
        ("timing", "opt:enum:ActivationWindow"),
    ),
    "SpellAbility": (
        ("kind", "enum:SpellKind"),
        ("effect", "opt:effect"),
        ("additional_costs", "tup:cost"),
    ),
    "KeywordAbility": (("keyword", "enum:Keyword"), ("params", "tup:keyword_param")),
    "ReplacementAbility": (
        ("event", "event"),
        ("condition", "opt:filter"),
        ("action", "effect"),
    ),
    "CostModifier": (
        ("filter", "filter"),
        # controller_ref: a ControllerRef OR a Selector (the controller of
        # the selected object).
        ("controller_ref", "controller_ref_or_selector"),
        ("delta", "cost_delta"),
        ("condition", "opt:filter"),
        ("extra_deltas", "tup:cost_delta"),
    ),
    "EtBState": (
        ("tapped", "bool"),
        ("initial_counters", "tup:counter_placement"),
        ("condition", "opt:filter"),
    ),
    "KickerAbility": (("cost", "cost"),),
    "EmblemAbility": (("embedded", "ability"),),
    # A face with no abilities serializes as {face_name} only (its text
    # lives in the unparsed register, never in a fake tree).
    "BackFace": (("face_name", "str"), ("abilities", "tup:ability")),
    "CardRecord": (
        ("oracle_id", "str"),
        ("name", "str"),
        ("type_line", "str"),
        ("types", "tup:str"),
        ("subtypes", "tup:str"),
        ("supertypes", "tup:str"),
        ("colors", "tup:str"),
        ("color_identity", "colorset"),
        ("mana_cost", "opt:cost"),
        ("mana_value", "int"),
        ("power", "opt:quantity"),
        ("toughness", "opt:quantity"),
        ("loyalty", "opt:int"),
        ("keywords", "tup:keyword_ability"),
        ("abilities", "tup:ability"),
        ("is_token", "bool"),
        ("emblem", "opt:card"),
    ),
}

_QUANTITY_TAGS = frozenset(
    {
        "QConst",
        "QX",
        "QUnbounded",
        "QCount",
        "QProp",
        "QBin",
        "QThisTurn",
        "QAtLeast",
        "QAtMost",
        "QDistinctColorCount",
        "QPartyCount",
    }
)
_FILTER_TAGS = frozenset({"FAnd", "FOr", "FNot", "FAtom"})
_EFFECT_TAGS = frozenset(
    {
        "Seq",
        "Choose",
        "OptionalEffect",
        "Conditional",
        "Repeat",
        "EachPlayer",
        "Atom",
        "DelayedTrigger",
    }
)
_ABILITY_TAGS = frozenset(
    {
        "StaticAbility",
        "TriggeredAbility",
        "ActivatedAbility",
        "SpellAbility",
        "KeywordAbility",
        "ReplacementAbility",
        "CostModifier",
        "EtBState",
        "EmblemAbility",
        "KickerAbility",
        "BackFace",
    }
)
_EVENT_TAGS = frozenset(
    {
        "ZoneChangeEvent",
        "CastSpellEvent",
        "DeclareAttackersEvent",
        "DeclareBlockersEvent",
        "CounterPlacedEvent",
        "CreatureDiesEvent",
        "BecomesBlockedEvent",
        "TapStateEvent",
        "AbilityTriggerEvent",
        "TurnPhaseEvent",
        "StepEvent",
        "DamageDealtEvent",
        "TargetingEvent",
        "CardDrawnEvent",
        "LifeGainedEvent",
        "LifeLostEvent",
        "SacrificeEvent",
        "AbilityActivatedEvent",
        "CounteredEvent",
    }
)
_COST_DELTA_TAGS = frozenset(
    {
        "CostDeltaReduceGeneric",
        "CostDeltaIncreaseGeneric",
        "CostDeltaReduceMana",
        "CostDeltaIncreaseLife",
        "CostDeltaWaiveMana",
    }
)
_DURATION_TAGS = frozenset(
    {
        "DurationEot",
        "DurationPermanent",
        "DurationUntilNextTurn",
        "DurationWhileCondition",
        "DurationUntilLeaves",
        "DurationUntilNextStep",
    }
)
_COST_PART_TAGS = frozenset(
    {
        "CostTap",
        "CostManaColor",
        "CostManaGeneric",
        "CostManaHybrid",
        "CostLife",
        "CostSacrifice",
        "CostDiscard",
        "CostPutCounter",
        "CostLoyalty",
    }
)
_KEYWORD_PARAM_TAGS = _QUANTITY_TAGS | _FILTER_TAGS | frozenset({"Cost"})
_ATOM_VALUE_TAGS = (
    _QUANTITY_TAGS
    | _FILTER_TAGS
    | _DURATION_TAGS
    | _EVENT_TAGS
    | _ABILITY_TAGS
    | frozenset(
        {
            "Selector",
            "Zone",
            "TokenSpec",
            "LiteralName",
            "PtDelta",
            "ControllerRef",
            "CounterKind",
            "Cost",  # PAY / CAST's `cost` role carries a full Cost
            # PREVENT_EFFECT's `step` role and GRANT_ACTIVATION's `window`
            # role carry enum values, like CounterKind / ControllerRef.
            "Step",
            "ActivationWindow",
        }
    )
)

_UNION_CONVS: dict[str, frozenset[str]] = {
    "quantity": _QUANTITY_TAGS,
    "filter": _FILTER_TAGS,
    "effect": _EFFECT_TAGS,
    "ability": _ABILITY_TAGS,
    "event": _EVENT_TAGS,
    "duration": _DURATION_TAGS,
    "zone": frozenset({"Zone"}),
    "selector": frozenset({"Selector"}),
    "cost": frozenset({"Cost"}),
    "cost_part": _COST_PART_TAGS,
    "cost_delta": _COST_DELTA_TAGS,
    "token": frozenset({"TokenSpec"}),
    "card": frozenset({"CardRecord"}),
    "keyword_ability": frozenset({"KeywordAbility"}),
    "keyword_param": _KEYWORD_PARAM_TAGS,
    "atom_args": frozenset({"AtomArgs"}),
}

# tag -> fields whose EMPTY DEFAULT (None, or the empty tuple) is
# serialized by OMITTING the key entirely, instead of serializing
# null / []. A field added to an existing class is registered here as well
# as in _SPECS, so every tree that does not use it keeps its exact bytes
# (without the row every existing golden byte-diffs on regeneration;
# pinned for TokenSpec and FAtom by test_ability_tree_r9.py). The older
# optional fields (CostTap.target, the first FAtom slots, ...) serialize
# their null / [] defaults. from_dict accepts these keys both absent (the
# empty default is injected) and present. This table is the only place a
# spec field may be absent from the tagged dict.
_OMIT_IF_EMPTY: dict[str, frozenset[str]] = {
    "EtBState": frozenset({"condition"}),
    "BackFace": frozenset({"abilities"}),
    "QBin": frozenset({"rounding"}),
    # Selector.zones is REQUIRED (no empty default): a dict without zones
    # must FAIL LOUD at from_dict, never be silently defaulted.
    "Selector": frozenset({"referent"}),
    "Zone": frozenset({"position"}),
    "ZoneChangeEvent": frozenset({"subject"}),
    "DeclareAttackersEvent": frozenset({"attacked"}),
    "DeclareBlockersEvent": frozenset({"subject", "blocked", "count"}),
    "CastSpellEvent": frozenset({"actor", "from_zone", "ordinal", "from_zone_not"}),
    "CardDrawnEvent": frozenset({"ordinal", "actor"}),
    "TurnPhaseEvent": frozenset({"actor"}),
    "LifeGainedEvent": frozenset({"actor"}),
    "LifeLostEvent": frozenset({"actor"}),
    "SacrificeEvent": frozenset({"actor"}),
    "AbilityActivatedEvent": frozenset({"actor"}),
    "TargetingEvent": frozenset({"actor"}),
    "CounterPlacedEvent": frozenset({"count"}),
    "FAtom": frozenset(
        {"zone", "from_zone", "to_zone", "referent", "right_inner_filter", "event"}
    ),
    "TokenSpec": frozenset({"colors", "enters_tapped", "enters_attacking"}),
    "DamageDealtEvent": frozenset({"source", "combat"}),
    "CostModifier": frozenset({"condition", "extra_deltas"}),
    "SpellAbility": frozenset({"effect", "additional_costs"}),
    "StaticAbility": frozenset({"condition"}),
    "ActivatedAbility": frozenset({"condition", "timing"}),
    "TriggeredAbility": frozenset({"once_per_event"}),
    "DelayedTrigger": frozenset({"once_per_event"}),
}


def _decode_union(d: Any, tags: frozenset[str], label: str) -> Any:
    if not isinstance(d, dict):
        raise ValueError(f"{label}: expected a tagged dict, got {type(d).__name__}")
    tag = d.get("tag")
    if tag not in tags:
        raise ValueError(f"{label}: bad tag {tag!r} (expected one of {sorted(tags)})")
    return from_dict(str(tag), d)


def _decode(conv: str, d: Any) -> Any:
    if conv in _UNION_CONVS:
        return _decode_union(d, _UNION_CONVS[conv], conv)
    if conv == "int":
        if isinstance(d, bool) or not isinstance(d, int):
            raise ValueError(f"expected int, got {type(d).__name__}")
        return d
    if conv == "bool":
        if not isinstance(d, bool):
            raise ValueError(f"expected bool, got {type(d).__name__}")
        return d
    if conv == "str":
        if not isinstance(d, str):
            raise ValueError(f"expected str, got {type(d).__name__}")
        return d
    if conv == "loyalty_delta":
        # a literal int stays bare; a Quantity arrives as its tagged dict
        # (Ugin's "[−X]" dynamic loyalty cost).
        if isinstance(d, bool):
            raise ValueError(
                "CostLoyalty delta: expected an int or a Quantity, got bool"
            )
        if isinstance(d, int):
            return d
        return _decode_union(d, _QUANTITY_TAGS, "CostLoyalty delta")
    if conv.startswith("opt:"):
        if d is None:
            return None
        return _decode(conv[4:], d)
    if conv.startswith("tup:"):
        if not isinstance(d, list):
            raise ValueError(f"expected a list of {conv[4:]}, got {type(d).__name__}")
        return tuple(_decode(conv[4:], x) for x in d)
    if conv.startswith("enum:"):
        cls = _ENUMS.get(conv[5:])
        if cls is None:
            raise ValueError(f"unknown enum {conv[5:]!r}")
        if not isinstance(d, dict) or d.get("tag") != cls.__name__:
            raise ValueError(f"expected {cls.__name__} tagged dict, got {d!r}")
        try:
            return cls[str(d.get("name"))]
        except KeyError:
            raise ValueError(
                f"{cls.__name__}: unknown member {d.get('name')!r}"
            ) from None
    if conv == "colorset":
        if not isinstance(d, dict) or d.get("tag") != "ColorSet":
            raise ValueError(f"expected a ColorSet tagged dict, got {d!r}")
        items = d.get("items")
        if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
            raise ValueError("ColorSet: items must be a list of str")
        return frozenset(items)
    if conv == "qprop_referent":
        if isinstance(d, str):
            if d not in _QPROP_STR_REFERENTS:
                raise ValueError(
                    f"QProp referent string must be one of {_QPROP_STR_REFERENTS}, got {d!r}"
                )
            return d
        return _decode_union(d, frozenset({"Selector"}), "qprop referent")
    if conv == "referent_str":
        # Selector.referent: a bare
        # string from the _QPROP_STR_REFERENTS vocabulary — never a tagged
        # dict (a bound object's name is data, not a node).
        if not isinstance(d, str):
            raise ValueError(f"Selector referent must be a str, got {type(d).__name__}")
        if d not in _QPROP_STR_REFERENTS:
            raise ValueError(
                f"Selector referent string must be one of {_QPROP_STR_REFERENTS}, got {d!r}"
            )
        return d
    if conv == "controller_ref_or_selector":
        # Shared by FAtom.who and CostModifier.controller_ref: a
        # ControllerRef tagged dict, OR a Selector tagged dict (the
        # controller of the selected object).
        if isinstance(d, dict) and d.get("tag") == "Selector":
            return _decode_union(
                d, frozenset({"Selector"}), "controller_ref/who selector"
            )
        return _decode("enum:ControllerRef", d)
    if conv == "counter_placement":
        # an EtBState counter entry: [CounterKind, Quantity]
        if not isinstance(d, list) or len(d) != 2:
            raise ValueError(
                f"counter_placement must be [CounterKind, Quantity], got {d!r}"
            )
        return (_decode("enum:CounterKind", d[0]), _decode("quantity", d[1]))
    if conv == "atom_pairs":
        if not isinstance(d, list):
            raise ValueError(
                f"expected a list of [role, value] pairs, got {type(d).__name__}"
            )
        pairs: list[tuple[str, object]] = []
        for item in d:
            if not isinstance(item, list) or len(item) != 2:
                raise ValueError(f"atom pair must be [role, value], got {item!r}")
            role, value = item
            if not isinstance(role, str):
                raise ValueError(
                    f"atom pair role must be a str, got {type(role).__name__}"
                )
            pairs.append((role, _decode("atom_value", value)))
        return tuple(pairs)
    if conv == "atom_value":
        if not isinstance(d, dict):
            raise ValueError(
                f"atom value must be a tagged dict, got {type(d).__name__}"
            )
        tag = d.get("tag")
        if tag == "String":
            value = d.get("value")
            if not isinstance(value, str):
                raise ValueError(f"String atom value must hold a str, got {value!r}")
            return value
        if tag == "StringTuple":
            items = d.get("items")
            if not isinstance(items, list) or not all(
                isinstance(x, str) for x in items
            ):
                raise ValueError("StringTuple atom value must hold a list of str")
            return tuple(items)
        if tag == "Bool":
            value = d.get("value")
            if not isinstance(value, bool):
                raise ValueError(f"Bool atom value must hold a bool, got {value!r}")
            return value
        if tag in _ATOM_VALUE_TAGS:
            return _decode_union(d, _ATOM_VALUE_TAGS, "atom value")
        raise ValueError(f"atom value: unknown tag {tag!r}")
    raise ValueError(f"unknown converter {conv!r}")


def to_dict(node: Any) -> Any:
    """Serialize any grammar node to a JSON-ready value.

    A top-level node (always a dataclass) yields a tagged dict; the
    encoding is documented in the serialization section header.
    """
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        if type(node) is AtomArgs:
            return {
                "tag": "AtomArgs",
                "pairs": [
                    [role, _atom_value_to_dict(value)] for role, value in node.pairs
                ],
            }
        out: dict[str, Any] = {"tag": _TAG[type(node)]}
        omit = _OMIT_IF_EMPTY.get(type(node).__name__, frozenset())
        for field in dataclasses.fields(node):
            value = getattr(node, field.name)
            if field.name in omit and (value is None or value == ()):
                continue  # an _OMIT_IF_EMPTY field at its empty default: omit the key
            out[field.name] = to_dict(value)
        return out
    if isinstance(node, Enum):
        return {"tag": type(node).__name__, "name": node.name}
    if isinstance(node, frozenset):
        return {"tag": "ColorSet", "items": sorted(node)}
    if isinstance(node, tuple):
        return [to_dict(x) for x in node]
    if node is None or isinstance(node, (str, int, bool)):
        return node
    raise ValueError(f"not a grammar node: {type(node).__name__}")


def _atom_value_to_dict(value: Any) -> Any:
    """AtomArgs values are always wrapped in a tag (see section header)."""
    if isinstance(value, bool):
        # bool before anything else: a bare bool would otherwise fall
        # through to to_dict's bare passthrough and decode as no tag.
        return {"tag": "Bool", "value": value}
    if isinstance(value, str):
        return {"tag": "String", "value": value}
    if isinstance(value, tuple):
        if not all(isinstance(x, str) for x in value):
            raise ValueError("StringTuple atom value must hold str only")
        return {"tag": "StringTuple", "items": list(value)}
    return to_dict(value)


def from_dict(tag: str, d: Any) -> Any:
    """Rebuild the node with stable tag `tag` from its tagged dict `d`.

    Strict: the tag must match, unknown or missing fields raise, and every
    value is type-checked before the class is constructed (which re-runs
    __post_init__). Round-trip guarantee: from_dict(tag, to_dict(x)) == x.
    """
    if not isinstance(d, dict):
        raise ValueError(f"from_dict: {tag} expects a dict, got {type(d).__name__}")
    if d.get("tag") != tag:
        raise ValueError(
            f"from_dict: tag mismatch: asked {tag!r}, got {d.get('tag')!r}"
        )
    enum_cls = _ENUMS.get(tag)
    if enum_cls is not None:
        try:
            return enum_cls[str(d.get("name"))]
        except KeyError:
            raise ValueError(f"{tag}: unknown member {d.get('name')!r}") from None
    spec = _SPECS.get(tag)
    cls = _CLASS_BY_TAG.get(tag)
    if spec is None or cls is None:
        raise ValueError(f"from_dict: unknown tag {tag!r}")
    fields = {name: conv for name, conv in spec}
    omit = _OMIT_IF_EMPTY.get(tag, frozenset())
    extra = sorted(set(d) - set(fields) - {"tag"})
    if extra:
        if tag == "Selector" and "zone" in extra:
            raise ValueError(
                "from_dict: Selector: unknown fields ['zone'] — stale "
                "pre-R0 bytes: the R0 zone-fold replaced the scalar `zone` "
                "key with the single `zones` set key; re-compile/re-bake "
                "with post-fold code (no silent migration anywhere)"
            )
        raise ValueError(f"from_dict: {tag}: unknown fields {extra}")
    # omit-if-empty fields may be absent: the empty default is
    # injected. Every other missing field still raises.
    missing = sorted(f for f in set(fields) - set(d) if f not in omit)
    if missing:
        raise ValueError(f"from_dict: {tag}: missing fields {missing}")
    kwargs: dict[str, Any] = {}
    for name, conv in spec:
        if name in d:
            kwargs[name] = _decode(conv, d[name])
        elif conv.startswith("opt:"):
            kwargs[name] = None
        elif conv.startswith("tup:"):
            kwargs[name] = ()
        else:
            raise ValueError(
                f"from_dict: {tag}: omit-if-empty field {name!r} needs an "
                f"opt: or tup: converter, got {conv!r}"
            )
    return cls(**kwargs)


def canonical_json(node: Any) -> str:
    """Canonical JSON of `node` (sort_keys=True, separators=(',',':')) —
    the golden-file body."""
    return json.dumps(to_dict(node), sort_keys=True, separators=(",", ":"))


def fingerprint(node: Any) -> str:
    """sha256 hexdigest of canonical_json — the golden-file key."""
    return hashlib.sha256(canonical_json(node).encode("utf-8")).hexdigest()


def walk(node: Any, *, skip: type | tuple[type, ...] = ()) -> Iterator[Any]:
    """Yield every dataclass grammar node in `node`'s tree, pre-order —
    the card record first, then every child node (effects, selectors,
    zones, quantities, filters, events, costs, tokens, the emblem). Enum
    and scalar leaves are not yielded (their parent handles them). This is
    the instrument both the executor and the EC-2 unhandled-node-rate
    measurement (docs/METRICS.md §3) walk the tree with.

    `skip`: a node type (or tuple of types) whose SUBTREE is not
    descended — the node itself is still yielded. Every consumer that
    computes a card-level VERDICT from the tree (executor produces_mana,
    compiler engine_support, coverage verb histograms) passes
    skip=BackFace: an unplayable back face's abilities must never reach a
    front-face verdict.
    """
    yield node
    if skip and isinstance(node, skip):
        return
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        for field in dataclasses.fields(node):
            yield from _walk_value(getattr(node, field.name), skip)


def _walk_value(value: Any, skip: type | tuple[type, ...] = ()) -> Iterator[Any]:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        yield from walk(value, skip=skip)
    elif isinstance(value, tuple):
        for item in value:
            yield from _walk_value(item, skip)
    elif isinstance(value, frozenset):
        for item in value:
            yield from _walk_value(item, skip)


# ---- Ability classification (one CR 605.1a classifier) ----

#: Nodes whose subtree belongs to ANOTHER ability: a granted ability, a
#: keyword, a token's own abilities, and a delayed trigger (created when the
#: ability resolves, it triggers and resolves later as its own ability, CR
#: 603.7). CR 605.1a judges the activated ability itself, so none of its
#: criteria look inside them.
_FOREIGN_ABILITY_NODES: tuple[type, ...] = (*_A_CLASSES, TokenSpec, DelayedTrigger)

#: Verbs that always take cards from a library (CR 121.1 draw, 701.17a mill).
_LIBRARY_POP_VERBS = frozenset({Verb.DRAW, Verb.MILL})
#: Verbs that move the objects their roles name. They touch a library when a
#: zone they name is a library, or ZoneKind.ANY (which includes the library).
_ZONE_MOVING_VERBS = frozenset(
    {
        Verb.MOVE_ZONE,
        Verb.SEARCH,
        Verb.CAST,
        Verb.EXILE,
        Verb.DISCARD,
        Verb.SACRIFICE,
        Verb.DESTROY,
        Verb.COUNTER_SPELL,
    }
)


def is_loyalty_ability(ability: object) -> bool:
    """CR 606.2: an activated ability with a loyalty symbol in its cost is a
    loyalty ability. A [0] symbol counts (``CostLoyalty(0)``)."""
    return isinstance(ability, ActivatedAbility) and any(
        isinstance(part, CostLoyalty) for part in ability.cost.parts
    )


def _own_nodes(effect: Any) -> list[Any]:
    """The nodes of ``effect`` that belong to this ability (foreign ability
    subtrees are neither descended nor returned)."""
    return [
        node
        for node in walk(effect, skip=_FOREIGN_ABILITY_NODES)
        if not isinstance(node, _FOREIGN_ABILITY_NODES)
    ]


def _leaf_values(node: Any) -> Iterator[Any]:
    """The non-node field values of one node (enums, strings, ints), with
    tuples flattened. Dataclass children are skipped: ``walk`` yields them."""
    stack = [getattr(node, f.name) for f in dataclasses.fields(node)]
    while stack:
        value = stack.pop()
        if isinstance(value, tuple):
            stack.extend(value)
        elif not dataclasses.is_dataclass(value):
            yield value


def _requires_target(nodes: list[Any]) -> bool:
    """CR 115.1c/115.6: the ability says "target": a TARGET-mode selector, or
    the target-player coordinate anywhere (a role, a zone's controller, a
    filter's ``who``, an EachPlayer ref). The IR has no other way to bind
    TARGET_PLAYER than a designation, so any reference to it is a target."""
    for node in nodes:
        if isinstance(node, Selector) and node.mode is SelectorMode.TARGET:
            return True
        if any(value is ControllerRef.TARGET_PLAYER for value in _leaf_values(node)):
            return True
    return False


def _zone_holds_library(zone: Zone) -> bool:
    return zone.kind in (ZoneKind.LIBRARY, ZoneKind.ANY)


def _atom_moves_library_card(atom: Atom) -> bool:
    """Does this atom move a card to or from a library (CR 605.1a's fourth
    criterion)? A draw or mill always does. A zone-moving verb does when its
    destination is a library, or its departure (``from``, the mill shape's
    top-of-library pop, or the zones of the selector naming what moves) may
    be one. A referent selector ("it", "that card") carries the neutral zone
    Zone(ANY, ANY), not a departure zone, so it is not read: the atom that
    produced the referent is judged on its own. Scry and shuffle keep the
    cards in the library (701.22a, 701.24a), reveal and look move nothing."""
    if atom.verb in _LIBRARY_POP_VERBS:
        return True
    if atom.verb not in _ZONE_MOVING_VERBS:
        return False
    return any(_role_touches_library(role, value) for role, value in atom.args.pairs)


def _role_touches_library(role: str, value: object) -> bool:
    """One role of a zone-moving atom, judged for :func:`_atom_moves_library_card`."""
    if role == "destination":
        return isinstance(value, Zone) and value.kind is ZoneKind.LIBRARY
    if role == "from":
        return isinstance(value, Zone) and _zone_holds_library(value)
    if role in ("pop_order", "journal_kind"):
        return value in ("TOP", "MILL")  # the mill shape's top-of-library pop
    return (
        role in ("cards", "target", "source")
        and isinstance(value, Selector)
        and value.referent is None
        and any(_zone_holds_library(zone) for zone in value.zones)
    )


def _cost_moves_library_card(cost: Cost) -> bool:
    """CR 605.1a's fourth criterion on the cost side. Of the closed CostPart
    union only sacrifice and discard move cards (to the graveyard, CR 701.21a,
    701.9a); they touch a library only if their selector's zone is one. A new
    card-moving cost part must be added here."""
    return any(
        isinstance(part, (CostSacrifice, CostDiscard))
        and any(_zone_holds_library(zone) for zone in part.target.zones)
        for part in cost.parts
    )


def is_mana_ability(ability: object) -> bool:
    """CR 605.1a, every criterion: an activated ability is a mana ability iff
    (i) it doesn't require a target (115.6), (ii) it could add mana when it
    resolves (any ADD_MANA atom reachable in its own effect, whatever else the
    effect does and whatever the board allows, 605.2), (iii) it isn't a
    loyalty ability (606), and (iv) its cost and effect don't move any card
    to or from a library. Replacement effects other than the ability's own
    are not consulted (605.1a's last sentence): an outside replacement never
    sits in the ability's tree, and a self-replacement does.

    This is the engine's one classifier: the act-window drivers
    (``games.RandomPolicy``, ``bench.router``), the activation journal row
    and the NON_MANA activation lock all read it."""
    if not isinstance(ability, ActivatedAbility):
        return False
    if is_loyalty_ability(ability) or _cost_moves_library_card(ability.cost):
        return False
    nodes = _own_nodes(ability.effect)
    if not any(isinstance(node, Atom) and node.verb is Verb.ADD_MANA for node in nodes):
        return False
    if _requires_target(nodes):
        return False
    return not any(
        isinstance(node, Atom) and _atom_moves_library_card(node) for node in nodes
    )


def activation_matches_kind(ability: object, kind: AbilityKind) -> bool:
    """Does an activation of ``ability`` count for an AbilityActivatedEvent
    of ``kind``? ANY: every activated ability; NON_MANA: not a mana ability
    (605.1a; a loyalty ability is never one); LOYALTY: a loyalty ability."""
    if kind is AbilityKind.ANY:
        return True
    if kind is AbilityKind.NON_MANA:
        return not is_mana_ability(ability)
    if kind is AbilityKind.LOYALTY:
        return is_loyalty_ability(ability)
    raise ValueError(f"activation_matches_kind: unknown AbilityKind {kind!r}")
