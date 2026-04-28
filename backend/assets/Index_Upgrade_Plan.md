# Index Upgrade Plan: Multi-Source Indexing Architecture

## Goal

Extend the application to support multiple index types — initially **GitHub** (existing) and **Financial** (new: local filesystem PDFs, spreadsheets, CSVs) — in a way that is cleanly extensible to future types without modifying existing code.

---

## Current State

- One model: `IndexedRepo` — stores `github_url`, `namespace`, timestamps
- One parser: `GitHubParser` — downloads repo ZIP, AST-parses Python, chunks Markdown
- One document type: `CodeElement` — text, source path, header, extension, description
- One indexer: `Indexer` — hybrid Pinecone (dense OpenAI + sparse BM25/SPLADE), per-namespace
- One Celery task: `run_indexing_task(github_url)` — end-to-end GitHub indexing
- One API endpoint: `POST /indexing/index` — accepts `github_url`
- Chat agent uses `namespace` to look up documents; assumes code/markdown content
- No schema migration tooling (tables created via `Base.metadata.create_all()`)

---

## Design Principles

1. **Open/Closed**: Add new index types by adding new classes, not modifying existing ones.
2. **Dependency Inversion**: The indexing API and Celery tasks depend on abstractions (protocols/base classes), not concrete parsers or indexers.
3. **Explicit index type**: Every indexed source carries an `index_type` discriminator so the retrieval and generation pipeline can adapt its behavior.
4. **Preserve existing data**: All migrations must be non-destructive to the existing `indexed_repos` table.

---

## Phase 1: Introduce Alembic

**Why**: `Base.metadata.create_all()` cannot perform ALTER TABLE. Any structural DB change (renaming columns, adding foreign keys, adding new tables with FK relationships) requires migrations.

### Steps

1. Add `alembic` to `pyproject.toml` dependencies.
2. Run `alembic init alembic` in `backend/` to create `alembic/` directory and `alembic.ini`.
3. Configure `alembic/env.py` to use the app's `Base` and the async SQLite engine from `app.core.db`.
4. Generate an initial migration from the current DB state (`alembic revision --autogenerate -m "initial"`).
5. Remove `create_tables()` from the lifespan startup; replace with `alembic upgrade head` (run once at startup, or via a script).

**Files changed**: `pyproject.toml`, new `alembic/` directory, `app/core/db.py` (remove `create_tables` or keep as fallback for tests).

---

## Phase 2: Unified `IndexedSource` Model (Database)

Replace the narrow `IndexedRepo` model with a polymorphic `IndexedSource` base model using **SQLAlchemy single-table inheritance (STI)**.

### Why STI over separate tables?
- Namespace lookups (the main chat-side operation) remain a single query regardless of type.
- Simpler for a small number of types with modest extra metadata per type.
- Can migrate to joined-table inheritance later if type-specific metadata grows large.

### New Model Structure

```python
# app/indexing/models.py

class IndexType(str, enum.Enum):
    GITHUB = "github"
    FINANCIAL = "financial"

class IndexedSource(Base):
    __tablename__ = "indexed_sources"
    id          = Column(Integer, primary_key=True)
    namespace   = Column(String, unique=True, nullable=False)
    index_type  = Column(Enum(IndexType), nullable=False)
    indexed_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # GitHub-specific (nullable for financial rows)
    github_url  = Column(String, unique=True, nullable=True)

    # Financial-specific (nullable for github rows)
    local_path  = Column(String, nullable=True)  # absolute path on the server
    description = Column(String, nullable=True)  # human-readable label

    __mapper_args__ = {
        "polymorphic_on": index_type,
        "polymorphic_identity": None,
    }

class IndexedGithubRepo(IndexedSource):
    __mapper_args__ = {"polymorphic_identity": IndexType.GITHUB}

class IndexedFinancialCollection(IndexedSource):
    __mapper_args__ = {"polymorphic_identity": IndexType.FINANCIAL}
```

### Migration

Write an Alembic migration that:
1. Creates the new `indexed_sources` table.
2. Copies all rows from the old `indexed_repos` table into `indexed_sources` with `index_type = 'github'`.
3. Drops the old `indexed_repos` table (or renames it as a backup).

**Files changed**: `app/indexing/models.py`, new Alembic migration file.

---

## Phase 3: Document Model Abstraction

`CodeElement` is tightly coupled to code/markdown structure (header, extension). Financial documents need different metadata.

### Introduce a base `Document` type

```python
# app/indexing/documents.py

class Document(BaseModel):
    text: str
    source: str               # file path or identifier
    description: str | None = None

class CodeElement(Document):  # existing, unchanged
    header: str | None = None
    extension: str

class FinancialDocument(Document):
    doc_type: str             # "pdf", "spreadsheet", "csv"
    page_or_sheet: str | None = None  # "page 3" or "Sheet1"
    fiscal_period: str | None = None  # e.g. "Q3 2024"
```

`CodeElement` is kept unchanged to avoid breaking the existing pipeline. `FinancialDocument` is a peer, not a subclass.

**Files changed**: new `app/indexing/documents.py`; `app/indexing/github_parsing.py` imports `CodeElement` from there instead of defining it locally.

---

## Phase 4: Parser Abstraction

### Base interface

```python
# app/indexing/parsers/base.py

from typing import Protocol
from app.indexing.documents import Document

class BaseParser(Protocol):
    def parse(self) -> list[Document]: ...
```

### Existing parser

- Move `app/indexing/github_parsing.py` → `app/indexing/parsers/github.py`
- `GitHubParser.parse_repo()` becomes `parse()` to satisfy the protocol (keep old name as alias for compatibility)

### New Financial parser

```python
# app/indexing/parsers/financial.py

class LocalFinancialParser:
    def __init__(self, local_path: str): ...

    def parse(self) -> list[FinancialDocument]:
        # Walk directory tree
        # .pdf  → extract text per page via PyMuPDF or pdfplumber
        # .xlsx / .xls → iterate sheets, stringify cell ranges via openpyxl
        # .csv  → chunk rows with header context via csv module
        # For each file, produce overlapping chunks with metadata
        ...
```

**New dependencies**: `pdfplumber` or `pymupdf`, `openpyxl` — add to `pyproject.toml`.

**Files changed**: new `app/indexing/parsers/` package, `app/indexing/github_parsing.py` adjusted.

---

## Phase 5: Indexer Abstraction

The core Pinecone indexing logic is the same for both types (hybrid vectors, upsert). The differences are:
- **Metadata stored**: code fields vs. financial fields
- **Summarization prompt**: code summary prompt vs. financial document summary prompt
- **Sparse encoding**: BM25 parameters per namespace (already namespace-scoped)

### Approach

Extract a thin `BaseIndexer` protocol:

```python
# app/indexing/indexers/base.py

class BaseIndexer(Protocol):
    async def index_data(self, documents: list[Document]) -> None: ...
    async def search(self, query: str, ...) -> list[Document]: ...
```

Rename current `Indexer` → `GithubIndexer` (or keep as `Indexer` with a factory alias). Create `FinancialIndexer` that overrides the summarization prompt and metadata schema.

Because Pinecone metadata is schemaless, the `FinancialIndexer` can store `doc_type`, `fiscal_period`, etc. in the metadata dict without any Pinecone schema changes.

**Files changed**: new `app/indexing/indexers/` package; existing `app/indexing/indexer.py` refactored.

---

## Phase 6: API & Task Layer

### New request schemas

```python
# app/indexing/schemas.py

class GithubIndexingRequest(BaseModel):
    github_url: str

class FinancialIndexingRequest(BaseModel):
    local_path: str
    description: str | None = None
```

### Dispatcher endpoint

```
POST /indexing/index/github    → run_github_indexing_task.delay(github_url)
POST /indexing/index/financial → run_financial_indexing_task.delay(local_path, description)
```

Or a single endpoint with a discriminated union:

```python
class IndexingRequest(BaseModel):
    index_type: IndexType
    github_url: str | None = None
    local_path: str | None = None
    description: str | None = None
```

The router calls a factory that returns the appropriate Celery task.

### New Celery task

```python
# app/indexing/tasks.py

@celery_app.task
def run_financial_indexing_task(local_path: str, description: str | None):
    parser = LocalFinancialParser(local_path)
    documents = parser.parse()
    namespace = slugify(local_path)   # deterministic namespace from path
    indexer = FinancialIndexer(namespace=namespace)
    run_sync(indexer.index_data(documents))
    save_indexed_financial_collection(local_path, namespace, description)
```

**Files changed**: `app/indexing/api.py`, `app/indexing/schemas.py`, `app/indexing/tasks.py`, `app/indexing/crud.py`.

---

## Phase 7: Chat Pipeline Adaptation

The chat agent's retrieval is namespace-scoped and currently agnostic to index type. Two areas need adaptation:

### 7a. `ChatRequest` carries namespace directly (already done)

`ChatRequest.namespace` is already decoupled from `github_url`. No change needed to the request schema.

### 7b. Agent routing by index type

When a chat request arrives, look up the `index_type` for the namespace from the DB and route to the appropriate agent graph:

- `index_type = GITHUB` → invoke `chat_agent` (existing multi-agent pipeline with intent router, retrieval agent, generation agent)
- `index_type = FINANCIAL` → invoke `basic_rag` agent (simpler retriever → generator pipeline, no intent routing)

**Implementation**: In `app/chat/api.py`, after looking up the namespace, branch on `index_type` to call either `chat_agent.ainvoke()` or `basic_chat_agent.ainvoke()`. Both accept a state with `namespace`, `chat_messages`, and return `generation`.

```python
# app/chat/api.py
from app.indexing.models import IndexType
from app.chat.agents.basic_rag.agent import basic_chat_agent
from app.chat.agents.basic_rag.state import BasicChatAgentState

source = await get_indexed_repo_by_namespace(db, request.namespace)

if source.index_type == IndexType.FINANCIAL:
    initial_state = BasicChatAgentState(
        namespace=source.namespace,
        chat_messages=chat_messages,
    )
    result = await basic_chat_agent.ainvoke(initial_state)
    final_state = BasicChatAgentState(**result)
else:
    initial_state = ChatAgentState(
        namespace=source.namespace,
        chat_messages=chat_messages,
    )
    result = await chat_agent.ainvoke(initial_state, debug=True)
    final_state = ChatAgentState(**result)

response_text = final_state.generation or "I'm sorry, I couldn't generate a response."
```

**Files changed**: `app/chat/api.py`.

---

### Deferred alternatives

- **Option A — prompt-swap within chat_agent**: Add `index_type` to `ChatAgentState`, look it up at request time, pass it through to the generation and evaluation nodes to select financial vs. code system prompts. Keeps a single agent graph but couples the graph state to index type. Suitable if the generation agent needs to be reused for financial with only prompt changes.

- **Option B — separate graph per type**: Define a `financial_rag` LangGraph graph (registered in `langgraph.json`) purpose-built for financial Q&A with tailored retrieval, generation, and evaluation prompts. The `chat/api.py` router dispatches by `index_type`. Maximum flexibility, highest initial cost.

---

## Phase 8: Admin UI

Add a `IndexedFinancialCollectionAdmin` view to SQLAdmin alongside the existing `IndexedRepoAdmin`. Both can inherit from a shared base admin class.

**Files changed**: `app/indexing/admin.py`.

---

## Summary of File Changes

| Area | Files Created | Files Modified |
|---|---|---|
| Migrations | `alembic/`, migration files | `app/core/db.py`, `pyproject.toml` |
| Models | — | `app/indexing/models.py` |
| Documents | `app/indexing/documents.py` | `app/indexing/github_parsing.py` |
| Parsers | `app/indexing/parsers/base.py`, `parsers/github.py`, `parsers/financial.py` | `app/indexing/github_parsing.py` |
| Indexers | `app/indexing/indexers/base.py`, `indexers/financial.py` | `app/indexing/indexer.py` |
| API/Tasks | — | `app/indexing/api.py`, `schemas.py`, `tasks.py`, `crud.py` |
| Chat | — | `app/chat/api.py`, `agents/chat_agent/state.py`, generation nodes |
| Admin | — | `app/indexing/admin.py` |

---

## Recommended Implementation Order

1. **Phase 1** — Alembic (unblocks all schema changes)
2. **Phase 3** — Document model (no DB changes, unblocks parsers)
3. **Phase 2** — Unified DB model + migration (requires Alembic)
4. **Phase 4** — Parsers (requires document model)
5. **Phase 5** — Indexers (requires parsers and document model)
6. **Phase 6** — API & tasks (requires models, parsers, indexers)
7. **Phase 7** — Chat adaptation (can start after Phase 2)
8. **Phase 8** — Admin (last, cosmetic)

---

## Open Questions

1. **Authentication for local paths**: The financial indexer walks the local filesystem. Should the API validate that the path is within an allowed root directory to prevent traversal attacks?
2. **File size limits**: PDFs and spreadsheets can be very large. Should there be a per-file size cap analogous to the 1MB cap in `GitHubParser`?
3. **Incremental re-indexing**: Should re-running the financial indexer on the same path append new documents, replace all, or diff?
4. **Namespace generation for financial collections**: `github_url` → `owner-repo[-ref]` is deterministic. For local paths, a slug of the path works but is fragile if the directory moves. Consider a user-supplied `collection_name` as the namespace key.
5. **Single-table vs joined-table inheritance**: STI is simple now, but if `IndexedFinancialCollection` grows many type-specific fields (a dozen+), migrate to joined-table to avoid a wide nullable-heavy table.
