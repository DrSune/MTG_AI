"""The typed ability-tree grammar: the ONE representation, TWO consumers.

NORTH_STAR / DESIGN_CARD_POOL.md step 1: the executor walks this tree and the
encoder reads the same tree. No second shape, no English anywhere (PITFALLS:
"English substrings cannot be the IR" — the ETB-substring bug killed forty
triggers for months). Every node is a frozen dataclass, every validation
fails loudly in ``__post_init__``, every node serializes to a tagged dict
with a stable string tag, so ``fingerprint`` is the golden-file key
(PC-4/PC-9) and ``walk`` is what the executor and the EC-2 unhandled-node
rate (METRICS.md §3) walk the tree with.

Design decisions (each pinned by tests in test_ability_tree.py):

- **Quantity on every numeric field, without exception**: ``QConst`` (>= 0),
  ``QX``, ``QUnbounded`` ("any number" — Siege Striker, Necromentia),
  ``QCount(selector)``, ``QProp(referent, field, agg)``, ``QBin``. QProp's
  referent is ``Selector | "source" | "controller" | "target" | "event"`` —
  the design lists three referents; "event" is the documented fourth because
  Brash Taunter ("deals that much damage") and Garruk's Harbinger ("look at
  that many cards") reference the triggering event's damage amount.
  ``QBinOp.DIV`` is floor division ("round up half" = ``(n+1)//2``, Peer
  into the Abyss). Negative quantities are rejected at construction: signed
  P/T adjustments go through :class:`PtDelta`; the single documented
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
- **Duration** = a union of four frozen dataclasses, not an enum: an enum
  cannot carry the ``Filter`` that ``WHILE_CONDITION`` needs.
- **Cost parts**: tap (``CostTap(target=None)`` = "tap the source" — every
  ``{T}:`` in the pool), generic/coloured/hybrid mana, life, sacrifice,
  discard, put-counter (Mazemind Tome's page-counter cost), loyalty (the
  only signed cost). Empty ``Cost()`` is a free activation.
- **Emblem**: ``CardRecord.emblem: Optional[CardRecord]`` — embedded in its
  planeswalker's record (the pool's 3 emblem-layout records are Basri Ket,
  Garruk Unleashed, Liliana's emblems). One-directional and validated: only
  a Planeswalker may carry an emblem; the emblem is an Emblem-typed token
  record that itself carries no emblem.
- **Selector.count by mode**: TARGET exact, CHOOSE up-to (``QUnbounded`` =
  any number), ALL ignores count (the compiler writes ``QConst(1)``),
  RANDOM exact; TARGET/RANDOM with ``QUnbounded`` are rejected.
- **Keyword enum**: 23 members — the pool's 24 MTGJSON keyword strings with
  "Hexproof from" folded into HEXPROOF (the "from X" is a Filter param, see
  ``_KEYWORD_PARAMS``).
- **Events**: 16 structured EventSpecs; ETB is a ZoneChange from anywhere to
  the battlefield, never a substring. declare_blockers / becomes_blocked /
  tap_state / targeting exist because pool cards need them (Pirate token
  "can't block", Gloom Sower, Ghostly Pilferer, Warden of the Woods,
  hexproof/protection statics). The T3 round (KNOWLEDGE 2026-09-19/02)
  added additive optional scoping to ZoneChangeEvent / CastSpellEvent /
  DamageDealtEvent (subject / controller+from_zone+ordinal / source+combat)
  and the new CardDrawn / LifeGained / Sacrifice events (controller
  referent); every such field defaults to None and serializes by
  OMITTING the key, so all pre-T3 trees keep byte-identical canonical
   JSON (pinned by test_ability_tree_t3.py).
- **r3b round (coin-flip, minimum-quantity, blocker subject)**: three
  additive, byte-stable vocabulary additions pinned by
  test_ability_tree_r3b.py — ``Verb.FLIP_COIN`` (no roles; "flip a coin",
  Tavern Swindler), ``FAtomPred.FLIP_WON`` (required ``who``; "you win the
  flip", so "you lose it" is ``FNot(FAtom(FLIP_WON, who=YOU))``),
  ``QAtLeast(n)`` (a quantity meaning "at least n", n >= 1 — the minimum
  the compiler previously had to lose to ``QUnbounded``), and
  ``DeclareBlockersEvent.subject`` (a ``Filter | None`` over the blocking
  creature, mirroring ``ZoneChangeEvent.subject``; omitted when None).
- **grammar round 4 (conditional & filtered triggers + object anaphora,
  KNOWLEDGE 2026-09-24/05)**: five additive, byte-stable items pinned by
  test_ability_tree_r5.py — ``CardDrawnEvent.ordinal`` (the Nth card drawn
  by the controller this turn; mirrors CastSpellEvent.ordinal — Jolrael,
  Mystic Skyfish), the new ``LoyaltyActivatedEvent(controller, filter)``
  ("Whenever you activate a loyalty ability of a Chandra planeswalker, ..."
  — Keral Keep Disciples), ``CastSpellEvent.from_zone_not`` ("from anywhere
  other than their hand" — Ghostly Pilferer; mutually exclusive with
  ``from_zone``), three ``FAtom`` zone slots (``zone`` / ``from_zone`` /
  ``to_zone``) with the condition predicates
  ``ENTERED_THIS_TURN_FROM`` / ``CAST_THIS_TURN_FROM`` /
  ``MOVED_TO_ZONE_THIS_TURN`` (Archfiend's Vessel, Barrin), and object
   anaphora: ``Selector.referent`` (the ``_QPROP_STR_REFERENTS`` vocabulary
   shared with QProp — "source" / "controller" / "target" / "event", where
   "event" is the triggering event's subject object; convention C2:
   CHOOSE + QConst(1) + neutral zone), plus the ``controller`` atom role
   and the ``CONTROLLER_IS`` ``who`` slot widened to ``ControllerRef |
   Selector`` (Gloom Sower, Feline Sovereign). Every new field defaults to
   None and serializes by OMITTING the key, so all pre-round-4 trees keep
   byte-identical canonical JSON.
 - **grammar round 5 (replacement/"instead" effects, KNOWLEDGE
   2026-09-24/07)**: four additive, byte-stable items pinned by
   test_ability_tree_r6.py — ``FAtomPred.WAS_CAST_THIS_TURN`` (required
   ``who``; "[the object] was cast this turn (by who)", Containment
   Priest; zone-agnostic, unlike ``CAST_THIS_TURN_FROM``),
   ``FAtomPred.NOT_FIRST_DRAW_THIS_STEP`` (required ``who``; "not the
   first card who draws in their draw step", Teferi's Ageless Insight —
   evaluated against the CardDrawnEvent subject),
   ``CounterPlacedEvent.count: Quantity | None`` (the number placed;
   "one or more" = ``QAtLeast(1)``) with the new
   ``QPropField.COUNTER_COUNT`` ("that many" =
   ``QProp("event", COUNTER_COUNT)`` — Conclave Mentor; event-referent
   only, like ``AMOUNT``), and ``CostModifier.controller_ref`` widened to
   ``ControllerRef | Selector`` (convention C7: a Selector means the
   controller of the selected object, and the modifier applies to costs
   that controller pays FOR the filtered object, including ``unless``
   payments — Lofty Denial; reuses the ``controller_ref_or_selector``
   dual conv). Every new field defaults to None and serializes by
   OMITTING the key, so all pre-round-5 trees keep byte-identical
   canonical JSON.
- **grammar round 8 / phase 8-A (decision-surface vocabulary, KNOWLEDGE
  2026-09-28/08)**, pinned by test_ability_tree_r9.py: ``QAtMost(n)``
  (convention C17 — TARGET-mode "up to n" designation), ``TokenSpec``
  trailing ``color`` / ``enters_tapped`` / ``enters_attacking`` optionals,
  the AtomArgs ``color`` vocabulary widened with ``"ANY"`` ("mana of any
  one color" — distinct from colourless ``"C"``), optional ``dealer`` /
  ``recipient`` roles on DEAL_DAMAGE, ``FAtomPred.
  IS_EXILED_WITH_SOURCE`` (no slots) and ``CONTROLLER_COUNT_GT`` (dual
  ``inner_filter`` / ``right_inner_filter`` comparison; the new FAtom
  filter slot is omit-when-None, byte-stable), ``Verb.GET_EMBLEM`` (no
  roles; C19 — the emblem payload is the card-level attach, quoted text
  never enters the IR) and ``Verb.ADD_LAND_PLAY`` (Azusa),
  ``ThisTurnKind.NONCOMBAT_DAMAGE``, and ``QProp`` COUNTER_COUNT widened
  to the "target" referent (Invigorating Surge). All items are additive;
  no template opts in yet (phase 8-B flips), so all 305 goldens stay
  byte-identical through 8-A.
- **No orphan guarantee yet**: verbs are cited to pool cards in docstrings;
  orphans are MEASURED by PC-6 and pruned then — the vocabulary is the
  Phase-1 hypothesis, not the post-hoc truth.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from MTG_bot.core.identity import validate_oracle_id

# The five magic colours. Colourless ("C") is only ever a value for the
# ADD_MANA "color" atom role; ColorSets are always drawn from WUBRG.
_COLORS = ("W", "U", "B", "R", "G")
_COLORLESS = "C"
# _ANY_COLOR (grammar round 8, R8-3): "mana of any one color" — the ADDER
# picks one colour at resolution (Jeskai Ascendancy-style triggers, the
# C-3 collapse repair). DISTINCT from _COLORLESS: "C" means colourless
# mana, "ANY" means a choice among WUBRG. Existing templates keep "C"
# until the 8-B fidelity flip.
_ANY_COLOR = "ANY"
# _MANA_POLICY_SCOPES (grammar round 9, R9-3, C21): the MANA_POLICY
# "scope" role vocabulary — THIS_MANA anchors the policy to the mana the
# ability itself added (Vodalian Arcanist's "Spend this mana only to
# cast instant or sorcery spells"), ALL_YOURS is a DurationPermanent
# permission over the player's whole mana pool (Orrery's "you may spend
# mana as though it were mana of any color"). Validated in
# AtomArgs.__post_init__ like the "color" role.
_MANA_POLICY_SCOPES = ("THIS_MANA", "ALL_YOURS")
# _DAMAGE_ASSIGN_SCOPES (grammar round 10, R10-4, C28): the
# DAMAGE_ASSIGN_POLICY "scope" role vocabulary — AS_UNBLOCKED is the
# "assign its combat damage as though it weren't blocked" policy (Garruk,
# Savage Herald's [−7]). MANA_POLICY twin: an AtomArgs-carried closed
# vocabulary, NO _SPECS field. AtomArgs validates against the union of
# all scope vocabularies; the per-verb vocabulary is enforced on the
# enclosing Atom (_SCOPE_VOCAB_BY_VERB).
_DAMAGE_ASSIGN_SCOPES = ("AS_UNBLOCKED",)
# _MOVE_JOURNAL_KINDS / _MOVE_POP_ORDERS (T4 P1a, 2026-10-07): the closed
# string vocabularies of the merged MOVE atom's two new string slots —
# journal_kind (A2 ii: the literal journalled event kind, "MILL" for the
# milled shape, "MOVE" default for every other) and pop_order (A2 iii:
# mill's TOP-of-library pop, pinned EXPLICITLY so the merged atom never
# falls onto a selector-order resolution). AtomArgs vocab-checks both,
# same precedent as "color"/"scope"; no cross-verb ambiguity, so the
# union check is complete at AtomArgs level.
_MOVE_JOURNAL_KINDS = ("MOVE", "MILL")
_MOVE_POP_ORDERS = ("TOP",)


# ---- Closed vocabularies (enums) ----


class Verb(Enum):
    """The closed verb vocabulary (DESIGN_CARD_POOL step 1: ~60 verbs).

    49 members covering the M21 pool; orphans are measured (PC-6) and pruned
    later. Each docstring cites the pool card(s) that need it. Every member
    carries an instance CLASS in ``VERB_CLASS`` (T4 §1 partition, below).

    T4 P1a (2026-10-07): the MILL/DISCARD/EXILE shapes COMPILE to the one
    merged MOVE_ZONE atom (docs/T4_SPEC.md §9 — destination + optional
    from/journal_kind/pop_order slots); their members stay in the enum for
    legacy decode of pre-merge serialisations and the CLASS partition of
    all 49, but the compiler and the executor table no longer emit or
    dispatch them.
    """

    DEAL_DAMAGE = "DEAL_DAMAGE"  # Brash Taunter (deals that much damage to target player or creature)
    DESTROY = "DESTROY"  # Legion's Judgment, Eliminate, Swift Response
    EXILE = "EXILE"  # Angelic Ascension, Transmogrify, Chandra [-9]
    DRAW = "DRAW"  # Opt, Frantic Inventory, Jeskai Elder
    MILL = "MILL"  # Carrion Grub ("mill four cards")
    GAIN_LIFE = "GAIN_LIFE"  # Faith's Fetters, Aven Gagglemaster, Witch's Cauldron
    LOSE_LIFE = "LOSE_LIFE"  # Grim Tutor
    ADD_MANA = "ADD_MANA"  # Vodalian Arcanist, Llanowar Visionary, Treasure token
    CREATE_TOKEN = "CREATE_TOKEN"  # Basri Ket, Falconer Adept, Gadrak (Treasure tokens)
    PUT_COUNTER = "PUT_COUNTER"  # Basri's Lieutenant (+1/+1), Malefic Scythe (soul), Basri Ket Emblem
    REMOVE_COUNTER = "REMOVE_COUNTER"  # Pestilent Haze ("remove two loyalty counters")
    MODIFY_PT = "MODIFY_PT"  # Defiant Strike, Jeskai Elder (prowess), Pestilent Haze (all creatures -2/-2)
    SET_PT = "SET_PT"  # Experimental Overload (Weird tokens' P/T), Tarmogoyf-class dynamic P/T
    GRANT_ABILITY = "GRANT_ABILITY"  # Riddleform (a 3/3 Sphinx creature with flying), Dub (first strike)
    GRANT_TYPE = (
        "GRANT_TYPE"  # Riddleform/Dub: "is a Knight in addition to its other types"
    )
    TAP = "TAP"  # Celestial Enforcer ("tap target creature")
    UNTAP = "UNTAP"  # Traitorous Greed ("untap that creature")
    MOVE_ZONE = "MOVE_ZONE"  # Sublime Epiphany (return to hand), Rise Again
    SEARCH = "SEARCH"  # Grim Tutor, Cultivate, Fierce Empath, Garruk's Unleashed emblem
    SHUFFLE = "SHUFFLE"  # Grim Tutor ("then shuffle"), Necromentia
    COUNTER_SPELL = "COUNTER_SPELL"  # Cancel, Lofty Denial, Miscast, Rewind
    COPY = "COPY"  # design list; no M21 card — orphan to be measured by PC-6
    SACRIFICE = "SACRIFICE"  # Goremand ("each opponent sacrifices a creature"); cost side: Village Rites, Witch's Cauldron
    DISCARD = "DISCARD"  # Teferi, Master of Time [+1] ("draw a card, then discard a card"), Jeskai Elder
    SCRY = "SCRY"  # Opt ("scry 1"), Riddleform
    REVEAL = "REVEAL"  # Track Down, Garruk's Harbinger
    LOOK_AT = "LOOK_AT"  # Opt, See the Truth, Garruk's Harbinger
    ATTACH = "ATTACH"  # Short Sword / Malefic Scythe (Equip)
    GAIN_CONTROL = "GAIN_CONTROL"  # Traitorous Greed
    PREVENT_EFFECT = "PREVENT_EFFECT"  # Faith's Fetters ("can't attack or block"), hexproof/protection statics
    PHASE_IN = "PHASE_IN"  # no M21 card — commander's general; kept pool-agnostic, PC-6 will say
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
    # CHOOSE (grammar round 7): "You choose a noncreature, nonland card
    # from it" (Duress, Kitesail) — the controller picks a set FROM the
    # `target` selector's pool (the anaphoric "it" of the preceding
    # sentence, bound via referent="result"); the choice is recorded as
    # the ability's result for later anaphora (C12).
    CHOOSE = "CHOOSE"
    CHOOSE_NAME = "CHOOSE_NAME"  # "choose a name" (Runed Halo, Necromentia); read back by FAtomPred.NAME_CHOSEN
    FIGHT = (
        "FIGHT"  # "this creature fights another target creature" (Brash
        # Taunter), "it fights up to one target creature you don't control"
        # (Primal Might). Attacker = the source/IT referent, `target` = the
        # fighter. Executor deferred per the MANDATE_BLOCK-orphan precedent.
    )
    LOSE_ABILITY = (
        "LOSE_ABILITY"  # "that permanent loses indestructible" (Soul
        # Sear) — mirrors GRANT_ABILITY's roles.
    )
    # GET_EMBLEM (grammar round 8, R8-7): "you get an emblem with
    # '…'" (Teferi, Master of Time [-X]; C19). A MARKER verb with NO
    # roles: the emblem payload is the card-level emblem attach
    # (compiler two-pass, compiler.py:1115) — the quoted emblem text
    # NEVER enters the ability IR. Executor deferred per the MANDATE_
    # ATTACK / FIGHT orphan precedent (PC-6 unaffected).
    GET_EMBLEM = "GET_EMBLEM"
    # ADD_LAND_PLAY (grammar round 8, R8-8): "You may play two additional
    # lands on each of your turns" (Azusa, Lost but Seeking); "you may
    # play one additional land each turn" (Uktabi Efreet). `count` = the
    # additional plays, `duration` scopes the grant. Executor deferred
    # per the FIGHT orphan precedent.
    ADD_LAND_PLAY = "ADD_LAND_PLAY"
    # MANA_POLICY (grammar round 9, R9-3, C21): spend-restriction verbs —
    # "Spend this mana only to cast instant or sorcery spells" (Vodalian
    # Arcanist; scope=THIS_MANA, event-anchored to the ability's own
    # ADD_MANA) and "you may spend mana as though it were mana of any
    # color" (Orrery; scope=ALL_YOURS, a DurationPermanent permission).
    # `scope` is the closed _MANA_POLICY_SCOPES string pair; `filter`
    # over narrows the allowed spend (a CastSpellEvent-shape Filter like
    # IS_INSTANT readings). Executor deferred per the ADD_LAND_PLAY
    # orphan precedent.
    MANA_POLICY = "MANA_POLICY"
    # GRANT_ACTIVATION (grammar round 9, R9-7): "You may activate
    # loyalty abilities of [targets] whenever you wish" (Teferi, Master
    # of Time — the NAME_CONTAINS("Teferi") gate closes the 8-C
    # withdrawal). `filter` selects the ability-holders, `window` is the
    # optional ActivationWindow the extra activation joins. Executor
    # deferred per the GRANT_ABILITY-adjacent orphan precedent.
    GRANT_ACTIVATION = "GRANT_ACTIVATION"
    # DAMAGE_ASSIGN_POLICY (grammar round 10, R10-4, C28): combat-damage
    # assignment-policy verbs — "You may have this creature assign its
    # combat damage as though it weren't blocked." (Garruk, Savage Herald
    # [−7], granted via GRANT_ABILITY over creatures you control).
    # `scope` is the closed _DAMAGE_ASSIGN_SCOPES vocabulary; `filter`
    # over narrows the affected damage dealers. The "You may" wording is
    # preserved OUTSIDE the atom (C15/C28: the granted StaticAbility
    # holds OptionalEffect(Atom(DAMAGE_ASSIGN_POLICY, ...))). Executor
    # deferred per the MANA_POLICY / ADD_LAND_PLAY orphan precedent.
    DAMAGE_ASSIGN_POLICY = "DAMAGE_ASSIGN_POLICY"
    # TRIGGER_ADDITIONAL (T5-D, Sanctum of All "that ability triggers an
    # additional time"): the {count} axis of the extra-trigger family — the
    # AbilityTriggerEvent firing re-triggers the ability it matched
    # `count` more times. CR 603.2e: those extra triggers are created
    # WITHOUT a triggering event, so they never re-arm an
    # AbilityTriggerEvent (the executor marks and skips them). Shared
    # encoding for the whole pool family (Panharmonicon, a derived
    # self-count carrier): one verb, reusable count Quantity.
    TRIGGER_ADDITIONAL = "TRIGGER_ADDITIONAL"


class VerbClass(Enum):
    """T4 §1: the instance CLASS of a Verb — its payload ROLE, not where a
    decision happens (§9: the {menu}/{count} axes are the shared PICK
    wrapper, so selection never belongs to the verb itself)."""

    OPERATION = "OPERATION"  # the atom IS a decision/observation operation
    POLICY = "POLICY"  # standing legality/timing/replacement constraint
    EFFECT = "EFFECT"  # an immediate state delta


# The CLASS partition of the FULL Verb enum (test_ability_tree asserts it
# covers every member exactly once). Rulings are the spec's, 2026-10-07:
# MANDATE_ATTACK/BLOCK are POLICY (combat-declaration legality — §11: the
# restricting card's own component); CAST/FLIP_COIN/FIGHT/TAP/UNTAP/
# SACRIFICE/DISCARD are EFFECTs whose menus live in the shared PICK/
# designate wrapper; DISCARD/MILL/EXILE keep their EFFECT class as the
# merged MOVE's legacy twins (P1a: unemitted members, same class).
VERB_CLASS: dict[Verb, VerbClass] = {
    # OPERATION (6)
    Verb.CHOOSE: VerbClass.OPERATION,
    Verb.CHOOSE_NAME: VerbClass.OPERATION,
    Verb.SCRY: VerbClass.OPERATION,
    Verb.SEARCH: VerbClass.OPERATION,
    Verb.LOOK_AT: VerbClass.OPERATION,
    Verb.PAY: VerbClass.OPERATION,
    # POLICY (7)
    Verb.MANA_POLICY: VerbClass.POLICY,
    Verb.DAMAGE_ASSIGN_POLICY: VerbClass.POLICY,
    Verb.GRANT_ACTIVATION: VerbClass.POLICY,
    Verb.PREVENT_EFFECT: VerbClass.POLICY,
    Verb.ADD_LAND_PLAY: VerbClass.POLICY,
    Verb.MANDATE_ATTACK: VerbClass.POLICY,
    Verb.MANDATE_BLOCK: VerbClass.POLICY,
    # EFFECT (37)
    Verb.DEAL_DAMAGE: VerbClass.EFFECT,
    Verb.DESTROY: VerbClass.EFFECT,
    Verb.EXILE: VerbClass.EFFECT,
    Verb.DRAW: VerbClass.EFFECT,
    Verb.MILL: VerbClass.EFFECT,
    Verb.GAIN_LIFE: VerbClass.EFFECT,
    Verb.LOSE_LIFE: VerbClass.EFFECT,
    Verb.ADD_MANA: VerbClass.EFFECT,
    Verb.CREATE_TOKEN: VerbClass.EFFECT,
    Verb.PUT_COUNTER: VerbClass.EFFECT,
    Verb.REMOVE_COUNTER: VerbClass.EFFECT,
    Verb.MODIFY_PT: VerbClass.EFFECT,
    Verb.SET_PT: VerbClass.EFFECT,
    Verb.GRANT_ABILITY: VerbClass.EFFECT,
    Verb.GRANT_TYPE: VerbClass.EFFECT,
    Verb.TAP: VerbClass.EFFECT,
    Verb.UNTAP: VerbClass.EFFECT,
    Verb.MOVE_ZONE: VerbClass.EFFECT,
    Verb.SHUFFLE: VerbClass.EFFECT,
    Verb.COUNTER_SPELL: VerbClass.EFFECT,
    Verb.COPY: VerbClass.EFFECT,
    Verb.SACRIFICE: VerbClass.EFFECT,
    Verb.DISCARD: VerbClass.EFFECT,
    Verb.REVEAL: VerbClass.EFFECT,
    Verb.ATTACH: VerbClass.EFFECT,
    Verb.GAIN_CONTROL: VerbClass.EFFECT,
    Verb.PHASE_IN: VerbClass.EFFECT,
    Verb.PHASE_OUT: VerbClass.EFFECT,
    Verb.EXTRA_TURN: VerbClass.EFFECT,
    Verb.END_TURN: VerbClass.EFFECT,
    Verb.LOSE_GAME: VerbClass.EFFECT,
    Verb.FLIP_COIN: VerbClass.EFFECT,
    Verb.CAST: VerbClass.EFFECT,
    Verb.FIGHT: VerbClass.EFFECT,
    Verb.LOSE_ABILITY: VerbClass.EFFECT,
    Verb.GET_EMBLEM: VerbClass.EFFECT,
    # T5-D: extra-trigger creation is an EFFECT — it puts new trigger
    # instances on the stack (CR 603.2e), not a standing policy.
    Verb.TRIGGER_ADDITIONAL: VerbClass.EFFECT,
}


class SelectorMode(Enum):
    """How a selector picks its objects (DESIGN_CARD_POOL: one Selector type
    used by targets, statics, counts, triggers, and search)."""

    # TARGET = exactly `count` objects for a concrete count; with a
    # QAtMost(n) count (grammar round 8, C17) it is the legal designation
    # of "up to n targets": the player chooses 1..n, the effect resolves
    # on 0..remaining (executor clamp).
    TARGET = "TARGET"  # exactly `count` objects, chosen by the effect
    CHOOSE = "CHOOSE"  # up to `count` objects, chosen by a controller
    ALL = "ALL"  # every object in the zone matching the filter (count ignored)
    RANDOM = "RANDOM"  # exactly `count` objects, chosen at random
    # ONE_OF / REST (grammar round 7, the split-selection pair): ONE_OF
    # takes exactly one object out of the selected set (Waker of Waves'
    # "put one of them in your hand", Cultivate's "put it onto the
    # battlefield"); REST is everything left after the ONE_OF pick
    # ("the rest into your graveyard/hand", See the Truth, Garruk's
    # Harbinger, Cultivate) — count is ignored, mirroring ALL.
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
    default) means the zone as a whole; None serializes by omitting the
    key (T3 round, byte-stable for pre-T3 trees)."""

    TOP = "TOP"
    BOTTOM = "BOTTOM"


class ControllerRef(Enum):
    """Whose zone. ANY = every controller's zones combined; in a two-player
    game that is both players, which is how "all graveyards" selectors read.
    OPPONENT is per-opponent in multiplayer (the executor evaluates each)."""

    YOU = "YOU"
    OPPONENT = "OPPONENT"
    TARGET_PLAYER = (
        "TARGET_PLAYER"  # "the target player" — the spell's target, when it is a player
    )
    ANY = "ANY"
    ALL_OPPONENTS = "ALL_OPPONENTS"
    OWNER = "OWNER"  # "its owner" — owner-scoped zones ("return to its owner's hand")


class QPropField(Enum):
    """Which property QProp reads from its referent. The player-count fields
    only make sense with the "controller" referent; AMOUNT, THIS_WAY_COUNT
    and THAT_MANY_COUNT only with "event"; COUNTER_COUNT with "event",
    "source" (grammar round 7: SOUL counters on the source Equipment,
    Malefic Scythe) or "target" (grammar round 8, R8-11: counters on the
    chosen target, Invigorating Surge) — all validated in
    QProp.__post_init__."""

    POWER = "POWER"
    TOUGHNESS = "TOUGHNESS"
    CMC = "CMC"
    MANA_VALUE = "MANA_VALUE"
    CARDS_IN_HAND = "CARDS_IN_HAND"  # "the number of cards in your hand"
    CARDS_IN_LIBRARY = "CARDS_IN_LIBRARY"  # Peer into the Abyss
    CARDS_IN_GRAVEYARD = "CARDS_IN_GRAVEYARD"  # Liliana, Waker of the Dead [-3]
    # r24a (2026-10-02, engine batch 24a; the C3 roadmap correction's engine
    # half): the life-TOTAL operand — "loses half their life. Round up" (Peer
    # into the Abyss). QCount counts zone OBJECTS and no field read a player's
    # life, so that clause had no compilable quantity (C3 STOP verdict). The
    # lane is additive+byte-stable per the R3 law: the frozen compiler emits
    # no LOSE_LIFE(QProp LIFE) tree yet — the emit lands with the compiler
    # batch; the executor already answers it (quantity._prop_value, pinned in
    # test_executor_r24a).
    LIFE = "LIFE"  # "half your life total" (Peer into the Abyss)
    AMOUNT = "AMOUNT"  # the triggering event's damage amount (Brash Taunter)
    COUNTER_COUNT = "COUNTER_COUNT"  # the counter count of the event or the source (Conclave Mentor; grammar round 7: Malefic Scythe's SOUL counters on this Equipment)
    THIS_WAY_COUNT = "THIS_WAY_COUNT"  # "for each creature tapped this way" (Siege Striker) / "for each card exiled this way" (Necromentia s3) — grammar round 7, referent "event"
    THAT_MANY_COUNT = "THAT_MANY_COUNT"  # "discard up to two … draw that many" (Kinetic Augur) — the count chosen by the preceding up-to-X choice; grammar round 7, referent "event"


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
    carries a ``rounding`` policy (T5-D, see Rounding); the historical
    (n + 1) // 2 round-up-half idiom stays valid, but new encodings state
    the policy explicitly (Peer into the Abyss), keeping the operator set
    closed."""

    ADD = "ADD"
    SUB = "SUB"
    MUL = "MUL"
    DIV = "DIV"
    MAX = "MAX"
    MIN = "MIN"


class Rounding(Enum):
    """T5-D (Peer into the Abyss "Round up each time."): the explicit
    rounding POLICY of a QBin DIV — the axis the (n + 1) // 2 idiom had to
    smuggle through arithmetic before. NONE is "the text states no
    rounding" (behaves as FLOOR, the operator's standing default); CEIL is
    the MTG rule rounding (CR 107.1a, always round up); FLOOR is an
    explicit "rounded down" text. The field rides QBin's DIV only —
    attaching it to any other op raises."""

    NONE = "NONE"
    CEIL = "CEIL"
    FLOOR = "FLOOR"


class ThisTurnKind(Enum):
    """What QThisTurn counts within the current turn — turn-scoped
    quantities ("the life you've gained this turn", "the cards an
    opponent has drawn this turn"); the family named in the T3 grammar
    decision (B2a #12/#14/#16, B4 #147/#163)."""

    LIFE_GAINED = "LIFE_GAINED"
    CARDS_DRAWN = "CARDS_DRAWN"
    # NONCOMBAT_DAMAGE (grammar round 8, R8-10): total noncombat damage
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
        "MAY_DONE"  # r18a CR 611.1: the "If you do, X" tail of a MAY sentence —
        # X executes only when the optional action actually executed. Handle-
        # free like FLIP_WON; answered from the 14b decision channel's logged
        # may-offer outcome (asked 'fire' at this ability's site). No slots
        # (precedent: TARGETS_SOURCE); never re-asks.
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
        # (Archfiend's Vessel; grammar round 4 — required zone slot)
    )
    CAST_THIS_TURN_FROM = (
        "CAST_THIS_TURN_FROM"  # "or you cast it from your graveyard"
        # (Archfiend's Vessel; grammar round 4 — required zone + who)
    )
    MOVED_TO_ZONE_THIS_TURN = (
        "MOVED_TO_ZONE_THIS_TURN"  # "a permanent was put into your hand
        # from the battlefield this turn" (Barrin, Tolarian Archmage;
        # grammar round 4 — required from_zone + to_zone + who)
    )
    WAS_CAST_THIS_TURN = (
        "WAS_CAST_THIS_TURN"  # "it was cast this turn (by who)" (Containment
        # Priest; grammar round 5 — required who; turn-scoped cast tracking
        # without a zone constraint, unlike CAST_THIS_TURN_FROM)
    )
    NOT_FIRST_DRAW_THIS_STEP = (
        "NOT_FIRST_DRAW_THIS_STEP"  # "not the first card who draws in their
        # draw step" (Teferi's Ageless Insight; grammar round 5 — required who;
        # evaluated against the drawn card, CardDrawnEvent subject)
    )
    TURN_OF = (
        "TURN_OF"  # "it is <who>'s turn" — "During your turn, …" (Radha,
        # Heart of Keld; Discontinuity; grammar round 6 — required who; the
        # Phase enum carries no turn owner)
    )
    ZONE_COUNT_GE = (
        "ZONE_COUNT_GE"  # "<who> has >= count cards in their <zone>
        # matching inner_filter" (Thieves' Guild Enforcer; grammar round 6
        # — required who + zone + inner_filter + count)
    )
    IS_ATTACHED_TO = (
        "IS_ATTACHED_TO"  # grammar round 7: the object is attached to the
        # referent object ("Destroy target Equipment attached to that" —
        # Turn to Slag; required referent slot from
        # _QPROP_STR_REFERENTS, e.g. "source")
    )
    NAME_CHOSEN = (
        "NAME_CHOSEN"  # grammar round 7: the object's name is the one
        # picked by Verb.CHOOSE_NAME ("cards with that name" — Runed Halo
        # s2, Necromentia s2). No slots (precedent: IS_TAPPED).
    )
    IS_EXILED_WITH_SOURCE = (
        "IS_EXILED_WITH_SOURCE"  # grammar round 8, R8-6: the card is in
        # exile AND was exiled by the source object — "the exiled card"
        # permission scoping (Horizon Scholar's "card exiled with ~",
        # Idol of Endurance). No slots (precedent: IS_TAPPED); evaluated
        # against the ability's source.
    )
    CONTROLLER_COUNT_GT = (
        "CONTROLLER_COUNT_GT"  # grammar round 8, R8-9: the referent
        # controller controls MORE objects matching inner_filter than
        # matching right_inner_filter — Garruk's "you control more
        # creatures than any opponent" split; dual-filter comparison,
        # the second filter lives in the new right_inner_filter slot.
    )
    LIFE_LEAD_OVER_START_GE = (
        "LIFE_LEAD_OVER_START_GE"  # grammar round 9, R9-2: the referent
        # (a player) has gained a net life lead of at least `count` over
        # their starting life total — "if you gained at least 7 life more
        # than your starting life total this game" (Speaker of the Heavens
        # class). The executor reads current-life minus starting-life;
        # the count slot carries the threshold Quantity from the text
        # (the PRED carries slots only — the number is template-side).
    )
    NAME_PARTITION_COUNT_GE = (
        "NAME_PARTITION_COUNT_GE"  # grammar round 10, R10-2, C26: the
        # maximum size of an EXACT-name group over the inner_filter-
        # matched objects the referent controls is >= `count` — "if you
        # control two or more nonland, nontoken permanents with the same
        # name as one another" (Chrome Anchor's Replicator gate). The
        # executor groups the matched objects by exact name and takes
        # the largest group; the PRED carries slots only (inner_filter,
        # count) — the threshold number is template-side.
    )
    ATTACK_AGAINST_COUNT_GE = (
        "ATTACK_AGAINST_COUNT_GE"  # grammar round 10, R10-3: count the
        # triggering event's subject attackers whose ATTACKED object
        # passes inner_filter >= `count` — "if two or more of those
        # creatures are attacking you and/or planeswalkers you control"
        # (Mangara, the Diplomat). Reads the declared-attackers list off
        # the DeclareAttackersEvent (LIFE_LEAD vocabulary-first
        # precedent: the executor reads the game record).
    )
    OPPONENT_OF = (
        "OPPONENT_OF"  # grammar round 11, R11-1 (batch 6 destination
        # ruling /10): the subject IS a PLAYER who is an opponent of
        # ``who`` — the damage-DESTINATION test "…deals damage TO AN
        # OPPONENT" (Chandra's Pyreling / Incinerator). A destination
        # PREDICATE in the existing event-filter idiom: the
        # DamageDealtEvent ``filter`` is already the lane over the
        # damaged object, so no new event field is needed. A card/
        # permanent subject is honestly FALSE (a permanent is not a
        # player, CR 109.5) — the pyreling suspect's negative: damage
        # to an opponent's CREATURE must not satisfy "to an opponent".
        # ``who`` is a ControllerRef or referent Selector (CONTROLLER_IS
        # precedent); the two-player harness answers "the seats that are
        # not who's side are its opponents" (controller_matches mirror).
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


class Keyword(Enum):
    """The pool's keyword abilities — 23 distinct keywords.

    The M21 file carries 24 distinct keyword *strings*; "Hexproof from" is
    HEXPROOF plus a Filter param on the KeywordAbility (Spine
    Megalodon/Sporeweb Weaver), not a separate keyword. File-level counts
    (NUMBERS.md): Flying 28, Scry 19, Vigilance 12, Lifelink 12, Flash 11,
    Enchant 11, Trample 9, Prowess 8, Reach 8, Hexproof 7 (+4 from),
    Protection 6, Mill 5, Defender 4, Haste 4, Fight 4, Deathtouch 3,
    First strike 2, Equip 2, Indestructible 2, Treasure 2, Battalion 1,
    Double strike 1, Menace 1.
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
    END_TURN: "at the beginning of your end step" (Gadrak, Griffin Aerie,
    Garruk's Unleashed emblem). COMBAT: "at the beginning of combat on your
    turn" (the three emblems).
    """

    UPKEEP = "UPKEEP"
    FIRST_MAIN = "FIRST_MAIN"
    END_TURN = "END_TURN"
    COMBAT = "COMBAT"


class Step(Enum):
    """StepEvent sub-steps (finer than Phase). The pool has no step-level
    triggers today; the members are the standard combat steps the executor
    will eventually emit. UNTAP (grammar round 9, R9-4) is not a trigger
    step but a DURATION scope: Frost Breath's "can't untap during their
    controller's next untap step" (see DurationUntilNextStep)."""

    DECLARE_ATTACKERS = "DECLARE_ATTACKERS"
    DEALS_COMBAT_DAMAGE = "DEALS_COMBAT_DAMAGE"
    END_OF_COMBAT = "END_OF_COMBAT"
    UNTAP = "UNTAP"  # the untap step (grammar round 9, R9-4, Frost Breath)


class ActivationWindow(Enum):
    """When an activated ability may be activated (grammar round 9, R9-1,
    convention C20). None on ActivatedAbility = the default window (play
    the activation any time you could cast an instant); SORCERY = only
    during the controller's own main phase with the stack empty
    ("Activate only as a sorcery" — Steward class). The timing slot lives
    ONLY on ActivatedAbility (C20)."""

    SORCERY = "SORCERY"
    INSTANT = "INSTANT"


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
class QDistinctColorCount:
    """The number of DISTINCT colors among the objects a selector matches
    (grammar round 9, R9-6) — Orrery's "{5},{T}: Draw a card for each
    color among permanents you control" (selector = ALL permanents, the
    count collapses the set to its color-colorimeter). QAgg has no
    distinct-count aggregation (verified round 9), so this is its own
    Quantity node; it is the count, the selector names the population it
    is counted over (QCount's registration shape mirrored exactly)."""

    selector: Selector

    def __post_init__(self) -> None:
        if not isinstance(self.selector, Selector):
            raise ValueError(
                f"QDistinctColorCount: selector must be a Selector, got {type(self.selector).__name__}"
            )


# The closed anaphora referent vocabulary (C12: structured strings, never
# English substrings). "result" (grammar round 7, R7-1): the object(s) the
# previous sentence acted on — revealed / chosen / exiled / moved; the
# anaphoric "it / them / that card" binding resolved by the compiler's
# per-ability result register (C12: register is compiler state, not tree).
_QPROP_STR_REFERENTS = ("source", "controller", "target", "event", "result")


@dataclass(frozen=True)
class QProp:
    """A property of a referent.

    referent = Selector | "source" | "controller" | "target" | "event"
    | "result" (the design's three referents plus the documented "event"
    and the round-7 "result"). field is
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
            # r24a: the life total is the same PLAYER property (same twin
            # convention, same controller-only referent rule).
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
        # COUNTER_COUNT (grammar round 7, R9b): the event's counter count
        # (Conclave Mentor) OR the source permanent's counter count
        # (Malefic Scythe's "for each soul counter on this Equipment");
        # widened to "target" in grammar round 8 (R8-11): "double that
        # many counters" on a chosen counter-holder (Invigorating Surge).
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

    T5-D: DIV carries an optional ``rounding`` policy (see Rounding); the
    field is empty-default and omitted from the serialization, so every
    pre-T5-D QBin keeps its exact golden bytes."""

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
    cards an opponent has drawn this turn" (T3 round E)."""

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
    amount must reach ("choose one or more", Sublime Epiphany). The
    compiler previously had to write ``QUnbounded()`` for these, losing the
    minimum-1 constraint; QAtLeast(1) restores it. n = 0 is redundant with
    the unbounded reading, so 0 and negatives are rejected."""

    n: int

    def __post_init__(self) -> None:
        if isinstance(self.n, bool) or not isinstance(self.n, int):
            raise ValueError(f"QAtLeast: n must be an int, got {self.n!r}")
        if self.n < 1:
            raise ValueError(f"QAtLeast: n must be >= 1, got {self.n}")


@dataclass(frozen=True)
class QAtMost:
    """A quantity meaning "up to n" (n >= 1) — grammar round 8, R8-1,
    convention C17 (KNOWLEDGE 2026-09-28/08). With a TARGET-mode Selector
    this is the legal designation of "up to n targets": the player may
    choose 1..n legal targets (it is still targeted — the legal-target
    distribution C15 protects is preserved), and the effect resolves on
    0..n of them (the executor clamps when targets leave). A resolution-
    time "up to N" that is NOT targeted ("fights up to one target…",
    "exile up to two cards this way") STAYS CHOOSE + QConst(N) per C17 —
    QAtMost is only for the targeted designation. n = 0 is a no-op, so 0
    and negatives are rejected (QAtLeast's validation style)."""

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
    | QProp
    | QBin
    | QThisTurn
    | QAtLeast
    | QAtMost
)


def count_semantics(count: Quantity, n_legal: int) -> tuple[bool, int]:
    """THE legality/count answer for one Quantity over a live population
    (T3 unification, doc 36; owner §9: the {menu} axis gets ONE answer).

    Returns ``(announceable, effective_k)`` where ANNOUNCEABILITY is the
    full-size law of CR 601.2c — "the number of targets must be exactly
    the number stated" — and ``effective_k`` is the ask/designate ceiling
    the executor loop runs against. The three former sites (binding.py
    TARGET, selectors.py ONE_OF, query.py feasibility) all call THIS; a
    site may layer its documented resolve-time lane on top (mid-loop
    depletion resolves as much as possible, 608.2c) but may not re-decide
    the announce-time answer:

    * QConst(N)   — "N targets" EXACT: unannounceable with fewer than N
      legal objects. Clamping (asking over fewer) is WRONG here. k = N,
      never clamped.
    * QAtMost(N)  — "up to N": clamps against the population with the
      NONE stoppable lane; announceable iff at least one legal object
      exists (C17 designation law: a nonempty TARGET slot must designate
      >= 1; an empty population designates nothing and resolves doing
      nothing, 603.4). k = min(N, n_legal).
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
    the zone as a whole and serializes by omitting the key (T3 round H,
    byte-stable for pre-T3 trees)."""

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
    and search (DESIGN_CARD_POOL). count semantics by mode: TARGET exact
    (or 1..n designation / 0..remaining resolution with QAtMost, C17),
    CHOOSE up-to (QUnbounded = any), ALL ignores count, RANDOM exact.
    ``zones`` additively widens the effective zone set to {zone} ∪ zones
    (T3 round C): "target player or planeswalker" = PLAYER ∪ BATTLEFIELD,
    "library and graveyard" search = LIBRARY ∪ GRAVEYARD, "target spell
    or creature" = STACK ∪ BATTLEFIELD. Empty (the default) serializes
    by omitting the key — byte-stable for every pre-T3 tree.

    ``referent`` (grammar round 4, object anaphora) binds the selector to
    an object already in scope instead of searching: one of
    ``_QPROP_STR_REFERENTS`` — "source", "controller", "target", "event",
    "result" (grammar round 7: the object(s) the previous sentence acted
    on) — the closed vocabulary shared with ``QProp``; "event" = the triggering
    event's subject object (cast → the cast spell; damage_dealt → the
    damaged recipient; becomes_blocked → the blocker; declare_attackers
    → the attacker; targeting → the new target). When set, the selector
    denotes the bound object and ``filter`` (if non-universal) acts as a
    type-check on it, not a fresh search. Convention C2: a referent
    selector must be ``mode=CHOOSE`` + ``count=QConst(1)`` + the neutral
    zone ``Zone(ANY, ANY)`` + ``zones=()`` (a bound object is not chosen,
    and its zone is unknown at compile time); violations raise in
    ``__post_init__``. None (the default) serializes by omitting the key
    — byte-stable for every pre-round-4 tree."""

    count: Quantity
    mode: SelectorMode
    filter: Filter
    zone: Zone
    zones: tuple[Zone, ...] = ()
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
        if not isinstance(self.zone, Zone):
            raise ValueError(
                f"Selector: zone must be a Zone, got {type(self.zone).__name__}"
            )
        if not isinstance(self.zones, tuple) or not all(
            isinstance(z, Zone) for z in self.zones
        ):
            raise ValueError("Selector: zones must be a tuple of Zone")
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
            if not (
                self.zone.kind is ZoneKind.ANY
                and self.zone.controller is ControllerRef.ANY
                and self.zone.position is None
            ):
                raise ValueError(
                    f"Selector: referent convention C2 requires the neutral zone, got {self.zone!r}"
                )
            if self.zones:
                raise ValueError(
                    f"Selector: referent convention C2 requires empty zones, got {self.zones!r}"
                )


# ---- Filters ----


@dataclass(frozen=True)
class FAnd:
    """Conjunction. ``FAnd(())`` is the universal filter ("any card")."""

    children: tuple[Filter, ...]

    def __post_init__(self) -> None:
        for child in self.children:
            if not _is_filter(child):
                raise ValueError(
                    f"FAnd: child must be a Filter, got {type(child).__name__}"
                )


@dataclass(frozen=True)
class FOr:
    """Disjunction. ``FOr(())`` is the empty filter (matches nothing)."""

    children: tuple[Filter, ...]

    def __post_init__(self) -> None:
        for child in self.children:
            if not _is_filter(child):
                raise ValueError(
                    f"FOr: child must be a Filter, got {type(child).__name__}"
                )


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
                      NAME_PARTITION_COUNT_GE, ATTACK_AGAINST_COUNT_GE
                      — grammar round 10);
                      a dynamic threshold (QProp/QBin/QCount) is as legal
                      as a literal
      counter_kind — CounterKind (HAS_COUNTER)
      keyword      — Keyword (KEYWORD_HAS)
       who          — ControllerRef | Selector (CONTROLLER_IS;
                        LIFE_GAINED_THIS_TURN_GE, CARDS_DRAWN_THIS_TURN_GE,
                        INSTANT_OR_SORCERY_CAST_THIS_TURN,
                        CAST_THIS_TURN_FROM, MOVED_TO_ZONE_THIS_TURN,
                        WAS_CAST_THIS_TURN, NOT_FIRST_DRAW_THIS_STEP —
                        grammar round 5;
                        you|opponent|target-player, or a referent Selector —
                        grammar round 4, object anaphora)
       inner_filter — a nested Filter (CONTROLLER_COUNT_GE/LE,
                      NAME_PARTITION_COUNT_GE, ATTACK_AGAINST_COUNT_GE —
                      grammar round 10)
       zone         — Zone (ENTERED_THIS_TURN_FROM / CAST_THIS_TURN_FROM —
                       "entered from / cast from this zone this turn")
       from_zone,   — Zones (MOVED_TO_ZONE_THIS_TURN — "a permanent was
       to_zone        put into your hand from the battlefield this turn")
       referent     — a referent string from _QPROP_STR_REFERENTS
                      (IS_ATTACHED_TO — grammar round 7: "attached to
                      that/source"; same vocabulary as Selector.referent;
                      omitted when None — byte-stable for pre-round-7
                      trees, per the R4-4 zone-slot precedent)
       right_inner_filter — a SECOND nested Filter (CONTROLLER_COUNT_GT —
                      grammar round 8, R8-9: dual-filter comparison
                      "controls more X than Y"); omitted when None —
                      byte-stable for pre-round-8 trees
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
    # right_inner_filter (grammar round 8, R8-9): the SECOND filter of a
    # dual-filter comparison (CONTROLLER_COUNT_GT — "controls more
    # creatures than you": inner_filter counts one side,
    # right_inner_filter the other). Omit-when-None, byte-stable for
    # pre-round-8 trees (the R4-4/R7-1 slot precedent).
    right_inner_filter: Filter | None = None

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
        if (
            self.pred is FAtomPred.CONTROLLER_IS
            and self.who
            not in (
                ControllerRef.YOU,
                ControllerRef.OPPONENT,
                ControllerRef.TARGET_PLAYER,
            )
            and not (isinstance(self.who, Selector) and self.who.referent is not None)
        ):
            raise ValueError(
                "FAtom: CONTROLLER_IS who must be you, opponent, the target "
                "player, or a referent Selector (grammar round 4)"
            )
        if self.pred is FAtomPred.OPPONENT_OF and not (
            isinstance(self.who, ControllerRef)
            or (isinstance(self.who, Selector) and self.who.referent is not None)
        ):
            raise ValueError(
                "FAtom: OPPONENT_OF who must be a ControllerRef or a referent "
                "Selector (grammar round 11, CONTROLLER_IS precedent)"
            )


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
    an owner (grammar round 9, R9-4, closing the round-6 item-3 note).
    Frost Breath's "Those creatures can't untap during their controller's
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
    Cabinet's "until this creature leaves the battlefield", Idol of
    Endurance's exile window). ``source`` names the anchored object as a
    referent string from ``_QPROP_STR_REFERENTS`` — default "source" =
    the object that owns the ability (C12: structured referent, never an
    English substring like "this creature")."""

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


# ---------------------------------------------------------------------------
# EventSpec — structured, NEVER a substring (PITFALLS: the ETB-substring bug
# killed forty triggers). Each event's filter selects the event's SUBJECT —
# the object the event is about: the spell cast, the creature that dealt
# damage / died / became blocked, the entering permanent, the damaged
# object, the targeted object.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneChangeEvent:
    """A permanent changed zones. ETB = from anywhere to the battlefield —
    a ZoneChange, never a substring. ``subject`` (T3 round F) narrows
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
    T3 round F optional scoping: ``controller`` = whose cast (None = any
    — "an opponent casts"), ``from_zone`` = the source zone (None = any),
    ``ordinal`` = the Nth cast by that controller this turn (None = every
    cast; 2 = "your second spell each turn"). Grammar round 4 adds
    ``from_zone_not`` = exclusion: the cast came from anywhere OTHER than
    this zone ("from anywhere other than their hand" — Ghostly Pilferer;
    mutually exclusive with ``from_zone``)."""

    filter: Filter
    controller: ControllerRef | None = None
    from_zone: Zone | None = None
    ordinal: int | None = None
    from_zone_not: Zone | None = None

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"CastSpellEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )
        if self.controller is not None and not isinstance(
            self.controller, ControllerRef
        ):
            raise ValueError(
                "CastSpellEvent: controller must be a ControllerRef, got "
                f"{type(self.controller).__name__}"
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
    ``attacked`` (grammar round 10, R10-3) narrows the ATTACKED-side
    object per attacker — Mangara's "two or more of those creatures are
    attacking you and/or planeswalkers you control"; omitted from the
    tagged dict when None, so pre-round-10 trees keep byte-identical
    canonical JSON."""

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
    ``subject`` (r3b) narrows WHICH declaration fires: None = any blocker,
    or a Filter over the blocking creature — mirroring
    ``ZoneChangeEvent.subject``; omitted from the tagged dict when None,
    so pre-r3b trees keep byte-identical canonical JSON.
    ``blocked`` (grammar round 6, R6-4) narrows the BLOCKED-side creature
    — "can't be blocked" / "can block only creatures with flying"
    restrict the blocked participant (Tome Anima, Ghostly Pilferer,
    Subira, Shacklegeist); omitted from the tagged dict when None, so
    pre-round-6 trees keep byte-identical canonical JSON."""

    filter: Filter
    subject: Filter | None = None
    blocked: Filter | None = None

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


@dataclass(frozen=True)
class CombatDamageEvent:
    """Combat damage was dealt (filter over the damage-dealing creature —
    Garruk's Harbinger, Jeskai Elder)."""

    filter: Filter

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"CombatDamageEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )


@dataclass(frozen=True)
class CounterPlacedEvent:
    """Counters of a kind were placed on the subject.

    `count` (grammar round 5, R5-2) names the number placed ("one or more"
    = QAtLeast(1); "that many" = QProp("event", COUNTER_COUNT)); omitted
    when None (byte-stable)."""

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
    """T5-D (Sanctum of All "whenever another Shrine you control's
    ability triggers"): an ability TRIGGERED — the {when-event} atom of
    the §9 decomposition, with the same {subject filter} axis as every
    other event class, evaluated over the TRIGGERING ability's source
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
    """A turn phase began for `controller` (see Phase for pool citations)."""

    phase: Phase
    controller: ControllerRef

    def __post_init__(self) -> None:
        if not isinstance(self.phase, Phase):
            raise ValueError(
                f"TurnPhaseEvent: phase must be a Phase, got {self.phase!r}"
            )
        if not isinstance(self.controller, ControllerRef):
            raise ValueError(f"TurnPhaseEvent: controller must be a ControllerRef")


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
            raise ValueError(f"StepEvent: controller must be a ControllerRef")


@dataclass(frozen=True)
class DamageDealtEvent:
    """Damage was dealt to the subject (filter over the damaged object —
    Brash Taunter's "whenever this creature is dealt damage"). `amount`
    rides the event for QProp("event", AMOUNT). T3 round F optional
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
    preventions attach to)."""

    filter: Filter

    def __post_init__(self) -> None:
        if not _is_filter(self.filter):
            raise ValueError(
                f"TargetingEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )


@dataclass(frozen=True)
class CardDrawnEvent:
    """A card was drawn by `controller` (T3 round F: "whenever you draw a
    card", "whenever an opponent draws a card"). The drawn card is the
    event subject — a TriggeredAbility `condition` Filter narrows it.
    ``ordinal`` (grammar round 4) = the Nth card drawn by that controller
    this turn (None = every draw) — "whenever you draw your second card
    each turn" (Jolrael, Mwonvuli Recluse; Mystic Skyfish). Mirrors
    CastSpellEvent.ordinal."""

    controller: ControllerRef
    ordinal: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.controller, ControllerRef):
            raise ValueError(
                f"CardDrawnEvent: controller must be a ControllerRef, got {type(self.controller).__name__}"
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
    """`controller` gained life (T3 round F: "whenever you gain life,
    target opponent loses that much life")."""

    controller: ControllerRef

    def __post_init__(self) -> None:
        if not isinstance(self.controller, ControllerRef):
            raise ValueError(
                f"LifeGainedEvent: controller must be a ControllerRef, got {type(self.controller).__name__}"
            )


@dataclass(frozen=True)
class SacrificeEvent:
    """`controller` sacrificed a permanent (T3 round F: "whenever you
    sacrifice a permanent"). The sacrificed permanent is the event
    subject — a TriggeredAbility `condition` Filter narrows it (e.g. a
    creature filter)."""

    controller: ControllerRef

    def __post_init__(self) -> None:
        if not isinstance(self.controller, ControllerRef):
            raise ValueError(
                f"SacrificeEvent: controller must be a ControllerRef, got {type(self.controller).__name__}"
            )


@dataclass(frozen=True)
class LoyaltyActivatedEvent:
    """`controller` activated a loyalty ability on a planeswalker (grammar
    round 4: Keral Keep Disciples' "whenever you activate a loyalty ability
    of a Chandra planeswalker"). ``filter`` selects the planeswalker whose
    loyalty ability was activated (e.g. subtype Chandra + type Planeswalker);
    it is required — a bare "any loyalty ability" trigger is never expressible.
    Convention C5: loyalty triggers compile as the EFFECT of the
    ActivatedAbility whose cost is the loyalty part, not as a standalone
    TriggeredAbility, so this event tags that activation."""

    controller: ControllerRef
    filter: Filter

    def __post_init__(self) -> None:
        if not isinstance(self.controller, ControllerRef):
            raise ValueError(  # noqa: TRY004 — module convention, tests pin ValueError
                f"LoyaltyActivatedEvent: controller must be a ControllerRef, got {type(self.controller).__name__}"
            )
        if not _is_filter(self.filter):
            raise ValueError(
                f"LoyaltyActivatedEvent: filter must be a Filter, got {type(self.filter).__name__}"
            )


EventSpec = (
    ZoneChangeEvent
    | CastSpellEvent
    | DeclareAttackersEvent
    | DeclareBlockersEvent
    | CombatDamageEvent
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
    | SacrificeEvent
    | LoyaltyActivatedEvent
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
    # color / enters_tapped / enters_attacking (grammar round 8, R8-2/R8-4):
    # token color words ("Treasure" artifact tokens are colourless, a Basri
    # Ket soldier is white), "put those tokens onto the battlefield tapped"
    # and "…that's attacking" (Basri Ket [-2]). All three default to None —
    # absent (unknown/unstated) — and serialize by OMITTING the key, so
    # every pre-round-8 token golden stays byte-identical (dual
    # registration: _SPECS opt-tags + _OMIT_IF_EMPTY row).
    color: str | None = None
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
        if self.color is not None and (
            not isinstance(self.color, str) or not self.color.strip()
        ):
            raise ValueError(
                f"TokenSpec: color must be a non-empty str, got {self.color!r}"
            )
        for flag in ("enters_tapped", "enters_attacking"):
            value = getattr(self, flag)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"TokenSpec: {flag} must be a bool, got {value!r}")


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
    either colour. Kept pool-agnostic: M21 has none, later sets do."""

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

    ``delta`` is a literal int or a Quantity (T3 round 2, item 6: Ugin's
    "[−X]" — a DYNAMIC loyalty cost); a dynamic delta is still always a
    reduction (loyalty is never gained as a cost)."""

    delta: int | Quantity

    def __post_init__(self) -> None:
        if isinstance(self.delta, bool):
            raise ValueError(
                f"CostLoyalty: delta must be an int or Quantity, got {self.delta!r}"
            )
        if isinstance(self.delta, int):
            if self.delta == 0:
                raise ValueError("CostLoyalty: delta must be non-zero")
        elif _is_quantity(self.delta):
            if isinstance(self.delta, QConst) and self.delta.value == 0:
                raise ValueError("CostLoyalty: delta must be non-zero")
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
    """An ability's cost. Empty parts = a free activation (legal MTG)."""

    parts: tuple[CostPart, ...] = ()

    def __post_init__(self) -> None:
        for part in self.parts:
            if not _is_cost_part(part):
                raise ValueError(
                    f"Cost: part must be a CostPart, got {type(part).__name__}"
                )


# Cost deltas — the signed cost changes a CostModifier applies (T3 round
# K: "cost {2} less to cast", "cost an additional 2 life to cast", "cost
# {2}{U} less", "cast without paying its mana cost"). `amount` is a
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

# _SCOPE_VOCAB_BY_VERB (grammar round 10, R10-4): the per-verb "scope"
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
            # "ANY" (grammar round 8, R8-3): "mana of any one color" — a
            # choice among WUBRG at resolution; distinct from "C"
            # (colourless). The C-3 collapse repair; templates flip in 8-B.
            if role == "color" and value not in (*_COLORS, _COLORLESS, _ANY_COLOR):
                raise ValueError(
                    f"AtomArgs: role 'color' must be one of WUBRG/C/ANY, got {value!r}"
                )
            # scope (grammar round 9, R9-3, C21; widened round 10, R10-4):
            # the closed per-verb scope vocabularies (MANA_POLICY's
            # spend-restriction pair, DAMAGE_ASSIGN_POLICY's damage-
            # assignment pair); same vocab-check precedent as the "color"
            # role above. AtomArgs is verb-blind, so it validates against
            # the UNION here; the enclosing Atom enforces the verb's own
            # vocabulary (_SCOPE_VOCAB_BY_VERB).
            if role == "scope" and value not in (
                *_MANA_POLICY_SCOPES,
                *_DAMAGE_ASSIGN_SCOPES,
            ):
                raise ValueError(
                    f"AtomArgs: role 'scope' must be one of "
                    f"{(*_MANA_POLICY_SCOPES, *_DAMAGE_ASSIGN_SCOPES)}, "
                    f"got {value!r}"
                )
            # T4 P1a: the merged MOVE's closed string slots — single-verb
            # vocabularies, so the AtomArgs-level union check is already
            # exact (no _SCOPE_VOCAB_BY_VERB twin needed).
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
        # P1a review follow-up (fresh-eyes MINOR): the mill lane is defined by
        # TOP-pop; a journal_kind="MILL" site that forgets pop_order would
        # silently fall through to the generic MOVE lane (wrong bookkeeping).
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
        # T4 P1a: the merged MOVE carries its objects on exactly one of
        # the three predecessor axes — an atom with none would be a
        # move of nothing (grammar round 6's at-least-one precedent).
        if self.verb is Verb.MOVE_ZONE and not roles.keys() & {
            "cards",
            "target",
            "amount",
        }:
            raise ValueError(
                f"Atom: {self.verb.name} needs one of the cards/target/"
                "amount object axes"
            )
        # R10-4: per-verb scope vocabulary (AtomArgs validates the union
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
    """Apply `effect` once per player denoted by `ref` (T3 round I:
    "each opponent creates a token / sacrifices a creature" — per-opponent
    effects are a named cross-set mechanic). `ref` = the player set:
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


@dataclass(frozen=True)
class DelayedTrigger:
    """A trigger created *inside* another effect, live only for `duration`
    (grammar round 9, R9-5, C22). Subira Toralf's "When a creature you
    control enters this turn, ..." is an Atom effect that registers this
    node; the node itself is never a standalone Ability — the duration is
    REQUIRED because a delayed trigger without a lifetime window is just a
    TriggeredAbility. `condition` optionally gates the fired event, same
    convention as TriggeredAbility.condition."""

    duration: Duration
    event: EventSpec
    condition: Filter | None
    effect: Effect

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
    creature gets +1/+1 for each soul counter). `condition` (T3 round 4,
    2026-09-24) optionally scopes WHEN the continuous effect applies ("As
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
    `effect` happens. `condition` is a Filter over the event's subject."""

    event: EventSpec
    condition: Filter | None
    effect: Effect

    def __post_init__(self) -> None:
        if not _is_event(self.event):
            raise ValueError(
                f"TriggeredAbility: event must be an EventSpec, got {type(self.event).__name__}"
            )
        if self.condition is not None and not _is_filter(self.condition):
            raise ValueError(
                f"TriggeredAbility: condition must be a Filter, got {type(self.condition).__name__}"
            )
        if not _is_effect(self.effect):
            raise ValueError(
                f"TriggeredAbility: effect must be an Effect, got {type(self.effect).__name__}"
            )


@dataclass(frozen=True)
class ActivatedAbility:
    """Cost: Effect — mana abilities, loyalty abilities, and Mazemind
    Tome's "{T}, put a page counter on this artifact: Scry 1". `condition`
    (T3 round 4, 2026-09-24) optionally gates activation ("Activate only
    if a creature died this turn"); None = unconditional — same convention
    as StaticAbility.condition (state predicate, no event subject).
    `timing` (grammar round 9, R9-1, C20) optionally pins WHEN the ability
    may be activated (ActivationWindow.SORCERY for "Activate only as a
    sorcery"); None = default instant speed — the existing default, so no
    pre-round-9 tree needs the key."""

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

    ``additional_costs`` (T3 round 2, item 3) carries the "As an additional
    cost to cast this spell, ..." costs ON TOP of the printed cost (sacrifice
    a creature, discard a card, ...) — the printed cost itself still lives on
    CardRecord.

    ``effect`` (T3 round 3) is optional: a creature can be castable with
    additional costs and no resolvable effect sentence of its own (Goremand,
    Sparkhunter Masticore). The compiler then builds an effect-less
    SpellAbility (``effect=None``) purely to carry the additional costs.
    ``None`` serializes by omitting the ``"effect"`` key, so every
    pre-round-3 tree (all of which carry an effect) stays byte-identical."""

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
    """A continuous cost-altering effect (T3 round K: "creature spells
    with flying you cast cost {2} less to cast", "cost an additional 2
    life to cast", "cost {2}{U} less", "without paying its mana cost").

    Structural choice (per the T3 decision doc's option 2): a SIBLING
    Ability node, not a StaticAbility payload — a cost modifier is not an
    executable Effect step (StaticAbility wraps an Effect: things that
    HAPPEN), it declares its own payload exactly like StaticAbility
    declares `effect`. `filter` selects the affected spells/permanents,
    `controller_ref` scopes whose, `delta` is the signed cost change.
    `condition` (T3 round 2, item 2) optionally narrows WHEN the modifier
    applies ("This spell costs {2} less to cast if you've gained 2 or more
    life this turn"); None = unconditional. `extra_deltas` (T3 round 4,
    2026-09-24) carries further cost deltas beyond the single `delta` slot
    (Stormwing Entity's {2}{U} = generic 2 + 1 blue); empty = single delta
    only — the additive-slot pattern of Selector.zone/Selector.zones.
    `controller_ref` widened (grammar round 5, R5-3) to
    ``ControllerRef | Selector``: convention C7 — a Selector means the
    controller of the selected object, and the modifier applies to costs
    that controller pays FOR the filtered object (Lofty Denial: the {1} of
    s1 becomes {4} under the condition, including `unless` payments)."""

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


@dataclass(frozen=True)
class EtBState:
    """The entered state of a permanent: `tapped` ("this creature enters
    tapped") and/or `initial_counters` ("enters with 3 +1/+1 counters",
    "this Equipment enters with a soul counter") — T3 round J, among the
    most common ETB states. An Ability node on the card record. Each
    counter entry is a (CounterKind, Quantity) pair. A no-op state
    (untapped, no counters) is rejected — a no-op is not a node in the
    tree (Seq's rule)."""

    tapped: bool = False
    initial_counters: tuple[tuple[CounterKind, Quantity], ...] = ()

    def __post_init__(self) -> None:
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


@dataclass(frozen=True)
class EmblemAbility:
    """An emblem's embedded ability — emblems carry triggered/static
    abilities of their own (T3 round L: Basri Ket / Garruk / Liliana
    emblems; "the emblem's -1: each opponent creates a token")."""

    embedded: Ability

    def __post_init__(self) -> None:
        if not _is_ability(self.embedded):
            raise ValueError(
                f"EmblemAbility: embedded must be an Ability, got {type(self.embedded).__name__}"
            )


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
)


# ---- CardRecord — the root node ----


@dataclass(frozen=True)
class CardRecord:
    """The root node: one card (or token) as a typed ability tree.

    Fields are the structured ingest of DESIGN_CARD_POOL step 1 plus the
    compiled abilities. P/T are Optional[Quantity]: a creature with
    dynamic P/T (Tarmogoyf-class, the Weird token) carries None plus a
    SET_PT ability; a non-creature can never carry P/T. `loyalty` is the
    starting loyalty (an ability, not P/T — NUMBERS.md). `emblem` embeds
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


# ---------------------------------------------------------------------------
# Validation tables + type guards.
# Referenced from __post_init__ methods above; resolved at call time, so
# they live after the classes they validate.
# ---------------------------------------------------------------------------

# QAtMost (grammar round 8, R8-1) joins the Quantity guards so Selector
# .count and Quantity-valued slots/roles accept it via _is_quantity.
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
)
_EV_CLASSES = (
    ZoneChangeEvent,
    CastSpellEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    CombatDamageEvent,
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
    SacrificeEvent,
    LoyaltyActivatedEvent,
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


def _is_duration(value: object) -> bool:  # noqa: F841 — part of the closed guard set
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
    # FLIP_WON: the flippers side — "if you win the flip" (required who).
    # "If you LOSE the flip" is FNot(FAtom(FLIP_WON, who=YOU)), never a
    # separate predicate (PITFALLS: no duplicate predicates).
    FAtomPred.FLIP_WON: (frozenset({"who"}), frozenset({"who"})),
    # INSTANT_OR_SORCERY_CAST_THIS_TURN: turn-scoped cast tracking — "if
    # you've cast an instant or sorcery spell this turn" (required who;
    # Stormwing Entity). Precedent: LIFE_GAINED_THIS_TURN_GE.
    FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN: (
        frozenset({"who"}),
        frozenset({"who"}),
    ),
    # TARGETS_SOURCE: "spells your opponents cast that target this creature"
    # — the spell targets the source object. No slots (precedent: IS_SOURCE).
    FAtomPred.TARGETS_SOURCE: (frozenset(), frozenset()),
    # MAY_DONE (r18a, CR 611.1): the "If you do, X" tail of a MAY sentence.
    # Handle-free like FLIP_WON; the executor answers it from the 14b
    # decision channel's logged may-offer outcome. No slots.
    FAtomPred.MAY_DONE: (frozenset(), frozenset()),
    # ENTERED_THIS_TURN_FROM: "if it entered from your graveyard this turn"
    # (Archfiend's Vessel). The zone slot names the source zone of the
    # entry. Precedent: the zone slots on CastSpellEvent.from_zone.
    FAtomPred.ENTERED_THIS_TURN_FROM: (
        frozenset({"zone"}),
        frozenset({"zone"}),
    ),
    # CAST_THIS_TURN_FROM: "or you cast it from your graveyard this turn"
    # (Archfiend's Vessel). zone = the cast's source zone; who = the
    # controller who cast it (a referent Selector is legal — round 4).
    FAtomPred.CAST_THIS_TURN_FROM: (
        frozenset({"zone", "who"}),
        frozenset({"zone", "who"}),
    ),
    # MOVED_TO_ZONE_THIS_TURN: "if a permanent was put into your hand from
    # the battlefield this turn" (Barrin, Tolarian Archmage). from_zone /
    # to_zone name the two zones; who = the controller the move was
    # relative to (a referent Selector is legal — round 4).
    FAtomPred.MOVED_TO_ZONE_THIS_TURN: (
        frozenset({"from_zone", "to_zone", "who"}),
        frozenset({"from_zone", "to_zone", "who"}),
    ),
    # WAS_CAST_THIS_TURN (grammar round 5, R5-1): "[the object] was cast this
    # turn (by who)" — Containment Priest. who = the controller who cast it
    # (a referent Selector is legal — round 4); no zone slot (the predicate is
    # zone-agnostic, unlike CAST_THIS_TURN_FROM).
    FAtomPred.WAS_CAST_THIS_TURN: (
        frozenset({"who"}),
        frozenset({"who"}),
    ),
    # NOT_FIRST_DRAW_THIS_STEP (grammar round 5, R5-4): "not the first card
    # who draws in their draw step" — Teferi's Ageless Insight. who = the
    # player drawing (a referent Selector is legal — round 4); evaluated
    # against the drawn card (the CardDrawnEvent subject).
    FAtomPred.NOT_FIRST_DRAW_THIS_STEP: (
        frozenset({"who"}),
        frozenset({"who"}),
    ),
    # TURN_OF (grammar round 6, R6-1): "it is <who>'s turn" — "During your
    # turn, …" (Radha, Heart of Keld; Discontinuity). who = the turn owner
    # (ControllerRef or referent Selector — precedent CONTROLLER_IS).
    FAtomPred.TURN_OF: (frozenset({"who"}), frozenset({"who"})),
    # ZONE_COUNT_GE (grammar round 6, R6-2): "an opponent has 8 or more
    # cards in their graveyard" (Thieves' Guild Enforcer). who = the player
    # whose zone is counted; zone = the zone counted (same Zone class and
    # required-zone-slot precedent as CAST_THIS_TURN_FROM); inner_filter =
    # the cards counted; count = the threshold Quantity (precedent
    # CONTROLLER_COUNT_GE — count unsetness is not enforced there either).
    FAtomPred.ZONE_COUNT_GE: (
        frozenset({"who", "zone", "inner_filter", "count"}),
        frozenset({"who", "zone", "inner_filter", "count"}),
    ),
    # IS_ATTACHED_TO (grammar round 7, R7-1): attached to the referent
    # object — required referent slot ("Destroy target Equipment attached
    # to that", Turn to Slag). Vocabulary: _QPROP_STR_REFERENTS (C12).
    FAtomPred.IS_ATTACHED_TO: (
        frozenset({"referent"}),
        frozenset({"referent"}),
    ),
    # NAME_CHOSEN (grammar round 7, R7-4): name equals the CHOOSE_NAME
    # pick ("cards with that name", Runed Halo s2 / Necromentia s2). No
    # slots (precedent: IS_TAPPED).
    FAtomPred.NAME_CHOSEN: (frozenset(), frozenset()),
    # IS_EXILED_WITH_SOURCE (grammar round 8, R8-6): "the card exiled
    # with ~" (Horizon Scholar, Idol of Endurance) — the card is in exile
    # AND the ability's source exiled it. No slots (precedent: IS_TAPPED);
    # evaluated against the source object.
    FAtomPred.IS_EXILED_WITH_SOURCE: (frozenset(), frozenset()),
    # CONTROLLER_COUNT_GT (grammar round 8, R8-9): dual-filter count
    # comparison — "controls more creatures than you" (Garruk, Primal
    # Hunter's rivals): inner_filter counts the referent controller's
    # objects, right_inner_filter the comparison side's. Both slots are
    # REQUIRED (the comparison has no one-sided reading).
    FAtomPred.CONTROLLER_COUNT_GT: (
        frozenset({"inner_filter", "right_inner_filter"}),
        frozenset({"inner_filter", "right_inner_filter"}),
    ),
    # LIFE_LEAD_OVER_START_GE (grammar round 9, R9-2): net life lead over
    # the referent player's starting total — count = the threshold Quantity
    # (rule row {count}-only, the CARDS_DRAWN-style single-slot precedent;
    # no who slot: the predicate binds its subject player directly).
    FAtomPred.LIFE_LEAD_OVER_START_GE: (frozenset({"count"}), frozenset({"count"})),
    # NAME_PARTITION_COUNT_GE / ATTACK_AGAINST_COUNT_GE (grammar round 10,
    # R10-2/R10-3): inner_filter + count, twin of the CONTROLLER_COUNT_GE
    # rule above — both slots required, no others.
    FAtomPred.NAME_PARTITION_COUNT_GE: (
        frozenset({"inner_filter", "count"}),
        frozenset({"inner_filter", "count"}),
    ),
    FAtomPred.ATTACK_AGAINST_COUNT_GE: (
        frozenset({"count", "inner_filter"}),
        frozenset({"count", "inner_filter"}),
    ),
    # OPPONENT_OF (grammar round 11, R11-1): the destination identity pred
    # — who = the side the subject must NOT be on (ControllerRef or
    # referent Selector, the CONTROLLER_IS single-slot precedent).
    FAtomPred.OPPONENT_OF: (frozenset({"who"}), frozenset({"who"})),
}

# Atom role -> allowed value types. "types" is a tuple of card-type strings
# (data); "color" is a WUBRG string plus colourless "C" and (grammar round
# 8, R8-3) "ANY" = "mana of any one color" — a choice among WUBRG, distinct
# from colourless "C" (validated in AtomArgs.__post_init__).
_ROLE_TYPES: dict[str, tuple[type, ...]] = {
    "target": (Selector,),
    "source": (Selector,),
    "cards": (Selector,),
    "equipment": (Selector,),
    # "controller" takes a referent Selector too (grammar round 4,
    # object anaphora): Gloom Sower's "its controller loses life" =
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
    # name_filter (grammar round 7, R7-4): CHOOSE_NAME's name restriction
    # ("choose a nonbasic card name", Necromentia); Filter-valued like
    # GRANT_ABILITY's ability / PREVENT_EFFECT's condition roles.
    "name_filter": _F_CLASSES,
    # dealer / recipient (grammar round 8, R8-5): DEAL_DAMAGE's optional
    # damage-surface roles — "you" as recipient ("damage to you", Nine
    # Lives) or a player-identity Filter naming a side. Widened like
    # "controller": a referent, a referent Selector, or a Filter.
    "dealer": (ControllerRef, Selector) + _F_CLASSES,
    "recipient": (ControllerRef, Selector) + _F_CLASSES,
    # filter (grammar round 9, R9-3): MANA_POLICY's / GRANT_ACTIVATION's
    # shape restriction role — "spells that cost {X} or less to cast" —
    # Filter-valued like the name_filter / condition roles above.
    "filter": _F_CLASSES,
    # scope (grammar round 9, R9-3, C21): MANA_POLICY's closed string pair
    # ("THIS_MANA" / "ALL_YOURS"), validated against _MANA_POLICY_SCOPES
    # in AtomArgs.__post_init__ (the "color" role's vocab-check precedent).
    "scope": (str,),
    # step (grammar round 9, R9-4): PREVENT_EFFECT's "during a target's
    # next untap step" role (Frost Breath) — same Step enum the StepEvent
    # and DurationUntilNextStep fields carry.
    "step": (Step,),
    # window (grammar round 9, R9-7): GRANT_ACTIVATION's optional timing
    # role — which ActivationWindow the extra activation joins (Teferi,
    # Master of Time's +2: "until end of turn" = the sorcery window).
    "window": (ActivationWindow,),
    # T4 P1a (2026-10-07), the merged MOVE atom's three new slots:
    # "from" — the visible departure-zone axis (menu-visibility law §10:
    # the mill/discard shapes ENCODE their source zone instead of leaning
    # on the verb name; old MOVE_ZONE rows stay from-less = "wherever the
    # objects are").
    "from": (Zone,),
    # "journal_kind" — A2(ii): the literal journalled event kind carried
    # as a SLOT so the merge moves no journal bytes ("MILL", else the
    # "MOVE" default); closed vocabulary _MOVE_JOURNAL_KINDS below.
    "journal_kind": (str,),
    # "pop_order" — A2(iii): mill's top-of-library pop, pinned explicitly
    # (never a selector-order resolution); "TOP" only.
    "pop_order": (str,),
}

# Verb -> {role: required?}. MODIFY_PT and SET_PT additionally require at
# least one of power/toughness (enforced in Atom.__post_init__). The optional
# "duration" role (Duration) marks the temporary-effect verbs: MODIFY_PT,
# SET_PT, GRANT_ABILITY, GRANT_TYPE, PREVENT_EFFECT ("until end of turn"),
# plus TAP / UNTAP (a tap or untap is a temporary effect) and MANDATE_ATTACK
# (a continuous "attacks each combat if able").
_VERB_ROLES: dict[Verb, dict[str, bool]] = {
    # dealer / recipient (grammar round 8, R8-5): optional roles for the
    # C-4 damage-surface rows — "damage THAT WOULD BE DEALT TO you"
    # restrictions (Nine Lives) and explicit "to you" recipients. Both
    # accept a ControllerRef, a referent Selector, or a Filter (the
    # player-identity FAtom names a side of the comparison); the
    # templates opt in during the 8-B fidelity flip.
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
    # CREATE_TOKEN += controller (grammar round 11, R11-2, batch 6 ruling
    # /10): the anaphoric "ITS CONTROLLER creates a … token" creator
    # (Secure the Scene / Angelic Ascension s2). Optional; omitted = the
    # ability's controller (every pre-round row, byte-unchanged). The
    # value is a ControllerRef or referent Selector (LOSE_LIFE-controller
    # precedent, Gloom-Sower/Death-Mage lanes).
    Verb.CREATE_TOKEN: {"tokens": True, "count": False, "controller": False},
    # T5-D (Sanctum of All): how many EXTRA times the matched ability
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
    # SET_PT (grammar round 6, R6-3): power/toughness are each optional,
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
    # value is wrapped in a "Bool" tag inside the pairs (T3 round 2, item 4).
    # MOVE_ZONE — T4 P1a (2026-10-07): the ONE move atom. `destination`
    # is the mandatory `to`; the object arrives on exactly one of three
    # axes, one per predecessor shape: `cards` (selector/binding, old
    # MOVE_ZONE), `target` (designation lane, old EXILE — role key kept
    # per A2(iv) so spell designation shadowing still finds it), or
    # `controller`+`amount` with `pop_order`="TOP" (old MILL's library
    # pop, A2(iii)). `from` states the departure zone where the shape
    # knows it (mill/discard); `journal_kind` carries A2(ii)'s literal
    # journal row kind. Axes stay orthogonal (§9): operation × menu ×
    # count × journal kind, no fused special-case verb.
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
    # REVEAL += duration (grammar round 8 R8-3 / round 9, R9-8): Snoop's
    # "Play with the top card of your library revealed" is a continuous
    # revealed state — DurationPermanent, top-of-library implicit per the
    # LOOK_AT convention (doc /10).
    Verb.REVEAL: {"controller": True, "count": True, "duration": False},
    Verb.LOOK_AT: {"controller": True, "count": True},
    Verb.ATTACH: {"equipment": True, "target": True},
    # GAIN_CONTROL: duration (grammar round 7, R7-2) — "gain control of
    # target creature until end of turn" (Traitorous), "…until this
    # creature leaves the battlefield" pairs with DurationUntilLeaves.
    Verb.GAIN_CONTROL: {"target": True, "controller": True, "duration": False},
    # PREVENT_EFFECT += step (grammar round 9, R9-4): Frost Breath's
    # "a target's next untap step" is prevented during Step.UNTAP — the
    # step slot names WHICH step the prevention covers, paired with
    # DurationUntilNextStep (doc /10).
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
    # MANDATE_BLOCK (grammar round 6, R6-5): mirrors MANDATE_ATTACK exactly
    # — "must be blocked if able" (Canopy Stalker); subject-scoped, the
    # executor is deferred per the PHASE_IN-orphan precedent.
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
    # CHOOSE (grammar round 7, R7-1): "You choose a noncreature, nonland
    # card from it" (Duress, Kitesail) — `target` is the pool chosen FROM
    # (typically a referent="result" Selector over the previous
    # sentence's zone); the pick records the ability's result register.
    Verb.CHOOSE: {"target": True, "count": False, "duration": False},
    # CHOOSE_NAME (grammar round 7, R7-4): "choose a name" (Runed Halo —
    # no filter; Necromentia — "a nonbasic card name", name_filter). The
    # pick is read back by FAtomPred.NAME_CHOSEN. Role decision: optional,
    # mirroring the bare-vs-parametrized split of GRANT/ATTACH analogues
    # (KeywordAbility params, PREVENT_EFFECT.condition) — the filter only
    # narrows which names are legal picks.
    Verb.CHOOSE_NAME: {"name_filter": False},
    # FIGHT (grammar round 7, R7-8): "This creature fights another target
    # creature" (Brash Taunter), "it fights up to one target creature you
    # don't control" (Primal Might). The attacker is the source/IT
    # referent, never a role. Executor deferred per the MANDATE_BLOCK /
    # PHASE_IN orphan precedent (PC-6 unaffected).
    Verb.FIGHT: {"target": True},
    # LOSE_ABILITY (grammar round 7, R9a): "that permanent loses
    # indestructible until end of turn" (Soul Sear) — mirrors
    # GRANT_ABILITY's roles exactly.
    Verb.LOSE_ABILITY: {"target": True, "ability": True, "duration": False},
    # GET_EMBLEM (grammar round 8, R8-7, C19): NO roles — mirroring the
    # FLIP_COIN role-less row exactly. The verb is the marker "you get an
    # emblem"; the emblem's own abilities are the payload via the
    # card-level emblem attach (compiler.py two-pass). The quoted text
    # NEVER enters the ability IR (no emblem_ref role: C19).
    Verb.GET_EMBLEM: {},
    # ADD_LAND_PLAY (grammar round 8, R8-8): "You may play two additional
    # lands on each of your turns" (Azusa, Lost but Seeking). `count` =
    # the number of additional plays, `duration` scopes the grant
    # (DurationPermanent for "on each of your turns"). Executor deferred
    # per the FIGHT / MANDATE_ATTACK orphan precedent.
    Verb.ADD_LAND_PLAY: {"count": False, "duration": False},
    # MANA_POLICY (grammar round 9, R9-3, C21): spend-restriction verbs —
    # Vodalian Invoice's "this spell can't be countered" style mana-use
    # policies are scope=THIS_MANA, Orrery-style "you may spend mana as
    # though it were mana of any color to cast that spell" is
    # scope=ALL_YOURS with a filter over the spell's cast shape. Executor
    # deferred per the ADD_LAND_PLAY orphan precedent (consumed in 9-B).
    Verb.MANA_POLICY: {"scope": True, "filter": False},
    # GRANT_ACTIVATION (grammar round 9, R9-7): "You may activate an
    # additional loyalty ability of targets named Teferi this turn" —
    # filter over the permanent shape (NAME_CONTAINS gate, closing the 8-C
    # withdrawal), window (R9-1's ActivationWindow) names which timing
    # window the extra activation joins. Executor deferred per the FIGHT /
    # ADD_LAND_PLAY orphan precedent.
    Verb.GRANT_ACTIVATION: {"filter": True, "window": False},
    # DAMAGE_ASSIGN_POLICY (grammar round 10, R10-4, C28): combat-damage
    # assignment policies — scope carries the closed _DAMAGE_ASSIGN_SCOPES
    # vocabulary (AS_UNBLOCKED), filter optionally narrows the affected
    # damage dealers. The "You may" vertex lives OUTSIDE the atom (C15:
    # the granted StaticAbility holds OptionalEffect wrapping this Atom).
    # Executor deferred per the MANA_POLICY orphan precedent.
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
}


# ---------------------------------------------------------------------------
# Serialization — to_dict / from_dict / canonical_json / fingerprint.
#
# Stable encoding (golden files and PC-9 depend on it — never renumber):
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
    CombatDamageEvent,
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
    SacrificeEvent,
    LoyaltyActivatedEvent,
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
    CardRecord,
)

_CLASS_BY_TAG: dict[str, type] = {c.__name__: c for c in _DATACLASSES}
_TAG: dict[type, str] = {c: c.__name__ for c in _DATACLASSES}

# tag -> ((field, converter), ...). Converters: "int", "bool", "str",
# "opt:X", "tup:X", "enum:<Name>", "colorset", "qprop_referent",
# "atom_pairs", "atom_value", and the union names in _UNION_CONVS.
_SPECS: dict[str, tuple[tuple[str, str], ...]] = {
    "QConst": (("value", "int"),),
    "QX": (),
    "QUnbounded": (),
    "QCount": (("selector", "selector"),),
    # grammar round 9, R9-6: distinct-color count of the selector's cards
    # (Orrery draw-per-color); same single-selector encoding as QCount.
    "QDistinctColorCount": (("selector", "selector"),),
    "QProp": (
        ("referent", "qprop_referent"),
        ("field", "enum:QPropField"),
        ("agg", "enum:QAgg"),
    ),
    "QBin": (
        ("op", "enum:QBinOp"),
        ("left", "quantity"),
        ("right", "quantity"),
        # T5-D rounding policy: omitted at the None default (_OMIT_IF_EMPTY
        # row) - every pre-T5-D QBin keeps its golden bytes.
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
        ("zone", "zone"),
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
        # who widens to a referent Selector (grammar round 4, object
        # anaphora): ControllerRef OR a tagged Selector dict.
        ("who", "opt:controller_ref_or_selector"),
        ("inner_filter", "opt:filter"),
        ("zone", "opt:zone"),
        ("from_zone", "opt:zone"),
        ("to_zone", "opt:zone"),
        ("referent", "opt:str"),
        # right_inner_filter (grammar round 8, R8-9): omit-when-None.
        ("right_inner_filter", "opt:filter"),
    ),
    "DurationEot": (),
    "DurationPermanent": (),
    "DurationUntilNextTurn": (),
    "DurationWhileCondition": (("filter", "filter"),),
    # source (grammar round 7, R7-2): a referent string, serialized bare;
    # vocabulary validated in __post_init__ (also on the from_dict path).
    "DurationUntilLeaves": (("source", "str"),),
    # grammar round 9, R9-4: "until <owner>'s next <step>" (Frost Breath
    # pairs it with PREVENT_EFFECT step=Step.UNTAP); owner_scoped True
    # (the default) serializes as a bare bool, byte-stable like TapStateEvent.
    "DurationUntilNextStep": (("step", "enum:Step"), ("owner_scoped", "bool")),
    "ZoneChangeEvent": (
        ("from_zone", "zone"),
        ("to_zone", "zone"),
        ("subject", "opt:filter"),
    ),
    "CastSpellEvent": (
        ("filter", "filter"),
        ("controller", "opt:enum:ControllerRef"),
        ("from_zone", "opt:zone"),
        ("ordinal", "opt:int"),
        # from_zone_not (grammar round 4): "from anywhere other than the
        # hand" — mutually exclusive with from_zone, omitted when None.
        ("from_zone_not", "opt:zone"),
    ),
    "DeclareAttackersEvent": (
        ("filter", "filter"),
        # attacked (grammar round 10, R10-3): narrows the attacked-side
        # object; omitted when None.
        ("attacked", "opt:filter"),
    ),
    "DeclareBlockersEvent": (
        ("filter", "filter"),
        ("subject", "opt:filter"),
        # blocked (grammar round 6, R6-4): narrows the blocked-side
        # creature; omitted when None.
        ("blocked", "opt:filter"),
    ),
    "CombatDamageEvent": (("filter", "filter"),),
    "CounterPlacedEvent": (
        ("counter_kind", "enum:CounterKind"),
        ("filter", "filter"),
        # count (grammar round 5, R5-2): the number placed; omitted when None.
        ("count", "opt:quantity"),
    ),
    "CreatureDiesEvent": (("filter", "filter"),),
    "BecomesBlockedEvent": (("filter", "filter"),),
    "TapStateEvent": (("tapped", "bool"), ("filter", "filter")),
    # T5-D: the Sanctum-of-All family event atom (subject = the
    # triggering ability's source permanent).
    "AbilityTriggerEvent": (("filter", "filter"),),
    "TurnPhaseEvent": (("phase", "enum:Phase"), ("controller", "enum:ControllerRef")),
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
    "TargetingEvent": (("filter", "filter"),),
    "CardDrawnEvent": (
        ("controller", "enum:ControllerRef"),
        ("ordinal", "opt:int"),
    ),
    "LifeGainedEvent": (("controller", "enum:ControllerRef"),),
    "SacrificeEvent": (("controller", "enum:ControllerRef"),),
    "LoyaltyActivatedEvent": (
        ("controller", "enum:ControllerRef"),
        ("filter", "filter"),
    ),
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
        # grammar round 8, R8-2/R8-4: trailing opt-in fields; omitted at
        # the None default (_OMIT_IF_EMPTY row) — byte-stable.
        ("color", "opt:str"),
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
    # grammar round 9, R9-5 (C22): duration REQUIRED — a delayed trigger
    # without a lifetime window is just a TriggeredAbility. Tag order
    # mirrors TriggeredAbility's event/condition/effect trio.
    "DelayedTrigger": (
        ("duration", "duration"),
        ("event", "event"),
        ("condition", "opt:filter"),
        ("effect", "effect"),
    ),
    "StaticAbility": (("effect", "effect"), ("condition", "opt:filter")),
    "TriggeredAbility": (
        ("event", "event"),
        ("condition", "opt:filter"),
        ("effect", "effect"),
    ),
    "ActivatedAbility": (
        ("cost", "cost"),
        ("effect", "effect"),
        ("condition", "opt:filter"),
        # timing (grammar round 9, R9-1, C20): omitted at the None
        # default (_OMIT_IF_EMPTY row) — byte-stable.
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
        # controller_ref (grammar round 5, R5-3): ControllerRef, OR a
        # Selector (the controller of the selected object — convention C7).
        ("controller_ref", "controller_ref_or_selector"),
        ("delta", "cost_delta"),
        ("condition", "opt:filter"),
        ("extra_deltas", "tup:cost_delta"),
    ),
    "EtBState": (
        ("tapped", "bool"),
        ("initial_counters", "tup:counter_placement"),
    ),
    "EmblemAbility": (("embedded", "ability"),),
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
    }
)
_EVENT_TAGS = frozenset(
    {
        "ZoneChangeEvent",
        "CastSpellEvent",
        "DeclareAttackersEvent",
        "DeclareBlockersEvent",
        "CombatDamageEvent",
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
        "SacrificeEvent",
        "LoyaltyActivatedEvent",
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
            "Cost",  # PAY / CAST's `cost` role carries a full Cost (T3 round)
            # grammar round 9, R9-4/R9-7: PREVENT_EFFECT's `step` role and
            # GRANT_ACTIVATION's `window` role carry enum values — the
            # CounterKind / ControllerRef enum-in-pairs precedent.
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
# null / []. Added by the T3 grammar round (binding constraint: every
# tree constructible before T3 must serialize byte-identical — PC-4/PC-9
# rail), so the table lists only NEW fields on pre-existing classes;
# pre-existing optional fields (CostTap.target, FAtom.slots, ...) keep
# serializing their null / [] defaults exactly as before. from_dict
# accepts these keys both absent (the empty default is injected) and
# present. This table is the only place a spec field may be absent from
# the tagged dict.
_OMIT_IF_EMPTY: dict[str, frozenset[str]] = {
    # rounding (T5-D): omit when None - byte-stable.
    "QBin": frozenset({"rounding"}),
    # referent (grammar round 4): omit when None — byte-stable.
    "Selector": frozenset({"zones", "referent"}),
    "Zone": frozenset({"position"}),
    "ZoneChangeEvent": frozenset({"subject"}),
    # attacked (grammar round 10, R10-3): omit when None — byte-stable.
    "DeclareAttackersEvent": frozenset({"attacked"}),
    # subject (r3b) + blocked (grammar round 6, R6-4): omit when None.
    "DeclareBlockersEvent": frozenset({"subject", "blocked"}),
    # from_zone_not (grammar round 4): omit when None.
    "CastSpellEvent": frozenset(
        {"controller", "from_zone", "ordinal", "from_zone_not"}
    ),
    # ordinal (grammar round 4): omit when None.
    "CardDrawnEvent": frozenset({"ordinal"}),
    # count (grammar round 5, R5-2): omit when None.
    "CounterPlacedEvent": frozenset({"count"}),
    # zone/from_zone/to_zone (grammar round 4, R4-4): omit when None. Every
    # pre-round-4 FAtom serializes byte-identical because these three keys
    # are absent (the pre-existing null/[] slots still serialize as before).
    # referent (grammar round 7, R7-1): same omission discipline — every
    # pre-round-7 FAtom keeps its exact bytes.
    # right_inner_filter (grammar round 8, R8-9): same discipline — every
    # pre-round-8 FAtom keeps its exact bytes.
    "FAtom": frozenset(
        {"zone", "from_zone", "to_zone", "referent", "right_inner_filter"}
    ),
    # color/enters_tapped/enters_attacking (grammar round 8, R8-2/R8-4):
    # TokenSpec had NO row before round 8 — without it, every existing
    # token golden would byte-diff on regeneration (dual-registration
    # rule, PITFALLS 2026-09-28; pinned in test_ability_tree_r9.py).
    "TokenSpec": frozenset({"color", "enters_tapped", "enters_attacking"}),
    "DamageDealtEvent": frozenset({"source", "combat"}),
    "CostModifier": frozenset({"condition", "extra_deltas"}),
    "SpellAbility": frozenset({"effect", "additional_costs"}),
    "StaticAbility": frozenset({"condition"}),
    # timing (grammar round 9, R9-1, C20): omit when None — without this
    # row every existing ActivatedAbility golden would byte-diff
    # (dual-registration rule, PITFALLS 2026-09-28).
    "ActivatedAbility": frozenset({"condition", "timing"}),
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
        # (T3 round 2, item 6: Ugin's "[−X]" dynamic loyalty cost).
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
        # Selector.referent (grammar round 4, object anaphora): a bare
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
        # Shared by FAtom.who (grammar round 4, object anaphora) and
        # CostModifier.controller_ref (grammar round 5, R5-3): a
        # ControllerRef tagged dict, OR a Selector tagged dict (the
        # referent selector — convention C7: the controller of the
        # selected object).
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
                continue  # T3 additive field at its empty default: omit the key
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
        raise ValueError(f"from_dict: {tag}: unknown fields {extra}")
    # omit-if-empty fields (T3 round) may be absent: the empty default is
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
    the golden-file body (PC-4)."""
    return json.dumps(to_dict(node), sort_keys=True, separators=(",", ":"))


def fingerprint(node: Any) -> str:
    """sha256 hexdigest of canonical_json — the PC-9 stability key."""
    return hashlib.sha256(canonical_json(node).encode("utf-8")).hexdigest()


def walk(node: Any) -> Iterator[Any]:
    """Yield every dataclass grammar node in `node`'s tree, pre-order —
    the card record first, then every child node (effects, selectors,
    zones, quantities, filters, events, costs, tokens, the emblem). Enum
    and scalar leaves are not yielded (their parent handles them). This is
    the instrument both the executor and the EC-2 unhandled-node-rate
    measurement (METRICS.md §3) walk the tree with.
    """
    yield node
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        for field in dataclasses.fields(node):
            yield from _walk_value(getattr(node, field.name))


def _walk_value(value: Any) -> Iterator[Any]:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        yield from walk(value)
    elif isinstance(value, tuple):
        for item in value:
            yield from _walk_value(item)
    elif isinstance(value, frozenset):
        for item in value:
            yield from _walk_value(item)
