"""The IR items gate round 4 ruled on (2026-11-12): ATTACK_POLICY, PhasingEvent, IS_RESULT,
DurationUntilEndOfNextTurn, REVEAL ``until`` and a referent Selector as EachPlayer's ref.

The cards that use them are pinned end to end by packs (tools/scenarios/ tyrannodon_*,
transmogrify_*, cards/M21/teferi_timeless_voyager_*). These cases pin the refusals: one meaning,
one encoding, and no silent reading where nothing can be read.
"""

from __future__ import annotations

import pytest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    DurationEot,
    DurationUntilEndOfNextTurn,
    DurationUntilNextTurn,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    PhasingEvent,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld
from MTG_bot.core.test_executor_binding import card_id, record_of
from MTG_bot.core.test_executor_verbs import BF_ANY, CREATURE, atom, target_sel

IS_RESULT = FAtom(FAtomPred.IS_RESULT)
ANY_ZONE = (Zone(ZoneKind.ANY, ControllerRef.ANY),)


def referent(name: str) -> Selector:
    return Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=ANY_ZONE, referent=name)


def they_cant_phase_in() -> Atom:
    """Teferi, Timeless Voyager's second [-8] sentence as compiled."""
    return atom(
        Verb.PREVENT_EFFECT,
        condition=IS_RESULT,
        event=PhasingEvent(phased_in=True, filter=IS_RESULT),
        duration=DurationUntilEndOfNextTurn(),
    )


# ------------------------------------------------------------- ATTACK_POLICY


def test_attack_policy_scope_is_its_own_closed_vocabulary() -> None:
    self_sel = Selector(QConst(1), SelectorMode.CHOOSE, FAtom(FAtomPred.IS_SOURCE), zones=(BF_ANY,))
    atom(Verb.ATTACK_POLICY, cards=self_sel, scope="AS_NO_DEFENDER")
    with pytest.raises(ValueError, match="ATTACK_POLICY scope must be one of"):
        atom(Verb.ATTACK_POLICY, cards=self_sel, scope="AS_UNBLOCKED")  # another verb's word
    with pytest.raises(ValueError, match="role 'scope' must be one of"):
        atom(Verb.ATTACK_POLICY, cards=self_sel, scope="AS_HASTE")  # no verb's word
    with pytest.raises(ValueError, match="missing required roles"):
        atom(Verb.ATTACK_POLICY, scope="AS_NO_DEFENDER")


# -------------------------------------------------------------- PhasingEvent


def test_phasing_event_constructor() -> None:
    assert PhasingEvent(phased_in=False, filter=CREATURE).phased_in is False
    with pytest.raises(ValueError, match="phased_in must be a bool"):
        PhasingEvent(phased_in=1, filter=CREATURE)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="filter must be a Filter"):
        PhasingEvent(phased_in=True, filter=target_sel())  # type: ignore[arg-type]


def test_the_binder_refuses_a_phasing_trigger() -> None:
    # No journal row records phasing (a status, CR 702.26d), so nothing could feed
    # "whenever a permanent phases in": the event is a prevention event only.
    world = GameWorld(num_players=2, start_life=20, master_seed=3)
    p0 = world.player_order[0]
    ex = Executor(world)
    cid = card_id("Phase Watcher", "1", "1")
    handle = world.add_card(cid, p0, ZONE_BATTLEFIELD)
    trigger = TriggeredAbility(
        event=PhasingEvent(phased_in=True, filter=CREATURE),
        condition=None,
        effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)),
    )
    with pytest.raises(NotImplementedError, match="PhasingEvent is a prevention event only"):
        ex.attach_card(handle, record_of([trigger], name="Phase Watcher", oid=cid.oracle_id))


# ----------------------------------------------------------------- IS_RESULT


def test_is_result_is_never_a_selector_filter() -> None:
    # Selector(referent="result") is the one encoding of "the objects the previous
    # instruction acted on" as a selection.
    with pytest.raises(ValueError, match="second form of Selector"):
        Selector(QUnbounded(), SelectorMode.ALL, IS_RESULT, zones=(BF_ANY,))
    with pytest.raises(ValueError, match="second form of Selector"):
        Selector(QUnbounded(), SelectorMode.ALL, FAnd((CREATURE, IS_RESULT)), zones=(BF_ANY,))


def test_is_result_only_in_filter_roles_that_take_no_selector() -> None:
    record_of([StaticAbility(effect=they_cant_phase_in())])  # condition + event: admitted
    # dealer/recipient take a Selector, so there it would be a second form
    damage = atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1), recipient=IS_RESULT)
    with pytest.raises(ValueError, match="IS_RESULT outside an Atom role"):
        record_of([StaticAbility(effect=damage)])
    # an ability's condition is read with no resolution, so no result register
    gated = StaticAbility(effect=they_cant_phase_in(), condition=IS_RESULT)
    with pytest.raises(ValueError, match="IS_RESULT outside an Atom role"):
        record_of([gated])


def test_is_result_with_no_register_raises() -> None:
    world = GameWorld(num_players=2, start_life=20, master_seed=3)
    p0 = world.player_order[0]
    bear = world.add_card(card_id("Bear", "2", "2"), p0, ZONE_BATTLEFIELD)
    ex = Executor(world)
    ctx = ex._ctx(source=bear, controller=p0, bindings={}, decisions=())
    with pytest.raises(NotImplementedError, match="IS_RESULT reads the result register"):
        eval_filter(IS_RESULT, bear, ctx)
    ctx.bindings["result"] = [bear]
    assert eval_filter(IS_RESULT, bear, ctx)
    with pytest.raises(NotImplementedError, match="no instruction before it wrote one"):
        ex.execute(they_cant_phase_in(), source=bear, controller=p0)


# --------------------------------------------------------- REVEAL until / LOOK_AT


def test_reveal_until_has_one_reading_of_count() -> None:
    atom(Verb.REVEAL, controller=ControllerRef.YOU, count=QConst(1), until=CREATURE)
    with pytest.raises(ValueError, match="passes every card"):
        atom(Verb.REVEAL, controller=ControllerRef.YOU, count=QConst(2), until=FAnd(()))
    with pytest.raises(ValueError, match="QUnbounded is no count"):
        atom(Verb.REVEAL, controller=ControllerRef.YOU, count=QUnbounded(), until=CREATURE)


def test_look_at_takes_no_until() -> None:
    with pytest.raises(ValueError, match=r"LOOK_AT does not take roles \['until'\]"):
        atom(Verb.LOOK_AT, controller=ControllerRef.YOU, count=QConst(1), until=CREATURE)


# ------------------------------------------------------- EachPlayer ref Selector


def test_each_player_selector_ref_needs_a_referent() -> None:
    draw = atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1))
    EachPlayer(ref=referent("target"), effect=draw)
    with pytest.raises(ValueError, match="must carry a referent"):
        EachPlayer(ref=target_sel(), effect=draw)


# ------------------------------------------------- GAIN_CONTROL durations


@pytest.mark.parametrize("duration", [DurationUntilNextTurn(), DurationUntilEndOfNextTurn()])
def test_gain_control_refuses_a_duration_it_cannot_end(duration) -> None:
    # _expire_control ends an entry at the end-of-turn sweep or when its anchor or the
    # creature leaves; any other duration would make the control permanent.
    world = GameWorld(num_players=2, start_life=20, master_seed=3)
    p0, p1 = world.player_order
    bear = world.add_card(card_id("Bear", "2", "2"), p1, ZONE_BATTLEFIELD)
    ex = Executor(world)
    steal = atom(Verb.GAIN_CONTROL, target=target_sel(), controller=ControllerRef.YOU,
                 duration=duration)
    with pytest.raises(NotImplementedError, match="no expiry in the control registry"):
        ex.execute(steal, source=bear, controller=p0, bindings={"target": bear})
    assert ex.controller_of(bear) == p1
    ex.execute(atom(Verb.GAIN_CONTROL, target=target_sel(), controller=ControllerRef.YOU,
                    duration=DurationEot()), source=bear, controller=p0, bindings={"target": bear})
    assert ex.controller_of(bear) == p0
