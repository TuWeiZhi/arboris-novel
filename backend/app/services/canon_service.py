from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.canon import CanonEntry


CANON_ACTIVE_STATUSES = ("active", "changed")


@dataclass
class CanonMatch:
    entry: CanonEntry
    reason: str
    score: int


class CanonService:
    """Manage project story-bible entries and select relevant canon for writing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_entry(self, entry_id: int) -> Optional[CanonEntry]:
        result = await self.db.execute(select(CanonEntry).where(CanonEntry.id == entry_id))
        return result.scalar_one_or_none()

    async def list_entries(
        self,
        project_id: str,
        *,
        category: Optional[str] = None,
        status: Optional[str] = None,
        chapter_number: Optional[int] = None,
        query: Optional[str] = None,
    ) -> List[CanonEntry]:
        stmt = select(CanonEntry).where(CanonEntry.project_id == project_id)
        if category:
            stmt = stmt.where(CanonEntry.category == category)
        if status:
            stmt = stmt.where(CanonEntry.status == status)
        if chapter_number is not None:
            stmt = stmt.where(_chapter_valid_clause(chapter_number))

        stmt = stmt.order_by(CanonEntry.hard_rule.desc(), CanonEntry.category, CanonEntry.title)
        result = await self.db.execute(stmt)
        entries = list(result.scalars().all())
        if query:
            needle = query.casefold()
            entries = [
                entry for entry in entries
                if _entry_text_for_search(entry).casefold().find(needle) >= 0
            ]
        return entries

    async def create_entry(self, project_id: str, data: Dict[str, Any]) -> CanonEntry:
        entry = CanonEntry(project_id=project_id)
        self._apply_entry_data(entry, data)
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def update_entry(self, entry: CanonEntry, data: Dict[str, Any]) -> CanonEntry:
        self._apply_entry_data(entry, data)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def delete_entry(self, entry: CanonEntry) -> None:
        await self.db.execute(delete(CanonEntry).where(CanonEntry.id == entry.id))
        await self.db.commit()

    async def select_relevant_entries(
        self,
        project_id: str,
        *,
        chapter_number: int,
        query_text: str,
        limit: int = 12,
    ) -> List[CanonMatch]:
        stmt = (
            select(CanonEntry)
            .where(
                and_(
                    CanonEntry.project_id == project_id,
                    CanonEntry.status.in_(CANON_ACTIVE_STATUSES),
                    _chapter_valid_clause(chapter_number),
                )
            )
            .order_by(CanonEntry.hard_rule.desc(), CanonEntry.category, CanonEntry.title)
        )
        result = await self.db.execute(stmt)
        entries = list(result.scalars().all())

        query_blob = query_text.casefold()
        matches: Dict[int, CanonMatch] = {}
        for entry in entries:
            score, reason = _score_entry(entry, query_blob)
            if score <= 0:
                continue
            matches[entry.id] = CanonMatch(entry=entry, reason=reason, score=score)

        selected = sorted(matches.values(), key=lambda item: (-item.score, item.entry.category, item.entry.title))
        return selected[:limit]

    async def build_prompt_context(
        self,
        project_id: str,
        *,
        chapter_number: int,
        query_text: str,
        limit: int = 12,
    ) -> Optional[str]:
        matches = await self.select_relevant_entries(
            project_id,
            chapter_number=chapter_number,
            query_text=query_text,
            limit=limit,
        )
        if not matches:
            return None
        return format_canon_matches(matches)

    @staticmethod
    def _apply_entry_data(entry: CanonEntry, data: Dict[str, Any]) -> None:
        allowed = {
            "category",
            "title",
            "content",
            "aliases",
            "keywords",
            "tags",
            "relations",
            "status",
            "visibility",
            "source",
            "valid_from_chapter",
            "valid_until_chapter",
            "last_verified_chapter",
            "hard_rule",
            "locked",
            "evidence",
            "extra",
        }
        for key, value in data.items():
            if key in allowed:
                setattr(entry, key, value)


def format_canon_matches(matches: Sequence[CanonMatch]) -> str:
    lines = ["# 小说圣经 / Canon 摘录"]
    for item in matches:
        entry = item.entry
        flags = []
        if entry.hard_rule:
            flags.append("硬规则")
        if entry.valid_from_chapter or entry.valid_until_chapter:
            start = entry.valid_from_chapter or "?"
            end = entry.valid_until_chapter or "今"
            flags.append(f"有效章节:{start}-{end}")
        flags.append(f"触发:{item.reason}")
        flag_text = f" ({'; '.join(flags)})" if flags else ""

        lines.append(f"\n## [{entry.category}] {entry.title}{flag_text}")
        aliases = _coerce_string_list(entry.aliases)
        keywords = _coerce_string_list(entry.keywords)
        if aliases:
            lines.append(f"- 别名: {'、'.join(aliases[:8])}")
        if keywords:
            lines.append(f"- 关键词: {'、'.join(keywords[:8])}")
        lines.append(entry.content.strip())
    return "\n".join(lines)


def build_canon_query_text(*parts: Any) -> str:
    rendered: List[str] = []
    for part in parts:
        if not part:
            continue
        if isinstance(part, str):
            rendered.append(part)
        else:
            try:
                rendered.append(json.dumps(part, ensure_ascii=False))
            except TypeError:
                rendered.append(str(part))
    return "\n".join(rendered)


def _chapter_valid_clause(chapter_number: int):
    return and_(
        or_(CanonEntry.valid_from_chapter.is_(None), CanonEntry.valid_from_chapter <= chapter_number),
        or_(CanonEntry.valid_until_chapter.is_(None), CanonEntry.valid_until_chapter >= chapter_number),
    )


def _score_entry(entry: CanonEntry, query_blob: str) -> tuple[int, str]:
    if entry.hard_rule:
        return 100, "hard_rule"

    terms = _entry_terms(entry)
    for term in terms:
        if term and term.casefold() in query_blob:
            return 80, f"keyword:{term}"

    return 0, "none"


def _entry_terms(entry: CanonEntry) -> List[str]:
    terms = [entry.title]
    terms.extend(_coerce_string_list(entry.aliases))
    terms.extend(_coerce_string_list(entry.keywords))
    terms.extend(_coerce_string_list(entry.tags))
    return [term.strip() for term in terms if isinstance(term, str) and term.strip()]


def _entry_text_for_search(entry: CanonEntry) -> str:
    parts = [
        entry.category,
        entry.title,
        entry.content,
        entry.status,
        entry.visibility,
        entry.source,
        *_coerce_string_list(entry.aliases),
        *_coerce_string_list(entry.keywords),
        *_coerce_string_list(entry.tags),
    ]
    return "\n".join(part for part in parts if part)


def _coerce_string_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []

