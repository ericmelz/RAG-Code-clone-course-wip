# RAG Code Backend

A multi-agent RAG (Retrieval-Augmented Generation) API for answering questions about indexed codebases. Built with FastAPI, LangGraph, Pinecone, and OpenAI.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Redis (for the Celery task queue)
- A [Pinecone](https://www.pinecone.io/) account and API key
- An [OpenAI](https://platform.openai.com/) API key
- A [LangSmith](https://smith.langchain.com/) account and API key (for tracing)

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment variables

Create a `.env` file in the `backend/` directory:

```env
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=pcsk_...
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=your-project-name
LANGSMITH_TRACING=true
```

> **LangSmith workspace ID**: if you need to specify a workspace, set `LANGSMITH_WORKSPACE_ID` to the UUID shown in your LangSmith URL (`smith.langchain.com/o/<uuid>/settings`), not the display name.

### 3. Run database migrations

```bash
uv run alembic upgrade head
```

This creates `sandbox.db` (SQLite) with all required tables. Always run this after pulling changes that include new migrations.

### 4. Start Redis

Redis is required for the Celery indexing task queue. With Docker:

```bash
docker run -d -p 6379:6379 redis
```

### 5. Start the Celery worker

In a separate terminal:

```bash
uv run celery -A app.core.celery_app worker --loglevel=info
```

### 6. Start the API server

```bash
uv run fastapi dev app/main.py
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## API Endpoints

### Indexing

#### `POST /indexing/index`

Enqueues a background job to index a GitHub repository into Pinecone.

```json
{
  "github_url": "https://github.com/owner/repo"
}
```

Returns a Celery task ID. Indexing runs asynchronously — monitor the Celery worker logs for progress.

#### `GET /indexing/repos`

Lists all indexed repositories.

```json
{
  "repos": [
    {
      "namespace": "owner-repo",
      "github_url": "https://github.com/owner/repo",
      "indexed_at": "2026-04-28T09:00:00Z"
    }
  ]
}
```

### Chat

#### `POST /chat/message`

Send a message and receive a RAG-generated response grounded in an indexed repository.

```json
{
  "username": "alice",
  "namespace": "owner-repo",
  "message": "How does the authentication middleware work?"
}
```

`namespace` must match the namespace of a previously indexed repository (returned by `GET /indexing/repos`).

---

## LangGraph Studio (local dev)

The agent graphs can be explored interactively via LangGraph Studio:

```bash
uv run langgraph dev
```

This starts a local LangGraph server at `http://127.0.0.1:2024` and opens Studio at `https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`.

The following graphs are registered in `langgraph.json`:

| Graph | Description |
|---|---|
| `basic_rag` | Simple retriever to generator pipeline |
| `chat_agent` | Full orchestrator with intent routing, multi-iteration retrieval, and iterative generation |

---

## Database Migrations (Alembic)

This project uses [Alembic](https://alembic.sqlalchemy.org/) to manage SQLite schema migrations.

### Apply all pending migrations

```bash
uv run alembic upgrade head
```

### Roll back the last migration

```bash
uv run alembic downgrade -1
```

### Check current migration state

```bash
uv run alembic current
```

### View migration history

```bash
uv run alembic history
```

### Create a new migration after changing a model

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

Alembic compares the SQLAlchemy models to the live database schema and generates a migration file in `alembic/versions/`. Review the generated file before running it — autogenerate is accurate for most changes but may miss some (e.g. check constraints, certain index changes).

The migration is applied at application startup automatically via `run_migrations_async()` in the FastAPI lifespan.

---

## Admin UI

A SQL admin interface is available at `http://localhost:8000/admin` when the API server is running. It provides read/write access to the `indexed_repos`, `users`, and `messages` tables.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, lifespan, router registration
│   ├── core/
│   │   ├── db.py                # SQLAlchemy engine, Base, migration runner
│   │   ├── clients.py           # OpenAI and Pinecone client singletons
│   │   └── celery_app.py        # Celery configuration
│   ├── indexing/
│   │   ├── api.py               # /indexing/* endpoints
│   │   ├── models.py            # IndexedRepo SQLAlchemy model
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   ├── crud.py              # DB operations for indexed repos
│   │   ├── tasks.py             # Celery task: run_indexing_task
│   │   ├── indexer.py           # Pinecone hybrid indexer (dense + sparse)
│   │   └── github_parsing.py    # GitHub ZIP download and code/markdown parsing
│   └── chat/
│       ├── api.py               # /chat/message endpoint
│       ├── models.py            # User, Message SQLAlchemy models
│       ├── schemas.py           # ChatRequest, ChatResponse
│       ├── crud.py              # User and message DB operations
│       └── agents/
│           ├── chat_agent/      # Main orchestrator graph
│           ├── retrieval_agent/ # Multi-iteration retrieval graph
│           ├── generation_agent/# Iterative generation + evaluation graph
│           └── basic_rag/       # Simplified retriever→generator graph
├── alembic/                     # Alembic migration environment
│   ├── env.py                   # Async-compatible migration runner
│   └── versions/                # Migration files (one per schema change)
├── alembic.ini                  # Alembic configuration
├── BM25_params/                 # Fitted BM25 encoder state per namespace
├── langgraph.json               # LangGraph graph registration
└── pyproject.toml               # Dependencies (managed with uv)
```
