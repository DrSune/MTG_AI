#!/bin/bash
# tests_on_main.sh <checkout> <label>: engine wave E3's tests and packs on one checkout. On main, a
# fresh `git archive` of 2c8eca31 gets the branch's test files copied in first (the packs are read
# from the branch). CPU-only, niced.
S=/tmp/claude-1000/-home-sune/53a867d9-979e-400a-9ce1-caf029cc7b16/scratchpad/e3
W=/home/sune/Desktop/MTG_AI/.claude/worktrees/agent-aa826eade9066c90a
PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
C=$1
export CUDA_VISIBLE_DEVICES=
export OMP_NUM_THREADS=2
if [ "$C" != "$W" ]; then
  for f in MTG_bot/core/test_executor_counters_new_object.py MTG_bot/core/test_executor_control_endpoints.py \
           MTG_bot/core/test_executor_cast_payability.py tools/audit/test_detectors.py \
           tools/test_run_scenarios.py tools/cards/test_gates.py; do
    cp $W/$f $C/$f
  done
fi
cd $C || exit 1
echo "== $2: engine tests (whole files)"
nice -n 19 $PY -m pytest MTG_bot/core/test_executor_counters_new_object.py MTG_bot/core/test_executor_control_endpoints.py \
  MTG_bot/core/test_executor_cast_payability.py -q -p no:cacheprovider -rf --tb=no 2>&1 | /usr/bin/grep -E '^FAILED|passed|failed|error'
echo "== $2: tools tests (the wave's own)"
nice -n 19 $PY -m pytest tools/audit/test_detectors.py tools/test_run_scenarios.py tools/cards/test_gates.py -q -p no:cacheprovider -rf --tb=line \
  -k 'd3_clean_after_a_death or move_of_several_cards or statics_own_look or one_top_card or proven_equivalent' 2>&1 | /usr/bin/grep -E '^FAILED|passed|failed|error|^/|^E '
echo "== $2: packs"
P=$W/tools/scenarios
nice -n 19 $PY $W/reports/engine_wave_e3_2026-11-18/runpack.py $C \
  $P/starfield_mystic_an_enchantment_you_control_counts_whoever_owns_it.json \
  $P/scavenging_ooze_that_left_the_battlefield_gets_no_counter.json \
  $P/havoc_jester_sees_its_controller_sacrifice_a_stolen_creature.json \
  $P/watcher_of_the_spheres_two_fliers_entering_at_once.json \
  $P/mapped/M21/chandra_flames_catalyst_minus_two_pays_with_an_untapped_mountain.json \
  $P/mapped/M21/chandra_flames_catalyst_minus_two_is_not_offered_without_mana_for_its_spell.json 2>&1 | cut -c1-300
