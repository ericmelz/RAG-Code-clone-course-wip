import asyncio
import logging
import re

from app.core.celery_app import celery_app
from app.core.db import AsyncSessionLocal
from app.indexing.crud import save_indexed_repo, save_indexed_financial_collection
from app.indexing.indexers.github import GithubIndexer
from app.indexing.indexers.financial import FinancialIndexer
from app.indexing.parsers.github import GitHubParser
from app.indexing.parsers.financial import LocalFinancialParser

logger = logging.getLogger(__name__)


def _path_to_namespace(local_path: str) -> str:
    """Derive a deterministic Pinecone namespace from a local filesystem path."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", local_path.strip("/"))
    slug = slug.strip("-").lower()
    return slug[:200]  # Pinecone namespace limit


# ---------------------------------------------------------------------------
# GitHub indexing task
# ---------------------------------------------------------------------------

@celery_app.task
def run_indexing_task(github_url: str) -> dict[str, str | bool]:
    """Celery task: index a GitHub repository into Pinecone."""
    return asyncio.run(_run_indexing(github_url))


async def _run_indexing(github_url: str) -> dict[str, str | bool]:
    try:
        parser = GitHubParser(github_url)
        indexer = GithubIndexer(owner=parser.owner, repo=parser.repo, ref=parser.ref)
        data = parser.parse()
        await indexer.index_data(data)

        async with AsyncSessionLocal() as db:
            await save_indexed_repo(db, github_url, indexer.namespace)

        logger.info(f"GitHub indexing completed for {github_url}")
        return {"ok": True, "github_url": github_url}
    except Exception as e:
        logger.error(f"GitHub indexing failed: {e}")
        return {"ok": False, "github_url": github_url}


# ---------------------------------------------------------------------------
# Financial indexing task
# ---------------------------------------------------------------------------

@celery_app.task
def run_financial_indexing_task(
    local_path: str,
    description: str | None = None,
) -> dict[str, str | bool]:
    """Celery task: index local financial documents (PDFs, spreadsheets, CSVs) into Pinecone."""
    return asyncio.run(_run_financial_indexing(local_path, description))


async def _run_financial_indexing(
    local_path: str,
    description: str | None,
) -> dict[str, str | bool]:
    try:
        parser = LocalFinancialParser(local_path)
        documents = parser.parse()
        namespace = _path_to_namespace(local_path)
        indexer = FinancialIndexer(namespace=namespace)
        await indexer.index_data(documents)

        async with AsyncSessionLocal() as db:
            await save_indexed_financial_collection(db, local_path, namespace, description)

        logger.info(f"Financial indexing completed for {local_path} (namespace={namespace})")
        return {"ok": True, "local_path": local_path, "namespace": namespace}
    except Exception as e:
        logger.error(f"Financial indexing failed for {local_path}: {e}")
        return {"ok": False, "local_path": local_path}
