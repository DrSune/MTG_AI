# Known engine bugs found by the M20 mappers, 2026-11-05

Each folder holds a mapper's draft tree for an M20 card and the pack or trace that shows the bug.
The cards are not dealt (their records are needs-atom, or the bug makes them weaker). Run a pack:

    .venv/bin/python tools/cards/cardtool.py runpack M20 <pack.json> --card "<card>" --draft <draft.py>

When a bug is fixed, its pack moves to tools/scenarios/ as a regression pack and the folder goes.

- **cr400_7_effects_survive_zone_change** (Wakeroot Elemental): STRONGER. Effects with no end, and GRANT_TYPE with DurationUntilLeaves, stay on a permanent that leaves and returns (CR 400.7: it is a new object). A bounced and replayed Forest still attacks as a 5/5 and dies to Murder. Likely any permanent one-shot effect, including a permanent gain of control.
- **sacrifice_takes_the_target** (Sorin, Imperious Bloodlord): STRONGER. In an ability that also has a target, SACRIFICE takes the targeted object instead of its controller's own choice: Sorin's +1 sacrifices a targeted opponent's creature even with no Vampire and still gains 3 life.
- **if_its_reads_the_source** (Marauding Raptor / Sorin, Imperious Bloodlord): STRONGER/WEAKER. DEAL_DAMAGE and GRANT_ABILITY do not record the object they affected, so a following "if it's / if a X is ..." is judged on the source: Raptor pumps whenever any creature enters (trace.txt); Sorin's Vampire counter never happens (pack_vamp_counter.json, with m1/sorin/draft.py).
- **up_to_one_none_chosen_crashes** (Cavalier of Dawn): CRASH (voids a game). With no target chosen for "destroy up to one target ...", the next step "Its controller creates a Golem" raises 'resolved to 0 players' (verbs.py ~1263).
- **cast_from_top_ignores_timing** (Mystic Forge): STRONGER. "You may cast ... from the top of your library" casts with no timing check (stack.cast_card): Prismite cast from the top on the opponent's turn. M21 Conspicuous Snoop uses the same form (its row is not offered today).
- **cr611_2a_control_ends_with_granter** (Sorin, Vampire Lord): WEAKER. Control gained through the granted "{T}: Gain control of target creature" ends when the Vampire that had the ability leaves; CR 611.2a: it lasts indefinitely.
- **damage_trigger_binding_overrides_all** (Wildfire Elemental): WEAKER. On a damage trigger, binding.py _ctx (~1904) binds `target` to the damage dealer (a Brash Taunter workaround) and selectors.role_handles lets it override an ALL selector: "creatures you control get +1/+0" pumps only the dealer.
- **b50_grant_ends_with_source** (Mu Yanling, Sky Dancer): WEAKER (B-50). The +2's "loses flying until your next turn" ends when Mu leaves the battlefield; the -2/-0 stays.
- **cr608_2b_no_target_recheck** (Ember Hauler): WRONG. No target legality recheck at resolution (CR 608.2b): Ember Hauler targeting itself is sacrificed for the cost and the card in the graveyard is still dealt 2 damage (probe variant `activate [0] targets=['card']`); the phantom damage event can set off damage triggers.
- **random_order_is_fixed** (Drawn from Dreams): MINOR. Cards put on the bottom "in a random order" keep their original order.

Second wave (M20 batches 5-9):

- **conditional_judged_on_source** (Overgrowth Elemental): STRONGER. A Conditional after a step that names no object (GAIN_LIFE) is judged on the ability's source, not on the dying creature (`_conditional_subject`, executor/__init__.py ~450): Overgrowth Elemental, itself an Elemental, gets a +1/+1 counter whenever any other creature of yours dies. Same family as if_its_reads_the_source.
- **modal_trigger_targets_before_mode** (Voracious Hydra, Dread Presence): WRONG (CR 700.2a, 603.3c). A modal trigger designates the target of its targeted mode when it fires and asks for the mode only at resolution, so the target is designated even when the other mode is chosen, and a targeted mode with no legal target is still offered.
- **targets_source_in_cast_filter_never_matches** (Gnarlback Rhino): WEAKER. TARGETS_SOURCE inside a CastSpellEvent filter reads the trigger's own target bindings, not the cast spell's targets, so "whenever you cast a spell that targets ~" never fires.
- **discard_any_number_never_asked_and_dies_trigger_target** (Cavalier of Flame): WEAKER. "Discard any number of cards" is never asked; the whole hand goes (selectors._choose_lift_allowed). And a dies trigger with no target binds the dead creature as `target`, so an "each ..." damage step hits the dead Cavalier.
- **prevent_counter_placement_has_no_consumer** (Blightbeetle): WEAKER. PREVENT_EFFECT on a counter-placement event registers, but PUT_COUNTER consults only replacements, so "creatures your opponents control can't have +1/+1 counters put on them" never applies.
- **graveyard_abilities_never_activatable** (Sanitarium Skeleton): WEAKER, plus a costed no-op row. Abilities that work from the graveyard (CR 113.6k) are refused (legality.py ~1183 ability_playable); the same row is offered on the battlefield, where it pays {2}{B} and does nothing.
- **cant_block_needs_until_end_of_turn** (Tectonic Rift): WEAKER. A spell's "can't block" effect applies only with an until-end-of-turn duration; permanent or until-your-next-turn durations never apply (seen with the deliberately wrong drafts).
