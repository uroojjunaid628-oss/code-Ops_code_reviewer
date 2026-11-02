# CodeOPS-AI — System Specification

> **Status:** Reflects actual implementation as of 2026-11-02, including uncommitted working-tree changes (Groq → Ollama migration). This is a descriptive spec of what the system does today, not what the SDD prescribes.

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Architecture Overview](#2-architecture-overview)
3. [Configuration Reference](#3-configuration-reference)
4. [Database Schema](#4-database-schema)
5. [API Reference](#5-api-reference)
6. [Data Schemas](#6-data-schemas)
7. [Review Pipeline](#7-review-pipeline)
8. [Agent Contracts](#8-agent-contracts)
9. [Static Analysis](#9-static-analysis)
10. [Report Builder](#10-report-builder)
11. [Known Limitations](#11-known-limitations)
12. [Out of Scope](#12-out-of-scope)

---

## 1. Purpose and Scope

CodeOPS-AI is a **self-hosted, automated Python code-review service**. Given a GitHub repository URL and a commit SHA, it:

1. Shallow-clones the repository at the target commit.
2. Runs deterministic static analysis (Ruff + Bandit) against the workspace.
3. Runs four specialised LLM agents (bug, security, quality, test) against a bounded set of Python files, using tool-calling to gather evidence.
4. Verifies and deduplicates all findings from both sources.
5. Persists findings and a structured report to a relational database.
6. Serves findings and the report over a REST API.

**In-scope inputs:**
- Public or private GitHub repositories via HTTPS (`https://github.com/...`).
- A 40-character hex commit SHA.
- Python source files up to 10 KB, capped at 3 files per agent run.

**Runtime environment:**
- Python 3.12+, FastAPI, SQLAlchemy, PostgreSQL (production) / SQLite (test).
- Ollama running locally at `http://localhost:11434`, model `qwen2.5:3b`.
- Ruff and Bandit installed in the same Python environment.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Browser / curl                                             │
│  POST /review/   GET /review/{id}   GET /review/{id}/report │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP
┌───────────────────────▼─────────────────────────────────────┐
│  FastAPI Application  (src/reviewer/api/main.py)            │
│  Router: api/api_review.py                                  │
│  BackgroundTasks queue (in-process, no persistence)         │
└───┬───────────────────────────────────────────────────────┬─┘
    │ DB session (get_db)                                   │ BackgroundTask
    ▼                                                       ▼
┌──────────────┐                            ┌──────────────────────────────┐
│  PostgreSQL  │                            │  process_review_job()        │
│  3 tables:   │◄───────────────────────────│  api/api_review.py           │
│  review_jobs │                            │                              │
│  review_     │                            │  ┌──────────────────────┐   │
│  findings    │                            │  │ RepositoryService    │   │
│  review_     │                            │  │ services/repository  │   │
│  reports     │                            │  │ git clone + checkout │   │
└──────────────┘                            │  └──────────┬───────────┘   │
                                            │             │workspace       │
                                            │  ┌──────────▼───────────┐   │
                                            │  │ ReviewService        │   │
                                            │  │ services/review.py   │   │
                                            │  │                      │   │
                                            │  │ StaticAnalyzer       │   │
                                            │  │ ├─ Ruff subprocess   │   │
                                            │  │ └─ Bandit subprocess │   │
                                            │  │                      │   │
                                            │  │ 4 LLM Agents         │   │
                                            │  │ ├─ BugAgent          │   │
                                            │  │ ├─ SecurityAgent     │   │
                                            │  │ ├─ QualityAgent      │   │
                                            │  │ └─ TestAgent         │   │
                                            │  │    (via tool_executor│   │
                                            │  │     + Ollama LLM)   │   │
                                            │  │                      │   │
                                            │  │ FindingVerifier      │   │
                                            │  │ FindingDeduplicator  │   │
                                            │  └──────────────────────┘   │
                                            │                              │
                                            │  build_review_report()       │
                                            │  services/report.py          │
                                            └──────────────────────────────┘
```

### File Layout

```
d:\CodeOPS-AI\
├── src/reviewer/
│   ├── api/
│   │   ├── main.py              # FastAPI app init, static mount, root route
│   │   ├── api_review.py        # All /review/* routes + process_review_job()
│   │   └── dependencies.py      # get_db() generator
│   ├── agents/
│   │   ├── bug_agent.py
│   │   ├── security_agent.py
│   │   ├── quality_agent.py
│   │   ├── test_agent.py
│   │   └── llm_utils.py         # invoke_with_rate_limit_retry()
│   ├── config/
│   │   └── settings.py          # Pydantic Settings, singleton `settings`
│   ├── models/
│   │   ├── review_job.py        # ReviewJob ORM model
│   │   ├── review_findings.py   # ReviewFinding ORM model
│   │   └── review_report.py     # ReviewReport ORM model
│   ├── schemas/
│   │   ├── findings.py          # Finding Pydantic model
│   │   └── review_job.py        # All request/response Pydantic models
│   ├── services/
│   │   ├── review.py            # ReviewService (orchestrator)
│   │   ├── analyzer.py          # StaticAnalyzer (Ruff + Bandit)
│   │   ├── verifier.py          # FindingVerifier
│   │   ├── deduplicator.py      # FindingDeduplicator
│   │   ├── report.py            # build_review_report()
│   │   ├── tools.py             # LangChain @tool functions
│   │   ├── tool_executor.py     # execute_agent() bounded loop
│   │   ├── repository.py        # RepositoryService (git)
│   │   └── llm_factory.py       # create_chat_model() → ChatOllama
│   ├── static/
│   │   └── app.js               # Frontend polling + rendering logic
│   ├── templates/
│   │   └── index.html           # Single-page form UI
│   └── database.py              # Engine, SessionLocal, Base
├── tests/                       # 45 tests, all passing
├── docs/
│   ├── SDD.md                   # Original design document
│   ├── spec.md                  # ← this file
│   ├── traces.md
│   └── tdd.md
├── pyproject.toml
└── .env                         # Runtime secrets / overrides
```

---

## 3. Configuration Reference

**Source:** `src/reviewer/config/settings.py` — Pydantic `BaseSettings`, reads from `.env`.

| Field | Type | Default | Env Var | Description |
|---|---|---|---|---|
| `app_name` | `str` | `"CodeOPS-AI"` | `APP_NAME` | Application display name |
| `app_version` | `str` | `"1.0.0"` | `APP_VERSION` | Application version string |
| `environment` | `str` | `"development"` | `ENVIRONMENT` | Runtime environment label |
| `debug` | `bool` | `False` | `DEBUG` | Enable debug mode |
| `database_url` | `str` | — | `DATABASE_URL` | SQLAlchemy connection string (required) |
| `ollama_base_url` | `str` | `"http://localhost:11434"` | `OLLAMA_BASE_URL` | Ollama API base URL |
| `llm_model` | `str` | `"qwen2.5:3b"` | `LLM_MODEL` | Ollama model name |

**Singleton:** `settings = Settings()` is instantiated once at module import. All services import `settings` directly.

**Example `.env`:**
```env
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/codeops
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=qwen2.5:3b
DEBUG=false
```

---

## 4. Database Schema

**Source:** `src/reviewer/database.py` (engine/session), `src/reviewer/models/`

SQLAlchemy with `Base.metadata.create_all(engine)` on startup. No Alembic migrations exist.

### 4.1 `review_jobs`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `UUID` | PK, default `uuid4` | Job identifier |
| `repository` | `String` | NOT NULL | Repository HTTPS URL |
| `commit_sha` | `String(40)` | NOT NULL | 40-char hex SHA |
| `status` | `String` | NOT NULL, default `"pending"` | `pending` \| `running` \| `completed` \| `failed` |
| `error_message` | `Text` | nullable | Populated on failure |
| `created_at` | `DateTime` | NOT NULL, default `utcnow` | Creation timestamp (UTC) |

### 4.2 `review_findings`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `UUID` | PK, default `uuid4` | Finding identifier |
| `job_id` | `UUID` | FK → `review_jobs.id`, CASCADE DELETE, NOT NULL | Parent job |
| `source` | `String` | NOT NULL | `ruff` \| `bandit` \| `ai_agent` |
| `category` | `String` | NOT NULL | `bug` \| `security` \| `quality` \| `test` |
| `rule_id` | `String` | nullable | e.g. `E501`, `B105` |
| `severity` | `String` | NOT NULL | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `confidence` | `String` | NOT NULL | `high` \| `medium` \| `low` |
| `message` | `Text` | NOT NULL | Human-readable finding description |
| `file_path` | `String` | NOT NULL | Relative path within workspace |
| `line` | `Integer` | nullable | 1-based line number |
| `column_number` | `Integer` | nullable | 1-based column number |
| `evidence` | `Text` | nullable | Source code snippet or excerpt |
| `recommendation` | `Text` | nullable | Suggested fix text |

### 4.3 `review_reports`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `UUID` | PK, default `uuid4` | Report identifier |
| `job_id` | `UUID` | FK → `review_jobs.id`, CASCADE DELETE, NOT NULL, UNIQUE | One report per job |
| `report_data` | `JSON` / `JSONB` | NOT NULL | Full `ReviewReportResponse` as JSON |
| `created_at` | `DateTime` | NOT NULL, default `utcnow` | Creation timestamp (UTC) |

---

## 5. API Reference

**Base URL:** `http://localhost:8000` (default)  
**Auth:** None — all endpoints are open.

---

### `POST /review/`

Submits a new code review job. Returns immediately; review runs asynchronously in a `BackgroundTask`.

**Request body** (`application/json`):
```json
{
  "repository": "https://github.com/owner/repo",
  "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
}
```

| Field | Type | Validation |
|---|---|---|
| `repository` | `str` | Must start with `https://github.com/` |
| `commit_sha` | `str` | Must match `^[0-9a-fA-F]{40}$` |

**Response** `202 Accepted`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "repository": "https://github.com/owner/repo",
  "commit_sha": "a1b2c3d4...",
  "status": "pending",
  "error_message": null,
  "created_at": "2026-11-02T08:00:00Z"
}
```

**Error:** `422 Unprocessable Entity` for validation failures.

> **Note:** No idempotency check. Submitting the same repo+SHA twice creates two independent jobs.

---

### `GET /review/{id}`

Returns the current status of a job.

**Path param:** `id` — UUID string.

**Response** `200 OK`:
```json
{
  "id": "550e8400-...",
  "repository": "https://github.com/owner/repo",
  "commit_sha": "a1b2c3d4...",
  "status": "completed",
  "error_message": null,
  "created_at": "2026-11-02T08:00:00Z"
}
```

**Status values:** `pending` → `running` → `completed` | `failed`

**Error:** `404 Not Found` if `id` does not exist.

---

### `GET /review/{id}/findings`

Returns the raw list of verified, deduplicated findings for a completed job.

**Response** `200 OK`:
```json
[
  {
    "id": "...",
    "job_id": "...",
    "source": "ruff",
    "category": "quality",
    "rule_id": "E501",
    "severity": "low",
    "confidence": "high",
    "message": "Line too long (92 > 88 characters)",
    "file_path": "src/main.py",
    "line": 42,
    "column_number": 89,
    "evidence": "    some_very_long_variable_name = another_very_long_value + yet_another_one",
    "recommendation": null
  }
]
```

**Error:** `404 Not Found` if job does not exist.

> **UI note:** The frontend (`app.js`) polls this endpoint only — it does **not** call `/report`.

---

### `GET /review/{id}/report`

Returns the fully structured review report for a completed job.

**Response** `200 OK` — see [Section 6.2](#62-reviewreportresponse) for full schema.

**Error:** `404 Not Found` if job does not exist or report not yet built.

---

### `GET /health/db`

Health check that verifies database connectivity.

**Response** `200 OK`:
```json
{"status": "ok"}
```

**Response** `503 Service Unavailable`:
```json
{"status": "error", "detail": "<exception message>"}
```

---

### `GET /`

Serves the single-page HTML UI (`templates/index.html`).

---

## 6. Data Schemas

### 6.1 `Finding` (internal Pydantic model)

**Source:** `src/reviewer/schemas/findings.py`

Used internally between services. Agents produce `Finding` objects; the verifier and deduplicator operate on them.

| Field | Type | Required | Constraints / Notes |
|---|---|---|---|
| `source` | `Literal["ruff","bandit","ai_agent"]` | Yes | Forced to `"ai_agent"` for all agent output |
| `category` | `Literal["bug","security","quality","test"]` | Yes | Forced per agent type |
| `rule_id` | `str \| None` | No | Static analysis rule codes (e.g. `E501`) |
| `severity` | `Literal["critical","high","medium","low","info"]` | Yes | |
| `confidence` | `Literal["high","medium","low"]` | Yes | |
| `message` | `str` | Yes | |
| `file_path` | `str` | Yes | Relative to workspace root |
| `line` | `int \| None` | No | 1-based |
| `column` | `int \| None` | No | 1-based (stored as `column_number` in DB) |
| `evidence` | `str \| None` | No | Code snippet |
| `recommendation` | `str \| None` | No | Suggested fix |

### 6.2 `ReviewReportResponse`

**Source:** `src/reviewer/schemas/review_job.py`

The full structured report served at `GET /review/{id}/report`.

```
ReviewReportResponse
├── job_id: UUID
├── overview: ReviewOverview
│   ├── repository: str
│   ├── commit_sha: str
│   ├── review_date: str           # ISO datetime string
│   ├── total_findings: int
│   └── status: str
│
├── executive_summary: ExecutiveSummary
│   ├── overall_assessment: str    # "Excellent" | "Good" | "Needs Improvement" | "Poor"
│   ├── key_findings: list[str]    # Up to 3 bullet strings
│   └── recommendation: str        # Single action sentence
│
├── findings_summary: FindingsSummary
│   ├── by_severity: SeverityBreakdown
│   │   ├── critical: int
│   │   ├── high: int
│   │   ├── medium: int
│   │   ├── low: int
│   │   └── info: int
│   └── by_category: CategoryBreakdown
│       ├── bug: int
│       ├── security: int
│       ├── quality: int
│       └── test: int
│
├── detailed_findings: list[DetailedFinding]
│   └── DetailedFinding
│       ├── id: str
│       ├── title: str             # Derived: rule_id + first sentence of message
│       ├── source: str
│       ├── category: str
│       ├── severity: str
│       ├── confidence: str
│       ├── file_path: str
│       ├── line: int | None
│       ├── evidence: str | None
│       └── recommendation: str | None
│
├── recommended_actions: list[RecommendedAction]
│   └── RecommendedAction
│       ├── priority: str          # Same as finding severity
│       ├── action: str            # "Fix: " + finding message
│       ├── rationale: str         # Category description
│       └── effort: str            # Always "Medium"
│
└── analysis_limitations: AnalysisStatusAndLimitations
    ├── completion_status: str
    ├── partial_review: bool
    ├── agent_failures: int
    └── limitations: list[str]
```

---

## 7. Review Pipeline

**Source:** `src/reviewer/services/review.py`, `src/reviewer/api/api_review.py`

The pipeline is triggered by `process_review_job()` running as a FastAPI `BackgroundTask`. It uses a manually created `SessionLocal()` session (not the `get_db()` dependency).

### 7.1 Step-by-step

```
1. Set job status → "running"

2. RepositoryService.prepare_repository(repository, commit_sha)
   ├── Validate repository URL (must start with https://github.com/)
   ├── Validate job_id format (UUID regex)
   ├── Shallow clone: git clone --depth=1 <url> <workspace_dir>
   ├── git fetch --depth=1 origin <commit_sha>
   └── git checkout <commit_sha>
   Returns: Path to workspace directory

3. StaticAnalyzer.analyze(workspace)
   ├── Run: python -m ruff check --output-format json .
   │   Parse stdout JSON → list[Finding] (source="ruff", category="quality")
   ├── Run: python -m bandit -r . -f json -q
   │   Parse stdout JSON → list[Finding] (source="bandit", category="security")
   └── Return combined list[Finding]

4. _analyze_with_agents(workspace)
   For each of [BugAgent, SecurityAgent, QualityAgent, TestAgent]:
   ├── enumerate Python files in workspace (up to MAX_FILES=3)
   ├── agent.analyze(workspace, file_list) → list[Finding]
   └── accumulate results
   Returns: combined list[Finding] from all agents

5. Merge: candidate_findings = static_findings + agent_findings

6. FindingVerifier.verify(candidate_findings)
   For each finding:
   ├── file must exist in workspace
   ├── path must not escape workspace (no ".." traversal)
   ├── line (if set) must be within file line count
   └── evidence (if set) must appear as substring within ±5-line window around `line`
   Rejected findings are logged (logger.warning) and dropped.
   Returns: list[Finding] (verified only)

7. FindingDeduplicator.deduplicate(verified_findings)
   ├── Cluster by (file_path, line, category)
   ├── Within each cluster, merge findings that share:
   │   └── same rule_id  OR  normalized message similarity
   ├── Promote highest severity and confidence within cluster
   └── Preserve all unique findings
   Returns: list[Finding]

8. Persist findings
   For each deduplicated finding:
   └── INSERT into review_findings

9. build_review_report(job, findings) → ReviewReportResponse
   └── Template-based assembly (no LLM call) — see Section 10

10. Persist report
    └── INSERT into review_reports (report_data = JSON blob)

11. Set job status → "completed"
    On any exception: set status → "failed", populate error_message
```

### 7.2 Constants

| Constant | Value | Location | Effect |
|---|---|---|---|
| `MAX_FILES` | `3` | `services/review.py` | Max Python files passed to each agent |
| `MAX_FILE_SIZE` | `10_000` | `services/review.py` | Max bytes per file read by agents |
| `MAX_ROUNDS` | `5` | `services/tool_executor.py` | Max tool-calling iterations per agent |
| `MAX_TOOL_FINDINGS` | `20` | `services/tools.py` | Max findings returned per tool call |

### 7.3 Dead Code

`_attach_agent_recommendations()` is defined in `ReviewService` but is **never called**. It was intended to back-fill recommendations from agent output onto static findings but is currently unreachable.

---

## 8. Agent Contracts

**Sources:** `src/reviewer/agents/`, `src/reviewer/services/tool_executor.py`, `src/reviewer/services/llm_factory.py`

### 8.1 LLM

- **Provider:** Ollama (local)
- **Model:** `qwen2.5:3b` (configurable via `LLM_MODEL`)
- **Temperature:** `0` (deterministic)
- **Framework:** LangChain `ChatOllama`
- **Retry:** `invoke_with_rate_limit_retry()` retries on `requests.exceptions.ConnectionError` and `requests.exceptions.Timeout`

### 8.2 Tool-Calling Loop (`execute_agent`)

**Source:** `src/reviewer/services/tool_executor.py`

```
Input: bound_model (LLM with tools), messages (list[BaseMessage])
Output: AIMessage (final LLM response with no tool_calls)

Loop (max MAX_ROUNDS=5 iterations):
  1. Invoke LLM with current messages
  2. Append AIMessage to messages
  3. If response has tool_calls:
     a. For each tool_call:
        - Execute tool function
        - Truncate output to safe size (_limit_tool_result)
        - Append ToolMessage to messages
     b. Continue loop
  4. If response has no tool_calls → return AIMessage
  5. If MAX_ROUNDS exceeded → return last AIMessage
```

### 8.3 Agent Pattern

All four agents follow this identical structure:

```python
def analyze(workspace: Path, files: list[str]) -> list[Finding]:
    llm = create_chat_model()                   # ChatOllama(qwen2.5:3b, temp=0)
    tools = [tool_a, tool_b]                    # per-agent tool set
    bound_model = llm.bind_tools(tools)
    messages = [
        SystemMessage(content="<role-specific system prompt>"),
        HumanMessage(content=f"Analyze these files: {files}")
    ]
    response = execute_agent(bound_model, messages, tools)
    
    # Parse JSON fence from response.content
    raw_json = strip_json_fence(response.content)
    raw_list = json.loads(raw_json)
    
    findings = []
    for item in raw_list:
        f = Finding.model_validate(item)
        # Force source and category fields
        f = f.model_copy(update={
            "source": "ai_agent",
            "category": "<agent-category>",
            "file_path": normalize(f.file_path)
        })
        findings.append(f)
    
    return findings
```

### 8.4 Per-Agent Tool Sets

| Agent | File | Tools Available | Output `category` |
|---|---|---|---|
| `BugAgent` | `agents/bug_agent.py` | `run_ruff`, `inspect_source` | `"bug"` |
| `SecurityAgent` | `agents/security_agent.py` | `run_bandit`, `inspect_source` | `"security"` |
| `QualityAgent` | `agents/quality_agent.py` | `run_ruff`, `inspect_source` | `"quality"` |
| `TestAgent` | `agents/test_agent.py` | `inspect_source`, `existing_test_inspection` | `"test"` |

### 8.5 Tool Definitions

**Source:** `src/reviewer/services/tools.py`

All tools enforce active-workspace access via `_resolve_workspace()`, which reads the current workspace from a `ContextVar`.

| Tool | Input | Output | Notes |
|---|---|---|---|
| `run_ruff(file_path)` | Relative file path | JSON string of findings list | Capped at `MAX_TOOL_FINDINGS=20` |
| `run_bandit(file_path)` | Relative file path | JSON string of findings list | Capped at `MAX_TOOL_FINDINGS=20` |
| `inspect_source(file_path)` | Relative file path | File contents as string | Enforces `MAX_FILE_SIZE` |
| `existing_test_inspection(file_path)` | Relative file path | File contents as string | Same as `inspect_source` but semantically for test files |

---

## 9. Static Analysis

**Source:** `src/reviewer/services/analyzer.py`

`StaticAnalyzer.analyze(workspace: Path) → list[Finding]`

### 9.1 Ruff

```bash
python -m ruff check --output-format json .
```

- Executed in `workspace` directory via `subprocess.run`.
- Stdout parsed as JSON array.
- Each result mapped to `Finding`:
  - `source="ruff"`, `category="quality"`
  - `rule_id` from `code` field
  - `severity` derived from rule code prefix (heuristic)
  - `confidence="high"` (deterministic tool)
  - `file_path` validated against workspace root (path traversal guard)

### 9.2 Bandit

```bash
python -m bandit -r . -f json -q
```

- Executed in `workspace` directory via `subprocess.run`.
- Stdout parsed as JSON (`results` key).
- Each result mapped to `Finding`:
  - `source="bandit"`, `category="security"`
  - `rule_id` from `test_id` field (e.g. `B105`)
  - `severity` from `issue_severity` field (lowercased)
  - `confidence` from `issue_confidence` field (lowercased)
  - `evidence` from `code` snippet field

---

## 10. Report Builder

**Source:** `src/reviewer/services/report.py`

`build_review_report(job: ReviewJob, findings: list[Finding]) → ReviewReportResponse`

**Important:** This is a purely template-based function. **No LLM is called.** All text is generated deterministically from finding metadata.

| Section | Logic |
|---|---|
| **Overview** | Counts total findings, uses `job.repository`, `job.commit_sha`, `datetime.utcnow()` |
| **Executive Summary** | `overall_assessment` derived from severity counts (thresholds); `key_findings` — up to 3 human-readable strings about worst findings; `recommendation` — canned sentence |
| **Findings Summary** | Counts by severity (5 levels) and category (4 types) |
| **Detailed Findings** | One `DetailedFinding` per finding; `title` = `_format_finding_title()` which splits message on first `.` |
| **Recommended Actions** | One `RecommendedAction` per finding — mechanical copy: `priority=severity`, `action="Fix: "+message`, `effort="Medium"` always |
| **Analysis Status** | Lists tools used (derived from finding sources), file count, canned limitations |

**Known quality issue:** Recommended actions are 1:1 copies of findings, not aggregated or prioritised. This is a known gap vs. the SDD.

---

## 11. Known Limitations

| Limitation | Detail |
|---|---|
| **File cap: 3 files per agent** | Agents only see up to `MAX_FILES=3` Python files, regardless of repository size. Large repos are severely under-analyzed. |
| **File size cap: 10 KB** | Files larger than 10,000 bytes are not read by agents. |
| **Tool call cap: 5 rounds** | Each agent stops after 5 tool-calling rounds regardless of how many issues remain. |
| **No authentication** | All API endpoints are open to any caller. |
| **No idempotency** | Submitting the same repo+SHA twice creates two independent, duplicate jobs. |
| **In-process queue** | `BackgroundTasks` runs in the FastAPI process. Pending/running jobs are lost on server restart. |
| **No SHA validation in RepositoryService** | SHA format is validated by Pydantic schema but `RepositoryService` does not re-validate — untrusted input could be passed if schema is bypassed. |
| **Sequential agents** | The four agents run one after another, not in parallel. |
| **Deterministic-only verification** | The verifier checks evidence substring presence but does not use LLM reasoning to assess finding validity. |
| **No Alembic migrations** | Schema is created via `create_all()` with no migration history. Schema changes require manual intervention. |
| **Dead code: `_attach_agent_recommendations()`** | This method is never called. |
| **UI uses only /findings** | The frontend never calls `GET /review/{id}/report`. The structured report is only accessible via direct API call. |
| **Static analysis runs twice for agents** | Ruff and Bandit are run once by `StaticAnalyzer` and can be run again by `BugAgent`/`SecurityAgent`/`QualityAgent` via their tools. |

---

## 12. Out of Scope

The following are explicitly **not implemented** and not planned:

- GitHub webhooks or CI/CD integration
- Support for non-GitHub hosts (GitLab, Bitbucket, self-hosted git)
- Support for non-Python repositories
- Sandboxed code execution (agents run against cloned source only)
- User accounts, authentication, or authorization
- LLM-based report narrative generation
- Persistent job queue (Redis, Celery, etc.)
- Evaluation framework or LLM output scoring
- Rate limiting on API endpoints
- Multi-tenancy or workspace isolation per user

