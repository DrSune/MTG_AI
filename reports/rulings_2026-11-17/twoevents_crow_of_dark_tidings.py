# FDN Crow of Dark Tidings: "Flying. When this creature enters or dies, mill two cards."
# Two triggered abilities, the enters one first, one effect (MAPPER_GUIDE, R_TWOEVENTS).
mill_two = A(Verb.MOVE_ZONE, {
    'amount': QConst(value=2),
    'controller': ControllerRef.YOU,
    'destination': Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
    'from': Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
    'journal_kind': 'MILL',
    'pop_order': 'TOP',
})
enters = TriggeredAbility(
    event=ZoneChangeEvent(
        from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    ),
    condition=None,
    effect=mill_two,
)
dies = TriggeredAbility(
    event=CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
    condition=None,
    effect=mill_two,
)
abilities = [enters, dies, *compiled]
