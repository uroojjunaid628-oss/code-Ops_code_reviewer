from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from reviewer.schemas.findings import Finding
from reviewer.services.analyzer import StaticAnalyzer

_analyzer = StaticAnalyzer()
_active_workspace: ContextVar[Path | None] = ContextVar("active_workspace", default=None)


def set_active_workspace(workspace: Path | str | None) -> Token[Path | None]:
    """Set the active repository workspace for tool executions in the current context."""
    path_val = Path(workspace).resolve() if workspace else None
    return _active_workspace.set(path_val)


def reset_active_workspace(token: Token[Path | None]) -> None:
    """Reset the active repository workspace to the value from the token."""
    _active_workspace.reset(token)


def get_active_workspace() -> Path:
    """Return the active workspace for the current context, or fallback to current directory."""
    ws = _active_workspace.get()
    if ws is not None and ws.is_dir():
        return ws
    return Path.cwd()


def _finding_to_dict(finding: Finding) -> dict[str, Any]:
    return finding.model_dump()


@tool
def run_ruff(workspace: str | None = None) -> list[dict[str, Any]]:
    """Run Ruff on the repository workspace to detect bugs, syntax issues, or code quality problems.

    Args:
        workspace: Optional workspace directory. Defaults to the active repository workspace.
    """
    ws_path = (
        Path(workspace).resolve()
        if workspace and Path(workspace).is_dir()
        else get_active_workspace()
    )
    findings = _analyzer._run_ruff(ws_path)
    return [_finding_to_dict(f) for f in findings]


@tool
def run_bandit(workspace: str | None = None) -> list[dict[str, Any]]:
    """Run Bandit on the repository workspace to detect security risks and vulnerabilities.

    Args:
        workspace: Optional workspace directory. Defaults to the active repository workspace.
    """
    ws_path = (
        Path(workspace).resolve()
        if workspace and Path(workspace).is_dir()
        else get_active_workspace()
    )
    findings = _analyzer._run_bandit(ws_path)
    return [_finding_to_dict(f) for f in findings]


@tool
def inspect_source(file_path: str, source_code: str) -> dict[str, Any]:
    """Lightweight source-code inspection.

    Returns basic metrics such as line count and number of import statements.
    """
    lines = source_code.splitlines()
    return {
        "file_path": file_path,
        "line_count": len(lines),
        "import_count": sum(
            1
            for line in lines
            if line.strip().startswith("import") or line.strip().startswith("from")
        ),
    }


@tool
def existing_test_inspection(workspace: str | None = None) -> list[dict[str, Any]]:
    """Inspect repository for existing test files.

    Args:
        workspace: Optional workspace directory. Defaults to the active repository workspace.
    """
    ws_path = (
        Path(workspace).resolve()
        if workspace and Path(workspace).is_dir()
        else get_active_workspace()
    )
    results: list[dict[str, Any]] = []
    for path in ws_path.rglob("*.py"):
        name = path.name.lower()
        if name.startswith("test_") or name.endswith("_test.py"):
            try:
                rel_path = path.relative_to(ws_path).as_posix()
            except ValueError:
                rel_path = path.name
            results.append({
                "file_path": rel_path,
                "has_tests": True,
            })
    return results

