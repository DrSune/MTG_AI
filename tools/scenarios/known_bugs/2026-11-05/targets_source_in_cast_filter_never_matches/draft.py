# Gnarlback Rhino: "Trample" (compiled keyword) +
# "Whenever you cast a spell that targets this creature, draw a card."
# CastSpellEvent (you cast, Quirion Dryad shape) whose spell filter is TARGETS_SOURCE
# ("spells ... that target this creature", the R3-6 cost-modifier predicate).
heroic_draw = TriggeredAbility(
    event=CastSpellEvent(
        filter=FAtom(pred=FAtomPred.TARGETS_SOURCE),
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    ),
    condition=None,
    effect=A(Verb.DRAW, {'amount': QConst(value=1), 'controller': ControllerRef.YOU}),
)
abilities = [heroic_draw, *compiled]
