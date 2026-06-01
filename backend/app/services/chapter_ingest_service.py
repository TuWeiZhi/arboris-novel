# AIMETA P=章节导入服务_批量章节导入|R=批量导入_格式解析|NR=不含内容生成|E=ChapterIngestService|X=internal|A=服务类|D=sqlalchemy|S=db,fs|RD=./README.ai
from __future__ import annotations

"""
章节向量入库服务：在章节确认后负责切分文本、生成嵌入并写入向量库。

全部注释使用中文，方便团队成员阅读理解。
"""

import asyncio
import logging
from typing import Dict, List, Optional, Sequence

from ..core.config import settings
from ..services.llm_service import LLMService
from ..services.vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)

# 向量入库并发限制 — 防止大量 chunk 同时调用 embedding API
_EMBED_CONCURRENCY = 10

try:  # noqa: SIM105 - 提示缺少可选依赖
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:  # pragma: no cover - 未安装时会走后备方案
    RecursiveCharacterTextSplitter = None  # type: ignore[assignment]


class ChapterIngestionService:
    """封装章节内容与摘要的向量化与入库流程。"""

    def __init__(
        self,
        *,
        llm_service: LLMService,
        vector_store: Optional[VectorStoreService] = None,
    ) -> None:
        self._llm_service = llm_service
        self._vector_store = vector_store or VectorStoreService()
        self._text_splitter = self._init_text_splitter()

    async def check_embedding_model_compatibility(self) -> Dict[str, Any]:
        """
        检测当前嵌入模型与向量库已有数据是否兼容。
        在入库前调用，返回兼容性报告。
        """
        current_model = await self._llm_service.get_embedding_model_name()
        current_dimension = await self._llm_service.get_embedding_dimension(current_model)
        if not current_dimension:
            # 尝试通过实际调用获取维度
            try:
                test_embedding = await self._llm_service.get_embedding("test", user_id=0)
                current_dimension = len(test_embedding) if test_embedding else 0
            except Exception:
                current_dimension = 0

        return await self._vector_store.check_model_compatibility(
            current_model, current_dimension or 0
        )

    async def ingest_chapter(
        self,
        *,
        project_id: str,
        chapter_number: int,
        title: str,
        content: str,
        summary: Optional[str],
        user_id: int,
        purge_summary: bool = False,
    ) -> Dict[str, Any]:
        """
        将章节正文与摘要写入向量库，供后续 RAG 检索使用。

        Returns:
            {"status": "ok" | "skipped" | "model_mismatch", "details": ...}
        """
        if not settings.vector_store_enabled:
            logger.warning("向量库未启用，跳过章节向量写入: project=%s chapter=%s", project_id, chapter_number)
            return {"status": "skipped", "reason": "vector_store_disabled"}
        if not content.strip():
            logger.warning("章节正文为空，跳过向量写入: project=%s chapter=%s", project_id, chapter_number)
            return {"status": "skipped", "reason": "empty_content"}

        # 获取当前嵌入模型信息
        current_model = await self._llm_service.get_embedding_model_name()
        current_dimension = await self._llm_service.get_embedding_dimension(current_model)

        chunks = self._split_into_chunks(content)
        if not chunks:
            logger.warning("章节正文切分后为空，跳过向量写入: project=%s chapter=%s", project_id, chapter_number)
            return {"status": "skipped", "reason": "empty_chunks"}

        logger.info(
            "开始写入章节向量: project=%s chapter=%s chunks=%d model=%s",
            project_id,
            chapter_number,
            len(chunks),
            current_model,
        )

        # 并发生成嵌入向量（带并发限制）
        _sem = asyncio.Semaphore(_EMBED_CONCURRENCY)

        async def _embed_with_model(text: str) -> Optional[List[float]]:
            async with _sem:
                return await self._llm_service.get_embedding(text, user_id=user_id)

        embedding_results = await asyncio.gather(
            *[_embed_with_model(chunk_text) for chunk_text in chunks],
            return_exceptions=True,
        )

        chunk_records = []
        for index, (chunk_text, embedding) in enumerate(zip(chunks, embedding_results)):
            if isinstance(embedding, Exception):
                logger.warning(
                    "生成章节片段向量异常: project=%s chapter=%s chunk=%s error=%s",
                    project_id, chapter_number, index, embedding,
                )
                continue
            if not embedding:
                logger.warning(
                    "生成章节片段向量失败，已跳过: project=%s chapter=%s chunk=%s",
                    project_id, chapter_number, index,
                )
                continue
            # 更新实际维度（首次调用后才知道）
            if not current_dimension:
                current_dimension = len(embedding)
            record_id = f"{project_id}:{chapter_number}:{index}"
            chunk_records.append(
                {
                    "id": record_id,
                    "project_id": project_id,
                    "chapter_number": chapter_number,
                    "chunk_index": index,
                    "chapter_title": title,
                    "content": chunk_text,
                    "embedding": embedding,
                    "metadata": {
                        "chunk_id": record_id,
                        "length": len(chunk_text),
                    },
                }
            )

        if chunk_records:
            await self._vector_store.upsert_chunks(
                records=chunk_records,
                embedding_model=current_model,
                embedding_dimension=current_dimension,
            )
            # 清理旧片段（upsert-then-prune，避免先删后写导致数据丢失）
            await self._vector_store.delete_chunks_except(
                project_id=project_id,
                chapter_number=chapter_number,
                keep_ids=[record["id"] for record in chunk_records],
            )
            logger.info(
                "章节正文向量写入完成: project=%s chapter=%s 成功片段=%d",
                project_id,
                chapter_number,
                len(chunk_records),
            )

        if summary:
            cleaned_summary = summary.strip()
            if cleaned_summary:
                summary_embedding = await self._llm_service.get_embedding(
                    cleaned_summary,
                    user_id=user_id,
                )
                if summary_embedding:
                    summary_id = f"{project_id}:{chapter_number}:summary"
                    await self._vector_store.upsert_summaries(
                        records=[
                            {
                                "id": summary_id,
                                "project_id": project_id,
                                "chapter_number": chapter_number,
                                "title": title,
                                "summary": cleaned_summary,
                                "embedding": summary_embedding,
                            }
                        ],
                        embedding_model=current_model,
                        embedding_dimension=current_dimension or len(summary_embedding),
                    )
                    await self._vector_store.delete_summaries_except(
                        project_id=project_id,
                        chapter_number=chapter_number,
                        keep_ids=[summary_id],
                    )
                    logger.info(
                        "章节摘要向量写入完成: project=%s chapter=%s",
                        project_id,
                        chapter_number,
                    )
                else:
                    logger.warning(
                        "生成章节摘要向量失败，已跳过: project=%s chapter=%s",
                        project_id,
                        chapter_number,
                    )
        elif purge_summary:
            # 显式要求清空该章节的所有摘要向量
            await self._vector_store.delete_summaries_except(
                project_id=project_id,
                chapter_number=chapter_number,
                keep_ids=[],
            )
            logger.info(
                "已按 purge_summary 清空章节摘要向量: project=%s chapter=%s",
                project_id,
                chapter_number,
            )

        # 更新全局模型记录
        if current_model and current_dimension:
            await self._vector_store.set_stored_model_info(current_model, current_dimension)

        return {"status": "ok", "chunks": len(chunk_records), "model": current_model, "dimension": current_dimension}

    async def delete_chapters(self, project_id: str, chapter_numbers: Sequence[int]) -> None:
        """从向量库中删除指定章节的所有片段与摘要。"""
        if not settings.vector_store_enabled or not chapter_numbers:
            return
        logger.info(
            "准备删除章节向量: project=%s chapters=%s",
            project_id,
            list(chapter_numbers),
        )
        await self._vector_store.delete_by_chapters(project_id, list(chapter_numbers))

    def _split_into_chunks(self, text: str) -> List[str]:
        """按照配置的 chunk 大小与重叠度切分章节正文。"""
        normalized = text.strip()
        if not normalized:
            return []

        if self._text_splitter:
            parts = [segment.strip() for segment in self._text_splitter.split_text(normalized)]
            filtered = [part for part in parts if part]
            if filtered:
                logger.debug(
                    "使用 LangChain 文本切分器完成分段: count=%d chunk_size=%d overlap=%d",
                    len(filtered),
                    settings.vector_chunk_size,
                    settings.vector_chunk_overlap,
                )
                return filtered

        return self._legacy_split(normalized)

    @staticmethod
    def _find_split_offset(segment: str) -> Optional[int]:
        """在片段内部寻找更自然的分割点，优先换行，其次常见标点。"""
        candidates: Dict[str, int] = {}
        newline_pos = segment.rfind("\n\n")
        if newline_pos == -1:
            newline_pos = segment.rfind("\n")
        if newline_pos > 0:
            candidates["newline"] = newline_pos

        punctuation_marks = ["。", "！", "？", "!", "?", ".", ";", "；"]
        for mark in punctuation_marks:
            idx = segment.rfind(mark)
            if idx > 0:
                candidates.setdefault("punctuation", idx + len(mark))

        if not candidates:
            return None

        # 选择最接近末尾但又不过短的分割点
        best_offset = max(candidates.values())
        if best_offset < len(segment) * 0.4:
            return None
        return best_offset

    def _init_text_splitter(self) -> Optional["RecursiveCharacterTextSplitter"]:
        """初始化 LangChain 文本切分器，可根据配置动态调整。"""
        if RecursiveCharacterTextSplitter is None:
            logger.warning("未安装 langchain-text-splitters，章节切分将回退至内置策略。")
            return None

        chunk_size = settings.vector_chunk_size
        overlap = min(settings.vector_chunk_overlap, chunk_size // 2)
        separators = [
            "\n\n",
            "\n",
            "。", "！", "？",
            "!", "?", "；", ";",
            "，", ",",
            " ",
        ]
        splitter = RecursiveCharacterTextSplitter(
            separators=separators,
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            keep_separator=False,
            strip_whitespace=True,
        )
        logger.info(
            "已初始化 LangChain 文本切分器: chunk_size=%d overlap=%d",
            chunk_size,
            overlap,
        )
        return splitter

    def _legacy_split(self, text: str) -> List[str]:
        """内置切分策略，作为 LangChain 缺失时的后备方案。"""
        chunk_size = settings.vector_chunk_size
        overlap = min(settings.vector_chunk_overlap, chunk_size // 2)

        chunks: List[str] = []
        start = 0
        total_length = len(text)

        while start < total_length:
            end = min(total_length, start + chunk_size)
            segment = text[start:end]

            split_offset = self._find_split_offset(segment)
            if split_offset is not None and start + split_offset < total_length:
                end = start + split_offset
                segment = text[start:end]

            chunk_text = segment.strip()
            if chunk_text:
                chunks.append(chunk_text)

            if end >= total_length:
                break
            start = max(0, end - overlap)

        logger.debug(
            "使用内置策略完成章节切分: count=%d chunk_size=%d overlap=%d",
            len(chunks),
            chunk_size,
            overlap,
        )
        return chunks


__all__ = ["ChapterIngestionService"]
