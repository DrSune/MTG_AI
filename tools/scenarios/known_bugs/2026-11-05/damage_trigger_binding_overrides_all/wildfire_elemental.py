# Wildfire Elemental: "Whenever an opponent is dealt noncombat damage, creatures you control get +1/+0
# until end of turn."
# Event: Chandra's Pyreling's DamageDealtEvent(OPPONENT_OF you, combat=False) without its source filter
# (any source). Effect: Burn Bright's "Creatures you control get +2/+0 until end of turn" with +1.
trigger = TriggeredAbility(
    event=DamageDealtEvent(
        amount=QUnbounded(),
        filter=FAtom(pred=FAtomPred.OPPONENT_OF, who=ControllerRef.YOU),
        combat=False,
    ),
    condition=None,
    effect=A(Verb.MODIFY_PT, {
        'duration': DurationEot(),
        'power': PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(value=1)),
        'target': Selector(
            count=QUnbounded(),
            mode=SelectorMode.ALL,
            filter=FAnd(children=(
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
            )),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
        ),
        'toughness': PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(value=0)),
    }),
)
abilities = [trigger, *compiled]
