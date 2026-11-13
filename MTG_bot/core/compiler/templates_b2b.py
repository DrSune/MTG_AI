"""B2b bucket templates: trigger-shaped sentences, the B2 keys not in B2a.

Bucket input: ``/tmp/opencode/phase1_buckets/B2b.json`` (normalized shape
keys → ``[card, sentence]`` pairs). Templates fullmatch the **concrete**
oracle sentence, never the normalized key. Keys no template covers are listed
in ``UNCOVERED``.

Conventions:

- ``When this ... enters`` uses ``ZoneChangeEvent(ANY → BATTLEFIELD YOU)``
  with subject ``IS_SOURCE``; ``Whenever a <class> enters`` sets the event
  ``subject`` to the class filter (e.g. a creature you control with a given
  power or keyword).
- ``you may`` drives ``OptionalEffect``.
- ``target`` drives ``SelectorMode.TARGET``.
- ``another`` / ``other`` adds ``FNot(inner=FAtom(IS_SOURCE))``.
- ``any target`` is ``_any_target()``: a creature, planeswalker or player
  (CR 109.5).
- ``X is the number of other attacking creatures`` is a ``QCount`` over a
  selector for other attacking creatures on the battlefield.
- Token color words populate ``TokenSpec.colors``.
- ``REVEAL`` after ``SEARCH`` cannot reference the searched cards; it carries
  only the revealing player and a count.
- ``+N/+N`` on a token and counter can differ (e.g. +1/+1 counter, 2/2 token);
  each is captured by its own regex group.
- A captured ``+N/+N`` counter on a source is validated by ``_plus1_counter``
  to be exactly ``+1/+1``; an exact ``+1/+1`` sentence uses ``QConst(1)``
  directly.
- ``you may pay {N}`` is ``Verb.PAY`` with ``Cost(parts=(CostManaGeneric(N),))``.
- ``each opponent`` for life gain/loss uses ``ControllerRef.ALL_OPPONENTS``; an
  ``EachPlayer`` effect runs relative to the iterated (opponent) player.
- ``CastSpellEvent.from_zone_not`` carries the single ``Zone`` exclusion:
  "anywhere other than their hand" → ``Zone(HAND, OPPONENT)`` ("their"
  relative to the iterated opponent, matching
  ``controller=ControllerRef.OPPONENT``); mutually exclusive with
  ``from_zone``.
- ``CastSpellEvent.ordinal`` counts the Nth cast by that controller this turn
  among the event's filter: ``ordinal=1`` over an instant/sorcery filter =
  "your first instant or sorcery spell each turn".
- ``CardDrawnEvent.ordinal`` carries "your second card each turn" the same
  way.
- Object anaphora: a referent ``Selector`` binds to an in-scope object — here
  always ``referent="event"`` (the triggering event's subject: cast → the
  cast spell; damage_dealt → the damaged recipient; becomes_blocked → the
  blocker; declare_attackers → the attacker) and is written
  ``Selector(QConst(1), CHOOSE, universal filter, Zone(ANY, ANY),
  referent="event")`` by ``_event_reference()``.  It serves as a role value
  (``LOSE_LIFE.controller``, ``DEAL_DAMAGE``/``DESTROY`` ``target``,
  ``COPY.source``) and as the ``who`` of ``CONTROLLER_IS`` ("that player
  controls").
- Quantity anaphora: "that much" / "that many" ride the triggering event and
  read ``QProp(referent="event", field=AMOUNT)``; the event itself carries
  ``amount=QUnbounded()`` (any amount).
- ``AbilityActivatedEvent`` with ``kind=LOYALTY`` carries "whenever you
  activate a loyalty ability of a Chandra planeswalker"; its ``source``
  filter is required (subtype Chandra + type Planeswalker).

Every B2b concrete sentence fullmatches **at most one** template (the
patterns are pairwise disjoint; the three named-card-search sentences share
one template and match only it); the tests check it.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Final

from MTG_bot.core.ability_tree import (
    AbilityActivatedEvent,
    AbilityKind,
    Atom,
    AtomArgs,
    BecomesBlockedEvent,
    CardDrawnEvent,
    CastSpellEvent,
    Choose,
    ControllerRef,
    Cost,
    CostManaGeneric,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DurationEot,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAgg,
    QAtMost,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    SacrificeEvent,
    Selector,
    SelectorMode,
    Seq,
    TapStateEvent,
    TargetingEvent,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    RuleReminderOutcome,
    SentenceOutcome,
    Template,
    and_or_zone_search,
)

_BUCKET: Final[str] = "B2b"
_PRIORITY: Final[int] = 50


# ---------------------------------------------------------------------------
# Shared node builders
# ---------------------------------------------------------------------------


def _n(m: re.Match[str], group: int) -> int:
    """Convert a numeric regex capture group to ``int``."""
    return int(m.group(group))


def _exact(sentence: str) -> re.Pattern[str]:
    """Compile an exact-sentence fullmatch pattern."""
    return re.compile(re.escape(sentence))


def _plus1_counter(m: re.Match[str]) -> int:
    """Validate that the captured counter is exactly ``+1/+1`` and return 1."""
    cp, ct = int(m.group(1)), int(m.group(2))
    if (cp, ct) != (1, 1):
        raise ValueError(f"B2b expects a +1/+1 counter, got +{cp}/+{ct}")
    return 1


def _to_a_player() -> Filter:
    """The damaged-recipient filter of "deals [combat] damage to a player".
    Only players, creatures, planeswalkers and battles can be dealt damage
    (CR 120.1), and all of them but a player are permanents, so "not a
    permanent" is exactly "a player". IS_PERMANENT is the CR 110.1 type-line
    test: a creature the damage killed still answers it, and the binder
    judges it FALSE for a player subject, so the FNot is TRUE there. The
    mapped card records write the same encoding (FDN Goldvein Pick)."""
    return FNot(inner=FAtom(pred=FAtomPred.IS_PERMANENT))


def _to_a_player_or_planeswalker() -> Filter:
    """ "... damage to a player or planeswalker" (Garruk's Harbinger): the
    :func:`_to_a_player` test, or a planeswalker."""
    return FOr(
        children=(
            _to_a_player(),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
        )
    )


def _ability(event, effect, condition=None, once_per_event=None) -> AbilityOutcome:
    """Wrap a triggered-ability effect as the B2b sentence outcome."""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=event, condition=condition, effect=effect, once_per_event=once_per_event
        )
    )


def _template(tid: str, name: str, pattern: re.Pattern[str], build) -> Template:
    """Build a B2b ``Template`` with the bucket's fixed priority."""
    return Template(
        tid=tid,
        name=name,
        bucket=_BUCKET,
        pattern=pattern,
        priority=_PRIORITY,
        build=build,
    )


def _self_selector() -> Selector:
    """Selector for ``this <permanent>`` — the source of the ability."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _other_creatures_you_control() -> Selector:
    """Selector for ``other creatures you control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _other_attacking_creatures() -> Selector:
    """Selector for ``other attacking creatures`` (any controller)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.IS_ATTACKING),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _untapped_creatures_you_control() -> Selector:
    """Selector for ``untapped creatures you control`` (any number)."""
    return Selector(
        QUnbounded(),
        SelectorMode.CHOOSE,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.IS_UNTAPPED),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _any_card_in_your_hand() -> Selector:
    """Selector for ``a card`` in your hand (universal filter)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
    )


def _target_opponent() -> Selector:
    """Selector for ``target opponent``: a TARGET over the opponents' seats,
    Zone(PLAYER, OPPONENT) (CR 115.1, 102.2: a target opponent is an opponent
    of the ability's controller). Not Zone(PLAYER, TARGET_PLAYER): inside a
    damage firing that reads the dealer anaphora, the controller of the
    damage's source."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(children=()),
        zones=(Zone(ZoneKind.PLAYER, ControllerRef.OPPONENT),),
    )


def _any_target() -> Selector:
    """Selector for ``any target``: a creature, planeswalker or player
    (CR 109.5), never a card in a hand or library. The card side is the
    battlefield with the FOr type filter; the player side joins through the
    engine's widening (query._widen_any_target and
    selectors._is_any_universal recognize this exact shape), so the filter
    is never evaluated on a player."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                # Never matches a card (no card has the type "Player"): it
                # marks the population as the CR 109.5 "any target" one, so
                # the engine widening can tell it from the printed "target
                # creature or planeswalker" shape (never a player, CR 115.1d).
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Player"),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _etb_event(subject: Filter) -> ZoneChangeEvent:
    """Zone-change event for ``When this ... enters``.

    ``subject`` is the object whose entering fires the trigger. Every b2b
    caller reads ``When <this permanent> enters`` and passes
    ``FAtom(pred=FAtomPred.IS_SOURCE)``. The ``Whenever a creature ...
    enters`` builders (e.g. ``_build_garruks_uprising_power_enter``) build
    their own event with the class filter; subject is never ``None``.
    """
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        subject=subject,
    )


def _attack_event() -> DeclareAttackersEvent:
    """Attackers event for ``Whenever this creature attacks``."""
    return DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE))


def _creature_power_ge_filter(power: int) -> FAnd:
    """Filter for ``a creature with power N or greater``."""
    return FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.POWER_GE, count=QConst(power)),
        )
    )


def _you_control_at_least(inner_filter: Filter, count: int) -> FAtom:
    """Set-level condition ``you control N or more`` matching ``inner_filter``."""
    return FAtom(
        pred=FAtomPred.CONTROLLER_COUNT_GE,
        inner_filter=inner_filter,
        count=QConst(count),
    )


def _event_reference() -> Selector:
    """Selector bound to the triggering event's subject (object anaphora,
    module docstring): CHOOSE, QConst(1), the neutral zone, and a universal
    filter with no type check."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
        referent="event",
    )


def _bird_token(power: int, toughness: int) -> TokenSpec:
    return TokenSpec(
        name="Bird",
        type_line="Creature — Bird",
        types=("Creature",),
        subtypes=("Bird",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(Keyword.FLYING,),
        abilities=(),
        colors=("W",),
    )


def _knight_token(power: int, toughness: int) -> TokenSpec:
    return TokenSpec(
        name="Knight",
        type_line="Creature — Knight",
        types=("Creature",),
        subtypes=("Knight",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(Keyword.VIGILANCE,),
        abilities=(),
        colors=("W",),
    )


def _saproling_token(power: int, toughness: int) -> TokenSpec:
    return TokenSpec(
        name="Saproling",
        type_line="Creature — Saproling",
        types=("Creature",),
        subtypes=("Saproling",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(),
        abilities=(),
        colors=("G",),
    )


def _cat_token(power: int, toughness: int) -> TokenSpec:
    return TokenSpec(
        name="Cat",
        type_line="Creature — Cat",
        types=("Creature",),
        subtypes=("Cat",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(),
        abilities=(),
        colors=("G",),
    )


# ---------------------------------------------------------------------------
# Builders — ETB search / draw / scry / life shapes
# ---------------------------------------------------------------------------


def _named_search_one(name: str) -> Atom:
    """One "a card named <name>" pick from your library into your hand: an
    up-to-one CHOOSE (QAtMost(1)). A player searching a hidden zone for a card
    with a stated quality need not find it (CR 701.23b), so each named find
    may come up empty; QConst(1) would make it a mandatory find."""
    return Atom(
        verb=Verb.SEARCH,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QAtMost(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.NAME_EQ, string_value=name),
                        zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
                    ),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )


def _build_alpine_houndmaster_etb(m: re.Match[str]) -> SentenceOutcome:
    """Search for named Alpine Watchdog and/or Igneous Cur, reveal, hand, shuffle.

    "a card named A and/or a card named B" is at most one card of each name:
    one pick per name, in printed order. One up-to-two pick over
    FOr(NAME A, NAME B) could fetch two Alpine Watchdogs. No IR node says
    "distinct names", so the one search is written as two picks; nothing
    observes the difference (no card in the pool triggers on searching).
    """
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        OptionalEffect(
            inner=Seq(
                steps=(
                    _named_search_one("Alpine Watchdog"),
                    _named_search_one("Igneous Cur"),
                    Atom(
                        verb=Verb.REVEAL,
                        args=AtomArgs(
                            pairs=(
                                ("controller", ControllerRef.YOU),
                                ("count", QUnbounded()),
                            )
                        ),
                    ),
                    Atom(
                        verb=Verb.SHUFFLE,
                        args=AtomArgs(
                            pairs=(
                                (
                                    "zone",
                                    Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                                ),
                            )
                        ),
                    ),
                )
            )
        ),
    )


def _build_fierce_empath_etb(m: re.Match[str]) -> SentenceOutcome:
    """Search for a creature with mana value N or greater, reveal, hand, shuffle."""
    n = _n(m, 1)
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        OptionalEffect(
            inner=Seq(
                steps=(
                    Atom(
                        verb=Verb.SEARCH,
                        args=AtomArgs(
                            pairs=(
                                (
                                    "cards",
                                    Selector(
                                        QConst(1),
                                        SelectorMode.CHOOSE,
                                        FAnd(
                                            children=(
                                                FAtom(
                                                    pred=FAtomPred.TYPE_EQ,
                                                    string_value="Creature",
                                                ),
                                                FAtom(
                                                    pred=FAtomPred.CMC_GE,
                                                    count=QConst(n),
                                                ),
                                            )
                                        ),
                                        zones=(
                                            Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                                        ),
                                    ),
                                ),
                                (
                                    "destination",
                                    Zone(ZoneKind.HAND, ControllerRef.YOU),
                                ),
                            )
                        ),
                    ),
                    Atom(
                        verb=Verb.REVEAL,
                        args=AtomArgs(
                            pairs=(
                                ("controller", ControllerRef.YOU),
                                ("count", QConst(1)),
                            )
                        ),
                    ),
                    Atom(
                        verb=Verb.SHUFFLE,
                        args=AtomArgs(
                            pairs=(
                                (
                                    "zone",
                                    Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                                ),
                            )
                        ),
                    ),
                )
            )
        ),
    )


def _build_teferis_tutelage_etb(m: re.Match[str]) -> SentenceOutcome:
    """Draw a card, then discard a card."""
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Seq(
            steps=(
                Atom(
                    verb=Verb.DRAW,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("amount", QConst(1)),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.MOVE_ZONE,
                    args=AtomArgs(
                        pairs=(
                            (
                                "destination",
                                Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                            ),
                            ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                            ("controller", ControllerRef.YOU),
                            ("cards", _any_card_in_your_hand()),
                        )
                    ),
                ),
            )
        ),
    )


def _build_temple_etb_scry(m: re.Match[str]) -> SentenceOutcome:
    """Scry N when this land enters."""
    n = _n(m, 1)
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.SCRY,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("count", QConst(n)),
                )
            ),
        ),
    )


def _build_temple_etb_gain_life(m: re.Match[str]) -> SentenceOutcome:
    """Gain N life when this land enters."""
    n = _n(m, 1)
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.GAIN_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(n)),
                )
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Builders — dies / counter / attack shapes
# ---------------------------------------------------------------------------


def _build_massacre_wurm(m: re.Match[str]) -> SentenceOutcome:
    """A creature an opponent controls dies: that player loses N life."""
    n = _n(m, 1)
    return _ability(
        CreatureDiesEvent(
            filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
                )
            )
        ),
        Atom(
            verb=Verb.LOSE_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.TARGET_PLAYER),
                    ("amount", QConst(n)),
                )
            ),
        ),
    )


def _build_hooded_blightfang(m: re.Match[str]) -> SentenceOutcome:
    """A creature you control with deathtouch attacks: each opponent loses N
    life and you gain N life."""
    n = _n(m, 1)
    return _ability(
        DeclareAttackersEvent(
            filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.DEATHTOUCH),
                )
            )
        ),
        Seq(
            steps=(
                Atom(
                    verb=Verb.LOSE_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.ALL_OPPONENTS),
                            ("amount", QConst(n)),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.GAIN_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("amount", QConst(n)),
                        )
                    ),
                ),
            )
        ),
    )


def _build_malefic_scythe(m: re.Match[str]) -> SentenceOutcome:
    """Equipped creature dies: put a soul counter on this Equipment."""
    return _ability(
        CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE)),
        Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("counter_kind", CounterKind.SOUL),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


def _build_wildwood_scorge(m: re.Match[str]) -> SentenceOutcome:
    """+1/+1 counters go on another non-Hydra creature you control: put one on this."""
    return _ability(
        CounterPlacedEvent(
            counter_kind=CounterKind.PLUS_1_PLUS_1,
            filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    FNot(inner=FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Hydra")),
                    FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                )
            ),
        ),
        Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Builders — this-creature-attacks shapes
# ---------------------------------------------------------------------------


def _build_falconer_adept(m: re.Match[str]) -> SentenceOutcome:
    """Create a 1/1 white Bird with flying that's tapped and attacking.

    "that's tapped and attacking" is TokenSpec.enters_tapped/enters_attacking
    (CR 508.4: put onto the battlefield attacking, never declared)."""
    bird = replace(_bird_token(1, 1), enters_tapped=True, enters_attacking=True)
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    ("tokens", bird),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


def _build_library_larcenist(m: re.Match[str]) -> SentenceOutcome:
    """Draw a card when this creature attacks."""
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(1)),
                )
            ),
        ),
    )


def _build_alpine_houndmaster_attack(m: re.Match[str]) -> SentenceOutcome:
    """Gets +X/+N until end of turn, X = the number of other attacking creatures."""
    n = _n(m, 1)
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    (
                        "power",
                        PtDelta(
                            PtDirection.INCREASE,
                            QCount(selector=_other_attacking_creatures()),
                        ),
                    ),
                    (
                        "toughness",
                        PtDelta(PtDirection.INCREASE, QConst(n)),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_bolt_hound(m: re.Match[str]) -> SentenceOutcome:
    """Other creatures you control get +N/+N until end of turn."""
    n_p = _n(m, 1)
    n_t = _n(m, 2)
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _other_creatures_you_control()),
                    (
                        "power",
                        PtDelta(PtDirection.INCREASE, QConst(n_p)),
                    ),
                    (
                        "toughness",
                        PtDelta(PtDirection.INCREASE, QConst(n_t)),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_spined_megalodon(m: re.Match[str]) -> SentenceOutcome:
    """Scry N when this creature attacks."""
    n = _n(m, 1)
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.SCRY,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("count", QConst(n)),
                )
            ),
        ),
    )


def _build_siege_striker(m: re.Match[str]) -> SentenceOutcome:
    """You may tap any number of untapped creatures you control. "Any number" already names
    none (CR 107.1c), asked pick by pick with a stop, so the "you may" is no choice of its own:
    no OptionalEffect around the pick (declining and stopping at once played the same)."""
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.TAP,
            args=AtomArgs(pairs=(("target", _untapped_creatures_you_control()),)),
        ),
    )


# ---------------------------------------------------------------------------
# Builders — damage-dealt shapes
# ---------------------------------------------------------------------------


def _build_brash_taunter(m: re.Match[str]) -> SentenceOutcome:
    """Dealt damage: deals that much damage to target opponent."""
    amount = QProp(referent="event", field=QPropField.AMOUNT, agg=QAgg.FIRST)
    return _ability(
        DamageDealtEvent(
            amount=amount,
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
        ),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _target_opponent()),
                    (
                        "amount",
                        QProp(
                            referent="event", field=QPropField.AMOUNT, agg=QAgg.FIRST
                        ),
                    ),
                )
            ),
        ),
    )


def _build_sporeweb_weaver(m: re.Match[str]) -> SentenceOutcome:
    """Dealt damage: gain N life and create an N/N green Saproling token."""
    n_life = _n(m, 1)
    n_power = _n(m, 2)
    n_tough = _n(m, 3)
    return _ability(
        DamageDealtEvent(
            amount=QProp(referent="event", field=QPropField.AMOUNT, agg=QAgg.FIRST),
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
        ),
        Seq(
            steps=(
                Atom(
                    verb=Verb.GAIN_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("amount", QConst(n_life)),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.CREATE_TOKEN,
                    args=AtomArgs(
                        pairs=(
                            ("tokens", _saproling_token(n_power, n_tough)),
                            ("count", QConst(1)),
                        )
                    ),
                ),
            )
        ),
    )


def _build_basris_lieutenant(m: re.Match[str]) -> SentenceOutcome:
    """A creature you control dies with a +N/+N counter on it: create an N/N
    white Knight with vigilance."""
    counter_n = int(m.group("cn"))
    token_p = int(m.group("tp"))
    token_t = int(m.group("tt"))
    return _ability(
        CreatureDiesEvent(
            filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            )
        ),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    ("tokens", _knight_token(token_p, token_t)),
                    ("count", QConst(1)),
                )
            ),
        ),
        condition=FAtom(
            pred=FAtomPred.HAS_COUNTER,
            counter_kind=CounterKind.PLUS_1_PLUS_1,
            count=QConst(counter_n),
        ),
    )


# ---------------------------------------------------------------------------
# Builders — enters, leaves, cast, draw, untap and sacrifice triggers
# ---------------------------------------------------------------------------


def _build_named_card_search_etb(m: re.Match[str]) -> SentenceOutcome:
    """Search library and/or graveyard for a named card, reveal, hand.

    "library and/or graveyard" is the visible zone choice
    (templates.and_or_zone_search); the shuffle sentence then joins only the
    options that search the library."""
    name = m.group("name")

    def search_in(zones: tuple[Zone, ...]) -> Seq:
        search = Atom(
            verb=Verb.SEARCH,
            args=AtomArgs(
                pairs=(
                    (
                        "cards",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAtom(pred=FAtomPred.NAME_EQ, string_value=name),
                            zones=zones,
                        ),
                    ),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                )
            ),
        )
        reveal = Atom(
            verb=Verb.REVEAL,
            args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("count", QConst(1)))),
        )
        return Seq(steps=(search, reveal))

    # "put it into your hand" is the SEARCH's own destination, not a separate
    # move.
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        OptionalEffect(
            inner=and_or_zone_search(
                search_in,
                Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
            )
        ),
    )


def _build_nine_lives_leave(m: re.Match[str]) -> SentenceOutcome:
    """This enchantment leaves the battlefield: you lose the game.

    The mover is this enchantment (CR 603.6c leaves-the-battlefield
    trigger): subject IS_SOURCE, as in the self-ETB shape.
    """
    return _ability(
        ZoneChangeEvent(
            from_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            to_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
            subject=FAtom(pred=FAtomPred.IS_SOURCE),
        ),
        Atom(verb=Verb.LOSE_GAME, args=AtomArgs()),
    )


def _build_garruks_uprising_power_enter(m: re.Match[str]) -> SentenceOutcome:
    """A creature you control with power N or greater enters: draw a card."""
    n = _n(m, 1)
    subject = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAtom(pred=FAtomPred.POWER_GE, count=QConst(n)),
        )
    )
    return _ability(
        ZoneChangeEvent(
            from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
            to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            subject=subject,
        ),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        ),
    )


def _build_mangara_second_spell(m: re.Match[str]) -> SentenceOutcome:
    """An opponent casts their second spell each turn: draw a card."""
    return _ability(
        CastSpellEvent(
            filter=FAnd(children=()),
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
            ordinal=2,
        ),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        ),
    )


def _build_terror_of_peaks_other_enter(m: re.Match[str]) -> SentenceOutcome:
    """Another creature you control enters: it deals damage equal to its power
    to any target."""
    subject = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
        )
    )
    return _ability(
        ZoneChangeEvent(
            from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
            to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            subject=subject,
        ),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _any_target()),
                    (
                        "amount",
                        QProp(referent="event", field=QPropField.POWER, agg=QAgg.FIRST),
                    ),
                )
            ),
        ),
    )


def _build_watcher_spheres_flying_enter(m: re.Match[str]) -> SentenceOutcome:
    """Another creature you control with flying enters: this gets +N/+N until
    end of turn."""
    p = _n(m, 1)
    t = _n(m, 2)
    subject = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
            FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
        )
    )
    return _ability(
        ZoneChangeEvent(
            from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
            to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            subject=subject,
        ),
        Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                    ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_ghostly_pilferer_untapped(m: re.Match[str]) -> SentenceOutcome:
    """This creature becomes untapped: you may pay {N}."""
    n = _n(m, 1)
    return _ability(
        TapStateEvent(tapped=False, filter=FAtom(pred=FAtomPred.IS_SOURCE)),
        OptionalEffect(
            inner=Atom(
                verb=Verb.PAY,
                args=AtomArgs(
                    pairs=(
                        (
                            "cost",
                            Cost(parts=(CostManaGeneric(QConst(n)),)),
                        ),
                    )
                ),
            )
        ),
    )


def _build_thieves_guild_enforcer(m: re.Match[str]) -> SentenceOutcome:
    """This creature or another Rogue you control enters: each opponent mills
    two cards."""
    subject = FOr(
        children=(
            FAtom(pred=FAtomPred.IS_SOURCE),
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Rogue"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                )
            ),
        )
    )
    return _ability(
        ZoneChangeEvent(
            from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
            to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            subject=subject,
        ),
        EachPlayer(
            ref=ControllerRef.ALL_OPPONENTS,
            effect=Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                        ("from", Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),
                        ("journal_kind", "MILL"),
                        ("pop_order", "TOP"),
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(2)),
                    )
                ),
            ),
        ),
    )


def _cast_subtype_token_builder(trigger_subtype: str):
    """Build a ``Whenever you cast a <subtype> spell, create a token`` builder."""

    def build(m: re.Match[str]) -> SentenceOutcome:
        p = int(m.group("p"))
        t = int(m.group("t"))
        tok = m.group("tok")
        # The printed color word is unnamed capture group 3 (white|green) of
        # both registrations.
        col = "W" if m.group(3) == "white" else "G"
        return _ability(
            CastSpellEvent(
                filter=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value=trigger_subtype),
                    )
                ),
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
            Atom(
                verb=Verb.CREATE_TOKEN,
                args=AtomArgs(
                    pairs=(
                        (
                            "tokens",
                            TokenSpec(
                                name=tok,
                                type_line=f"Creature — {tok}",
                                types=("Creature",),
                                subtypes=(tok,),
                                power=QConst(p),
                                toughness=QConst(t),
                                keywords=(),
                                abilities=(),
                                colors=(col,),
                            ),
                        ),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )

    return build


def _build_spellgorger_weird_counter(m: re.Match[str]) -> SentenceOutcome:
    """You cast a noncreature spell: put a +1/+1 counter on this creature."""
    count = _plus1_counter(m)
    return _ability(
        CastSpellEvent(
            filter=FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")),
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        ),
        Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                    ("count", QConst(count)),
                )
            ),
        ),
    )


def _build_riddleform(m: re.Match[str]) -> SentenceOutcome:
    """You cast a noncreature spell: this enchantment may become an N/N Sphinx
    creature with flying until end of turn."""
    p = _n(m, 1)
    t = _n(m, 2)
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.SET_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("power", QConst(p)),
                        ("toughness", QConst(t)),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            # "a 3/3 Sphinx creature ... in addition to its other types": the
            # card type Creature and the subtype Sphinx (CR 205.1b; the type
            # overlay is the single TYPE_EQ/SUBTYPE_EQ oracle).
            Atom(
                verb=Verb.GRANT_TYPE,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("types", ("Creature", "Sphinx")),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.FLYING, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return _ability(
        CastSpellEvent(
            filter=FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")),
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        ),
        OptionalEffect(inner=seq),
    )


def _build_quirion_dryad_colored(m: re.Match[str]) -> SentenceOutcome:
    """You cast a white, blue, black or red spell: put a +1/+1 counter on
    this creature.

    A spell "that's white, blue, black, or red" is one with at least one of
    those colors, a green-blue spell included (CR 105.2, 105.2b), so the
    filter is the FOr of COLOR_HAS (MAPPER_GUIDE "Colours"). COLOR_IN is a
    subset test, which a gold spell with green would fail."""
    return _ability(
        CastSpellEvent(
            filter=FOr(
                children=tuple(
                    FAtom(pred=FAtomPred.COLOR_HAS, color=color)
                    for color in ("W", "U", "B", "R")
                )
            ),
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        ),
        Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


def _build_lorescale_coatl_draw_counter(m: re.Match[str]) -> SentenceOutcome:
    """You draw a card: put a +1/+1 counter on this creature."""
    count = _plus1_counter(m)
    return _ability(
        CardDrawnEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        ),
        Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                    ("count", QConst(count)),
                )
            ),
        ),
    )


def _build_teferis_tutelage_draw_mill(m: re.Match[str]) -> SentenceOutcome:
    """You draw a card: target opponent mills two cards."""
    return _ability(
        CardDrawnEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        ),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    (
                        "destination",
                        Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_OPPONENT),
                    ),
                    ("from", Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_OPPONENT)),
                    ("journal_kind", "MILL"),
                    ("pop_order", "TOP"),
                    ("controller", ControllerRef.TARGET_OPPONENT),
                    ("amount", QConst(2)),
                )
            ),
        ),
    )


def _build_burlfist_oak_draw_boost(m: re.Match[str]) -> SentenceOutcome:
    """You draw a card: this creature gets +N/+N until end of turn."""
    p = _n(m, 1)
    t = _n(m, 2)
    return _ability(
        CardDrawnEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        ),
        Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                    ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_tolarian_kraken_draw_pay(m: re.Match[str]) -> SentenceOutcome:
    """You draw a card: you may pay {N}."""
    n = _n(m, 1)
    return _ability(
        CardDrawnEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        ),
        OptionalEffect(
            inner=Atom(
                verb=Verb.PAY,
                args=AtomArgs(
                    pairs=(
                        (
                            "cost",
                            Cost(parts=(CostManaGeneric(QConst(n)),)),
                        ),
                    )
                ),
            )
        ),
    )


def _build_havoc_jester_sacrifice(m: re.Match[str]) -> SentenceOutcome:
    """You sacrifice a permanent: this creature deals N damage to any target."""
    n = _n(m, 1)
    return _ability(
        SacrificeEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        ),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(pairs=(("target", _any_target()), ("amount", QConst(n)))),
        ),
    )


# ---------------------------------------------------------------------------
# Builders — single-card trigger shapes
# ---------------------------------------------------------------------------


def _build_solemn_simulacrum_etb(m: re.Match[str]) -> SentenceOutcome:
    """Search for a basic land, put it onto the battlefield tapped, shuffle."""
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        OptionalEffect(
            inner=Seq(
                steps=(
                    Atom(
                        verb=Verb.SEARCH,
                        args=AtomArgs(
                            pairs=(
                                (
                                    "cards",
                                    Selector(
                                        QConst(1),
                                        SelectorMode.CHOOSE,
                                        FAnd(
                                            children=(
                                                FAtom(
                                                    pred=FAtomPred.SUPERTYPE_EQ,
                                                    string_value="Basic",
                                                ),
                                                FAtom(
                                                    pred=FAtomPred.TYPE_EQ,
                                                    string_value="Land",
                                                ),
                                            )
                                        ),
                                        zones=(
                                            Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                                        ),
                                    ),
                                ),
                                (
                                    "destination",
                                    Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                                ),
                                ("tapped_on_enter", True),
                            )
                        ),
                    ),
                    Atom(
                        verb=Verb.SHUFFLE,
                        args=AtomArgs(
                            pairs=(
                                (
                                    "zone",
                                    Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                                ),
                            )
                        ),
                    ),
                )
            )
        ),
    )


def _build_garruks_uprising_etb_condition(m: re.Match[str]) -> SentenceOutcome:
    """ETB, if you control a creature with power N or greater, draw a card.

    "a creature" means one or more: count=1, and the power threshold lives
    only in the inner POWER_GE filter (as for Historian Teferi below).
    """
    n = _n(m, 1)
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(1)),
                )
            ),
        ),
        condition=_you_control_at_least(_creature_power_ge_filter(n), 1),
    )


def _build_historian_teferi_condition(m: re.Match[str]) -> SentenceOutcome:
    """Attacks, if you control a Teferi planeswalker: draw a card."""
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(1)),
                )
            ),
        ),
        condition=_you_control_at_least(
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                    FAtom(pred=FAtomPred.NAME_CONTAINS, string_value="Teferi"),
                )
            ),
            1,
        ),
    )


def _build_ornery_power_condition_self_boost(m: re.Match[str]) -> SentenceOutcome:
    """Attacks, if you control a creature with power N or greater: this
    creature gets +P/+T until end of turn.

    The clause is an existence claim: count=1, with the threshold N only in
    the inner POWER_GE filter (as for Garruk's Uprising's ETB above)."""
    n = _n(m, 1)
    power = _n(m, 2)
    toughness = _n(m, 3)
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    (
                        "power",
                        PtDelta(PtDirection.INCREASE, QConst(power)),
                    ),
                    (
                        "toughness",
                        PtDelta(PtDirection.INCREASE, QConst(toughness)),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        ),
        condition=_you_control_at_least(_creature_power_ge_filter(n), 1),
    )


def _build_tide_skimmer_two_flying(m: re.Match[str]) -> SentenceOutcome:
    """You attack with two or more creatures with flying: draw a card.

    DeclareAttackersEvent is per-creature; "you attack with" triggers once per
    declaration (once_per_event, CR 508.3d). "Two or more" is part of the
    trigger event, so it is in the event's filter, read once as the attackers
    are declared; it is not an intervening "if" (CR 603.4), so it is not the
    condition, which is read again as the ability resolves. The card draws
    even when attackers leave or lose flying meanwhile (its ruling).
    """
    flying = (
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
    )
    two_attacking = _you_control_at_least(
        FAnd(children=(*flying, FAtom(pred=FAtomPred.IS_ATTACKING))), 2
    )
    return _ability(
        DeclareAttackersEvent(filter=FAnd(children=(*flying, two_attacking))),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(1)),
                )
            ),
        ),
        once_per_event=True,
    )


def _build_vito_gain_life_lose_life(m: re.Match[str]) -> SentenceOutcome:
    """Whenever you gain life, target opponent loses that much life."""
    return _ability(
        LifeGainedEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        ),
        Atom(
            verb=Verb.LOSE_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.TARGET_OPPONENT),
                    (
                        "amount",
                        QProp(referent="event", field=QPropField.AMOUNT),
                    ),
                )
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Builders — object anaphora, ordinals, from_zone_not and loyalty activation
# ---------------------------------------------------------------------------


def _targeted_by_an_opponent(subject: Filter) -> TargetingEvent:
    """"Whenever <subject> becomes the target of a spell or ability an opponent
    controls": ``filter`` reads the targeted object, ``actor`` the controller
    of the targeting spell or ability (the direction encoding CastSpellEvent's
    actor uses). Shared by the Warden template and the targeted frame
    (frames.py), so both build the same bytes."""
    return TargetingEvent(
        filter=subject,
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
    )


def _build_warden_of_the_woods(m: re.Match[str]) -> SentenceOutcome:
    """Becomes the target of a spell or ability an opponent controls: you may
    draw two cards. "an opponent controls" is the event's ``actor``."""
    return _ability(
        _targeted_by_an_opponent(FAtom(pred=FAtomPred.IS_SOURCE)),
        OptionalEffect(
            inner=Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(2)),
                    )
                ),
            )
        ),
    )


def _build_jeskai_elder(m: re.Match[str]) -> SentenceOutcome:
    """Deals combat damage to a player: you may draw a card.

    DamageDealtEvent{amount: QUnbounded, source: IS_SOURCE, combat: True},
    the same shell as Garruk's Harbinger's, with the recipient
    :func:`_to_a_player`."""
    return _ability(
        DamageDealtEvent(
            amount=QUnbounded(),
            filter=_to_a_player(),
            source=FAtom(pred=FAtomPred.IS_SOURCE),
            combat=True,
        ),
        OptionalEffect(
            inner=Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(1)),
                    )
                ),
            )
        ),
    )


def _noncombat_source_event() -> DamageDealtEvent:
    """DamageDealtEvent for "a source you control deals noncombat damage to
    an opponent" (Incinerator / Pyreling). The dealer is the event ``source``
    filter (CONTROLLER_IS YOU). The recipient is the event ``filter``,
    ``OPPONENT_OF`` (who=YOU), so damage to an opponent's permanent or to
    yourself does not fire the trigger. ``combat=False`` pins noncombat
    damage."""
    return DamageDealtEvent(
        amount=QUnbounded(),
        filter=FAtom(pred=FAtomPred.OPPONENT_OF, who=ControllerRef.YOU),
        source=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        combat=False,
    )


def _build_chandras_incinerator(m: re.Match[str]) -> SentenceOutcome:
    """This creature deals that much damage to target creature or
    planeswalker that player controls.

    "That much" = QProp("event", AMOUNT); "that player" = the damaged
    recipient, the event referent in the CONTROLLER_IS who slot."""
    target = Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FOr(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                    )
                ),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=_event_reference()),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )
    return _ability(
        _noncombat_source_event(),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", target),
                    (
                        "amount",
                        QProp(referent="event", field=QPropField.AMOUNT),
                    ),
                )
            ),
        ),
    )


def _build_chandras_pyreling(m: re.Match[str]) -> SentenceOutcome:
    """This creature gets +N/+N and gains double strike until end of turn
    (both effects DurationEot-scoped)."""
    p = _n(m, 1)
    t = _n(m, 2)
    return _ability(
        _noncombat_source_event(),
        Seq(
            steps=(
                Atom(
                    verb=Verb.MODIFY_PT,
                    args=AtomArgs(
                        pairs=(
                            ("target", _self_selector()),
                            ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                            ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
                            ("duration", DurationEot()),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.GRANT_ABILITY,
                    args=AtomArgs(
                        pairs=(
                            ("target", _self_selector()),
                            ("ability", KeywordAbility(keyword=Keyword.DOUBLE_STRIKE)),
                            ("duration", DurationEot()),
                        )
                    ),
                ),
            )
        ),
    )


def _build_pack_leader(m: re.Match[str]) -> SentenceOutcome:
    """Prevent all combat damage that would be dealt this turn to Dogs you
    control.

    PREVENT_EFFECT with condition and event over the same protected subject:
    condition = the Dogs filter, event = the damage event over the same
    subject with ``combat=True``, duration = DurationEot for "this turn"."""
    dogs = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Dog"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        )
    )
    return _ability(
        DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.PREVENT_EFFECT,
            args=AtomArgs(
                pairs=(
                    ("condition", dogs),
                    (
                        "event",
                        DamageDealtEvent(amount=QUnbounded(), filter=dogs, combat=True),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_gloom_sower(m: re.Match[str]) -> SentenceOutcome:
    """Becomes blocked by a creature: that creature's controller loses N
    life and you gain N life.

    "That creature" = the blocker, the BecomesBlockedEvent subject, bound
    via the event referent in the LOSE_LIFE controller role."""
    # The pattern's \1 backreference guarantees the two life values are
    # equal, so a single capture group carries both.
    n = _n(m, 1)
    return _ability(
        BecomesBlockedEvent(
            filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
        ),
        Seq(
            steps=(
                Atom(
                    verb=Verb.LOSE_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", _event_reference()),
                            ("amount", QConst(n)),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.GAIN_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("amount", QConst(n)),
                        )
                    ),
                ),
            )
        ),
    )


def _build_hooded_blightfang_planeswalker(m: re.Match[str]) -> SentenceOutcome:
    """A creature you control with deathtouch deals damage to a
    planeswalker: destroy that planeswalker.

    The damaged recipient carries the Planeswalker supertype filter; "that
    planeswalker" binds via the event referent (damage_dealt → the damaged
    recipient)."""
    source = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.DEATHTOUCH),
        )
    )
    return _ability(
        DamageDealtEvent(
            amount=QUnbounded(),
            filter=FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Planeswalker"),
            source=source,
        ),
        Atom(
            verb=Verb.DESTROY,
            args=AtomArgs(pairs=(("target", _event_reference()),)),
        ),
    )


def _build_feline_sovereign(m: re.Match[str]) -> SentenceOutcome:
    """One or more Cats you control deal combat damage to a player: destroy
    up to one target artifact or enchantment that player controls.

    DamageDealtEvent{amount: QUnbounded, source: the Cats filter, combat:
    True}, recipient :func:`_to_a_player`. The event subject is the damaged
    player, so "that player" is the event referent in the CONTROLLER_IS who
    slot. "One or more Cats" is once_per_event: one trigger per combat damage
    step for each player the Cats damaged (CR 510.2, 603.2c), not one per
    Cat."""
    cats = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Cat"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        )
    )
    # "destroy up to one target artifact or enchantment" — TARGET +
    # QAtMost(1) (targeted "up to N").
    target = Selector(
        QAtMost(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FOr(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Enchantment"),
                    )
                ),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=_event_reference()),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )
    return _ability(
        DamageDealtEvent(
            amount=QUnbounded(),
            filter=_to_a_player(),
            source=cats,
            combat=True,
        ),
        Atom(
            verb=Verb.DESTROY,
            args=AtomArgs(pairs=(("target", target),)),
        ),
        once_per_event=True,
    )


def _build_ghostly_pilferer_cast(m: re.Match[str]) -> SentenceOutcome:
    """An opponent casts a spell from anywhere other than their hand: draw a
    card.

    CastSpellEvent.from_zone_not carries the exclusion; "their hand" is
    relative to the iterated opponent → Zone(HAND, OPPONENT)."""
    return _ability(
        CastSpellEvent(
            filter=FAnd(children=()),
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
            from_zone_not=Zone(ZoneKind.HAND, ControllerRef.OPPONENT),
        ),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(1)),
                )
            ),
        ),
    )


def _build_double_vision_copy(m: re.Match[str]) -> SentenceOutcome:
    """You cast your first instant or sorcery spell each turn: copy that
    spell.

    CastSpellEvent.ordinal=1 counts the first cast matching the event's
    instant/sorcery filter this turn; "that spell" binds via the event
    referent on COPY.source (cast → the cast spell)."""
    return _ability(
        CastSpellEvent(
            filter=FOr(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
                )
            ),
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ordinal=1,
        ),
        Atom(
            verb=Verb.COPY,
            args=AtomArgs(pairs=(("source", _event_reference()),)),
        ),
    )


def _build_double_vision_new_targets(m: re.Match[str]) -> RuleReminderOutcome:
    """"You may choose new targets for the copy." — the continuation of
    Double Vision's copy sentence; the anaphoric "the copy" cannot be
    resolved standalone. The concrete row lives in the B4 bucket, but the
    template is registered here."""
    return RuleReminderOutcome(reason="anaphoric_continuation")


def _build_garruks_harbinger(m: re.Match[str]) -> SentenceOutcome:
    """This creature deals combat damage to a player or planeswalker: look
    at that many cards from the top of your library.

    "That many" = QProp("event", AMOUNT); LOOK_AT looks at the top of the
    library. The recipient is :func:`_to_a_player_or_planeswalker`."""
    return _ability(
        DamageDealtEvent(
            amount=QUnbounded(),
            filter=_to_a_player_or_planeswalker(),
            source=FAtom(pred=FAtomPred.IS_SOURCE),
            combat=True,
        ),
        Atom(
            verb=Verb.LOOK_AT,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    (
                        "count",
                        QProp(referent="event", field=QPropField.AMOUNT),
                    ),
                )
            ),
        ),
    )


def _build_jolrael_cat_token(m: re.Match[str]) -> SentenceOutcome:
    """You draw your second card each turn: create an N/N green Cat token
    (CardDrawnEvent.ordinal=2)."""
    p = _n(m, 1)
    t = _n(m, 2)
    return _ability(
        CardDrawnEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU), ordinal=2
        ),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(pairs=(("tokens", _cat_token(p, t)), ("count", QConst(1)))),
        ),
    )


def _build_mystic_skyfish(m: re.Match[str]) -> SentenceOutcome:
    """You draw your second card each turn: this creature gains flying until
    end of turn."""
    return _ability(
        CardDrawnEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU), ordinal=2
        ),
        Atom(
            verb=Verb.GRANT_ABILITY,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("ability", KeywordAbility(keyword=Keyword.FLYING)),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_keral_keep_disciples(m: re.Match[str]) -> SentenceOutcome:
    """You activate a loyalty ability of a Chandra planeswalker: this
    creature deals 1 damage to each opponent.

    AbilityActivatedEvent with kind LOYALTY (CR 606.2; source = subtype
    Chandra + type Planeswalker). "Each opponent" is
    EachPlayer(ref=ALL_OPPONENTS) with the inner DEAL_DAMAGE rebound to the
    iterated opponent (Zone(PLAYER, YOU))."""
    chandra = FAnd(
        children=(
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Chandra"),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
        )
    )
    return _ability(
        AbilityActivatedEvent(
            source=chandra,
            kind=AbilityKind.LOYALTY,
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        ),
        EachPlayer(
            ref=ControllerRef.ALL_OPPONENTS,
            effect=Atom(
                verb=Verb.DEAL_DAMAGE,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
                            Selector(
                                QConst(1),
                                SelectorMode.CHOOSE,
                                FAnd(children=()),
                                zones=(Zone(ZoneKind.PLAYER, ControllerRef.YOU),),
                            ),
                        ),
                        ("amount", QConst(1)),
                    )
                ),
            ),
        ),
    )


def _build_blocks_flying_pump(m: re.Match[str]) -> SentenceOutcome:
    """This creature blocks a creature with flying: it gets +N/+0 until end
    of turn (Snarespinner).

    The blocker is the event filter (IS_SOURCE) and the blocked creature the
    ``blocked`` slot (KEYWORD_HAS flying). The zero toughness delta is
    omitted (MODIFY_PT needs only one of power/toughness)."""
    return _ability(
        DeclareBlockersEvent(
            FAtom(pred=FAtomPred.IS_SOURCE),
            blocked=FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
        ),
        Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _self_selector()),
                    ("power", PtDelta(PtDirection.INCREASE, QConst(_n(m, 1)))),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_kraken_do_tap_or_untap(m: re.Match[str]) -> SentenceOutcome:
    """Tolarian Kraken: "When you do, you may tap or untap target creature."
    The continuation parses as a standalone EffectOutcome, and the
    compiler's "When you do" merge (compiler._merge_if_do_continuation) makes
    it a reflexive trigger gated on the {1} payment (``B2b-draw-pay``), CR
    603.12. The final tree is ``Seq(OptionalEffect(PAY {1}),
    Conditional(MAY_DONE, DelayedTrigger(reflexive, OptionalEffect(Choose(1,
    tap|untap)))))``.

    Both decisions stay open: this "you may" keeps its own OptionalEffect
    inside the reflexive trigger, and "tap or untap" is a one-of-two Choose.
    One TARGET creature selector is shared by both options: the target is
    declared once, as the reflexive trigger goes on the stack, so both atoms
    denote the same object."""
    target = Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )
    return EffectOutcome(
        effect=OptionalEffect(
            inner=Choose(
                count=QConst(1),
                options=(
                    Atom(verb=Verb.TAP, args=AtomArgs(pairs=(("target", target),))),
                    Atom(verb=Verb.UNTAP, args=AtomArgs(pairs=(("target", target),))),
                ),
            )
        )
    )


def _you_or_your_planeswalkers() -> FOr:
    """Filter for the attacked object in "you and/or planeswalkers you
    control" (Mangara). Limb 1 is the defending player: CONTROLLER_IS
    who=YOU matches a player who is you (a player is their own controller,
    as the DRAW/EXILE controller roles read it). Limb 2, the planeswalkers
    you control, is a subset of limb 1 by that reading but stays its own
    branch so the two printed limbs remain distinct in the tree."""
    return FOr(
        children=(
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
        )
    )


def _build_mangara_attackers_draw(m: re.Match[str]) -> SentenceOutcome:
    """``Whenever an opponent attacks with creatures, if two or more of
    those creatures are attacking you and/or planeswalkers you control,
    draw a card.`` (Mangara, the Diplomat)

    DeclareAttackersEvent over the opponent's creatures, with the
    ``attacked`` slot carrying :func:`_you_or_your_planeswalkers` (it narrows
    the attacked object per attacker). "An opponent attacks with creatures"
    triggers once per declaration (once_per_event, CR 508.3d). The "if" is
    the condition ``ATTACK_AGAINST_COUNT_GE`` (same filter, count=2): it
    counts the event's declared attackers whose attacked object passes the
    filter."""
    return _ability(
        DeclareAttackersEvent(
            filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
                )
            ),
            attacked=_you_or_your_planeswalkers(),
        ),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(1)),
                )
            ),
        ),
        condition=FAtom(
            pred=FAtomPred.ATTACK_AGAINST_COUNT_GE,
            inner_filter=_you_or_your_planeswalkers(),
            count=QConst(2),
        ),
        once_per_event=True,
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


TEMPLATES: Final[tuple[Template, ...]] = (
    _template(
        "B2b-alpine-houndmaster-etb",
        "Alpine Houndmaster ETB",
        _exact(
            "When this creature enters, you may search your library "
            "for a card named Alpine Watchdog and/or a card named Igneous Cur, "
            "reveal them, put them into your hand, then shuffle."
        ),
        _build_alpine_houndmaster_etb,
    ),
    _template(
        "B2b-fierce-empath-etb",
        "Fierce Empath ETB",
        re.compile(
            r"When this creature enters, you may search your library "
            r"for a creature card with mana value (\d+) or greater, "
            r"reveal it, put it into your hand, then shuffle\."
        ),
        _build_fierce_empath_etb,
    ),
    _template(
        "B2b-teferis-tutelage-etb",
        "Teferi's Tutelage ETB",
        _exact("When this enchantment enters, draw a card, then discard a card."),
        _build_teferis_tutelage_etb,
    ),
    _template(
        "B2b-temple-etb-scry",
        "Temple ETB Scry",
        re.compile(r"When this land enters, scry (\d+)\."),
        _build_temple_etb_scry,
    ),
    _template(
        "B2b-temple-etb-gain-life",
        "Temple ETB Gain Life",
        re.compile(r"When this land enters, you gain (\d+) life\."),
        _build_temple_etb_gain_life,
    ),
    _template(
        "B2b-massacre-wurm",
        "Massacre Wurm",
        re.compile(
            r"Whenever a creature an opponent controls dies, "
            r"that player loses (\d+) life\."
        ),
        _build_massacre_wurm,
    ),
    _template(
        "B2b-hooded-blightfang",
        "Hooded Blightfang",
        re.compile(
            r"Whenever a creature you control with deathtouch attacks, "
            r"each opponent loses (\d+) life and you gain \1 life\."
        ),
        _build_hooded_blightfang,
    ),
    _template(
        "B2b-malefic-scythe",
        "Malefic Scythe",
        _exact(
            "Whenever equipped creature dies, put a soul counter on this Equipment."
        ),
        _build_malefic_scythe,
    ),
    _template(
        "B2b-wildwood-scorge",
        "Wildwood Scourge",
        _exact(
            "Whenever one or more +1/+1 counters are put on another "
            "non-Hydra creature you control, put a +1/+1 counter on this creature."
        ),
        _build_wildwood_scorge,
    ),
    _template(
        "B2b-falconer-adept",
        "Falconer Adept",
        _exact(
            "Whenever this creature attacks, create a 1/1 white Bird "
            "creature token with flying that's tapped and attacking."
        ),
        _build_falconer_adept,
    ),
    _template(
        "B2b-library-larcenist",
        "Library Larcenist",
        _exact("Whenever this creature attacks, draw a card."),
        _build_library_larcenist,
    ),
    _template(
        "B2b-alpine-houndmaster-attack",
        "Alpine Houndmaster Attack",
        re.compile(
            r"Whenever this creature attacks, it gets \+X/\+(\d+) "
            r"until end of turn, where X is the number of other attacking creatures\."
        ),
        _build_alpine_houndmaster_attack,
    ),
    _template(
        "B2b-bolt-hound",
        "Bolt Hound",
        re.compile(
            r"Whenever this creature attacks, other creatures you control "
            r"get \+(\d+)/\+(\d+) until end of turn\."
        ),
        _build_bolt_hound,
    ),
    _template(
        "B2b-spined-megalodon",
        "Spined Megalodon",
        re.compile(r"Whenever this creature attacks, scry (\d+)\."),
        _build_spined_megalodon,
    ),
    _template(
        "B2b-siege-striker",
        "Siege Striker",
        _exact(
            "Whenever this creature attacks, you may tap any number "
            "of untapped creatures you control."
        ),
        _build_siege_striker,
    ),
    _template(
        "B2b-brash-taunter",
        "Brash Taunter",
        _exact(
            "Whenever this creature is dealt damage, "
            "it deals that much damage to target opponent."
        ),
        _build_brash_taunter,
    ),
    _template(
        "B2b-sporeweb-weaver",
        "Sporeweb Weaver",
        re.compile(
            r"Whenever this creature is dealt damage, "
            r"you gain (\d+) life and create a (\d+)/(\d+) "
            r"green Saproling creature token\."
        ),
        _build_sporeweb_weaver,
    ),
    _template(
        "B2b-basris-lieutenant",
        "Basri's Lieutenant",
        re.compile(
            r"Whenever this creature or another creature you control dies, "
            r"if it had a \+(?P<cn>\d+)/\+(?P=cn) counter on it, "
            r"create a (?P<tp>\d+)/(?P<tt>\d+) "
            r"white Knight creature token with vigilance\."
        ),
        _build_basris_lieutenant,
    ),
    _template(
        "B2b-named-card-search",
        "Named Card Search ETB",
        re.compile(
            r"When this creature enters, you may search your library and/or graveyard "
            r"for a card named (?P<name>.+?), reveal it, and put it into your hand\."
        ),
        _build_named_card_search_etb,
    ),
    _template(
        "B2b-nine-lives-leave",
        "Nine Lives Leave",
        _exact("When this enchantment leaves the battlefield, you lose the game."),
        _build_nine_lives_leave,
    ),
    _template(
        "B2b-power-ge-enters-draw",
        "Power N+ Enters Draw",
        re.compile(
            r"Whenever a creature you control with power (\d+) or greater enters, draw a card\."
        ),
        _build_garruks_uprising_power_enter,
    ),
    _template(
        "B2b-opponent-second-spell-draw",
        "Opponent Second Spell Draw",
        _exact("Whenever an opponent casts their second spell each turn, draw a card."),
        _build_mangara_second_spell,
    ),
    _template(
        "B2b-other-enters-power-damage",
        "Other Enters Power Damage",
        _exact(
            "Whenever another creature you control enters, this creature deals damage "
            "equal to that creature's power to any target."
        ),
        _build_terror_of_peaks_other_enter,
    ),
    _template(
        "B2b-flying-enters-self-boost",
        "Flying Enters Self Boost",
        re.compile(
            r"Whenever another creature you control with flying enters, "
            r"this creature gets \+(\d+)/\+(\d+) until end of turn\."
        ),
        _build_watcher_spheres_flying_enter,
    ),
    _template(
        "B2b-untapped-pay",
        "Untapped Pay",
        re.compile(r"Whenever this creature becomes untapped, you may pay \{(\d+)\}\."),
        _build_ghostly_pilferer_untapped,
    ),
    _template(
        "B2b-other-rogue-enters-mill",
        "Other Rogue Enters Mill",
        _exact(
            "Whenever this creature or another Rogue you control enters, "
            "each opponent mills two cards."
        ),
        _build_thieves_guild_enforcer,
    ),
    _template(
        "B2b-cast-cat-create-dog",
        "Cast Cat Create Dog",
        re.compile(
            r"Whenever you cast a Cat spell, create a (?P<p>\d+)/(?P<t>\d+) "
            r"(white|green) (?P<tok>Dog|Cat) creature token\."
        ),
        _cast_subtype_token_builder("Cat"),
    ),
    _template(
        "B2b-cast-dog-create-cat",
        "Cast Dog Create Cat",
        re.compile(
            r"Whenever you cast a Dog spell, create a (?P<p>\d+)/(?P<t>\d+) "
            r"(white|green) (?P<tok>Dog|Cat) creature token\."
        ),
        _cast_subtype_token_builder("Dog"),
    ),
    _template(
        "B2b-noncreature-counter",
        "Noncreature Cast Counter",
        re.compile(
            r"Whenever you cast a noncreature spell, "
            r"put a \+(\d+)/\+(\d+) counter on this creature\."
        ),
        _build_spellgorger_weird_counter,
    ),
    _template(
        "B2b-riddleform",
        "Riddleform",
        re.compile(
            r"Whenever you cast a noncreature spell, you may have this enchantment "
            r"become a (\d+)/(\d+) Sphinx creature with flying in addition to "
            r"its other types until end of turn\."
        ),
        _build_riddleform,
    ),
    _template(
        "B2b-colored-cast-counter",
        "Colored Cast Counter",
        _exact(
            "Whenever you cast a spell that's white, blue, black, or red, "
            "put a +1/+1 counter on this creature."
        ),
        _build_quirion_dryad_colored,
    ),
    _template(
        "B2b-draw-counter",
        "Draw Counter",
        re.compile(
            r"Whenever you draw a card, put a \+(\d+)/\+(\d+) counter on this creature\."
        ),
        _build_lorescale_coatl_draw_counter,
    ),
    _template(
        "B2b-draw-target-mill",
        "Draw Target Mill",
        _exact("Whenever you draw a card, target opponent mills two cards."),
        _build_teferis_tutelage_draw_mill,
    ),
    _template(
        "B2b-draw-self-boost",
        "Draw Self Boost",
        re.compile(
            r"Whenever you draw a card, this creature gets \+(\d+)/\+(\d+) until end of turn\."
        ),
        _build_burlfist_oak_draw_boost,
    ),
    _template(
        "B2b-draw-pay",
        "Draw Pay",
        re.compile(r"Whenever you draw a card, you may pay \{(\d+)\}\."),
        _build_tolarian_kraken_draw_pay,
    ),
    _template(
        "B2b-sacrifice-any-damage",
        "Sacrifice Any Damage",
        re.compile(
            r"Whenever you sacrifice a permanent, this creature deals (\d+) damage to any target\."
        ),
        _build_havoc_jester_sacrifice,
    ),
    _template(
        "B2b-etb-basic-land",
        "ETB Basic Land Search",
        _exact(
            "When this creature enters, you may search your library "
            "for a basic land card, put that card onto the battlefield tapped, "
            "then shuffle."
        ),
        _build_solemn_simulacrum_etb,
    ),
    _template(
        "B2b-etb-power-condition-draw",
        "ETB Power Condition Draw",
        re.compile(
            r"When this enchantment enters, if you control a creature with power "
            r"(\d+) or greater, draw a card\."
        ),
        _build_garruks_uprising_etb_condition,
    ),
    _template(
        "B2b-attack-teferi-condition-draw",
        "Attack Teferi Condition Draw",
        _exact(
            "Whenever this creature attacks, if you control a Teferi planeswalker, draw a card."
        ),
        _build_historian_teferi_condition,
    ),
    _template(
        "B2b-attack-power-condition-self-boost",
        "Attack Power Condition Self Boost",
        re.compile(
            r"Whenever this creature attacks, if you control a creature with power "
            r"(\d+) or greater, this creature gets \+(\d+)/\+(\d+) until end of turn\."
        ),
        _build_ornery_power_condition_self_boost,
    ),
    _template(
        "B2b-attack-two-flying-draw",
        "Attack Two Flying Draw",
        _exact(
            "Whenever you attack with two or more creatures with flying, draw a card."
        ),
        _build_tide_skimmer_two_flying,
    ),
    _template(
        "B2b-gain-life-target-opponent",
        "Gain Life Target Opponent",
        _exact("Whenever you gain life, target opponent loses that much life."),
        _build_vito_gain_life_lose_life,
    ),
    _template(
        "B2b-warden-of-the-woods",
        "Warden of the Woods",
        _exact(
            "Whenever this creature becomes the target of a spell or ability an "
            "opponent controls, you may draw two cards."
        ),
        _build_warden_of_the_woods,
    ),
    _template(
        "B2b-jeskai-elder",
        "Jeskai Elder",
        _exact(
            "Whenever this creature deals combat damage to a player, you may "
            "draw a card."
        ),
        _build_jeskai_elder,
    ),
    _template(
        "B2b-chandras-incinerator",
        "Chandra's Incinerator",
        _exact(
            "Whenever a source you control deals noncombat damage to an "
            "opponent, this creature deals that much damage to target "
            "creature or planeswalker that player controls."
        ),
        _build_chandras_incinerator,
    ),
    _template(
        "B2b-chandras-pyreling",
        "Chandra's Pyreling",
        re.compile(
            r"^Whenever a source you control deals noncombat damage to an "
            r"opponent, this creature gets \+(\d+)/\+(\d+) and gains double "
            r"strike until end of turn\.$"
        ),
        _build_chandras_pyreling,
    ),
    _template(
        "B2b-pack-leader",
        "Pack Leader",
        _exact(
            "Whenever this creature attacks, prevent all combat damage that "
            "would be dealt this turn to Dogs you control."
        ),
        _build_pack_leader,
    ),
    _template(
        "B2b-gloom-sower",
        "Gloom Sower",
        re.compile(
            r"^Whenever this creature becomes blocked by a creature, that "
            r"creature's controller loses (\d+) life and you gain \1 life\.$"
        ),
        _build_gloom_sower,
    ),
    _template(
        "B2b-hooded-blightfang-pw",
        "Hooded Blightfang Planeswalker",
        _exact(
            "Whenever a creature you control with deathtouch deals damage to "
            "a planeswalker, destroy that planeswalker."
        ),
        _build_hooded_blightfang_planeswalker,
    ),
    _template(
        "B2b-feline-sovereign",
        "Feline Sovereign",
        _exact(
            "Whenever one or more Cats you control deal combat damage to a "
            "player, destroy up to one target artifact or enchantment that "
            "player controls."
        ),
        _build_feline_sovereign,
    ),
    _template(
        "B2b-ghostly-pilferer-cast",
        "Ghostly Pilferer Cast",
        _exact(
            "Whenever an opponent casts a spell from anywhere other than "
            "their hand, draw a card."
        ),
        _build_ghostly_pilferer_cast,
    ),
    _template(
        "B2b-double-vision-copy",
        "Double Vision Copy",
        _exact(
            "Whenever you cast your first instant or sorcery spell each "
            "turn, copy that spell."
        ),
        _build_double_vision_copy,
    ),
    _template(
        "B2b-double-vision-new-targets",
        "Double Vision New Targets",
        _exact("You may choose new targets for the copy."),
        _build_double_vision_new_targets,
    ),
    _template(
        "B2b-garruks-harbinger",
        "Garruk's Harbinger",
        _exact(
            "Whenever this creature deals combat damage to a player or "
            "planeswalker, look at that many cards from the top of your "
            "library."
        ),
        _build_garruks_harbinger,
    ),
    _template(
        "B2b-jolrael-cat-token",
        "Jolrael Cat Token",
        re.compile(
            r"^Whenever you draw your second card each turn, create a "
            r"(\d+)/(\d+) green Cat creature token\.$"
        ),
        _build_jolrael_cat_token,
    ),
    _template(
        "B2b-mystic-skyfish",
        "Mystic Skyfish",
        _exact(
            "Whenever you draw your second card each turn, this creature "
            "gains flying until end of turn."
        ),
        _build_mystic_skyfish,
    ),
    _template(
        "B2b-keral-keep-disciples",
        "Keral Keep Disciples",
        _exact(
            "Whenever you activate a loyalty ability of a Chandra "
            "planeswalker, this creature deals 1 damage to each opponent."
        ),
        _build_keral_keep_disciples,
    ),
    _template(
        "B2b-blocks-flying-pump",
        "Snarespinner",
        re.compile(
            r"^Whenever this creature blocks a creature with flying, this "
            r"creature gets \+(\d+)/\+0 until end of turn\.$"
        ),
        _build_blocks_flying_pump,
    ),
    _template(
        "B2b-do-tap-or-untap",
        "Kraken Do Tap Or Untap",
        _exact("When you do, you may tap or untap target creature."),
        _build_kraken_do_tap_or_untap,
    ),
    _template(
        "B2b-attackers-against-me-draw",
        "Mangara, the Diplomat",
        re.compile(
            r"^Whenever an opponent attacks with creatures, if two or "
            r"more of those creatures are attacking you and/or "
            r"planeswalkers you control, draw a card\.$"
        ),
        _build_mangara_attackers_draw,
    ),
)


# ---------------------------------------------------------------------------
# Uncovered shapes
# ---------------------------------------------------------------------------

UNCOVERED: Final[tuple[tuple[str, str], ...]] = (
    (
        "Whenever this creature attacks or blocks, choose one —",
        (
            "handled by the compiler's choose-opener built-in; "
            "two TriggeredAbilities share one Choose"
        ),
    ),
)
