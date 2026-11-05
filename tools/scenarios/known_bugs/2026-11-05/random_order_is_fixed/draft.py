# Drawn from Dreams: "Look at the top seven cards of your library. Put two of them into your hand
# and the rest on the bottom of your library in a random order."  See the Truth's compiled shape:
# LOOK_AT, then the sentence's own Seq of a ONE_OF pick (here k=2, the T2 k-of-n lane) into the
# hand and the REST onto the library bottom (Garruk's Harbinger: "in a random order" is the same
# REST-to-bottom move).
top = Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU, position=ZonePosition.TOP)
effect = Seq(
    steps=(
        A(Verb.LOOK_AT, {'controller': ControllerRef.YOU, 'count': QConst(value=7)}),
        Seq(
            steps=(
                A(Verb.MOVE_ZONE, {
                    'cards': Selector(
                        count=QConst(value=2),
                        mode=SelectorMode.ONE_OF,
                        filter=FAnd(children=()),
                        zones=(top,),
                    ),
                    'destination': Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                }),
                A(Verb.MOVE_ZONE, {
                    'cards': Selector(
                        count=QConst(value=1),
                        mode=SelectorMode.REST,
                        filter=FAnd(children=()),
                        zones=(top,),
                    ),
                    'destination': Zone(
                        kind=ZoneKind.LIBRARY,
                        controller=ControllerRef.YOU,
                        position=ZonePosition.BOTTOM,
                    ),
                }),
            ),
        ),
    ),
)
abilities = [SpellAbility(kind=SpellKind.SORCERY, effect=effect)]
