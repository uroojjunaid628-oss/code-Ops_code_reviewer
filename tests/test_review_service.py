
import json
from pathlib import Path
from unittest.mock import Mock

from langchain_core.messages import AIMessage

from reviewer.agents.bug_agent import BugAnalysisAgent
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

    service.repository_service.prepare_repository = Mock(return_value=tmp_path)
    service.repository_service.cleanup_workspace = Mock()

    valid_finding_1 = Finding(
        source="ai_agent",
        category="quality",
        rule_id="E501",
        severity="medium",
        confidence="high",
        message="Line too long",
        file_path="app.py",
        line=1,
    )
    valid_finding_2 = Finding(
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
    agent.analyze.return_value = [
        valid_finding_1,
        valid_finding_2,
        hallucinated_finding,
    ]
    service.agents = [agent]

    results = service.review_repository(
        repository_url="https://github.com/test/repo",
        commit_sha="a" * 40,
        job_id="test-job-123",
        cleanup=True,
    )

    assert len(results) == 2
    rule_ids = {finding.rule_id for finding in results}
    assert "E501" in rule_ids
    assert "BUG001" in rule_ids
    assert "BUG002" not in rule_ids

    service.repository_service.cleanup_workspace.assert_called_once_with(
        tmp_path
    )


def test_review_repository_deduplicates_verified_findings(
    tmp_path: Path,
) -> None:
    service = ReviewService()

    source_file = tmp_path / "main.py"
    source_file.write_text("import sys\nx = 10\n", encoding="utf-8")

    service.repository_service.prepare_repository = Mock(return_value=tmp_path)
    service.repository_service.cleanup_workspace = Mock()

    ai_f401_initial = Finding(
        source="ai_agent",
        category="quality",
        rule_id="F401",
        severity="low",
        confidence="high",
        message="`sys` imported but unused",
        file_path="main.py",
        line=1,
    )
    ai_f401_enriched = Finding(
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
    ai_security = Finding(
        source="ai_agent",
        category="security",
        rule_id="B608",
        severity="high",
        confidence="high",
        message="SQL injection risk",
        file_path="main.py",
        line=2,
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
    agent.analyze.return_value = [
        ai_f401_initial,
        ai_f401_enriched,
        ai_security,
        ai_distinct_quality,
    ]
    service.agents = [agent]

    results = service.review_repository(
        repository_url="https://github.com/test/repo",
        commit_sha="b" * 40,
        job_id="test-job-456",
        cleanup=True,
    )

    assert len(results) == 3

    rule_map = {finding.rule_id: finding for finding in results}
    assert set(rule_map.keys()) == {"F401", "B608", "QUAL001"}

    merged_f401 = rule_map["F401"]
    assert merged_f401.severity == "medium"
    assert merged_f401.recommendation == "Remove unused import sys"
    assert merged_f401.evidence == "import sys"

    assert rule_map["B608"].category == "security"
    assert rule_map["QUAL001"].category == "quality"


def test_review_repository_uses_agents_without_baseline_analyzer(
    tmp_path: Path,
) -> None:
    """Verify that review uses agents and does not require StaticAnalyzer."""
    service = ReviewService()

    source_file = tmp_path / "module.py"
    source_file.write_text("print('test')", encoding="utf-8")

    service.repository_service.prepare_repository = Mock(return_value=tmp_path)
    service.repository_service.cleanup_workspace = Mock()

    agent = Mock()
    agent.analyze.return_value = []
    service.agents = [agent]

    service.review_repository(
        repository_url="https://github.com/test/repo",
        commit_sha="c" * 40,
        job_id="test-job-789",
    )

    assert not hasattr(service, "analyzer")
    agent.analyze.assert_called_once()

    service.repository_service.cleanup_workspace.assert_called_once_with(
        tmp_path
    )


def test_agent_invokes_assigned_tool_and_uses_result_in_analysis(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Verify that an agent requests a tool and uses its returned result."""
    agent = BugAnalysisAgent()

    mock_llm = Mock()

    tool_call_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "inspect_source",
                "args": {
                    "file_path": "sample.py",
                    "source_code": "import math\nprint(math.pi)",
                },
                "id": "call_inspect_123",
            }
        ],
    )

    final_analysis_response = AIMessage(
        content=json.dumps(
            {
                "findings": [
                    {
                        "source": "ai_agent",
                        "category": "bug",
                        "rule_id": "BUG_AFTER_TOOL",
                        "severity": "medium",
                        "confidence": "high",
                        "message": "Potential bug identified using tool inspection",
                        "file_path": "sample.py",
                        "line": 1,
                        "evidence": "import math",
                        "recommendation": "Check math usage",
                    }
                ]
            }
        )
    )

    mock_llm.invoke.side_effect = [
        tool_call_response,
        final_analysis_response,
    ]
    agent.llm = mock_llm

    findings = agent.analyze(
        source_code="import math\nprint(math.pi)",
        file_path="sample.py",
    )

    assert mock_llm.invoke.call_count == 2

    second_call_messages = mock_llm.invoke.call_args_list[1][0][0]
    tool_messages = [
        message
        for message in second_call_messages
        if getattr(message, "tool_call_id", None) == "call_inspect_123"
    ]

    assert len(tool_messages) == 1

    tool_payload = json.loads(tool_messages[0].content)
    assert tool_payload["file_path"] == "sample.py"
    assert tool_payload["import_count"] == 1

    assert len(findings) == 1
    assert findings[0].rule_id == "BUG_AFTER_TOOL"
    assert findings[0].category == "bug"
    assert findings[0].source == "ai_agent"


def test_agent_and_tool_failures_record_agent_failures_without_false_success(
    tmp_path: Path,
) -> None:
    """Verify that agent failures are recorded without reporting false success."""
    service = ReviewService()

    source_file = tmp_path / "broken.py"
    source_file.write_text("x = 10", encoding="utf-8")

    service.repository_service.prepare_repository = Mock(return_value=tmp_path)
    service.repository_service.cleanup_workspace = Mock()

    failing_agent = Mock()
    failing_agent.analyze.side_effect = RuntimeError(
        "Tool execution error inside agent"
    )

    working_agent = Mock()
    working_agent.analyze.return_value = []

    service.agents = [failing_agent, working_agent]

    findings = service.review_repository(
        repository_url="https://github.com/test/repo",
        commit_sha="d" * 40,
        job_id="test-job-fail",
    )

    assert findings == []
    assert service.agent_failures == 1

    service.repository_service.cleanup_workspace.assert_called_once_with(
        tmp_path
    )
