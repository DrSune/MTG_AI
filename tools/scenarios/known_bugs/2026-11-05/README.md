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
