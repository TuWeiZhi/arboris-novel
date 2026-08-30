# AIMETA P=写作流水线编排_统一生成入口|R=编排_生成_审查_优化|NR=上下文收集已提取至ChapterContextAssembler|E=PipelineOrchestrator|X=internal|A=编排器|D=fastapi,sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.foreshadowing import Foreshadowing
from ..repositories.system_config_repository import SystemConfigRepository
from ..services.ai_review_service import AIReviewService
from ..services.chapter_context_assembler import (
    AssembledChapterContext,
    ChapterContextAssembler,
    _normalize_blueprint,
)
from ..services.chapter_guardrails import ChapterGuardrails
from ..services.consistency_service import ConsistencyService, ViolationSeverity
from ..services.enhanced_writing_flow import EnhancedWritingFlow
from ..services.enrichment_service import EnrichmentService
from ..services.llm_service import LLMService
from ..services.novel_service import NovelService
from ..services.preview_generation_service import PreviewGenerationService
from ..services.prompt_service import PromptService
from ..services.reader_simulator_service import ReaderSimulatorService, ReaderType
from ..services.self_critique_service import CritiqueDimension, SelfCritiqueService
from ..services.writer_context_builder import WriterContextBuilder
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    preset: str = "basic"
    version_count: int = 2
    enable_preview: bool = False
    enable_optimizer: bool = False
    enable_consistency: bool = False
    enable_enrichment: bool = False
    async_finalize: bool = False
    enable_constitution: bool = False
    enable_persona: bool = False
    enable_six_dimension: bool = False
    enable_reader_sim: bool = False
    enable_self_critique: bool = False
    enable_memory: bool = False
    enable_rag: bool = True
    rag_mode: str = "simple"
    enable_foreshadowing: bool = False
    enable_faction: bool = False


class PipelineOrchestrator:
    """统一写作流水线编排器。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_service = LLMService(session)
        self.prompt_service = PromptService(session)
        self.novel_service = NovelService(session)
        self.context_builder = WriterContextBuilder()
        self.guardrails = ChapterGuardrails()

    async def generate_chapter(
        self,
        *,
        project_id: str,
        chapter_number: int,
        user_id: int,
        writing_notes: Optional[str] = None,
        flow_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """统一章节生成入口。"""
        config = await self._resolve_config(flow_config)
        project = await self.novel_service.ensure_project_owner(project_id, user_id)

        outline = await self.novel_service.get_outline(project_id, chapter_number)
        if not outline:
            raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

        chapter = await self.novel_service.get_or_create_chapter(project_id, chapter_number)
        chapter.real_summary = None
        chapter.selected_version_id = None
        chapter.status = "generating"
        await self.session.commit()

        outlines_map = {item.chapter_number: item for item in project.outlines}
        project_schema = await self.novel_service._serialize_project(project)
        blueprint_dict = _normalize_blueprint(project_schema.blueprint.model_dump())

        outline_title = outline.title or f"第{outline.chapter_number}章"
        outline_summary = outline.summary or "暂无摘要"
        writing_notes = writing_notes or "无额外写作指令"

        all_characters = [
            c.get("name") for c in blueprint_dict.get("characters", []) if c.get("name")
        ]

        # 先构建可视化上下文（需要导演脚本的 allowed_new_characters，后补）
        pilot_visibility = self.context_builder.build_visibility_context(
            blueprint=blueprint_dict,
            completed_summaries=[],
            previous_tail="",
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            allowed_new_characters=[],
        )

        # ---- 一站式上下文收集 ----
        assembler = ChapterContextAssembler(self.session, self.llm_service, self.prompt_service)
        ctx = await assembler.assemble(
            project_id=project_id,
            chapter_number=chapter_number,
            user_id=user_id,
            writing_notes=writing_notes,
            outlines_map=outlines_map,
            chapters=project.chapters,
            blueprint_dict=blueprint_dict,
            project_schema=project_schema,
            outline_title=outline_title,
            outline_summary=outline_summary,
            config=config,
            visibility_context=pilot_visibility,
            chapter_mission_inputs={
                "introduced_characters": [],
                "all_characters": all_characters,
            },
        )

        logger.info(
            "Pipeline context: project=%s chapter=%s introduced=%d allowed_new=%d forbidden=%d",
            project_id, chapter_number,
            len(ctx.introduced_characters),
            len(ctx.allowed_new_characters),
            len(ctx.forbidden_characters),
        )

        # ---- 获取写作提示词 ----
        writer_prompt = await self.prompt_service.get_prompt("writing_v2")
        if not writer_prompt:
            writer_prompt = await self.prompt_service.get_prompt("writing")
        if not writer_prompt:
            raise HTTPException(status_code=500, detail="缺少写作提示词，请联系管理员配置")

        logger.debug("Pipeline prompt length: %s chars", len(ctx.prompt_input))

        # ---- 多版本并发生成 ----
        _gen_sem = asyncio.Semaphore(min(config.version_count, 3))

        async def _gen_one(idx: int) -> Dict[str, Any]:
            style_hint = ctx.version_style_hints[idx] if idx < len(ctx.version_style_hints) else None
            async with _gen_sem:
                return await self._generate_single_version(
                    index=idx,
                    prompt_input=ctx.prompt_input,
                    writer_prompt=writer_prompt,
                    style_hint=style_hint,
                    project_id=project_id,
                    chapter_number=chapter_number,
                    outline_title=outline_title,
                    outline_summary=outline_summary,
                    chapter_mission=ctx.chapter_mission,
                    forbidden_characters=ctx.forbidden_characters,
                    allowed_new_characters=ctx.allowed_new_characters,
                    user_id=user_id,
                    writer_blueprint=ctx.writer_blueprint,
                    memory_context=ctx.memory_context,
                    enhanced_context=ctx.enhanced_context,
                    config=config,
                )

        versions: List[Dict[str, Any]] = await asyncio.gather(
            *(_gen_one(i) for i in range(config.version_count))
        )
        # Remove None entries for robustness (shouldn't happen in normal flow)
        versions = [v for v in versions if v is not None]

        # ---- AI 评审 ----
        best_version_index, ai_review_result = await self._run_ai_review(
            versions=versions, chapter_mission=ctx.chapter_mission, user_id=user_id,
        )

        review_summaries: Dict[str, Any] = {}
        if ai_review_result:
            review_summaries["ai_review"] = ai_review_result

        if versions:
            best_version_index = max(0, min(best_version_index, len(versions) - 1))
        else:
            best_version_index = 0

        # ---- 后处理流水线 ----
        if versions:
            best_version = versions[best_version_index]
            best_content = best_version["content"]

            if ctx.enhanced_context and config.enable_six_dimension:
                enhanced_flow = EnhancedWritingFlow(self.session, self.llm_service, self.prompt_service)
                review_summaries["enhanced_review"] = await enhanced_flow.post_generation_review(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    chapter_title=outline_title,
                    chapter_content=best_content,
                    chapter_plan=json.dumps(ctx.chapter_mission, ensure_ascii=False) if ctx.chapter_mission else None,
                    previous_summary=ctx.history["previous_summary"],
                )

            if config.enable_self_critique:
                best_content, critique_summary = await self._run_self_critique(
                    best_content, user_id=user_id,
                    context={
                        "character_profiles": json.dumps(ctx.writer_blueprint.get("characters", []), ensure_ascii=False),
                        "previous_summary": ctx.history["previous_summary"],
                    },
                )
                review_summaries["self_critique"] = critique_summary

            if config.enable_reader_sim:
                review_summaries["reader_simulator"] = await self._run_reader_simulation(
                    best_content, chapter_number=chapter_number,
                    previous_summary=ctx.history["previous_summary"], user_id=user_id,
                )

            if config.enable_consistency:
                best_content, consistency_report = await self._run_consistency_check(
                    project_id=project_id,
                    chapter_text=best_content,
                    user_id=user_id,
                    chapter_number=chapter_number,
                )
                review_summaries["consistency"] = consistency_report

            if config.enable_optimizer:
                best_content, optimizer_report = await self._run_optimizer(best_content, user_id=user_id)
                review_summaries["optimizer"] = optimizer_report

            if config.enable_enrichment:
                best_content, enrichment_report = await self._run_enrichment(best_content, user_id=user_id)
                if enrichment_report:
                    review_summaries["enrichment"] = enrichment_report

            best_version["content"] = best_content
            best_version.setdefault("metadata", {})["review_summaries"] = review_summaries

        # 伏笔一致性后置检查
        if versions and config.enable_foreshadowing:
            best_content = versions[best_version_index].get("content", "")
            foreshadowing_check = await self._check_foreshadowing_consistency(
                project_id=project_id, chapter_number=chapter_number, chapter_content=best_content,
            )
            if foreshadowing_check:
                review_summaries["foreshadowing_check"] = foreshadowing_check
                if foreshadowing_check.get("unexpected_resolutions"):
                    logger.warning(
                        "伏笔一致性警告: 章节 %s 意外回收了 %d 个伏笔",
                        chapter_number, len(foreshadowing_check["unexpected_resolutions"]),
                    )

        # ---- 持久化版本 ----
        contents = [v.get("content", "") for v in versions]
        metadata = [v.get("metadata") for v in versions]
        versions_models = await self.novel_service.replace_chapter_versions(chapter, contents, metadata)

        variants = []
        for idx, version_model in enumerate(versions_models):
            variants.append({
                "index": idx,
                "version_id": version_model.id,
                "content": versions[idx].get("content", ""),
                "metadata": versions[idx].get("metadata"),
            })

        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "preset": config.preset,
            "best_version_index": best_version_index,
            "variants": variants,
            "review_summaries": review_summaries,
            "debug_metadata": {
                "version_count": config.version_count,
                "stages": self._build_stage_flags(config),
                "retrieval_stats": ctx.rag_stats,
            },
        }

    async def _resolve_config(self, flow_config: Optional[Dict[str, Any]]) -> PipelineConfig:
        flow_config = flow_config or {}
        preset = flow_config.get("preset", "basic")

        config = PipelineConfig(preset=preset)
        config.version_count = await self._resolve_version_count(flow_config.get("versions"))

        if preset in ("enhanced", "ultimate"):
            config.enable_constitution = True
            config.enable_persona = True
            config.enable_foreshadowing = True
            config.enable_faction = True
            config.rag_mode = "two_stage"

        if preset == "enhanced":
            config.enable_six_dimension = True

        if preset == "ultimate":
            config.enable_memory = True

        if preset == "basic":
            config.enable_rag = True

        for key in (
            "enable_preview",
            "enable_optimizer",
            "enable_consistency",
            "enable_enrichment",
            "async_finalize",
            "enable_rag",
        ):
            if key in flow_config and flow_config[key] is not None:
                setattr(config, key, bool(flow_config[key]))

        if flow_config.get("rag_mode"):
            config.rag_mode = str(flow_config["rag_mode"])

        if preset == "ultimate":
            config.enable_preview = False
            config.enable_optimizer = False
            config.enable_consistency = False
            config.enable_enrichment = False
            config.enable_six_dimension = False
            config.enable_reader_sim = False
            config.enable_self_critique = False

        return config

    async def _resolve_version_count(self, requested_count: Optional[int]) -> int:
        if requested_count:
            try:
                count = int(requested_count)
                return max(1, count)
            except (TypeError, ValueError):
                pass

        repo = SystemConfigRepository(self.session)
        for key in ("writer.chapter_versions", "writer.version_count"):
            record = await repo.get_by_key(key)
            if record and record.value:
                try:
                    val = int(record.value)
                    if val >= 1:
                        return val
                except ValueError:
                    pass

        for env in ("WRITER_CHAPTER_VERSION_COUNT", "WRITER_CHAPTER_VERSIONS", "WRITER_VERSION_COUNT"):
            v = os.getenv(env)
            if v:
                try:
                    val = int(v)
                    if val >= 1:
                        return val
                except ValueError:
                    pass

        return int(settings.writer_chapter_versions)

    # ── 上下文收集已提取至 ChapterContextAssembler ──

    async def _generate_single_version(
        self,
        *,
        index: int,
        prompt_input: str,
        writer_prompt: str,
        style_hint: Optional[str],
        project_id: str,
        chapter_number: int,
        outline_title: str,
        outline_summary: str,
        chapter_mission: Optional[dict],
        forbidden_characters: List[str],
        allowed_new_characters: List[str],
        user_id: int,
        writer_blueprint: Dict[str, Any],
        memory_context: Optional[str],
        enhanced_context: Optional[Dict[str, Any]],
        config: PipelineConfig,
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "chapter_mission": chapter_mission,
            "style_hint": style_hint,
            "pipeline": {"preset": config.preset},
        }

        content = ""
        if config.enable_preview:
            content, preview_meta = await self._generate_with_preview(
                project_id=project_id,
                chapter_number=chapter_number,
                outline_title=outline_title,
                outline_summary=outline_summary,
                writer_blueprint=writer_blueprint,
                memory_context=memory_context,
                style_hint=style_hint,
                enhanced_context=enhanced_context,
                user_id=user_id,
            )
            metadata["preview"] = preview_meta

        if not content:
            final_prompt_input = prompt_input
            if style_hint:
                final_prompt_input += f"\n\n[版本风格提示]\n{style_hint}"

            response = await self.llm_service.get_llm_response(
                system_prompt=writer_prompt,
                conversation_history=[{"role": "user", "content": final_prompt_input}],
                temperature=0.9,
                user_id=user_id,
                timeout=600.0,
                response_format=None,
            )
            cleaned = remove_think_tags(response)
            content = unwrap_markdown_json(cleaned)

        guardrail_result = self.guardrails.check(
            generated_text=content,
            forbidden_characters=forbidden_characters,
            allowed_new_characters=allowed_new_characters,
            pov=chapter_mission.get("pov") if chapter_mission else None,
        )
        guardrail_metadata = {"passed": guardrail_result.passed, "violations": [], "retry_count": 0}

        if not guardrail_result.passed:
            guardrail_metadata["violations"] = [
                {"type": v.type, "severity": v.severity, "description": v.description}
                for v in guardrail_result.violations
            ]
            # 自动返工机制：最多重试 3 次
            max_retries = 3
            for retry in range(max_retries):
                violations_text = self.guardrails.format_violations_for_rewrite(guardrail_result)
                content = await self._rewrite_with_guardrails(
                    original_text=content,
                    chapter_mission=chapter_mission,
                    violations_text=violations_text,
                    user_id=user_id,
                )
                # 重新检查
                guardrail_result = self.guardrails.check(
                    generated_text=content,
                    forbidden_characters=forbidden_characters,
                    allowed_new_characters=allowed_new_characters,
                    pov=chapter_mission.get("pov") if chapter_mission else None,
                )
                if guardrail_result.passed:
                    guardrail_metadata["passed"] = True
                    guardrail_metadata["retry_count"] = retry + 1
                    break
                # 红线违规时额外记录
                if guardrail_result.red_line_triggered:
                    guardrail_metadata["red_line_triggered"] = True
                    guardrail_metadata["violations"] = [
                        {"type": v.type, "severity": v.severity, "description": v.description}
                        for v in guardrail_result.violations
                    ]
            else:
                # 3 次重试后仍未通过
                guardrail_metadata["retry_count"] = max_retries
                guardrail_metadata["auto_fix_failed"] = True
                if guardrail_result.red_line_triggered:
                    guardrail_metadata["red_line_triggered"] = True
                guardrail_metadata["violations"] = [
                    {"type": v.type, "severity": v.severity, "description": v.description}
                    for v in guardrail_result.violations
                ]

        parsed_json = None
        extracted_text = None
        try:
            parsed_json = json.loads(content)
            extracted_text = self._extract_text(parsed_json)
        except Exception:
            parsed_json = None

        metadata["guardrail"] = guardrail_metadata
        if parsed_json is not None:
            metadata["parsed_json"] = parsed_json

        return {
            "index": index,
            "content": extracted_text or content,
            "metadata": metadata,
        }

    async def _generate_with_preview(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outline_title: str,
        outline_summary: str,
        writer_blueprint: Dict[str, Any],
        memory_context: Optional[str],
        style_hint: Optional[str],
        enhanced_context: Optional[Dict[str, Any]],
        user_id: int,
    ) -> Tuple[str, Dict[str, Any]]:
        preview_service = PreviewGenerationService(self.session, self.llm_service, self.prompt_service)
        blueprint_context = json.dumps(writer_blueprint, ensure_ascii=False, indent=2)

        extra_constraints = []
        if enhanced_context:
            if enhanced_context.get("constitution"):
                extra_constraints.append(enhanced_context["constitution"])
            if enhanced_context.get("writer_persona"):
                extra_constraints.append(enhanced_context["writer_persona"])

        if extra_constraints:
            blueprint_context = blueprint_context + "\n\n" + "\n\n".join(extra_constraints)

        preview_result = await preview_service.generate_with_preview(
            project_id=project_id,
            chapter_number=chapter_number,
            outline={"title": outline_title, "summary": outline_summary},
            blueprint_context=blueprint_context,
            emotion_context="（无情绪曲线指导）",
            memory_context=memory_context or "（无记忆层上下文）",
            style_hint=style_hint or "",
            user_id=user_id,
        )

        return preview_result.get("full_chapter", ""), preview_result

    async def _rewrite_with_guardrails(
        self,
        *,
        original_text: str,
        chapter_mission: Optional[dict],
        violations_text: str,
        user_id: int,
    ) -> str:
        rewrite_prompt = await self.prompt_service.get_prompt("rewrite_guardrails")
        if not rewrite_prompt:
            logger.warning("未配置 rewrite_guardrails 提示词，跳过自动修复")
            return original_text

        rewrite_input = f"""
[原文]
{original_text}

[章节导演脚本]
{json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无"}

[违规列表]
{violations_text}
"""

        try:
            response = await self.llm_service.get_llm_response(
                system_prompt=rewrite_prompt,
                conversation_history=[{"role": "user", "content": rewrite_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=300.0,
                response_format=None,
            )
            cleaned = remove_think_tags(response)
            return cleaned
        except Exception as exc:
            logger.warning("自动修复失败，返回原文: %s", exc)
            return original_text

    @staticmethod
    def _extract_text(value: object) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("content", "chapter_content", "chapter_text", "text", "body", "story"):
                if value.get(key):
                    nested = PipelineOrchestrator._extract_text(value.get(key))
                    if nested:
                        return nested
            return None
        if isinstance(value, list):
            for item in value:
                nested = PipelineOrchestrator._extract_text(item)
                if nested:
                    return nested
        return None

    async def _run_ai_review(
        self,
        *,
        versions: List[Dict[str, Any]],
        chapter_mission: Optional[dict],
        user_id: int,
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        if len(versions) <= 1:
            return 0, None

        contents = [v.get("content", "") for v in versions]
        try:
            ai_review_service = AIReviewService(self.llm_service, self.prompt_service)
            ai_review_result = await ai_review_service.review_versions(
                versions=contents,
                chapter_mission=chapter_mission,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("AI 评审失败，跳过: %s", exc)
            return 0, None

        if not ai_review_result:
            return 0, None

        for idx, variant in enumerate(versions):
            variant.setdefault("metadata", {})["ai_review"] = {
                "is_best": idx == ai_review_result.best_version_index,
                "scores": ai_review_result.scores,
                "evaluation": ai_review_result.overall_evaluation if idx == ai_review_result.best_version_index else None,
                "flaws": ai_review_result.critical_flaws if idx == ai_review_result.best_version_index else None,
                "suggestions": ai_review_result.refinement_suggestions if idx == ai_review_result.best_version_index else None,
            }

        # LLM 发现的红线违规记录到元数据
        llm_red_lines = ai_review_result.red_line_violations or []

        return ai_review_result.best_version_index, {
            "best_version_index": ai_review_result.best_version_index,
            "scores": ai_review_result.scores,
            "evaluation": ai_review_result.overall_evaluation,
            "flaws": ai_review_result.critical_flaws,
            "suggestions": ai_review_result.refinement_suggestions,
            "anti_ai_score": ai_review_result.scores.get("anti_ai"),
            "llm_red_line_violations": llm_red_lines,
        }

    async def _run_self_critique(
        self,
        chapter_content: str,
        *,
        user_id: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        service = SelfCritiqueService(self.session, self.llm_service, self.prompt_service)
        critique = await service.critique_and_revise_loop(
            chapter_content=chapter_content,
            max_iterations=1,
            target_score=75.0,
            dimensions=[
                CritiqueDimension.LOGIC,
                CritiqueDimension.CHARACTER,
                CritiqueDimension.WRITING,
            ],
            context=context,
            user_id=user_id,
        )
        return critique.get("final_content", chapter_content), {
            "iterations": len(critique.get("iterations", [])),
            "final_score": critique.get("final_score", 0),
            "improvement": critique.get("improvement", 0),
            "status": critique.get("status", "unknown"),
        }

    async def _run_reader_simulation(
        self,
        chapter_content: str,
        *,
        chapter_number: int,
        previous_summary: Optional[str],
        user_id: int,
    ) -> Dict[str, Any]:
        service = ReaderSimulatorService(self.session, self.llm_service, self.prompt_service)
        return await service.simulate_reading_experience(
            chapter_content=chapter_content,
            chapter_number=chapter_number,
            reader_types=[ReaderType.THRILL_SEEKER, ReaderType.CRITIC, ReaderType.CASUAL],
            previous_summary=previous_summary,
            user_id=user_id,
        )

    async def _run_consistency_check(
        self,
        *,
        project_id: str,
        chapter_text: str,
        user_id: int,
        chapter_number: Optional[int] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        service = ConsistencyService(self.session, self.llm_service)
        result = await service.check_consistency(
            project_id, chapter_text, user_id, include_foreshadowing=True, chapter_number=chapter_number
        )
        report = {
            "is_consistent": result.is_consistent,
            "summary": result.summary,
            "check_time_ms": result.check_time_ms,
            "violations": [
                {
                    "severity": v.severity.value if hasattr(v.severity, "value") else v.severity,
                    "category": v.category,
                    "description": v.description,
                    "location": v.location,
                    "suggested_fix": v.suggested_fix,
                    "confidence": v.confidence,
                }
                for v in result.violations
            ],
        }

        needs_fix = any(
            v.severity in (ViolationSeverity.CRITICAL, ViolationSeverity.MAJOR)
            for v in result.violations
        )
        if needs_fix:
            fixed = await service.auto_fix(project_id, chapter_text, result.violations, user_id)
            if fixed:
                report["auto_fix_applied"] = True
                return fixed, report

        report["auto_fix_applied"] = False
        return chapter_text, report

    async def _run_optimizer(self, chapter_content: str, *, user_id: int) -> Tuple[str, Dict[str, Any]]:
        prompt_map = {
            "dialogue": "optimize_dialogue",
            "environment": "optimize_environment",
            "psychology": "optimize_psychology",
            "rhythm": "optimize_rhythm",
        }

        optimized_content = chapter_content
        notes = []
        for dimension, prompt_name in prompt_map.items():
            prompt = await self.prompt_service.get_prompt(prompt_name)
            if not prompt:
                logger.warning("缺少优化提示词 %s，跳过 %s 维度", prompt_name, dimension)
                continue

            optimize_input = {
                "original_content": optimized_content,
                "additional_notes": "在不改变剧情走向的前提下优化该维度。",
            }
            try:
                response = await self.llm_service.get_llm_response(
                    system_prompt=prompt,
                    conversation_history=[{"role": "user", "content": json.dumps(optimize_input, ensure_ascii=False)}],
                    temperature=0.7,
                    user_id=user_id,
                    timeout=600.0,
                )
                cleaned = remove_think_tags(response)
                normalized = unwrap_markdown_json(cleaned)
                try:
                    parsed = json.loads(normalized)
                    optimized_content = parsed.get("optimized_content", cleaned)
                    notes.append(
                        {
                            "dimension": dimension,
                            "notes": parsed.get("optimization_notes", "优化完成"),
                        }
                    )
                except json.JSONDecodeError:
                    optimized_content = cleaned
                    notes.append({"dimension": dimension, "notes": "优化完成（响应格式非标准JSON）"})
            except Exception as exc:
                logger.warning("优化维度 %s 失败: %s", dimension, exc)

        return optimized_content, {"steps": notes}

    async def _run_enrichment(
        self,
        chapter_content: str,
        *,
        user_id: int,
        target_word_count: int = 3000,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        service = EnrichmentService(self.llm_service)
        result = await service.check_and_enrich(
            chapter_text=chapter_content,
            target_word_count=target_word_count,
            user_id=user_id,
        )
        if not result:
            return chapter_content, None

        return result.enriched_content, {
            "original_word_count": result.original_word_count,
            "enriched_word_count": result.enriched_word_count,
            "enrichment_ratio": result.enrichment_ratio,
            "enrichment_type": result.enrichment_type,
        }

    async def _check_foreshadowing_consistency(
        self,
        *,
        project_id: str,
        chapter_number: int,
        chapter_content: str,
    ) -> Optional[Dict[str, Any]]:
        """
        伏笔一致性后置检查：
        1. 检查是否有未到期伏笔被意外回收
        2. 检查超期伏笔是否被推进
        3. 生成伏笔台账报告
        """
        result = await self.session.execute(
            select(Foreshadowing).where(
                and_(
                    Foreshadowing.project_id == project_id,
                    Foreshadowing.status.in_(["planted", "developing", "partial"]),
                )
            )
        )
        active_foreshadowings = list(result.scalars().all())
        if not active_foreshadowings:
            return None

        unexpected_resolutions = []
        overdue_addressed = []
        overdue_ignored = []

        for fs in active_foreshadowings:
            content_lower = chapter_content.lower()
            # 简单关键词匹配检测伏笔是否在本章被提及
            fs_keywords = fs.keywords or []
            fs_content = (fs.content or "").lower()
            mentioned = False
            if fs_content and any(kw in content_lower for kw in fs_content[:20].split()):
                mentioned = True
            if fs_keywords and any(kw.lower() in content_lower for kw in fs_keywords if kw):
                mentioned = True

            if not mentioned:
                continue

            # 伏笔被提及
            if fs.target_reveal_chapter and fs.target_reveal_chapter > chapter_number + 3:
                # 未到期的伏笔被提及 — 可能是意外回收
                unexpected_resolutions.append({
                    "foreshadowing_id": fs.id,
                    "content": (fs.content or "")[:80],
                    "planted_chapter": fs.chapter_number,
                    "target_reveal_chapter": fs.target_reveal_chapter,
                })
            elif fs.target_reveal_chapter and fs.target_reveal_chapter <= chapter_number:
                # 超期伏笔被推进 — 正面信号
                overdue_addressed.append({
                    "foreshadowing_id": fs.id,
                    "content": (fs.content or "")[:80],
                    "overdue_by": chapter_number - fs.target_reveal_chapter,
                })

        # 检查超期但未被推进的伏笔
        for fs in active_foreshadowings:
            if fs.target_reveal_chapter and fs.target_reveal_chapter < chapter_number:
                if fs.id not in [a["foreshadowing_id"] for a in overdue_addressed]:
                    overdue_ignored.append({
                        "foreshadowing_id": fs.id,
                        "content": (fs.content or "")[:80],
                        "overdue_by": chapter_number - fs.target_reveal_chapter,
                    })

        report = {
            "total_active": len(active_foreshadowings),
            "unexpected_resolutions": unexpected_resolutions,
            "overdue_addressed": overdue_addressed,
            "overdue_ignored": overdue_ignored[:5],  # 最多报告 5 个
        }

        # 伏笔台账统计
        if active_foreshadowings:
            total = len(active_foreshadowings)
            overdue_count = sum(
                1 for fs in active_foreshadowings
                if fs.target_reveal_chapter and fs.target_reveal_chapter < chapter_number
            )
            due_soon_count = sum(
                1 for fs in active_foreshadowings
                if fs.target_reveal_chapter and 0 <= fs.target_reveal_chapter - chapter_number <= 5
            )
            report["foreshadowing_ledger"] = {
                "active_count": total,
                "overdue_count": overdue_count,
                "due_soon_count": due_soon_count,
                "health": "critical" if overdue_count > 5 else "warning" if overdue_count > 2 else "healthy",
            }

        return report if any([unexpected_resolutions, overdue_addressed, overdue_ignored]) else None

    @staticmethod
    def _build_stage_flags(config: PipelineConfig) -> Dict[str, bool]:
        return {
            "preview": config.enable_preview,
            "optimizer": config.enable_optimizer,
            "consistency": config.enable_consistency,
            "enrichment": config.enable_enrichment,
            "constitution": config.enable_constitution,
            "persona": config.enable_persona,
            "six_dimension": config.enable_six_dimension,
            "reader_sim": config.enable_reader_sim,
            "self_critique": config.enable_self_critique,
            "memory": config.enable_memory,
            "rag": config.enable_rag,
            "rag_mode": config.rag_mode == "two_stage",
        }



__all__ = ["PipelineOrchestrator", "PipelineConfig"]
