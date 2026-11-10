#!/bin/bash
# Start a registered run, or continue it if it has saved state. Made to sit under a systemd unit
# with Restart=on-failure, so a run that dies (memory floor, crash, kill) comes back by itself
# and one that was stopped by hand resumes with a plain `systemctl --user start`.
#
#   tools/selfplay/launch.sh RUN_DIR LEARNER-ARGS...      (from the pinned worktree)
#
# Two safety rails, neither a tuning knob:
# - it waits until NEED_GIB of memory is available (default 60: the run takes about 35 and its
#   floor is 15), so it yields to an LLM engine on this box and returns when the engine is gone;
# - the allocator setting without which one PPO update reserves 54 GiB instead of 22
#   (KNOWLEDGE/2026-11-10/189 §1).
run=$1
shift
need=${NEED_GIB:-60}
avail() { awk '/MemAvailable/ {print int($2 / 1048576)}' /proc/meminfo; }
if [ "$(avail)" -lt "$need" ]; then
  echo "{\"t\": $(date +%s), \"event\": \"launch_wait\", \"avail_gib\": $(avail), \"need_gib\": $need}"
  while [ "$(avail)" -lt "$need" ]; do sleep 120; done
fi
[ -f "$run/state.pkl" ] && set -- "$@" --resume "$run"
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}
exec .venv/bin/python -m tools.selfplay.learner --run "$run" "$@"
