#!/usr/bin/env python3
"""Deterministic merge gates for an Odoo 18 addons repository.

Every finding carries a control code (ODO-01 ... ODO-08, GIT-07) and makes the
process exit 1, so the same command works as a pre-commit hook and as a
required status check. Standard library only: nothing to install, nothing to
trust.

Usage:
    python tools/odoo_gates.py                 # static checks only
    python tools/odoo_gates.py --base origin/main   # + checks that compare to the base
"""

from __future__ import annotations

import argparse
import ast
import csv
import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# --- repository policy (edit here, reviewed through CODEOWNERS) -------------
ADDONS_DIR = "addons"
MODULE_PREFIX = "acme_"
VENDOR_DIRS = ("odoo", "enterprise", "themes")  # upstream code: never edited or copied
FIXTURE_DIRS = ("seeds/",)  # seeded violations used by the self-test
MAX_FILE_MB = 10
FORBIDDEN_GLOBS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore",
    "*.sql", "*.sql.gz", "*.dump", "*.bak",
)
ALLOWED_NAMES = (".env.example",)
SENSITIVE_NAMES = {
    "email", "email_from", "phone", "mobile", "vat", "password", "passwd",
    "national_id", "iban", "birthdate", "street", "token", "access_token",
}
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
LOGGER_NAMES = {"_logger", "logger", "log"}
MODEL_BASES = {"Model", "TransientModel"}


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    path: str
    line: int
    message: str


# --- git helpers -------------------------------------------------------------
def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return proc.stdout.decode("utf-8", "replace")


def repo_files(root: Path) -> list[str]:
    out = _git(root, "ls-files", "-co", "--exclude-standard", "-z")
    if out is None:
        paths = [
            str(p.relative_to(root)).replace(os.sep, "/")
            for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts
        ]
    else:
        paths = [p for p in out.split("\0") if p]
    return sorted(p for p in paths if (root / p).is_file())


def resolve_base(root: Path, base: str) -> str:
    merge_base = _git(root, "merge-base", base, "HEAD")
    return merge_base.strip() if merge_base and merge_base.strip() else base


def changed_paths(root: Path, base: str) -> set[str]:
    tracked = _git(root, "diff", "--name-only", base) or ""
    untracked = _git(root, "ls-files", "-o", "--exclude-standard") or ""
    return {p for p in (tracked + "\n" + untracked).splitlines() if p}


def show(root: Path, base: str, path: str) -> str | None:
    return _git(root, "show", f"{base}:{path}")


# --- parsing helpers ---------------------------------------------------------
def parse(source: str) -> ast.AST | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def read(root: Path, path: str) -> str:
    return (root / path).read_text(encoding="utf-8", errors="replace")


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _class_attr(cls: ast.ClassDef, name: str) -> ast.AST | None:
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return stmt.value
    return None


def _is_model_class(cls: ast.ClassDef) -> bool:
    for base in cls.bases:
        if isinstance(base, ast.Attribute) and base.attr in MODEL_BASES:
            return True
    return False


def _field_call(value: ast.AST) -> ast.Call | None:
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and isinstance(value.func.value, ast.Name)
        and value.func.value.id == "fields"
    ):
        return value
    return None


def class_fields(cls: ast.ClassDef) -> dict[str, ast.Call]:
    found: dict[str, ast.Call] = {}
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            call = _field_call(stmt.value)
            if isinstance(target, ast.Name) and call is not None:
                found[target.id] = call
    return found


def model_key(cls: ast.ClassDef) -> str:
    name = _const_str(_class_attr(cls, "_name"))
    inherit = _const_str(_class_attr(cls, "_inherit"))
    return name or inherit or cls.name


def field_signature(source: str | None) -> set[tuple[str, str, str]]:
    tree = parse(source) if source else None
    if tree is None:
        return set()
    signature = set()
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for field, call in class_fields(cls).items():
            signature.add((model_key(cls), field, call.func.attr))
    return signature


def function_names(source: str | None) -> set[str]:
    tree = parse(source) if source else None
    if tree is None:
        return set()
    return {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
    }


def manifest_of(source: str | None) -> dict:
    if not source:
        return {}
    try:
        value = ast.literal_eval(source)
    except (ValueError, SyntaxError):
        return {}
    return value if isinstance(value, dict) else {}


def _is_cursor(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr in ("cr", "_cr")
    if isinstance(node, ast.Name):
        return node.id in ("cr", "_cr")
    return False


# --- checks ------------------------------------------------------------------
def check_git_07(root: Path, files: list[str]) -> list[Finding]:
    findings = []
    for path in files:
        if path.startswith(FIXTURE_DIRS):
            continue
        name = path.rsplit("/", 1)[-1]
        if name not in ALLOWED_NAMES and any(
            fnmatch.fnmatch(name, glob) for glob in FORBIDDEN_GLOBS
        ):
            findings.append(
                Finding("GIT-07", path, 1, "environment, key or database dump file must not be committed")
            )
        size_mb = (root / path).stat().st_size / (1024 * 1024)
        if size_mb > MAX_FILE_MB:
            findings.append(
                Finding("GIT-07", path, 1, f"file is {size_mb:.1f} MB, limit is {MAX_FILE_MB} MB")
            )
    return findings


def check_odo_01(files: list[str]) -> list[Finding]:
    findings = []
    seen_modules = set()
    for path in files:
        top = path.split("/", 1)[0]
        if top in VENDOR_DIRS:
            findings.append(
                Finding("ODO-01", path, 1, "Odoo or Enterprise source is never edited or copied: extend with _inherit and XPath")
            )
        parts = path.split("/")
        if parts[0] == ADDONS_DIR and len(parts) > 2 and parts[1] not in seen_modules:
            seen_modules.add(parts[1])
            if not parts[1].startswith(MODULE_PREFIX):
                findings.append(
                    Finding("ODO-01", f"{ADDONS_DIR}/{parts[1]}", 1, f"custom module name must start with '{MODULE_PREFIX}'")
                )
    return findings


XML_ODO_02 = (
    (re.compile(r"<tree[\s>/]"), "<tree> is Odoo 17 syntax: use <list>"),
    (re.compile(r"</tree>"), "</tree> is Odoo 17 syntax: use </list>"),
    (re.compile(r"\battrs\s*="), "attrs= was removed: use invisible=/readonly=/required= expressions"),
    (re.compile(r"\bstates\s*="), "states= was removed: use an invisible= expression"),
    (re.compile(r'name="view_mode"[^>]*>[^<]*\btree\b'), "view_mode 'tree' is Odoo 17 syntax: use 'list'"),
)


def check_odo_02(root: Path, module_files: list[str]) -> list[Finding]:
    findings = []
    for path in module_files:
        if path.endswith(".xml"):
            for number, line in enumerate(read(root, path).splitlines(), 1):
                for pattern, message in XML_ODO_02:
                    if pattern.search(line):
                        findings.append(Finding("ODO-02", path, number, message))
        elif path.endswith(".py"):
            tree = parse(read(root, path))
            for node in ast.walk(tree) if tree else ():
                if isinstance(node, ast.FunctionDef) and node.name == "name_get":
                    findings.append(
                        Finding("ODO-02", path, node.lineno, "name_get() was removed: compute display_name instead")
                    )
    return findings


def new_models(root: Path, module_files: list[str]) -> list[tuple[str, str, int, bool]]:
    """(model name, path, line, has company_id) for every model the module creates."""
    models = []
    for path in module_files:
        if not path.endswith(".py"):
            continue
        tree = parse(read(root, path))
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)) if tree else ():
            if not _is_model_class(cls):
                continue
            name = _const_str(_class_attr(cls, "_name"))
            inherit_node = _class_attr(cls, "_inherit")
            inherit = _const_str(inherit_node)
            inherit_list = (
                [_const_str(e) for e in inherit_node.elts]
                if isinstance(inherit_node, (ast.List, ast.Tuple))
                else []
            )
            if not name or name == inherit or name in inherit_list:
                continue
            models.append((name, path, cls.lineno, "company_id" in class_fields(cls)))
    return models


def check_odo_03(root: Path, module: str, module_files: list[str]) -> list[Finding]:
    findings = []
    models = new_models(root, module_files)
    if not models:
        return findings
    manifest = manifest_of(read(root, f"{module}/__manifest__.py"))
    data = set(manifest.get("data", []))
    csv_rel = "security/ir.model.access.csv"
    csv_path = f"{module}/{csv_rel}"
    granted = set()
    if csv_path in module_files:
        with open(root / csv_path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                granted.add((row.get("model_id:id") or "").split(".")[-1].strip())
        if csv_rel not in data:
            findings.append(Finding("ODO-03", csv_path, 1, "ir.model.access.csv is not loaded by __manifest__.py"))
    xml_sources = {p: read(root, p) for p in module_files if p.endswith(".xml")}
    for name, path, line, has_company in models:
        external_id = "model_" + name.replace(".", "_")
        if external_id not in granted:
            findings.append(
                Finding("ODO-03", path, line, f"new model {name} has no row in ir.model.access.csv ({external_id})")
            )
        if has_company and not any(
            "ir.rule" in source and external_id in source
            and p[len(module) + 1:] in data
            for p, source in xml_sources.items()
        ):
            findings.append(
                Finding("ODO-03", path, line, f"model {name} has company_id but no multi-company record rule")
            )
    return findings


def check_odo_04_05(root: Path, module_files: list[str]) -> list[Finding]:
    findings = []
    for path in (p for p in module_files if p.endswith(".py")):
        source = read(root, path)
        lines = source.splitlines()
        for number, line in enumerate(lines, 1):
            code = line.split("#", 1)[0]
            if ".sudo(" in code:
                previous = lines[number - 2].strip() if number > 1 else ""
                if "# sudo:" not in line and not previous.startswith("# sudo:"):
                    findings.append(
                        Finding("ODO-04", path, number, "sudo() needs a '# sudo: <reason>' comment on or above the line")
                    )
        tree = parse(source)
        for node in ast.walk(tree) if tree else ():
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                findings.append(Finding("ODO-05", path, node.lineno, "print() is not allowed: use _logger"))
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr == "commit" and _is_cursor(func.value):
                findings.append(
                    Finding("ODO-05", path, node.lineno, "cr.commit() breaks the transaction Odoo manages for you")
                )
            if func.attr == "execute" and _is_cursor(func.value) and node.args:
                query = node.args[0]
                built = isinstance(query, (ast.JoinedStr, ast.BinOp)) or (
                    isinstance(query, ast.Call)
                    and isinstance(query.func, ast.Attribute)
                    and query.func.attr == "format"
                )
                if built:
                    findings.append(
                        Finding("ODO-04", path, node.lineno, "SQL built from strings: pass parameters to cr.execute() or use the ORM")
                    )
            if (
                func.attr in LOG_METHODS
                and isinstance(func.value, ast.Name)
                and func.value.id in LOGGER_NAMES
            ):
                for arg in node.args[1:] + [k.value for k in node.keywords]:
                    for sub in ast.walk(arg):
                        leaked = (
                            sub.attr if isinstance(sub, ast.Attribute)
                            else sub.id if isinstance(sub, ast.Name) else None
                        )
                        if leaked in SENSITIVE_NAMES:
                            findings.append(
                                Finding("ODO-05", path, node.lineno, f"personal data in a log message ({leaked})")
                            )
    return findings


def check_odo_06_07(
    root: Path, module: str, module_files: list[str], base: str | None, changed: set[str]
) -> list[Finding]:
    findings = []
    tests = [p for p in module_files if re.fullmatch(rf"{re.escape(module)}/tests/test_\w+\.py", p)]
    has_transaction_case = any("TransactionCase" in read(root, p) for p in tests)
    created = new_models(root, module_files)
    if created and not has_transaction_case:
        name, path, line, _ = created[0]
        findings.append(Finding("ODO-07", path, line, f"model {name} has no TransactionCase tests in {module}/tests/"))
    if base is None:
        return findings

    mine = {p for p in changed if p.startswith(module + "/")}
    model_changes = sorted(p for p in mine if p.startswith(f"{module}/models/") and p.endswith(".py"))
    fields_changed = []
    new_functions: dict[str, set[str]] = {}
    for path in model_changes:
        before = show(root, base, path)
        after = read(root, path) if (root / path).is_file() else None
        if before is not None and field_signature(before) != field_signature(after):
            fields_changed.append(path)
        added = function_names(after) - function_names(before)
        if added:
            new_functions[path] = added
    data_changed = sorted(p for p in mine if p.startswith(f"{module}/data/"))

    manifest_path = f"{module}/__manifest__.py"
    before_manifest = manifest_of(show(root, base, manifest_path))
    after_manifest = manifest_of(read(root, manifest_path))
    version = str(after_manifest.get("version", ""))
    if before_manifest and (fields_changed or data_changed):
        trigger = (fields_changed + data_changed)[0]
        if str(before_manifest.get("version", "")) == version:
            findings.append(
                Finding("ODO-06", manifest_path, 1, f"fields or data changed in {trigger} but version is still {version}")
            )
        elif fields_changed and not any(
            p.startswith(f"{module}/migrations/{version}/") and p.endswith(".py") for p in module_files
        ):
            findings.append(
                Finding("ODO-06", fields_changed[0], 1, f"field change needs a migration script in {module}/migrations/{version}/")
            )

    tests_changed = any(p in mine for p in tests)
    if new_functions and not tests_changed:
        path, names = sorted(new_functions.items())[0]
        findings.append(
            Finding("ODO-07", path, 1, f"new business logic ({', '.join(sorted(names))}) without a new or updated test")
        )
    return findings


PO_ENTRY = re.compile(r'^msgid "(.*)"\nmsgstr "(.*)"$', re.MULTILINE)
XML_LABEL = re.compile(r'\b(?:string|placeholder|confirm)="([^"]+)"')
MENU_NAME = re.compile(r'<menuitem\b[^>]*\bname="([^"]+)"')


def _default_label(field_name: str) -> str:
    for suffix in ("_ids", "_id"):
        if field_name.endswith(suffix):
            field_name = field_name[: -len(suffix)]
            break
    return field_name.replace("_", " ").title()


def translatable_strings(root: Path, module_files: list[str]) -> list[tuple[str, str, int]]:
    strings = []
    for path in module_files:
        if "/tests/" in path or "/migrations/" in path:
            continue
        if path.endswith(".xml"):
            for number, line in enumerate(read(root, path).splitlines(), 1):
                for pattern in (XML_LABEL, MENU_NAME):
                    strings += [(m, path, number) for m in pattern.findall(line)]
        elif path.endswith(".py"):
            tree = parse(read(root, path))
            for node in ast.walk(tree) if tree else ():
                if isinstance(node, ast.ClassDef) and _is_model_class(node):
                    for field, call in class_fields(node).items():
                        keywords = {k.arg: k.value for k in call.keywords}
                        label = _const_str(keywords.get("string")) or _default_label(field)
                        strings.append((label, path, call.lineno))
                        if _const_str(keywords.get("help")):
                            strings.append((_const_str(keywords["help"]), path, call.lineno))
                        selection = keywords.get("selection") or (call.args[0] if call.args else None)
                        if call.func.attr == "Selection" and isinstance(selection, (ast.List, ast.Tuple)):
                            for option in selection.elts:
                                if isinstance(option, ast.Tuple) and len(option.elts) == 2:
                                    text = _const_str(option.elts[1])
                                    if text:
                                        strings.append((text, path, option.lineno))
                if isinstance(node, ast.Call) and node.args:
                    func = node.func
                    is_gettext = (isinstance(func, ast.Name) and func.id in ("_", "_lt")) or (
                        isinstance(func, ast.Attribute) and func.attr == "_"
                    )
                    text = _const_str(node.args[0])
                    if is_gettext and text:
                        strings.append((text, path, node.lineno))
    return strings


def check_odo_08(root: Path, module: str, module_files: list[str]) -> list[Finding]:
    strings = translatable_strings(root, module_files)
    if not strings:
        return []
    po_path = f"{module}/i18n/ar.po"
    if po_path not in module_files:
        return [Finding("ODO-08", module, 1, "module has user-facing text but no i18n/ar.po")]
    translated = {
        msgid.replace('\\"', '"')
        for msgid, msgstr in PO_ENTRY.findall(read(root, po_path))
        if msgid and msgstr
    }
    findings = []
    reported = set()
    for text, path, line in strings:
        if text not in translated and text not in reported:
            reported.add(text)
            findings.append(Finding("ODO-08", path, line, f'"{text}" has no Arabic translation in i18n/ar.po'))
    return findings


# --- runner ------------------------------------------------------------------
def run(root: Path, base: str | None) -> list[Finding]:
    files = repo_files(root)
    changed: set[str] = set()
    if base is not None:
        base = resolve_base(root, base)
        changed = changed_paths(root, base)
    findings = check_git_07(root, files) + check_odo_01(files)
    modules = sorted(
        path[: -len("/__manifest__.py")]
        for path in files
        if path.startswith(ADDONS_DIR + "/") and path.count("/") == 2 and path.endswith("/__manifest__.py")
    )
    for module in modules:
        module_files = [p for p in files if p.startswith(module + "/")]
        findings += check_odo_02(root, module_files)
        findings += check_odo_03(root, module, module_files)
        findings += check_odo_04_05(root, module_files)
        findings += check_odo_06_07(root, module, module_files, base, changed)
        findings += check_odo_08(root, module, module_files)
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--base", default=None, help="base ref to compare with (enables ODO-06 and the diff part of ODO-07)")
    args = parser.parse_args(argv)
    findings = run(Path(args.root).resolve(), args.base)
    annotate = os.environ.get("GITHUB_ACTIONS") == "true"
    for finding in findings:
        print(f"{finding.code} BLOCKING {finding.path}:{finding.line} {finding.message}")
        if annotate:
            print(f"::error file={finding.path},line={finding.line},title={finding.code} BLOCKING::{finding.message}")
    if findings:
        codes = ", ".join(sorted({f.code for f in findings}))
        print(f"\nRejected: {len(findings)} blocking finding(s) [{codes}]. Fix them and push again.")
        return 1
    print("All gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
