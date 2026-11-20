#!/usr/bin/env python3
"""Deterministic structural validator for the FictionForge Stage 4 submission.

Checks ``manifest.yaml`` (schema_version 2) against the files that would be
packaged.  No network, no LLM, no randomness: the same tree always yields the
same report.

The Stage 4 specification text was not available in the workspace, so R1-R7
below are derived from the structure of the existing manifest and the
packaging requirements.  They are NOT verified against the official spec.

    R1  manifest.yaml parses and declares schema_version 2 plus the expected
        top-level sections.
    R2  workflow block has name, entry_point, artifacts (all required keys)
        and a non-empty list of uniquely named steps.
    R3  every step declares prompt_file, a non-empty eval_files list and a
        non-empty log_files list.
    R4  every referenced path is a safe relative POSIX path, is not an
        excluded (secret/cache/venv/temp) path, and exists as a packaged file.
    R5  every not_judged entry has a path and a reason, is unique, exists and
        does not overlap a referenced path.
    R6  every packaged file is referenced by the manifest or accounted for
        under not_judged.
    R7  no secret material or symlinks in the package, and every referenced
        file is non-empty and well formed (.json/.jsonl/.yaml parse).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "manifest.yaml"
SCHEMA_VERSION = 2
STAGE = 4

RULES = {
    "R1": "manifest parses and declares schema_version 2",
    "R2": "workflow block has name, entry_point, artifacts and steps",
    "R3": "every step has prompt_file, eval_files and log_files",
    "R4": "referenced paths are safe, not excluded, and exist",
    "R5": "not_judged entries are well formed, exist and do not overlap references",
    "R6": "every packaged file is referenced or accounted for under not_judged",
    "R7": "no secrets or symlinks; referenced files are non-empty and well formed",
}

TOP_LEVEL_KEYS = {"schema_version", "submission", "workflow", "not_judged"}
SUBMISSION_KEYS = {"title", "stage"}
WORKFLOW_KEYS = {"name", "entry_point", "artifacts", "steps"}
ARTIFACT_KEYS = ("guardrails", "punch_out", "success_rate", "audit_trail", "log")
STEP_KEYS = {"name", "prompt_file", "eval_files", "log_files"}

EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox", "node_modules", ".idea", ".vscode", ".promptfoo",
    ".ipynb_checkpoints", "dist", "build",
}
EXCLUDED_DIR_SUFFIXES = (".egg-info",)
EXCLUDED_FILE_NAMES = {".DS_Store", "Thumbs.db", ".coverage"}
EXCLUDED_FILE_SUFFIXES = (
    ".pyc", ".pyo", ".pyd", ".swp", ".swo", ".tmp", ".temp", ".bak", ".orig", ".rej",
    ".log", "~", ".pem", ".key", ".p12", ".pfx", ".zip", ".sha256",
)
EXCLUDED_FILE_PREFIXES = ("id_rsa", "id_ed25519", "credentials", "secrets")
ENV_TEMPLATE_NAMES = {".env.example", ".env.sample", ".env.template"}

SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "API key (sk-)": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
}
MAX_SCAN_BYTES = 8 * 1024 * 1024


@dataclass
class Finding:
    rule: str
    message: str


@dataclass
class Report:
    root: Path
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    package_files: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    referenced: set[str] = field(default_factory=set)

    def fail(self, rule: str, message: str) -> None:
        self.findings.append(Finding(rule, message))

    def failed_rules(self) -> set[str]:
        return {f.rule for f in self.findings}

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, Any]:
        failed = self.failed_rules()
        return {
            "ok": self.ok,
            "rules": {r: {"description": d, "status": "FAIL" if r in failed else "PASS"} for r, d in RULES.items()},
            "findings": [{"rule": f.rule, "message": f.message} for f in self.findings],
            "warnings": self.warnings,
            "package_file_count": len(self.package_files),
            "referenced_file_count": len(self.referenced),
            "excluded": self.excluded,
        }


def is_excluded_dir(name: str) -> bool:
    return name in EXCLUDED_DIRS or name.endswith(EXCLUDED_DIR_SUFFIXES)


def is_excluded_file(name: str) -> bool:
    if name in ENV_TEMPLATE_NAMES:
        return False
    if name in EXCLUDED_FILE_NAMES or name == ".env" or name.startswith(".env."):
        return True
    lowered = name.lower()
    return lowered.endswith(EXCLUDED_FILE_SUFFIXES) or lowered.startswith(EXCLUDED_FILE_PREFIXES)


def path_is_excluded(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    return any(is_excluded_dir(p) for p in parts[:-1]) or is_excluded_file(parts[-1])


def collect_package_files(root: Path) -> tuple[list[str], list[str]]:
    """Return (sorted packageable relative paths, sorted excluded relative paths)."""
    files: list[str] = []
    excluded: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        keep = []
        for d in sorted(dirnames):
            rel = (base / d).relative_to(root).as_posix()
            if (base / d).is_symlink():
                files.append(rel)
            elif is_excluded_dir(d):
                excluded.append(rel + "/")
            else:
                keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            rel = (base / f).relative_to(root).as_posix()
            (excluded if is_excluded_file(f) else files).append(rel)
    return sorted(files), sorted(excluded)


def _path_problem(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return "must be a non-empty string"
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return "must be a relative POSIX path"
    p = PurePosixPath(value)
    if ".." in p.parts or p.as_posix() != value or value.startswith("./"):
        return "must be normalised and must not contain '..' or './'"
    return None


def _load_manifest(report: Report) -> dict[str, Any] | None:
    path = report.root / MANIFEST_NAME
    if not path.is_file():
        report.fail("R1", f"{MANIFEST_NAME} not found")
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        report.fail("R1", f"{MANIFEST_NAME} is not valid YAML: {exc}")
        return None
    if not isinstance(data, dict):
        report.fail("R1", f"{MANIFEST_NAME} must be a YAML mapping")
        return None
    if data.get("schema_version") != SCHEMA_VERSION or isinstance(data.get("schema_version"), bool):
        report.fail("R1", f"schema_version must be {SCHEMA_VERSION}, got {data.get('schema_version')!r}")
    for key in ("submission", "workflow", "not_judged"):
        if key not in data:
            report.fail("R1", f"missing top-level section '{key}'")
    for key in sorted(set(data) - TOP_LEVEL_KEYS):
        report.warnings.append(f"R1: unknown top-level key '{key}'")
    sub = data.get("submission")
    if sub is not None:
        if not isinstance(sub, dict):
            report.fail("R1", "submission must be a mapping")
        else:
            if not isinstance(sub.get("title"), str) or not sub["title"].strip():
                report.fail("R1", "submission.title must be a non-empty string")
            if sub.get("stage") != STAGE:
                report.fail("R1", f"submission.stage must be {STAGE}, got {sub.get('stage')!r}")
    return data


def _collect_references(report: Report, data: dict[str, Any]) -> list[tuple[str, Any]]:
    """Validate workflow/step structure (R2, R3); return (location, path) references."""
    refs: list[tuple[str, Any]] = []
    wf = data.get("workflow")
    if not isinstance(wf, dict):
        report.fail("R2", "workflow must be a mapping")
        return refs
    for key in sorted(set(wf) - WORKFLOW_KEYS):
        report.warnings.append(f"R2: unknown workflow key '{key}'")
    if not isinstance(wf.get("name"), str) or not wf["name"].strip():
        report.fail("R2", "workflow.name must be a non-empty string")
    if "entry_point" not in wf:
        report.fail("R2", "workflow.entry_point is required")
    else:
        refs.append(("workflow.entry_point", wf["entry_point"]))
    artifacts = wf.get("artifacts")
    if not isinstance(artifacts, dict):
        report.fail("R2", "workflow.artifacts must be a mapping")
    else:
        for key in ARTIFACT_KEYS:
            if key not in artifacts:
                report.fail("R2", f"workflow.artifacts.{key} is required")
        for key in sorted(artifacts):
            if key not in ARTIFACT_KEYS:
                report.warnings.append(f"R2: unknown artifact key '{key}'")
            refs.append((f"workflow.artifacts.{key}", artifacts[key]))
    steps = wf.get("steps")
    if not isinstance(steps, list) or not steps:
        report.fail("R2", "workflow.steps must be a non-empty list")
        return refs
    seen: set[str] = set()
    for i, step in enumerate(steps):
        loc = f"workflow.steps[{i}]"
        if not isinstance(step, dict):
            report.fail("R3", f"{loc} must be a mapping")
            continue
        name = step.get("name")
        if not isinstance(name, str) or not name.strip():
            report.fail("R3", f"{loc}.name must be a non-empty string")
        elif name in seen:
            report.fail("R2", f"duplicate step name '{name}'")
        else:
            seen.add(name)
        loc = f"step '{name}'" if isinstance(name, str) else loc
        for key in sorted(set(step) - STEP_KEYS):
            report.warnings.append(f"R3: unknown key '{key}' in {loc}")
        if "prompt_file" not in step:
            report.fail("R3", f"{loc}.prompt_file is required")
        else:
            refs.append((f"{loc}.prompt_file", step["prompt_file"]))
        for key in ("eval_files", "log_files"):
            value = step.get(key)
            if not isinstance(value, list) or not value:
                report.fail("R3", f"{loc}.{key} must be a non-empty list")
                continue
            if len(set(map(str, value))) != len(value):
                dups = sorted({str(v) for v in value if value.count(v) > 1})
                report.fail("R4", f"{loc}.{key} contains duplicates: {dups}")
            refs.extend((f"{loc}.{key}", v) for v in value)
    return refs


def _check_references(report: Report, refs: list[tuple[str, Any]], package: set[str]) -> None:
    for loc, value in refs:
        problem = _path_problem(value)
        if problem:
            report.fail("R4", f"{loc}: path {value!r} {problem}")
        elif path_is_excluded(value):
            report.fail("R4", f"{loc}: {value} is an excluded secret/cache/venv/temp path")
        elif value not in package:
            report.fail("R4", f"{loc}: {value} does not exist as a packaged file")
        else:
            report.referenced.add(value)


def _not_judged(report: Report, data: dict[str, Any], package: set[str]) -> list[str]:
    entries = data.get("not_judged")
    if entries is None:
        return []
    if not isinstance(entries, list):
        report.fail("R5", "not_judged must be a list")
        return []
    accepted: list[str] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        loc = f"not_judged[{i}]"
        if not isinstance(entry, dict):
            report.fail("R5", f"{loc} must be a mapping with path and reason")
            continue
        for key in sorted(set(entry) - {"path", "reason"}):
            report.warnings.append(f"R5: unknown key '{key}' in {loc}")
        path = entry.get("path")
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            report.fail("R5", f"{loc} ({path}): reason must be a non-empty string")
        is_dir = isinstance(path, str) and path.endswith("/")
        problem = _path_problem(path.rstrip("/") if isinstance(path, str) else path)
        if problem:
            report.fail("R5", f"{loc}: path {path!r} {problem}")
            continue
        if path in seen:
            report.fail("R5", f"{loc}: duplicate not_judged path {path}")
            continue
        seen.add(path)
        if is_dir:
            if not any(f.startswith(path) for f in package):
                report.fail("R5", f"{loc}: directory {path} contains no packaged files")
                continue
        elif path not in package:
            report.fail("R5", f"{loc}: {path} does not exist as a packaged file")
            continue
        overlap = sorted(r for r in report.referenced if (r.startswith(path) if is_dir else r == path))
        if overlap:
            report.fail("R5", f"{loc}: {path} overlaps referenced file(s): {overlap[:3]}")
        accepted.append(path)
    return accepted


def _check_coverage(report: Report, package: list[str], not_judged: list[str]) -> None:
    dirs = tuple(p for p in not_judged if p.endswith("/"))
    exact = {p for p in not_judged if not p.endswith("/")}
    missing = [f for f in package if f not in report.referenced and f not in exact and not f.startswith(dirs)]
    for f in missing:
        report.fail("R6", f"{f} is neither referenced nor listed under not_judged")


def _check_content(report: Report, package: list[str]) -> None:
    for rel in package:
        path = report.root / rel
        if path.is_symlink():
            report.fail("R7", f"{rel} is a symlink")
            continue
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size and size <= MAX_SCAN_BYTES:
            text = path.read_bytes().decode("utf-8", errors="ignore")
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    report.fail("R7", f"{rel} appears to contain a secret ({label})")
    for rel in sorted(report.referenced):
        path = report.root / rel
        if path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size == 0:
            report.fail("R7", f"referenced file {rel} is empty")
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if rel.endswith(".json"):
                json.loads(text)
            elif rel.endswith(".jsonl"):
                for n, line in enumerate(text.splitlines(), 1):
                    if line.strip():
                        json.loads(line)
            elif rel.endswith((".yaml", ".yml")):
                yaml.safe_load(text)
        except (ValueError, yaml.YAMLError) as exc:
            report.fail("R7", f"referenced file {rel} is malformed: {exc}")


def validate(root: Path = REPO_ROOT) -> Report:
    report = Report(root=root.resolve())
    files, report.excluded = collect_package_files(report.root)
    report.package_files = files
    package = set(files)
    data = _load_manifest(report)
    if data is None:
        return report
    if MANIFEST_NAME not in package:
        report.fail("R1", f"{MANIFEST_NAME} is not a packageable file")
    refs = _collect_references(report, data)
    _check_references(report, refs, package)
    not_judged = _not_judged(report, data, package)
    report.referenced.discard(MANIFEST_NAME)
    _check_coverage(report, [f for f in files if f != MANIFEST_NAME], not_judged)
    _check_content(report, files)
    return report


def format_report(report: Report) -> str:
    failed = report.failed_rules()
    lines = [f"Submission root: {report.root}"]
    lines += [f"  {r}  {'FAIL' if r in failed else 'PASS'}  {d}" for r, d in RULES.items()]
    lines.append(
        f"Packaged files: {len(report.package_files)}; referenced: {len(report.referenced)}; "
        f"excluded paths: {len(report.excluded)}"
    )
    lines += [f"  FAIL {f.rule}: {f.message}" for f in report.findings]
    lines += [f"  WARN {w}" for w in report.warnings]
    lines.append("RESULT: " + ("PASS" if report.ok else "FAIL"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="submission root (default: repo root)")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)
    report = validate(args.root)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True) if args.json else format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
