"""add governance columns to canon/character_state/foreshadowing

Revision ID: c1d2e3f4a5b6
Revises: 9b6d3f2a1c4e
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "9b6d3f2a1c4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # canon_entries：锁定 + 证据
    op.add_column("canon_entries", sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("canon_entries", sa.Column("evidence", sa.JSON(), nullable=True))

    # character_states：确认态 + 锁定 + 来源 + 证据
    op.add_column("character_states", sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.text("1")))
    op.add_column("character_states", sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    op.add_column("character_states", sa.Column("source", sa.String(length=32), nullable=True))
    op.add_column("character_states", sa.Column("evidence", sa.JSON(), nullable=True))

    # foreshadowings：锁定
    op.add_column("foreshadowings", sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("foreshadowings", "locked")
    op.drop_column("character_states", "evidence")
    op.drop_column("character_states", "source")
    op.drop_column("character_states", "locked")
    op.drop_column("character_states", "confirmed")
    op.drop_column("canon_entries", "evidence")
    op.drop_column("canon_entries", "locked")
