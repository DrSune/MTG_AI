# Chandra's Outrage: "Chandra's Outrage deals 4 damage to target creature and 2 damage to that
# creature's controller."
# Shape: ZNR Synchronized Spellcraft (B8-party-four-and-x-controller): Seq of two DEAL_DAMAGE;
# the second is the controller-of-the-target fold, a TARGET Selector over the PLAYER zone that
# reads the one creature designation's controller (selectors.py, the 16a designation face).
abilities = [
    SpellAbility(
        kind=SpellKind.INSTANT,
        effect=Seq(steps=(
            A(Verb.DEAL_DAMAGE, {
                'amount': QConst(value=4),
                'target': Selector(
                    count=QConst(value=1),
                    mode=SelectorMode.TARGET,
                    filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
                    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                ),
            }),
            A(Verb.DEAL_DAMAGE, {
                'amount': QConst(value=2),
                'target': Selector(
                    count=QConst(value=1),
                    mode=SelectorMode.TARGET,
                    filter=FAnd(children=()),
                    zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.ANY),),
                ),
            }),
        )),
    ),
]
