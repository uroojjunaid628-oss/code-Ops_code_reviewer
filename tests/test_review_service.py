
from pathlib import Path
from unittest.mock import Mock

from reviewer.schemas.findings import Finding
from reviewer.services.review import ReviewService


def test_review_continues_when_one_agent_fails(tmp_path: Path) -> None:
    service = ReviewService()

    source_file = tmp_path / "example.py"
    source_file.write_text("print('hello')", encoding="utf-8")

    failed_agent = Mock()
    failed_agent.analyze.side_effect = RuntimeError("Simulated AI failure")

    successful_agent = Mock()
    successful_agent.analyze.return_value = [
        Finding(
            source="ai_agent",
            category="quality",
            rule_id="TEST001",
            severity="low",
            confidence="high",
            message="Example finding",
            file_path="example.py",
            line=1,
            evidence="print('hello')",
            recommendation="Review this code.",
        )
    ]

    service.agents = [failed_agent, successful_agent]

    findings = service._analyze_with_agents(tmp_path)

    assert len(findings) == 1
    assert findings[0].message == "Example finding"
    assert service.agent_failures == 1


def test_review_repository_filters_unverified_findings(tmp_path: Path) -> None:
    service = ReviewService()

    source_file = tmp_path / "app.py"
    source_file.write_text("x = 1\ny = 2\n", encoding="utf-8")

    # Mock prepare_repository to return tmp_path without real git clone
    service.repository_service.prepare_repository = Mock(return_value=tmp_path)
    service.repository_service.cleanup_workspace = Mock()

    # Static analyzer returns 1 valid finding
    service.analyzer.analyze = Mock(
        return_value=[
            Finding(
                source="ruff",
                category="quality",
                rule_id="E501",
                severity="medium",
                confidence="high",
                message="Line too long",
                file_path="app.py",
                line=1,
            )
        ]
    )

    # Agents return 1 valid finding and 1 hallucinated finding (fake line 999)
    valid_finding = Finding(
        source="ai_agent",
        category="bug",
        rule_id="BUG001",
        severity="high",
        confidence="high",
        message="Valid bug",
        file_path="app.py",
        line=1,
        evidence="x = 1",
    )
    hallucinated_finding = Finding(
        source="ai_agent",
        category="bug",
        rule_id="BUG002",
        severity="critical",
        confidence="high",
        message="Hallucinated bug on fake line",
        file_path="app.py",
        line=999,
        evidence="nonexistent_code()",
    )

    agent = Mock()
    agent.analyze.return_value = [valid_finding, hallucinated_finding]
    service.agents = [agent]

    results = service.review_repository(
        repository_url="https://github.com/test/repo",
        commit_sha="a" * 40,
        job_id="test-job-123",
        cleanup=True,
    )

    # Should retain the valid ruff finding and valid agent finding, but drop the hallucinated one
    assert len(results) == 2
    rule_ids = {f.rule_id for f in results}
    assert "E501" in rule_ids
    assert "BUG001" in rule_ids
    assert "BUG002" not in rule_ids

    # Cleanup must be called
    service.repository_service.cleanup_workspace.assert_called_once_with(tmp_path)


def test_review_repository_deduplicates_verified_findings(tmp_path: Path) -> None:
    service = ReviewService()

    source_file = tmp_path / "main.py"
    source_file.write_text("import sys\nx = 10\n", encoding="utf-8")

    service.repository_service.prepare_repository = Mock(return_value=tmp_path)
    service.repository_service.cleanup_workspace = Mock()

    # Tool returns:
    # 1. Ruff F401 on line 1 (low severity)
    # 2. Bandit B608 security on line 2
    tool_f401 = Finding(
        source="ruff",
        category="quality",
        rule_id="F401",
        severity="low",
        confidence="high",
        message="`sys` imported but unused",
        file_path="main.py",
        line=1,
    )
    tool_security = Finding(
        source="bandit",
        category="security",
        rule_id="B608",
        severity="high",
        confidence="high",
        message="SQL injection risk",
        file_path="main.py",
        line=2,
    )
    service.analyzer.analyze = Mock(return_value=[tool_f401, tool_security])

    # AI agents return:
    # 3. Duplicate F401 on line 1 (medium severity, with evidence & recommendation)
    # 4. Distinct quality finding on line 2 (magic number)
    ai_f401_duplicate = Finding(
        source="ai_agent",
        category="quality",
        rule_id="F401",
        severity="medium",
        confidence="high",
        message="Unused import sys detected in main",
        file_path="main.py",
        line=1,
        evidence="import sys",
        recommendation="Remove unused import sys",
    )
    ai_distinct_quality = Finding(
        source="ai_agent",
        category="quality",
        rule_id="QUAL001",
        severity="low",
        confidence="medium",
        message="Magic number used instead of named constant",
        file_path="main.py",
        line=2,
        evidence="x = 10",
        recommendation="Define a named constant",
    )

    agent = Mock()
    agent.analyze.return_value = [ai_f401_duplicate, ai_distinct_quality]
    service.agents = [agent]

    results = service.review_repository(
        repository_url="https://github.com/test/repo",
        commit_sha="b" * 40,
        job_id="test-job-456",
        cleanup=True,
    )

    # 1. Duplicate F401 on line 1 should merge into one finding
    # 2. Distinct issues on line 2 (B608 security and QUAL001 quality) must BOTH survive
    # Total results must be 3 (not 4)
    assert len(results) == 3

    rule_map = {f.rule_id: f for f in results}
    assert set(rule_map.keys()) == {"F401", "B608", "QUAL001"}

    # The merged F401 should retain elevated medium severity and enriched recommendation
    merged_f401 = rule_map["F401"]
    assert merged_f401.severity == "medium"
    assert merged_f401.recommendation == "Remove unused import sys"
    assert merged_f401.evidence == "import sys"

    # Distinct line 2 findings both present
    assert rule_map["B608"].category == "security"
    assert rule_map["QUAL001"].category == "quality"


