# Dread Presence (M20)
# "Whenever a Swamp you control enters, choose one —
#   • You draw a card and you lose 1 life.
#   • This creature deals 2 damage to any target and you gain 2 life."
# event: Landfall's ZoneChangeEvent (B7-landfall-trigger) with the land-type noun "Swamp" = SUBTYPE_EQ Swamp +
#        TYPE_EQ Land (the guide's tribal-noun convention: subtype plus its card type; no land-type precedent parses).
# modes: Elder Gargaroth's Choose(count=QConst(1), options=(...)); each mode is a Seq in printed order.
# atoms: B5a-draw-one, B4-lose-life-n, B5b-damage-any (Shock's any-target selector), B4-gain-life-n.
swamp_enters = ZoneChangeEvent(
    from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    subject=FAnd(
        children=(
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value='Swamp'),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value='Land'),
        ),
    ),
)
any_target = Selector(
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
)
mode_draw = Seq(
    steps=(
        A(Verb.DRAW, {'amount': QConst(value=1), 'controller': ControllerRef.YOU}),
        A(Verb.LOSE_LIFE, {'amount': QConst(value=1), 'controller': ControllerRef.YOU}),
    ),
)
mode_burn = Seq(
    steps=(
        A(Verb.DEAL_DAMAGE, {'amount': QConst(value=2), 'target': any_target}),
        A(Verb.GAIN_LIFE, {'amount': QConst(value=2), 'controller': ControllerRef.YOU}),
    ),
)
swamp_trigger = TriggeredAbility(
    event=swamp_enters,
    condition=None,
    effect=Choose(count=QConst(value=1), options=(mode_draw, mode_burn)),
)
abilities = [swamp_trigger, *compiled]
