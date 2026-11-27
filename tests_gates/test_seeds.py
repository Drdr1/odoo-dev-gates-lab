"""Acceptance tests for the gates.

A gate counts only when a deliberate violation is rejected. Each seed under
seeds/reject is applied to a clean copy of the repository and must be rejected
with exactly its own control code. Each seed under seeds/accept must pass.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COPIED = ("addons", "tools")


def seeds(kind):
    return sorted(p.parent for p in (ROOT / "seeds" / kind).glob("*/seed.json"))


def git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=gate-test", "-c", "user.email=gate-test@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def run_gates(repo):
    return subprocess.run(
        [sys.executable, "tools/odoo_gates.py", "--base", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
    )


def codes_in(output):
    return {line.split()[0] for line in output.splitlines() if " BLOCKING " in line}


@pytest.fixture
def clean_repo(tmp_path):
    for name in COPIED:
        shutil.copytree(ROOT / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def apply_seed(repo, seed_dir):
    shutil.copytree(seed_dir / "files", repo, dirs_exist_ok=True)


def test_clean_repository_passes(clean_repo):
    result = run_gates(clean_repo)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("seed_dir", seeds("reject"), ids=lambda p: p.name)
def test_seeded_violation_is_rejected(clean_repo, seed_dir):
    meta = json.loads((seed_dir / "seed.json").read_text())
    if meta.get("ci_only"):
        pytest.skip("checked by tools/pr_meta.py, see test_pr_meta.py")
    apply_seed(clean_repo, seed_dir)
    result = run_gates(clean_repo)
    assert result.returncode == 1, f"{seed_dir.name} was NOT rejected\n{result.stdout}"
    assert codes_in(result.stdout) == set(meta["codes"]), result.stdout


@pytest.mark.parametrize("seed_dir", seeds("accept"), ids=lambda p: p.name)
def test_compliant_change_is_accepted(clean_repo, seed_dir):
    apply_seed(clean_repo, seed_dir)
    result = run_gates(clean_repo)
    assert result.returncode == 0, result.stdout


def test_every_static_control_has_a_seed():
    covered = set()
    for seed_dir in seeds("reject"):
        covered |= set(json.loads((seed_dir / "seed.json").read_text())["codes"])
    expected = {f"ODO-0{n}" for n in range(1, 9)} | {"GIT-04", "GIT-07"}
    assert expected <= covered, f"controls without a seeded violation: {expected - covered}"
