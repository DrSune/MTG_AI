#!/usr/bin/env bash
# Start (or restart) the MTG_AI status board on 0.0.0.0:8788.
# Fully detached (setsid+nohup): survives this shell exiting.
# Pidfile: reports/monitoring/monitor.pid
set -u
cd "$(dirname "$0")/../.."
mkdir -p reports/monitoring logs
PIDF=reports/monitoring/monitor.pid

if [ -f "$PIDF" ]; then
  OLD=$(cat "$PIDF")
  if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
    kill "$OLD" && echo "monitor: killed previous pid $OLD"
    sleep 1
  fi
  rm -f "$PIDF"
fi

PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
setsid nohup "$PY" tools/training/monitor.py >> logs/monitor.log 2>&1 < /dev/null &
echo $! > "$PIDF"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "monitor: started pid $(cat "$PIDF") -> http://${IP:-localhost}:8788/ (health: /health)"
