# Sorin, Vampire Lord. The compiler attached "You gain 4 life." to the planeswalker's cast carrier
# (casting Sorin would gain 4 life); it belongs to the [-2]. The carrier is the effect-less
# SpellAbility(PLANESWALKER) and the gain-life atom moves into the [-2]'s Seq.
# [+1]: Garruk, Unleashed's "up to one target creature" MODIFY_PT with "+2/+0" (toughness +0).
# [-2]: Chandra's "deals N damage to any target" loyalty shape, then the compiler's own
#       "You gain 4 life." atom.
# [-8]: GRANT_ABILITY until end of turn to each Vampire you control (tribal noun = SUBTYPE_EQ plus
#       TYPE_EQ Creature), the granted ability "{T}: Gain control of target creature." being
#       Traitorous Greed's GAIN_CONTROL without a duration (indefinite).
gain_life = compiled[0].effect
plus1 = ActivatedAbility(
    cost=Cost(parts=(CostLoyalty(delta=1),)),
    effect=A(Verb.MODIFY_PT, {
        'duration': DurationEot(),
        'power': PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(value=2)),
        'target': Selector(
            count=QAtMost(n=1),
            mode=SelectorMode.TARGET,
            filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
        ),
        'toughness': PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(value=0)),
    }),
)
minus2 = ActivatedAbility(
    cost=Cost(parts=(CostLoyalty(delta=-2),)),
    effect=Seq(steps=(
        A(Verb.DEAL_DAMAGE, {
            'amount': QConst(value=4),
            'target': Selector(
                count=QConst(value=1),
                mode=SelectorMode.TARGET,
                filter=FOr(children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value='Planeswalker'),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value='Player'),
                )),
                zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
            ),
        }),
        gain_life,
    )),
)
minus8 = ActivatedAbility(
    cost=Cost(parts=(CostLoyalty(delta=-8),)),
    effect=A(Verb.GRANT_ABILITY, {
        'ability': ActivatedAbility(
            cost=Cost(parts=(CostTap(),)),
            effect=A(Verb.GAIN_CONTROL, {
                'controller': ControllerRef.YOU,
                'target': Selector(
                    count=QConst(value=1),
                    mode=SelectorMode.TARGET,
                    filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                ),
            }),
        ),
        'duration': DurationEot(),
        'target': Selector(
            count=QUnbounded(),
            mode=SelectorMode.ALL,
            filter=FAnd(children=(
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value='Vampire'),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
            )),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
        ),
    }),
)
abilities = [plus1, minus2, minus8, SpellAbility(kind=SpellKind.PLANESWALKER)]
