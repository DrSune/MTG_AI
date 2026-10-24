#!/usr/bin/env bash
# Commit everything and push to main. Deliberately blunt: the project's rule is that
# too many commits is always better than losing work.
#
#   tools/save.sh "what changed"
#
# Two guards, both added 2026-10-24 after main went five weeks unpushed (KNOWLEDGE/PITFALLS.md):
#   - refuse to commit a file over 95 MB (GitHub rejects 100 MB, and one such blob makes main
#     unpushable until history is rewritten);
#   - after pushing, verify the remote really holds HEAD, and fail loudly if it does not.
set -euo pipefail
cd "$(dirname "$0")/.."
msg="${1:-wip: checkpoint}"
limit=$((95 * 1024 * 1024))
if git diff --quiet && git diff --cached --quiet && [ -z "$(git status --porcelain)" ]; then
  echo "nothing to commit"
else
  git add -A
  big=$(git diff --cached --name-only --diff-filter=AM -z | while IFS= read -r -d '' f; do
    if [ -f "$f" ] && [ "$(stat -c %s "$f")" -gt "$limit" ]; then echo "$f"; fi
  done)
  if [ -n "$big" ]; then
    echo "REFUSED: staged files over 95 MB (record a sha256 instead, see tools/training/CHECKPOINTS.md):" >&2
    echo "$big" >&2
    exit 1
  fi
  git commit -m "$msg"$'\n\n'"Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
fi
git push origin main
remote=$(git ls-remote origin refs/heads/main | cut -f1)
if [ "$remote" != "$(git rev-parse HEAD)" ]; then
  echo "PUSH NOT VERIFIED: origin/main is ${remote:-<none>}, HEAD is $(git rev-parse HEAD)" >&2
  exit 1
fi
git log --oneline -1
