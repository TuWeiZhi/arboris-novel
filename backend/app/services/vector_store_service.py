# AIMETA P=向量存储服务_文本向量化|R=向量存储_相似搜索|NR=不含业务逻辑|E=VectorStoreService|X=internal|A=服务类|D=chromadb|S=db,fs|RD=./README.ai
from __future__ import annotations

"""
基于 libsql 的向量检索服务，封装章节内容的存储与查询。

本文件中的注释均使用中文，便于团队成员快速理解 RAG 相关逻辑。
"""

import json
import logging
import math
import re
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence

from ..core.config import settings

try:  # noqa: SIM105 - 明确区分依赖缺失的情况
    import libsql_client
except ImportError:  # pragma: no cover - 在未安装依赖时提供友好提示
    libsql_client = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """向量检索得到的剧情片段。"""

    content: str
    chapter_number: int
    chapter_title: Optional[str]
    score: float
    metadata: Dict[str, Any]


@dataclass
class RetrievedSummary:
    """向量检索得到的章节摘要。"""

    chapter_number: int
    title: str
    summary: str
    score: float


class VectorStoreService:
    """libsql 向量库操作工具，确保不同小说项目的数据隔离。"""

    def __init__(self) -> None:
        if not settings.vector_store_enabled:
            logger.warning("未开启向量库配置，RAG 检索将被跳过。")
            self._client = None
            self._schema_ready = True
            return

        if libsql_client is None:  # pragma: no cover - 运行环境缺少依赖
            raise RuntimeError("缺少 libsql-client 依赖，请先在环境中安装。")

        url = settings.vector_db_url
        if url and url.startswith("file:"):
            path_part = url.split("file:", 1)[1]
            resolved = Path(path_part).expanduser().resolve()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            url = f"file:{resolved}"
            logger.info("向量库使用本地文件: %s", resolved)

        try:
            logger.info("初始化 libsql 客户端: url=%s", url)
            self._client = libsql_client.create_client(
                url=url,
                auth_token=settings.vector_db_auth_token,
            )
        except Exception as exc:  # pragma: no cover - 连接异常仅打印日志
            logger.error("初始化 libsql 客户端失败: %s", exc)
            self._client = None
            self._schema_ready = True
        else:
            self._schema_ready = False
            logger.info("libsql 客户端初始化成功，等待建表。")

    async def ensure_schema(self) -> None:
        """初始化向量表结构，保证系统首次运行即可使用。"""
        if not self._client or self._schema_ready:
            return

        statements = [
            """
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                chapter_title TEXT,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL,
                metadata TEXT,
                embedding_model TEXT,
                embedding_dimension INTEGER,
                created_at INTEGER DEFAULT (unixepoch())
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rag_chunks_project
            ON rag_chunks(project_id, chapter_number)
            """,
            """
            CREATE TABLE IF NOT EXISTS rag_summaries (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                embedding BLOB NOT NULL,
                embedding_model TEXT,
                embedding_dimension INTEGER,
                created_at INTEGER DEFAULT (unixepoch())
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_rag_summaries_project
            ON rag_summaries(project_id, chapter_number)
            """,
            """
            CREATE TABLE IF NOT EXISTS rag_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER DEFAULT (unixepoch())
            )
            """,
        ]

        try:
            for sql in statements:
                await self._client.execute(sql)  # type: ignore[union-attr]
            # 旧表升级：为已有表添加缺失列（兼容已有数据库）
            await self._migrate_schema()
            logger.info("已确保向量库表结构存在。")
        except Exception as exc:  # pragma: no cover - 初始化失败时记录日志
            logger.error("创建向量库表结构失败: %s", exc)
        else:
            self._schema_ready = True

    async def _migrate_schema(self) -> None:
        """为旧版数据库表添加新列，兼容升级。"""
        migrations = [
            ("rag_chunks", "embedding_model", "TEXT"),
            ("rag_chunks", "embedding_dimension", "INTEGER"),
            ("rag_summaries", "embedding_model", "TEXT"),
            ("rag_summaries", "embedding_dimension", "INTEGER"),
        ]
        for table, column, col_type in migrations:
            try:
                await self._client.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                )
            except Exception:
                pass  # 列已存在时 SQLite 会报错，忽略即可

    async def get_stored_model_info(self) -> Optional[Dict[str, str]]:
        """读取向量库中记录的嵌入模型信息。"""
        if not self._client:
            return None
        await self.ensure_schema()
        try:
            result = await self._client.execute(
                "SELECT key, value FROM rag_meta WHERE key IN ('embedding_model', 'embedding_dimension', 'last_ingest_at')"
            )
            rows = self._iter_rows(result)
            if not rows:
                return None
            return {row["key"]: row["value"] for row in rows}
        except Exception:
            return None

    async def set_stored_model_info(self, model: str, dimension: int) -> None:
        """写入当前使用的嵌入模型信息。"""
        if not self._client:
            return
        await self.ensure_schema()
        import time
        for key, value in [("embedding_model", model), ("embedding_dimension", str(dimension)), ("last_ingest_at", str(int(time.time())))]:
            try:
                await self._client.execute(
                    "INSERT INTO rag_meta (key, value, updated_at) VALUES (:key, :value, unixepoch()) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    {"key": key, "value": value},
                )
            except Exception as exc:
                logger.warning("写入 rag_meta 失败: key=%s error=%s", key, exc)

    async def check_model_compatibility(
        self, current_model: str, current_dimension: int
    ) -> Dict[str, Any]:
        """
        检测当前嵌入模型与向量库中已有数据是否兼容。

        Returns:
            {
                "compatible": bool,
                "stored_model": str or None,
                "stored_dimension": int or None,
                "current_model": str,
                "current_dimension": int,
                "reason": str,  # "match" | "first_run" | "model_changed" | "dimension_changed"
                "stored_record_count": int,
            }
        """
        stored = await self.get_stored_model_info()
        stored_model = stored.get("embedding_model") if stored else None
        stored_dim_str = stored.get("embedding_dimension") if stored else None
        stored_dimension = int(stored_dim_str) if stored_dim_str else None

        # 统计已有记录数
        record_count = 0
        if self._client:
            try:
                await self.ensure_schema()
                result = await self._client.execute(
                    "SELECT COUNT(*) AS cnt FROM rag_chunks"
                )
                for row in self._iter_rows(result):
                    record_count = row.get("cnt", 0)
                    break
            except Exception:
                pass

        if not stored_model:
            return {
                "compatible": True,
                "stored_model": None,
                "stored_dimension": None,
                "current_model": current_model,
                "current_dimension": current_dimension,
                "reason": "first_run",
                "stored_record_count": record_count,
            }

        if stored_model != current_model:
            return {
                "compatible": False,
                "stored_model": stored_model,
                "stored_dimension": stored_dimension,
                "current_model": current_model,
                "current_dimension": current_dimension,
                "reason": "model_changed",
                "stored_record_count": record_count,
            }

        if stored_dimension and stored_dimension != current_dimension:
            return {
                "compatible": False,
                "stored_model": stored_model,
                "stored_dimension": stored_dimension,
                "current_model": current_model,
                "current_dimension": current_dimension,
                "reason": "dimension_changed",
                "stored_record_count": record_count,
            }

        return {
            "compatible": True,
            "stored_model": stored_model,
            "stored_dimension": stored_dimension,
            "current_model": current_model,
            "current_dimension": current_dimension,
            "reason": "match",
            "stored_record_count": record_count,
        }

    async def rebuild_vectors(
        self,
        *,
        project_id: str,
        chapters_data: List[Dict[str, Any]],
        llm_service: Any,
        user_id: int,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ) -> Dict[str, Any]:
        """
        用当前嵌入模型重新生成所有向量数据（模型变更后的恢复操作）。

        Args:
            project_id: 小说项目 ID
            chapters_data: [{"chapter_number": int, "title": str, "content": str, "summary": str}, ...]
            llm_service: LLMService 实例
            user_id: 用户 ID
            chunk_size: 切分大小
            chunk_overlap: 重叠大小

        Returns:
            {"rebuilt_chapters": int, "total_chunks": int, "total_summaries": int, "errors": int}
        """
        if not self._client:
            return {"rebuilt_chapters": 0, "total_chunks": 0, "total_summaries": 0, "errors": 0}

        await self.ensure_schema()

        # 先清空该项目的所有旧向量
        try:
            await self._client.execute(
                "DELETE FROM rag_chunks WHERE project_id = :pid", {"pid": project_id}
            )
            await self._client.execute(
                "DELETE FROM rag_summaries WHERE project_id = :pid", {"pid": project_id}
            )
            logger.info("已清空项目 %s 的旧向量数据", project_id)
        except Exception as exc:
            logger.warning("清空旧向量失败: %s", exc)

        total_chunks = 0
        total_summaries = 0
        errors = 0

        # 导入切分器
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                separators=["\n\n", "\n", "。", "！", "？", "!", "?", "；", ";", "，", ",", " "],
                chunk_size=chunk_size,
                chunk_overlap=min(chunk_overlap, chunk_size // 2),
                keep_separator=False,
                strip_whitespace=True,
            )
        except ImportError:
            splitter = None

        for ch in chapters_data:
            ch_num = ch["chapter_number"]
            title = ch.get("title", f"第{ch_num}章")
            content = ch.get("content", "")
            summary = ch.get("summary", "")

            # 切分正文
            if splitter and content.strip():
                chunks = [s.strip() for s in splitter.split_text(content.strip()) if s.strip()]
            elif content.strip():
                chunks = [content.strip()]
            else:
                chunks = []

            # 生成正文向量
            chunk_records = []
            for idx, chunk_text in enumerate(chunks):
                try:
                    embedding = await llm_service.get_embedding(chunk_text, user_id=user_id)
                    if embedding:
                        record_id = f"{project_id}:{ch_num}:{idx}"
                        chunk_records.append({
                            "id": record_id,
                            "project_id": project_id,
                            "chapter_number": ch_num,
                            "chunk_index": idx,
                            "chapter_title": title,
                            "content": chunk_text,
                            "embedding": embedding,
                            "metadata": {"chunk_id": record_id, "length": len(chunk_text)},
                        })
                except Exception as exc:
                    logger.warning("重建向量失败: project=%s chapter=%s chunk=%s error=%s", project_id, ch_num, idx, exc)
                    errors += 1

            if chunk_records:
                await self.upsert_chunks(records=chunk_records)
                total_chunks += len(chunk_records)

            # 生成摘要向量
            if summary.strip():
                try:
                    summary_embedding = await llm_service.get_embedding(summary.strip(), user_id=user_id)
                    if summary_embedding:
                        await self.upsert_summaries(records=[{
                            "id": f"{project_id}:{ch_num}:summary",
                            "project_id": project_id,
                            "chapter_number": ch_num,
                            "title": title,
                            "summary": summary.strip(),
                            "embedding": summary_embedding,
                        }])
                        total_summaries += 1
                except Exception as exc:
                    logger.warning("重建摘要向量失败: project=%s chapter=%s error=%s", project_id, ch_num, exc)
                    errors += 1

        # 记录当前模型信息
        current_model = await llm_service.get_embedding_model_name()
        current_dim = await llm_service.get_embedding_dimension(current_model)
        if current_model and current_dim:
            await self.set_stored_model_info(current_model, current_dim)

        logger.info(
            "向量重建完成: project=%s chapters=%d chunks=%d summaries=%d errors=%d",
            project_id, len(chapters_data), total_chunks, total_summaries, errors,
        )
        return {
            "rebuilt_chapters": len(chapters_data),
            "total_chunks": total_chunks,
            "total_summaries": total_summaries,
            "errors": errors,
        }

    async def query_chunks(
        self,
        *,
        project_id: str,
        embedding: Sequence[float],
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """根据查询向量检索剧情片段，结果已按相似度排序。"""
        if not self._client or not embedding:
            return []

        await self.ensure_schema()
        top_k = top_k or settings.vector_top_k_chunks
        if top_k <= 0:
            return []

        blob = self._to_f32_blob(embedding)
        sql = """
        SELECT
            content,
            chapter_number,
            chapter_title,
            COALESCE(metadata, '{}') AS metadata,
            vector_distance_cosine(embedding, :query) AS distance
        FROM rag_chunks
        WHERE project_id = :project_id
        ORDER BY distance ASC
        LIMIT :limit
        """
        try:
            result = await self._client.execute(  # type: ignore[union-attr]
                sql,
                {
                    "project_id": project_id,
                    "query": blob,
                    "limit": top_k,
                },
            )
        except Exception as exc:  # pragma: no cover - 查询异常时仅记录
            if "no such function: vector_distance_cosine" in str(exc).lower():
                logger.warning("向量库缺少 vector_distance_cosine 函数，回退至应用层相似度计算。")
                return await self._query_chunks_with_python_similarity(
                    project_id=project_id,
                    embedding=embedding,
                    top_k=top_k,
                )
            logger.warning("向量检索剧情片段失败: %s", exc)
            return []

        items: List[RetrievedChunk] = []
        for row in self._iter_rows(result):
            items.append(
                RetrievedChunk(
                    content=row.get("content", ""),
                    chapter_number=row.get("chapter_number", 0),
                    chapter_title=row.get("chapter_title"),
                    score=row.get("distance", 0.0),
                    metadata=self._parse_metadata(row.get("metadata")),
                )
            )
        return items

    async def query_summaries(
        self,
        *,
        project_id: str,
        embedding: Sequence[float],
        top_k: Optional[int] = None,
    ) -> List[RetrievedSummary]:
        """根据查询向量检索章节摘要列表。"""
        if not self._client or not embedding:
            return []

        await self.ensure_schema()
        top_k = top_k or settings.vector_top_k_summaries
        if top_k <= 0:
            return []

        blob = self._to_f32_blob(embedding)
        sql = """
        SELECT
            chapter_number,
            title,
            summary,
            vector_distance_cosine(embedding, :query) AS distance
        FROM rag_summaries
        WHERE project_id = :project_id
        ORDER BY distance ASC
        LIMIT :limit
        """
        try:
            result = await self._client.execute(  # type: ignore[union-attr]
                sql,
                {
                    "project_id": project_id,
                    "query": blob,
                    "limit": top_k,
                },
            )
        except Exception as exc:  # pragma: no cover - 查询异常时仅记录
            if "no such function: vector_distance_cosine" in str(exc).lower():
                logger.warning("向量库缺少 vector_distance_cosine 函数，回退至应用层相似度计算。")
                return await self._query_summaries_with_python_similarity(
                    project_id=project_id,
                    embedding=embedding,
                    top_k=top_k,
                )
            logger.warning("向量检索章节摘要失败: %s", exc)
            return []

        items: List[RetrievedSummary] = []
        for row in self._iter_rows(result):
            items.append(
                RetrievedSummary(
                    chapter_number=row.get("chapter_number", 0),
                    title=row.get("title", ""),
                    summary=row.get("summary", ""),
                    score=row.get("distance", 0.0),
                )
            )
        return items

    async def upsert_chunks(
        self,
        *,
        records: Iterable[Dict[str, Any]],
        embedding_model: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
    ) -> None:
        """批量写入章节片段，供后续检索使用。"""
        if not self._client:
            return

        await self.ensure_schema()
        sql = """
        INSERT INTO rag_chunks (
            id,
            project_id,
            chapter_number,
            chunk_index,
            chapter_title,
            content,
            embedding,
            metadata,
            embedding_model,
            embedding_dimension
        ) VALUES (
            :id,
            :project_id,
            :chapter_number,
            :chunk_index,
            :chapter_title,
            :content,
            :embedding,
            :metadata,
            :embedding_model,
            :embedding_dimension
        )
        ON CONFLICT(id) DO UPDATE SET
            content=excluded.content,
            embedding=excluded.embedding,
            metadata=excluded.metadata,
            chapter_title=excluded.chapter_title,
            embedding_model=excluded.embedding_model,
            embedding_dimension=excluded.embedding_dimension
        """
        payload = []
        for item in records:
            embedding = item.get("embedding", [])
            record = {
                **item,
                "embedding": self._to_f32_blob(embedding),
                "metadata": json.dumps(item.get("metadata") or {}, ensure_ascii=False),
                "embedding_model": embedding_model or item.get("embedding_model"),
                "embedding_dimension": embedding_dimension or len(embedding),
            }
            payload.append(record)

        if not payload:
            return

        # 批量写入：使用 batch() 而非逐条 execute() 以减少网络往返
        try:
            stmts = [libsql_client.Statement(sql, item) for item in payload]
            await self._client.batch(stmts)  # type: ignore[union-attr]
        except Exception as exc:  # pragma: no cover - 批量写入失败时回退至逐条
            logger.warning("向量批量写入失败，回退至逐条写入: %s", exc)
            for item in payload:
                try:
                    await self._client.execute(sql, item)  # type: ignore[union-attr]
                except Exception as item_exc:
                    logger.error("写入 rag_chunks 失败: %s", item_exc)
        else:
            logger.debug("批量写入 rag_chunks 完成: %d 条", len(payload))

    async def upsert_summaries(
        self,
        *,
        records: Iterable[Dict[str, Any]],
        embedding_model: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
    ) -> None:
        """同步章节摘要向量，供摘要层检索使用。"""
        if not self._client:
            return

        await self.ensure_schema()
        sql = """
        INSERT INTO rag_summaries (
            id,
            project_id,
            chapter_number,
            title,
            summary,
            embedding,
            embedding_model,
            embedding_dimension
        ) VALUES (
            :id,
            :project_id,
            :chapter_number,
            :title,
            :summary,
            :embedding,
            :embedding_model,
            :embedding_dimension
        )
        ON CONFLICT(id) DO UPDATE SET
            summary=excluded.summary,
            embedding=excluded.embedding,
            title=excluded.title,
            embedding_model=excluded.embedding_model,
            embedding_dimension=excluded.embedding_dimension
        """

        payload = []
        for item in records:
            embedding = item.get("embedding", [])
            record = {
                **item,
                "embedding": self._to_f32_blob(embedding),
                "embedding_model": embedding_model or item.get("embedding_model"),
                "embedding_dimension": embedding_dimension or len(embedding),
            }
            payload.append(record)

        if not payload:
            return

        try:
            stmts = [libsql_client.Statement(sql, item) for item in payload]
            await self._client.batch(stmts)  # type: ignore[union-attr]
        except Exception as exc:  # pragma: no cover - 批量写入失败时回退至逐条
            logger.warning("摘要向量批量写入失败，回退至逐条写入: %s", exc)
            for item in payload:
                try:
                    await self._client.execute(sql, item)  # type: ignore[union-attr]
                except Exception as item_exc:
                    logger.error("写入 rag_summaries 失败: %s", item_exc)
        else:
            logger.debug("批量写入 rag_summaries 完成: %d 条", len(payload))

    async def delete_chunks_except(
        self,
        *,
        project_id: str,
        chapter_number: int,
        keep_ids: Sequence[str],
    ) -> None:
        """删除指定章节中不在 keep_ids 内的旧片段，实现 upsert-then-prune 的原子语义。"""
        if not self._client:
            return

        await self.ensure_schema()
        await self._delete_except(
            table="rag_chunks",
            project_id=project_id,
            chapter_number=chapter_number,
            keep_ids=keep_ids,
        )

    async def delete_summaries_except(
        self,
        *,
        project_id: str,
        chapter_number: int,
        keep_ids: Sequence[str],
    ) -> None:
        """删除指定章节中不在 keep_ids 内的旧摘要。"""
        if not self._client:
            return

        await self.ensure_schema()
        await self._delete_except(
            table="rag_summaries",
            project_id=project_id,
            chapter_number=chapter_number,
            keep_ids=keep_ids,
        )

    async def _delete_except(
        self,
        *,
        table: str,
        project_id: str,
        chapter_number: int,
        keep_ids: Sequence[str],
    ) -> None:
        """通用 prune 实现：用 json_each 展开 keep_ids，规避 SQLite 变量数上限。"""
        # 表名为内部常量，安全；keep_ids 通过 JSON 参数化传入
        params: Dict[str, Any] = {
            "project_id": project_id,
            "chapter_number": chapter_number,
        }
        if keep_ids:
            params["keep_ids_json"] = json.dumps(list(keep_ids))
            sql = f"""
            DELETE FROM {table}
            WHERE project_id = :project_id
              AND chapter_number = :chapter_number
              AND id NOT IN (SELECT value FROM json_each(:keep_ids_json))
            """
        else:
            sql = f"""
            DELETE FROM {table}
            WHERE project_id = :project_id
              AND chapter_number = :chapter_number
            """

        try:
            await self._client.execute(sql, params)  # type: ignore[union-attr]
        except Exception as exc:  # pragma: no cover
            logger.error(
                "Failed to prune %s: project=%s chapter=%s error=%s",
                table, project_id, chapter_number, exc,
            )

    async def delete_by_chapters(self, project_id: str, chapter_numbers: Sequence[int]) -> None:
        """根据章节编号批量删除对应的上下文数据。"""
        if not self._client or not chapter_numbers:
            return

        await self.ensure_schema()
        placeholders = ",".join(":chapter_" + str(idx) for idx in range(len(chapter_numbers)))
        params = {
            "project_id": project_id,
            **{f"chapter_{idx}": number for idx, number in enumerate(chapter_numbers)},
        }
        chunk_sql = f"""
        DELETE FROM rag_chunks
        WHERE project_id = :project_id
          AND chapter_number IN ({placeholders})
        """
        summary_sql = f"""
        DELETE FROM rag_summaries
        WHERE project_id = :project_id
          AND chapter_number IN ({placeholders})
        """
        try:
            await self._client.execute(chunk_sql, params)  # type: ignore[union-attr]
            await self._client.execute(summary_sql, params)  # type: ignore[union-attr]
            logger.info(
                "已删除章节向量: project=%s chapters=%s",
                project_id,
                list(chapter_numbers),
            )
        except Exception as exc:  # pragma: no cover - 删除失败时记录日志
            logger.error("删除章节向量失败: project=%s chapters=%s error=%s", project_id, chapter_numbers, exc)

    @staticmethod
    def _to_f32_blob(embedding: Sequence[float]) -> bytes:
        """将向量浮点列表编码为 libsql 可识别的 float32 二进制。"""
        return array("f", embedding).tobytes()

    @staticmethod
    def _from_f32_blob(blob: bytes) -> array:
        """将 float32 二进制 blob 解码为 array('f')。"""
        arr = array('f')
        arr.frombytes(blob) if isinstance(blob, bytes) else None
        return arr

    # ------------------------------------------------------------------
    # 章节写入与检索（原 VectorStoreServiceExt 的高层封装）
    # ------------------------------------------------------------------
    async def add_chapter_to_store(
        self,
        *,
        project_id: str,
        chapter_number: int,
        content: str,
        chapter_title: Optional[str] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        embedding_func: Callable[[str], Awaitable[Optional[List[float]]]],
        embedding_model: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
    ) -> int:
        """将章节内容分块、生成嵌入并写入向量库，返回写入的块数。"""
        if not self._client:
            return 0

        await self.ensure_schema()

        # 先删除旧数据
        await self.delete_by_chapters(project_id, [chapter_number])

        chunks = self._split_text(content, chunk_size, chunk_overlap)
        if not chunks:
            return 0

        records = []
        for idx, chunk_text in enumerate(chunks):
            embedding = await embedding_func(chunk_text)
            if embedding:
                records.append({
                    "id": f"{project_id}:{chapter_number}:{idx}",
                    "project_id": project_id,
                    "chapter_number": chapter_number,
                    "chunk_index": idx,
                    "chapter_title": chapter_title,
                    "content": chunk_text,
                    "embedding": embedding,
                    "metadata": {"source": "chapter", "chunk_index": idx, "total_chunks": len(chunks)},
                })

        if records:
            await self.upsert_chunks(
                records=records,
                embedding_model=embedding_model,
                embedding_dimension=embedding_dimension or len(records[0]["embedding"]),
            )

        logger.info("已写入章节向量: project=%s chapter=%s chunks=%d", project_id, chapter_number, len(records))
        return len(records)

    @staticmethod
    def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """按段落优先分割文本块，保持语义完整性。"""
        if not text:
            return []

        paragraphs = re.split(r'\n\s*\n', text)
        chunks: List[str] = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) > chunk_size:
                if current:
                    chunks.append(current)
                if len(para) > chunk_size:
                    sentences = re.split(r'([。！？.!?])', para)
                    temp = ""
                    for i in range(0, len(sentences), 2):
                        sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")
                        if len(temp) + len(sentence) > chunk_size:
                            if temp:
                                chunks.append(temp)
                            temp = sentence
                        else:
                            temp += sentence
                    current = temp
                else:
                    current = para
            else:
                current = f"{current}\n\n{para}" if current else para

        if current:
            chunks.append(current)

        # 添加重叠以保持上下文连续性
        if chunk_overlap > 0 and len(chunks) > 1:
            overlapped = []
            for i, chunk in enumerate(chunks):
                if i > 0:
                    prev = chunks[i - 1]
                    overlap_text = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
                    chunk = f"{overlap_text}...{chunk}"
                overlapped.append(chunk)
            return overlapped

        return chunks

    @staticmethod
    def _from_f32_blob(blob: Any) -> List[float]:
        """将数据库中的 BLOB 解码为浮点列表。"""
        if not blob:
            return []
        if isinstance(blob, memoryview):
            blob = blob.tobytes()
        data = array("f")
        data.frombytes(bytes(blob))
        return list(data)

    @staticmethod
    def _cosine_distance(query_a: "array", vec_b: Sequence[float]) -> float:
        """余弦距离（1 - similarity），使用 array("f") 加速计算。"""
        if len(query_a) == 0 or not vec_b:
            return 1.0
        b = array("f", vec_b)
        dot = sum(a * b for a, b in zip(query_a, b))
        norm_a = math.sqrt(sum(a * a for a in query_a))
        norm_b = math.sqrt(sum(b * b for b in b))
        if norm_a == 0 or norm_b == 0:
            return 1.0
        return 1.0 - (dot / (norm_a * norm_b))

    async def _query_chunks_with_python_similarity(
        self,
        *,
        project_id: str,
        embedding: Sequence[float],
        top_k: int,
    ) -> List[RetrievedChunk]:
        sql = """
        SELECT
            content,
            chapter_number,
            chapter_title,
            COALESCE(metadata, '{}') AS metadata,
            embedding
        FROM rag_chunks
        WHERE project_id = :project_id
        """
        result = await self._client.execute(sql, {"project_id": project_id})  # type: ignore[union-attr]
        scored: List[RetrievedChunk] = []
        for row in self._iter_rows(result):
            stored_embedding = self._from_f32_blob(row.get("embedding"))
            distance = self._cosine_distance(embedding, stored_embedding)
            scored.append(
                RetrievedChunk(
                    content=row.get("content", ""),
                    chapter_number=row.get("chapter_number", 0),
                    chapter_title=row.get("chapter_title"),
                    score=distance,
                    metadata=self._parse_metadata(row.get("metadata")),
                )
            )
        scored.sort(key=lambda item: item.score)
        return scored[:top_k]

    async def _query_summaries_with_python_similarity(
        self,
        *,
        project_id: str,
        embedding: Sequence[float],
        top_k: int,
    ) -> List[RetrievedSummary]:
        sql = """
        SELECT
            chapter_number,
            title,
            summary,
            embedding
        FROM rag_summaries
        WHERE project_id = :project_id
        """
        result = await self._client.execute(sql, {"project_id": project_id})  # type: ignore[union-attr]
        scored: List[RetrievedSummary] = []
        for row in self._iter_rows(result):
            stored_embedding = self._from_f32_blob(row.get("embedding"))
            distance = self._cosine_distance(embedding, stored_embedding)
            scored.append(
                RetrievedSummary(
                    chapter_number=row.get("chapter_number", 0),
                    title=row.get("title", ""),
                    summary=row.get("summary", ""),
                    score=distance,
                )
            )
        scored.sort(key=lambda item: item.score)
        return scored[:top_k]

    @staticmethod
    def _parse_metadata(raw: Any) -> Dict[str, Any]:
        """解析存储的 JSON 文本，确保输出为 dict。"""
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _iter_rows(result: Any) -> Iterable[Dict[str, Any]]:
        """统一处理 libsql 返回的行数据，确保以 dict 形式迭代。"""
        rows = getattr(result, "rows", None)
        if rows is None:
            rows = result
        if not rows:
            return []
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                normalized.append(row)
            elif hasattr(row, "_asdict"):
                normalized.append(row._asdict())  # type: ignore[attr-defined]
            else:
                try:
                    normalized.append(dict(row))
                except Exception:  # pragma: no cover - 无法转换时跳过
                    continue
        return normalized


__all__ = [
    "VectorStoreService",
    "RetrievedChunk",
    "RetrievedSummary",
]
