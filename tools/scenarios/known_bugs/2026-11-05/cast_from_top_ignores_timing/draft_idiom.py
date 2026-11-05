# Mystic Forge in the compiler's permission-row idiom (Radha, Heart of Keld / Conspicuous Snoop):
# free activated abilities whose effect is an optional LOOK_AT / CAST from the top of the library.
# Diagnostic draft: used to show how the engine plays the idiom, not written.
look = ActivatedAbility(
    cost=Cost(),
    effect=OptionalEffect(inner=A(Verb.LOOK_AT, {'controller': ControllerRef.YOU, 'count': QConst(value=1)})),
)
cast_top = ActivatedAbility(
    cost=Cost(),
    effect=OptionalEffect(inner=A(Verb.CAST, {
        'source': Selector(
            count=QConst(value=1),
            mode=SelectorMode.CHOOSE,
            filter=FOr(children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Artifact'),
                FNot(inner=FAtom(pred=FAtomPred.COLOR_COUNT_GE, count=QConst(value=1))),
            )),
            zones=(Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU, position=ZonePosition.TOP),),
        ),
    })),
)
exile_top = ActivatedAbility(
    cost=Cost(parts=(CostTap(), CostLife(amount=QConst(value=1)))),
    effect=A(Verb.MOVE_ZONE, {
        'amount': QConst(value=1),
        'controller': ControllerRef.YOU,
        'destination': Zone(kind=ZoneKind.EXILE, controller=ControllerRef.YOU),
        'from': Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
        'pop_order': 'TOP',
    }),
)
abilities = [look, cast_top, exile_top, *compiled]
