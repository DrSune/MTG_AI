#!/usr/bin/env bash
# The local pre-push gate (added 2026-10-24). There is no CI, so this is the check.
#
#   tools/check.sh           # everything: ~1 min without checkpoints, ~9 min with them
#   tools/check.sh --quick   # skip `pytest tools` (the slow, torch-heavy half)
#
# Green means: the default `pytest MTG_bot` fails ONLY the two by-design gate tests (CLAUDE.md),
# `pytest tools` is clean, all scenario packs pass, and ruff is clean on MTG_bot/bench.
set -uo pipefail
cd "$(dirname "$0")/.."
export TORCH_DISABLE_NATIVE_JIT=1   # until python3.12-dev is installed (CLAUDE.md)
PY=.venv/bin/python
status=0
expected_fail=$'MTG_bot/strategic_brain/test_model.py::test_no_parameter_is_orphaned_from_the_architecture\nMTG_bot/strategic_brain/test_model.py::test_reasoning_loop_can_actually_iterate'

echo "== pytest MTG_bot"
out=$($PY -m pytest MTG_bot -q --tb=no -rf -p no:cacheprovider 2>&1)
echo "$out" | tail -1
failed=$(echo "$out" | sed -n 's/^FAILED \([^ ]*\).*/\1/p' | sort)
if [ "$failed" != "$expected_fail" ]; then
  echo "UNEXPECTED failure set (only the two D3/D11 gates may fail):"
  diff <(echo "$expected_fail") <(echo "$failed") | sed -n 's/^> /  new failure: /p; s/^< /  gate now passes (update CLAUDE.md): /p'
  status=1
fi

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
