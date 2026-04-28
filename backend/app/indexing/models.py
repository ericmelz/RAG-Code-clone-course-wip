import enum
from app.core.db import Base
from sqlalchemy import String, DateTime, func
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column


class IndexType(str, enum.Enum):
    GITHUB = "github"
    FINANCIAL = "financial"


class IndexedSource(Base):
    __tablename__ = "indexed_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    namespace: Mapped[str] = mapped_column(String(2048), unique=True)
    index_type: Mapped[str] = mapped_column(String(50), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # GitHub-specific (null for financial rows)
    github_url: Mapped[str | None] = mapped_column(String(2048), unique=True, nullable=True)

    # Financial-specific (null for github rows)
    local_path: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    __mapper_args__ = {
        "polymorphic_on": "index_type",
    }


class IndexedGithubRepo(IndexedSource):
    __mapper_args__ = {
        "polymorphic_identity": IndexType.GITHUB,
    }


class IndexedFinancialCollection(IndexedSource):
    __mapper_args__ = {
        "polymorphic_identity": IndexType.FINANCIAL,
    }


# Backwards-compatible alias so existing imports keep working
IndexedRepo = IndexedGithubRepo
