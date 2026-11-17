# KNOWN BUG (M3 mapper, 2026-11-17): FDN Hoarding Dragon's draft, the tree the record should hold.
# "Flying. When this creature enters, you may search your library for an artifact card, exile it,
# then shuffle. When this creature dies, you may put the exiled card into its owner's hand."
# Enters: M21 Solemn Simulacrum's verified optional search (OptionalEffect(Seq(SEARCH, SHUFFLE)),
# no `controller` role on SEARCH) for an artifact card, to exile (Zone(EXILE, OWNER)).
# Dies: "you may" (OptionalEffect) move "the exiled card", the card the linked enters ability
# exiled (CR 607.2a), with M20 Bag of Holding's verified IS_EXILED_WITH_SOURCE selector (an ALL:
# the card is named, not chosen), to its owner's hand.
# IS_EXILED_WITH_SOURCE counts every journalled exile whose cause is the source's card handle,
# across the card's lives (CR 400.7): a Dragon that left the battlefield and came back returns
# the first life's card too when it dies. Run:
#   .venv/bin/python tools/cards/cardtool.py runpack FDN \
#     tools/scenarios/known_bugs/2026-11-17/exiled_with_source_spans_lives/pack_a_returned_dragon_forgets_its_first_card.json \
#     --card "Hoarding Dragon" --draft tools/scenarios/known_bugs/2026-11-17/exiled_with_source_spans_lives/draft.py
etb = TriggeredAbility(
    event=ZoneChangeEvent(
        from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    ),
    condition=None,
    effect=OptionalEffect(
        inner=Seq(
            steps=(
                A(Verb.SEARCH, {
                    'cards': Selector(
                        count=QConst(value=1),
                        mode=SelectorMode.CHOOSE,
                        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value='Artifact'),
                        zones=(Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),),
                    ),
                    'destination': Zone(kind=ZoneKind.EXILE, controller=ControllerRef.OWNER),
                }),
                A(Verb.SHUFFLE, {'zone': Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU)}),
            ),
        ),
    ),
)
dies = TriggeredAbility(
    event=CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
    condition=None,
    effect=OptionalEffect(
        inner=A(Verb.MOVE_ZONE, {
            'cards': Selector(
                count=QUnbounded(),
                mode=SelectorMode.ALL,
                filter=FAtom(pred=FAtomPred.IS_EXILED_WITH_SOURCE),
                zones=(Zone(kind=ZoneKind.EXILE, controller=ControllerRef.ANY),),
            ),
            'destination': Zone(kind=ZoneKind.HAND, controller=ControllerRef.OWNER),
        }),
    ),
)
abilities = [etb, dies, *compiled]
