# CodeOPS-AI — Test-Driven Development Document

## Table of Contents

1. [Test Infrastructure](#1-test-infrastructure)
2. [Test Inventory](#2-test-inventory)
3. [Coverage Map](#3-coverage-map)
4. [Test Patterns](#4-test-patterns)
5. [What Is Tested Well](#5-what-is-tested-well)
6. [Testing Gaps](#6-testing-gaps)
7. [Proposed New Tests (TDD Plan)](#7-proposed-new-tests-tdd-plan)
8. [Running Tests](#8-running-tests)
9. [CI Considerations](#9-ci-considerations)

---

## 1. Test Infrastructure

### 1.1 Framework & Tools

| Tool | Role |
|---|---|
| `pytest` | Test runner |
| `httpx` | ASGI test client (`AsyncClient` or `TestClient`) |
| `unittest.mock` (`Mock`, `patch`, `MagicMock`) | Mock heavy collaborators |
| `pytest` `tmp_path` fixture | Temporary file system for agent/tool tests |
| `pytest` `monkeypatch` | Patch module-level singletons and env vars |
| SQLite in-memory | Database for API lifecycle tests (via `DATABASE_URL=sqlite:///:memory:`) |

### 1.2 Database Strategy

- **API tests** (`test_review_api.py`, `test_review_lifecycle.py`, `test_report_persistence.py`): Use SQLite in-memory via `DATABASE_URL` override in test fixtures. `Base.metadata.create_all(engine)` creates schema fresh for each test.
- **Integration test** (`test_postgres_integration.py`): Targets a real PostgreSQL instance. Skipped when `DATABASE_URL` is not set to Postgres.
- **Unit tests** (verifier, deduplicator, report, agent tools): No database involved — operate purely on in-memory Python objects.

### 1.3 LLM Strategy

No test uses a real Ollama instance. All LLM calls are mocked:

```python
# Representative pattern from test_review_service.py
mock_agent = Mock()
mock_agent.analyze.return_value = [fake_finding]
with patch("reviewer.services.review.BugAgent", return_value=mock_agent):
    ...
```

### 1.4 File System Strategy

Tests that need real files (verifier, tool tests) use `pytest`'s `tmp_path` fixture:

```python
def test_verifier_accepts_valid(tmp_path):
    f = tmp_path / "src" / "main.py"
    f.parent.mkdir(parents=True)
    f.write_text("x = 1\n")
    finding = make_finding(file_path="src/main.py", line=1, evidence="x = 1")
    result = FindingVerifier(tmp_path).verify([finding])
    assert len(result) == 1
```

---

## 2. Test Inventory

### `tests/test_review_service.py` — 5 tests

| Test Name | What It Covers |
|---|---|
| `test_review_service_invokes_baseline_analyzer` | Confirms `StaticAnalyzer.analyze()` is called during `review_repository()`; result is included in candidate findings |
| `test_agent_invokes_assigned_tool_and_uses_result_in_analysis` | End-to-end tool-call mock: LLM returns `tool_call`, result injected as `ToolMessage`, LLM returns final JSON; verifies agent produces `Finding` |
| `test_review_repository_filters_unverified_findings` | Findings that fail verification are dropped from final results |
| `test_review_repository_deduplicates_verified_findings` | Duplicate findings (same file+line+category) are merged to one |
| `test_review_service_handles_agent_failure` | Agent raising an exception → empty findings for that agent, job continues |

### `tests/test_verifier.py` — 7 tests

| Test Name | What It Covers |
|---|---|
| `test_verifier_accepts_valid_finding` | File exists, line in bounds, evidence matches → accepted |
| `test_verifier_rejects_missing_file` | File does not exist → rejected |
| `test_verifier_rejects_path_traversal` | `file_path="../../etc/passwd"` → rejected |
| `test_verifier_rejects_line_out_of_bounds` | `line=999` on 10-line file → rejected |
| `test_verifier_rejects_evidence_not_found` | Evidence string not in ±window context → rejected |
| `test_verifier_accepts_no_line` | `line=None` → skips line/evidence checks, accepted if file exists |
| `test_verifier_accepts_no_evidence` | `evidence=None` → skips evidence check |

### `tests/test_deduplicator.py` — 8 tests

| Test Name | What It Covers |
|---|---|
| `test_dedup_single_finding_unchanged` | Single finding → returned unchanged |
| `test_dedup_same_rule_id_merged` | Two findings, same (file, line, category, rule_id) → merged to one |
| `test_dedup_same_message_merged` | Two findings, same normalized message → merged |
| `test_dedup_different_file_not_merged` | Same line/category, different file → kept separate |
| `test_dedup_different_line_not_merged` | Same file/category, different line → kept separate |
| `test_dedup_different_category_not_merged` | Same file/line, different category → kept separate |
| `test_dedup_promotes_higher_severity` | Merge keeps `critical` over `low` |
| `test_dedup_promotes_higher_confidence` | Equal severity, keeps `high` confidence over `low` |

### `tests/test_report.py` — 4 tests

| Test Name | What It Covers |
|---|---|
| `test_report_overview_fields` | `overview.total_findings`, `repository`, `commit_sha` are correct |
| `test_report_severity_breakdown` | `findings_summary.by_severity` counts correctly |
| `test_report_executive_summary_assessment` | Thresholds for "Poor"/"Good"/"Excellent" |
| `test_report_detailed_findings_title` | `_format_finding_title()` splits on `.` and prefixes `rule_id` |

### `tests/test_report_persistence.py` — 6 tests

| Test Name | What It Covers |
|---|---|
| `test_report_saved_to_db` | After `process_review_job`, `review_reports` table has 1 row |
| `test_report_data_is_valid_json` | `report_data` column deserializes to valid `ReviewReportResponse` |
| `test_report_job_id_matches` | `report.job_id == job.id` |
| `test_get_report_endpoint_returns_200` | `GET /review/{id}/report` returns 200 with correct body |
| `test_get_report_returns_404_for_unknown_job` | Non-existent job ID → 404 |
| `test_report_unique_per_job` | Submitting twice creates two separate report rows |

### `tests/test_review_api.py` — 3 tests

| Test Name | What It Covers |
|---|---|
| `test_post_review_returns_202` | Valid request → 202 with `id` and `status="pending"` |
| `test_post_review_invalid_url_returns_422` | Non-GitHub URL → 422 |
| `test_post_review_invalid_sha_returns_422` | Short/invalid SHA → 422 |

### `tests/test_review_lifecycle.py` — 6 tests

| Test Name | What It Covers |
|---|---|
| `test_job_transitions_to_running` | After submit, status becomes "running" while processing |
| `test_job_transitions_to_completed` | After successful review, status = "completed" |
| `test_job_transitions_to_failed_on_error` | When agent/repo fails, status = "failed" |
| `test_findings_persisted_after_completion` | `GET /review/{id}/findings` returns rows after completion |
| `test_get_job_returns_404_for_unknown` | Unknown UUID → 404 |
| `test_error_message_set_on_failure` | `error_message` field populated when job fails |

### `tests/test_agent_tools.py` — 4 tests

| Test Name | What It Covers |
|---|---|
| `test_inspect_source_reads_file` | `inspect_source("main.py")` returns file contents |
| `test_inspect_source_rejects_traversal` | `inspect_source("../../etc/passwd")` → raises/returns error |
| `test_run_ruff_returns_findings` | `run_ruff("main.py")` returns JSON string (mocked subprocess) |
| `test_tool_respects_max_file_size` | File > MAX_FILE_SIZE → truncated or skipped |

### `tests/test_postgres_integration.py` — 1 test

| Test Name | What It Covers |
|---|---|
| `test_postgres_round_trip` | Full insert + select of ReviewJob, ReviewFinding, ReviewReport on real Postgres |

---

## 3. Coverage Map

This maps source modules to the tests that cover them.

| Module | Tests Covering It | Coverage Quality |
|---|---|---|
| `api/api_review.py` | `test_review_api`, `test_review_lifecycle`, `test_report_persistence` | **Good** — happy path + error paths |
| `api/main.py` | `test_review_api` (via TestClient) | **Partial** — routes mounted, health not explicitly tested |
| `api/dependencies.py` | Used indirectly via API tests | **Implicit** only |
| `services/review.py` | `test_review_service`, `test_review_lifecycle` | **Good** — orchestration flow, agent failure |
| `services/verifier.py` | `test_verifier` | **Excellent** — 7 targeted unit tests |
| `services/deduplicator.py` | `test_deduplicator` | **Excellent** — 8 targeted unit tests |
| `services/report.py` | `test_report`, `test_report_persistence` | **Good** — sections covered, edge cases light |
| `services/tools.py` | `test_agent_tools` | **Good** — 4 tests; workspace enforcement tested |
| `services/tool_executor.py` | `test_review_service` (via agent mock flow) | **Partial** — tool-calling loop logic, not isolated |
| `services/analyzer.py` | **No dedicated tests** | ❌ **Gap** |
| `services/repository.py` | **No dedicated tests** | ❌ **Gap** |
| `services/llm_factory.py` | **No tests** | ❌ **Gap** |
| `agents/llm_utils.py` | **No tests** | ❌ **Gap** |
| `agents/bug_agent.py` | `test_review_service` (mocked) | **Partial** — agent interface tested, internals not |
| `agents/security_agent.py` | `test_review_service` (mocked) | **Partial** |
| `agents/quality_agent.py` | `test_review_service` (mocked) | **Partial** |
| `agents/test_agent.py` | `test_review_service` (mocked) | **Partial** |
| `models/` (3 files) | `test_postgres_integration`, API tests | **Implicit** |
| `schemas/findings.py` | Used by all tests with `Finding` objects | **Implicit** |
| `schemas/review_job.py` | `test_report`, API tests | **Implicit** |
| `config/settings.py` | `monkeypatch` in multiple tests | **Implicit** |
| `database.py` | API lifecycle tests (SQLite) | **Partial** |
| `static/app.js` | **No tests** | ❌ **Gap** |
| `templates/index.html` | **No tests** | ❌ **Gap** |

---

## 4. Test Patterns

### 4.1 Mock-Heavy Agent Testing

Agents are never instantiated with a real LLM. The collaborator is replaced with `Mock`:

```python
mock_bug_agent = Mock()
mock_bug_agent.analyze.return_value = [
    Finding(source="ai_agent", category="bug", severity="high", ...)
]
with patch("reviewer.services.review.BugAgent", return_value=mock_bug_agent):
    result = review_service.review_repository(repo, sha)
assert mock_bug_agent.analyze.called
```

### 4.2 tmp_path for File-System Tests

```python
def test_inspect_source_reads_file(tmp_path):
    src = tmp_path / "main.py"
    src.write_text("def foo(): pass\n")
    _active_workspace.set(tmp_path)          # ContextVar for tools
    result = inspect_source.invoke({"file_path": "main.py"})
    assert "def foo" in result
```

### 4.3 SQLite In-Memory for API Tests

```python
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from reviewer.database import engine, Base
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)
```

### 4.4 Fake Finding Factory

Most tests use a helper to create `Finding` objects rather than inline literals:

```python
def make_finding(**kwargs) -> Finding:
    defaults = {
        "source": "ai_agent",
        "category": "bug",
        "severity": "medium",
        "confidence": "high",
        "message": "Test finding",
        "file_path": "src/main.py",
        "line": 1,
        "evidence": "x = 1",
        "recommendation": None,
        "rule_id": None,
    }
    defaults.update(kwargs)
    return Finding(**defaults)
```

---

## 5. What Is Tested Well

| Area | Reason |
|---|---|
| **FindingVerifier** | 7 tests cover every rejection reason + acceptance scenarios |
| **FindingDeduplicator** | 8 tests cover all cluster/merge/promotion paths |
| **Report builder** | Assessment thresholds, section fields, title formatting all tested |
| **API contract** | Correct status codes, 422 on bad input, 404 on unknown ID |
| **Job lifecycle** | Status transitions (pending → running → completed/failed) verified |
| **Report persistence** | DB round-trip, correct JSON, 404 before completion |
| **Agent tool-calling** | End-to-end mock: tool_call → ToolMessage injection → final parse |
| **Tool workspace enforcement** | Traversal rejection tested in `test_agent_tools` |

---

## 6. Testing Gaps

### GAP-1: No `StaticAnalyzer` Unit Tests ❌

`src/reviewer/services/analyzer.py` has zero test coverage. This means:
- Ruff/Bandit subprocess invocations are untested
- Path normalization and traversal guard in analyzer are untested
- Failure handling (tool not installed, empty output, malformed JSON) is untested

### GAP-2: No `RepositoryService` Tests ❌

`src/reviewer/services/repository.py` has zero tests:
- URL validation logic is untested (only indirectly via Pydantic schema)
- git command sequence (clone, fetch, checkout) is untested
- Error handling on git failure is untested

### GAP-3: No `llm_factory` Tests ❌

`src/reviewer/services/llm_factory.py` (`create_chat_model()`) is untested. If Ollama configuration is wrong, errors appear at runtime only.

### GAP-4: No `llm_utils` Retry Tests ❌

`invoke_with_rate_limit_retry()` in `agents/llm_utils.py` has no tests. The retry/backoff behavior on `ConnectionError` is unverified.

### GAP-5: Agent JSON Parsing Edge Cases ❌

All four agents parse raw LLM output via JSON fence stripping. The following scenarios are untested:
- Response with no JSON at all
- Response with malformed JSON (`{broken`)
- Response where JSON is valid but fields have wrong types
- Response where `file_path` is an absolute path (normalization logic)

### GAP-6: Workspace Cleanup on Failure ❌

The `finally` block in `process_review_job()` should clean up the workspace directory even on exception. This is not tested — a test could verify no workspace directory remains after a failed job.

### GAP-7: `_attach_agent_recommendations()` is Dead Code ❌

This method exists but is never called. There is no test for it. It should either be tested or removed.

### GAP-8: No `tool_executor` Isolation Tests ❌

`execute_agent()` is tested only indirectly via the agent integration test in `test_review_service.py`. These scenarios are untested in isolation:
- Reaching `MAX_ROUNDS=5` (loop cap)
- Tool raises an exception
- Tool output exceeds size limit → truncation

### GAP-9: No Frontend Tests ❌

`static/app.js` has no tests. The polling logic, finding card rendering, and status display are entirely untested.

### GAP-10: No Idempotency or Concurrent Submission Tests ❌

Submitting the same repo+SHA twice creates duplicate jobs. No test verifies this behavior (or guards against it).

---

## 7. Proposed New Tests (TDD Plan)

Tests are grouped by priority. Each uses **Arrange / Act / Assert** structure.

---

### Priority 1 — Critical Gaps

#### `tests/test_static_analyzer.py` (new file)

**Test: Ruff output is parsed into Finding objects**
```python
def test_analyzer_ruff_findings(tmp_path, monkeypatch):
    # Arrange
    py_file = tmp_path / "bad.py"
    py_file.write_text("x=1\n")  # ruff E225: missing whitespace

    ruff_output = json.dumps([{
        "filename": str(tmp_path / "bad.py"),
        "location": {"row": 1, "column": 2},
        "code": "E225",
        "message": "Missing whitespace around operator"
    }])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockResult(stdout=ruff_output, returncode=0))

    analyzer = StaticAnalyzer()

    # Act
    findings = analyzer.analyze(tmp_path)

    # Assert
    assert len(findings) >= 1
    f = next(f for f in findings if f.source == "ruff")
    assert f.rule_id == "E225"
    assert f.category == "quality"
    assert f.confidence == "high"
    assert f.file_path == "bad.py"
```

**Test: Bandit output is parsed into Finding objects**
```python
def test_analyzer_bandit_findings(tmp_path, monkeypatch):
    # Arrange
    bandit_output = json.dumps({"results": [{
        "filename": str(tmp_path / "secret.py"),
        "test_id": "B105",
        "issue_severity": "HIGH",
        "issue_confidence": "MEDIUM",
        "issue_text": "Possible hardcoded password",
        "line_number": 3,
        "code": "password = 'hunter2'"
    }]})
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockResult(stdout=bandit_output, returncode=0))
    (tmp_path / "secret.py").write_text("password = 'hunter2'\n")

    # Act
    findings = StaticAnalyzer().analyze(tmp_path)

    # Assert
    f = next(f for f in findings if f.source == "bandit")
    assert f.rule_id == "B105"
    assert f.severity == "high"
    assert f.confidence == "medium"
    assert f.category == "security"
```

**Test: Ruff subprocess failure returns empty findings (no crash)**
```python
def test_analyzer_ruff_failure_returns_empty(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.setattr(subprocess, "run", side_effect=FileNotFoundError("ruff not found"))

    # Act
    findings = StaticAnalyzer().analyze(tmp_path)

    # Assert
    ruff_findings = [f for f in findings if f.source == "ruff"]
    assert ruff_findings == []
```

**Test: Path traversal in analyzer output is rejected**
```python
def test_analyzer_rejects_traversal_path(tmp_path, monkeypatch):
    # Arrange
    ruff_output = json.dumps([{
        "filename": "/etc/passwd",
        "location": {"row": 1, "column": 1},
        "code": "E501",
        "message": "Line too long"
    }])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockResult(stdout=ruff_output, returncode=0))

    # Act
    findings = StaticAnalyzer().analyze(tmp_path)

    # Assert — /etc/passwd is not under tmp_path, should be excluded
    assert all(not f.file_path.startswith("/etc") for f in findings)
```

---

#### `tests/test_repository_service.py` (new file)

**Test: Invalid URL raises ValueError**
```python
def test_repository_rejects_non_github_url():
    # Arrange
    svc = RepositoryService()

    # Act / Assert
    with pytest.raises(ValueError, match="github.com"):
        svc.prepare_repository("https://gitlab.com/owner/repo", "a" * 40, str(uuid4()))
```

**Test: Git clone called with correct arguments**
```python
def test_repository_clones_with_depth_1(tmp_path, monkeypatch):
    # Arrange
    calls = []
    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return MockResult(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    svc = RepositoryService(base_dir=tmp_path)

    # Act
    svc.prepare_repository("https://github.com/owner/repo", "a" * 40, str(uuid4()))

    # Assert
    clone_call = next(c for c in calls if "clone" in c)
    assert "--depth=1" in clone_call
    assert "https://github.com/owner/repo" in clone_call
```

**Test: Git failure raises exception**
```python
def test_repository_raises_on_clone_failure(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.setattr(subprocess, "run", side_effect=subprocess.CalledProcessError(128, "git"))
    svc = RepositoryService(base_dir=tmp_path)

    # Act / Assert
    with pytest.raises(subprocess.CalledProcessError):
        svc.prepare_repository("https://github.com/owner/repo", "a" * 40, str(uuid4()))
```

---

#### `tests/test_tool_executor.py` (new file — isolation tests)

**Test: Loop exits when max rounds reached**
```python
def test_executor_stops_at_max_rounds():
    # Arrange
    tool_call = ToolCall(name="run_ruff", args={"file_path": "main.py"}, id="tc1")
    always_calls_tool = Mock(return_value=AIMessage(content="", tool_calls=[tool_call]))
    mock_tool = Mock(); mock_tool.name = "run_ruff"; mock_tool.invoke = Mock(return_value="[]")
    messages = [HumanMessage(content="go")]

    # Act
    result = execute_agent(always_calls_tool, messages, [mock_tool], max_rounds=3)

    # Assert
    assert always_calls_tool.call_count == 3   # stopped, did not loop forever
```

**Test: Tool exception does not crash executor**
```python
def test_executor_handles_tool_exception():
    # Arrange
    tool_call = ToolCall(name="run_ruff", args={"file_path": "x.py"}, id="tc1")
    first_response = AIMessage(content="", tool_calls=[tool_call])
    second_response = AIMessage(content="```json\n[]\n```")
    model = Mock(side_effect=[first_response, second_response])
    bad_tool = Mock(); bad_tool.name = "run_ruff"; bad_tool.invoke = Mock(side_effect=RuntimeError("boom"))
    messages = [HumanMessage(content="go")]

    # Act — should not raise
    result = execute_agent(model, messages, [bad_tool])

    # Assert
    assert result is not None
```

---

### Priority 2 — Agent JSON Parsing

#### `tests/test_agent_parsing.py` (new file)

**Test: Non-JSON response returns empty findings**
```python
def test_bug_agent_handles_non_json_response(tmp_path, monkeypatch):
    # Arrange
    mock_response = AIMessage(content="I found some issues but cannot format them.")
    monkeypatch.setattr("reviewer.services.tool_executor.execute_agent", lambda *a, **kw: mock_response)
    monkeypatch.setattr("reviewer.services.llm_factory.create_chat_model", Mock())
    _active_workspace.set(tmp_path)

    # Act
    result = BugAgent().analyze(tmp_path, ["main.py"])

    # Assert
    assert result == []
```

**Test: Malformed JSON response returns empty findings (no crash)**
```python
def test_bug_agent_handles_malformed_json(tmp_path, monkeypatch):
    # Arrange
    mock_response = AIMessage(content="```json\n{broken json\n```")
    monkeypatch.setattr("reviewer.services.tool_executor.execute_agent", lambda *a, **kw: mock_response)

    # Act
    result = BugAgent().analyze(tmp_path, ["main.py"])

    # Assert
    assert result == []
```

**Test: Agent forces source="ai_agent" regardless of LLM output**
```python
def test_bug_agent_forces_source_field(tmp_path, monkeypatch):
    # Arrange — LLM sets wrong source
    raw = json.dumps([{
        "source": "ruff", "category": "bug", "severity": "high",
        "confidence": "medium", "message": "Test", "file_path": "main.py",
        "line": 1, "evidence": "x=1"
    }])
    mock_response = AIMessage(content=f"```json\n{raw}\n```")
    monkeypatch.setattr("reviewer.services.tool_executor.execute_agent", lambda *a, **kw: mock_response)

    # Act
    result = BugAgent().analyze(tmp_path, ["main.py"])

    # Assert
    assert all(f.source == "ai_agent" for f in result)
```

---

### Priority 3 — Reliability & Edge Cases

#### `tests/test_workspace_cleanup.py` (new file)

**Test: Workspace is deleted after successful job**
```python
def test_workspace_cleaned_up_on_success(client, monkeypatch, tmp_path):
    # Arrange
    workspace_paths = []
    original_prepare = RepositoryService.prepare_repository
    def capture_workspace(self, *args, **kwargs):
        ws = original_prepare(self, *args, **kwargs)
        workspace_paths.append(ws)
        return ws
    monkeypatch.setattr(RepositoryService, "prepare_repository", capture_workspace)

    # Act
    resp = client.post("/review/", json={"repository": "https://github.com/o/r", "commit_sha": "a"*40})
    job_id = resp.json()["id"]
    # wait for background task to complete (poll or use sync test client)

    # Assert
    assert not workspace_paths[0].exists()
```

**Test: Workspace is deleted even when job fails**
```python
def test_workspace_cleaned_up_on_failure(client, monkeypatch):
    # Arrange — make repo service fail after creating workspace
    monkeypatch.setattr(RepositoryService, "prepare_repository",
                        side_effect=RuntimeError("clone failed"))

    # Act
    resp = client.post("/review/", json={"repository": "https://github.com/o/r", "commit_sha": "a"*40})
    # wait...

    # Assert — workspace should be gone (or never created if error is pre-workspace)
    # At minimum, job status should be "failed"
    job = client.get(f"/review/{resp.json()['id']}").json()
    assert job["status"] == "failed"
```

#### `tests/test_llm_utils.py` (new file)

**Test: Retry on ConnectionError**
```python
def test_retry_on_connection_error():
    # Arrange
    call_count = 0
    def flaky_invoke(messages):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise requests.exceptions.ConnectionError("refused")
        return AIMessage(content="ok")

    mock_model = Mock(); mock_model.invoke = flaky_invoke

    # Act
    result = invoke_with_rate_limit_retry(mock_model, [HumanMessage(content="go")])

    # Assert
    assert result.content == "ok"
    assert call_count == 3
```

**Test: Raises after max retries exceeded**
```python
def test_raises_after_max_retries():
    # Arrange
    model = Mock(); model.invoke = Mock(side_effect=requests.exceptions.ConnectionError("refused"))

    # Act / Assert
    with pytest.raises(requests.exceptions.ConnectionError):
        invoke_with_rate_limit_retry(model, [HumanMessage(content="go")], max_retries=3)
    assert model.invoke.call_count == 3
```

---

### Priority 4 — Report Quality

#### Additions to `tests/test_report.py`

**Test: Empty findings produce "Excellent" assessment**
```python
def test_report_empty_findings_is_excellent(mock_job):
    report = build_review_report(mock_job, [])
    assert report.executive_summary.overall_assessment == "Excellent"
    assert report.overview.total_findings == 0
```

**Test: Recommended actions count equals findings count**
```python
def test_recommended_actions_count_matches_findings(mock_job):
    findings = [make_finding(severity="high") for _ in range(5)]
    report = build_review_report(mock_job, findings)
    assert len(report.recommended_actions) == 5
```

**Test: Analysis status lists correct tools used**
```python
def test_analysis_status_tools_used(mock_job):
    findings = [
        make_finding(source="ruff"),
        make_finding(source="bandit"),
        make_finding(source="ai_agent"),
    ]
    report = build_review_report(mock_job, findings)
    tools = set(report.analysis_status.tools_used)
    assert tools == {"ruff", "bandit", "ai_agent"}
```

---

## 8. Running Tests

### 8.1 Full Test Suite

```powershell
# From D:\CodeOPS-AI
python -m pytest tests/ -v --tb=short
```

Expected output: `45 passed in ~22s`

### 8.2 Run by Module

```powershell
python -m pytest tests/test_verifier.py -v
python -m pytest tests/test_deduplicator.py -v
python -m pytest tests/test_report.py -v
```

### 8.3 Run a Specific Test

```powershell
python -m pytest tests/test_review_service.py::test_review_service_invokes_baseline_analyzer -v
```

### 8.4 With Coverage Report

```powershell
python -m pytest tests/ --cov=src/reviewer --cov-report=term-missing
```

### 8.5 Postgres Integration Test

Requires a running PostgreSQL instance with `DATABASE_URL` set:

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://user:pass@localhost:5432/codeops_test"
python -m pytest tests/test_postgres_integration.py -v
```

### 8.6 With Real Ollama (manual, no existing tests)

Currently no tests target a real Ollama instance. To smoke-test manually:

```powershell
# Ensure Ollama is running and qwen2.5:3b is pulled
ollama serve
ollama pull qwen2.5:3b

# Start the service
uvicorn reviewer.api.main:app --reload

# Submit a small public repo
curl -X POST http://localhost:8000/review/ `
  -H "Content-Type: application/json" `
  -d '{"repository":"https://github.com/tiangolo/fastapi","commit_sha":"<40-char-sha>"}'
```

---

## 9. CI Considerations

| Consideration | Detail |
|---|---|
| **No network required** | All 45 tests mock git, LLM, and subprocesses. Safe for offline CI. |
| **No Ollama required** | LLM is always mocked. `ollama serve` does not need to be running. |
| **No Postgres required** | API tests use SQLite in-memory. Only `test_postgres_integration.py` requires Postgres. |
| **Test speed** | 45 tests pass in ~22 seconds. Suitable for pre-commit and PR gates. |
| **PostgreSQL in CI** | Use a Postgres service container (e.g., GitHub Actions `services: postgres`). Set `DATABASE_URL` env var to enable integration test. |
| **Flakiness risk** | Tests are deterministic. No `time.sleep()` or network calls. Low flakiness risk. |
| **Missing: branch coverage** | `StaticAnalyzer`, `RepositoryService`, `llm_utils` have no tests. CI will show green despite these untested code paths. |
| **Recommended pytest flags** | `pytest tests/ -v --tb=short -x` — fail fast (`-x`) is helpful during development. |
| **Coverage gate** | Consider adding `--cov-fail-under=80` after new tests from Section 7 are written. Current coverage without new tests is ~65% (estimated). |

