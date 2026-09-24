"""B2b bucket templates — 42 templates covering 44 of 62 B2b normalized shape keys.

Bucket input: ``/tmp/opencode/phase1_buckets/B2b.json`` (62 normalized shape
keys → ``[card, sentence]`` pairs; 76 card/sentence entries).  Templates
fullmatch the **concrete** oracle sentence, never the normalized key.

Coverage (62 shapes = 44 template-covered + 18 uncovered):

- **42 templates** cover 44 normalized keys and 58 concrete rows.
  - *Round 1* (18 templates): 18 shapes and 32 concrete rows.  Shape ``#10``
    has 5 concrete rows and ``#11`` has 11; all other covered shapes have 1
    each.
  - *Round 2* (18 templates → 20 shapes): 20 shapes and 20 concrete rows.  The
    three named-card-search shapes (``#1``/``#2``/``#3``) share one parameterized
    template, so 18 templates cover 20 shapes.
  - *Round 4* (6 templates): 6 shapes and 6 concrete rows, each a single-card
    shape (Solemn Simulacrum, Garruk's Uprising, Historian of Zhalfir,
    Ornery Dilophosaur, Tide Skimmer, Vito).
- **18 uncovered normalized keys** have no grammar construct and are recorded
  in ``UNCOVERED``.

Conventions (documented build decisions):

- ``When this ... enters`` uses ``ZoneChangeEvent(ANY → BATTLEFIELD YOU)``.
  Round 2 additionally sets the event ``subject`` filter to restrict the
  entering permanent (e.g. a creature you control with a given power or
  keyword); the grammar cannot otherwise restrict the ETB subject.
- ``you may`` drives ``OptionalEffect``.
- ``target`` drives ``SelectorMode.TARGET``.
- ``another`` / ``other`` adds ``FNot(inner=FAtom(IS_SOURCE))``.
- ``any target`` is ``Selector(QConst(1), TARGET, universal filter, ANY zone)``.
- ``X is the number of other attacking creatures`` is a ``QCount`` over a
  selector for other attacking creatures on the battlefield.
- Token colors are dropped: ``TokenSpec`` has no color field.
- ``REVEAL`` after ``SEARCH`` cannot reference the searched cards; it reveals
  an unbounded count of cards from the controller's perspective.
- ``+N/+N`` on a token and counter can differ (e.g. +1/+1 counter, 2/2 token);
  each is captured by its own regex group.
- A captured ``+N/+N`` counter on a source is validated by ``_plus1_counter``
  to be exactly ``+1/+1`` (keys #51/#55); an exact ``+1/+1`` sentence uses
  ``QConst(1)`` directly (key #53).
- ``you may pay {N}`` is ``Verb.PAY`` with ``Cost(parts=(CostManaGeneric(N),))``.
- ``each opponent`` for life gain/loss uses ``ControllerRef.ALL_OPPONENTS``; an
  ``EachPlayer`` effect runs relative to the iterated (opponent) player.
- ``CastSpellEvent.from_zone`` exists but is a single ``Zone`` (not a
  ``Filter``), so "anywhere other than their hand" is not expressible.
- ``CardDrawnEvent`` has no ordinal field, so "second card each turn" is not
  expressible.

PC-3: every B2b concrete sentence fullmatches **at most one** template
(patterns are pairwise disjoint by construction; the three named-card-search
sentences share one template and match only it); verified in tests.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardDrawnEvent,
    CastSpellEvent,
    ControllerRef,
    Cost,
    CostManaGeneric,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
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
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    SentenceOutcome,
    Template,
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


def _ability(event, effect, condition=None) -> AbilityOutcome:
    """Wrap a triggered-ability effect as the B2b sentence outcome."""
    return AbilityOutcome(
        ability=TriggeredAbility(event=event, condition=condition, effect=effect)
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
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )


def _creatures_you_control() -> Selector:
    """Selector for ``creatures you control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
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
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
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
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
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
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
    )


def _any_card_in_your_hand() -> Selector:
    """Selector for ``a card`` in your hand (universal filter)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        Zone(ZoneKind.HAND, ControllerRef.YOU),
    )


def _target_opponent() -> Selector:
    """Selector for ``target opponent``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(children=()),
        Zone(ZoneKind.PLAYER, ControllerRef.TARGET_PLAYER),
    )


def _any_target() -> Selector:
    """Selector for ``any target`` (single target, universal filter, any zone)."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(children=()),
        Zone(ZoneKind.ANY, ControllerRef.ANY),
    )


def _etb_event() -> ZoneChangeEvent:
    """Zone-change event for ``When this ... enters``."""
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
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


def _bird_token(power: int, toughness: int) -> TokenSpec:
    # GAP: token color omitted — TokenSpec has no color field.
    return TokenSpec(
        name="Bird",
        type_line="Creature — Bird",
        types=("Creature",),
        subtypes=("Bird",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(Keyword.FLYING,),
        abilities=(),
    )


def _knight_token(power: int, toughness: int) -> TokenSpec:
    # GAP: token color omitted — TokenSpec has no color field.
    return TokenSpec(
        name="Knight",
        type_line="Creature — Knight",
        types=("Creature",),
        subtypes=("Knight",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(Keyword.VIGILANCE,),
        abilities=(),
    )


def _saproling_token(power: int, toughness: int) -> TokenSpec:
    # GAP: token color omitted — TokenSpec has no color field.
    return TokenSpec(
        name="Saproling",
        type_line="Creature — Saproling",
        types=("Creature",),
        subtypes=("Saproling",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(),
        abilities=(),
    )


# ---------------------------------------------------------------------------
# Builders — ETB search / draw / scry / life shapes
# ---------------------------------------------------------------------------


def _build_alpine_houndmaster_etb(m: re.Match[str]) -> SentenceOutcome:
    """#5: search for named Alpine Watchdog and/or Igneous Cur, reveal, hand, shuffle."""
    return _ability(
        _etb_event(),
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
                                        QConst(2),
                                        SelectorMode.CHOOSE,
                                        FOr(
                                            children=(
                                                FAtom(
                                                    pred=FAtomPred.NAME_EQ,
                                                    string_value="Alpine Watchdog",
                                                ),
                                                FAtom(
                                                    pred=FAtomPred.NAME_EQ,
                                                    string_value="Igneous Cur",
                                                ),
                                            )
                                        ),
                                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
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
    """#6: search for creature with mana value N+, reveal, hand, shuffle."""
    n = _n(m, 1)
    return _ability(
        _etb_event(),
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
                                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
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
    """#7: draw a card, then discard a card."""
    return _ability(
        _etb_event(),
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
                    verb=Verb.DISCARD,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("cards", _any_card_in_your_hand()),
                        )
                    ),
                ),
            )
        ),
    )


def _build_temple_etb_scry(m: re.Match[str]) -> SentenceOutcome:
    """#10: scry N when this land enters."""
    n = _n(m, 1)
    return _ability(
        _etb_event(),
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
    """#11: gain N life when this land enters."""
    n = _n(m, 1)
    return _ability(
        _etb_event(),
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
    """#13: opponent creature dies, that player loses N life."""
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
    """#14: creature with deathtouch attacks, each opponent loses N, you gain N."""
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
    """#24: equipped creature dies, put soul counter on this Equipment."""
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
    """#25: +1/+1 counters on another non-Hydra creature you control, put +1/+1 on this."""
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
    """#28: create 1/1 white Bird with flying, tapped and attacking."""
    # GAP: token color omitted; tapped/attacking token state omitted.
    return _ability(
        _attack_event(),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    ("tokens", _bird_token(1, 1)),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


def _build_library_larcenist(m: re.Match[str]) -> SentenceOutcome:
    """#29: draw a card when this creature attacks."""
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
    """#32: gets +X/+N until eot, X = number of other attacking creatures."""
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
    """#33: other creatures you control get +N/+N until eot."""
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
    """#35: scry N when this creature attacks."""
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
    """#36: you may tap any number of untapped creatures you control."""
    return _ability(
        _attack_event(),
        OptionalEffect(
            inner=Atom(
                verb=Verb.TAP,
                args=AtomArgs(pairs=(("target", _untapped_creatures_you_control()),)),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Builders — damage-dealt shapes
# ---------------------------------------------------------------------------


def _build_brash_taunter(m: re.Match[str]) -> SentenceOutcome:
    """#43: dealt damage, deals that much damage to target opponent."""
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
    """#44: dealt damage, gain N life and create N/N green Saproling token."""
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
    """#46: creature you control dies, if +N/+N counter, create N/N white Knight with vigilance."""
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
# Builders — Round 2 shapes
# ---------------------------------------------------------------------------


def _build_named_card_search_etb(m: re.Match[str]) -> SentenceOutcome:
    """#1/#2/#3: search library and/or graveyard for a named card, reveal, hand."""
    name = m.group("name")
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
                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                        zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),),
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
    move = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.IS_SOURCE),
                        Zone(
                            ZoneKind.LIBRARY,
                            ControllerRef.YOU,
                            position=ZonePosition.TOP,
                        ),
                    ),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    return _ability(
        _etb_event(),
        OptionalEffect(inner=Seq(steps=(search, reveal, move))),
    )


def _build_nine_lives_leave(m: re.Match[str]) -> SentenceOutcome:
    """#9: this enchantment leaves the battlefield, you lose the game."""
    return _ability(
        ZoneChangeEvent(
            from_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            to_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        ),
        Atom(verb=Verb.LOSE_GAME, args=AtomArgs()),
    )


def _build_garruks_uprising_power_enter(m: re.Match[str]) -> SentenceOutcome:
    """#16: a creature you control with power N+ enters, draw a card."""
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
    """#21: an opponent casts their second spell each turn, draw a card."""
    return _ability(
        CastSpellEvent(
            filter=FAnd(children=()),
            controller=ControllerRef.OPPONENT,
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
    """#22: another creature you control enters, deals its power to any target."""
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
    """#23: another creature you control with flying enters, gets +N/+N until eot."""
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
    """#39: this creature becomes untapped, you may pay {N}."""
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
    """#45: this creature or another Rogue you control enters, each opponent mills two."""
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
                verb=Verb.MILL,
                args=AtomArgs(
                    pairs=(("controller", ControllerRef.YOU), ("amount", QConst(2)))
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
        return _ability(
            CastSpellEvent(
                filter=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value=trigger_subtype),
                    )
                ),
                controller=ControllerRef.YOU,
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
                            ),
                        ),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )

    return build


def _build_spellgorger_weird_counter(m: re.Match[str]) -> SentenceOutcome:
    """#51: cast a noncreature spell, put a +1/+1 counter on this creature."""
    count = _plus1_counter(m)
    return _ability(
        CastSpellEvent(
            filter=FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")),
            controller=ControllerRef.YOU,
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
    """#52: cast a noncreature spell, this enchantment becomes an N/N Sphinx with flying."""
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
            Atom(
                verb=Verb.GRANT_TYPE,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("types", ("Sphinx",)),
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
            controller=ControllerRef.YOU,
        ),
        OptionalEffect(inner=seq),
    )


def _build_quirion_dryad_colored(m: re.Match[str]) -> SentenceOutcome:
    """#53: cast a W/U/B/R spell, put a +1/+1 counter on this creature."""
    return _ability(
        CastSpellEvent(
            filter=FAtom(pred=FAtomPred.COLOR_IN, colors=("W", "U", "B", "R")),
            controller=ControllerRef.YOU,
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
    """#55: draw a card, put a +1/+1 counter on this creature."""
    count = _plus1_counter(m)
    return _ability(
        CardDrawnEvent(controller=ControllerRef.YOU),
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
    """#56: draw a card, target opponent mills two cards."""
    return _ability(
        CardDrawnEvent(controller=ControllerRef.YOU),
        Atom(
            verb=Verb.MILL,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.TARGET_PLAYER),
                    ("amount", QConst(2)),
                )
            ),
        ),
    )


def _build_burlfist_oak_draw_boost(m: re.Match[str]) -> SentenceOutcome:
    """#57: draw a card, this creature gets +N/+N until eot."""
    p = _n(m, 1)
    t = _n(m, 2)
    return _ability(
        CardDrawnEvent(controller=ControllerRef.YOU),
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
    """#58: draw a card, you may pay {N}."""
    n = _n(m, 1)
    return _ability(
        CardDrawnEvent(controller=ControllerRef.YOU),
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
    """#62: sacrifice a permanent, this creature deals N damage to any target."""
    n = _n(m, 1)
    return _ability(
        SacrificeEvent(controller=ControllerRef.YOU),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(pairs=(("target", _any_target()), ("amount", QConst(n)))),
        ),
    )


# ---------------------------------------------------------------------------
# Builders — Round 4 shapes
# ---------------------------------------------------------------------------


def _build_solemn_simulacrum_etb(m: re.Match[str]) -> SentenceOutcome:
    """#4: search for a basic land, put it onto the battlefield tapped, shuffle."""
    return _ability(
        _etb_event(),
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
                                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
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
    """#8: ETB, if you control a creature with power N or greater, draw a card."""
    n = _n(m, 1)
    return _ability(
        _etb_event(),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(1)),
                )
            ),
        ),
        condition=_you_control_at_least(_creature_power_ge_filter(n), n),
    )


def _build_historian_teferi_condition(m: re.Match[str]) -> SentenceOutcome:
    """#30: attacks, if you control a Teferi planeswalker, draw a card."""
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
    """#31: attacks, if you control a creature with power N or greater,
    this creature gets +P/+T until end of turn."""
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
        condition=_you_control_at_least(_creature_power_ge_filter(n), n),
    )


def _build_tide_skimmer_two_flying(m: re.Match[str]) -> SentenceOutcome:
    """#48: you attack with two or more flying creatures, draw a card.

    Convention: DeclareAttackersEvent is per-creature; the set-level
    "two or more" requirement is carried by the trigger condition.
    """
    flying_attackers = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
        )
    )
    return _ability(
        DeclareAttackersEvent(filter=flying_attackers),
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
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
                    FAtom(pred=FAtomPred.IS_ATTACKING),
                )
            ),
            2,
        ),
    )


def _build_vito_gain_life_lose_life(m: re.Match[str]) -> SentenceOutcome:
    """#61: whenever you gain life, target opponent loses that much life."""
    return _ability(
        LifeGainedEvent(controller=ControllerRef.YOU),
        Atom(
            verb=Verb.LOSE_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.TARGET_PLAYER),
                    (
                        "amount",
                        QProp(referent="event", field=QPropField.AMOUNT),
                    ),
                )
            ),
        ),
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
)


# ---------------------------------------------------------------------------
# Uncovered shapes
# ---------------------------------------------------------------------------

UNCOVERED: Final[tuple[tuple[str, str], ...]] = (
    (
        "When you do, you may tap or untap target creature.",
        "Anaphoric 'When you do' has no expressible continuation trigger event.",
    ),
    (
        "Whenever a creature you control with deathtouch deals damage to a planeswalker, "
        "destroy that planeswalker.",
        "The effect 'destroy that planeswalker' needs a referent to the damaged "
        "object; the grammar exposes no damaged-object selector in the effect.",
    ),
    (
        "Whenever a source you control deals noncombat damage to an opponent, "
        "this creature deals that much damage to target creature or planeswalker "
        "that player controls.",
        "The effect 'that player controls' needs a referent to the damaged "
        "opponent; no damaged-opponent referent is exposed.",
    ),
    (
        "Whenever a source you control deals noncombat damage to an opponent, "
        "this creature gets +N/+N and gains double strike until end of turn.",
        "The damaged object 'an opponent' is not expressible as a "
        "DamageDealtEvent.filter (no opponent/player predicate); source/combat "
        "fields exist but the opponent filter is the blocker.",
    ),
    (
        "Whenever an opponent attacks with creatures, if two or more of those creatures "
        "are attacking you and/or planeswalkers you control, draw a card.",
        "Set-level 'two or more of those creatures' condition not expressible.",
    ),
    (
        "Whenever an opponent casts a spell from anywhere other than their hand, "
        "draw a card.",
        "CastSpellEvent.from_zone is a single Zone, not a Filter/negation, so "
        "'anywhere other than their hand' is not expressible.",
    ),
    (
        "Whenever one or more Cats you control deal combat damage to a player, "
        "destroy up to one target artifact or enchantment that player controls.",
        "CombatDamageEvent lacks source/recipient distinction.",
    ),
    (
        "Whenever this creature attacks or blocks, choose one —",
        "handled by the compiler's choose-opener built-in; "
        "two TriggeredAbilities share one Choose",
    ),
    (
        "Whenever this creature attacks, prevent all combat damage that would be dealt "
        "this turn to Dogs you control.",
        "No turn-scoped PREVENT_EFFECT; B4 precedent is static source-scoped only.",
    ),
    (
        "Whenever this creature becomes blocked by a creature, that creature's controller "
        "loses N life and you gain N life.",
        "BecomesBlockedEvent filter is over the blocker; blocker controller not referenceable.",
    ),
    (
        "Whenever this creature becomes the target of a spell or ability an opponent controls, "
        "you may draw two cards.",
        "TargetingEvent has no source-controller field.",
    ),
    (
        "Whenever this creature blocks a creature with flying, "
        "this creature gets +N/+N until end of turn.",
        "DeclareBlockersEvent filter is over the blocking creature only.",
    ),
    (
        "Whenever this creature deals combat damage to a player or planeswalker, "
        "look at that many cards from the top of your library.",
        "CombatDamageEvent lacks amount and recipient fields.",
    ),
    (
        "Whenever this creature deals combat damage to a player, you may draw a card.",
        "CombatDamageEvent lacks recipient field.",
    ),
    (
        "Whenever you activate a loyalty ability of a Chandra planeswalker, "
        "this creature deals N damage to each opponent.",
        "No loyalty-activation event.",
    ),
    (
        "Whenever you cast your first instant or sorcery spell each turn, copy that spell.",
        "The COPY effect needs the cast spell as an explicit selector, "
        "which CastSpellEvent does not expose.",
    ),
    (
        "Whenever you draw your second card each turn, create a N/N green Cat creature token.",
        "No ordinal per-turn draw event.",
    ),
    (
        "Whenever you draw your second card each turn, this creature gains flying until end of turn.",
        "No ordinal per-turn draw event.",
    ),
)
