# Cavalier of Dawn.
# ETB: "destroy up to one target nonland permanent" = B11-destroy-np's selector with the targeted
# "up to one" count QAtMost(1) (Frost Breath, C17); "Its controller creates a 3/3 colorless Golem
# artifact creature token." = B5b-its-controller-token (Secure the Scene / Angelic Ascension: the
# controller role is a referent='target' selector, no count role) with B11-create-tokens' Golem
# spec. Dies: the B13-dies frame + Shipwreck Dowser's return-to-hand with "artifact or enchantment".
etb = TriggeredAbility(
    event=ZoneChangeEvent(
        from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    ),
    condition=None,
    effect=Seq(steps=(
        A(Verb.DESTROY, {
            'target': Selector(
                count=QAtMost(n=1),
                mode=SelectorMode.TARGET,
                filter=FAnd(children=(
                    FAtom(pred=FAtomPred.IS_PERMANENT),
                    FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Land')),
                )),
                zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
            ),
        }),
        A(Verb.CREATE_TOKEN, {
            'controller': Selector(
                count=QConst(value=1),
                mode=SelectorMode.CHOOSE,
                filter=FAnd(children=()),
                zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
                referent='target',
            ),
            'tokens': TokenSpec(
                name='Golem',
                type_line='Artifact Creature — Golem',
                types=('Artifact', 'Creature'),
                subtypes=('Golem',),
                power=QConst(value=3),
                toughness=QConst(value=3),
                keywords=(),
                abilities=(),
            ),
        }),
    )),
)
dies = TriggeredAbility(
    event=CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
    condition=None,
    effect=A(Verb.MOVE_ZONE, {
        'cards': Selector(
            count=QConst(value=1),
            mode=SelectorMode.TARGET,
            filter=FOr(children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Artifact'),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value='Enchantment'),
            )),
            zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
        ),
        'destination': Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
    }),
)
abilities = [etb, dies, *compiled]
