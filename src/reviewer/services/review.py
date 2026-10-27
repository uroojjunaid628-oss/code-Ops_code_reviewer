
import logging
from pathlib import Path
from typing import ClassVar, Protocol

from reviewer.agents.bug_agent import BugAnalysisAgent
from reviewer.agents.quality_agent import CodeQualityAgent
from reviewer.agents.security_agent import SecurityAnalysisAgent
from reviewer.agents.test_agent import TestAnalysisAgent
from reviewer.schemas.findings import Finding
from reviewer.services.analyzer import StaticAnalyzer
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
    """Coordinate repository preparation, analysis, and verification."""

    EXCLUDED_DIRECTORIES: ClassVar[set[str]] = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
    }

    MAX_FILES: ClassVar[int] = 3
    MAX_FILE_SIZE: ClassVar[int] = 10_000

    def __init__(self) -> None:
        self.repository_service = RepositoryService()
        self.analyzer = StaticAnalyzer()
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
        """Analyze a repository and return verified, deduplicated findings."""
        self.agent_failures = 0

        workspace = self.repository_service.prepare_repository(
            repository_url=repository_url,
            commit_sha=commit_sha,
            job_id=job_id,
        )

        token = set_active_workspace(workspace)
        try:
            agent_findings = self._analyze_with_agents(workspace)
            verified_findings = self.verifier.verify(agent_findings, workspace)

            return self.deduplicator.deduplicate(verified_findings)
        finally:
            reset_active_workspace(token)
            if cleanup:
                self.repository_service.cleanup_workspace(workspace)

    @staticmethod
    def _attach_agent_recommendations(
        static_findings: list[Finding],
        agent_findings: list[Finding],
    ) -> list[Finding]:
        """Attach nearby, category-matched AI recommendations to static findings."""
        enriched: list[Finding] = []

        for finding in static_findings:
            if finding.recommendation:
                enriched.append(finding)
                continue

            if finding.line is None:
                enriched.append(finding)
                continue

            matching_recommendations = [
                agent_finding
                for agent_finding in agent_findings
                if agent_finding.file_path == finding.file_path
                and agent_finding.category == finding.category
                and agent_finding.recommendation
                and agent_finding.line is not None
                and abs(agent_finding.line - finding.line) <= 3
            ]

            if matching_recommendations:
                best_match = min(
                    matching_recommendations,
                    key=lambda item: abs(item.line - finding.line),
                )
                finding = finding.model_copy(
                    update={
                        "recommendation": best_match.recommendation,
                    }
                )

            enriched.append(finding)

        return enriched

    def _analyze_with_agents(self, workspace: Path) -> list[Finding]:
        """Run AI agents while isolating file and agent failures."""
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

                except OSError:
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
            return []

        findings: list[Finding] = []

        for file_path in python_files:
            relative_path = file_path.relative_to(workspace).as_posix()

            try:
                source_code = file_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                self.agent_failures += 1
                logger.exception(
                    "Could not read source file: %s",
                    relative_path,
                )
                continue

            for agent in self.agents:
                try:
                    agent_findings = agent.analyze(
                        source_code=source_code,
                        file_path=relative_path,
                    )

                    findings.extend(agent_findings)

                except Exception:
                    self.agent_failures += 1
                    logger.exception(
                        "AI agent %s failed for %s",
                        type(agent).__name__,
                        relative_path,
                    )

        return findings
