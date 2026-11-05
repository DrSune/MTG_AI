# WRONG on purpose: no end of turn
destroy_land = compiled[0].effect
no_block = A(Verb.PREVENT_EFFECT, {
    'condition': FAnd(children=()),
    'event': DeclareBlockersEvent(
        filter=FAnd(children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
            FNot(inner=FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING)),
        )),
    ),
})
abilities = [SpellAbility(kind=SpellKind.SORCERY, effect=Seq(steps=(destroy_land, no_block)))]
