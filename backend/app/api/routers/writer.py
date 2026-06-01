# AIMETA P=写作API_章节生成和大纲创建|R=章节生成_大纲生成_评审_L2导演脚本_护栏检查|NR=不含数据存储|E=route:POST_/api/writer/*|X=http|A=生成_评审_过滤|D=fastapi,openai|S=net,db|RD=./README.ai
"""
Writer API Router - 人类化起点长篇写作系统

核心架构：
- L1 Planner：全知规划层（蓝图/大纲）
- L2 Director：章节导演脚本（ChapterMission）
- L3 Writer：有限视角正文生成

关键改进：
1. 信息可见性过滤：L3 Writer 只能看到已登场角色
2. 跨章 1234 逻辑：通过 ChapterMission 控制每章只写一个节拍
3. 后置护栏检查：自动检测并修复违规内容
"""
import asyncio
import json
import logging
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.novel import Chapter, ChapterOutline, ChapterVersion
from ...schemas.novel import (
    Chapter as ChapterSchema,
    ChapterGenerationStatus,
    ChapterVersion as ChapterVersionSchema,
    AdvancedGenerateRequest,
    AdvancedGenerateResponse,
    DeleteChapterRequest,
    EditChapterRequest,
    EvaluateChapterRequest,
    FinalizeChapterRequest,
    FinalizeChapterResponse,
    GenerateChapterRequest,
    GenerateOutlineRequest,
    NovelProject as NovelProjectSchema,
    SelectVersionRequest,
    UpdateChapterOutlineRequest,
)
from ...schemas.user import UserInDB
from ...services.chapter_context_service import ChapterContextService
from ...services.chapter_ingest_service import ChapterIngestionService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...services.vector_store_service import VectorStoreService
from ...services.writer_context_builder import WriterContextBuilder
from ...services.chapter_guardrails import ChapterGuardrails
from ...services.ai_review_service import AIReviewService
from ...services.finalize_service import FinalizeService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json
from ...repositories.system_config_repository import SystemConfigRepository
from ...services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/api/writer", tags=["Writer"])
logger = logging.getLogger(__name__)


async def _load_project_schema(service: NovelService, project_id: str, user_id: int) -> NovelProjectSchema:
    return await service.get_project_schema(project_id, user_id)


async def _generate_chapter_via_pipeline(
    *,
    session: AsyncSession,
    project_id: str,
    chapter_number: int,
    user_id: int,
    writing_notes: Optional[str] = None,
    flow_config: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    orchestrator = PipelineOrchestrator(session)
    try:
        return await orchestrator.generate_chapter(
            project_id=project_id,
            chapter_number=chapter_number,
            writing_notes=writing_notes,
            user_id=user_id,
            flow_config=flow_config,
        )
    except Exception:
        stmt = select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        if chapter:
            chapter.status = ChapterGenerationStatus.FAILED.value
            await session.commit()
        raise


def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
    """截取章节结尾文本，默认保留 500 字。"""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


async def _resolve_version_count(session: AsyncSession) -> int:
    """
    解析章节版本数量配置，优先级：
    1) SystemConfig: writer.chapter_versions
    2) SystemConfig: writer.version_count（兼容旧键）
    3) ENV: WRITER_CHAPTER_VERSION_COUNT / WRITER_CHAPTER_VERSIONS（与 config.py 对齐）
    4) ENV: WRITER_VERSION_COUNT（兼容旧）
    5) settings.writer_chapter_versions（默认=2）
    """
    repo = SystemConfigRepository(session)
    # 1) 新键优先，兼容旧键
    for key in ("writer.chapter_versions", "writer.version_count"):
        record = await repo.get_by_key(key)
        if record and record.value:
            try:
                val = int(record.value)
                if val >= 1:
                    return val
            except ValueError:
                pass
    # 2) 环境变量（与 Settings 对齐）
    for env in ("WRITER_CHAPTER_VERSION_COUNT", "WRITER_CHAPTER_VERSIONS", "WRITER_VERSION_COUNT"):
        v = os.getenv(env)
        if v:
            try:
                val = int(v)
                if val >= 1:
                    return val
            except ValueError:
                pass
    # 3) 默认值
    return int(settings.writer_chapter_versions)


async def _generate_chapter_mission(
    llm_service: LLMService,
    prompt_service: PromptService,
    blueprint_dict: dict,
    previous_summary: str,
    previous_tail: str,
    outline_title: str,
    outline_summary: str,
    writing_notes: str,
    introduced_characters: List[str],
    all_characters: List[str],
    user_id: int,
) -> Optional[dict]:
    """
    L2 Director: 生成章节导演脚本（ChapterMission）
    """
    plan_prompt = await prompt_service.get_prompt("chapter_plan")
    if not plan_prompt:
        logger.warning("未配置 chapter_plan 提示词，跳过导演脚本生成")
        return None

    plan_input = f"""
[上一章摘要]
{previous_summary or "暂无（这是第一章）"}

[上一章结尾]
{previous_tail or "暂无（这是第一章）"}

[当前章节大纲]
标题：{outline_title}
摘要：{outline_summary}

[已登场角色]
{json.dumps(introduced_characters, ensure_ascii=False) if introduced_characters else "暂无"}

[全部角色]
{json.dumps(all_characters, ensure_ascii=False)}

[写作指令]
{writing_notes or "无额外指令"}
"""

    try:
        response = await llm_service.get_llm_response(
            system_prompt=plan_prompt,
            conversation_history=[{"role": "user", "content": plan_input}],
            temperature=0.3,
            user_id=user_id,
            timeout=120.0,
        )
        cleaned = remove_think_tags(response)
        normalized = unwrap_markdown_json(cleaned)
        mission = json.loads(normalized)
        logger.info("成功生成章节导演脚本: macro_beat=%s", mission.get("macro_beat"))
        return mission
    except Exception as exc:
        logger.warning("生成章节导演脚本失败，将使用默认模式: %s", exc)
        return None


async def _rewrite_with_guardrails(
    llm_service: LLMService,
    prompt_service: PromptService,
    original_text: str,
    chapter_mission: Optional[dict],
    violations_text: str,
    user_id: int,
) -> str:
    """
    使用护栏修复提示词重写违规内容
    """
    rewrite_prompt = await prompt_service.get_prompt("rewrite_guardrails")
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
        response = await llm_service.get_llm_response(
            system_prompt=rewrite_prompt,
            conversation_history=[{"role": "user", "content": rewrite_input}],
            temperature=0.3,
            user_id=user_id,
            timeout=300.0,
            response_format=None,
        )
        cleaned = remove_think_tags(response)
        logger.debug("护栏修复成功")
        return cleaned
    except Exception as exc:
        logger.warning("护栏自动修复失败，返回原文: %s", exc)
        return original_text


async def _refresh_edit_summary_and_ingest(
    project_id: str,
    chapter_number: int,
    content: str,
    user_id: Optional[int],
) -> None:
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)

        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.selected_version))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        if not chapter:
            return

        summary_text = None
        try:
            summary = await llm_service.get_summary(
                content,
                temperature=0.15,
                user_id=user_id,
            )
            summary_text = remove_think_tags(summary)
        except Exception as exc:
            logger.warning("编辑章节后自动生成摘要失败: %s", exc)

        if summary_text and chapter.selected_version and chapter.selected_version.content == content:
            chapter.real_summary = summary_text
            await session.commit()

        try:
            outline_stmt = select(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == chapter_number,
            )
            outline_result = await session.execute(outline_stmt)
            outline = outline_result.scalars().first()
            title = outline.title if outline and outline.title else f"第{chapter_number}章"
            ingest_service = ChapterIngestionService(llm_service=llm_service)
            await ingest_service.ingest_chapter(
                project_id=project_id,
                chapter_number=chapter_number,
                title=title,
                content=content,
                # 编辑章节时若已生成摘要则一并入库；为 None 时由 ingest 跳过摘要而非清空
                summary=summary_text,
                user_id=user_id or 0,
            )
            logger.info("章节 %s 向量化入库成功", chapter_number)
        except Exception as exc:
            logger.error("章节 %s 向量化入库失败: %s", chapter_number, exc)


async def _finalize_chapter_async(
    project_id: str,
    chapter_number: int,
    selected_version_id: int,
    user_id: int,
    skip_vector_update: bool = False,
) -> None:
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)

        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.versions))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        if not chapter:
            return

        selected_version = next(
            (v for v in chapter.versions if v.id == selected_version_id),
            None,
        )
        if not selected_version or not selected_version.content:
            return

        chapter.selected_version_id = selected_version.id
        chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
        chapter.word_count = len(selected_version.content or "")
        await session.commit()

        vector_store = None
        if settings.vector_store_enabled:
            try:
                vector_store = VectorStoreService()
            except RuntimeError as exc:
                logger.warning("向量库初始化失败，跳过定稿写入: %s", exc)

        finalize_service = FinalizeService(session, llm_service, vector_store)
        await finalize_service.finalize_chapter(
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_text=selected_version.content,
            user_id=user_id,
            skip_vector_update=skip_vector_update,
        )


def _schedule_finalize_task(
    project_id: str,
    chapter_number: int,
    selected_version_id: int,
    user_id: int,
    skip_vector_update: bool = False,
) -> None:
    asyncio.create_task(
        _finalize_chapter_async(
            project_id=project_id,
            chapter_number=chapter_number,
            selected_version_id=selected_version_id,
            user_id=user_id,
            skip_vector_update=skip_vector_update,
        )
    )


@router.post("/advanced/generate", response_model=AdvancedGenerateResponse)
async def advanced_generate_chapter(
    request: AdvancedGenerateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AdvancedGenerateResponse:
    """
    高级写作入口：通过 PipelineOrchestrator 统一编排生成流程。
    """
    result = await _generate_chapter_via_pipeline(
        session=session,
        project_id=request.project_id,
        chapter_number=request.chapter_number,
        writing_notes=request.writing_notes,
        user_id=current_user.id,
        flow_config=request.flow_config.model_dump(),
    )

    flow_config = request.flow_config
    if flow_config.async_finalize and result.get("variants"):
        best_index = result.get("best_version_index", 0)
        variants = result["variants"]
        if 0 <= best_index < len(variants):
            selected_version_id = variants[best_index]["version_id"]
            background_tasks.add_task(
                _schedule_finalize_task,
                request.project_id,
                request.chapter_number,
                selected_version_id,
                current_user.id,
                False,
            )

    return AdvancedGenerateResponse(**result)


@router.post("/chapters/{chapter_number}/finalize", response_model=FinalizeChapterResponse)
async def finalize_chapter(
    chapter_number: int,
    request: FinalizeChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> FinalizeChapterResponse:
    """
    定稿入口：选中版本后触发 FinalizeService 进行记忆更新与快照写入。
    """
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(request.project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.versions))
        .where(
            Chapter.project_id == request.project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    selected_version = next(
        (v for v in chapter.versions if v.id == request.selected_version_id),
        None,
    )
    if not selected_version or not selected_version.content:
        raise HTTPException(status_code=400, detail="选中的版本不存在或内容为空")

    chapter.selected_version_id = selected_version.id
    chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
    chapter.word_count = len(selected_version.content or "")
    await session.commit()

    vector_store = None
    if settings.vector_store_enabled and not request.skip_vector_update:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过定稿写入: %s", exc)

    finalize_service = FinalizeService(session, LLMService(session), vector_store)
    finalize_result = await finalize_service.finalize_chapter(
        project_id=request.project_id,
        chapter_number=chapter_number,
        chapter_text=selected_version.content,
        user_id=current_user.id,
        skip_vector_update=request.skip_vector_update or False,
    )

    return FinalizeChapterResponse(
        project_id=request.project_id,
        chapter_number=chapter_number,
        selected_version_id=selected_version.id,
        result=finalize_result,
    )


@router.post("/novels/{project_id}/chapters/generate", response_model=NovelProjectSchema)
async def generate_chapter(
    project_id: str,
    request: GenerateChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """兼容旧入口：内部统一转发到 PipelineOrchestrator。"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("用户 %s 通过兼容入口为项目 %s 生成第 %s 章", current_user.id, project_id, request.chapter_number)

    await _generate_chapter_via_pipeline(
        session=session,
        project_id=project_id,
        chapter_number=request.chapter_number,
        writing_notes=request.writing_notes,
        user_id=current_user.id,
        flow_config={"preset": "basic"},
    )
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/select", response_model=NovelProjectSchema)
async def select_chapter_version(
    project_id: str,
    request: SelectVersionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    # 使用 novel_service.select_chapter_version 确保排序一致
    # 该函数会按 created_at 排序并校验索引
    selected_version = await novel_service.select_chapter_version(chapter, request.version_index)
    
    # 校验内容是否为空
    if not selected_version.content or len(selected_version.content.strip()) == 0:
        # 回滚状态，不标记为 successful
        await session.rollback()
        raise HTTPException(status_code=400, detail="选中的版本内容为空，无法确认为最终版")

    # 异步触发向量化入库
    try:
        llm_service = LLMService(session)
        ingest_service = ChapterIngestionService(llm_service=llm_service)
        await ingest_service.ingest_chapter(
            project_id=project_id,
            chapter_number=request.chapter_number,
            title=chapter.title or f"第{request.chapter_number}章",
            content=selected_version.content,
            summary=None
        )
        logger.info(f"章节 {request.chapter_number} 向量化入库成功")
    except Exception as e:
        logger.error(f"章节 {request.chapter_number} 向量化入库失败: {e}")
        # 向量化失败不应阻止版本选择，仅记录错误

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/evaluate", response_model=NovelProjectSchema)
async def evaluate_chapter(
    project_id: str,
    request: EvaluateChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    # 确保预加载 selected_version 关系
    from sqlalchemy.orm import selectinload
    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.selected_version))
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    
    if not chapter:
        chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    # 如果没有选中版本，使用最新版本进行评审
    version_to_evaluate = chapter.selected_version
    if not version_to_evaluate:
        # 获取该章节的所有版本，选择最新的一个
        from sqlalchemy.orm import selectinload
        stmt_versions = (
            select(Chapter)
            .options(selectinload(Chapter.versions))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == request.chapter_number,
            )
        )
        result_versions = await session.execute(stmt_versions)
        chapter_with_versions = result_versions.scalars().first()
        
        if not chapter_with_versions or not chapter_with_versions.versions:
            raise HTTPException(status_code=400, detail="该章节还没有生成任何版本，无法进行评审")
        
        # 使用最新的版本（列表中的最后一个）
        version_to_evaluate = chapter_with_versions.versions[-1]
    
    if not version_to_evaluate or not version_to_evaluate.content:
        raise HTTPException(status_code=400, detail="版本内容为空，无法进行评审")

    chapter.status = "evaluating"
    await session.commit()

    eval_prompt = await prompt_service.get_prompt("evaluation")
    if not eval_prompt:
        logger.warning("未配置名为 'evaluation' 的评审提示词，将跳过 AI 评审")
        # 使用 add_chapter_evaluation 创建评审记录
        await novel_service.add_chapter_evaluation(
            chapter=chapter,
            version=version_to_evaluate,
            feedback="未配置评审提示词",
            decision="skipped"
        )
        return await _load_project_schema(novel_service, project_id, current_user.id)

    try:
        evaluation_raw = await llm_service.get_llm_response(
            system_prompt=eval_prompt,
            conversation_history=[{"role": "user", "content": version_to_evaluate.content}],
            temperature=0.3,
            user_id=current_user.id,
        )
        evaluation_text = remove_think_tags(evaluation_raw)
        
        # 校验 AI 返回的内容不为空
        if not evaluation_text or len(evaluation_text.strip()) == 0:
            raise ValueError("评审结果为空")
        
        # 使用 add_chapter_evaluation 创建评审记录
        # 这会自动设置状态为 WAITING_FOR_CONFIRM
        await novel_service.add_chapter_evaluation(
            chapter=chapter,
            version=version_to_evaluate,
            feedback=evaluation_text,
            decision="reviewed"
        )
        logger.info("项目 %s 第 %s 章评审成功", project_id, request.chapter_number)
    except Exception as exc:
        logger.exception("项目 %s 第 %s 章评审失败: %s", project_id, request.chapter_number, exc)
        # 回滚事务，恢复状态
        await session.rollback()
        
        # 重新加载 chapter 对象（因为 rollback 后对象已脱离 session）
        stmt = (
            select(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == request.chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        
        if chapter:
            # 使用 add_chapter_evaluation 创建失败记录
            # 注意：这里不能再用 add_chapter_evaluation，因为它会设置状态为 waiting_for_confirm
            # 失败时应该设置为 evaluation_failed
            from app.models.novel import ChapterEvaluation
            evaluation_record = ChapterEvaluation(
                chapter_id=chapter.id,
                version_id=version_to_evaluate.id,
                decision="failed",
                feedback=f"评审失败: {str(exc)}",
                score=None
            )
            session.add(evaluation_record)
            chapter.status = "evaluation_failed"
            await session.commit()
        
        # 抛出异常，让前端知道评审失败
        raise HTTPException(status_code=500, detail=f"评审失败: {str(exc)}")
    
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/update-outline", response_model=NovelProjectSchema)
async def update_chapter_outline(
    project_id: str,
    request: UpdateChapterOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="未找到对应章节大纲")

    outline.title = request.title
    outline.summary = request.summary
    await session.commit()

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/delete", response_model=NovelProjectSchema)
async def delete_chapters(
    project_id: str,
    request: DeleteChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    for ch_num in request.chapter_numbers:
        await novel_service.delete_chapter(project_id, ch_num)

    await session.commit()
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/outline", response_model=NovelProjectSchema)
async def generate_chapters_outline(
    project_id: str,
    request: GenerateOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    
    # 获取蓝图信息
    project_schema = await novel_service._serialize_project(project)
    blueprint_text = json.dumps(project_schema.blueprint.model_dump(), ensure_ascii=False, indent=2)
    
    # 获取已有的章节大纲
    existing_outlines = [
        f"第{o.chapter_number}章 - {o.title}: {o.summary}"
        for o in sorted(project.outlines, key=lambda x: x.chapter_number)
    ]
    existing_outlines_text = "\n".join(existing_outlines) if existing_outlines else "暂无"

    outline_prompt = await prompt_service.get_prompt("outline_generation")
    if not outline_prompt:
        raise HTTPException(status_code=500, detail="未配置大纲生成提示词")

    prompt_input = f"""
[世界蓝图]
{blueprint_text}

[已有章节大纲]
{existing_outlines_text}

[生成任务]
请从第 {request.start_chapter} 章开始，续写接下来的 {request.num_chapters} 章的大纲。
要求返回 JSON 格式，包含一个 chapters 数组，每个元素包含 chapter_number, title, summary。
"""

    response = await llm_service.get_llm_response(
        system_prompt=outline_prompt,
        conversation_history=[{"role": "user", "content": prompt_input}],
        temperature=0.7,
        user_id=current_user.id,
    )
    
    cleaned = remove_think_tags(response)
    normalized = unwrap_markdown_json(cleaned)
    try:
        data = json.loads(normalized)
        new_outlines = data.get("chapters", [])
        for item in new_outlines:
            await novel_service.update_or_create_outline(
                project_id, 
                item["chapter_number"], 
                item["title"], 
                item["summary"]
            )
        await session.commit()
    except Exception as exc:
        logger.exception("生成大纲解析失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"大纲生成失败: {str(exc)}")

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit", response_model=NovelProjectSchema)
async def edit_chapter_content(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    
    await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    
    # 更新内容：优先更新选中版本，否则选最新版本或创建新版本
    target_version = chapter.selected_version
    if not target_version and chapter.versions:
        target_version = sorted(chapter.versions, key=lambda item: item.created_at)[-1]

    if target_version:
        target_version.content = request.content
        if not chapter.selected_version_id:
            chapter.selected_version_id = target_version.id
    else:
        target_version = ChapterVersion(
            chapter_id=chapter.id,
            content=request.content,
            version_label="manual_edit",
        )
        session.add(target_version)
        await session.flush()
        chapter.selected_version_id = target_version.id
    
    chapter.status = "successful"
    chapter.word_count = len(request.content or "")
    await session.commit()

    background_tasks.add_task(
        _refresh_edit_summary_and_ingest,
        project_id,
        request.chapter_number,
        request.content,
        current_user.id,
    )

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit-fast", response_model=ChapterSchema)
async def edit_chapter_content_fast(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    target_version = chapter.selected_version
    if not target_version and chapter.versions:
        target_version = sorted(chapter.versions, key=lambda item: item.created_at)[-1]

    if target_version:
        target_version.content = request.content
        if not chapter.selected_version_id:
            chapter.selected_version_id = target_version.id
    else:
        target_version = ChapterVersion(
            chapter_id=chapter.id,
            content=request.content,
            version_label="manual_edit",
        )
        session.add(target_version)
        await session.flush()
        chapter.selected_version_id = target_version.id

    chapter.status = "successful"
    chapter.word_count = len(request.content or "")
    await session.commit()

    background_tasks.add_task(
        _refresh_edit_summary_and_ingest,
        project_id,
        request.chapter_number,
        request.content,
        current_user.id,
    )

    stmt = (
        select(Chapter)
        .options(
            selectinload(Chapter.versions),
            selectinload(Chapter.evaluations),
            selectinload(Chapter.selected_version),
        )
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    outline_stmt = select(ChapterOutline).where(
        ChapterOutline.project_id == project_id,
        ChapterOutline.chapter_number == request.chapter_number,
    )
    outline_result = await session.execute(outline_stmt)
    outline = outline_result.scalars().first()

    title = outline.title if outline else f"第{request.chapter_number}章"
    summary = outline.summary if outline else ""
    real_summary = chapter.real_summary
    content = chapter.selected_version.content if chapter.selected_version else None
    versions = (
        [
            ChapterVersionSchema(
                id=v.id,
                content=v.content,
                style=v.version_label,
                metadata=v.metadata,
                is_selected=bool(chapter.selected_version_id and v.id == chapter.selected_version_id),
            )
            for v in sorted(chapter.versions, key=lambda item: item.created_at)
        ]
        if chapter.versions
        else None
    )
    evaluation_text = None
    if chapter.evaluations:
        latest = sorted(chapter.evaluations, key=lambda item: item.created_at)[-1]
        evaluation_text = latest.feedback or latest.decision
    status_value = chapter.status or ChapterGenerationStatus.NOT_GENERATED.value

    return ChapterSchema(
        chapter_number=request.chapter_number,
        title=title,
        summary=summary,
        real_summary=real_summary,
        content=content,
        versions=versions,
        evaluation=evaluation_text,
        generation_status=ChapterGenerationStatus(status_value),
        word_count=chapter.word_count or 0,
    )
