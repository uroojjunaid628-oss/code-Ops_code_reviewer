
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from reviewer.schemas.findings import Finding
from reviewer.services.analyzer import StaticAnalyzer

_analyzer = StaticAnalyzer()

_active_workspace: ContextVar[Path | None] = ContextVar(
    "active_workspace",
    default=None,
)

MAX_TOOL_FINDINGS = 20
MAX_TEST_FILES = 50
MAX_SOURCE_CHARS = 8_000

EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
}


def set_active_workspace(
    workspace: Path | str | None,
) -> Token[Path | None]:
    """Set the active repository workspace for the current context."""
    path = Path(workspace).resolve() if workspace else None
    return _active_workspace.set(path)


def reset_active_workspace(token: Token[Path | None]) -> None:
    """Restore the previous active workspace."""
    _active_workspace.reset(token)


def get_active_workspace() -> Path:
    """Return the active workspace, or the current directory as fallback."""
    workspace = _active_workspace.get()

    if workspace is not None and workspace.is_dir():
        return workspace

    return Path.cwd().resolve()


def _resolve_workspace(workspace: str | None = None) -> Path:
    """Resolve a requested workspace without accepting invalid paths."""
    if not workspace:
        return get_active_workspace()

    requested = Path(workspace).resolve()

    if not requested.is_dir():
        raise ValueError("Workspace must be an existing directory.")

    active = _active_workspace.get()

    # When a workspace is active, tools must not access another directory.
    if active is not None:
        active = active.resolve()

        if requested != active and active not in requested.parents:
            raise ValueError(
                "Requested workspace is outside the active repository."
            )

    return requested


def _finding_to_dict(finding: Finding) -> dict[str, Any]:
    """Convert a Finding to a JSON-compatible dictionary."""
    return finding.model_dump(mode="json")


def _limit_findings(
    findings: list[Finding],
) -> list[dict[str, Any]]:
    """Bound the number and size of findings returned to an agent."""
    results: list[dict[str, Any]] = []

    for finding in findings[:MAX_TOOL_FINDINGS]:
        item = _finding_to_dict(finding)

        for field in ("message", "evidence", "recommendation"):
            value = item.get(field)

            if isinstance(value, str) and len(value) > 1_000:
                item[field] = value[:1_000] + "... [truncated]"

        results.append(item)

    if len(findings) > MAX_TOOL_FINDINGS:
        results.append({
            "notice": (
                f"{len(findings) - MAX_TOOL_FINDINGS} additional "
                "findings omitted to limit output."
            )
        })

    return results


def _is_excluded(path: Path, workspace: Path) -> bool:
    """Check whether a path is inside an excluded directory."""
    try:
        relative = path.relative_to(workspace)
    except ValueError:
        return True

    return any(
        part in EXCLUDED_DIRECTORIES
        for part in relative.parts
    )


@tool
def run_ruff(workspace: str | None = None) -> list[dict[str, Any]]:
    """Run Ruff on the active repository and return bounded findings.

    Args:
        workspace: Optional workspace directory; defaults to the active workspace.
    """
    ws_path = _resolve_workspace(workspace)
    findings = _analyzer._run_ruff(ws_path)
    return _limit_findings(findings)


@tool
def run_bandit(workspace: str | None = None) -> list[dict[str, Any]]:
    """Run Bandit on the active repository and return bounded findings.

    Args:
        workspace: Optional workspace directory; defaults to the active workspace.
    """
    ws_path = _resolve_workspace(workspace)
    findings = _analyzer._run_bandit(ws_path)
    return _limit_findings(findings)


@tool
def inspect_source(file_path: str, source_code: str) -> dict[str, Any]:
    """Return basic source metrics without returning the source code itself.

    Args:
        file_path: Repository-relative path of the source file.
        source_code: Source code to inspect.
    """
    lines = source_code.splitlines()
    truncated = len(source_code) > MAX_SOURCE_CHARS
    inspected_source = source_code[:MAX_SOURCE_CHARS]
    inspected_lines = inspected_source.splitlines()

    return {
        "file_path": Path(file_path).as_posix(),
        "line_count": len(lines),
        "import_count": sum(
            1
            for line in inspected_lines
            if line.strip().startswith(("import ", "from "))
        ),
        "source_truncated": truncated,
    }


@tool
def existing_test_inspection(
    workspace: str | None = None,
) -> list[dict[str, Any]]:
    """Find existing Python test files, with a bounded result list.

    Args:
        workspace: Optional workspace directory; defaults to the active workspace.
    """
    ws_path = _resolve_workspace(workspace)
    results: list[dict[str, Any]] = []

    for path in ws_path.rglob("*.py"):
        if _is_excluded(path, ws_path):
            continue

        name = path.name.lower()

        if not (name.startswith("test_") or name.endswith("_test.py")):
            continue

        results.append({
            "file_path": path.relative_to(ws_path).as_posix(),
            "has_tests": True,
        })

        if len(results) >= MAX_TEST_FILES:
            break

    return results
