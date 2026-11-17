# FDN Garna, Bloodfist of Keld: "Whenever another creature you control dies, draw a card if it was
# attacking. Otherwise, Garna deals 1 damage to each opponent."
# Known-bug draft (M5 mapper, 2026-11-17; the card is needs-atom): one trigger whose effect branches
# on the dying creature's attacking status. The engine judges the bare Conditional's IS_ATTACKING on
# the source (executor._conditional_subject: IS_ATTACKING is no characteristic), and IS_ATTACKING
# never reads a departed creature's LastKnown.attacking. pack_attacker_dies_draws.json fails on it.
trigger = TriggeredAbility(
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
    effect=Conditional(
        pred=FAtom(pred=FAtomPred.IS_ATTACKING),
        then_effect=A(Verb.DRAW, {'amount': QConst(value=1), 'controller': ControllerRef.YOU}),
        else_effect=A(Verb.DEAL_DAMAGE, {
            'amount': QConst(value=1),
            'target': Selector(
                count=QUnbounded(),
                mode=SelectorMode.ALL,
                filter=FAnd(children=()),
                zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.OPPONENT),),
            ),
        }),
    ),
)
abilities = [trigger, *compiled]
