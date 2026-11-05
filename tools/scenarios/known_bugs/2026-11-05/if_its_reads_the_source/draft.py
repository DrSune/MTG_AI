# Marauding Raptor.
# 1 "Creature spells you cast cost {1} less to cast." Watcher of the Spheres' CostModifier without
#   its flying conjunct.
# 2 "Whenever another creature you control enters, this creature deals 2 damage to it." Terror of
#   the Peaks' event; "it" is the entering creature, Chandra's Incinerator's 'event' referent.
# 3 "If a Dinosaur is dealt damage this way, this creature gets +2/+0 until end of turn." A bare
#   Conditional with a characteristics-only predicate is judged on the object the previous step
#   acted on (executor _conditional_subject, V11); then Hellkite Punisher's self +N/+0 EOT.
discount = CostModifier(
    filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
    controller_ref=ControllerRef.YOU,
    delta=CostDeltaReduceGeneric(amount=QConst(value=1)),
)
it = Selector(
    count=QConst(value=1),
    mode=SelectorMode.CHOOSE,
    filter=FAnd(children=()),
    zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
    referent='event',
)
me = Selector(
    count=QConst(value=1),
    mode=SelectorMode.CHOOSE,
    filter=FAtom(pred=FAtomPred.IS_SOURCE),
    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
)
trigger = TriggeredAbility(
    event=ZoneChangeEvent(
        from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        subject=FAnd(
            children=(
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            ),
        ),
    ),
    condition=None,
    effect=Seq(
        steps=(
            A(Verb.DEAL_DAMAGE, {'amount': QConst(value=2), 'target': it}),
            Conditional(
                pred=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value='Dinosaur'),
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                    ),
                ),
                then_effect=A(Verb.MODIFY_PT, {
                    'duration': DurationEot(),
                    'power': PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(value=2)),
                    'target': me,
                    'toughness': PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(value=0)),
                }),
            ),
        ),
    ),
)
abilities = [discount, trigger, *compiled]
