
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
    """Coordinate static analysis, AI analysis, verification, and deduplication."""

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
        """Collect static and AI findings, then verify and deduplicate them."""
        self.agent_failures = 0

        workspace = self.repository_service.prepare_repository(
            repository_url=repository_url,
            commit_sha=commit_sha,
            job_id=job_id,
        )

        token = set_active_workspace(workspace)

        try:
            # Deterministic analysis runs independently of AI agent decisions.
            try:
                static_findings = self.analyzer.analyze(workspace)
            except Exception:
                self.agent_failures += 1
                logger.exception(
                    "Static analysis failed for review job %s",
                    job_id,
                )
                static_findings = []

            # AI analysis continues even if static analysis fails.
            agent_findings = self._analyze_with_agents(workspace)

            # Verify both sources through the same evidence-validation pipeline.
            candidate_findings = static_findings + agent_findings
            verified_findings = self.verifier.verify(
                candidate_findings,
                workspace,
            )

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
            if finding.recommendation or finding.line is None:
                enriched.append(finding)
                continue

            matching_recommendations = [
                item
                for item in agent_findings
                if item.file_path == finding.file_path
                and item.category == finding.category
                and item.recommendation
                and item.line is not None
                and abs(item.line - finding.line) <= 3
            ]

            if matching_recommendations:
                best_match = min(
                    matching_recommendations,
                    key=lambda item: abs(item.line - finding.line),
                )
                finding = finding.model_copy(
                    update={"recommendation": best_match.recommendation}
                )

            enriched.append(finding)

        return enriched

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
