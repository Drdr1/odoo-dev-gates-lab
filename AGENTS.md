# AGENTS.md

Rules for any AI agent that writes or reviews code in this repository. Changes
to this file need a platform owner's approval (see `.github/CODEOWNERS`),
because an agent reads its instructions from the pull request branch.

## When you review a pull request

1. Start every comment with the control code and a severity, for example
   `ODO-04 BLOCKING` or `ODO-02 SUGGESTION`.
2. `BLOCKING` means the pull request must not merge until it is fixed. Do not
   approve while one BLOCKING comment is unresolved.
3. `SUGGESTION` never blocks. Use it for performance, duplication and readability.
4. Attach a suggested change whenever the fix is mechanical.
5. Do not repeat what the `gates` check already reports. Review what a script
   cannot judge (the right-hand column below).

## Controls

| Code | Rule | The `gates` check rejects | You review |
|---|---|---|---|
| ODO-01 | Extend with `_inherit` and XPath. Never edit or copy Odoo or Enterprise code. | Files under `odoo/`, `enterprise/`. Module names without the `acme_` prefix. | Copied upstream methods pasted into a custom module. |
| ODO-02 | Odoo 18 syntax only. | `<tree>`, `attrs=`, `states=`, `name_get()`. | Other deprecated APIs. |
| ODO-03 | Every new model has access rights. Multi-company or owner-linked data has record rules. | Model with no row in `ir.model.access.csv`. `company_id` with no record rule. | Whether the groups and the rule domain are right for the data. |
| ODO-04 | No `sudo()` without a stated reason and a test. No SQL built from strings. | `sudo()` with no `# sudo:` comment. `cr.execute()` with an f-string, `%`, `+` or `.format()`. | Whether the stated reason is valid and a test covers it. |
| ODO-05 | No `cr.commit()`, no `print()`, no personal data in logs. | All three, for the field names listed in `tools/odoo_gates.py`. | Personal data reaching logs through other names. |
| ODO-06 | A field or data change bumps the version and ships a migration script. | Unchanged version. Missing `migrations/<version>/`. | Whether the migration is correct and safe to re-run. |
| ODO-07 | New business logic has `TransactionCase` tests. | New public method with no new or updated test. | Whether the tests assert the behaviour, not just call it. |
| ODO-08 | User-facing text is translatable and `i18n/ar.po` is current. | Label with no Arabic entry. | Text built by concatenation that cannot be translated. |
| GIT-03 | Branches are `feature/`, `fix/` or `hotfix/`. | Any other branch name. | |
| GIT-04 | The title is a Conventional Commit. | Any other title. | |
| GIT-05 | The pull request template is complete. | Empty sections. | Whether a risky change has a real rollback plan. |
| GIT-07 | No `.env`, keys, database dumps or files over 10 MB. | All of them. | |

## When you write code

- Run `pre-commit run --all-files` before you push. It runs the same gates as CI.
- One purpose per pull request. Add or update a test with every logic change.
- Never read or print `.env` files, keys or credentials.
