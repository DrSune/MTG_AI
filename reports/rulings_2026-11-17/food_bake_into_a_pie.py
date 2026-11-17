# FDN Bake into a Pie: "Destroy target creature. Create a Food token."
FOOD = TokenSpec(
    name='Food',
    type_line='Artifact — Food',
    types=('Artifact',),
    subtypes=('Food',),
    power=None,
    toughness=None,
    keywords=(),
    abilities=(
        ActivatedAbility(
            cost=Cost(parts=(
                CostManaGeneric(amount=QConst(value=2)),
                CostTap(),
                CostSacrifice(target=Selector(
                    count=QConst(value=1),
                    mode=SelectorMode.CHOOSE,
                    filter=FAtom(pred=FAtomPred.IS_SOURCE),
                    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                )),
            )),
            effect=A(Verb.GAIN_LIFE, {'amount': QConst(value=3), 'controller': ControllerRef.YOU}),
        ),
    ),
)
spell = compiled[0]
abilities = [
    SpellAbility(
        kind=SpellKind.INSTANT,
        effect=Seq(steps=(spell.effect, A(Verb.CREATE_TOKEN, {'count': QConst(value=1), 'tokens': FOOD}))),
    ),
]
