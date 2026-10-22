from reviewer.schemas.findings import Finding
from reviewer.services.deduplicator import FindingDeduplicator


def test_merges_exact_duplicate_findings_on_same_line() -> None:
    deduplicator = FindingDeduplicator()

    finding1 = Finding(
        source="ruff",
        category="quality",
        rule_id="F401",
        severity="medium",
        confidence="high",
        message="`sys` imported but unused",
        file_path="app.py",
        line=1,
    )
    finding2 = Finding(
        source="ai_agent",
        category="quality",
        rule_id="F401",
        severity="medium",
        confidence="high",
        message="Unused import sys",
        file_path="app.py",
        line=1,
        recommendation="Remove import sys",
    )

    results = deduplicator.deduplicate([finding1, finding2])
    assert len(results) == 1
    assert results[0].rule_id == "F401"
    assert results[0].recommendation == "Remove import sys"


def test_preserves_distinct_categories_on_same_line() -> None:
    deduplicator = FindingDeduplicator()

    # Same line 10, but one is security and one is quality
    security_finding = Finding(
        source="bandit",
        category="security",
        rule_id="B608",
        severity="high",
        confidence="high",
        message="SQL injection risk",
        file_path="db.py",
        line=10,
    )
    quality_finding = Finding(
        source="ruff",
        category="quality",
        rule_id="E501",
        severity="low",
        confidence="high",
        message="Line too long",
        file_path="db.py",
        line=10,
    )

    results = deduplicator.deduplicate([security_finding, quality_finding])
    assert len(results) == 2
    categories = {f.category for f in results}
    assert "security" in categories
    assert "quality" in categories


def test_preserves_distinct_issues_with_different_rules_on_same_line() -> None:
    deduplicator = FindingDeduplicator()

    finding1 = Finding(
        source="ruff",
        category="quality",
        rule_id="E501",
        severity="low",
        confidence="high",
        message="Line exceeds length limit",
        file_path="utils.py",
        line=12,
    )
    finding2 = Finding(
        source="ai_agent",
        category="quality",
        rule_id="QUAL002",
        severity="medium",
        confidence="medium",
        message="Overly complex nested ternary expression",
        file_path="utils.py",
        line=12,
    )

    results = deduplicator.deduplicate([finding1, finding2])
    assert len(results) == 2
    rule_ids = {f.rule_id for f in results}
    assert "E501" in rule_ids
    assert "QUAL002" in rule_ids


def test_retains_highest_severity_when_merging() -> None:
    deduplicator = FindingDeduplicator()

    low_finding = Finding(
        source="ruff",
        category="bug",
        rule_id="B006",
        severity="low",
        confidence="low",
        message="Mutable default argument",
        file_path="service.py",
        line=5,
    )
    critical_finding = Finding(
        source="ai_agent",
        category="bug",
        rule_id="B006",
        severity="critical",
        confidence="high",
        message="Mutable default argument causes state leak between calls",
        file_path="service.py",
        line=5,
        recommendation="Use None as default and initialize inside function",
    )

    results = deduplicator.deduplicate([low_finding, critical_finding])
    assert len(results) == 1
    assert results[0].severity == "critical"
    assert results[0].confidence == "high"


def test_findings_in_different_files_never_merge() -> None:
    deduplicator = FindingDeduplicator()

    finding_a = Finding(
        source="ruff",
        category="quality",
        rule_id="F401",
        severity="medium",
        confidence="high",
        message="Unused import",
        file_path="module_a.py",
        line=1,
    )
    finding_b = Finding(
        source="ruff",
        category="quality",
        rule_id="F401",
        severity="medium",
        confidence="high",
        message="Unused import",
        file_path="module_b.py",
        line=1,
    )

    results = deduplicator.deduplicate([finding_a, finding_b])
    assert len(results) == 2
    files = {f.file_path for f in results}
    assert "module_a.py" in files
    assert "module_b.py" in files


def test_findings_on_different_lines_never_merge() -> None:
    deduplicator = FindingDeduplicator()

    finding_line1 = Finding(
        source="ruff",
        category="quality",
        rule_id="E501",
        severity="low",
        confidence="high",
        message="Line too long",
        file_path="app.py",
        line=10,
    )
    finding_line2 = Finding(
        source="ruff",
        category="quality",
        rule_id="E501",
        severity="low",
        confidence="high",
        message="Line too long",
        file_path="app.py",
        line=25,
    )

    results = deduplicator.deduplicate([finding_line1, finding_line2])
    assert len(results) == 2
    lines = {f.line for f in results}
    assert lines == {10, 25}


def test_preserves_evidence_and_recommendation_when_merging() -> None:
    deduplicator = FindingDeduplicator()

    tool_finding = Finding(
        source="bandit",
        category="security",
        rule_id="B105",
        severity="medium",
        confidence="high",
        message="Hardcoded password string",
        file_path="auth.py",
        line=8,
    )
    agent_finding = Finding(
        source="ai_agent",
        category="security",
        rule_id="B105",
        severity="high",
        confidence="high",
        message="Hardcoded password string detected in source code",
        file_path="auth.py",
        line=8,
        evidence="password = 'secret'",
        recommendation="Store secrets in environment variables",
    )

    results = deduplicator.deduplicate([tool_finding, agent_finding])
    assert len(results) == 1
    assert results[0].evidence == "password = 'secret'"
    assert results[0].recommendation == "Store secrets in environment variables"
    assert results[0].severity == "high"


def test_deduplicate_empty_list() -> None:
    deduplicator = FindingDeduplicator()
    assert deduplicator.deduplicate([]) == []
