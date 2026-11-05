# Keldon Raider: "When this creature enters, you may discard a card. If you do, draw a card."
# The compiler hung "If you do, draw a card." on the creature's SpellAbility as a spell effect
# (casting it would draw a card); that carrier is replaced by the plain creature carrier.
# Shape: Crypt Lurker / Jeskai Elder: Seq(OptionalEffect(X), Conditional(MAY_DONE, DRAW)),
# discard = the B5b-cont-discard MOVE_ZONE.
etb_loot = TriggeredAbility(
    event=ZoneChangeEvent(
        from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    ),
    condition=None,
    effect=Seq(steps=(
        OptionalEffect(inner=A(Verb.MOVE_ZONE, {
            'cards': Selector(
                count=QConst(value=1),
                mode=SelectorMode.CHOOSE,
                filter=FAnd(children=()),
                zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
            ),
            'controller': ControllerRef.YOU,
            'destination': Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
            'from': Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
        })),
        Conditional(
            pred=FAtom(pred=FAtomPred.MAY_DONE),
            then_effect=A(Verb.DRAW, {'amount': QConst(value=1), 'controller': ControllerRef.YOU}),
        ),
    )),
)
abilities = [etb_loot, SpellAbility(kind=SpellKind.CREATURE)]
