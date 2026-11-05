# Blightbeetle (M20)
# Protection from green
# Creatures your opponents control can't have +1/+1 counters put on them.
keywords = [
    KeywordAbility(
        keyword=Keyword.PROTECTION,
        params=(FAtom(pred=FAtomPred.COLOR_HAS, color='G'),),
    ),
]
_opp_creatures = FAnd(
    children=(
        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value='Creature'),
    ),
)
no_counters = StaticAbility(
    effect=A(Verb.PREVENT_EFFECT, {
        'condition': _opp_creatures,
        'event': CounterPlacedEvent(counter_kind=CounterKind.PLUS_1_PLUS_1, filter=_opp_creatures),
    }),
)
abilities = [no_counters, *compiled]
