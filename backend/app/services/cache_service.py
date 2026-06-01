# AIMETA P=缓存服务_Redis缓存操作|R=异步缓存读写_失效|NR=同步兼容Celery|E=CacheService|X=internal|A=服务类|D=redis|S=cache|RD=./README.ai
"""Redis 缓存服务 — 同时支持异步（FastAPI）和同步（Celery）调用。"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import redis
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

DEFAULT_TTL = 3600


class CacheService:
    """Redis 缓存服务。

    内部维护两套客户端：
    - _redis: 同步客户端，供 Celery 任务使用
    - _aredis: 异步客户端，供 FastAPI 路由使用
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self._redis: Optional[redis.Redis] = None
        self._aredis: Optional[aioredis.Redis] = None
        self._redis_url = redis_url

        try:
            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            logger.info("Redis (sync) 连接成功")
        except Exception as e:
            logger.warning("Redis (sync) 连接失败: %s，缓存功能将被禁用", e)
            self._redis = None

        self._aredis = None  # 延迟初始化，避免在非 async 上下文中创建

        self.EMOTION_CURVE_TTL = 7 * 24 * 3600
        self.EMOTION_META_TTL = 24 * 3600
        self.EMOTION_TASK_TTL = 3600

    # ── 异步客户端延迟初始化 ──

    async def _ensure_async(self) -> Optional[aioredis.Redis]:
        if self._aredis is not None:
            return self._aredis
        if self._redis is None:
            return None  # sync 连接失败，async 也跳过
        try:
            self._aredis = aioredis.from_url(self._redis_url, decode_responses=True)
            return self._aredis
        except Exception as e:
            logger.warning("Redis (async) 初始化失败: %s", e)
            self._aredis = None
            return None

    def is_available(self) -> bool:
        return self._redis is not None

    # ── 通用异步方法（analytics_enhanced 使用） ──

    async def get(self, key: str) -> Optional[str]:
        client = await self._ensure_async()
        if client is None:
            return None
        try:
            return await client.get(key)
        except Exception as e:
            logger.warning("缓存 get(%s) 失败: %s", key, e)
            return None

    async def set(self, key: str, value: str, ttl: int = DEFAULT_TTL) -> bool:
        client = await self._ensure_async()
        if client is None:
            return False
        try:
            await client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.warning("缓存 set(%s) 失败: %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        client = await self._ensure_async()
        if client is None:
            return False
        try:
            await client.delete(key)
            return True
        except Exception as e:
            logger.warning("缓存 delete(%s) 失败: %s", key, e)
            return False

    # ── 情感曲线缓存（同步，Celery 使用） ──

    def get_emotion_curve(self, novel_id: str) -> Optional[Dict]:
        if not self.is_available():
            return None
        try:
            data = self._redis.get(f"emotion_curve:{novel_id}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning("获取情感曲线缓存失败: %s", e)
            return None

    def set_emotion_curve(self, novel_id: str, data: Dict) -> bool:
        if not self.is_available():
            return False
        try:
            self._redis.setex(
                f"emotion_curve:{novel_id}",
                self.EMOTION_CURVE_TTL,
                json.dumps(data, default=str, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.warning("设置情感曲线缓存失败: %s", e)
            return False

    def get_emotion_meta(self, novel_id: str) -> Optional[Dict]:
        if not self.is_available():
            return None
        try:
            data = self._redis.get(f"emotion_meta:{novel_id}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning("获取情感元数据缓存失败: %s", e)
            return None

    def set_emotion_meta(self, novel_id: str, meta: Dict) -> bool:
        if not self.is_available():
            return False
        try:
            self._redis.setex(
                f"emotion_meta:{novel_id}",
                self.EMOTION_META_TTL,
                json.dumps(meta, default=str, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.warning("设置情感元数据缓存失败: %s", e)
            return False

    def get_chapter_emotion(self, novel_id: str, chapter_id: str) -> Optional[Dict]:
        if not self.is_available():
            return None
        try:
            data = self._redis.get(f"emotion:{novel_id}:{chapter_id}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning("获取章节情感缓存失败: %s", e)
            return None

    def set_chapter_emotion(self, novel_id: str, chapter_id: str, data: Dict) -> bool:
        if not self.is_available():
            return False
        try:
            self._redis.setex(
                f"emotion:{novel_id}:{chapter_id}",
                self.EMOTION_CURVE_TTL,
                json.dumps(data, default=str, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.warning("设置章节情感缓存失败: %s", e)
            return False

    def invalidate_emotion_cache(self, novel_id: str) -> bool:
        if not self.is_available():
            return False
        try:
            keys = self._redis.keys(f"emotion*:{novel_id}*")
            if keys:
                self._redis.delete(*keys)
            return True
        except Exception as e:
            logger.warning("清除情感曲线缓存失败: %s", e)
            return False

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        if not self.is_available():
            return None
        try:
            data = self._redis.get(f"task:{task_id}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning("获取任务状态失败: %s", e)
            return None

    def set_task_status(self, task_id: str, status: Dict) -> bool:
        if not self.is_available():
            return False
        try:
            self._redis.setex(
                f"task:{task_id}",
                self.EMOTION_TASK_TTL,
                json.dumps(status, default=str, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.warning("设置任务状态失败: %s", e)
            return False
