"""测试配置 — SQLite 临时数据库 + 异步客户端。"""
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing")
os.environ.setdefault("DB_PROVIDER", "sqlite")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("ALLOW_USER_REGISTRATION", "true")

from app.db.base import Base
from app.core.security import hash_password
from app.models import User  # noqa: E402


@pytest_asyncio.fixture(scope="session")
async def shared_engine():
    """会话级异步引擎 — SQLite 临时文件。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    url = f"sqlite+aiosqlite:///{tmp.name}"
    tmp.close()
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest_asyncio.fixture(scope="function")
async def session(shared_engine) -> AsyncGenerator[AsyncSession, None]:
    """函数级会话，自动回滚隔离。"""
    factory = async_sessionmaker(shared_engine, expire_on_commit=False)
    async with factory() as s:
        async with s.begin():
            yield s
            await s.rollback()


async def _ensure_user(engine, username: str, email: str, password: str, is_admin: bool) -> None:
    """通过独立会话确保用户存在（跨 HTTP 测试 client 可见）。"""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        async with s.begin():
            from sqlalchemy import select
            result = await s.execute(select(User).where(User.username == username))
            if not result.scalar_one_or_none():
                s.add(User(
                    username=username,
                    email=email,
                    hashed_password=hash_password(password),
                    is_admin=is_admin,
                ))


@pytest_asyncio.fixture(scope="function")
async def client(shared_engine) -> AsyncGenerator[AsyncClient, None]:
    """异步 HTTP 测试客户端 — 自动注入测试数据库会话。"""
    from app.main import app
    from app.db.session import get_session

    factory = async_sessionmaker(shared_engine, expire_on_commit=False)

    async def override_get_session():
        async with factory() as s:
            yield s

    # 跳过 lifespan 避免 Alembic 干扰测试
    _lifespan = app.router.lifespan_context
    app.router.lifespan_context = lambda _: _empty_lifespan()
    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    app.router.lifespan_context = _lifespan


async def _empty_lifespan():
    yield


@pytest_asyncio.fixture(scope="function")
async def auth_headers(client: AsyncClient, shared_engine) -> dict:
    """返回管理员认证头。"""
    await _ensure_user(shared_engine, "testadmin", "admin@example.com", "admin123", True)
    resp = await client.post("/api/auth/token", data={
        "username": "testadmin",
        "password": "admin123",
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def user_headers(client: AsyncClient, shared_engine) -> dict:
    """返回普通用户认证头。"""
    await _ensure_user(shared_engine, "testuser", "user@example.com", "user123", False)
    resp = await client.post("/api/auth/token", data={
        "username": "testuser",
        "password": "user123",
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
