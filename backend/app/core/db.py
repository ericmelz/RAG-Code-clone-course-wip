from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from alembic.config import Config
from alembic import command
import asyncio

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./sandbox.db"

engine = create_async_engine(SQLALCHEMY_DATABASE_URL)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")


async def run_migrations_async():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_migrations)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session