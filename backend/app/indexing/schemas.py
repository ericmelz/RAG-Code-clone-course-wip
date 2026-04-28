from pydantic import BaseModel, ConfigDict, field_serializer
from datetime import datetime

from app.indexing.documents import CodeElement  # noqa: F401 — re-exported for existing importers


class File(BaseModel):
    content: str
    path: str
    extension: str


# ---------------------------------------------------------------------------
# Indexing request schemas
# ---------------------------------------------------------------------------

class IndexingRequest(BaseModel):
    """Backwards-compatible GitHub indexing request."""
    github_url: str


# Explicit typed variants (preferred for new code)
GithubIndexingRequest = IndexingRequest


class FinancialIndexingRequest(BaseModel):
    local_path: str
    description: str | None = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class Repo(BaseModel):
    """Response schema for a single indexed GitHub repository."""
    github_url: str
    namespace: str
    indexed_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("indexed_at")
    def serialize_indexed_at(self, value: datetime) -> str:
        return value.isoformat()


class RepoListResponse(BaseModel):
    repos: list[Repo]


class FinancialCollection(BaseModel):
    """Response schema for a single indexed financial collection."""
    local_path: str
    namespace: str
    description: str | None = None
    indexed_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("indexed_at")
    def serialize_indexed_at(self, value: datetime) -> str:
        return value.isoformat()


class FinancialCollectionListResponse(BaseModel):
    collections: list[FinancialCollection]


class IndexedSourceResponse(BaseModel):
    """Unified response schema for any indexed source, regardless of type."""
    id: int
    namespace: str
    index_type: str
    indexed_at: datetime
    github_url: str | None = None
    local_path: str | None = None
    description: str | None = None
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("indexed_at")
    def serialize_indexed_at(self, value: datetime) -> str:
        return value.isoformat()


class SourceListResponse(BaseModel):
    sources: list[IndexedSourceResponse]
