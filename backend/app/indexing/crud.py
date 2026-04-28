from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.indexing.models import IndexedSource, IndexedGithubRepo, IndexedFinancialCollection


async def save_indexed_repo(
        session: AsyncSession,
        github_url: str,
        namespace: str
) -> IndexedGithubRepo:
    statement = select(IndexedGithubRepo).where(IndexedGithubRepo.github_url == github_url)
    result = await session.execute(statement)
    repo = result.scalar_one_or_none()

    if not repo:
        repo = IndexedGithubRepo(github_url=github_url, namespace=namespace)
        session.add(repo)
        await session.commit()
        await session.refresh(repo)

    return repo


async def save_indexed_financial_collection(
        session: AsyncSession,
        local_path: str,
        namespace: str,
        description: str | None = None
) -> IndexedFinancialCollection:
    statement = select(IndexedFinancialCollection).where(
        IndexedFinancialCollection.local_path == local_path
    )
    result = await session.execute(statement)
    collection = result.scalar_one_or_none()

    if not collection:
        collection = IndexedFinancialCollection(
            local_path=local_path,
            namespace=namespace,
            description=description,
        )
        session.add(collection)
        await session.commit()
        await session.refresh(collection)

    return collection


async def get_indexed_repo_by_url(
    session: AsyncSession,
    github_url: str
) -> IndexedGithubRepo | None:
    statement = select(IndexedGithubRepo).where(IndexedGithubRepo.github_url == github_url)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_indexed_repo_by_namespace(
    session: AsyncSession,
    namespace: str
) -> IndexedSource | None:
    """Look up any indexed source by namespace, regardless of type."""
    statement = select(IndexedSource).where(IndexedSource.namespace == namespace)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_indexed_repos(
        session: AsyncSession
) -> list[IndexedGithubRepo]:
    """Return all indexed GitHub repositories ordered by most recent."""
    stmt = select(IndexedGithubRepo).order_by(IndexedGithubRepo.indexed_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_indexed_sources(
        session: AsyncSession
) -> list[IndexedSource]:
    """Return all indexed sources of any type ordered by most recent."""
    stmt = select(IndexedSource).order_by(IndexedSource.indexed_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())
