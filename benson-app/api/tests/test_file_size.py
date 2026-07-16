from pathlib import Path


MAX_CODE_LINES = 550


def code_line_count(path: Path) -> int:
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def test_python_files_do_not_exceed_ai_context_limit() -> None:
    project_root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for path in sorted(project_root.rglob("*.py")):
        if {".venv", "__pycache__", "migrations"} & set(path.parts):
            continue
        count = code_line_count(path)
        if count > MAX_CODE_LINES:
            relative = path.relative_to(project_root)
            violations.append(f"{relative}: {count} code lines")
    assert not violations, (
        f"Python files must stay at or below {MAX_CODE_LINES} code lines. "
        "Split at a natural responsibility boundary:\n- " + "\n- ".join(violations)
    )
