# FDN Garna, Bloodfist of Keld: "Whenever another creature you control dies, draw a card if it was
# attacking. Otherwise, Garna deals 1 damage to each opponent."
# Known-bug draft (M5 mapper, 2026-11-17; the card is needs-atom): the branch moved into two event
# filters on the dying creature (IS_ATTACKING / FNot(IS_ATTACKING)), a shape no ruling covers. The
# binder judges IS_ATTACKING on the dead creature from the live attack record, which it has already
# left, so the draw never triggers and every death deals the damage. pack_attacker_dies_draws.json
# fails on it.
dmg = A(Verb.DEAL_DAMAGE, {
    'amount': QConst(value=1),
    'target': Selector(
        count=QUnbounded(),
        mode=SelectorMode.ALL,
        filter=FAnd(children=()),
        zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.OPPONENT),),
    ),
})
attacking = TriggeredAbility(
    event=CreatureDiesEvent(
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.IS_ATTACKING),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            ),
        ),
    ),
    condition=None,
    effect=A(Verb.DRAW, {'amount': QConst(value=1), 'controller': ControllerRef.YOU}),
)
otherwise = TriggeredAbility(
    event=CreatureDiesEvent(
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                FNot(inner=FAtom(pred=FAtomPred.IS_ATTACKING)),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            ),
        ),
    ),
    condition=None,
    effect=dmg,
)
abilities = [attacking, otherwise, *compiled]
