# Whenever Lathril deals combat damage to a player, create that many 1/1 green Elf Warrior creature
# tokens.  (Jeskai Elder's event; "that many" is the event's amount, Garruk's Harbinger)
combat_elves = TriggeredAbility(
    event=DamageDealtEvent(
        amount=QUnbounded(),
        filter=FNot(inner=FAtom(pred=FAtomPred.IS_PERMANENT)),
        source=FAtom(pred=FAtomPred.IS_SOURCE),
        combat=True),
    condition=None,
    effect=A(Verb.CREATE_TOKEN, {
        'count': QProp(referent='event', field=QPropField.AMOUNT),
        'tokens': TokenSpec(
            name='Elf Warrior', type_line='Creature — Elf Warrior', types=('Creature',),
            subtypes=('Elf', 'Warrior'), power=QConst(value=1), toughness=QConst(value=1),
            keywords=(), abilities=(), colors=('G',)),
    }),
)
# {T}, Tap ten untapped Elves you control: Each opponent loses 10 life and you gain 10 life.
# (Shacklegeist's "Tap two untapped Spirits you control" cost part; Spirit of Malevolence's effect)
# Lathril is an Elf, but {T} taps her, so she is never one of the ten untapped Elves (CR 601.2h,
# 602.2b: each cost part is paid once; tapped for {T}, she is no longer untapped). FNot(IS_SOURCE)
# says so: without it the engine's payment taps her for both parts, so nine other Elves were enough.
tap_ten = ActivatedAbility(
    cost=Cost(parts=(
        CostTap(),
        CostTap(target=Selector(
            count=QConst(value=10), mode=SelectorMode.CHOOSE,
            filter=FAnd(children=(
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.IS_UNTAPPED),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value='Elf'),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            )),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),))),
    )),
    effect=Seq(steps=(
        A(Verb.LOSE_LIFE, {'amount': QConst(value=10), 'controller': ControllerRef.ALL_OPPONENTS}),
        A(Verb.GAIN_LIFE, {'amount': QConst(value=10), 'controller': ControllerRef.YOU}),
    )),
)
# compiled[0] is the carrier; the Menace keyword stays in compiled_keywords.
abilities = [combat_elves, tap_ten, *compiled]
