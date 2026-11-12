"""B2a bucket templates: trigger-shaped sentences, the first alphabetical half of B2.

Bucket input: ``/tmp/opencode/phase1_buckets/B2a.json`` (normalized shape keys
→ ``[card, sentence]`` pairs). Templates fullmatch the **concrete** oracle
sentence, never the normalized key. Keys no template covers are listed in
``UNCOVERED``.

Conventions:

- ``this creature`` / ``this Aura`` / ``this artifact`` / ``this
  enchantment`` self-referent targets are encoded as
  ``Selector(CHOOSE, QConst(1), FAtom(IS_SOURCE), zone)`` — a semantic
  self-reference, never a hardcoded card name.
- ``up to N target(s) ...`` uses ``SelectorMode.TARGET`` with ``QAtMost(N)``:
  a targeted "up to N" designates 1..N and resolves 0..N (a resolution-time
  "up to" stays CHOOSE). The word ``target`` drives target mode, while
  ``you may`` alone drives ``OptionalEffect``.
- ``another`` / ``other`` adds ``FNot(inner=FAtom(IS_SOURCE))``.
- ``X is the number of Shrines you control`` is a ``QCount`` over
  ``TYPE_EQ("Shrine")`` permanents you control: "Shrine" is a type-line word.
  ``NAME_EQ`` tests card names and would match no card.
- Token color words populate ``TokenSpec.colors``, a WUBRG tuple;
  ``Treasure`` artifact tokens stay colorless, ``()``.
- ``add X mana of any one color`` is encoded as ``ADD_MANA(color="ANY")``;
  concrete-color and colorless "{C}" rows keep their letter.
- ``each opponent`` for life gain/loss uses ``ControllerRef.ALL_OPPONENTS``;
  for damage targets it uses a ``Selector`` over ``Zone(PLAYER, OPPONENT)``.
- Quoted token text (``"This token can't block"``) is hand-built as IR in
  ``TokenSpec.abilities``, never carried as strings.

Every B2a concrete sentence fullmatches **at most one** template (the
patterns are pairwise disjoint); the tests check it.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    Choose,
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    CostSacrifice,
    CostTap,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DeclareBlockersEvent,
    DurationEot,
    DurationUntilLeaves,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    Phase,
    PtDelta,
    PtDirection,
    QAgg,
    QAtMost,
    QBin,
    QBinOp,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TokenSpec,
    TriggeredAbility,
    TurnPhaseEvent,
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
    and_or_zone_search,
)

_BUCKET: Final[str] = "B2a"
_PRIORITY: Final[int] = 50


# ---------------------------------------------------------------------------
# Shared node builders
# ---------------------------------------------------------------------------


def _n(m: re.Match[str], group: int) -> int:
    """Convert a numeric regex capture group to ``int``."""
    return int(m.group(group))


def _self_selector() -> Selector:
    """Selector for ``this <permanent>`` — the source of the ability."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
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
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _creatures_opponents_control() -> Selector:
    """Selector for ``creatures your opponents control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _creatures_died_this_turn(
    controlled_by: ControllerRef | None = None,
    *,
    nontoken: bool = False,
) -> Selector:
    """Selector for creatures that died this turn.

    ``controlled_by=ControllerRef.YOU`` encodes "under your control";
    ``nontoken=True`` encodes "nontoken".
    """
    children: list[Filter] = [
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
    ]
    if controlled_by is not None:
        children.append(FAtom(pred=FAtomPred.CONTROLLER_IS, who=controlled_by))
    if nontoken:
        children.append(FNot(inner=FAtom(pred=FAtomPred.IS_TOKEN)))
    children.append(FAtom(pred=FAtomPred.DIED_THIS_TURN))
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(children=tuple(children)),
        zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),),
    )


def _shrine_count() -> QCount:
    """``X`` for "where X is the number of Shrines you control".

    ``TYPE_EQ("Shrine")``, not ``NAME_EQ``: "Shrine" is a word of the printed
    type line ("Legendary Enchantment — Shrine"), which the executor's type
    word test reads. NAME_EQ tests card names, and no card is named "Shrine".
    """
    return QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Shrine"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
        )
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


def _target_creature() -> Selector:
    """Selector for ``target creature``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _opponent_players() -> Selector:
    """Selector for ``each opponent`` as damage targets."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(children=()),
        zones=(Zone(ZoneKind.PLAYER, ControllerRef.OPPONENT),),
    )


def _etb_event(subject: Filter) -> ZoneChangeEvent:
    """Zone-change event for ``When this ... enters``.

    ``subject`` is the object whose entering fires the trigger. Every b2a
    caller reads ``When <this permanent> enters`` and passes
    ``FAtom(pred=FAtomPred.IS_SOURCE)``. A ``When a <class> enters`` pattern
    would pass the class filter instead (as b2b's Garruk's Uprising does),
    never ``None``.
    """
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        subject=subject,
    )


def _combat_event() -> TurnPhaseEvent:
    """Turn-phase event for ``At the beginning of combat on your turn``."""
    return TurnPhaseEvent(
        phase=Phase.COMBAT,
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )


def _end_step_event() -> TurnPhaseEvent:
    """Turn-phase event for ``At the beginning of your end step``."""
    return TurnPhaseEvent(
        phase=Phase.END_TURN,
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )


def _first_main_event() -> TurnPhaseEvent:
    """Turn-phase event for ``At the beginning of your first main phase``."""
    return TurnPhaseEvent(
        phase=Phase.FIRST_MAIN,
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )


def _upkeep_event() -> TurnPhaseEvent:
    """Turn-phase event for ``At the beginning of your upkeep``."""
    return TurnPhaseEvent(
        phase=Phase.UPKEEP,
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )


def _dies_event() -> CreatureDiesEvent:
    """Creature-dies event for ``When this creature dies``."""
    return CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE))


def _life_gained_this_turn_ge(threshold: int) -> FAtom:
    """Filter for ``if you gained N or more life this turn``: ``count`` is
    the threshold, ``who`` the player whose life gain is counted."""
    return FAtom(
        pred=FAtomPred.LIFE_GAINED_THIS_TURN_GE,
        count=QConst(threshold),
        who=ControllerRef.YOU,
    )


def _soldier_token(power: int, toughness: int) -> TokenSpec:
    return TokenSpec(
        name="Soldier",
        type_line="Creature — Soldier",
        types=("Creature",),
        subtypes=("Soldier",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(),
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


def _griffin_token(power: int, toughness: int) -> TokenSpec:
    return TokenSpec(
        name="Griffin",
        type_line="Creature — Griffin",
        types=("Creature",),
        subtypes=("Griffin",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(Keyword.FLYING,),
        abilities=(),
        colors=("W",),
    )


def _treasure_token() -> TokenSpec:
    """Treasure artifact token (Gadrak, the Crown-Scourge).

    The printed parenthetical "(Tap it, sacrifice it: Add one mana of any
    color.)" is rules text, not reminder text, so it is a real
    ``ActivatedAbility`` in ``TokenSpec.abilities``."""
    return TokenSpec(
        name="Treasure",
        type_line="Artifact",
        types=("Artifact",),
        subtypes=(),
        power=None,
        toughness=None,
        keywords=(Keyword.TREASURE,),
        abilities=(
            ActivatedAbility(
                cost=Cost(
                    parts=(
                        CostTap(),
                        CostSacrifice(target=_self_selector()),
                    )
                ),
                effect=Atom(
                    verb=Verb.ADD_MANA,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("amount", QConst(1)),
                            ("color", "ANY"),
                        )
                    ),
                ),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Template plumbing
# ---------------------------------------------------------------------------


def _exact(sentence: str) -> re.Pattern[str]:
    """Compile an exact-sentence fullmatch pattern."""
    return re.compile(re.escape(sentence))


def _ability(event, effect, condition=None) -> AbilityOutcome:
    """Wrap a triggered-ability effect as the B2a sentence outcome."""
    return AbilityOutcome(
        ability=TriggeredAbility(event=event, condition=condition, effect=effect)
    )


def _template(tid, name, pattern, build) -> Template:
    """Build a B2a ``Template`` with the bucket's fixed priority."""
    return Template(
        tid=tid,
        name=name,
        bucket=_BUCKET,
        pattern=pattern,
        priority=_PRIORITY,
        build=build,
    )


# ---------------------------------------------------------------------------
# Builders — combat and end-step / first-main Shrine shapes
# ---------------------------------------------------------------------------


def _build_basri_ket(m: re.Match[str]) -> SentenceOutcome:
    power, toughness = _n(m, 1), _n(m, 2)
    counter_p, counter_t = _n(m, 3), _n(m, 4)
    if (counter_p, counter_t) != (1, 1):
        raise ValueError(
            "B2a-basri-ket-emblem expects a +1/+1 counter, "
            f"got +{counter_p}/+{counter_t}"
        )
    return _ability(
        _combat_event(),
        Seq(
            steps=(
                Atom(
                    verb=Verb.CREATE_TOKEN,
                    args=AtomArgs(
                        pairs=(
                            ("tokens", _soldier_token(power, toughness)),
                            ("count", QConst(1)),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.PUT_COUNTER,
                    args=AtomArgs(
                        pairs=(
                            ("target", _creatures_you_control()),
                            (
                                "counter_kind",
                                CounterKind.PLUS_1_PLUS_1,
                            ),
                            ("count", QConst(1)),
                        )
                    ),
                ),
            )
        ),
    )


def _build_liliana_waker(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _combat_event(),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    (
                        "cards",
                        Selector(
                            QConst(1),
                            SelectorMode.TARGET,
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                            zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),),
                        ),
                    ),
                    (
                        "destination",
                        Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                    ),
                )
            ),
        ),
    )


def _build_battle_rattle_shaman(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _combat_event(),
        OptionalEffect(
            inner=Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _target_creature()),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(_n(m, 1))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(_n(m, 2))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            )
        ),
    )


def _build_dire_fleet_warmonger(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _combat_event(),
        OptionalEffect(
            inner=Atom(
                verb=Verb.SACRIFICE,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
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
                                            pred=FAtomPred.CONTROLLER_IS,
                                            who=ControllerRef.YOU,
                                        ),
                                        FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                                    )
                                ),
                                zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                            ),
                        ),
                    )
                ),
            )
        ),
    )


def _build_gadrak_treasures(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _end_step_event(),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    ("tokens", _treasure_token()),
                    (
                        "count",
                        QCount(_creatures_died_this_turn(nontoken=True)),
                    ),
                )
            ),
        ),
    )


def _build_twinblade_assassins(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _end_step_event(),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        ),
        condition=FAtom(pred=FAtomPred.DIED_THIS_TURN),
    )


def _build_sabertooth_mauler(m: re.Match[str]) -> SentenceOutcome:
    counter_p, counter_t = _n(m, 1), _n(m, 2)
    if (counter_p, counter_t) != (1, 1):
        raise ValueError(
            "B2a-sabertooth-mauler expects a +1/+1 counter, "
            f"got +{counter_p}/+{counter_t}"
        )
    return _ability(
        _end_step_event(),
        Seq(
            steps=(
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
                Atom(
                    verb=Verb.UNTAP,
                    args=AtomArgs(pairs=(("target", _self_selector()),)),
                ),
            )
        ),
        condition=FAtom(pred=FAtomPred.DIED_THIS_TURN),
    )


def _build_garruk_emblem(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _end_step_event(),
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
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ,
                                            string_value="Creature",
                                        ),
                                        zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
                                    ),
                                ),
                                (
                                    "destination",
                                    Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                                ),
                                ("controller", ControllerRef.YOU),
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


def _build_sanctum_fruitful_harvest(m: re.Match[str]) -> SentenceOutcome:
    # "mana of any one color" is color="ANY", a choice, not colorless "C".
    return _ability(
        _first_main_event(),
        Atom(
            verb=Verb.ADD_MANA,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", _shrine_count()),
                    ("color", "ANY"),
                )
            ),
        ),
    )


def _build_sanctum_stone_fangs(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _first_main_event(),
        Seq(
            steps=(
                Atom(
                    verb=Verb.LOSE_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.ALL_OPPONENTS),
                            ("amount", _shrine_count()),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.GAIN_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("amount", _shrine_count()),
                        )
                    ),
                ),
            )
        ),
    )


def _build_sanctum_calm_waters(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _first_main_event(),
        OptionalEffect(
            inner=Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", _shrine_count()),
                    )
                ),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Builders — named ETB, counter threshold, Aura, artifact, and dies shapes
# ---------------------------------------------------------------------------


def _build_barrin_etb(m: re.Match[str]) -> SentenceOutcome:
    """Barrin ETB: "return up to one other target creature or planeswalker
    to its owner's hand" — TARGET + QAtMost(1) (targeted "up to N").

    "to its owner's hand" is Zone(HAND, OWNER) (CR 400.3: a card goes to its
    owner's hand), like every other owner's-hand return."""
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    (
                        "cards",
                        Selector(
                            QAtMost(1),
                            SelectorMode.TARGET,
                            FAnd(
                                children=(
                                    FOr(
                                        children=(
                                            FAtom(
                                                pred=FAtomPred.TYPE_EQ,
                                                string_value="Creature",
                                            ),
                                            FAtom(
                                                pred=FAtomPred.TYPE_EQ,
                                                string_value="Planeswalker",
                                            ),
                                        )
                                    ),
                                    FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                                )
                            ),
                            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                        ),
                    ),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.OWNER)),
                )
            ),
        ),
    )


def _build_niambi_etb(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        OptionalEffect(
            inner=Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAnd(
                                    children=(
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ,
                                            string_value="Creature",
                                        ),
                                        FAtom(
                                            pred=FAtomPred.CONTROLLER_IS,
                                            who=ControllerRef.YOU,
                                        ),
                                        FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                                    )
                                ),
                                zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                            ),
                        ),
                        ("destination", Zone(ZoneKind.HAND, ControllerRef.OWNER)),
                    )
                ),
            )
        ),
    )


def _exile_at_counters(kind: CounterKind, n: int) -> SentenceOutcome:
    """"When there are N or more <kind> counters on this <permanent>, exile it." (Mazemind
    Tome, Nine Lives): a state trigger (CR 603.8), read as the counters are placed. The
    threshold is part of the trigger event, so it is in the event's filter: it is not an
    intervening "if" (CR 603.4) and is not read again as the ability resolves."""
    return _ability(
        CounterPlacedEvent(
            counter_kind=kind,
            filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.IS_SOURCE),
                    FAtom(pred=FAtomPred.HAS_COUNTER, counter_kind=kind, count=QConst(n)),
                )
            ),
        ),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                    ("target", _self_selector()),
                )
            ),
        ),
    )


def _build_mazemind_tome(m: re.Match[str]) -> SentenceOutcome:
    return _exile_at_counters(CounterKind.PAGE, 4)


def _build_nine_lives(m: re.Match[str]) -> SentenceOutcome:
    return _exile_at_counters(CounterKind.INCARNATION, 9)


def _build_setessan_training(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        ),
    )


def _build_rousing_read(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Seq(
            steps=(
                Atom(
                    verb=Verb.DRAW,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("amount", QConst(2)),
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
                            (
                                "cards",
                                Selector(
                                    QConst(1),
                                    SelectorMode.CHOOSE,
                                    FAnd(children=()),
                                    zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                                ),
                            ),
                        )
                    ),
                ),
            )
        ),
    )


def _build_capture_sphere(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.TAP,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(
                            QUnbounded(),
                            SelectorMode.ALL,
                            FAnd(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Creature",
                                    ),
                                    FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE),
                                )
                            ),
                            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                        ),
                    ),
                )
            ),
        ),
    )


def _build_faiths_fetters(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.GAIN_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(_n(m, 1))),
                )
            ),
        ),
    )


def _build_meteorite(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _any_target()),
                    ("amount", QConst(_n(m, 1))),
                )
            ),
        ),
    )


def _build_deathbloom_thallid(m: re.Match[str]) -> SentenceOutcome:
    power, toughness = _n(m, 1), _n(m, 2)
    return _ability(
        _dies_event(),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    ("tokens", _saproling_token(power, toughness)),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


def _build_spirit_of_malevolence(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _dies_event(),
        Seq(
            steps=(
                Atom(
                    verb=Verb.LOSE_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.ALL_OPPONENTS),
                            ("amount", QConst(_n(m, 1))),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.GAIN_LIFE,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            ("amount", QConst(_n(m, 2))),
                        )
                    ),
                ),
            )
        ),
    )


def _build_pitchburn_devils(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _dies_event(),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _any_target()),
                    ("amount", QConst(_n(m, 1))),
                )
            ),
        ),
    )


def _build_canopy_stalker(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _dies_event(),
        Atom(
            verb=Verb.GAIN_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    (
                        "amount",
                        QBin(
                            op=QBinOp.MUL,
                            left=QConst(_n(m, 1)),
                            right=QCount(_creatures_died_this_turn()),
                        ),
                    ),
                )
            ),
        ),
    )


def _build_conclave_mentor(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _dies_event(),
        Atom(
            verb=Verb.GAIN_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    (
                        "amount",
                        QProp(
                            referent="source",
                            field=QPropField.POWER,
                            agg=QAgg.FIRST,
                        ),
                    ),
                )
            ),
        ),
    )


def _build_solemn_simulacrum(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _dies_event(),
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


def _build_goblin_arsonist(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _dies_event(),
        OptionalEffect(
            inner=Atom(
                verb=Verb.DEAL_DAMAGE,
                args=AtomArgs(
                    pairs=(
                        ("target", _any_target()),
                        ("amount", QConst(_n(m, 1))),
                    )
                ),
            )
        ),
    )


def _build_valorous_steed(m: re.Match[str]) -> SentenceOutcome:
    power, toughness = _n(m, 1), _n(m, 2)
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    ("tokens", _knight_token(power, toughness)),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


def _build_massacre_wurm(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _creatures_opponents_control()),
                    (
                        "power",
                        PtDelta(PtDirection.DECREASE, QConst(_n(m, 1))),
                    ),
                    (
                        "toughness",
                        PtDelta(PtDirection.DECREASE, QConst(_n(m, 2))),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_rambunctious_mutt(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DESTROY,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(
                            QConst(1),
                            SelectorMode.TARGET,
                            FAnd(
                                children=(
                                    FOr(
                                        children=(
                                            FAtom(
                                                pred=FAtomPred.TYPE_EQ,
                                                string_value="Artifact",
                                            ),
                                            FAtom(
                                                pred=FAtomPred.TYPE_EQ,
                                                string_value="Enchantment",
                                            ),
                                        )
                                    ),
                                    FAtom(
                                        pred=FAtomPred.CONTROLLER_IS,
                                        who=ControllerRef.OPPONENT,
                                    ),
                                )
                            ),
                            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                        ),
                    ),
                )
            ),
        ),
    )


def _build_lilianas_standard_bearer(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    (
                        "amount",
                        QCount(
                            _creatures_died_this_turn(controlled_by=ControllerRef.YOU)
                        ),
                    ),
                )
            ),
        ),
    )


def _build_etb_draw_one(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        ),
    )


def _build_skeleton_archer(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _any_target()),
                    ("amount", QConst(_n(m, 1))),
                )
            ),
        ),
    )


def _build_storm_caller(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _opponent_players()),
                    ("amount", QConst(_n(m, 1))),
                )
            ),
        ),
    )


def _build_carrion_grub(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                    ("from", Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),
                    ("journal_kind", "MILL"),
                    ("pop_order", "TOP"),
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(4)),
                )
            ),
        ),
    )


def _build_basris_acolyte(m: re.Match[str]) -> SentenceOutcome:
    """ETB +1/+1 counter on each of up to two other target creatures you
    control — TARGET + QAtMost(2) (targeted "up to N")."""
    counter_p, counter_t = _n(m, 1), _n(m, 2)
    if (counter_p, counter_t) != (1, 1):
        raise ValueError(
            f"B2a-basris-acolyte expects a +1/+1 counter, got +{counter_p}/+{counter_t}"
        )
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(
                            QAtMost(2),
                            SelectorMode.TARGET,
                            FAnd(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Creature",
                                    ),
                                    FAtom(
                                        pred=FAtomPred.CONTROLLER_IS,
                                        who=ControllerRef.YOU,
                                    ),
                                    FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                                )
                            ),
                            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                        ),
                    ),
                    ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


def _build_basris_lieutenant(m: re.Match[str]) -> SentenceOutcome:
    counter_p, counter_t = _n(m, 1), _n(m, 2)
    if (counter_p, counter_t) != (1, 1):
        raise ValueError(
            "B2a-basris-lieutenant expects a +1/+1 counter, "
            f"got +{counter_p}/+{counter_t}"
        )
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(
                            QConst(1),
                            SelectorMode.TARGET,
                            FAnd(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Creature",
                                    ),
                                    FAtom(
                                        pred=FAtomPred.CONTROLLER_IS,
                                        who=ControllerRef.YOU,
                                    ),
                                )
                            ),
                            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                        ),
                    ),
                    ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                    ("count", QConst(1)),
                )
            ),
        ),
    )


def _build_shipwreck_dowser(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    (
                        "cards",
                        Selector(
                            QConst(1),
                            SelectorMode.TARGET,
                            FOr(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Instant",
                                    ),
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Sorcery",
                                    ),
                                )
                            ),
                            zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),),
                        ),
                    ),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                )
            ),
        ),
    )


def _build_roaming_ghostlight(m: re.Match[str]) -> SentenceOutcome:
    """ETB: return up to one target non-Spirit creature — TARGET +
    QAtMost(1) (targeted "up to N")."""
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    (
                        "cards",
                        Selector(
                            QAtMost(1),
                            SelectorMode.TARGET,
                            FAnd(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Creature",
                                    ),
                                    FNot(
                                        inner=FAtom(
                                            pred=FAtomPred.SUBTYPE_EQ,
                                            string_value="Spirit",
                                        )
                                    ),
                                )
                            ),
                            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                        ),
                    ),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.OWNER)),
                )
            ),
        ),
    )


def _build_scry_n(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.SCRY,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("count", QConst(_n(m, 1))),
                )
            ),
        ),
    )


def _build_gale_swooper(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.GRANT_ABILITY,
            args=AtomArgs(
                pairs=(
                    ("target", _target_creature()),
                    (
                        "ability",
                        KeywordAbility(keyword=Keyword.FLYING, params=()),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_bone_pit_brute(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    ("target", _target_creature()),
                    (
                        "power",
                        PtDelta(PtDirection.INCREASE, QConst(_n(m, 1))),
                    ),
                    (
                        "toughness",
                        PtDelta(PtDirection.INCREASE, QConst(_n(m, 2))),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        ),
    )


def _build_kitesail_freebooter(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.REVEAL,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.TARGET_OPPONENT),
                    ("count", QUnbounded()),
                )
            ),
        ),
    )


def _build_aven_gagglemaster(m: re.Match[str]) -> SentenceOutcome:
    flying_creatures_you_control = Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.GAIN_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    (
                        "amount",
                        QBin(
                            op=QBinOp.MUL,
                            left=QConst(_n(m, 1)),
                            right=QCount(flying_creatures_you_control),
                        ),
                    ),
                )
            ),
        ),
    )


def _build_crypt_lurker(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        OptionalEffect(
            inner=Choose(
                count=QConst(1),
                options=(
                    Atom(
                        verb=Verb.SACRIFICE,
                        args=AtomArgs(
                            pairs=(
                                (
                                    "target",
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
                                                    pred=FAtomPred.CONTROLLER_IS,
                                                    who=ControllerRef.YOU,
                                                ),
                                            )
                                        ),
                                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                                    ),
                                ),
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
                                (
                                    "cards",
                                    Selector(
                                        QConst(1),
                                        SelectorMode.CHOOSE,
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ,
                                            string_value="Creature",
                                        ),
                                        zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                                    ),
                                ),
                            )
                        ),
                    ),
                ),
            )
        ),
    )


# ---------------------------------------------------------------------------
# Builders — POWER_GE, NAME_CONTAINS, EachPlayer, ZonePosition and PAY shapes
# ---------------------------------------------------------------------------


def _build_adherent_of_hope(m: re.Match[str]) -> SentenceOutcome:
    """``At the beginning of combat on your turn, if you control a Basri
    planeswalker, put a +1/+1 counter on this creature.``

    The intervening "if" (CR 603.4) is an existence claim over your
    permanents: ``CONTROLLER_COUNT_GE`` count=1 with the Basri /
    Planeswalker / you-control test inside the inner filter, evaluated per
    candidate. A bare filter as the condition would be judged against the
    trigger's source, the Adherent itself.
    """
    counter_p, counter_t = _n(m, 1), _n(m, 2)
    if (counter_p, counter_t) != (1, 1):
        raise ValueError(
            "B2a-adherent-of-hope expects a +1/+1 counter, "
            f"got +{counter_p}/+{counter_t}"
        )
    return _ability(
        _combat_event(),
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
        condition=FAtom(
            pred=FAtomPred.CONTROLLER_COUNT_GE,
            inner_filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.NAME_CONTAINS, string_value="Basri"),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
            count=QConst(1),
        ),
    )


def _build_lilianas_devotee(m: re.Match[str]) -> SentenceOutcome:
    n = _n(m, 1)
    return _ability(
        _end_step_event(),
        OptionalEffect(
            inner=Atom(
                verb=Verb.PAY,
                args=AtomArgs(
                    pairs=(
                        (
                            "cost",
                            Cost(
                                parts=(
                                    CostManaGeneric(QConst(n)),
                                    CostManaColor(color="B", amount=QConst(1)),
                                )
                            ),
                        ),
                    )
                ),
            )
        ),
        condition=FAtom(pred=FAtomPred.DIED_THIS_TURN),
    )


def _build_furious_rise(m: re.Match[str]) -> SentenceOutcome:
    n = _n(m, 1)
    return _ability(
        _end_step_event(),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                    (
                        "target",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(children=()),
                            zones=(Zone(
                                ZoneKind.LIBRARY,
                                ControllerRef.YOU,
                                ZonePosition.TOP,
                            ),),
                        ),
                    ),
                )
            ),
        ),
        # "if you control a creature with power N or greater" is an existence
        # test over your creatures (CR 603.4); a bare filter would be judged
        # on this enchantment.
        condition=FAtom(
            pred=FAtomPred.CONTROLLER_COUNT_GE,
            count=QConst(1),
            inner_filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.POWER_GE, count=QConst(n)),
                )
            ),
        ),
    )


def _build_sanctum_of_all(m: re.Match[str]) -> SentenceOutcome:
    """Sanctum of All: "At the beginning of your upkeep, you may search your
    library and/or graveyard for a Shrine card and put it onto the
    battlefield." The zone choice is visible, as for the named tutors
    (templates.and_or_zone_search); the shuffle joins only the options that
    search the library."""

    def search_in(zones: tuple[Zone, ...]) -> Atom:
        return Atom(
            verb=Verb.SEARCH,
            args=AtomArgs(
                pairs=(
                    (
                        "cards",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Shrine"),
                            zones=zones,
                        ),
                    ),
                    (
                        "destination",
                        Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                    ),
                    ("controller", ControllerRef.YOU),
                )
            ),
        )

    return _ability(
        _upkeep_event(),
        OptionalEffect(
            inner=and_or_zone_search(
                search_in,
                Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
            )
        ),
    )


def _build_goremand(m: re.Match[str]) -> SentenceOutcome:
    # EachPlayer rebinds ControllerRef.YOU in the inner effect to the looping
    # player.
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        EachPlayer(
            ref=ControllerRef.ALL_OPPONENTS,
            effect=Atom(
                verb=Verb.SACRIFICE,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
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
                                            pred=FAtomPred.CONTROLLER_IS,
                                            who=ControllerRef.YOU,
                                        ),
                                    )
                                ),
                                zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                            ),
                        ),
                    )
                ),
            ),
        ),
    )


def _build_turret_ogre(m: re.Match[str]) -> SentenceOutcome:
    """ETB, if you control another creature with power N or greater, deal D
    to each opponent.

    The intervening "if" (CR 603.4) is an existence claim:
    ``CONTROLLER_COUNT_GE`` counts your battlefield permanents through the
    inner filter, and ``FNot(IS_SOURCE)`` inside the per-candidate test is
    "another". Judged against the trigger's source instead, it could never
    hold.
    """
    threshold, damage = _n(m, 1), _n(m, 2)
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _opponent_players()),
                    ("amount", QConst(damage)),
                )
            ),
        ),
        condition=FAtom(
            pred=FAtomPred.CONTROLLER_COUNT_GE,
            inner_filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.POWER_GE, count=QConst(threshold)),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                )
            ),
            count=QConst(1),
        ),
    )


# ---------------------------------------------------------------------------
# Builders — end-step life-gained-this-turn threshold shapes
# ---------------------------------------------------------------------------


def _build_griffin_aerie(m: re.Match[str]) -> SentenceOutcome:
    # The threshold N and the token's P/T are independent numbers in the
    # concrete sentence (gained 3 or more -> a 2/2 Griffin).
    threshold, power, toughness = _n(m, 1), _n(m, 2), _n(m, 3)
    return _ability(
        _end_step_event(),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    ("tokens", _griffin_token(power, toughness)),
                    ("count", QConst(1)),
                )
            ),
        ),
        condition=_life_gained_this_turn_ge(threshold),
    )


def _build_indulging_patrician(m: re.Match[str]) -> SentenceOutcome:
    threshold, amount = _n(m, 1), _n(m, 2)
    return _ability(
        _end_step_event(),
        Atom(
            verb=Verb.LOSE_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.ALL_OPPONENTS),
                    ("amount", QConst(amount)),
                )
            ),
        ),
        condition=_life_gained_this_turn_ge(threshold),
    )


def _build_silversmote_ghoul(m: re.Match[str]) -> SentenceOutcome:
    threshold = _n(m, 1)
    return _ability(
        _end_step_event(),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    (
                        "cards",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAtom(pred=FAtomPred.IS_SOURCE),
                            zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),),
                        ),
                    ),
                    ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
                    ("tapped_on_enter", True),
                )
            ),
        ),
        condition=_life_gained_this_turn_ge(threshold),
    )


# ---------------------------------------------------------------------------
# Builders — this-turn conditions and each-end-step triggers
# ---------------------------------------------------------------------------


def _build_archfiends_vessel(m: re.Match[str]) -> SentenceOutcome:
    """ETB, if it entered from your graveyard or you cast it from your
    graveyard, exile it: FOr of ENTERED_THIS_TURN_FROM and
    CAST_THIS_TURN_FROM over your graveyard (the cast one's ``who`` is YOU,
    the caster)."""
    condition = FOr(
        children=(
            FAtom(
                pred=FAtomPred.ENTERED_THIS_TURN_FROM,
                zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
            ),
            FAtom(
                pred=FAtomPred.CAST_THIS_TURN_FROM,
                zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                who=ControllerRef.YOU,
            ),
        )
    )
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                    ("target", _self_selector()),
                )
            ),
        ),
        condition=condition,
    )


def _build_lilianas_scrounger(m: re.Match[str]) -> SentenceOutcome:
    """At the beginning of each end step, if a creature died this turn, you
    may put a loyalty counter on a Liliana planeswalker you control.

    "Each end step" is every player's end step: TurnPhaseEvent(END_TURN)
    with no actor."""
    target = Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.NAME_CONTAINS, string_value="Liliana"),
                FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Planeswalker"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )
    return _ability(
        TurnPhaseEvent(phase=Phase.END_TURN),
        OptionalEffect(
            inner=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        ("counter_kind", CounterKind.LOYALTY),
                        ("count", QConst(1)),
                    )
                ),
            )
        ),
        condition=FAtom(pred=FAtomPred.DIED_THIS_TURN),
    )


def _build_barrin_end_step(m: re.Match[str]) -> SentenceOutcome:
    """At the beginning of your end step, if a permanent was put into your
    hand from the battlefield this turn, draw a card.

    MOVED_TO_ZONE_THIS_TURN from the battlefield to your hand, ``who`` = YOU,
    the player the move is relative to. Lossy: "a permanent" carries no
    permanent-type filter."""
    return _ability(
        _end_step_event(),
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
            pred=FAtomPred.MOVED_TO_ZONE_THIS_TURN,
            from_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            to_zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
            who=ControllerRef.YOU,
        ),
    )


# ---------------------------------------------------------------------------
# Builders — "that many", exile-until-leaves, token-text and same-name shapes
# ---------------------------------------------------------------------------


def _build_kinetic_augur_etb(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, discard up to two cards, then draw
    that many cards.`` (Kinetic Augur) — "up to two" is CHOOSE + QAtMost(2):
    the discarding player picks 0, 1 or 2 cards. "That many" is the
    ``THAT_MANY_COUNT`` quantity, the discarded count read off the effect
    register."""
    discard = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                ("controller", ControllerRef.YOU),
                (
                    "cards",
                    Selector(
                        QAtMost(2),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                    ),
                ),
            )
        ),
    )
    draw = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QProp(referent="event", field=QPropField.THAT_MANY_COUNT)),
            )
        ),
    )
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)), Seq(steps=(discard, draw))
    )


def _build_idol_of_endurance_etb(m: re.Match[str]) -> SentenceOutcome:
    """``When this artifact enters, exile all creature cards with mana
    value N or less from your graveyard until this artifact leaves the
    battlefield.`` (Idol of Endurance) — ALL+QUnbounded exile of the
    filtered graveyard with ``duration=DurationUntilLeaves()`` (CR 610.3):
    when the Idol leaves the battlefield, the cards still in exile return to
    their owner's graveyard."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                ("duration", DurationUntilLeaves()),
                (
                    "target",
                    Selector(
                        QUnbounded(),
                        SelectorMode.ALL,
                        FAnd(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                                FAtom(
                                    pred=FAtomPred.CMC_LE,
                                    count=QConst(_n(m, 1)),
                                ),
                            )
                        ),
                        zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),),
                    ),
                ),
            )
        ),
    )
    return _ability(_etb_event(FAtom(pred=FAtomPred.IS_SOURCE)), atom)


def _build_pursued_whale_token(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, each opponent creates a 1/1 red Pirate
    creature token with "This token can't block" and "Creatures you control
    attack each combat if able."`` (Pursued Whale).

    The quoted token text never enters the payload as strings: the pattern
    locks the sentence and the builder hand-builds the IR into
    ``TokenSpec.abilities``:

    - ``"This token can't block"`` → b4 ``_build_cant_block``'s shape,
      StaticAbility(PREVENT_EFFECT(condition=IS_SOURCE,
      event=DeclareBlockersEvent(IS_SOURCE))); inside the token's own
      ability the source is the token.
    - ``"Creatures you control attack each combat if able."`` → b4
      ``_build_mandate_attack_you``'s MANDATE_ATTACK shape; "you" is the
      token's controller.

    EachPlayer(ref=ALL_OPPONENTS) carries "each opponent creates";
    CREATE_TOKEN has no creator role, so the iterating player creates the
    token."""
    cant_block = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAtom(pred=FAtomPred.IS_SOURCE)),
                ("event", DeclareBlockersEvent(FAtom(pred=FAtomPred.IS_SOURCE))),
            )
        ),
    )
    attack_if_able = Atom(
        verb=Verb.MANDATE_ATTACK,
        args=AtomArgs(
            pairs=(
                ("cards", _creatures_you_control()),
                ("controller", ControllerRef.YOU),
            )
        ),
    )
    pirate = TokenSpec(
        name="Pirate",
        type_line="Creature — Pirate",
        types=("Creature",),
        subtypes=("Pirate",),
        power=QConst(1),
        toughness=QConst(1),
        keywords=(),
        abilities=(
            StaticAbility(effect=cant_block),
            StaticAbility(effect=attack_if_able),
        ),
        colors=("R",),
    )
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        EachPlayer(
            ref=ControllerRef.ALL_OPPONENTS,
            effect=Atom(
                verb=Verb.CREATE_TOKEN,
                args=AtomArgs(pairs=(("tokens", pirate), ("count", QConst(1)))),
            ),
        ),
    )


def _build_chrome_replicator_etb(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, if you control two or more nonland,
    nontoken permanents with the same name as one another, create a 4/4
    colorless Construct artifact creature token.`` (Chrome Replicator)

    The "if" is the condition ``NAME_PARTITION_COUNT_GE``: the inner filter
    is nonland and nontoken, count=2 the threshold; the executor groups the
    matched permanents by exact name and tests the largest group. A
    colorless token leaves ``colors`` empty."""
    p, t = _n(m, 1), _n(m, 2)
    return _ability(
        _etb_event(FAtom(pred=FAtomPred.IS_SOURCE)),
        Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    (
                        "tokens",
                        TokenSpec(
                            name="Construct",
                            type_line="Artifact Creature — Construct",
                            types=("Artifact", "Creature"),
                            subtypes=("Construct",),
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
        condition=FAtom(
            pred=FAtomPred.NAME_PARTITION_COUNT_GE,
            inner_filter=FAnd(
                children=(
                    FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land")),
                    FNot(inner=FAtom(pred=FAtomPred.IS_TOKEN)),
                )
            ),
            count=QConst(2),
        ),
    )


# ---------------------------------------------------------------------------
# Template table
# ---------------------------------------------------------------------------


TEMPLATES: Final[tuple[Template, ...]] = (
    _template(
        "B2a-basri-ket-emblem",
        "Basri Ket Emblem",
        re.compile(
            r"At the beginning of combat on your turn, "
            r"create a (\d+)/(\d+) white Soldier creature token, "
            r"then put a \+(\d+)/\+(\d+) counter on each creature you control\."
        ),
        _build_basri_ket,
    ),
    _template(
        "B2a-liliana-waker-emblem",
        "Liliana, Waker of the Dead Emblem",
        _exact(
            "At the beginning of combat on your turn, "
            "put target creature card from a graveyard onto the battlefield "
            "under your control."
        ),
        _build_liliana_waker,
    ),
    _template(
        "B2a-battle-rattle-shaman",
        "Battle-Rattle Shaman",
        re.compile(
            r"At the beginning of combat on your turn, "
            r"you may have target creature get \+(\d+)/\+(\d+) "
            r"until end of turn\."
        ),
        _build_battle_rattle_shaman,
    ),
    _template(
        "B2a-dire-fleet-warmonger",
        "Dire Fleet Warmonger",
        _exact(
            "At the beginning of combat on your turn, "
            "you may sacrifice another creature."
        ),
        _build_dire_fleet_warmonger,
    ),
    _template(
        "B2a-gadrak-treasures",
        "Gadrak, the Crown-Scourge",
        _exact(
            "At the beginning of your end step, "
            "create a Treasure token for each nontoken creature "
            "that died this turn."
        ),
        _build_gadrak_treasures,
    ),
    _template(
        "B2a-twinblade-assassins",
        "Twinblade Assassins",
        _exact(
            "At the beginning of your end step, "
            "if a creature died this turn, draw a card."
        ),
        _build_twinblade_assassins,
    ),
    _template(
        "B2a-sabertooth-mauler",
        "Sabertooth Mauler",
        re.compile(
            r"At the beginning of your end step, "
            r"if a creature died this turn, "
            r"put a \+(\d+)/\+(\d+) counter on this creature "
            r"and untap it\."
        ),
        _build_sabertooth_mauler,
    ),
    _template(
        "B2a-garruk-emblem",
        "Garruk, Unleashed Emblem",
        _exact(
            "At the beginning of your end step, "
            "you may search your library for a creature card, "
            "put it onto the battlefield, "
            "then shuffle your library."
        ),
        _build_garruk_emblem,
    ),
    _template(
        "B2a-sanctum-fruitful-harvest",
        "Sanctum of Fruitful Harvest",
        _exact(
            "At the beginning of your first main phase, "
            "add X mana of any one color, "
            "where X is the number of Shrines you control."
        ),
        _build_sanctum_fruitful_harvest,
    ),
    _template(
        "B2a-sanctum-stone-fangs",
        "Sanctum of Stone Fangs",
        _exact(
            "At the beginning of your first main phase, "
            "each opponent loses X life and you gain X life, "
            "where X is the number of Shrines you control."
        ),
        _build_sanctum_stone_fangs,
    ),
    _template(
        "B2a-sanctum-calm-waters",
        "Sanctum of Calm Waters",
        _exact(
            "At the beginning of your first main phase, "
            "you may draw X cards, "
            "where X is the number of Shrines you control."
        ),
        _build_sanctum_calm_waters,
    ),
    _template(
        "B2a-barrin-etb",
        "Barrin, Tolarian Archmage ETB",
        _exact(
            "When Barrin enters, "
            "return up to one other target creature or planeswalker "
            "to its owner's hand."
        ),
        _build_barrin_etb,
    ),
    _template(
        "B2a-niambi-etb",
        "Niambi, Esteemed Speaker ETB",
        _exact(
            "When Niambi enters, "
            "you may return another target creature you control "
            "to its owner's hand."
        ),
        _build_niambi_etb,
    ),
    _template(
        "B2a-mazemind-tome",
        "Mazemind Tome",
        _exact("When there are four or more page counters on this artifact, exile it."),
        _build_mazemind_tome,
    ),
    _template(
        "B2a-nine-lives",
        "Nine Lives",
        _exact(
            "When there are nine or more incarnation counters "
            "on this enchantment, exile it."
        ),
        _build_nine_lives,
    ),
    _template(
        "B2a-setessan-training",
        "Setessan Training",
        _exact("When this Aura enters, draw a card."),
        _build_setessan_training,
    ),
    _template(
        "B2a-rousing-read",
        "Rousing Read",
        _exact("When this Aura enters, draw two cards, then discard a card."),
        _build_rousing_read,
    ),
    _template(
        "B2a-capture-sphere",
        "Capture Sphere",
        _exact("When this Aura enters, tap enchanted creature."),
        _build_capture_sphere,
    ),
    _template(
        "B2a-faiths-fetters",
        "Faith's Fetters",
        re.compile(r"When this Aura enters, you gain (\d+) life\."),
        _build_faiths_fetters,
    ),
    _template(
        "B2a-meteorite",
        "Meteorite",
        re.compile(r"When this artifact enters, it deals (\d+) damage to any target\."),
        _build_meteorite,
    ),
    _template(
        "B2a-deathbloom-thallid",
        "Deathbloom Thallid",
        re.compile(
            r"When this creature dies, "
            r"create a (\d+)/(\d+) green Saproling creature token\."
        ),
        _build_deathbloom_thallid,
    ),
    _template(
        "B2a-spirit-of-malevolence",
        "Spirit of Malevolence",
        re.compile(
            r"When this creature dies, "
            r"each opponent loses (\d+) life and you gain (\d+) life\."
        ),
        _build_spirit_of_malevolence,
    ),
    _template(
        "B2a-pitchburn-devils",
        "Pitchburn Devils",
        re.compile(r"When this creature dies, it deals (\d+) damage to any target\."),
        _build_pitchburn_devils,
    ),
    _template(
        "B2a-canopy-stalker",
        "Canopy Stalker",
        re.compile(
            r"When this creature dies, "
            r"you gain (\d+) life for each creature that died this turn\."
        ),
        _build_canopy_stalker,
    ),
    _template(
        "B2a-conclave-mentor",
        "Conclave Mentor",
        _exact("When this creature dies, you gain life equal to its power."),
        _build_conclave_mentor,
    ),
    _template(
        "B2a-solemn-simulacrum",
        "Solemn Simulacrum",
        _exact("When this creature dies, you may draw a card."),
        _build_solemn_simulacrum,
    ),
    _template(
        "B2a-goblin-arsonist",
        "Goblin Arsonist",
        re.compile(
            r"When this creature dies, you may have it deal (\d+) damage "
            r"to any target\."
        ),
        _build_goblin_arsonist,
    ),
    _template(
        "B2a-valorous-steed",
        "Valorous Steed",
        re.compile(
            r"When this creature enters, "
            r"create a (\d+)/(\d+) white Knight creature token "
            r"with vigilance\."
        ),
        _build_valorous_steed,
    ),
    _template(
        "B2a-massacre-wurm",
        "Massacre Wurm",
        re.compile(
            r"When this creature enters, "
            r"creatures your opponents control get -(\d+)/-(\d+) "
            r"until end of turn\."
        ),
        _build_massacre_wurm,
    ),
    _template(
        "B2a-rambunctious-mutt",
        "Rambunctious Mutt",
        _exact(
            "When this creature enters, "
            "destroy target artifact or enchantment an opponent controls."
        ),
        _build_rambunctious_mutt,
    ),
    _template(
        "B2a-lilianas-standard-bearer",
        "Liliana's Standard Bearer",
        _exact(
            "When this creature enters, "
            "draw X cards, "
            "where X is the number of creatures that died under your control "
            "this turn."
        ),
        _build_lilianas_standard_bearer,
    ),
    _template(
        "B2a-etb-draw-one",
        "Creature ETB draw one",
        _exact("When this creature enters, draw a card."),
        _build_etb_draw_one,
    ),
    _template(
        "B2a-skeleton-archer",
        "Skeleton Archer",
        re.compile(r"When this creature enters, it deals (\d+) damage to any target\."),
        _build_skeleton_archer,
    ),
    _template(
        "B2a-storm-caller",
        "Storm Caller",
        re.compile(
            r"When this creature enters, it deals (\d+) damage to each opponent\."
        ),
        _build_storm_caller,
    ),
    _template(
        "B2a-carrion-grub",
        "Carrion Grub",
        _exact("When this creature enters, mill four cards."),
        _build_carrion_grub,
    ),
    _template(
        "B2a-basris-acolyte",
        "Basri's Acolyte",
        re.compile(
            r"When this creature enters, "
            r"put a \+(\d+)/\+(\d+) counter "
            r"on each of up to two other target creatures you control\."
        ),
        _build_basris_acolyte,
    ),
    _template(
        "B2a-basris-lieutenant",
        "Basri's Lieutenant / Pridemalkin",
        re.compile(
            r"When this creature enters, "
            r"put a \+(\d+)/\+(\d+) counter on target creature you control\."
        ),
        _build_basris_lieutenant,
    ),
    _template(
        "B2a-shipwreck-dowser",
        "Shipwreck Dowser",
        _exact(
            "When this creature enters, "
            "return target instant or sorcery card from your graveyard "
            "to your hand."
        ),
        _build_shipwreck_dowser,
    ),
    _template(
        "B2a-roaming-ghostlight",
        "Roaming Ghostlight",
        _exact(
            "When this creature enters, "
            "return up to one target non-Spirit creature "
            "to its owner's hand."
        ),
        _build_roaming_ghostlight,
    ),
    _template(
        "B2a-scry-n",
        "Creature ETB scry N",
        re.compile(r"When this creature enters, scry (\d+)\."),
        _build_scry_n,
    ),
    _template(
        "B2a-gale-swooper",
        "Gale Swooper",
        _exact(
            "When this creature enters, target creature gains flying until end of turn."
        ),
        _build_gale_swooper,
    ),
    _template(
        "B2a-bone-pit-brute",
        "Bone Pit Brute / Daybreak Charger",
        re.compile(
            r"When this creature enters, "
            r"target creature gets \+(\d+)/\+(\d+) until end of turn\."
        ),
        _build_bone_pit_brute,
    ),
    _template(
        "B2a-kitesail-freebooter",
        "Kitesail Freebooter",
        _exact("When this creature enters, target opponent reveals their hand."),
        _build_kitesail_freebooter,
    ),
    _template(
        "B2a-aven-gagglemaster",
        "Aven Gagglemaster",
        re.compile(
            r"When this creature enters, "
            r"you gain (\d+) life for each creature you control with flying\."
        ),
        _build_aven_gagglemaster,
    ),
    _template(
        "B2a-crypt-lurker",
        "Crypt Lurker",
        _exact(
            "When this creature enters, "
            "you may sacrifice a creature or discard a creature card."
        ),
        _build_crypt_lurker,
    ),
    _template(
        "B2a-adherent-of-hope",
        "Adherent of Hope",
        re.compile(
            r"At the beginning of combat on your turn, "
            r"if you control a Basri planeswalker, "
            r"put a \+(\d+)/\+(\d+) counter on this creature\."
        ),
        _build_adherent_of_hope,
    ),
    _template(
        "B2a-lilianas-devotee",
        "Liliana's Devotee",
        re.compile(
            r"At the beginning of your end step, "
            r"if a creature died this turn, "
            r"you may pay \{(\d+)\}\{B\}\."
        ),
        _build_lilianas_devotee,
    ),
    _template(
        "B2a-furious-rise",
        "Furious Rise",
        re.compile(
            r"At the beginning of your end step, "
            r"if you control a creature with power (\d+) or greater, "
            r"exile the top card of your library\."
        ),
        _build_furious_rise,
    ),
    _template(
        "B2a-sanctum-of-all",
        "Sanctum of All",
        _exact(
            "At the beginning of your upkeep, "
            "you may search your library and/or graveyard "
            "for a Shrine card and put it onto the battlefield."
        ),
        _build_sanctum_of_all,
    ),
    _template(
        "B2a-goremand",
        "Goremand",
        _exact("When this creature enters, each opponent sacrifices a creature."),
        _build_goremand,
    ),
    _template(
        "B2a-turret-ogre",
        "Turret Ogre",
        re.compile(
            r"When this creature enters, "
            r"if you control another creature with power (\d+) or greater, "
            r"this creature deals (\d+) damage to each opponent\."
        ),
        _build_turret_ogre,
    ),
    _template(
        "B2a-griffin-aerie",
        "Griffin Aerie",
        re.compile(
            r"At the beginning of your end step, "
            r"if you gained (\d+) or more life this turn, "
            r"create a (\d+)/(\d+) white Griffin creature token with flying\."
        ),
        _build_griffin_aerie,
    ),
    _template(
        "B2a-indulging-patrician",
        "Indulging Patrician",
        re.compile(
            r"At the beginning of your end step, "
            r"if you gained (\d+) or more life this turn, "
            r"each opponent loses (\d+) life\."
        ),
        _build_indulging_patrician,
    ),
    _template(
        "B2a-silversmote-ghoul",
        "Silversmote Ghoul",
        re.compile(
            r"At the beginning of your end step, "
            r"if you gained (\d+) or more life this turn, "
            r"return this card from your graveyard to the battlefield tapped\."
        ),
        _build_silversmote_ghoul,
    ),
    _template(
        "B2a-archfiends-vessel",
        "Archfiend's Vessel",
        _exact(
            "When this creature enters, "
            "if it entered from your graveyard or you cast it from your "
            "graveyard, exile it."
        ),
        _build_archfiends_vessel,
    ),
    _template(
        "B2a-lilianas-scrounger",
        "Liliana's Scrounger",
        _exact(
            "At the beginning of each end step, "
            "if a creature died this turn, "
            "you may put a loyalty counter on a Liliana planeswalker you control."
        ),
        _build_lilianas_scrounger,
    ),
    _template(
        "B2a-barrin-end-step",
        "Barrin, Tolarian Archmage End Step",
        _exact(
            "At the beginning of your end step, "
            "if a permanent was put into your hand from the battlefield this turn, "
            "draw a card."
        ),
        _build_barrin_end_step,
    ),
    _template(
        "B2a-draw-that-many",
        "Kinetic Augur",
        _exact(
            "When this creature enters, "
            "discard up to two cards, then draw that many cards."
        ),
        _build_kinetic_augur_etb,
    ),
    _template(
        "B2a-etb-exile-until-leaves",
        "Idol of Endurance",
        re.compile(
            r"^When this artifact enters, exile all creature cards with "
            r"mana value (\d+) or less from your graveyard until this "
            r"artifact leaves the battlefield\.$"
        ),
        _build_idol_of_endurance_etb,
    ),
    _template(
        "B2a-whale-opponent-pirate-tokens",
        "Pursued Whale Opponent Pirate Tokens",
        re.compile(
            r"^When this creature enters, each opponent creates a 1/1 red "
            r"Pirate creature token with \"This token can't block\" and "
            r"\"Creatures you control attack each combat if able\.\"$"
        ),
        _build_pursued_whale_token,
    ),
    _template(
        "B2a-etb-same-name-token",
        "Chrome Replicator",
        re.compile(
            r"^When this creature enters, if you control two or more "
            r"nonland, nontoken permanents with the same name as one "
            r"another, create a (\d+)/(\d+) colorless Construct artifact "
            r"creature token\.$"
        ),
        _build_chrome_replicator_etb,
    ),
)


UNCOVERED: Final[tuple[tuple[str, str], ...]] = (
    (
        "When this creature enters, choose one —",
        "handled by the compiler's choose-opener built-in (ETB variant)",
    ),
)
