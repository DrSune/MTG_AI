"""T4 P1a grammar pins (docs/T4_SPEC.md §1/§9, 2026-10-07).

The verb CLASS partition, the merged MOVE atom's slot vocabulary, and the
closed-vocab raises.  Executor-side behaviour (journal kind, pop order,
result register, trigger matching) is locked in test_executor_p1a_move.py.
"""

from collections import Counter

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
    VerbClass,
    VERB_CLASS,
    Zone,
    ZoneKind,
)


def test_verb_class_partitions_the_full_enum_exactly_once() -> None:
    # 6 OPERATION / 7 POLICY / 36 EFFECT == 49 members, no gaps, no
    # double-classing (T4 §1: CLASS = payload role, the shared PICK
    # wrapper holds selection).
    assert set(VERB_CLASS) == set(Verb)
    counts = Counter(VERB_CLASS.values())
    assert counts == {
        VerbClass.OPERATION: 6,
        VerbClass.POLICY: 7,
        VerbClass.EFFECT: 37,
    }
    # Embedded rulings: mandates are legality policies; the legacy
    # move-shape twins of the merged MOVE stay EFFECTs beside it.
    assert VERB_CLASS[Verb.MANDATE_ATTACK] is VerbClass.POLICY
    assert VERB_CLASS[Verb.MANDATE_BLOCK] is VerbClass.POLICY
    for legacy in (Verb.MILL, Verb.DISCARD, Verb.EXILE, Verb.MOVE_ZONE):
        assert VERB_CLASS[legacy] is VerbClass.EFFECT


GY_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
LIB_YOU = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
UNIV = FAnd(())


def _move(**roles) -> Atom:
    return Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=tuple(roles.items())))


def test_mill_shape_is_slots_on_the_one_move_operation() -> None:
    # {operation × menu × count × journal-kind} stay orthogonal (§9):
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
    # The designation menu on the same operation (old EXILE, A2(iv):
    # role key `target` kept): no from, journal defaults to MOVE.
    exile = _move(
        destination=Zone(ZoneKind.EXILE, ControllerRef.ANY),
        target=Selector(
            QConst(1),
            SelectorMode.TARGET,
            UNIV,
            Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
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
    # P1a removes EMISSION and DISPATCH, not the enum members: the
    # legacy atoms stay constructible (legacy decode, CLASS partition).
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
                        Zone(ZoneKind.HAND, ControllerRef.YOU),
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
    """Fresh-eyes MINOR fix: MILL without TOP must RAISE, not lane-fall-through."""
    import pytest
    from MTG_bot.core.ability_tree import AtomArgs

    with pytest.raises(ValueError):
        AtomArgs(pairs=[("journal_kind", "MILL")])  # forgotten pop_order
    with pytest.raises(ValueError):
        AtomArgs(pairs=[("journal_kind", "MILL"), ("pop_order", "RANDOM")])
    AtomArgs(pairs=[("journal_kind", "MILL"), ("pop_order", "TOP")])  # ok
