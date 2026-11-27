# Copilot instructions

This is an Odoo 18 Enterprise addons repository. The full control list is in
`AGENTS.md` at the repository root. Follow it for both code review and coding.

## Code review

- Start every comment with a control code and severity: `ODO-04 BLOCKING ...`
  or `ODO-02 SUGGESTION ...`.
- Mark as BLOCKING: secrets in code, SQL built from strings, missing access
  rights or record rules, `sudo()` without a valid reason, personal data in
  logs, logic changes without tests, behaviour changes without a README or
  CHANGELOG update, and edits to Odoo or Enterprise source.
- Mark as SUGGESTION: performance, duplication, naming and readability.
- Attach a suggested change when the fix is mechanical.
- Do not approve while any BLOCKING comment is unresolved.

## Coding

- Extend with `_inherit` and XPath only.
- Odoo 18 syntax: `<list>`, `invisible=` expressions, `display_name`.
- Every new model gets a row in `security/ir.model.access.csv`.
- Every field or data change bumps `version` and adds a migration script.
- Every new label gets an entry in `i18n/ar.po`.
- Write `TransactionCase` tests for new business logic.
