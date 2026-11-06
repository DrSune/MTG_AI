"""Grammar pins for the merged MOVE atom (docs/T4_SPEC.md §6).

The merged MOVE atom's slot vocabulary and the closed-vocab raises.
Executor-side behaviour (journal kind, pop order, result register, trigger
matching) is locked in test_executor_p1a_move.py.
"""

import pytest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    FAnd,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)


GY_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
LIB_YOU = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
UNIV = FAnd(())


def _move(**roles) -> Atom:
    return Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=tuple(roles.items())))


def test_mill_shape_is_slots_on_the_one_move_operation() -> None:
    # {operation × menu × count × journal-kind} stay orthogonal:
    # the mill shape is MOVE{from=LIBRARY/ctrl, to=GRAVEYARD/ctrl,
    # amount, journal_kind=MILL, pop_order=TOP} — the SAME operation
    # pairs with the designation menu and no from (exile shape).
    mill = _move(
        destination=GY_YOU,
        controller=ControllerRef.YOU,
        amount=QConst(2),
        **{"from": LIB_YOU, "journal_kind": "MILL", "pop_order": "TOP"},
    )
    assert mill.args.get("from") == LIB_YOU
    assert mill.args.get("journal_kind") == "MILL"
    assert mill.args.get("pop_order") == "TOP"
    # The designation menu on the same operation (the exile shape, role
    # key `target`): no from, journal defaults to MOVE.
    exile = _move(
        destination=Zone(ZoneKind.EXILE, ControllerRef.ANY),
        target=Selector(
            QConst(1),
            SelectorMode.TARGET,
            UNIV,
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
        ),
    )
    assert exile.args.get("journal_kind") is None


def test_closed_vocab_and_object_axis_raise() -> None:
    with pytest.raises(ValueError, match="journal_kind"):
        AtomArgs(pairs=(("journal_kind", "EXILE"),))
    with pytest.raises(ValueError, match="pop_order"):
        AtomArgs(pairs=(("pop_order", "BOTTOM"),))
    # A MOVE with NO object axis (no cards/target/amount) is a move of
    # nothing — rejected at the verb level.
    with pytest.raises(ValueError, match="cards/target/amount"):
        _move(destination=GY_YOU, **{"from": LIB_YOU})


def test_legacy_move_shapes_still_construct() -> None:
    # The move-shape twins have no executor handler (MOVE_ZONE carries
    # them), but their atoms stay constructible.
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
                        UNIV,
                        zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                    ),
                ),
            )
        ),
    )
    Atom(
        verb=Verb.MILL,
        args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(2)))),
    )


def test_mill_journal_requires_top_pop():
    """MILL without pop_order TOP must RAISE, not fall through to another lane."""
    import pytest
    from MTG_bot.core.ability_tree import AtomArgs

    with pytest.raises(ValueError):
        AtomArgs(pairs=[("journal_kind", "MILL")])  # forgotten pop_order
    with pytest.raises(ValueError):
        AtomArgs(pairs=[("journal_kind", "MILL"), ("pop_order", "RANDOM")])
    AtomArgs(pairs=[("journal_kind", "MILL"), ("pop_order", "TOP")])  # ok
