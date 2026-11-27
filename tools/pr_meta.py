#!/usr/bin/env python3
"""Pull request metadata gates: branch name (GIT-03), title (GIT-04), template (GIT-05).

Values arrive through environment variables, never through shell interpolation,
so a hostile PR title cannot inject commands into the workflow.
"""

from __future__ import annotations

import os
import re
import sys

BRANCH = re.compile(r"^(feature|fix|hotfix|copilot|dependabot)/[A-Za-z0-9._/-]+$")
TITLE = re.compile(
    r"^(feat|fix|docs|refactor|test|chore|perf|build|ci|revert)(\([a-z0-9_.-]+\))?!?: \S.*$"
)
SECTIONS = ("Purpose", "Ticket", "How it was tested", "Tool used")
BOT_PREFIXES = ("dependabot/",)


def section_text(body: str, heading: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", body, re.MULTILINE | re.DOTALL
    )
    if not match:
        return ""
    return re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL).strip()


def check(title: str, head_ref: str, body: str) -> list[tuple[str, str]]:
    findings = []
    if not BRANCH.match(head_ref):
        findings.append(
            ("GIT-03", f"branch '{head_ref}' must start with feature/, fix/ or hotfix/")
        )
    if not TITLE.match(title):
        findings.append(
            ("GIT-04", f"title '{title}' is not a Conventional Commit, for example 'feat(visit_log): add duration'")
        )
    if not head_ref.startswith(BOT_PREFIXES):
        for heading in SECTIONS:
            if not section_text(body, heading):
                findings.append(("GIT-05", f"pull request template section '{heading}' is empty"))
    return findings


def main() -> int:
    findings = check(
        os.environ.get("PR_TITLE", ""),
        os.environ.get("PR_HEAD_REF", ""),
        os.environ.get("PR_BODY", ""),
    )
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    for code, message in findings:
        print(f"{code} BLOCKING {message}")
        if annotate:
            print(f"::error title={code} BLOCKING::{message}")
    if findings:
        print(f"\nRejected: {len(findings)} blocking finding(s).")
        return 1
    print("Pull request metadata passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
