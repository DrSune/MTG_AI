# Overgrowth Elemental (M20)
# s1: When this creature enters, put a +1/+1 counter on another target Elemental you control.
#     ETB shape (Dauntless Survivor B9-etb-put-counter-target); target filter: tribal noun SUBTYPE_EQ + TYPE_EQ Creature,
#     "you control" CONTROLLER_IS YOU, "another" FNot(IS_SOURCE) (Selfless Savior).
# s2: Whenever another creature you control dies, you gain 1 life.
#     CreatureDiesEvent over FAnd(CONTROLLER_IS YOU, TYPE_EQ Creature) (Basri's Lieutenant) + FNot(IS_SOURCE) for "another".
# s3: If that creature was an Elemental, put a +1/+1 counter on this creature.
#     Conditional after the life gain (Scavenging Ooze's B5b-if-was-creature-counter-gain shape: Conditional(pred=<type test>,
#     then=PUT_COUNTER on the source)); "an Elemental" = SUBTYPE_EQ Elemental + TYPE_EQ Creature.
etb = TriggeredAbility(
    event=ZoneChangeEvent(
        from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    ),
    condition=None,
    effect=A(Verb.PUT_COUNTER, {
        'count': QConst(value=1),
        'counter_kind': CounterKind.PLUS_1_PLUS_1,
        'target': Selector(
            count=QConst(value=1),
            mode=SelectorMode.TARGET,
            filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value='Elemental'),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                    FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                ),
            ),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
        ),
    }),
)
counter_on_self = A(Verb.PUT_COUNTER, {
    'count': QConst(value=1),
    'counter_kind': CounterKind.PLUS_1_PLUS_1,
    'target': Selector(
        count=QConst(value=1),
        mode=SelectorMode.CHOOSE,
        filter=FAtom(pred=FAtomPred.IS_SOURCE),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    ),
})
dies = TriggeredAbility(
    event=CreatureDiesEvent(
        filter=FAnd(
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
            A(Verb.GAIN_LIFE, {'amount': QConst(value=1), 'controller': ControllerRef.YOU}),
            Conditional(
                pred=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value='Elemental'),
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                    ),
                ),
                then_effect=counter_on_self,
            ),
        ),
    ),
)
abilities = [etb, dies, *compiled]
