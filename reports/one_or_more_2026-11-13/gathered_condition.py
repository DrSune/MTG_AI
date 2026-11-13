"""On a tree given as argv[1]: is a gathered trigger's condition reading QProp('event', field)
refused (per field, both events)? Prints one line per case."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (Atom, AtomArgs, ControllerRef, FAnd, FAtom, FAtomPred, QConst,
                                       QProp, QPropField, TriggeredAbility, Verb, Zone, ZoneKind)

CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
YOU = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
gain = Atom(Verb.GAIN_LIFE, AtomArgs(pairs=(("amount", QConst(1)), ("controller", ControllerRef.YOU))))
events = {
    "zone change": at.ZoneChangeEvent(Zone(ZoneKind.ANY, ControllerRef.ANY),
                                      Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                                      FAtom(FAtomPred.IS_TOKEN)),
    "declaration": at.DeclareAttackersEvent(filter=FAnd((YOU, CREATURE))),
}
for name, event in events.items():
    for field in (QPropField.POWER, QPropField.TOUGHNESS, QPropField.CMC, QPropField.MANA_VALUE,
                  QPropField.COUNTER_COUNT, QPropField.AMOUNT):
        cond = FAtom(FAtomPred.CONTROLLER_COUNT_GE, inner_filter=CREATURE,
                     count=QProp(referent="event", field=field))
        try:
            TriggeredAbility(event, cond, gain, once_per_event=True)
            print(name, field.name, "condition ACCEPTED")
        except ValueError as e:
            print(name, field.name, "condition refused:", str(e)[:60])
