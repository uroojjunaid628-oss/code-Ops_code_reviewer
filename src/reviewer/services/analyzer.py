
import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from reviewer.schemas.findings import Finding


class StaticAnalyzer:
    """Run deterministic Python code-quality and security analysis."""

    EXCLUDED_DIRECTORIES: ClassVar[set[str]] = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
}

    def __init__(self, timeout_seconds: int = 120) -> None:
        self.timeout_seconds = timeout_seconds

    def analyze(self, workspace: Path) -> list[Finding]:
        """Analyze a repository and return normalized findings."""
        workspace = workspace.resolve()

        if not workspace.is_dir():
            raise NotADirectoryError(
                f"Repository workspace does not exist: {workspace}"
            )

        return [
            *self._run_ruff(workspace),
            *self._run_bandit(workspace),
        ]

    @staticmethod
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
            target.relative_to(workspace)

            if not target.is_file():
                return None

            lines = target.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()

            if line > len(lines):
                return None

            return lines[line - 1].strip() or None

        except (OSError, ValueError):
            return None

    def _run_ruff(self, workspace: Path) -> list[Finding]:
        """Run Ruff and normalize its JSON output."""
        result = self._run_tool(
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
            file_path = self._normalize_file_path(
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
                    evidence=self._get_evidence(
                        file_path,
                        line,
                        workspace,
                    ),
                )
            )

        return findings

    def _run_bandit(self, workspace: Path) -> list[Finding]:
        """Run Bandit and normalize its JSON output."""
        result = self._run_tool(
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
                    for directory in sorted(self.EXCLUDED_DIRECTORIES)
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
            file_path = self._normalize_file_path(
                issue.get("filename", ""),
                workspace,
            )

            if not file_path:
                continue

            rule_id = issue.get("test_id") or "unknown"

            # Assertions are normal in tests; suppress this specific
            # low-value warning in test files, not in application code.
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
                    severity=self._normalize_severity(
                        issue.get("issue_severity")
                    ),
                    confidence=self._normalize_confidence(
                        issue.get("issue_confidence")
                    ),
                    message=issue.get("issue_text") or "Bandit issue detected",
                    file_path=file_path,
                    line=line,
                    evidence=self._get_evidence(
                        file_path,
                        line,
                        workspace,
                    ),
                )
            )

        return findings

    def _run_tool(
        self,
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
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Analysis timed out after {self.timeout_seconds} seconds"
            ) from exc

    @staticmethod
    def _normalize_severity(value: str | None) -> str:
        severity = (value or "").lower()

        if severity in {"high", "medium", "low"}:
            return severity

        return "unknown"

    @staticmethod
    def _normalize_confidence(value: str | None) -> str:
        confidence = (value or "").lower()

        if confidence in {"high", "medium", "low"}:
            return confidence

        return "unknown"

    @staticmethod
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
            relative_path = resolved_path.relative_to(workspace)

            return relative_path.as_posix()

        except (OSError, ValueError, RuntimeError):
            return ""
