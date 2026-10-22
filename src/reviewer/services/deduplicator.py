import logging
from collections import defaultdict

from reviewer.schemas.findings import Finding

logger = logging.getLogger(__name__)

SEVERITY_ORDER: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}

CONFIDENCE_ORDER: dict[str, int] = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}


class FindingDeduplicator:
    """Merge duplicate findings across static tools and AI agents without discarding distinct issues."""

    def deduplicate(self, findings: list[Finding]) -> list[Finding]:
        """Group findings by file, line, and category, merging duplicates safely."""
        if not findings:
            return []

        # Cluster by exact location and category: (file_path, line, category)
        # Findings on different files, lines, or categories NEVER merge.
        clusters: dict[tuple[str, int | None, str], list[Finding]] = defaultdict(list)
        for finding in findings:
            key = (finding.file_path, finding.line, finding.category)
            clusters[key].append(finding)

        deduplicated: list[Finding] = []

        for group in clusters.values():
            deduplicated.extend(self._deduplicate_group(group))

        return deduplicated

    def _deduplicate_group(self, group: list[Finding]) -> list[Finding]:
        """Process findings at the same file, line, and category."""
        unique_findings: list[Finding] = []

        for incoming in group:
            match_idx = self._find_matching_index(incoming, unique_findings)
            if match_idx is None:
                unique_findings.append(incoming)
            else:
                existing = unique_findings[match_idx]
                merged = self._merge_findings(existing, incoming)
                unique_findings[match_idx] = merged

        return unique_findings

    def _find_matching_index(
        self,
        candidate: Finding,
        existing_list: list[Finding],
    ) -> int | None:
        """Find the index of an existing finding that describes the same issue."""
        for idx, existing in enumerate(existing_list):
            # 1. Exact match on rule_id
            if candidate.rule_id == existing.rule_id:
                return idx

            # 2. Exact match on normalized message
            if self._normalize_text(candidate.message) == self._normalize_text(existing.message):
                return idx

        return None

    def _merge_findings(self, existing: Finding, incoming: Finding) -> Finding:
        """Safely combine two duplicate findings using model_copy without mutation."""
        # 1. Retain the highest severity
        best_severity = (
            incoming.severity
            if SEVERITY_ORDER.get(incoming.severity, 0) > SEVERITY_ORDER.get(existing.severity, 0)
            else existing.severity
        )

        # 2. Retain the highest confidence
        best_confidence = (
            incoming.confidence
            if CONFIDENCE_ORDER.get(incoming.confidence, 0) > CONFIDENCE_ORDER.get(existing.confidence, 0)
            else existing.confidence
        )

        # 3. Preserve non-empty evidence
        best_evidence = existing.evidence or incoming.evidence

        # 4. Preserve non-empty recommendation
        best_recommendation = existing.recommendation or incoming.recommendation

        # 5. Preserve column number if available
        best_column = existing.column or incoming.column

        # 6. Prefer the longer, more descriptive message
        best_message = (
            incoming.message
            if len(incoming.message.strip()) > len(existing.message.strip())
            else existing.message
        )

        # Return a new immutable model_copy
        return existing.model_copy(
            update={
                "severity": best_severity,
                "confidence": best_confidence,
                "evidence": best_evidence,
                "recommendation": best_recommendation,
                "column": best_column,
                "message": best_message,
            }
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Strip punctuation and whitespace for comparison."""
        return " ".join(text.lower().split())
