# Odoo dev gates lab

Merge gates for an Odoo 18 addons repository, where **a control counts only
when a deliberate violation is rejected**.

Each control has a code. Each code has a seeded violation. Each seeded
violation is an open pull request that the `gates` check turns red, and a test
that fails the build if the gate ever stops rejecting it.

## The evidence

Open the [pull requests](../../pulls). One per seed:

| Control | Seeded violation | Expected result |
|---|---|---|
| ODO-01 | A copied and edited Enterprise file | Rejected |
| ODO-02 | List view with `<tree>` and `attrs=` | Rejected |
| ODO-03 | New model with no row in `ir.model.access.csv` | Rejected |
| ODO-04 | SQL built with an f-string, `sudo()` with no reason | Rejected |
| ODO-05 | `cr.commit()` in a loop, `print()` | Rejected |
| ODO-06 | New field, version not bumped, no migration | Rejected |
| ODO-07 | New business method with no test | Rejected |
| ODO-08 | New label with no Arabic translation | Rejected |
| GIT-04 | Pull request title that is not a Conventional Commit | Rejected |
| GIT-07 | `.env` file and a database dump | Rejected |
| none | The ODO-06 field again, done properly | **Passes** |

The last row matters as much as the others: a gate that also blocks compliant
work gets switched off.

A rejection looks like this, in the check log and as annotations on the diff:

```
ODO-05 BLOCKING addons/acme_visit_log/models/visit_log.py:34 cr.commit() breaks the transaction Odoo manages for you
ODO-05 BLOCKING addons/acme_visit_log/models/visit_log.py:35 print() is not allowed: use _logger

Rejected: 2 blocking finding(s) [ODO-05]. Fix them and push again.
```

## Reproduce it locally

```bash
pip install -r requirements-ci.txt
python -m pytest tests_gates -v
```

`tests_gates/test_seeds.py` copies the repository, applies one seed and runs
the gate. The seed must be rejected with exactly its own code and no other.
The clean seed must pass. A last test fails if any control has no seed.

## How it is enforced

| Layer | What | Where |
|---|---|---|
| Developer machine | The same gates, before the commit exists | `.pre-commit-config.yaml` |
| Pull request | Required status check `gates` | `.github/workflows/gates.yml` |
| Branch | No direct push to `main`. Only the owner updates `production`. | `rulesets/lab-*.json` |
| Rule files | Platform owner approval for anything that defines the rules | `.github/CODEOWNERS` |
| AI review | Reviewer contract: control code first, BLOCKING or SUGGESTION | `AGENTS.md`, `.github/copilot-instructions.md` |

The gates are deterministic on purpose. An AI reviewer is a useful second
layer for what a script cannot judge, and `AGENTS.md` splits each control into
"the check rejects" and "you review". It is not the only gate, because its
answers can differ between runs.

The checker (`tools/odoo_gates.py`) uses only the Python standard library and
parses Python with `ast`, not with regular expressions, so a `cr.commit()` in a
comment or a string is not a finding.

### Workflow hardening

- Actions are pinned to a commit SHA, not a tag.
- `permissions: contents: read` and `persist-credentials: false`.
- The pull request title and body reach the script through environment
  variables, never shell interpolation. A test covers a title containing shell
  characters.
- CI dependencies are installed with `--require-hashes`.

## Set it up on a new repository

```bash
git push -u origin main
./scripts/apply_rulesets.sh              # needs gh, as repository admin
./scripts/prove_direct_push_rejected.sh  # passes only if GitHub refuses the push
python scripts/open_seed_prs.py          # one pull request per seed
```

## What this lab does not prove

- **AI code review itself.** The instruction files are here. Automatic review
  and approval need a Copilot seat with code review, so
  `rulesets/org-copilot-review.json` is written but not applied.
- **Odoo.sh.** The `TransactionCase` tests are real, but they run on Odoo.sh,
  whose commit status would be a second required check next to `gates`.
- **Push rulesets.** `rulesets/org-push-hygiene.json` blocks `.env` files at
  push time. On private repositories that needs the GitHub Team plan, so here
  the same rule is enforced by the `gates` check instead.
- **Owner-only production with other users.** On a personal repository there
  is one admin, so the `production` ruleset is applied but only the
  direct-push-to-`main` rejection is demonstrated.

## Layout

```
addons/acme_visit_log/   sample Odoo 18 module the gates run on
tools/                   odoo_gates.py, pr_meta.py
seeds/reject/            one deliberate violation per control
seeds/accept/            compliant changes that must pass
tests_gates/             the acceptance tests
rulesets/                branch and push rulesets as JSON
scripts/                 apply rulesets, prove the push rejection, open seed PRs
```
