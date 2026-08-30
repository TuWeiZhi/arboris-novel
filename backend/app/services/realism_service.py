# AIMETA P=现实常识审核配置_三级现实约束解析|R=现实程度解析_元素级规则加载_提示词渲染|NR=不含LLM调用|E=resolve_realism_config_render_realism_section|X=internal|A=现实约束配置|D=sqlalchemy|S=db|RD=./README.ai
"""现实常识审核配置服务 (RealismService)

把「现实程度」约束解析为可注入一致性检查提示词的内容，支持三级、按作用域覆盖：

1. 全局基线：`NovelConstitution.realism_level`（整本书默认）
2. 元素级：`CanonEntry.hard_rule=True` 的自定义现实规则（按章节有效期过滤）
3. 章级覆盖：`ChapterBlueprint.mission_constraints` 中的
   `realism_override` 与 `realism_exempt_domains`

覆盖优先级：章级 > 元素级 > 全局基线。
元素级没有自定义数据时视为「无元素级限制」，只做通用常识检查，不额外约束任何领域。

全局基线 `realism_level` 取值约定：
- 写实 / 严格 / strict / realistic   → 启用，常识硬伤按 critical
- 半写实 / 混合 / semi / mixed / 软科幻 / 都市异能 → 启用，常识硬伤按 major
- 低现实 / 自由 / 玄幻 / 奇幻 / off / none → 不启用
- 空 / 未设置 → 不启用（保持向后兼容，存量项目不会突然新增失败项）

章级 `realism_override` 取值：strict（强）/ relaxed（弱）/ off（关）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.canon import CanonEntry
from ..models.chapter_blueprint import ChapterBlueprint
from ..models.constitution import NovelConstitution

CANON_ACTIVE_STATUSES = ("active", "changed")

# 全局基线 → 审核强度
_STRONG_LEVELS = {"写实", "现实", "严格", "strict", "realistic", "realism"}
_MODERATE_LEVELS = {
    "半写实", "半现实", "混合", "semi", "semi-realistic", "mixed", "软科幻", "都市异能",
}

# 章级覆盖
_OVERRIDE_STRONG = {"strict", "严格", "写实", "现实"}
_OVERRIDE_MODERATE = {"relaxed", "宽松", "半写实", "半现实", "混合"}
_OVERRIDE_OFF = {"off", "关闭", "禁用", "低现实", "自由", "玄幻", "奇幻", "fantasy", "none"}


def _resolve_strength(level: Optional[str]) -> Optional[str]:
    """全局基线 → 'critical' / 'major' / None（不启用）。"""
    if not level:
        return None
    normalized = str(level).strip().casefold()
    if normalized in _STRONG_LEVELS:
        return "critical"
    if normalized in _MODERATE_LEVELS:
        return "major"
    return None


def _resolve_override(override: Optional[str]) -> Optional[str]:
    """章级覆盖 → 'critical' / 'major' / 'off' / None（未设置）。"""
    if not override:
        return None
    normalized = str(override).strip().casefold()
    if normalized in _OVERRIDE_STRONG:
        return "critical"
    if normalized in _OVERRIDE_MODERATE:
        return "major"
    if normalized in _OVERRIDE_OFF:
        return "off"
    return None


@dataclass
class RealismConfig:
    """一次解析后的现实约束配置。"""

    global_level: Optional[str] = None
    chapter_override: Optional[str] = None
    effective_strength: Optional[str] = None  # 'critical' | 'major' | None
    exempt_domains: List[str] = field(default_factory=list)
    element_rules: List[CanonEntry] = field(default_factory=list)
    element_rules_text: str = ""

    @property
    def enabled(self) -> bool:
        return self.effective_strength is not None


async def resolve_realism_config(
    session: AsyncSession,
    project_id: str,
    chapter_number: Optional[int] = None,
) -> RealismConfig:
    """解析项目某章的生效现实约束。

    Args:
        session: 数据库会话
        project_id: 项目 ID
        chapter_number: 章节号，传 None 时跳过章级覆盖与元素规则的章节有效期过滤
    """
    config = RealismConfig()

    # 1. 全局基线
    result = await session.execute(
        select(NovelConstitution.realism_level).where(NovelConstitution.project_id == project_id)
    )
    config.global_level = result.scalar_one_or_none()

    # 2. 章级覆盖
    if chapter_number is not None:
        result = await session.execute(
            select(ChapterBlueprint.mission_constraints).where(
                ChapterBlueprint.project_id == project_id,
                ChapterBlueprint.chapter_number == chapter_number,
            )
        )
        raw = result.scalar_one_or_none()
        mission_constraints = _coerce_mission_constraints(raw)
        config.chapter_override = mission_constraints.get("realism_override")
        config.exempt_domains = _coerce_string_list(
            mission_constraints.get("realism_exempt_domains")
        )

    # 3. 计算生效强度：章级 > 全局
    override_strength = _resolve_override(config.chapter_override)
    if override_strength == "off":
        config.effective_strength = None
    elif override_strength is not None:
        config.effective_strength = override_strength
    else:
        config.effective_strength = _resolve_strength(config.global_level)

    # 4. 元素级自定义现实规则（hard_rule canon，按章有效 + 豁免域过滤）
    if config.enabled:
        config.element_rules = await _load_element_rules(session, project_id, chapter_number)
        exempt = {domain.casefold() for domain in config.exempt_domains}
        config.element_rules = [
            entry for entry in config.element_rules
            if not entry.category or entry.category.casefold() not in exempt
        ]
        config.element_rules_text = _format_element_rules(config.element_rules)

    return config


async def _load_element_rules(
    session: AsyncSession,
    project_id: str,
    chapter_number: Optional[int],
) -> List[CanonEntry]:
    """加载元素级现实硬规则：`hard_rule=True` 且对本章有效的 canon 条目。"""
    stmt = select(CanonEntry).where(
        CanonEntry.project_id == project_id,
        CanonEntry.hard_rule.is_(True),
        CanonEntry.status.in_(CANON_ACTIVE_STATUSES),
    )
    if chapter_number is not None:
        stmt = stmt.where(
            and_(
                or_(
                    CanonEntry.valid_from_chapter.is_(None),
                    CanonEntry.valid_from_chapter <= chapter_number,
                ),
                or_(
                    CanonEntry.valid_until_chapter.is_(None),
                    CanonEntry.valid_until_chapter >= chapter_number,
                ),
            )
        )
    stmt = stmt.order_by(CanonEntry.category, CanonEntry.title)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def render_realism_section(config: RealismConfig) -> str:
    """把现实约束渲染为一致性检查提示词的一个片段；未启用时返回空串。"""
    if not config.enabled:
        return ""

    if config.effective_strength == "critical":
        severity_label = "严格（现实常识硬伤按 critical 处理）"
    else:
        severity_label = "宽松（现实常识硬伤按 major 处理）"

    lines = [
        "### 5. 现实常识一致性",
        f"本作现实程度约束强度：{severity_label}。",
        "请检查正文是否存在违背现实常识的描写（例如「用鼻子吃饭」这类生理/物理/常识错误）。",
        "自定义现实规则（元素级硬约束，仅约束以下所列领域；未列出的领域不做额外元素级限制）：",
        config.element_rules_text,
    ]
    if config.exempt_domains:
        lines.append(f"本章豁免领域：{'、'.join(config.exempt_domains)}（这些领域不做现实常识检查）。")
    lines.append("注意：作者已在世界观中显式设定或豁免的内容不算违规。")
    return "\n".join(lines)


def _format_element_rules(entries: List[CanonEntry]) -> str:
    if not entries:
        return "（未配置自定义现实规则，本章不做元素级限制，仅按通用常识检查）"
    lines = []
    for entry in entries:
        content = (entry.content or "").strip()
        lines.append(f"- [{entry.category}] {entry.title}: {content}")
    return "\n".join(lines)


def _coerce_mission_constraints(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}
    return {}


def _coerce_string_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    return []
