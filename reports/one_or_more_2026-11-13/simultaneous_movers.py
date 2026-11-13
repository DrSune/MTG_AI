"""Do permanents that move in one atom see each other's moves (CR 603.6a, 603.10a)? Two creatures
each with "whenever another creature you control dies, you gain 1 life" die to one DESTROY: by
the rules each sees the other die (CR 603.10a: leaves-the-battlefield abilities look back), so
the controller gains 2. Then two creatures each with "whenever another creature you control
enters, you gain 1 life" enter in one MOVE_ZONE: each sees the other enter (CR 603.6a: the
newcomers are checked too), 2 again.

    simultaneous_movers.py <checkout>
"""
import sys

ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
import MTG_bot

assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CreatureDiesEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    QConst,
    Selector,
    SelectorMode,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.decisions import in_trigger_order
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import atom, card_id, record_of

YOU = ControllerRef.YOU
OTHER = FAnd((FAtom(FAtomPred.TYPE_EQ, string_value="Creature"), FNot(FAtom(FAtomPred.IS_SOURCE)),
              FAtom(FAtomPred.CONTROLLER_IS, who=YOU)))
GAIN = atom(Verb.GAIN_LIFE, controller=YOU, amount=QConst(1))
EVERY = Selector(QConst(9), SelectorMode.ALL, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))
for label, event, zone, dest in (
    ("two creatures die in one DESTROY", CreatureDiesEvent(filter=OTHER), ZONE_BATTLEFIELD, None),
    ("two creatures enter in one MOVE_ZONE",
     ZoneChangeEvent(Zone(ZoneKind.ANY, ControllerRef.ANY), Zone(ZoneKind.BATTLEFIELD, YOU), OTHER),
     ZONE_HAND, Zone(ZoneKind.BATTLEFIELD, YOU)),
):
    world = GameWorld(num_players=2, start_life=20, master_seed=11)
    p0 = world.player_order[0]
    ex = Executor(world)
    ex.decisions.provider = in_trigger_order
    pair = [world.add_card(card_id(f"C{i}", "2", "2"), p0, zone) for i in (1, 2)]
    for h in pair:
        rec = record_of([TriggeredAbility(event, None, GAIN)], oid=world.cards[h].identity.oracle_id)
        if zone == ZONE_BATTLEFIELD:
            ex.attach_card(h, rec)
        else:  # as a dealt game binds a card in hand: by oracle id, attached as it enters
            ex.binder.records[rec.oracle_id] = rec
    move = atom(Verb.DESTROY, target=EVERY) if dest is None else atom(Verb.MOVE_ZONE, cards=EVERY, destination=dest)
    ex.execute(move, source=pair[0], controller=p0, bindings={"target" if dest is None else "cards": pair})
    print(f"{label}: life 20 -> {world.players[p0].life} (the rules give 22)")
