#!/usr/bin/env bash
# The local pre-push gate. There is no CI, so this is the check.
#
#   tools/check.sh           # everything
#   tools/check.sh --quick   # skip `pytest tools` (the torch-heavy half)
#
# Green means: `pytest MTG_bot` and `pytest tools` pass, all scenario packs pass, and ruff is clean
# on MTG_bot/bench.
set -uo pipefail
cd "$(dirname "$0")/.."
export TORCH_DISABLE_NATIVE_JIT=1   # needed only on a box without python3.12-dev (CLAUDE.md)
PY=.venv/bin/python
status=0

echo "== pytest MTG_bot"
out=$($PY -m pytest MTG_bot -q --tb=no -rfE -p no:cacheprovider 2>&1); rc=$?
echo "$out" | grep -E '^(FAILED|ERROR) ' ; echo "$out" | tail -1
[ $rc = 0 ] || status=1

if [ "${1:-}" != "--quick" ]; then
  echo "== pytest tools"
  out=$($PY -m pytest tools -q --tb=short -rfE -p no:cacheprovider 2>&1); rc=$?
  echo "$out" | grep -E '^(FAILED|ERROR) ' ; echo "$out" | tail -1
  [ $rc = 0 ] || status=1
fi

echo "== scenario packs"
out=$($PY tools/run_scenarios.py 2>&1); rc=$?
echo "$out" | grep '^FAIL' ; echo "$out" | tail -1
[ $rc = 0 ] || status=1

if [ -d MTG_bot/bench ]; then
  echo "== ruff MTG_bot/bench"
  # N999 flags the package name MTG_bot itself, a repo-wide given, not a finding.
  ruff check MTG_bot/bench --ignore N999 || status=1
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "NOTE: tracked files differ from HEAD. Uncommitted edits are fine; if a CHECK wrote them, that is a bug."
  git status --short --untracked-files=no
fi
[ $status = 0 ] && echo "CHECK GREEN" || echo "CHECK RED"
exit $status
