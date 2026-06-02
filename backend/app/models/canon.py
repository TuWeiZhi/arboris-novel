from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


BIGINT_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")
LONG_TEXT_TYPE = Text().with_variant(LONGTEXT, "mysql")


class CanonEntry(Base):
    """Project-level story bible entry used as authoritative writing context."""

    __tablename__ = "canon_entries"

    id: Mapped[int] = mapped_column(BIGINT_PK_TYPE, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("novel_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(LONG_TEXT_TYPE, nullable=False)

    aliases: Mapped[Optional[list]] = mapped_column(JSON)
    keywords: Mapped[Optional[list]] = mapped_column(JSON)
    tags: Mapped[Optional[list]] = mapped_column(JSON)
    relations: Mapped[Optional[dict]] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="pov_safe")
    source: Mapped[Optional[str]] = mapped_column(String(64))

    valid_from_chapter: Mapped[Optional[int]] = mapped_column(Integer)
    valid_until_chapter: Mapped[Optional[int]] = mapped_column(Integer)
    last_verified_chapter: Mapped[Optional[int]] = mapped_column(Integer)
    hard_rule: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    extra: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

