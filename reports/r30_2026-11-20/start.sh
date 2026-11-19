#!/bin/bash
# Start or resume r30 (KNOWLEDGE/2026-11-20/217): the main line, r29 arm B's save at update 945,
# continued on main's corrected code, as the transient user unit mtg-r30 with its guard
# mtg-r30-guard, from the worktree pinned at the launch commit. The learner resumes from its last
# save (launch.sh). A transient unit leaves no file behind and does not come back after a reboot:
# run this again then. Pausing is `systemctl --user stop mtg-r30 mtg-r30-guard`.
#   reports/r30_2026-11-20/start.sh
# Why a new run and not a resume of r29b: the code changed under it (zero fallback, every public
# card, the turn-so-far columns, engine waves E3, W0, W1, W3, rounds B3 and B12), so this is a new
# segment with its own registration; its v0 is its init.
set -euo pipefail
W=${W:-/home/sune/Desktop/MTG_AI-r30}
R=${R:-/home/sune/Desktop/MTG_AI/runs/selfplay}
INIT=${INIT:-/home/sune/Desktop/MTG_AI/runs/r29_looks/r29b_u945.pt}
run=$R/r30_main
unit=mtg-r30
[ -x "$W/.venv/bin/python" ] || {
  echo "$W/.venv/bin/python is not executable (ln -s /home/sune/Desktop/MTG_AI/.venv $W/.venv): nothing started" >&2
  exit 1
}
case $(systemctl --user is-active "$unit") in
  inactive|failed) systemctl --user reset-failed "$unit" 2>/dev/null || true
    # r29 arm B's flags (208 §1, 199 §1) unchanged but the seed; 217 says why each stays
    systemd-run --user --unit "$unit" --working-directory="$W" -p Nice="$(nice)" \
      -p Restart=on-failure -p RestartSec=300 -p SuccessExitStatus=143 \
      -p StandardOutput=append:"$run.out" -p StandardError=inherit \
      "$W/tools/selfplay/launch.sh" "$run" \
      --init "$INIT" --seed 30 --workers 18 --slots 16 --groups 4 \
      --gamma 1.0 --lam 1.0 --steps 139264 --epochs 1 --lr 2e-5 --wd 0.01 --clip 0.2 \
      --vclip 0.5 --vcoef 0.5 --ent 0.004 --max-grad 1.0 --target-kl 0 --mb 4096 \
      --tok-budget 98304 --infer-bf16 --teacher-iters 0 --gate-every 25 --gate-deals 1000 \
      --gate-score 0.55 --ladder-deals 500 --p-heuristic 0.15 --p-past 0.15 --p-self 0.55 \
      --coherent-share 1.0 --mix-sets M20 --mix-share 0.25 --extend-sets M20 --refresh-table \
      --pool verified --save-every 5 --progress-every 300 --mem-floor-gib 15.0 --iters 6000 ;;
  *) echo "$unit is already active: nothing started" ;;
esac
case $(systemctl --user is-active "$unit-guard") in
  inactive|failed) systemctl --user reset-failed "$unit-guard" 2>/dev/null || true
    systemd-run --user --unit "$unit-guard" --working-directory="$W" -p Nice="$(nice)" \
      "$W/.venv/bin/python" -m tools.selfplay.guard "$run" "$unit" ;;
esac
