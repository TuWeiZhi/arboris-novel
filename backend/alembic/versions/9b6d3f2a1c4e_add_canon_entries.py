"""add_canon_entries

Revision ID: 9b6d3f2a1c4e
Revises: d534ad5ae8e0
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "9b6d3f2a1c4e"
down_revision: Union[str, Sequence[str], None] = "d534ad5ae8e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "canon_entries",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text().with_variant(mysql.LONGTEXT(), "mysql"), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("relations", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("valid_from_chapter", sa.Integer(), nullable=True),
        sa.Column("valid_until_chapter", sa.Integer(), nullable=True),
        sa.Column("last_verified_chapter", sa.Integer(), nullable=True),
        sa.Column("hard_rule", sa.Boolean(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["novel_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_canon_entries_category"), "canon_entries", ["category"], unique=False)
    op.create_index(op.f("ix_canon_entries_project_id"), "canon_entries", ["project_id"], unique=False)
    op.create_index(op.f("ix_canon_entries_status"), "canon_entries", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_canon_entries_status"), table_name="canon_entries")
    op.drop_index(op.f("ix_canon_entries_project_id"), table_name="canon_entries")
    op.drop_index(op.f("ix_canon_entries_category"), table_name="canon_entries")
    op.drop_table("canon_entries")

