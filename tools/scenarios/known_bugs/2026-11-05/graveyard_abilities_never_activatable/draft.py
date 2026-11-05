# Sanitarium Skeleton: "{2}{B}: Return this card from your graveyard to your hand."
# The effect moves the source out of the graveyard, so the ability functions only
# there (CR 113.6k). Self-in-graveyard selector as in Silversmote Ghoul.
act = ActivatedAbility(
    cost=Cost(parts=(
        CostManaColor(color='B', amount=QConst(value=1)),
        CostManaGeneric(amount=QConst(value=2)),
    )),
    effect=A(Verb.MOVE_ZONE, {
        'cards': Selector(
            count=QConst(value=1),
            mode=SelectorMode.CHOOSE,
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
            zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
        ),
        'destination': Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
    }),
)
abilities = [act, *compiled]
