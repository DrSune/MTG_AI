# Known engine bugs found by the M20 mappers, 2026-11-05

Each folder holds a mapper's draft tree for an M20 card and the pack or trace that showed the bug.
Run a pack against its draft:

    .venv/bin/python tools/cards/cardtool.py runpack M20 <pack.json> --card "<card>" --draft <draft.py>

Fixed bugs keep their folder until the M20 cards recorded `needs-atom` for them are re-mapped: the
drafts are those cards' trees. The fixes carry their own regression tests in MTG_bot/core and
tools/scenarios. Folders of bugs fixed on fix/w2-stack were removed there (CR 608.2b target
recheck, permission-cast timing, modal triggers, TARGETS_SOURCE in cast filters, the free player
target and orphaned "If you do" templates).

## Fixed (fix/w2-effects, KNOWLEDGE/2026-11-05/184)
- **cr400_7_effects_survive_zone_change** (Wakeroot Elemental): effects survived a zone change.
- **sacrifice_takes_the_target** (Sorin, Imperious Bloodlord): SACRIFICE took the target.
- **if_its_reads_the_source** (Marauding Raptor), **conditional_judged_on_source** (Overgrowth
  Elemental): conditions judged on the source, not the affected object.
- **cr611_2a_control_ends_with_granter** (Sorin, Vampire Lord); **b50_grant_ends_with_source**
  (Mu Yanling, Sky Dancer): effects ended with their source.
- **damage_trigger_binding_overrides_all** (Wildfire Elemental); **cant_block_needs_until_end_of_turn**
  (Tectonic Rift); **prevent_counter_placement_has_no_consumer** (Blightbeetle).
- **discard_any_number_never_asked_and_dies_trigger_target** (Cavalier of Flame): the dies-trigger
  half is fixed (fix/w2-stack); "discard any number" is still never asked (open, below).

## Open
- **up_to_one_none_chosen_crashes** (Cavalier of Dawn): CRASH. With no target chosen for "destroy up
  to one target ...", the next step "Its controller creates a Golem" raises "resolved to 0 players"
  (verbs.py ~1263). M20 only (not dealt).
- **graveyard_abilities_never_activatable** (Sanitarium Skeleton): abilities that work from the
  graveyard (CR 113.6k) are refused (legality.py ability_playable). M20 only.
- **"Discard any number of cards"** (Cavalier of Flame, Necromentia, Siege Striker) is never asked:
  an unbounded CHOOSE takes the whole population (the /141 deferral). Weaker than printed, never
  stronger.
- **random_order_is_fixed** (Drawn from Dreams; verified Garruk's Harbinger): "in a random order" and
  "in any order" compile alike, so the order is neither random nor chosen. Needs an IR order role.
