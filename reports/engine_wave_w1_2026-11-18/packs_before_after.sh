#!/bin/bash
# packs_before_after.sh: 215 §8 (a) for wave W1. The wave's acceptance packs, each played by the
# base checkout (the W0 follow-up, ae2190b4: the engine before W1) and by the W1 commit, both
# exported with `git archive` into $S. The five W1 known-bug packs and the Lockbox pack run through
# tools/run_scenarios.py; verification wave 7's F44 pack (Masterful Replication, mapped but not
# verified at this base) through `cardtool runpack`, as tools/scenarios/mapped/ packs are played.
S=${S:-/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad}
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=2
PACKS=$S/w1_packs
rm -rf "$PACKS" && mkdir -p "$PACKS"
for p in colossus_hammer_equip_misses_the_hammer_brought_back griffin_protector_pump_misses_the_protector_brought_back \
         watcher_of_the_spheres_pump_misses_the_watcher_stitched_back \
         brought_back_aura_cannot_enchant_the_creature_returning_with_it dub_falls_off_riddleform_when_its_animation_ends \
         diviners_lockbox_disenchanted_in_response_still_draws; do
  cp "$S/branch/tools/scenarios/$p.json" "$PACKS/"
done
MR=$S/branch/tools/scenarios/mapped/M20/masterful_replication_turns_oakenforms_host_into_a_noncreature.json
for side in base branch; do
  echo "== $side"
  ( cd "$S/$side" && nice -n 19 $PY tools/run_scenarios.py --dir "$PACKS" 2>&1 | grep -E '^(PASS|FAIL)|^     |packs passed' )
  ( cd "$S/$side" && nice -n 19 $PY tools/cards/cardtool.py runpack M20 "$MR" 2>&1 | grep -E '^(PASS|FAIL)|^     ' )
done
