# CodeOPS-AI — Test-Driven Development Document

> **Status:** Updated 2026-11-02  
> **Purpose:** Document the current test infrastructure, existing test inventory, tested behavior, testing gaps, and proposed future tests.
>
> **Accuracy note:** The existing test inventory below is based on the current `tests/` directory and its discovered test functions. A listed test confirms that a test exists; it does not automatically mean that every branch of the related implementation is covered.

---

## Table of Contents

1. Test Infrastructure
2. Test Inventory
3. Test Coverage Map
4. Test Patterns
5. Areas with Existing Tests
6. Testing Gaps
7. Proposed New Tests
8. Running Tests
9. CI Considerations

---

## 1. Test Infrastructure

The project uses `pytest` as its Python testing framework.

### 1.1 Testing tools

| Tool | Purpose |
|---|---|
| pytest | Test discovery and execution |
| pytest fixtures | Reusable test setup and dependencies |
| `tmp_path` | Temporary directories for filesystem-related tests |
| `monkeypatch` | Replacing functions, attributes, or environment values during tests |
| unittest.mock | Mocking dependencies and external behavior where used |
| PostgreSQL | Database integration testing |

The test files use the standard `test_*.py` naming convention.

### 1.2 Test organization

Current test directory:

```text
tests/
│
├── test_agent_tools.py
├── test_deduplicator.py
├── test_postgres_integration.py
├── test_report.py
├── test_report_persistence.py
├── test_review_api.py
├── test_review_lifecycle.py
├── test_review_service.py
└── test_verifier.py
```

### 1.3 Testing approach

The test suite covers several levels of application behavior:

- Individual service behavior.
- Agent and tool integration.
- Finding verification and deduplication.
- Report generation.
- API behavior.
- Review job lifecycle.
- Database persistence.
- PostgreSQL integration.

The tests use temporary directories, test doubles, and database-related setup where appropriate.

The exact fixture configuration and database isolation strategy should be verified against the current test setup before being documented as a project-wide guarantee.

---

## 2. Test Inventory

The current test inventory contains **45 discovered test functions across 9 test files**.

<text> </text>

### 2.1 Agent tools and tool execution

**File:** `tests/test_agent_tools.py`

**Test count:** 4

| Test | Responsibility |
|---|---|
| `test_active_workspace_context` | Tests active workspace context behavior |
| `test_active_workspace_token_reset` | Tests workspace context reset |
| `test_active_workspace_separate_contexts_isolated` | Tests isolation between workspace contexts |
| `test_execute_agent_tool_calling_loop` | Tests the agent tool-calling loop |

### 2.2 Finding deduplication

**File:** `tests/test_deduplicator.py`

**Test count:** 8

| Test | Responsibility |
|---|---|
| `test_merges_exact_duplicate_findings_on_same_line` | Ensures duplicate findings are merged |
| `test_preserves_distinct_categories_on_same_line` | Ensures different categories remain separate |
| `test_preserves_distinct_issues_with_different_rules_on_same_line` | Ensures different rule identifiers are preserved |
| `test_retains_highest_severity_when_merging` | Checks severity selection |
| `test_findings_in_different_files_never_merge` | Prevents merging across files |
| `test_findings_on_different_lines_never_merge` | Prevents merging across lines |
| `test_preserves_evidence_and_recommendation_when_merging` | Checks retained finding information |
| `test_deduplicate_empty_list` | Tests empty input |

### 2.3 PostgreSQL integration

**File:** `tests/test_postgres_integration.py`

**Test count:** 1

| Test | Responsibility |
|---|---|
| `test_postgres_report_persistence_and_query` | Tests report persistence and querying against PostgreSQL |

This is an integration test and may require a configured PostgreSQL database.

### 2.4 Report generation

**File:** `tests/test_report.py`

**Test count:** 4

| Test | Responsibility |
|---|---|
| `test_build_report_empty_findings` | Tests report generation with no findings |
| `test_build_report_with_findings_and_prioritization` | Tests report generation and prioritization |
| `test_build_report_partial_review_status` | Tests report generation for partial review status |
| `test_build_report_with_review_finding_db_objects` | Tests report generation using database finding objects |

### 2.5 Report persistence

**File:** `tests/test_report_persistence.py`

**Test count:** 6

| Test | Responsibility |
|---|---|
| `test_completed_job_persists_report_and_retrieves_via_api` | Tests persistence and API retrieval of completed reports |
| `test_partial_completion_job_stores_correct_status_and_limitations` | Tests partial completion report persistence |
| `test_reprocessing_does_not_create_duplicate_reports` | Tests duplicate report prevention during reprocessing |
| `test_get_report_nonexistent_job_returns_404` | Tests missing job response |
| `test_get_report_queued_or_running_job_returns_409` | Tests report retrieval for jobs that are not finished |
| `test_terminal_job_missing_report_returns_404` | Tests missing report for a terminal job |

### 2.6 Review API

**File:** `tests/test_review_api.py`

**Test count:** 3

| Test | Responsibility |
|---|---|
| `test_get_missing_review_job_returns_404` | Tests retrieval of a nonexistent review job |
| `test_get_findings_for_missing_job_returns_404` | Tests findings retrieval for a nonexistent job |
| `test_create_review_job_returns_202` | Tests successful review job submission |

### 2.7 Review lifecycle

**File:** `tests/test_review_lifecycle.py`

**Test count:** 6

| Test | Responsibility |
|---|---|
| `test_create_review_job_rejects_invalid_url` | Tests invalid repository URL validation |
| `test_create_review_job_rejects_invalid_commit_sha` | Tests invalid commit SHA validation |
| `test_create_review_job_accepts_valid_ssh_url` | Tests acceptance of a valid SSH repository URL |
| `test_lifecycle_transitions_to_completed_with_findings` | Tests successful review completion |
| `test_lifecycle_transitions_to_completed_partial_on_agent_failure` | Tests partial completion after agent failure |
| `test_lifecycle_transitions_to_failed_on_fatal_exception` | Tests failed job status after a fatal exception |

### 2.8 Review service

**File:** `tests/test_review_service.py`

**Test count:** 6

| Test | Responsibility |
|---|---|
| `test_review_continues_when_one_agent_fails` | Tests review continuation after an individual agent failure |
| `test_review_repository_filters_unverified_findings` | Tests filtering of unverified findings |
| `test_review_repository_deduplicates_verified_findings` | Tests deduplication of verified findings |
| `test_review_repository_uses_agents_without_baseline_analyzer` | Tests the current agent-based review flow without the old baseline analyzer |
| `test_agent_invokes_assigned_tool_and_uses_result_in_analysis` | Tests agent integration with assigned tools |
| `test_agent_and_tool_failures_record_agent_failures_without_false_success` | Tests failure recording for agents and tools |

### 2.9 Finding verification

**File:** `tests/test_verifier.py`

**Test count:** 7

| Test | Responsibility |
|---|---|
| `test_verifier_accepts_valid_finding` | Tests acceptance of a valid finding |
| `test_verifier_rejects_hallucinated_line` | Tests rejection of an invalid reported line |
| `test_verifier_rejects_nonexistent_file` | Tests rejection of nonexistent files |
| `test_verifier_rejects_path_traversal` | Tests path traversal protection |
| `test_verifier_rejects_evidence_on_wrong_line` | Tests rejection of incorrect evidence location |
| `test_verifier_accepts_multiline_evidence_at_line` | Tests multiline evidence handling |
| `test_verifier_validates_tool_findings` | Tests verification of tool-generated findings |

### 2.10 Test count summary

| Test file | Number of tests |
|---|---:|
| `test_agent_tools.py` | 4 |
| `test_deduplicator.py` | 8 |
| `test_postgres_integration.py` | 1 |
| `test_report.py` | 4 |
| `test_report_persistence.py` | 6 |
| `test_review_api.py` | 3 |
| `test_review_lifecycle.py` | 6 |
| `test_review_service.py` | 6 |
| `test_verifier.py` | 7 |
| **Total** | **45** |

---

## 3. Test Coverage Map

This table maps major implementation areas to their current test files.

| Implementation area | Related test file | Testing status |
|---|---|---|
| Agent workspace context | `test_agent_tools.py` | Existing tests |
| Agent tool-calling loop | `test_agent_tools.py` | Existing tests |
| Agent-to-tool integration | `test_review_service.py` | Existing tests |
| Review orchestration | `test_review_service.py` | Existing tests |
| Finding verification | `test_verifier.py` | Existing tests |
| Finding deduplication | `test_deduplicator.py` | Existing tests |
| Report generation | `test_report.py` | Existing tests |
| Report persistence | `test_report_persistence.py` | Existing tests |
| Review API | `test_review_api.py` | Existing tests |
| Review lifecycle | `test_review_lifecycle.py` | Existing tests |
| PostgreSQL persistence | `test_postgres_integration.py` | Existing integration test |

### Areas without a dedicated test file in the current inventory

The following areas do not have a separately named test module in the current test directory:

- Repository preparation.
- LLM model factory.
- LLM retry utilities.
- Individual agent response parsing.
- Workspace cleanup behavior.
- Tool executor edge cases beyond the existing tool-loop test.
- Frontend behavior.

This does not prove that none of these behaviors are indirectly exercised. It means there is no dedicated test module for them in the current inventory.

---

## 4. Test Patterns

The following are common testing techniques used or identifiable in the current test suite.

### 4.1 Temporary directories

Tests that require repository files or workspace directories can use pytest's `tmp_path` fixture.

Example:

```python
def test_example(tmp_path):
    source_file = tmp_path / "example.py"
    source_file.write_text("print('hello')")
    
    assert source_file.exists()
```

This avoids relying on a permanent project directory for temporary test files.

### 4.2 Monkeypatching

Tests can use `monkeypatch` to replace functions or dependencies during execution.

This is useful when testing:

- Agent failures.
- Tool failures.
- API background processing.
- Database-related behavior.
- External service dependencies.

The exact patch targets are defined in each individual test.

### 4.3 Finding test data

Finding-related tests need valid finding objects.

The project uses the Pydantic `Finding` schema as the common structure for findings from static tools and agents.

Tests should construct findings that satisfy the current schema rather than relying on outdated field definitions.

### 4.4 Isolated workspace context

The agent tools use an active workspace context.

The workspace tests check context assignment, reset behavior, and isolation between contexts.

These tests are important because tools must operate on the correct repository workspace.

### 4.5 Database integration

The test suite contains a dedicated PostgreSQL integration test.

It should be run with the required PostgreSQL configuration available.

Do not assume that a successful SQLite-based test run also proves PostgreSQL integration works.

---

## 5. Areas with Existing Tests

### 5.1 Finding verification

The verifier has seven dedicated tests.

Existing coverage includes:

- Valid finding acceptance.
- Nonexistent file rejection.
- Invalid line rejection.
- Path traversal rejection.
- Evidence validation.
- Multiline evidence.
- Tool-generated findings.

### 5.2 Finding deduplication

The deduplicator has eight dedicated tests.

Existing coverage includes:

- Exact duplicate merging.
- Different categories.
- Different rule identifiers.
- Severity selection.
- Different files.
- Different lines.
- Evidence and recommendation preservation.
- Empty input.

### 5.3 Agent and tool integration

The tests cover:

- Active workspace context.
- Context isolation.
- Tool-calling loop execution.
- Agent invocation of assigned tools.
- Use of tool results in agent analysis.
- Recording agent and tool failures.

### 5.4 Review lifecycle

The lifecycle tests cover:

- Request validation.
- Valid repository submission.
- Successful completion.
- Partial completion.
- Fatal review failure.

### 5.5 Report generation and persistence

The report tests cover:

- Empty findings.
- Findings and prioritization.
- Partial review status.
- Database finding objects.
- Completed report persistence.
- Partial report persistence.
- Duplicate report prevention.
- API retrieval errors.

---

## 6. Testing Gaps

The following are proposed testing areas, not claims that tests already exist.

### GAP-1: Repository preparation

**Implementation area:** `src/reviewer/services/repository.py`

There is no dedicated `tests/test_repository_service.py` in the current inventory.

Important behaviors to test:

- Successful repository preparation.
- Invalid repository input.
- Git clone failure.
- Git fetch failure.
- Checkout failure.
- Workspace cleanup after preparation failure.
- Correct commit checkout.

### GAP-2: LLM model factory

**Implementation area:** LLM model factory and configuration.

There is no dedicated model-factory test file in the current inventory.

Important behaviors to test:

- Correct model configuration.
- Correct provider selection.
- Missing configuration handling.
- Invalid configuration handling.

### GAP-3: LLM retry utilities

**Implementation area:** LLM utility/retry module.

There is no dedicated retry utility test file in the current inventory.

Important behaviors to test:

- Retry on supported connection errors.
- Retry on supported timeout errors.
- Stop after the configured retry limit.
- Propagate unsupported exceptions.
- Verify retry delays without introducing real waiting into tests.

The exact exception classes and retry parameters must match the current implementation.

### GAP-4: Agent response parsing

**Implementation area:** Individual agent modules.

There is no dedicated agent-parsing test file in the current inventory.

Important behaviors to test:

- Valid JSON response.
- JSON response wrapped in Markdown fences.
- Invalid JSON response.
- Empty response.
- Missing required fields.
- Invalid finding schema.
- Incorrect file paths.
- Agent-specific source and category normalization.

### GAP-5: Workspace cleanup

**Implementation area:** Background review processing and repository workspace management.

Existing tests cover workspace context isolation, but there is no dedicated cleanup test file in the current inventory.

Important behaviors to test:

- Cleanup after successful review.
- Cleanup after repository failure.
- Cleanup after agent failure.
- Cleanup after fatal processing exception.
- Context reset after review processing.

### GAP-6: Tool executor edge cases

**Implementation area:** `src/reviewer/services/tool_executor.py`

The existing test suite has one dedicated tool-loop test.

Additional behaviors worth testing:

- Maximum tool rounds.
- Unknown tool names.
- Tool execution exceptions.
- Oversized tool output.
- Tool result truncation.
- Empty tool results.
- Multiple tool calls in one response.

### GAP-7: Frontend testing

There are no dedicated frontend test files in the current test inventory.

Potential future tests:

- Review submission.
- Job status display.
- Findings display.
- Report display.
- API error handling.

### GAP-8: Review concurrency and idempotency

The existing report persistence suite includes a reprocessing test.

Additional concurrency and idempotency scenarios may still need dedicated tests:

- Two requests for the same review.
- Concurrent report creation.
- Duplicate finding prevention.
- Job status consistency after concurrent processing.

### GAP-9: Database failure recovery

Additional tests could verify:

- Failure while persisting findings.
- Failure while persisting a report.
- Failure while updating job status.
- Database rollback behavior.
- Recovery when the database session encounters an error.

---

## 7. Proposed New Tests

These tests should be added incrementally after inspecting the relevant implementation.

They are proposals, not existing test files.

| Priority | Proposed test file | Purpose |
|---|---|---|
| High | `tests/test_repository_service.py` | Verify repository preparation and Git failure handling |
| High | `tests/test_workspace_cleanup.py` | Verify cleanup across success and failure paths |
| High | `tests/test_llm_utils.py` | Verify retry behavior |
| High | `tests/test_agent_parsing.py` | Verify LLM response parsing |
| Medium | `tests/test_tool_executor.py` | Verify tool executor edge cases |
| Medium | Additional report persistence tests | Verify database failure and recovery behavior |
| Medium | Additional lifecycle tests | Verify concurrency and idempotency |
| Low | Frontend tests | Verify user-interface behavior |

### Suggested implementation order

1. Repository preparation tests.
2. Workspace cleanup tests.
3. LLM retry tests.
4. Agent response parsing tests.
5. Tool executor edge-case tests.
6. Database failure and concurrency tests.
7. Frontend tests.

The priority order should be reconsidered when the implementation changes or a specific risk becomes more important.

---

## 8. Running Tests

Run these commands from the project root:

```powershell
D:\CodeOPS-AI
```

Activate the virtual environment if it is not already active:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 8.1 Run the complete test suite

```powershell
python -m pytest tests/ -v --tb=short
```

### 8.2 Run one test file

Example:

```powershell
python -m pytest tests/test_review_service.py -v
```

### 8.3 Run one specific test

Example:

```powershell
python -m pytest tests/test_review_service.py::test_review_repository_uses_agents_without_baseline_analyzer -v
```

### 8.4 Run finding verification tests

```powershell
python -m pytest tests/test_verifier.py -v
```

### 8.5 Run deduplication tests

```powershell
python -m pytest tests/test_deduplicator.py -v
```

### 8.6 Run report tests

```powershell
python -m pytest tests/test_report.py tests/test_report_persistence.py -v
```

### 8.7 Run agent and tool tests

```powershell
python -m pytest tests/test_agent_tools.py tests/test_review_service.py -v
```

### 8.8 Run PostgreSQL integration test

```powershell
python -m pytest tests/test_postgres_integration.py -v
```

This test may require a running PostgreSQL instance and the appropriate database configuration.

### 8.9 Run Ruff

```powershell
ruff check src tests
```

### 8.10 Coverage reporting

If `pytest-cov` is installed in the project environment, coverage can be measured with:

```powershell
python -m pytest tests/ --cov=reviewer --cov-report=term-missing
```

An HTML report can be generated with:

```powershell
python -m pytest tests/ --cov=reviewer --cov-report=html
```

The HTML report is written to the `htmlcov/` directory by default.

**Important:** No overall coverage percentage is stated in this document because a current coverage report has not been provided. Do not claim a specific coverage percentage without running and recording the report.

Pytest supports running complete suites, individual modules, and individual test functions. See the [official pytest command-line documentation](https://docs.pytest.org/en/stable/how-to/usage.html).

Coverage options are provided by [pytest-cov](https://pytest-cov.readthedocs.io/en/latest/).

---

## 9. CI Considerations

The test suite should be executed automatically whenever changes are submitted to the repository.

### Recommended CI checks

1. Install project dependencies.
2. Run Ruff.
3. Run the unit and service test suite.
4. Run integration tests when the required PostgreSQL service is available.
5. Publish test and coverage results.

### Suggested CI commands

```powershell
ruff check src tests
python -m pytest tests/ -v --tb=short
```

PostgreSQL integration tests should run in an environment where the required database service and configuration are available.

### CI principles

- Tests should not depend on a developer's local repository state.
- External LLM calls should not be required for ordinary unit tests.
- Tests should use controlled test data and isolated workspaces.
- Temporary files and resources should be cleaned up.
- Integration tests should clearly identify their external dependencies.
- Coverage thresholds should only be introduced after measuring the actual baseline.

### Current testing baseline

| Item | Current documented status |
|---|---|
| Test files | 9 |
| Discovered test functions | 45 |
| Finding verifier tests | 7 |
| Finding deduplicator tests | 8 |
| Report generation tests | 4 |
| Report persistence tests | 6 |
| Review API tests | 3 |
| Review lifecycle tests | 6 |
| Review service tests | 6 |
| Agent tools tests | 4 |
| PostgreSQL integration tests | 1 |
| Overall coverage percentage | Not measured in this document |

**End of document.**