"""B2a bucket templates — 45 templates covering 47 of 64 B2a concrete rows.

Bucket input: ``/tmp/opencode/phase1_buckets/B2a.json`` (62 normalized shape
keys → ``[card, sentence]`` pairs; 66 card/sentence entries collapse to 64
distinct concrete oracle sentences).  Templates fullmatch the **concrete**
oracle sentence, never the normalized key.

Coverage (64 concrete rows = 47 template-covered + 17 uncovered):

- **45 templates** cover 45 normalized keys and 47 concrete rows.  Two
  normalized keys map to two concrete rows each (``scry N`` and
  ``target creature gets +N/+0 until end of turn``), while two other
  normalized keys each collapse two cards into one concrete row
  (``When this creature enters, draw a card.`` and
  ``When this creature enters, put a +1/+1 counter on target creature you
  control.``).
- **17 uncovered normalized keys** have no grammar construct and are recorded
  in ``UNCOVERED``.

Conventions (documented build decisions):

- ``this creature`` / ``this Aura`` / ``this artifact`` / ``this
  enchantment`` self-referent targets are encoded as
  ``Selector(CHOOSE, QConst(1), FAtom(IS_SOURCE), zone)`` — a semantic
  self-reference, never a hardcoded card name.
- ``up to one target ...`` uses ``SelectorMode.TARGET`` with ``QConst(1)``;
  the word ``target`` drives target mode, while ``you may`` alone drives
  ``OptionalEffect``.
- ``another`` / ``other`` adds ``FNot(inner=FAtom(IS_SOURCE))``.
- ``X is the number of Shrines you control`` is encoded as a ``QCount`` over
  ``NAME_EQ("Shrine")`` permanents you control.
- Token colors are dropped: ``TokenSpec`` has no color field.
- ``add X mana of any one color`` is encoded as ``ADD_MANA(color="C")`` —
  lossy: the grammar cannot distinguish "any one color" from colorless.
- ``each opponent`` for life gain/loss uses ``ControllerRef.ALL_OPPONENTS``;
  for damage targets it uses a ``Selector`` over ``Zone(PLAYER, OPPONENT)``.

PC-3: every B2a concrete sentence fullmatches **at most one** template
(patterns are pairwise disjoint by construction); verified in tests.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    Choose,
    ControllerRef,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DurationEot,
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
    TokenSpec,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    SentenceOutcome,
    Template,
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


def _creatures_opponents_control() -> Selector:
    """Selector for ``creatures your opponents control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(
                    pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT
                ),
            )
        ),
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
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
        children.append(
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=controlled_by)
        )
    if nontoken:
        children.append(FNot(inner=FAtom(pred=FAtomPred.IS_TOKEN)))
    children.append(FAtom(pred=FAtomPred.DIED_THIS_TURN))
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(children=tuple(children)),
        Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
    )


def _shrine_count() -> QCount:
    """``X`` for "where X is the number of Shrines you control"."""
    return QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAtom(pred=FAtomPred.NAME_EQ, string_value="Shrine"),
            Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        )
    )


def _any_target() -> Selector:
    """Selector for ``any target``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(children=()),
        Zone(ZoneKind.ANY, ControllerRef.ANY),
    )


def _target_creature() -> Selector:
    """Selector for ``target creature``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )


def _opponent_players() -> Selector:
    """Selector for ``each opponent`` as damage targets."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(children=()),
        Zone(ZoneKind.PLAYER, ControllerRef.OPPONENT),
    )


def _etb_event() -> ZoneChangeEvent:
    """Zone-change event for ``When this ... enters``."""
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
    )


def _combat_event() -> TurnPhaseEvent:
    """Turn-phase event for ``At the beginning of combat on your turn``."""
    return TurnPhaseEvent(phase=Phase.COMBAT, controller=ControllerRef.YOU)


def _end_step_event() -> TurnPhaseEvent:
    """Turn-phase event for ``At the beginning of your end step``."""
    return TurnPhaseEvent(phase=Phase.END_TURN, controller=ControllerRef.YOU)


def _first_main_event() -> TurnPhaseEvent:
    """Turn-phase event for ``At the beginning of your first main phase``."""
    return TurnPhaseEvent(phase=Phase.FIRST_MAIN, controller=ControllerRef.YOU)


def _dies_event() -> CreatureDiesEvent:
    """Creature-dies event for ``When this creature dies``."""
    return CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE))


def _soldier_token(power: int, toughness: int) -> TokenSpec:
    # GAP: token color omitted — TokenSpec has no color field.
    return TokenSpec(
        name="Soldier",
        type_line="Creature — Soldier",
        types=("Creature",),
        subtypes=("Soldier",),
        power=QConst(power),
        toughness=QConst(toughness),
        keywords=(),
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


def _treasure_token() -> TokenSpec:
    return TokenSpec(
        name="Treasure",
        type_line="Artifact",
        types=("Artifact",),
        subtypes=(),
        power=None,
        toughness=None,
        keywords=(Keyword.TREASURE,),
        abilities=(),
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
                            Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
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
                            PtDelta(
                                PtDirection.INCREASE, QConst(_n(m, 1))
                            ),
                        ),
                        (
                            "toughness",
                            PtDelta(
                                PtDirection.INCREASE, QConst(_n(m, 2))
                            ),
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
                                        FNot(
                                            inner=FAtom(pred=FAtomPred.IS_SOURCE)
                                        ),
                                    )
                                ),
                                Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
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
            args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))),
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
                                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
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
    # GAP: "any one color" is lossy — encoded as colorless mana.
    return _ability(
        _first_main_event(),
        Atom(
            verb=Verb.ADD_MANA,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", _shrine_count()),
                    ("color", "C"),
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
    return _ability(
        _etb_event(),
        Atom(
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
                            Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                        ),
                    ),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.ANY)),
                )
            ),
        ),
    )


def _build_niambi_etb(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
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
                                Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                            ),
                        ),
                        ("destination", Zone(ZoneKind.HAND, ControllerRef.ANY)),
                    )
                ),
            )
        ),
    )


def _build_mazemind_tome(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        CounterPlacedEvent(
            counter_kind=CounterKind.PAGE,
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
        ),
        Atom(
            verb=Verb.EXILE,
            args=AtomArgs(pairs=(("target", _self_selector()),)),
        ),
        condition=FAtom(
            pred=FAtomPred.HAS_COUNTER,
            counter_kind=CounterKind.PAGE,
            count=QConst(4),
        ),
    )


def _build_nine_lives(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        CounterPlacedEvent(
            counter_kind=CounterKind.INCARNATION,
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
        ),
        Atom(
            verb=Verb.EXILE,
            args=AtomArgs(pairs=(("target", _self_selector()),)),
        ),
        condition=FAtom(
            pred=FAtomPred.HAS_COUNTER,
            counter_kind=CounterKind.INCARNATION,
            count=QConst(9),
        ),
    )


def _build_setessan_training(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        ),
    )


def _build_rousing_read(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
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
                    verb=Verb.DISCARD,
                    args=AtomArgs(
                        pairs=(
                            ("controller", ControllerRef.YOU),
                            (
                                "cards",
                                Selector(
                                    QConst(1),
                                    SelectorMode.CHOOSE,
                                    FAnd(children=()),
                                    Zone(ZoneKind.HAND, ControllerRef.YOU),
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
        _etb_event(),
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
                            Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                        ),
                    ),
                )
            ),
        ),
    )


def _build_faiths_fetters(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
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
        _etb_event(),
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
        _etb_event(),
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
        _etb_event(),
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
        _etb_event(),
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
                            Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                        ),
                    ),
                )
            ),
        ),
    )


def _build_lilianas_standard_bearer(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    (
                        "amount",
                        QCount(_creatures_died_this_turn(controlled_by=ControllerRef.YOU)),
                    ),
                )
            ),
        ),
    )


def _build_etb_draw_one(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
        Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        ),
    )


def _build_skeleton_archer(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
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
        _etb_event(),
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
        _etb_event(),
        Atom(
            verb=Verb.MILL,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(4)),
                )
            ),
        ),
    )


def _build_basris_acolyte(m: re.Match[str]) -> SentenceOutcome:
    counter_p, counter_t = _n(m, 1), _n(m, 2)
    if (counter_p, counter_t) != (1, 1):
        raise ValueError(
            "B2a-basris-acolyte expects a +1/+1 counter, "
            f"got +{counter_p}/+{counter_t}"
        )
    return _ability(
        _etb_event(),
        Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(
                            QConst(2),
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
                            Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
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
        _etb_event(),
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
                            Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
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
        _etb_event(),
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
                            Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                        ),
                    ),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                )
            ),
        ),
    )


def _build_roaming_ghostlight(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
        Atom(
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
                                    FNot(
                                        inner=FAtom(
                                            pred=FAtomPred.SUBTYPE_EQ,
                                            string_value="Spirit",
                                        )
                                    ),
                                )
                            ),
                            Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                        ),
                    ),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.ANY)),
                )
            ),
        ),
    )


def _build_scry_n(m: re.Match[str]) -> SentenceOutcome:
    return _ability(
        _etb_event(),
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
        _etb_event(),
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
        _etb_event(),
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
        _etb_event(),
        Atom(
            verb=Verb.REVEAL,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.TARGET_PLAYER),
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
        Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
    )
    return _ability(
        _etb_event(),
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
        _etb_event(),
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
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ,
                                            string_value="Creature",
                                        ),
                                        Zone(
                                            ZoneKind.BATTLEFIELD, ControllerRef.YOU
                                        ),
                                    ),
                                ),
                            )
                        ),
                    ),
                    Atom(
                        verb=Verb.DISCARD,
                        args=AtomArgs(
                            pairs=(
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
                                        Zone(ZoneKind.HAND, ControllerRef.YOU),
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
        _exact(
            "When there are four or more page counters on this artifact, "
            "exile it."
        ),
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
        re.compile(
            r"When this creature dies, it deals (\d+) damage to any target\."
        ),
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
        re.compile(
            r"When this creature enters, it deals (\d+) damage to any target\."
        ),
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
            "When this creature enters, "
            "target creature gains flying until end of turn."
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
        _exact(
            "When this creature enters, target opponent reveals their hand."
        ),
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
)


UNCOVERED: Final[tuple[tuple[str, str], ...]] = (
    (
        "At the beginning of combat on your turn, "
        "if you control a Basri planeswalker, "
        "put a +N/+N counter on this creature.",
        "No name-contains predicate; only exact NAME_EQ is available.",
    ),
    (
        "At the beginning of each end step, "
        "if a creature died this turn, "
        "you may put a loyalty counter on a Liliana planeswalker you control.",
        "No name-contains predicate; only exact NAME_EQ is available.",
    ),
    (
        "At the beginning of your end step, "
        "if a creature died this turn, you may pay {N}{B}.",
        "No PAY verb or payable-cost trigger construct.",
    ),
    (
        "At the beginning of your end step, "
        "if a permanent was put into your hand from the battlefield this turn, "
        "draw a card.",
        "No turn-scoped zone-change trigger.",
    ),
    (
        "At the beginning of your end step, "
        "if you control a creature with power N or greater, "
        "exile the top card of your library.",
        "No power-only threshold and no top-of-library selector.",
    ),
    (
        "At the beginning of your end step, "
        "if you gained N or more life this turn, "
        "create a N/N white Griffin creature token with flying.",
        "No life-gained-this-turn quantity.",
    ),
    (
        "At the beginning of your end step, "
        "if you gained N or more life this turn, "
        "each opponent loses N life.",
        "No life-gained-this-turn quantity.",
    ),
    (
        "At the beginning of your end step, "
        "if you gained N or more life this turn, "
        "return this card from your graveyard to the battlefield tapped.",
        "No life-gained-this-turn quantity and no tap-on-return.",
    ),
    (
        "At the beginning of your upkeep, "
        "you may search your library and/or graveyard for a Shrine card "
        "and put it onto the battlefield.",
        "No multi-zone selector or and/or zone search.",
    ),
    (
        "When this artifact enters, "
        "exile all creature cards with mana value N or less "
        "from your graveyard until this artifact leaves the battlefield.",
        "No duration-until-source-leaves construct.",
    ),
    (
        "When this creature enters, choose one —",
        "Modal ability header, not a single triggered ability.",
    ),
    (
        "When this creature enters, "
        "discard up to two cards, then draw that many cards.",
        "Anaphoric 'that many' quantity is not expressible.",
    ),
    (
        "When this creature enters, "
        "each opponent creates a N/N red Pirate creature token "
        'with "This token can\'t block" '
        'and "Creatures you control attack each combat if able."',
        "Per-opponent token creation with nested token abilities.",
    ),
    (
        "When this creature enters, each opponent sacrifices a creature.",
        "Per-opponent action loop is not expressible.",
    ),
    (
        "When this creature enters, "
        "if it entered from your graveyard or you cast it from your graveyard, "
        "exile it.",
        "Event/source disjunction is not expressible.",
    ),
    (
        "When this creature enters, "
        "if you control another creature with power N or greater, "
        "this creature deals N damage to each opponent.",
        "No power-only threshold predicate.",
    ),
    (
        "When this creature enters, "
        "if you control two or more nonland, nontoken permanents "
        "with the same name as one another, "
        "create a N/N colorless Construct artifact creature token.",
        "No pairwise name-equality predicate.",
    ),
)
