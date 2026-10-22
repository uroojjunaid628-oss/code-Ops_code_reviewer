# CodeOps-AI

> **Agentic AI Code Review and Verification System**

CodeOps-AI is an automated code review service that combines deterministic static analysis with specialized Large Language Model (LLM) agents to deliver actionable, evidence-grounded feedback on software repositories.

---

## Architecture Overview

CodeOps-AI does not rely on a simple single-prompt LLM wrapper. It employs a **hybrid architecture** combining deterministic tools and specialized LLM agents:

1. **Repository Preparation**: Clones and checks out the specific commit SHA in an isolated workspace.
2. **Deterministic Static Analysis**:
   - **Ruff**: Identifies syntax issues, code quality flaws, and standard Python anti-patterns.
   - **Bandit**: Scans for common security issues, unsafe functions, and vulnerability patterns.
3. **Multi-Agent LLM Analysis (via Groq)**:
   - **Bug Agent**: Detects logic bugs, unhandled edge cases, and runtime failure risks.
   - **Security Agent**: Identifies application security vulnerabilities (injection, insecure handling).
   - **Quality Agent**: Highlights maintainability, architectural design, and complexity concerns.
   - **Test Agent**: Detects missing test coverage and edge cases.
4. **Resilient Persistence**: Preserves findings from successful tools even if an individual AI agent encounters rate limits or errors.

---

## Project Structure

```text
CodeOPS-AI/
├── alembic/                # Database migrations
├── docs/                   # Software Design Document (SDD.md)
├── src/
│   └── reviewer/
│       ├── agents/         # LLM agents (bug, security, quality, test) & utils
│       ├── api/            # FastAPI routes, dependencies, and main entry
│       ├── config/         # Pydantic Settings and environment configs
│       ├── models/         # SQLAlchemy database models
│       ├── schemas/        # Pydantic validation schemas
│       ├── services/       # Repository cloning, static analyzer, review orchestrator
│       └── database.py     # Database engine and session setup
├── tests/                  # Pytest test suite
├── pyproject.toml          # Build configuration and dependencies
└── .env.example            # Environment variables template
```

---

## Getting Started

### Prerequisites

- **Python 3.12+**
- **Git** (installed and available in `PATH`)
- **PostgreSQL** database (or SQLite for local testing)
- **Groq API Key** (for agentic LLM analysis)

### 1. Installation

Clone this repository and create a virtual environment:

```bash
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Environment Configuration

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your database URL and Groq API key:

```env
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=postgresql+psycopg://postgres:your_password@localhost:5432/codeops_ai
GROQ_API_KEY=your_groq_api_key_here
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
```

### 3. Database Migrations

Apply the database migrations using Alembic:

```bash
alembic upgrade head
```

### 4. Running the API Server

Start the FastAPI application with Uvicorn:

```bash
uvicorn reviewer.api.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`. You can explore the interactive OpenAPI documentation at `http://127.0.0.1:8000/docs`.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Service health and version status |
| `GET` | `/health/db` | Database connectivity verification |
| `POST` | `/review/` | Trigger asynchronous review (`202 Accepted`) |
| `GET` | `/review/{job_id}` | Retrieve review job status and metadata |
| `GET` | `/review/{job_id}/findings` | Retrieve all normalized findings sorted by severity |

### Example Review Request

```bash
curl -X POST "http://127.0.0.1:8000/review/" \
  -H "Content-Type: application/json" \
  -d '{
    "repository": "https://github.com/example/sample-repo.git",
    "commit_sha": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
  }'
```

---

## Testing & Code Quality

Run tests using Pytest:

```bash
pytest
```

Run linter checks using Ruff:

```bash
ruff check src tests
```

Run security audits using Bandit:

```bash
bandit -r src
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
