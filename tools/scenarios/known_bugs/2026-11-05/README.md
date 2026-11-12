# Known engine bugs found by the M20 mappers, 2026-11-05

Each folder holds a mapper's draft tree for an M20 card and the pack or trace that showed the bug.
Run a pack against its draft:

    .venv/bin/python tools/cards/cardtool.py runpack M20 <pack.json> --card "<card>" --draft <draft.py>

A fixed bug keeps its folder until the M20 card recorded `needs-atom` for it is re-mapped: the
draft is that card's tree. The fixes carry their own regression tests in MTG_bot/core and
tools/scenarios. Folders of bugs fixed on fix/w2-stack were removed there (CR 608.2b target
recheck, permission-cast timing, modal triggers, TARGETS_SOURCE in cast filters, the free player
target and orphaned "If you do" templates); the nine fixed on fix/w2-effects were removed on
2026-11-06, once their cards were mapped (MTG_bot/core/test_executor_effect_fixes.py holds the
regressions; KNOWLEDGE/2026-11-05/184 lists them). graveyard_abilities_never_activatable (Sanitarium
Skeleton, CR 113.6m) was fixed and removed on 2026-11-12: its pack is
tools/scenarios/mapped/M20/sanitarium_skeleton_returns_from_the_graveyard.json, its regressions are in
MTG_bot/core/test_executor_r20c.py.

## Open (each pack fails against its draft, checked 2026-11-06)
- **up_to_one_none_chosen_crashes** (Cavalier of Dawn): CRASH. With no target chosen for "destroy up
  to one target ...", the next step "Its controller creates a Golem" raises "resolved to 0 players"
  (verbs.py ~1313). M20 only (not dealt).
- **discard_any_number_never_asked_and_dies_trigger_target** (Cavalier of Flame; also Necromentia,
  Siege Striker): "Discard any number of cards" is never asked: an unbounded CHOOSE takes the whole
  population (the /141 deferral). Weaker than printed, never stronger. The folder's dies-trigger
  half is fixed (fix/w2-stack).

random_order_is_fixed (Drawn from Dreams) was removed on 2026-11-12: "in a random order" is
MOVE_ZONE's `arrange` RANDOM, and without it the owner orders the cards (CR 401.4).
