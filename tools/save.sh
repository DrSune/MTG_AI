#!/usr/bin/env bash
# Commit everything and push to main. Deliberately blunt: the project's rule is that
# too many commits is always better than losing work.
#
#   tools/save.sh "what changed"
#
set -euo pipefail
cd "$(dirname "$0")/.."
msg="${1:-wip: checkpoint}"
if git diff --quiet && git diff --cached --quiet && [ -z "$(git status --porcelain)" ]; then
  echo "nothing to commit"
else
  git add -A
  git commit -m "$msg"$'\n\n'"Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
fi
git push origin main
git log --oneline -1
