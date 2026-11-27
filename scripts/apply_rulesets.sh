#!/usr/bin/env bash
# Apply the two lab rulesets to the current repository. Needs the gh CLI,
# authenticated as the repository admin. Run it once, after the first push.
set -euo pipefail
repo="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
for file in rulesets/lab-main.json rulesets/lab-production.json; do
  name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$file")"
  if gh api "repos/$repo/rulesets" --jq '.[].name' | grep -Fxq "$name"; then
    echo "exists: $name"
  else
    gh api --method POST "repos/$repo/rulesets" --input "$file" --jq '"created: " + .name'
  fi
done
