#!/usr/bin/env python3
"""Open one pull request per seed, so every rejection is visible on GitHub.

Each seed under seeds/reject becomes a branch and a pull request that must go
red with its control code. Each seed under seeds/accept becomes a pull request
that must go green. Needs git and the gh CLI. Run from a clean checkout of main.

    python scripts/open_seed_prs.py            # all seeds
    python scripts/open_seed_prs.py odo-05     # seeds whose name contains "odo-05"
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BODY = """## Purpose
{summary}

## Ticket
LAB-SEED

## How it was tested
`python -m pytest tests_gates` applies this same change to a clean copy and asserts the result below.

## Tool used
none

## Rollback plan
Close the pull request. It is never meant to merge.

---
**Seeded on purpose.** Expected result: {expected}
"""


def sh(*args, check=True):
    return subprocess.run(args, cwd=ROOT, check=check, text=True, capture_output=True)


def main():
    wanted = sys.argv[1] if len(sys.argv) > 1 else ""
    if sh("git", "status", "--porcelain").stdout.strip():
        sys.exit("Working tree is not clean. Commit or stash first.")
    seeds = sorted((ROOT / "seeds").glob("*/*/seed.json"))
    for seed_file in seeds:
        seed_dir = seed_file.parent
        if wanted not in seed_dir.name:
            continue
        meta = json.loads(seed_file.read_text())
        branch = meta["branch"]
        if sh("git", "ls-remote", "--exit-code", "--heads", "origin", branch, check=False).returncode == 0:
            print(f"skip   {seed_dir.name}: branch already on origin")
            continue
        sh("git", "switch", "-q", "-C", branch, "main")
        files = [p for p in (seed_dir / "files").rglob("*") if p.is_file()]
        for source in files:
            target = ROOT / source.relative_to(seed_dir / "files")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        relative = [str(p.relative_to(seed_dir / "files")) for p in files]
        sh("git", "add", "-f", "--", *relative)
        sh("git", "commit", "-q", "-m", meta["title"])
        sh("git", "push", "-q", "-u", "origin", branch)
        expected = (
            "rejected with " + ", ".join(meta["codes"]) if meta["codes"] else "all gates pass"
        )
        body = BODY.format(summary=meta["summary"], expected=expected)
        created = sh("gh", "pr", "create", "--base", "main", "--head", branch, "--title", meta["title"], "--body", body)
        print(f"opened {seed_dir.name}: {created.stdout.strip()}  ({expected})")
        sh("git", "switch", "-q", "main")
    sh("git", "switch", "-q", "main", check=False)


if __name__ == "__main__":
    main()
