#!/usr/bin/env python3
"""Verify that the integrated tree is an additive superset of v12.9.0."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "scripts" / "parity" / "benson-baseline.json"
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
SKIP_DIRECTORIES = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "artifacts", "dist", "node_modules"}
OPERATION_PATTERN = re.compile(r"operation_id\s*=\s*['\"]([^'\"]+)")
ROUTE_PATTERNS = (
    re.compile(r"(?:path|to)\s*[:=]\s*['\"](/[^'\"]*)"),
    re.compile(r"<Route[^>]+path=['\"]([^'\"]+)"),
)
CLI_PATTERNS = (
    re.compile(r"\.add_parser\(\s*['\"]([^'\"]+)"),
    re.compile(r"@(?:app|cli)\.command\(\s*['\"]([^'\"]+)"),
)
TASK_PATTERNS = (
    re.compile(r"@(?:shared_task|app\.task|celery_app\.task)(?:\([^)]*name=['\"]([^'\"]+))?"),
    re.compile(r"task_name\s*=\s*['\"]([^'\"]+)"),
)
PERMISSION_PATTERN = re.compile(r"['\"]([a-z][a-z0-9_-]*\.[a-z][a-z0-9_.:-]*)['\"]")
TS_EXPORT_PATTERN = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:class|function|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)"
)
SKIP_PATTERN = re.compile(r"pytest\.mark\.skip|pytest\.skip\(|(?:describe|it|test)\.skip\(")


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def extract_baseline(commit: str, destination: Path) -> None:
    archive = destination.parent / "baseline.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", f"--output={archive}", commit],
        cwd=ROOT,
        check=True,
    )
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination, filter="data")


def tracked_paths(commit: str) -> list[str]:
    output = run("git", "ls-tree", "-r", "--name-only", commit)
    return output.splitlines() if output else []


def backend_modules(paths: list[str]) -> set[str]:
    result = set()
    for path in paths:
        parts = Path(path).parts
        if len(parts) > 4 and parts[:3] == ("backend", "app", "modules"):
            result.add(parts[3])
    return result


def source_files(root: Path):
    for directory, child_directories, files in os.walk(root):
        child_directories[:] = [name for name in child_directories if name not in SKIP_DIRECTORIES]
        parent = Path(directory)
        for name in files:
            path = parent / name
            if path.suffix in SOURCE_SUFFIXES:
                yield path


def python_symbols(path: Path, root: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    relative = path.relative_to(root).as_posix()
    symbols = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(f"{relative}:{node.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    symbols.add(f"{relative}:{target.id}")
    return symbols


def inventory(root: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for path in source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if path.suffix == ".py":
            result["python_exports"].update(python_symbols(path, root))
        else:
            relative = path.relative_to(root).as_posix()
            result["typescript_exports"].update(
                f"{relative}:{symbol}" for symbol in TS_EXPORT_PATTERN.findall(text)
            )
        result["openapi_operation_ids"].update(OPERATION_PATTERN.findall(text))
        for pattern in ROUTE_PATTERNS:
            result["routes"].update(match for match in pattern.findall(text) if match)
        for pattern in CLI_PATTERNS:
            result["cli_commands"].update(pattern.findall(text))
        for pattern in TASK_PATTERNS:
            result["celery_tasks"].update(match for match in pattern.findall(text) if match)
        result["permissions"].update(PERMISSION_PATTERN.findall(text))
    result["frontend_features"] = {
        path.name for path in (root / "frontend" / "src" / "features").iterdir() if path.is_dir()
    }
    result["module_manifests"] = {
        path.parent.name for path in (root / "backend" / "app" / "modules").glob("*/manifest.py")
    }
    return result


def migration_inventory(root: Path) -> tuple[set[str], set[str]]:
    revisions: set[str] = set()
    parents: set[str] = set()
    revision_re = re.compile(r"^revision(?:\s*:[^=]+)?\s*=\s*['\"]([^'\"]+)", re.MULTILINE)
    down_re = re.compile(r"^down_revision(?:\s*:[^=]+)?\s*=\s*['\"]([^'\"]+)", re.MULTILINE)
    for path in (root / "backend").rglob("*.py"):
        if "versions" not in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        revisions.update(revision_re.findall(text))
        parents.update(down_re.findall(text))
    return revisions, revisions - parents


def skip_counts(root: Path, baseline_paths: list[str]) -> dict[str, int]:
    counts = {}
    for relative in baseline_paths:
        if "test" not in Path(relative).name or not relative.endswith((".py", ".ts", ".tsx")):
            continue
        path = root / relative
        if path.exists():
            counts[relative] = len(SKIP_PATTERN.findall(path.read_text(encoding="utf-8")))
    return counts


def verify() -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    commit = config["upstream_commit"]
    paths = tracked_paths(commit)
    failures: list[str] = []
    if len(paths) != config["tracked_paths"]:
        failures.append(f"baseline path count is {len(paths)}, expected {config['tracked_paths']}")
    missing_paths = [path for path in paths if not (ROOT / path).exists()]
    if missing_paths:
        failures.append(f"missing {len(missing_paths)} upstream paths")
    modules = backend_modules(paths)
    if len(modules) != config["backend_module_directories"]:
        failures.append(
            f"baseline backend module count is {len(modules)}, expected {config['backend_module_directories']}"
        )

    with tempfile.TemporaryDirectory(prefix="benson-parity-") as temp:
        baseline_root = Path(temp) / "baseline"
        baseline_root.mkdir()
        extract_baseline(commit, baseline_root)
        baseline_inventory = inventory(baseline_root)
        current_inventory = inventory(ROOT)
        inventory_counts = {}
        for name, expected in baseline_inventory.items():
            missing = expected - current_inventory[name]
            inventory_counts[name] = {"baseline": len(expected), "integrated": len(current_inventory[name])}
            if missing:
                sample = ", ".join(sorted(missing)[:8])
                failures.append(f"{name} lost {len(missing)} items: {sample}")

        baseline_revisions, baseline_heads = migration_inventory(baseline_root)
        current_revisions, current_heads = migration_inventory(ROOT)
        if not baseline_revisions <= current_revisions:
            failures.append(f"lost {len(baseline_revisions - current_revisions)} Alembic revisions")
        if not baseline_heads <= current_heads:
            failures.append(f"lost Alembic heads: {sorted(baseline_heads - current_heads)}")

        baseline_skips = skip_counts(baseline_root, paths)
        current_skips = skip_counts(ROOT, paths)
        increased_skips = {
            path: current_skips.get(path, 0) - count
            for path, count in baseline_skips.items()
            if current_skips.get(path, 0) > count
        }
        if increased_skips:
            failures.append(f"upstream tests gained skip markers in {len(increased_skips)} files")

    return {
        "baseline_commit": commit,
        "status": "pass" if not failures else "fail",
        "tracked_paths": {"baseline": len(paths), "missing": len(missing_paths)},
        "backend_modules": {"baseline": len(modules), "integrated": len(backend_modules([
            path.relative_to(ROOT).as_posix() for path in (ROOT / "backend" / "app" / "modules").rglob("*")
        ]))},
        "inventories": inventory_counts,
        "migrations": {
            "baseline_revisions": len(baseline_revisions),
            "integrated_revisions": len(current_revisions),
            "baseline_heads": sorted(baseline_heads),
            "integrated_heads": sorted(current_heads),
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify()
    output = json.dumps(report, indent=2, sort_keys=True)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
