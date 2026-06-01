"""章节上下文组装器 — 从 PipelineOrchestrator 中提取的上下文收集逻辑。

职责：
1. 历史章节收集 (_collect_history_context)
2. 蓝图规范化 + 导演脚本生成 (_normalize_blueprint, _generate_chapter_mission)
3. RAG 检索 (_get_rag_context, _get_two_stage_rag_context)
4. 记忆/结构化记忆 (_get_memory_context, _get_structured_memory)
5. Prompt 片段拼装 (_build_prompt_sections)
6. 风格提示/POV 解析 (_resolve_style_hints, _resolve_pov_character)

不负责：配置解析、版本生成、评审、后处理 — 这些保留在 PipelineOrchestrator。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.foreshadowing import Foreshadowing
from ..models.memory_layer import CausalChain, CharacterState
from ..models.project_memory import ProjectMemory
from .knowledge_retrieval_service import FilteredContext, KnowledgeRetrievalService
from .llm_service import LLMService
from .memory_layer_service import MemoryLayerService
from .prompt_service import PromptService
from .chapter_context_service import ChapterContextService
from .vector_store_service import VectorStoreService
from .writer_context_builder import WriterContextBuilder
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 输出数据结构
# ---------------------------------------------------------------------------

@dataclass
class AssembledChapterContext:
    """组装完成的章节上下文，供 PipelineOrchestrator 的生成阶段使用。"""
    history: Dict[str, Any] = field(default_factory=dict)
    blueprint_dict: Dict[str, Any] = field(default_factory=dict)
    chapter_mission: Optional[dict] = None
    visibility_context: Dict[str, Any] = field(default_factory=dict)
    enhanced_context: Optional[Dict[str, Any]] = None
    memory_context: Optional[str] = None
    project_memory_text: Optional[str] = None
    structured_memory: Optional[str] = None
    rag_context: Optional[Dict[str, Any]] = None
    knowledge_context: Optional[str] = None
    rag_stats: Optional[Dict[str, Any]] = None
    prompt_sections: List[Tuple[str, str]] = field(default_factory=list)
    prompt_input: str = ""
    version_style_hints: List[Optional[str]] = field(default_factory=list)

    # 快捷访问
    writer_blueprint: Dict[str, Any] = field(default_factory=dict)
    forbidden_characters: List[str] = field(default_factory=list)
    introduced_characters: List[str] = field(default_factory=list)
    allowed_new_characters: List[str] = field(default_factory=list)
    character_profiles: str = ""


# ---------------------------------------------------------------------------
# 上下文组装器
# ---------------------------------------------------------------------------

class ChapterContextAssembler:
    """章节上下文组装器 — 收集生成所需的一切信息。"""

    def __init__(
        self,
        session: AsyncSession,
        llm_service: LLMService,
        prompt_service: PromptService,
    ):
        self.session = session
        self.llm_service = llm_service
        self.prompt_service = prompt_service

    # ---- 主入口 ----

    async def assemble(
        self,
        *,
        project_id: str,
        chapter_number: int,
        user_id: int,
        writing_notes: str,
        outlines_map: Dict[int, Any],
        chapters: List[Any],
        blueprint_dict: Dict[str, Any],
        project_schema: Any,  # NovelProjectSchema
        outline_title: str,
        outline_summary: str,
        config: Any,  # PipelineConfig
        visibility_context: Dict[str, Any],
        chapter_mission_inputs: Dict[str, Any],
    ) -> AssembledChapterContext:
        """一站式收集所有上下文。"""
        ctx = AssembledChapterContext()

        # 1. 历史章节 + 尾部摘录
        ctx.history = await self._collect_history_context(
            project_id=project_id,
            chapter_number=chapter_number,
            outlines_map=outlines_map,
            chapters=chapters,
            user_id=user_id,
        )

        # 2. 生成导演脚本
        ctx.chapter_mission = await self._generate_chapter_mission(
            blueprint_dict=blueprint_dict,
            previous_summary=ctx.history["previous_summary"],
            previous_tail=ctx.history["previous_tail"],
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            introduced_characters=chapter_mission_inputs.get("introduced_characters", []),
            all_characters=chapter_mission_inputs.get("all_characters", []),
            user_id=user_id,
        )

        ctx.allowed_new_characters = (
            ctx.chapter_mission.get("allowed_new_characters", []) if ctx.chapter_mission else []
        )

        # 3. 可视化上下文
        ctx.visibility_context = WriterContextBuilder().build_visibility_context(
            blueprint=blueprint_dict,
            completed_summaries=ctx.history.get("completed_summaries", []),
            previous_tail=ctx.history.get("previous_tail", ""),
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            allowed_new_characters=ctx.allowed_new_characters,
        ) or visibility_context
        ctx.writer_blueprint = ctx.visibility_context.get("writer_blueprint", {})
        ctx.forbidden_characters = ctx.visibility_context.get("forbidden_characters", [])
        ctx.introduced_characters = ctx.visibility_context.get("introduced_characters", [])
        ctx.character_profiles = ctx.visibility_context.get("character_profiles", "")

        # 4. Enhanced flow context（宪法/Persona/势力）
        if config.enable_constitution or config.enable_persona or config.enable_foreshadowing or config.enable_faction:
            from .enhanced_writing_flow import EnhancedWritingFlow
            enhanced_flow = EnhancedWritingFlow(self.session, self.llm_service, self.prompt_service)
            ctx.enhanced_context = await enhanced_flow.prepare_writing_context(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_outline=outline_summary,
            )

        # 5. 记忆上下文
        if config.enable_memory:
            ctx.memory_context = await self._get_memory_context(
                project_id=project_id,
                chapter_number=chapter_number,
                involved_characters=ctx.introduced_characters,
            )

        # 6. 项目记忆文本
        ctx.project_memory_text = await self._get_project_memory_text(project_id)

        # 7. 结构化记忆（角色状态/伏笔/因果链）
        ctx.structured_memory = await self._get_structured_memory(
            project_id=project_id,
            chapter_number=chapter_number,
            involved_characters=ctx.introduced_characters,
        )

        # 8. RAG 检索
        if config.enable_rag:
            if config.rag_mode == "two_stage":
                ctx.knowledge_context, ctx.rag_stats = await self._get_two_stage_rag_context(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    writing_notes=writing_notes,
                    pov_character=self._resolve_pov_character(ctx.chapter_mission),
                    user_id=user_id,
                )
            else:
                ctx.rag_context = await self._get_rag_context(
                    project_id=project_id,
                    outline_title=outline_title,
                    outline_summary=outline_summary,
                    writing_notes=writing_notes,
                    user_id=user_id,
                )
                ctx.rag_stats = {
                    "mode": "simple",
                    "chunks": len(ctx.rag_context.get("chunks", [])) if ctx.rag_context else 0,
                    "summaries": len(ctx.rag_context.get("summaries", [])) if ctx.rag_context else 0,
                }

        # 9. 组装 Prompt
        ctx.prompt_sections = self._build_prompt_sections(
            writer_blueprint=ctx.writer_blueprint,
            previous_summary=ctx.history["previous_summary"],
            previous_tail=ctx.history["previous_tail"],
            chapter_mission=ctx.chapter_mission,
            rag_context=ctx.rag_context,
            knowledge_context=ctx.knowledge_context,
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            forbidden_characters=ctx.forbidden_characters,
            project_memory_text=ctx.project_memory_text,
            memory_context=ctx.memory_context,
            structured_memory=ctx.structured_memory,
            character_profiles=ctx.character_profiles,
        )

        # 10. Enhanced 增强 Prompt（套壳宪法/Persona 注入）
        if ctx.enhanced_context:
            from .enhanced_writing_flow import EnhancedWritingFlow
            enhanced_flow = EnhancedWritingFlow(self.session, self.llm_service, self.prompt_service)
            ctx.prompt_sections = enhanced_flow.build_enhanced_prompt_sections(
                ctx.prompt_sections, ctx.enhanced_context
            )

        ctx.prompt_input = "\n\n".join(
            f"{title}\n{content}" for title, content in ctx.prompt_sections if content
        )

        # 11. 风格提示（多版本差异化）
        ctx.version_style_hints = self._resolve_style_hints(
            ctx.enhanced_context, config.version_count
        )

        return ctx

    # ---- 历史章节收集 ----

    async def _collect_history_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outlines_map: Dict[int, Any],
        chapters: List[Any],
        user_id: int,
    ) -> Dict[str, Any]:
        completed_summaries: List[str] = []
        completed_chapters: List[Dict[str, Any]] = []
        latest_prev_number = -1
        previous_summary_text = ""
        previous_tail_excerpt = ""

        for existing in chapters:
            if existing.chapter_number >= chapter_number:
                continue
            if existing.selected_version is None or not existing.selected_version.content:
                continue
            if not existing.real_summary:
                summary = await self.llm_service.get_summary(
                    existing.selected_version.content,
                    temperature=0.15,
                    user_id=user_id,
                    timeout=180.0,
                )
                existing.real_summary = remove_think_tags(summary)
                await self.session.commit()

            completed_chapters.append({
                "chapter_number": existing.chapter_number,
                "title": (
                    outlines_map[existing.chapter_number].title
                    if outlines_map.get(existing.chapter_number)
                    else f"第{existing.chapter_number}章"
                ),
                "summary": existing.real_summary,
            })
            completed_summaries.append(existing.real_summary or "")

            if existing.chapter_number > latest_prev_number:
                latest_prev_number = existing.chapter_number
                previous_summary_text = existing.real_summary or ""
                previous_tail_excerpt = _extract_tail_excerpt(existing.selected_version.content)

        return {
            "completed_chapters": completed_chapters,
            "completed_summaries": completed_summaries,
            "previous_summary": previous_summary_text or "暂无（这是第一章）",
            "previous_tail": previous_tail_excerpt or "暂无（这是第一章）",
        }

    # ---- 导演脚本生成 ----

    async def _generate_chapter_mission(
        self,
        *,
        blueprint_dict: Dict[str, Any],
        previous_summary: str,
        previous_tail: str,
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        introduced_characters: List[str],
        all_characters: List[str],
        user_id: int,
    ) -> Optional[dict]:
        plan_prompt = await self.prompt_service.get_prompt("chapter_plan")
        if not plan_prompt:
            logger.warning("未配置 chapter_plan 提示词，跳过导演脚本生成")
            return None

        plan_input = f"""
[上一章摘要]
{previous_summary}

[上一章结尾]
{previous_tail}

[当前章节大纲]
标题：{outline_title}
摘要：{outline_summary}

[已登场角色]
{json.dumps(introduced_characters, ensure_ascii=False) if introduced_characters else "暂无"}

[全部角色]
{json.dumps(all_characters, ensure_ascii=False)}

[写作指令]
{writing_notes}
"""
        try:
            response = await self.llm_service.get_llm_response(
                system_prompt=plan_prompt,
                conversation_history=[{"role": "user", "content": plan_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=120.0,
            )
            cleaned = remove_think_tags(response)
            normalized = unwrap_markdown_json(cleaned)
            mission = json.loads(normalized)
            logger.info("章节导演脚本生成完成: macro_beat=%s", mission.get("macro_beat"))
            return mission
        except Exception as exc:
            logger.warning("生成章节导演脚本失败，将使用默认模式: %s", exc)
            return None

    # ---- RAG 检索 ----

    async def _get_rag_context(
        self,
        *,
        project_id: str,
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        user_id: int,
    ) -> Dict[str, Any]:
        if not settings.vector_store_enabled:
            return {"chunks": [], "summaries": []}

        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过 RAG: %s", exc)
            return {"chunks": [], "summaries": []}

        compat = await _check_embedding_compatibility(vector_store, self.llm_service)
        if not compat["compatible"]:
            logger.warning(
                "嵌入模型已变更（%s → %s），RAG 检索结果可能不准确，建议重建向量库",
                compat.get("stored_model"),
                compat.get("current_model"),
            )

        query_parts = [outline_title, outline_summary]
        if writing_notes:
            query_parts.append(writing_notes)
        rag_query = "\n".join(part for part in query_parts if part)

        context_service = ChapterContextService(llm_service=self.llm_service, vector_store=vector_store)
        rag_context = await context_service.retrieve_for_generation(
            project_id=project_id,
            query_text=rag_query or outline_title or outline_summary,
            user_id=user_id,
        )
        return {
            "chunks": rag_context.chunk_texts() if rag_context.chunks else [],
            "summaries": rag_context.summary_lines() if rag_context.summaries else [],
        }

    async def _get_two_stage_rag_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        writing_notes: str,
        pov_character: Optional[str],
        user_id: int,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        if not settings.vector_store_enabled:
            return None, {"mode": "two_stage", "enabled": False}

        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过两层 RAG: %s", exc)
            return None, {"mode": "two_stage", "enabled": False, "error": str(exc)}

        retrieval_service = KnowledgeRetrievalService(self.session, self.llm_service, vector_store)
        filtered = await retrieval_service.retrieve_and_filter(
            project_id=project_id,
            chapter_number=chapter_number,
            user_id=user_id,
            pov_character=pov_character,
            user_guidance=writing_notes,
            top_k=settings.vector_top_k_chunks,
        )
        context_text = _format_filtered_context(filtered)
        stats = filtered.stats or {}
        stats["mode"] = "two_stage"
        return context_text, stats

    # ---- 记忆上下文 ----

    async def _get_memory_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        involved_characters: List[str],
    ) -> str:
        memory_layer = MemoryLayerService(self.session, self.llm_service, self.prompt_service)
        return await memory_layer.get_memory_context(project_id, chapter_number, involved_characters)

    async def _get_project_memory_text(self, project_id: str) -> Optional[str]:
        result = await self.session.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        )
        memory = result.scalars().first()
        if not memory:
            return None
        parts = []
        if memory.global_summary:
            parts.append(f"## 前文全局摘要\n\n{memory.global_summary}")
        return "\n\n".join(parts) if parts else None

    async def _get_structured_memory(
        self,
        *,
        project_id: str,
        chapter_number: int,
        involved_characters: List[str],
    ) -> Optional[str]:
        sections: List[str] = []

        # 角色当前状态
        raw_state = await self._get_raw_state_text(project_id)
        if raw_state:
            sections.append("## 角色当前状态\n\n" + raw_state)
        else:
            character_states = await self._query_latest_character_states(project_id, chapter_number - 1)
            if character_states:
                lines = []
                for state in character_states:
                    if involved_characters and state.character_name not in involved_characters:
                        continue
                    parts = [f"### {state.character_name}"]
                    if state.location:
                        parts.append(f"- 位置：{state.location}")
                    if state.emotion:
                        parts.append(f"- 情绪：{state.emotion}（强度 {state.emotion_intensity}/10）")
                    if state.health_status and state.health_status != "healthy":
                        parts.append(f"- 健康：{state.health_status}")
                    if state.known_secrets:
                        parts.append(f"- 已知秘密：{', '.join(state.known_secrets[:3])}")
                    if state.current_goals:
                        parts.append(f"- 当前目标：{', '.join(state.current_goals[:3])}")
                    if len(parts) > 1:
                        lines.append("\n".join(parts))
                if lines:
                    sections.append("## 角色当前状态\n\n" + "\n\n".join(lines))

        # 活跃伏笔
        foreshadowings = await self._query_active_foreshadowings(project_id, chapter_number)
        if foreshadowings:
            lines = []
            for fs in foreshadowings:
                label = f"第{fs.chapter_number}章埋设"
                if fs.target_reveal_chapter:
                    label += f"，计划第{fs.target_reveal_chapter}章回收"
                urgency_tag = ""
                if fs.target_reveal_chapter:
                    diff = fs.target_reveal_chapter - chapter_number
                    if diff < 0:
                        urgency_tag = " [已超期]"
                    elif diff <= 3:
                        urgency_tag = " [即将到期]"
                lines.append(f"- {fs.content[:100]}（{label}）{urgency_tag}")
            if lines:
                sections.append("## 活跃伏笔\n\n" + "\n".join(lines))

        # 待解决因果链
        causal_chains = await self._query_pending_causal_chains(project_id)
        if causal_chains:
            lines = []
            for chain in causal_chains[:5]:
                chars = ""
                if chain.involved_characters:
                    chars = f" [涉及：{', '.join(chain.involved_characters[:3])}]"
                lines.append(
                    f"- 第{chain.cause_chapter}章：{chain.cause_description} → "
                    f"待兑现：{chain.effect_description}{chars}"
                )
            if lines:
                sections.append("## 待解决因果链\n\n" + "\n".join(lines))

        return "\n\n".join(sections) if sections else None

    async def _get_raw_state_text(self, project_id: str) -> Optional[str]:
        result = await self.session.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        )
        memory = result.scalars().first()
        if memory and memory.extra:
            text = memory.extra.get("raw_state_text")
            if text:
                return text
        return None

    async def _query_latest_character_states(self, project_id: str, chapter_number: int) -> list:
        max_chapter_subq = (
            select(
                CharacterState.character_name.label("character_name"),
                func.max(CharacterState.chapter_number).label("max_chapter"),
            )
            .where(
                and_(
                    CharacterState.project_id == project_id,
                    CharacterState.chapter_number <= chapter_number,
                )
            )
            .group_by(CharacterState.character_name)
            .subquery()
        )

        max_id_subq = (
            select(
                CharacterState.character_name.label("character_name"),
                CharacterState.chapter_number.label("chapter_number"),
                func.max(CharacterState.id).label("max_id"),
            )
            .join(
                max_chapter_subq,
                and_(
                    CharacterState.character_name == max_chapter_subq.c.character_name,
                    CharacterState.chapter_number == max_chapter_subq.c.max_chapter,
                ),
            )
            .where(CharacterState.project_id == project_id)
            .group_by(CharacterState.character_name, CharacterState.chapter_number)
            .subquery()
        )

        query = (
            select(CharacterState)
            .join(max_id_subq, CharacterState.id == max_id_subq.c.max_id)
            .where(CharacterState.project_id == project_id)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def _query_active_foreshadowings(self, project_id: str, chapter_number: int) -> list:
        query = (
            select(Foreshadowing)
            .where(
                and_(
                    Foreshadowing.project_id == project_id,
                    Foreshadowing.status.in_(["planted", "developing", "partial"]),
                )
            )
            .order_by(Foreshadowing.chapter_number)
        )
        result = await self.session.execute(query)
        all_active = list(result.scalars().all())

        overdue, due_soon, urgent, rest = [], [], [], []
        for fs in all_active:
            if fs.urgency and fs.urgency >= 8:
                urgent.append(fs)
            elif fs.target_reveal_chapter:
                diff = fs.target_reveal_chapter - chapter_number
                if diff < 0:
                    overdue.append(fs)
                elif diff <= 3:
                    due_soon.append(fs)
                else:
                    rest.append(fs)
            elif (chapter_number - fs.chapter_number) >= 20:
                overdue.append(fs)
            else:
                rest.append(fs)

        return (overdue + due_soon + urgent + rest)[:10]

    async def _query_pending_causal_chains(self, project_id: str) -> list:
        result = await self.session.execute(
            select(CausalChain)
            .where(
                and_(
                    CausalChain.project_id == project_id,
                    CausalChain.status == "pending",
                )
            )
            .order_by(CausalChain.cause_chapter)
        )
        return list(result.scalars().all())

    # ---- Prompt 组装 ----

    @staticmethod
    def _build_prompt_sections(
        *,
        writer_blueprint: Dict[str, Any],
        previous_summary: str,
        previous_tail: str,
        chapter_mission: Optional[dict],
        rag_context: Optional[Dict[str, Any]],
        knowledge_context: Optional[str],
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        forbidden_characters: List[str],
        project_memory_text: Optional[str],
        memory_context: Optional[str],
        structured_memory: Optional[str],
        character_profiles: str,
    ) -> List[Tuple[str, str]]:
        sections: List[Tuple[str, str]] = []

        sections.append(("蓝图 / 写作上下文", json.dumps(writer_blueprint, ensure_ascii=False, indent=2)))

        if character_profiles:
            sections.append(("## 角色心理档案", character_profiles))

        sections.append(("## 上一章摘要", previous_summary))
        sections.append(("## 上一章结尾（续写起点）", previous_tail))

        if chapter_mission:
            sections.append(("## 本章导演脚本 (ChapterMission)", json.dumps(chapter_mission, ensure_ascii=False, indent=2)))

        if rag_context:
            chunks = rag_context.get("chunks", [])
            summaries = rag_context.get("summaries", [])
            if chunks:
                sections.append(("## 相关剧情片段 (RAG)", "\n\n".join(chunks)))
            if summaries:
                sections.append(("## 相关章节摘要", "\n".join(summaries)))

        if knowledge_context:
            sections.append(("## 过滤后的世界知识 (Two-Stage RAG)", knowledge_context))

        sections.append(("## 本章大纲", f"标题：{outline_title}\n摘要：{outline_summary}"))
        sections.append(("## 用户写作指令", writing_notes))

        if forbidden_characters:
            sections.append(("## 禁止出现角色", "、".join(forbidden_characters)))

        if project_memory_text:
            sections.append(("## 项目记忆", project_memory_text))

        if memory_context:
            sections.append(
                ("## 记忆层上下文",
                 memory_context if isinstance(memory_context, str) else str(memory_context))
            )

        if structured_memory:
            sections.append(("## 结构化记忆（角色状态/伏笔/因果链）", structured_memory))

        return sections

    # ---- 风格提示 / POV ----

    @staticmethod
    def _resolve_style_hints(
        enhanced_context: Optional[Dict[str, Any]], version_count: int
    ) -> List[Optional[str]]:
        if not enhanced_context:
            return [None] * version_count

        styles = []
        persona = enhanced_context.get("persona")
        if persona:
            styles = persona.get("style_hints", []) if isinstance(persona, dict) else []

        if not styles:
            return [None] * version_count

        # 循环分配风格提示到各版本
        hints: List[Optional[str]] = []
        for i in range(version_count):
            hints.append(styles[i % len(styles)] if styles else None)
        return hints

    @staticmethod
    def _resolve_pov_character(chapter_mission: Optional[dict]) -> Optional[str]:
        if not chapter_mission:
            return None
        return chapter_mission.get("pov_character") or chapter_mission.get("pov")


# ---------------------------------------------------------------------------
# 模块级工具（从 PipelineOrchestrator 提取的静态方法）
# ---------------------------------------------------------------------------

def _extract_tail_excerpt(text: Optional[str], limit: int = 1500) -> str:
    if not text:
        return ""
    stripped = text.strip()
    return stripped[-limit:] if len(stripped) > limit else stripped


def _normalize_blueprint(blueprint_dict: Dict[str, Any]) -> Dict[str, Any]:
    if "relationships" in blueprint_dict and blueprint_dict["relationships"]:
        for relation in blueprint_dict["relationships"]:
            if "character_from" in relation:
                relation["from"] = relation.pop("character_from")
            if "character_to" in relation:
                relation["to"] = relation.pop("character_to")
    return blueprint_dict


async def _check_embedding_compatibility(
    vector_store: VectorStoreService,
    llm_service: LLMService,
) -> Dict[str, Any]:
    try:
        current_model = await llm_service.get_embedding_model_name()
        current_dimension = await llm_service.get_embedding_dimension(current_model)
        if not current_dimension:
            current_dimension = 0

        return await vector_store.check_model_compatibility(
            current_model,
            current_dimension,
        )
    except Exception as exc:
        logger.warning("嵌入模型兼容性检查失败: %s", exc)
        return {"compatible": True, "checked": False, "error": str(exc)}


def _format_filtered_context(filtered: FilteredContext) -> Optional[str]:
    sections: List[str] = []
    if filtered.plot_fuel:
        sections.append("## 情节燃料\n" + "\n".join(f"- {item}" for item in filtered.plot_fuel))
    if filtered.character_info:
        sections.append("## 人物信息\n" + "\n".join(f"- {item}" for item in filtered.character_info))
    if filtered.world_fragments:
        sections.append("## 世界碎片\n" + "\n".join(f"- {item}" for item in filtered.world_fragments))
    if filtered.narrative_techniques:
        sections.append("## 叙事技法\n" + "\n".join(f"- {item}" for item in filtered.narrative_techniques))
    return "\n\n".join(sections) if sections else None
