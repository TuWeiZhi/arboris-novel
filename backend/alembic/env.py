"""Alembic 异步环境配置。

从 app.core.config 读取数据库连接串，使用异步引擎执行迁移。
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

from app.core.config import settings
from app.db.base import Base

# 导入所有模型确保 Base.metadata 包含完整表定义
import app.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """从项目配置获取数据库连接串，同时写入 config 供 Alembic 内部引用。"""
    url = settings.sqlalchemy_database_uri
    config.set_main_option("sqlalchemy.url", url)
    return url


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而非直接执行。"""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """在给定的连接上执行迁移。"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步在线模式：创建异步引擎并执行迁移。"""
    configuration = config.get_section(config.config_ini_section, {})
    url = get_url()
    configuration["sqlalchemy.url"] = url

    connectable = create_async_engine(url, poolclass=pool.NullPool)
    async with connectable.begin() as conn:
        await conn.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口，适配 Alembic 同步调用风格。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
