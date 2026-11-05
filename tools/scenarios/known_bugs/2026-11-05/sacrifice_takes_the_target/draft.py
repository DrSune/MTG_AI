# Sorin, Imperious Bloodlord (loyalty 4).
# [+1]: Target creature you control gains deathtouch and lifelink until end of turn. If it's a
#       Vampire, put a +1/+1 counter on it.
#       Angelheart Protector's target slot; the second keyword rides Alchemist's Gift's
#       referent-'target' selector; "If it's a Vampire" is a bare characteristics Conditional.
# [+1]: You may sacrifice a Vampire. When you do, Sorin deals 3 damage to any target and you gain
#       3 life.  Tolarian Kraken's "you may X. When you do, Y" = OptionalEffect(Seq(X, Y)).
# [-3]: You may put a Vampire creature card from your hand onto the battlefield.
#       Ugin's hand-to-battlefield MOVE_ZONE, count 1, under OptionalEffect.
it = Selector(
    count=QConst(value=1),
    mode=SelectorMode.CHOOSE,
    filter=FAnd(children=()),
    zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
    referent='target',
)
vampire = FAnd(
    children=(
        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value='Vampire'),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
    ),
)
plus1a = ActivatedAbility(
    cost=Cost(parts=(CostLoyalty(delta=1),)),
    effect=Seq(
        steps=(
            A(Verb.GRANT_ABILITY, {
                'ability': KeywordAbility(keyword=Keyword.DEATHTOUCH),
                'duration': DurationEot(),
                'target': Selector(
                    count=QConst(value=1),
                    mode=SelectorMode.TARGET,
                    filter=FAnd(
                        children=(
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                        ),
                    ),
                    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                ),
            }),
            A(Verb.GRANT_ABILITY, {
                'ability': KeywordAbility(keyword=Keyword.LIFELINK),
                'duration': DurationEot(),
                'target': it,
            }),
            Conditional(
                pred=vampire,
                then_effect=A(Verb.PUT_COUNTER, {
                    'count': QConst(value=1),
                    'counter_kind': CounterKind.PLUS_1_PLUS_1,
                    'target': it,
                }),
            ),
        ),
    ),
)
plus1b = ActivatedAbility(
    cost=Cost(parts=(CostLoyalty(delta=1),)),
    effect=OptionalEffect(
        inner=Seq(
            steps=(
                A(Verb.SACRIFICE, {
                    'target': Selector(
                        count=QConst(value=1),
                        mode=SelectorMode.CHOOSE,
                        filter=FAnd(
                            children=(
                                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value='Vampire'),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                            ),
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                }),
                A(Verb.DEAL_DAMAGE, {
                    'amount': QConst(value=3),
                    'target': Selector(
                        count=QConst(value=1),
                        mode=SelectorMode.TARGET,
                        filter=FOr(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Planeswalker'),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Player'),
                            ),
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                }),
                A(Verb.GAIN_LIFE, {'amount': QConst(value=3), 'controller': ControllerRef.YOU}),
            ),
        ),
    ),
)
minus3 = ActivatedAbility(
    cost=Cost(parts=(CostLoyalty(delta=-3),)),
    effect=OptionalEffect(
        inner=A(Verb.MOVE_ZONE, {
            'cards': Selector(
                count=QConst(value=1),
                mode=SelectorMode.CHOOSE,
                filter=vampire,
                zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
            ),
            'destination': Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        }),
    ),
)
abilities = [plus1a, plus1b, minus3, *compiled]
