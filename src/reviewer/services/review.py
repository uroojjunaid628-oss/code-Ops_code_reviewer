
import logging
from pathlib import Path
from typing import ClassVar, Protocol

from reviewer.agents.bug_agent import BugAnalysisAgent
from reviewer.agents.quality_agent import CodeQualityAgent
from reviewer.agents.security_agent import SecurityAnalysisAgent
from reviewer.agents.test_agent import TestAnalysisAgent
from reviewer.schemas.findings import Finding
from reviewer.services.deduplicator import FindingDeduplicator
from reviewer.services.repository import RepositoryService
from reviewer.services.tools import reset_active_workspace, set_active_workspace
from reviewer.services.verifier import FindingVerifier

logger = logging.getLogger(__name__)


class SourceCodeAgent(Protocol):
    """Define the interface required by source-code analysis agents."""

    def analyze(
        self,
        source_code: str,
        file_path: str,
    ) -> list[Finding]: ...


class ReviewService:
    """Coordinate AI agent analysis, verification, and deduplication."""

    EXCLUDED_DIRECTORIES: ClassVar[set[str]] = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }

    MAX_FILES: ClassVar[int] = 5
    MAX_FILE_SIZE: ClassVar[int] = 10_000

    def __init__(self) -> None:
        self.repository_service = RepositoryService()
        self.verifier = FindingVerifier()
        self.deduplicator = FindingDeduplicator()
        self.agent_failures = 0

        self.agents: list[SourceCodeAgent] = [
            BugAnalysisAgent(),
            SecurityAnalysisAgent(),
            CodeQualityAgent(),
            TestAnalysisAgent(),
        ]

    def review_repository(
        self,
        repository_url: str,
        commit_sha: str,
        job_id: str,
        cleanup: bool = True,
    ) -> list[Finding]:
        """Collect agent findings, then verify and deduplicate them."""
        self.agent_failures = 0

        workspace = self.repository_service.prepare_repository(
            repository_url=repository_url,
            commit_sha=commit_sha,
            job_id=job_id,
        )

        token = set_active_workspace(workspace)

        try:
            agent_findings = self._analyze_with_agents(workspace)

            verified_findings = self.verifier.verify(
                agent_findings,
                workspace,
            )

            return self.deduplicator.deduplicate(verified_findings)

        finally:
            reset_active_workspace(token)

            if cleanup:
                self.repository_service.cleanup_workspace(workspace)

    def _collect_python_files(self, workspace: Path) -> list[Path]:
        """Collect a deterministic, bounded set of eligible Python files."""
        python_files: list[Path] = []

        try:
            candidates = sorted(workspace.rglob("*.py"))

            for path in candidates:
                try:
                    relative_parts = path.relative_to(workspace).parts

                    if self.EXCLUDED_DIRECTORIES.intersection(relative_parts):
                        continue

                    if not path.is_file():
                        continue

                    if path.stat().st_size > self.MAX_FILE_SIZE:
                        continue

                    python_files.append(path)

                    if len(python_files) >= self.MAX_FILES:
                        break

                except (OSError, ValueError):
                    self.agent_failures += 1
                    logger.warning(
                        "Could not inspect source file: %s",
                        path,
                        exc_info=True,
                    )

        except OSError:
            self.agent_failures += 1
            logger.exception(
                "Could not enumerate Python files in workspace: %s",
                workspace,
            )

        return python_files

    def _analyze_with_agents(self, workspace: Path) -> list[Finding]:
        """Run AI agents while isolating individual file and agent failures."""
        findings: list[Finding] = []

        for file_path in self._collect_python_files(workspace):
            try:
                relative_path = file_path.relative_to(workspace).as_posix()
                source_code = file_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except (OSError, ValueError):
                self.agent_failures += 1
                logger.exception("Could not read source file: %s", file_path)
                continue

            for agent in self.agents:
                try:
                    findings.extend(
                        agent.analyze(
                            source_code=source_code,
                            file_path=relative_path,
                        )
                    )
                except Exception:
                    self.agent_failures += 1
                    logger.exception(
                        "AI agent %s failed for %s",
                        type(agent).__name__,
                        relative_path,
                    )

        return findings
