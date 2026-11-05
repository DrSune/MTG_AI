# Mu Yanling, Sky Dancer (M20). "[+2]: Until your next turn, up to one target creature gets -2/-0
# and loses flying." Garruk, Unleashed's loyalty +1 shape (B5c-loyalty-pt-trample: a Seq of
# MODIFY_PT and a keyword change over one "up to one target creature" selector) with Rookie
# Mistake's "-2/-0" (DECREASE 2 / DECREASE 0), Soul Sear's LOSE_ABILITY for "loses flying", and
# DurationUntilNextTurn for "until your next turn" on both steps. The compiled [-3] and [-8] and
# the planeswalker carrier are kept, in printed order after the [+2].
target = Selector(
    count=QAtMost(n=1),
    mode=SelectorMode.TARGET,
    filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
)
plus_two = ActivatedAbility(
    cost=Cost(parts=(CostLoyalty(delta=2),)),
    effect=Seq(
        steps=(
            A(Verb.MODIFY_PT, {
                'duration': DurationUntilNextTurn(),
                'power': PtDelta(direction=PtDirection.DECREASE, magnitude=QConst(value=2)),
                'target': target,
                'toughness': PtDelta(direction=PtDirection.DECREASE, magnitude=QConst(value=0)),
            }),
            A(Verb.LOSE_ABILITY, {
                'ability': KeywordAbility(keyword=Keyword.FLYING),
                'duration': DurationUntilNextTurn(),
                'target': target,
            }),
        ),
    ),
)
abilities = [plus_two, *compiled]
