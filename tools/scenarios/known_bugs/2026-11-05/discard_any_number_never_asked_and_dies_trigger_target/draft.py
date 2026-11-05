# Cavalier of Flame.
_yours = Selector(
    count=QUnbounded(),
    mode=SelectorMode.ALL,
    filter=FAnd(children=(
        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
    )),
    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
)
# "{1}{R}: Creatures you control get +1/+0 and gain haste until end of turn."
# Basri, Devoted Paladin [-6] shape (Seq MODIFY_PT + GRANT_ABILITY, both EOT) under the
# B13-activated cost of "{1}{R}: Creatures you control get +1/+0 until end of turn.".
team_pump = ActivatedAbility(
    cost=Cost(parts=(
        CostManaColor(color='R', amount=QConst(value=1)),
        CostManaGeneric(amount=QConst(value=1)),
    )),
    effect=Seq(steps=(
        A(Verb.MODIFY_PT, {
            'duration': DurationEot(),
            'power': PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(value=1)),
            'target': _yours,
            'toughness': PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(value=0)),
        }),
        A(Verb.GRANT_ABILITY, {
            'ability': KeywordAbility(keyword=Keyword.HASTE),
            'duration': DurationEot(),
            'target': _yours,
        }),
    )),
)
# "When this creature enters, discard any number of cards, then draw that many cards."
# Kinetic Augur (B2a-draw-that-many) with "any number" = CHOOSE QUnbounded (Necromentia).
etb_rummage = TriggeredAbility(
    event=ZoneChangeEvent(
        from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    ),
    condition=None,
    effect=Seq(steps=(
        A(Verb.MOVE_ZONE, {
            'cards': Selector(
                count=QUnbounded(),
                mode=SelectorMode.CHOOSE,
                filter=FAnd(children=()),
                zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
            ),
            'controller': ControllerRef.YOU,
            'destination': Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
            'from': Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
        }),
        A(Verb.DRAW, {
            'amount': QProp(referent='event', field=QPropField.THAT_MANY_COUNT),
            'controller': ControllerRef.YOU,
        }),
    )),
)
# "When this creature dies, it deals X damage to each opponent and each planeswalker they
# control, where X is the number of land cards in your graveyard."
_x = QCount(selector=Selector(
    count=QUnbounded(),
    mode=SelectorMode.ALL,
    filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Land'),
    zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
))
dies_burn = TriggeredAbility(
    event=CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
    condition=None,
    effect=Seq(steps=(
        A(Verb.DEAL_DAMAGE, {
            'amount': _x,
            'target': Selector(
                count=QUnbounded(),
                mode=SelectorMode.ALL,
                filter=FAnd(children=()),
                zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.OPPONENT),),
            ),
        }),
        A(Verb.DEAL_DAMAGE, {
            'amount': _x,
            'target': Selector(
                count=QUnbounded(),
                mode=SelectorMode.ALL,
                filter=FAnd(children=(
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value='Planeswalker'),
                )),
                zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
            ),
        }),
    )),
)
abilities = [team_pump, etb_rummage, dies_burn, *compiled]
