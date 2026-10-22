import logging
from pathlib import Path

from reviewer.schemas.findings import Finding

logger = logging.getLogger(__name__)


class FindingVerifier:
    """Verify that candidate findings are grounded in actual source code."""

    def __init__(self, context_window_lines: int = 3) -> None:
        self.context_window_lines = context_window_lines

    def verify(
        self,
        candidates: list[Finding],
        workspace: Path,
    ) -> list[Finding]:
        """Filter out candidate findings whose coordinates or evidence are invalid."""
        verified: list[Finding] = []

        for finding in candidates:
            if self._verify_finding(finding, workspace):
                verified.append(finding)
            else:
                logger.warning(
                    "Rejected invalid finding: [%s] %s in %s (line %s)",
                    finding.source,
                    finding.message,
                    finding.file_path,
                    finding.line,
                )

        return verified

    def _verify_finding(self, finding: Finding, workspace: Path) -> bool:
        workspace_resolved = workspace.resolve()
        target_file = (workspace / finding.file_path).resolve()

        # 1. Prevent directory traversal outside the workspace
        try:
            target_file.relative_to(workspace_resolved)
        except ValueError:
            return False

        # 2. Target file must exist and be an actual regular file
        if not target_file.is_file():
            return False

        try:
            content = target_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

        lines = content.splitlines()

        # 3. Line coordinates validation (applies to all findings, including static tools)
        if finding.line is not None:
            if finding.line < 1:
                return False
            if lines and finding.line > len(lines):
                return False
            if not lines and finding.line > 0:
                return False

        # 4. Evidence snippet validation
        # If evidence is provided, it must correspond to the reported location in the file
        if finding.evidence and finding.evidence.strip():
            evidence_normalized = " ".join(finding.evidence.split())

            if finding.line is not None and lines:
                # Calculate window around finding.line to accommodate multi-line snippets
                evidence_line_count = len(finding.evidence.splitlines())
                window_padding = max(self.context_window_lines, evidence_line_count)

                target_idx = finding.line - 1
                start_idx = max(0, target_idx - window_padding)
                end_idx = min(len(lines), target_idx + window_padding + 1)

                window_content = " ".join(" ".join(lines[start_idx:end_idx]).split())
                if evidence_normalized not in window_content:
                    return False
            else:
                # If no line number is specified, evidence must appear in the file
                file_normalized = " ".join(content.split())
                if evidence_normalized not in file_normalized:
                    return False

        return True
