import os
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.indexing.crud import get_indexed_repos, get_all_indexed_sources
from app.indexing.tasks import run_indexing_task, run_financial_indexing_task
from app.indexing.schemas import (
    IndexingRequest,
    FinancialIndexingRequest,
    RepoListResponse,
    Repo,
    FinancialCollectionListResponse,
    FinancialCollection,
    SourceListResponse,
    IndexedSourceResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# GitHub indexing
# ---------------------------------------------------------------------------

@router.post("/index")
def index_repo(request: IndexingRequest) -> dict:
    """Enqueue a background job to index a GitHub repository."""
    task = run_indexing_task.delay(request.github_url)
    return {"task_id": task.id, "status": "started"}


# ---------------------------------------------------------------------------
# Financial indexing
# ---------------------------------------------------------------------------

@router.post("/index/financial")
def index_financial(request: FinancialIndexingRequest) -> dict:
    """Enqueue a background job to index local financial documents."""
    if not os.path.exists(request.local_path):
        raise HTTPException(status_code=400, detail=f"Path does not exist: {request.local_path}")
    task = run_financial_indexing_task.delay(request.local_path, request.description)
    return {"task_id": task.id, "status": "started"}


# ---------------------------------------------------------------------------
# Listing endpoints
# ---------------------------------------------------------------------------

@router.get("/repos", response_model=RepoListResponse)
async def list_indexed_repos(db: AsyncSession = Depends(get_db)):
    """List all indexed GitHub repositories."""
    repos = await get_indexed_repos(db)
    return RepoListResponse(repos=[Repo.model_validate(r) for r in repos])


@router.get("/sources", response_model=SourceListResponse)
async def list_indexed_sources(db: AsyncSession = Depends(get_db)):
    """List all indexed sources of any type (GitHub repos and financial collections)."""
    sources = await get_all_indexed_sources(db)
    return SourceListResponse(
        sources=[IndexedSourceResponse.model_validate(s) for s in sources]
    )
