# Ember Hauler: "{1}, Sacrifice this creature: It deals 2 damage to any target."
# Shape: Silent Dart's "{4}, {T}, Sacrifice this artifact: It deals 3 damage to target creature."
# (B5c-cost-sacrifice-dmg) without {T}, with Shock's "any target" selector (B5b-damage-any).
ability = ActivatedAbility(
    cost=Cost(parts=(
        CostManaGeneric(amount=QConst(value=1)),
        CostSacrifice(target=Selector(
            count=QConst(value=1),
            mode=SelectorMode.CHOOSE,
            filter=FAnd(children=(
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FAtom(pred=FAtomPred.IS_SOURCE),
            )),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
        )),
    )),
    effect=A(Verb.DEAL_DAMAGE, {
        'amount': QConst(value=2),
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
)
abilities = [ability, *compiled]
