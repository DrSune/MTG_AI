# R_FOOD
FOOD = TokenSpec(
    name='Food', type_line='Artifact — Food', types=('Artifact',), subtypes=('Food',),
    power=None, toughness=None, keywords=(),
    abilities=(ActivatedAbility(
        cost=Cost(parts=(CostManaGeneric(amount=QConst(value=2)), CostTap(), CostSacrifice(
            target=Selector(
                count=QConst(value=1), mode=SelectorMode.CHOOSE,
                filter=FAtom(pred=FAtomPred.IS_SOURCE),
                zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),))))),
        effect=A(Verb.GAIN_LIFE, {'amount': QConst(value=3), 'controller': ControllerRef.YOU})),),
)
create_food = A(Verb.CREATE_TOKEN, {'count': QConst(value=1), 'tokens': FOOD})

SELF = Selector(
    count=QConst(value=1), mode=SelectorMode.CHOOSE, filter=FAtom(pred=FAtomPred.IS_SOURCE),
    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),))
# Raid — At the beginning of your end step, if you attacked this turn, create a Food token.
# The intervening "if" is FDN Goblin Boarders' verified Raid condition.
raid = TriggeredAbility(
    event=TurnPhaseEvent(
        phase=Phase.END_TURN,
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
    condition=FAnd(children=(
        FAtom(pred=FAtomPred.TURN_OF, who=ControllerRef.YOU),
        FAtom(
            pred=FAtomPred.EVENT_THIS_TURN,
            count=QConst(value=1),
            event=DeclareAttackersEvent(filter=FAnd(children=()))),
    )),
    effect=create_food,
)
# {2}{B}, Sacrifice this enchantment: Target opponent loses X life, where X is the amount of life
# you gained this turn.
snack = ActivatedAbility(
    cost=Cost(parts=(
        CostManaColor(color='B', amount=QConst(value=1)),
        CostManaGeneric(amount=QConst(value=2)),
        CostSacrifice(target=SELF),
    )),
    effect=A(Verb.LOSE_LIFE, {
        'amount': QThisTurn(kind=ThisTurnKind.LIFE_GAINED, referent=ControllerRef.YOU),
        'controller': ControllerRef.TARGET_OPPONENT,
    }),
)
abilities = [raid, snack, *compiled]
