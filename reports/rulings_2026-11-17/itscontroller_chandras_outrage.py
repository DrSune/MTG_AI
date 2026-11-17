# M20 Chandra's Outrage: "Chandra's Outrage deals 4 damage to target creature and 2 damage to that
# creature's controller." The recipient is M20 Chandra, Flame's Fury's verified -2 form: every
# player who controls the target (MAPPER_GUIDE, R_ITSCONTROLLER).
its_controller = Selector(
    count=QUnbounded(),
    mode=SelectorMode.ALL,
    filter=FAtom(
        pred=FAtomPred.CONTROLLER_IS,
        who=Selector(
            count=QConst(value=1),
            mode=SelectorMode.CHOOSE,
            filter=FAnd(children=()),
            zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
            referent='target',
        ),
    ),
    zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.ANY),),
)
abilities = [
    SpellAbility(
        kind=SpellKind.INSTANT,
        effect=Seq(steps=(
            A(Verb.DEAL_DAMAGE, {
                'amount': QConst(value=4),
                'target': Selector(
                    count=QConst(value=1),
                    mode=SelectorMode.TARGET,
                    filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                ),
            }),
            A(Verb.DEAL_DAMAGE, {'amount': QConst(value=2), 'target': its_controller}),
        )),
    ),
]
