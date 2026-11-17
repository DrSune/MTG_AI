# KNOWN BUG (M3 mapper, 2026-11-17): FDN Angel of Finality's draft, the tree the record should hold.
# "Flying. When this creature enters, exile target player's graveyard."
# Event: the compiler's "When this creature enters". Effect: M21 Tormod's Crypt's "Exile target
# player's graveyard." (B5c-cost-sacrifice-exile: every card of the graveyard of the designated
# player, TARGET_PLAYER, to its owner's exile), the moved cards under MOVE_ZONE's `cards` role.
# A trigger never designates that player: binding.TriggerBinder._designated_player_refs reads an
# atom's ControllerRef and Zone role values and its filters, not a Selector's zones (which
# query._designated_player_refs, the spell and activation lanes, reads), so the trigger raises
# "TARGET_PLAYER needs a bound target" as it resolves. Run:
#   .venv/bin/python tools/cards/cardtool.py runpack FDN \
#     tools/scenarios/known_bugs/2026-11-17/trigger_never_designates_a_selector_zone_player/pack_exiles_the_target_players_graveyard.json \
#     --card "Angel of Finality" --draft tools/scenarios/known_bugs/2026-11-17/trigger_never_designates_a_selector_zone_player/draft.py
etb = TriggeredAbility(
    event=ZoneChangeEvent(
        from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        subject=FAtom(pred=FAtomPred.IS_SOURCE),
    ),
    condition=None,
    effect=A(Verb.MOVE_ZONE, {
        'cards': Selector(
            count=QUnbounded(),
            mode=SelectorMode.ALL,
            filter=FAnd(children=()),
            zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.TARGET_PLAYER),),
        ),
        'destination': Zone(kind=ZoneKind.EXILE, controller=ControllerRef.OWNER),
    }),
)
abilities = [etb, *compiled]
