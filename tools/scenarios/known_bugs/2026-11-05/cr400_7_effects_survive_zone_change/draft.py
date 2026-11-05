# Wakeroot Elemental: "{G}{G}{G}{G}{G}: Untap target land you control. It becomes a 5/5 Elemental
# creature with haste. It's still a land. (This effect lasts as long as that land remains on the
# battlefield.)"  The compiled untap is kept; "It becomes a 5/5 Elemental creature with haste" is
# Riddleform's become-a-creature Seq (SET_PT, GRANT_TYPE adding 'Creature' + the subtype, so the
# land stays a land, GRANT_ABILITY), aimed at "it" = the ability's target (referent 'target'), with
# no duration role: absent is permanent, and the effect ends when the land leaves (CR 400.7).
act = compiled[0]
it = Selector(
    count=QConst(value=1),
    mode=SelectorMode.CHOOSE,
    filter=FAnd(children=()),
    zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
    referent='target',
)
become = Seq(
    steps=(
        A(Verb.SET_PT, {'power': QConst(value=5), 'target': it, 'toughness': QConst(value=5)}),
        A(Verb.GRANT_TYPE, {'target': it, 'types': ('Creature', 'Elemental')}),
        A(Verb.GRANT_ABILITY, {'ability': KeywordAbility(keyword=Keyword.HASTE), 'target': it}),
    ),
)
abilities = [
    ActivatedAbility(cost=act.cost, effect=Seq(steps=(act.effect, become))),
    compiled[1],
]
