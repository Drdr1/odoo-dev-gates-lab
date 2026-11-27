#!/usr/bin/env bash
# GEN-01 acceptance test: a direct push to main must be rejected by the ruleset.
# Exits 0 only when GitHub refuses the push.
set -uo pipefail
git fetch -q origin main
tmp="$(mktemp -d)"
trap 'git worktree remove --force "$tmp" >/dev/null 2>&1' EXIT
git worktree add -q --detach "$tmp" origin/main
git -C "$tmp" commit -q --allow-empty -m "chore: seeded violation, direct push to main"
if output="$(git -C "$tmp" push origin HEAD:main 2>&1)"; then
  echo "$output"
  echo "FAIL: the direct push was accepted. The ruleset is not enforcing GEN-01."
  exit 1
fi
echo "$output"
echo "PASS: GitHub rejected the direct push to main."
