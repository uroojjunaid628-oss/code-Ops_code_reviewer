# CodeOPS-AI — System Specification

**Document type:** Implementation-aligned system specification  
**Project:** CodeOPS-AI — AI-Powered Python Code Reviewer  
**Status:** Current implementation snapshot  
**Last updated:** November 2026

---

# Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [Architecture Overview](#2-architecture-overview)
3. [Configuration Reference](#3-configuration-reference)
4. [Database Schema](#4-database-schema)
5. [API Reference](#5-api-reference)
6. [Data Schemas](#6-data-schemas)
7. [Review Pipeline](#7-review-pipeline)
8. [Agent Contracts](#8-agent-contracts)
9. [Tool System](#9-tool-system)
10. [Finding Verification and Deduplication](#10-finding-verification-and-deduplication)
11. [Report Builder](#11-report-builder)
12. [Testing and Verification](#12-testing-and-verification)
13. [Known Limitations](#13-known-limitations)
14. [Out of Scope](#14-out-of-scope)
15. [Implementation Notes and Maintenance](#15-implementation-notes-and-maintenance)

---

# 1. Purpose and Scope

## 1.1 Purpose

CodeOPS-AI is a self-hosted, automated Python code-review system that combines deterministic static-analysis tools with specialized Large Language Model (LLM) agents.

The system accepts a GitHub repository URL and a target commit SHA, retrieves the specified repository revision, analyzes selected Python files, verifies the resulting findings, removes duplicate findings, and generates a structured review report.

The objective is to identify potential:

- Software bugs and logical errors.
- Security vulnerabilities.
- Code-quality and maintainability problems.
- Missing tests and potential testing gaps.

CodeOPS-AI uses specialized agents rather than relying on one general-purpose LLM to perform every review task.

## 1.2 Core Capabilities

The implemented system provides the following capabilities:

1. Accept a repository URL and commit SHA through a REST API.
2. Create a review job and process it asynchronously.
3. Clone the requested GitHub repository revision.
4. Select a bounded number of Python files for agent analysis.
5. Provide agents with access to relevant analysis tools.
6. Execute Ruff and Bandit through LangChain tools.
7. Run four specialized agents:
   - Bug Agent
   - Security Agent
   - Quality Agent
   - Test Agent
8. Collect findings from the agents.
9. Verify finding paths, line numbers, and evidence.
10. Deduplicate overlapping findings.
11. Persist review findings in the database.
12. Generate and persist a structured review report.
13. Expose review status, findings, and reports through REST endpoints.

**Architecture decision:** Ruff and Bandit are implemented as agent-callable tools in `services/tools.py`. There is no separate `StaticAnalyzer` service or independent static-analysis stage in the current review pipeline.

## 1.3 Supported Inputs

| Input | Description |
|---|---|
| Repository URL | GitHub repository URL using HTTPS |
| Commit SHA | Full 40-character hexadecimal commit identifier |
| Source files | Python files selected from the cloned repository |
| Source file size | Files are subject to the configured 10,000-byte limit |
| Number of files | Maximum of three selected Python files |

The repository service is designed around GitHub HTTPS repositories. Support for private repositories depends on the configured Git authentication mechanism.

## 1.4 Runtime Technologies

The project uses the following technologies:

| Component | Technology |
|---|---|
| Programming language | Python |
| API framework | FastAPI |
| ORM | SQLAlchemy |
| Database | PostgreSQL-compatible SQLAlchemy database; SQLite may be used for tests |
| LLM integration | LangChain |
| LLM provider | Groq |
| LLM model | `openai/gpt-oss-120b` |
| Static analysis | Ruff and Bandit |
| Repository operations | GitPython / Git |
| Data validation | Pydantic |
| Testing | Pytest |
| Code-quality checks | Ruff |

The actual model is determined by the project configuration. Ollama and `qwen2.5:3b` are not the current documented runtime configuration.

---

# 2. Architecture Overview

## 2.1 Architectural Style

CodeOPS-AI follows a modular monolithic architecture.

The application is organized into separate modules responsible for API handling, repository management, agent execution, tool execution, review orchestration, data persistence, finding verification, deduplication, and report generation.

The application does not use independently deployed microservices.

Background processing is performed through FastAPI background tasks.

## 2.2 High-Level Architecture

```text
                       Client / Browser
                              |
                              |
                       FastAPI Application
                              |
                    POST /review/
                              |
                       Create Review Job
                              |
                       Background Task
                              |
                       Review Processing
                              |
                    RepositoryService
                              |
                    Clone GitHub Repository
                              |
                     Checkout Commit SHA
                              |
                         Workspace
                              |
                         ReviewService
                              |
                     Select Python Files
                              |
                    Specialized Agents
                              |
           +------------------+------------------+
           |                  |                  |
        Bug Agent        Security Agent      Quality Agent
           |                  |                  |
        Ruff Tool          Bandit Tool          Ruff Tool
           |                  |                  |
           +------------------+------------------+
                              |
                          Test Agent
                              |
                 Source Inspection / Test
                       Inspection Tools
                              |
                       Agent Findings
                              |
                     FindingVerifier
                              |
                   FindingDeduplicator
                              |
                     Verified Findings
                              |
                     Database Storage
                              |
                    Report Builder
                              |
                     Report Storage
                              |
                    REST API Responses
```

## 2.3 Main Architectural Components

| Component | Responsibility |
|---|---|
| FastAPI application | Initializes the application and exposes API routes |
| Review API | Accepts requests and manages review jobs |
| RepositoryService | Clones repositories and checks out requested commits |
| ReviewService | Coordinates the review workflow |
| Specialized agents | Analyze source files according to their assigned responsibilities |
| Tools | Provide source inspection, Ruff, Bandit, and test-file inspection |
| Tool executor | Manages bounded LLM tool-calling interactions |
| FindingVerifier | Checks finding validity against repository files |
| FindingDeduplicator | Removes duplicate findings |
| Report builder | Generates the structured review report |
| Database | Persists review jobs, findings, and reports |

## 2.4 Project Structure

The following represents the current documented architecture. Exact filenames and auxiliary modules should remain synchronized with the repository.

```text
CodeOPS-AI/
│
├── src/
│   └── reviewer/
│       │
│       ├── api/
│       │   ├── main.py
│       │   ├── api_review.py
│       │   └── dependencies.py
│       │
│       ├── agents/
│       │   ├── bug_agent.py
│       │   ├── security_agent.py
│       │   ├── quality_agent.py
│       │   ├── test_agent.py
│       │   └── llm_utils.py
│       │
│       ├── config/
│       │   └── settings.py
│       │
│       ├── models/
│       │   ├── review_job.py
│       │   ├── review_findings.py
│       │   └── review_report.py
│       │
│       ├── schemas/
│       │   ├── findings.py
│       │   └── review_job.py
│       │
│       ├── services/
│       │   ├── review.py
│       │   ├── repository.py
│       │   ├── tools.py
│       │   ├── tool_executor.py
│       │   ├── verifier.py
│       │   ├── deduplicator.py
│       │   ├── report.py
│       │   └── llm_factory.py
│       │
│       ├── static/
│       │   └── app.js
│       │
│       ├── templates/
│       │   └── index.html
│       │
│       └── database.py
│
├── tests/
│
├── docs/
│   ├── SDD.md
│   ├── spec.md
│   ├── traces.md
│   └── tdd.md
│
├── pyproject.toml
└── .env
```

**Important:** `services/analyzer.py` is no longer part of the current architecture. Its Ruff and Bandit execution responsibilities have been moved into `services/tools.py`.

---

# 3. Configuration Reference

## 3.1 Configuration Management

Configuration is managed through the project's settings module:

```text
src/reviewer/config/settings.py
```

The application uses Pydantic Settings to load runtime configuration, including environment variables and values supplied through `.env`.

The settings object is shared by application modules.

## 3.2 Configuration Values

The following are the configuration values established in the project context. Exact defaults and environment-variable names should be checked against the current settings implementation before being treated as immutable.

| Setting | Purpose |
|---|---|
| `database_url` | SQLAlchemy database connection |
| `llm_model` | Groq model identifier |
| Groq API key | Authentication for Groq API requests |
| Environment settings | Application environment and runtime behavior |

The current model configuration uses:

```text
openai/gpt-oss-120b
```

The LLM integration is implemented through the project's LLM factory and agent modules.

## 3.3 Secrets

API credentials and database connection details must be supplied through environment configuration.

The `.env` file must not be committed to the public repository.

Example configuration structure:

```env
DATABASE_URL=your_database_connection_string
GROQ_API_KEY=your_groq_api_key
LLM_MODEL=openai/gpt-oss-120b
```

This is an illustrative configuration structure, not a guarantee that every variable name matches the current settings class. The settings implementation is the authoritative source.

---

# 4. Database Schema

## 4.1 Database Layer

Database initialization and session management are handled by:

```text
src/reviewer/database.py
```

SQLAlchemy is used for database connectivity, ORM models, and session management.

The application uses a session factory named `SessionLocal`.

The database models are organized under:

```text
src/reviewer/models/
```

The principal persisted entities are:

1. Review jobs.
2. Review findings.
3. Review reports.

## 4.2 Review Jobs

The review job represents one requested repository review.

It stores information about the repository, target commit, execution status, and job errors.

| Field | Description |
|---|---|
| `id` | Unique job identifier |
| `repository` | GitHub repository URL |
| `commit_sha` | Target commit SHA |
| `status` | Current review execution status |
| `error_message` | Error information when applicable |
| `created_at` | Job creation timestamp |

The exact SQLAlchemy column types, nullability, defaults, and foreign-key constraints are defined by `models/review_job.py`.

## 4.3 Review Findings

Each verified, deduplicated finding is persisted as an individual database record.

| Field | Description |
|---|---|
| `id` | Finding identifier |
| `job_id` | Associated review job |
| `source` | Origin of the finding |
| `category` | Finding classification |
| `rule_id` | Static-analysis rule identifier or agent rule identifier |
| `severity` | Finding severity |
| `confidence` | Finding confidence |
| `message` | Finding description |
| `file_path` | Repository-relative file path |
| `line` | Source line number |
| `column_number` | Source column number, where stored |
| `evidence` | Supporting source evidence |
| `recommendation` | Recommendation, when supplied |

The `Finding` Pydantic schema is the internal data contract. ORM column definitions remain authoritative for database storage details.

## 4.4 Review Reports

A review report represents the structured output of one completed review.

The report model stores the report associated with a review job.

The report builder produces a `ReviewReportResponse`, which is serialized for persistence.

The exact database JSON column type and relationship constraints are defined in `models/review_report.py`.

## 4.5 Database Sessions

The project uses SQLAlchemy sessions for database operations.

The API uses the database dependency where appropriate.

Background review processing creates its own database session through `SessionLocal`, rather than reusing the request-scoped session.

---

# 5. API Reference

## 5.1 API Overview

The API is implemented using FastAPI.

The main application is initialized in:

```text
src/reviewer/api/main.py
```

Review endpoints are organized in:

```text
src/reviewer/api/api_review.py
```

The API provides job submission, job status retrieval, finding retrieval, and report retrieval.

## 5.2 Submit a Review

**Endpoint:**

```http
POST /review/
```

**Purpose:**

Creates a review job for a GitHub repository and schedules its processing through a background task.

**Input:**

A repository URL and target commit SHA are supplied in the request body.

The exact Pydantic validation rules are defined in the review-job request schema.

**Behavior:**

1. Validate the request.
2. Create a review job record.
3. Schedule background processing.
4. Return the created job information.

The endpoint does not wait for the entire code review to finish.

## 5.3 Retrieve Job Status

**Endpoint:**

```http
GET /review/{job_id}
```

**Purpose:**

Retrieves the current state of a review job.

The response includes job information and its execution status.

The exact response model is defined by the API schema.

## 5.4 Retrieve Findings

**Endpoint:**

```http
GET /review/{job_id}/findings
```

**Purpose:**

Retrieves the findings associated with a review job.

Findings are persisted after verification and deduplication.

## 5.5 Retrieve Report

**Endpoint:**

```http
GET /review/{job_id}/report
```

**Purpose:**

Retrieves the structured report associated with a review job.

The report is generated by the report builder and stored in the database.

## 5.6 Database Health Check

If enabled in the current API implementation:

```http
GET /health/db
```

This endpoint checks database connectivity.

Its exact response and availability should be confirmed against the current route implementation.

## 5.7 Web Interface

The project includes a basic web interface implemented using:

```text
src/reviewer/templates/index.html
src/reviewer/static/app.js
```

The interface provides a browser-based way to submit and monitor code reviews.

The frontend and REST API are separate presentation and application layers.

---

# 6. Data Schemas

## 6.1 Finding

**Source:**

```text
src/reviewer/schemas/findings.py
```

The `Finding` model is the common internal representation used by the analysis tools, agents, verifier, and deduplicator.

Current schema:

```python
from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    source: Literal["ruff", "bandit", "ai_agent"]
    category: Literal["bug", "security", "quality", "test"]
    rule_id: str
    severity: Literal["critical", "high", "medium", "low", "unknown"]
    confidence: Literal["high", "medium", "low", "unknown"]
    message: str
    file_path: str
    line: int | None = None
    column: int | None = None
    evidence: str | None = None
    recommendation: str | None = None
```

### Field Reference

| Field | Type | Description |
|---|---|---|
| `source` | Literal | Finding origin: Ruff, Bandit, or AI agent |
| `category` | Literal | Bug, security, quality, or test |
| `rule_id` | `str` | Rule identifier |
| `severity` | Literal | Critical, high, medium, low, or unknown |
| `confidence` | Literal | High, medium, low, or unknown |
| `message` | `str` | Description of the finding |
| `file_path` | `str` | Repository-relative file path |
| `line` | `int \| None` | Source line number |
| `column` | `int \| None` | Source column number |
| `evidence` | `str \| None` | Supporting source code evidence |
| `recommendation` | `str \| None` | Suggested remediation, when available |

### Finding Sources

| Source | Meaning |
|---|---|
| `ruff` | Deterministic code-quality finding |
| `bandit` | Deterministic security finding |
| `ai_agent` | Finding produced by an LLM agent |

### Category Assignment

| Agent | Category |
|---|---|
| Bug Agent | `bug` |
| Security Agent | `security` |
| Quality Agent | `quality` |
| Test Agent | `test` |

The agents normalize their returned findings to the appropriate source and category.

## 6.2 Agent Output

Agents return structured findings that are converted into `Finding` objects.

The agents are responsible for producing valid structured output.

Invalid or malformed agent responses may be handled as agent failures rather than accepted as valid findings.

## 6.3 Review Report Schema

**Source:**

```text
src/reviewer/schemas/review_job.py
```

The report builder returns the project's `ReviewReportResponse` model.

The report contains the following conceptual sections:

| Section | Purpose |
|---|---|
| Overview | Repository, commit, review date, finding count, and status |
| Executive summary | Overall assessment and key findings |
| Findings summary | Counts grouped by severity and category |
| Detailed findings | Individual finding information |
| Recommended actions | Actions derived from findings |
| Analysis limitations | Review completion and limitations information |

The actual field names, nested Pydantic models, defaults, and validation rules in `review_job.py` are authoritative.

---

# 7. Review Pipeline

## 7.1 Overview

The review pipeline is coordinated by:

```text
src/reviewer/services/review.py
```

The review is initiated by the API background-processing function.

The current implementation uses agent-based analysis with agent-callable tools.

There is no independent `StaticAnalyzer.analyze()` stage.

## 7.2 Step-by-Step Workflow

```text
1. Review Job Creation
   |
   |-- Receive repository URL and commit SHA
   |-- Validate request data
   |-- Create ReviewJob record
   |-- Schedule background processing
   |
   v

2. Background Processing
   |
   |-- Create database session
   |-- Set job status to RUNNING
   |
   v

3. Repository Preparation
   |
   |-- RepositoryService prepares repository
   |-- Clone repository into job workspace
   |-- Fetch requested commit if necessary
   |-- Checkout target commit
   |
   v

4. Workspace Preparation
   |
   |-- Set active workspace context
   |-- Enumerate Python source files
   |-- Apply file-count and file-size limits
   |
   v

5. Agent Analysis
   |
   |-- Bug Agent
   |     |-- inspect_source
   |     |-- run_ruff
   |
   |-- Security Agent
   |     |-- inspect_source
   |     |-- run_bandit
   |
   |-- Quality Agent
   |     |-- inspect_source
   |     |-- run_ruff
   |
   |-- Test Agent
         |-- inspect_source
         |-- existing_test_inspection
   |
   v

6. Finding Collection
   |
   |-- Collect agent findings
   |-- Normalize findings
   |
   v

7. Finding Verification
   |
   |-- Validate repository-relative paths
   |-- Check file existence
   |-- Check line numbers
   |-- Validate evidence
   |
   v

8. Finding Deduplication
   |
   |-- Group related findings
   |-- Identify duplicates
   |-- Retain the appropriate finding
   |
   v

9. Database Persistence
   |
   |-- Persist verified findings
   |
   v

10. Report Generation
    |
    |-- build_review_report()
    |-- Create ReviewReportResponse
    |-- Persist report
    |
    v

11. Job Completion
    |
    |-- Update job status
    |-- Commit database changes
    |-- Clean up repository workspace
    |
    v

12. API Retrieval
    |
    |-- Job status
    |-- Findings
    |-- Structured report
```

## 7.3 Agent Execution

The four agents are coordinated by `ReviewService`.

The current implementation invokes the agents sequentially rather than using parallel agent execution.

Each agent receives the relevant repository context and selected source files.

The agents can invoke only the tools assigned to them.

The agent results are collected and passed to the finding-verification stage.

## 7.4 Important Constants

| Constant | Value | Module | Purpose |
|---|---:|---|---|
| `MAX_FILES` | 3 | `services/review.py` | Maximum number of Python files selected |
| `MAX_FILE_SIZE` | 10,000 bytes | `services/review.py` | Maximum source-file size |
| `MAX_ROUNDS` | 5 | `services/tool_executor.py` | Maximum tool-calling rounds |
| `MAX_TOOL_ITEMS` | 15 | `services/tool_executor.py` | Maximum tool-result collection items |
| `MAX_STRING_LENGTH` | 1,200 | `services/tool_executor.py` | Tool-result string limit |
| `MAX_DICT_KEYS` | 30 | `services/tool_executor.py` | Maximum dictionary keys in bounded results |
| `MAX_TOOL_FINDINGS` | 20 | `services/tools.py` | Maximum findings returned by an analysis tool |
| `MAX_TEST_FILES` | 50 | `services/tools.py` | Maximum existing test files returned |
| `MAX_SOURCE_CHARS` | 8,000 | `services/tools.py` | Source inspection character limit |
| `TOOL_TIMEOUT` | 120 seconds | `services/tools.py` | Subprocess timeout for Ruff and Bandit |

## 7.5 Error Handling

The review workflow handles failures at different levels.

Examples include:

- Repository cloning or checkout failure.
- Missing or invalid repository workspace.
- Ruff or Bandit execution failure.
- LLM API errors.
- Invalid agent responses.
- Finding verification failures.
- Database persistence errors.
- Report generation failures.

Agent failures are isolated where supported by the review orchestration logic.

A review may be completed partially when some agents fail but the remaining workflow can continue.

The exact job status and error-handling branches are determined by the current `ReviewService` and API implementation.

## 7.6 Workspace Cleanup

Repository workspaces are temporary review resources.

The review workflow performs workspace cleanup after processing according to its cleanup logic.

The workspace context is reset after use so that subsequent operations do not accidentally reuse the previous repository context.

---

# 8. Agent Contracts

## 8.1 LLM Integration

The LLM integration is implemented through:

```text
src/reviewer/services/llm_factory.py
```

The current project uses LangChain with Groq.

| Property | Current implementation |
|---|---|
| Provider | Groq |
| Model | `openai/gpt-oss-120b` |
| Framework | LangChain |
| Model integration | ChatGroq |
| Temperature | 0 |
| Output | Structured agent findings |
| Tool calling | LangChain tool binding |

The exact factory configuration is authoritative if the model or provider changes.

## 8.2 Rate-Limit Retry

The agent utility module contains rate-limit retry behavior.

**Source:**

```text
src/reviewer/agents/llm_utils.py
```

The current implementation handles Groq rate-limit errors through a retry helper.

The established retry configuration is:

| Setting | Value |
|---|---:|
| Maximum attempts | 3 |
| Base delay | 5 seconds |
| Maximum delay | 30 seconds |

Retry behavior is intended to handle temporary provider rate limits. It does not guarantee that an agent will succeed after the provider's usage limit is exhausted.

## 8.3 Tool-Calling Execution

**Source:**

```text
src/reviewer/services/tool_executor.py
```

The shared function:

```python
execute_agent(
    llm,
    messages,
    allowed_tools,
    max_rounds=MAX_ROUNDS,
)
```

manages bounded tool-calling interactions.

### Execution Process

1. Receive a model with bound tools.
2. Receive the current conversation messages.
3. Invoke the LLM.
4. Inspect the response for tool calls.
5. Validate requested tool names against the allowed tool set.
6. Execute permitted tools.
7. Bound and serialize tool results.
8. Append tool responses to the conversation.
9. Continue until the model returns a response without tool calls or the maximum number of rounds is reached.

The executor also handles unknown tool names and tool execution errors.

Tool outputs are bounded to reduce excessive model context consumption.

## 8.4 Agent Responsibilities

### Bug Agent

**Source:**

```text
src/reviewer/agents/bug_agent.py
```

**Responsibility:**

Analyze selected Python source files for potential logical errors and software bugs.

**Available tools:**

- `inspect_source`
- `run_ruff`

**Output category:**

```text
bug
```

### Security Agent

**Source:**

```text
src/reviewer/agents/security_agent.py
```

**Responsibility:**

Analyze selected Python source files for potential security problems.

**Available tools:**

- `inspect_source`
- `run_bandit`

**Output category:**

```text
security
```

### Quality Agent

**Source:**

```text
src/reviewer/agents/quality_agent.py
```

**Responsibility:**

Analyze code structure, maintainability, and code-quality issues.

**Available tools:**

- `inspect_source`
- `run_ruff`

**Output category:**

```text
quality
```

### Test Agent

**Source:**

```text
src/reviewer/agents/test_agent.py
```

**Responsibility:**

Inspect the repository's existing Python test files and identify potential missing test coverage or testing gaps.

**Available tools:**

- `inspect_source`
- `existing_test_inspection`

**Output category:**

```text
test
```

## 8.5 Agent Tool Assignment

| Agent | Tool | Purpose |
|---|---|---|
| Bug Agent | `inspect_source` | Inspect source metrics |
| Bug Agent | `run_ruff` | Obtain Ruff diagnostics |
| Security Agent | `inspect_source` | Inspect source metrics |
| Security Agent | `run_bandit` | Obtain Bandit security findings |
| Quality Agent | `inspect_source` | Inspect source metrics |
| Quality Agent | `run_ruff` | Obtain Ruff diagnostics |
| Test Agent | `inspect_source` | Inspect source metrics |
| Test Agent | `existing_test_inspection` | Discover existing test files |

The agent's tool assignment determines which tools it is permitted to invoke.

Ruff is shared by the Bug and Quality agents. The tools are not automatically guaranteed to execute only once across both agents.

---

# 9. Tool System

## 9.1 Overview

**Source:**

```text
src/reviewer/services/tools.py
```

The tool system provides repository-analysis capabilities to the specialized agents.

The tools are implemented using LangChain's `@tool` decorator.

Ruff and Bandit are executed directly inside their respective tool implementations.

There is no `StaticAnalyzer` dependency.

## 9.2 Active Workspace Context

The tool module maintains the active repository workspace using:

```python
_active_workspace: ContextVar[Path | None]
```

The workspace context allows tool functions to operate against the repository currently being reviewed.

The main workspace functions are:

| Function | Responsibility |
|---|---|
| `set_active_workspace()` | Set the current repository workspace |
| `reset_active_workspace()` | Restore the previous context |
| `get_active_workspace()` | Retrieve the active workspace |
| `_resolve_workspace()` | Resolve and validate a requested workspace |

When an active workspace exists, requested workspace paths are checked against it.

## 9.3 Ruff Tool

**Tool name:**

```python
run_ruff(workspace: str | None = None)
```

**Purpose:**

Run Ruff against the active repository and return normalized code-quality findings.

**Execution command:**

```bash
python -m ruff check --output-format json .
```

**Processing:**

1. Resolve the active workspace.
2. Execute Ruff using a subprocess.
3. Parse JSON output.
4. Normalize each diagnostic into a `Finding`.
5. Preserve rule ID, file path, line, and column.
6. Extract source evidence where available.
7. Apply output limits.
8. Return JSON-compatible finding dictionaries.

**Finding attributes:**

| Field | Value |
|---|---|
| `source` | `ruff` |
| `category` | `quality` |
| `severity` | `medium` |
| `confidence` | `high` |
| `rule_id` | Ruff diagnostic code |

The current implementation assigns medium severity and high confidence to Ruff findings. It does not derive severity from Ruff rule-code prefixes.

## 9.4 Bandit Tool

**Tool name:**

```python
run_bandit(workspace: str | None = None)
```

**Purpose:**

Run Bandit against the active repository and return normalized security findings.

**Execution command:**

```bash
python -m bandit -r . -f json -q
```

The implementation also supplies excluded-directory patterns.

**Processing:**

1. Resolve the active workspace.
2. Execute Bandit.
3. Parse JSON output.
4. Read the `results` collection.
5. Normalize security findings.
6. Preserve rule identifiers and source locations.
7. Extract source evidence.
8. Apply finding limits.
9. Return JSON-compatible finding dictionaries.

**Finding attributes:**

| Field | Value |
|---|---|
| `source` | `bandit` |
| `category` | `security` |
| `rule_id` | Bandit test identifier |
| `severity` | Normalized Bandit severity |
| `confidence` | Normalized Bandit confidence |

Unknown severity and confidence values are normalized to `unknown`.

The current implementation suppresses Bandit B101 findings in recognized test files and test directories.

## 9.5 Source Inspection Tool

**Tool name:**

```python
inspect_source(
    file_path: str,
    source_code: str,
)
```

**Purpose:**

Provide basic source metrics to an agent without returning the complete source code.

The tool returns:

| Field | Description |
|---|---|
| `file_path` | Repository-relative source path |
| `line_count` | Number of source lines |
| `import_count` | Number of lines beginning with `import` or `from` |
| `source_truncated` | Whether source exceeds the inspection character limit |

The source inspection limit is:

```text
MAX_SOURCE_CHARS = 8,000
```

The tool does not perform a complete semantic analysis of Python source code.

## 9.6 Existing Test Inspection Tool

**Tool name:**

```python
existing_test_inspection(
    workspace: str | None = None,
)
```

**Purpose:**

Discover existing Python test files in the active repository.

Recognized naming conventions include:

```text
test_*.py
*_test.py
```

The tool:

- Recursively searches Python files.
- Excludes configured directories.
- Returns repository-relative paths.
- Marks discovered files with `has_tests: True`.
- Stops after the configured maximum number of files.

The result limit is:

```text
MAX_TEST_FILES = 50
```

This tool discovers existing test files. It does not execute the tests or calculate actual code coverage.

## 9.7 Excluded Directories

The tool module excludes the following directories from relevant source discovery and analysis:

```python
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
}
```

## 9.8 Subprocess Execution

Ruff and Bandit are executed using Python subprocesses.

The execution helper:

- Uses the current Python interpreter.
- Executes commands without shell-based command construction.
- Uses the repository workspace as the working directory.
- Captures standard output and standard error.
- Uses a timeout of 120 seconds.
- Checks the process return code.

The implementation accepts return codes 0 and 1 as normal analysis outcomes, since these tools can return 1 when findings are detected.

Other execution failures are raised as errors.

## 9.9 Tool Output Limits

Tool output is bounded to control the amount of information returned to agents.

| Limit | Value |
|---|---:|
| Maximum findings per analysis tool | 20 |
| Maximum message length | 1,000 characters |
| Maximum evidence length | 1,000 characters |
| Maximum recommendation length | 1,000 characters |
| Maximum existing test files | 50 |
| Maximum source inspection characters | 8,000 |

When the finding limit is exceeded, the tool includes a notice that additional findings were omitted.

---

# 10. Finding Verification and Deduplication

## 10.1 Finding Verification

**Source:**

```text
src/reviewer/services/verifier.py
```

The `FindingVerifier` validates collected findings against the repository workspace.

Its purpose is to reject findings that do not have sufficient support in the source repository.

Verification includes checks for:

- Valid repository-relative file paths.
- File existence.
- Path containment within the repository workspace.
- Valid line numbers when provided.
- Evidence consistency with the relevant source lines.

Evidence is checked against the configured surrounding source-line window.

Invalid findings are rejected rather than persisted as verified results.

Verification is deterministic. It does not independently use an LLM to decide whether a finding represents a genuine software defect.

## 10.2 Finding Deduplication

**Source:**

```text
src/reviewer/services/deduplicator.py
```

The `FindingDeduplicator` reduces duplicate or overlapping findings.

The deduplication process groups findings using their source location and category.

Related findings are compared using rule identifiers and normalized message information.

Where findings are identified as duplicates, the deduplication logic retains the appropriate finding and resolves severity and confidence according to its implementation.

The objective is to prevent the same issue from appearing multiple times in the final review.

The deduplicator does not guarantee that all semantically equivalent findings will be detected.

## 10.3 Processing Order

The current processing order is:

```text
Agent Findings
      |
      v
FindingVerifier
      |
      v
Verified Findings
      |
      v
FindingDeduplicator
      |
      v
Deduplicated Findings
      |
      v
Database Persistence
```

There is no separate baseline `StaticAnalyzer` result list being merged into the agent findings.

---

# 11. Report Builder

## 11.1 Overview

**Source:**

```text
src/reviewer/services/report.py
```

The report builder converts a review job and its final findings into a structured report.

The report-generation function is:

```python
build_review_report(job, findings)
```

The report builder is template-based and deterministic.

It does not make an additional LLM request to generate the report narrative.

## 11.2 Report Sections

The structured report contains conceptual sections for:

### Overview

Contains information about the reviewed repository, target commit, review date, total findings, and review status.

### Executive Summary

Provides an overall assessment, important findings, and a general recommendation.

The summary is derived from the available finding information and the report-building logic.

### Findings Summary

Groups findings by:

- Severity.
- Category.

### Detailed Findings

Contains the individual findings and their relevant information.

Typical fields include:

- Finding identifier.
- Title.
- Source.
- Category.
- Severity.
- Confidence.
- File path.
- Line number.
- Evidence.
- Recommendation.

### Recommended Actions

Provides actions derived from findings.

The current report implementation uses deterministic report-building logic. Recommended actions should not be interpreted as independently validated LLM-generated remediation plans.

### Analysis Limitations

Provides information about review completion and analysis limitations, including partial completion and agent failures where available.

## 11.3 Report Persistence

The generated report is serialized and persisted through the report database model.

The API exposes the stored report through:

```http
GET /review/{job_id}/report
```

---

# 12. Testing and Verification

## 12.1 Test Framework

The project uses Pytest.

The test suite covers components of the application, including review orchestration, agent handling, tool behavior, finding processing, and other application functionality.

## 12.2 Current Verification Baseline

After removing the separate `StaticAnalyzer` service and moving Ruff and Bandit execution into `tools.py`, the project passed the following checks.

| Verification | Result |
|---|---|
| Ruff check on `src` and `tests` | All checks passed |
| Full Pytest suite | 45 passed |
| Application imports of `StaticAnalyzer` | None found |
| Old `analyzer.py` module | Removed |

These results represent the verification performed after the architecture change.

They do not prove that every possible repository review scenario or every LLM response is correct.

## 12.3 Verification Commands

Run the following commands from the project root.

**Ruff:**

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
```

**Pytest:**

```powershell
.\.venv\Scripts\pytest -q
```

## 12.4 Integration Testing

The project should also verify the complete workflow using a controlled test repository.

A complete integration test should verify:

1. A review job is accepted.
2. The repository is prepared successfully.
3. The correct commit is checked out.
4. The agents receive the intended files.
5. The assigned tools can be invoked.
6. Tool results are returned in the expected format.
7. Findings are verified.
8. Duplicate findings are removed.
9. Findings are persisted.
10. A report is generated and persisted.
11. The job reaches the expected final status.

LLM-dependent integration tests should account for external API availability and provider rate limits.

---

# 13. Known Limitations

The following limitations describe the current architecture and established implementation constraints.

| Limitation | Description |
|---|---|
| Three-file limit | Only a bounded number of Python files are selected for agent analysis. |
| 10 KB file limit | Larger files are not included in the normal agent source-reading workflow. |
| Five tool-calling rounds | An agent cannot continue tool calling indefinitely. |
| Twenty findings per tool | Analysis tool output is bounded. |
| LLM dependency | Agent analysis depends on external Groq API availability. |
| Provider rate limits | Requests may fail or require retry when provider limits are reached. |
| Sequential agents | Agents are executed sequentially rather than in parallel. |
| Shared Ruff tool | Bug and Quality agents both have access to Ruff; repeated execution may occur. |
| Limited test inspection | Discovering test files does not establish actual test coverage. |
| No full repository coverage | The file and size limits mean the complete repository may not be analyzed. |
| Deterministic verification | Finding verification checks source evidence but does not independently establish semantic correctness. |
| In-process background processing | Background tasks depend on the FastAPI process and are not a durable job queue. |
| No documented authentication | API authentication and authorization are not part of the established current scope. |
| No migration history established | Database migration behavior should be confirmed against the actual project configuration. |
| LLM output variability | Even with temperature zero, external model output should not be treated as guaranteed identical across all requests. |
| Report limitations | The report is generated from available findings and metadata rather than a separate comprehensive reasoning process. |

---

# 14. Out of Scope

The following capabilities are not part of the current implemented system.

They must not be presented as completed features unless they are subsequently implemented and verified.

- GitHub webhook integration.
- Automatic pull-request review.
- CI/CD pipeline integration.
- GitLab and Bitbucket repository support.
- Non-Python repository analysis.
- Full execution of untrusted repository code.
- A dedicated sandboxed execution environment.
- User accounts and role-based access control.
- Persistent distributed background job processing.
- Redis or Celery-based task queues.
- Automatic repair and modification of source files.
- Automatic creation of pull requests.
- LLM-generated report narratives.
- Guaranteed complete test coverage analysis.
- Guaranteed detection of all software bugs or vulnerabilities.
- Guaranteed detection of every duplicate finding.

These features may be considered for future development but are not current system capabilities.

---

# 15. Implementation Notes and Maintenance

## 15.1 Source of Truth

The implementation is the source of truth for current system behavior.

The following files are especially important when updating this specification:

| File | Documentation responsibility |
|---|---|
| `api/api_review.py` | API endpoints and background processing |
| `services/repository.py` | Repository cloning and checkout |
| `services/review.py` | Review orchestration and pipeline |
| `services/tools.py` | Tool interfaces and analysis behavior |
| `services/tool_executor.py` | LLM tool-calling execution |
| `agents/bug_agent.py` | Bug analysis behavior |
| `agents/security_agent.py` | Security analysis behavior |
| `agents/quality_agent.py` | Quality analysis behavior |
| `agents/test_agent.py` | Test analysis behavior |
| `services/verifier.py` | Finding verification |
| `services/deduplicator.py` | Finding deduplication |
| `services/report.py` | Report generation |
| `schemas/findings.py` | Finding data contract |
| `schemas/review_job.py` | Review request and response contracts |
| `config/settings.py` | Runtime configuration |
| `database.py` | Database initialization and session management |
| `models/` | Persisted database structures |

## 15.2 Documentation Maintenance Rules

Whenever a feature or architecture change is introduced:

1. Update the relevant source code.
2. Update or add tests.
3. Run the relevant test suite.
4. Verify the complete project where appropriate.
5. Update this specification to reflect the implemented behavior.
6. Record unimplemented or deferred requirements separately.

Do not document a planned feature as implemented.

Do not retain references to removed modules or obsolete architecture.

## 15.3 Architectural Invariants

The following architectural decisions should remain consistent unless deliberately changed:

- `ReviewService` coordinates the review workflow.
- Specialized agents own their respective analysis responsibilities.
- Agents invoke only their assigned tools.
- `tools.py` provides the agent-callable analysis tools.
- Ruff and Bandit are not run through a separate `StaticAnalyzer` pipeline.
- `Finding` is the common internal finding representation.
- Findings pass through verification and deduplication before persistence.
- The report builder produces a structured report from the final findings.
- LLM tool execution remains bounded.

## 15.4 Specification Status

This document describes the current implementation snapshot.

Any new feature, changed behavior, or architectural modification must be reflected in the specification after implementation and verification.

**End of Specification**