from pathlib import Path

from reviewer.schemas.findings import Finding
from reviewer.services.verifier import FindingVerifier


def test_verifier_accepts_valid_finding(tmp_path: Path) -> None:
    code_file = tmp_path / "example.py"
    code_file.write_text("x = 10\ny = 20\n", encoding="utf-8")

    verifier = FindingVerifier()
    finding = Finding(
        source="ai_agent",
        category="bug",
        rule_id="BUG001",
        severity="high",
        confidence="high",
        message="Valid bug report",
        file_path="example.py",
        line=1,
        evidence="x = 10",
        recommendation="Fix it",
    )

    verified = verifier.verify([finding], tmp_path)
    assert len(verified) == 1
    assert verified[0].rule_id == "BUG001"


def test_verifier_rejects_hallucinated_line(tmp_path: Path) -> None:
    code_file = tmp_path / "example.py"
    code_file.write_text("print('hello')\n", encoding="utf-8")

    verifier = FindingVerifier()
    finding = Finding(
        source="ai_agent",
        category="bug",
        rule_id="BUG001",
        severity="high",
        confidence="high",
        message="Fake line bug",
        file_path="example.py",
        line=999,  # Only 1 line exists
        evidence="print('hello')",
        recommendation="Fix it",
    )

    verified = verifier.verify([finding], tmp_path)
    assert len(verified) == 0


def test_verifier_rejects_nonexistent_file(tmp_path: Path) -> None:
    verifier = FindingVerifier()
    finding = Finding(
        source="ai_agent",
        category="bug",
        rule_id="BUG001",
        severity="high",
        confidence="high",
        message="Bug in ghost file",
        file_path="ghost.py",
        line=1,
        evidence="something",
        recommendation="Fix it",
    )

    verified = verifier.verify([finding], tmp_path)
    assert len(verified) == 0


def test_verifier_rejects_path_traversal(tmp_path: Path) -> None:
    # Create a file outside workspace
    outside = tmp_path.parent / "secret.py"
    outside.write_text("secret = 123\n", encoding="utf-8")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    verifier = FindingVerifier()
    finding = Finding(
        source="ai_agent",
        category="security",
        rule_id="SEC001",
        severity="critical",
        confidence="high",
        message="Path traversal attempt",
        file_path="../secret.py",
        line=1,
        evidence="secret = 123",
        recommendation="Prevent this",
    )

    verified = verifier.verify([finding], workspace)
    assert len(verified) == 0


def test_verifier_rejects_evidence_on_wrong_line(tmp_path: Path) -> None:
    code_lines = ["# line 1: target code", *[f"x_{i} = {i}" for i in range(2, 50)], "y = 100"]
    code_file = tmp_path / "example.py"
    code_file.write_text("\n".join(code_lines), encoding="utf-8")

    verifier = FindingVerifier()
    # Claims line 45, but quotes evidence from line 1
    finding = Finding(
        source="ai_agent",
        category="bug",
        rule_id="BUG002",
        severity="medium",
        confidence="medium",
        message="Mismatched line evidence",
        file_path="example.py",
        line=45,
        evidence="# line 1: target code",
        recommendation="Fix line mismatch",
    )

    verified = verifier.verify([finding], tmp_path)
    assert len(verified) == 0


def test_verifier_accepts_multiline_evidence_at_line(tmp_path: Path) -> None:
    code_file = tmp_path / "example.py"
    code_file.write_text(
        "def calculate(a, b):\n"
        "    result = a + b\n"
        "    return result\n",
        encoding="utf-8",
    )

    verifier = FindingVerifier()
    finding = Finding(
        source="ai_agent",
        category="quality",
        rule_id="QUAL001",
        severity="low",
        confidence="high",
        message="Redundant variable",
        file_path="example.py",
        line=2,
        evidence="result = a + b\nreturn result",
        recommendation="Return directly",
    )

    verified = verifier.verify([finding], tmp_path)
    assert len(verified) == 1


def test_verifier_validates_tool_findings(tmp_path: Path) -> None:
    code_file = tmp_path / "example.py"
    code_file.write_text("import sys\n", encoding="utf-8")

    verifier = FindingVerifier()

    # Valid tool finding with existing file and in-bounds line
    valid_tool_finding = Finding(
        source="ruff",
        category="quality",
        rule_id="F401",
        severity="medium",
        confidence="high",
        message="`sys` imported but unused",
        file_path="example.py",
        line=1,
    )

    # Invalid tool finding citing a nonexistent file
    invalid_tool_file = Finding(
        source="ruff",
        category="quality",
        rule_id="F401",
        severity="medium",
        confidence="high",
        message="Unused import in ghost file",
        file_path="nonexistent.py",
        line=1,
    )

    # Invalid tool finding with out-of-bounds line
    invalid_tool_line = Finding(
        source="bandit",
        category="security",
        rule_id="B101",
        severity="low",
        confidence="high",
        message="Assert used",
        file_path="example.py",
        line=50,  # File only has 1 line
    )

    verified = verifier.verify(
        [valid_tool_finding, invalid_tool_file, invalid_tool_line],
        tmp_path,
    )
    assert len(verified) == 1
    assert verified[0].rule_id == "F401"
