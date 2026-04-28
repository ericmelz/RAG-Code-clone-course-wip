"""replace_indexed_repos_with_indexed_sources

Revision ID: 7c6e89400253
Revises: e98b5c918f30
Create Date: 2026-04-28 09:25:08.911525

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c6e89400253'
down_revision: Union[str, Sequence[str], None] = 'e98b5c918f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'indexed_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('namespace', sa.String(length=2048), nullable=False),
        sa.Column('index_type', sa.String(length=50), nullable=False),
        sa.Column('indexed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('github_url', sa.String(length=2048), nullable=True),
        sa.Column('local_path', sa.String(length=4096), nullable=True),
        sa.Column('description', sa.String(length=2048), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('namespace'),
        sa.UniqueConstraint('github_url'),
    )

    # Migrate existing GitHub repo rows, preserving all data
    op.execute("""
        INSERT INTO indexed_sources
            (id, namespace, index_type, indexed_at, updated_at, github_url)
        SELECT id, namespace, 'github', indexed_at, updated_at, github_url
        FROM indexed_repos
    """)

    op.drop_table('indexed_repos')


def downgrade() -> None:
    op.create_table(
        'indexed_repos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('github_url', sa.String(length=2048), nullable=False),
        sa.Column('namespace', sa.String(length=2048), nullable=False),
        sa.Column('indexed_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('github_url'),
        sa.UniqueConstraint('namespace'),
    )

    # Restore only GitHub rows
    op.execute("""
        INSERT INTO indexed_repos
            (id, github_url, namespace, indexed_at, updated_at)
        SELECT id, github_url, namespace, indexed_at, updated_at
        FROM indexed_sources
        WHERE index_type = 'github'
    """)

    op.drop_table('indexed_sources')
