
import json
import subprocess
import sys
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from reviewer.schemas.findings import Finding

_active_workspace: ContextVar[Path | None] = ContextVar(
    "active_workspace",
    default=None,
)

MAX_TOOL_FINDINGS = 20
MAX_TEST_FILES = 50
MAX_SOURCE_CHARS = 8_000
TOOL_TIMEOUT = 120

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


def _run_command(
    command: list[str],
    workspace: Path,
) -> subprocess.CompletedProcess[str]:
    """Execute an installed analysis tool with a timeout."""
    try:
        return subprocess.run(
            [sys.executable, "-m", *command],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Analysis timed out after {TOOL_TIMEOUT} seconds"
        ) from exc


def _normalize_file_path(
    raw_path: str,
    workspace: Path,
) -> str:
    """Return only paths safely contained within the workspace."""
    if not raw_path:
        return ""

    try:
        path_obj = Path(raw_path)

        if not path_obj.is_absolute():
            path_obj = workspace / path_obj

        resolved_path = path_obj.resolve()
        relative_path = resolved_path.relative_to(workspace.resolve())

        if _is_excluded(resolved_path, workspace):
            return ""

        return relative_path.as_posix()

    except (OSError, ValueError, RuntimeError):
        return ""


def _get_evidence(
    file_path: str,
    line: int | None,
    workspace: Path,
) -> str | None:
    """Extract the actual source line associated with a finding."""
    if not file_path or line is None or line < 1:
        return None

    try:
        target = (workspace / file_path).resolve()
        target.relative_to(workspace.resolve())

        if not target.is_file() or _is_excluded(target, workspace):
            return None

        lines = target.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()

        if line > len(lines):
            return None

        return lines[line - 1].strip() or None

    except (OSError, ValueError, RuntimeError):
        return None


def _run_ruff(workspace: Path) -> list[Finding]:
    """Run Ruff and normalize its JSON output."""
    result = _run_command(
        ["ruff", "check", "--output-format", "json", "."],
        workspace,
    )

    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"Ruff failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )

    try:
        issues = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ruff returned invalid JSON") from exc

    findings: list[Finding] = []

    for issue in issues:
        location = issue.get("location") or {}
        file_path = _normalize_file_path(
            issue.get("filename", ""),
            workspace,
        )
        line = location.get("row")

        if not file_path:
            continue

        findings.append(
            Finding(
                source="ruff",
                category="quality",
                rule_id=issue.get("code") or "unknown",
                severity="medium",
                confidence="high",
                message=issue.get("message") or "Ruff issue detected",
                file_path=file_path,
                line=line,
                column=location.get("column"),
                evidence=_get_evidence(
                    file_path,
                    line,
                    workspace,
                ),
            )
        )

    return findings


def _normalize_severity(value: str | None) -> str:
    """Normalize Bandit severity."""
    severity = (value or "").lower()

    if severity in {"high", "medium", "low"}:
        return severity

    return "unknown"


def _normalize_confidence(value: str | None) -> str:
    """Normalize Bandit confidence."""
    confidence = (value or "").lower()

    if confidence in {"high", "medium", "low"}:
        return confidence

    return "unknown"


def _run_bandit(workspace: Path) -> list[Finding]:
    """Run Bandit and normalize its JSON output."""
    result = _run_command(
        [
            "bandit",
            "-r",
            ".",
            "-f",
            "json",
            "-q",
            "--exclude",
            ",".join(
                f"**/{directory}/**"
                for directory in sorted(EXCLUDED_DIRECTORIES)
            ),
        ],
        workspace,
    )

    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"Bandit failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )

    try:
        report = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("Bandit returned invalid JSON") from exc

    findings: list[Finding] = []

    for issue in report.get("results", []):
        file_path = _normalize_file_path(
            issue.get("filename", ""),
            workspace,
        )

        if not file_path:
            continue

        rule_id = issue.get("test_id") or "unknown"

        path_parts = {part.lower() for part in Path(file_path).parts}
        is_test_file = (
            any(part in {"test", "tests"} for part in path_parts)
            or Path(file_path).name.lower().startswith("test_")
        )

        if rule_id == "B101" and is_test_file:
            continue

        line = issue.get("line_number")

        findings.append(
            Finding(
                source="bandit",
                category="security",
                rule_id=rule_id,
                severity=_normalize_severity(
                    issue.get("issue_severity")
                ),
                confidence=_normalize_confidence(
                    issue.get("issue_confidence")
                ),
                message=issue.get("issue_text") or "Bandit issue detected",
                file_path=file_path,
                line=line,
                evidence=_get_evidence(
                    file_path,
                    line,
                    workspace,
                ),
            )
        )

    return findings


@tool
def run_ruff(workspace: str | None = None) -> list[dict[str, Any]]:
    """Run Ruff on the active repository and return bounded findings.

    Args:
        workspace: Optional workspace directory; defaults to the active workspace.
    """
    ws_path = _resolve_workspace(workspace)
    findings = _run_ruff(ws_path)
    return _limit_findings(findings)


@tool
def run_bandit(workspace: str | None = None) -> list[dict[str, Any]]:
    """Run Bandit on the active repository and return bounded findings.

    Args:
        workspace: Optional workspace directory; defaults to the active workspace.
    """
    ws_path = _resolve_workspace(workspace)
    findings = _run_bandit(ws_path)
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
