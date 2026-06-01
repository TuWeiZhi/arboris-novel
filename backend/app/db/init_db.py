# AIMETA P=数据库初始化_创建表和默认数据|R=Alembic迁移_初始化管理员|NR=不含业务逻辑|E=init_db|X=internal|A=初始化函数|D=sqlalchemy,alembic|S=db|RD=./README.ai
import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ..core.config import settings
from ..core.security import hash_password
from ..models import Prompt, SystemConfig, User
from .system_config_defaults import SYSTEM_CONFIG_DEFAULTS
from .session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_ALEMBIC_CFG_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"


async def init_db() -> None:
    """初始化数据库结构并确保默认管理员存在。

    表结构通过 Alembic 迁移管理，
    数据初始化（管理员、系统配置、提示词）在迁移后完成。
    """
    await _ensure_database_exists()

    # Auto-fix Alembic encoding on Windows GBK locale
    _patch_alembic_encoding()

    # ---- 第一步：运行 Alembic 迁移创建/升级表结构 ----
    # Alembic 内部使用 asyncio.run() 创建事件循环，在 FastAPI lifespan
    # 中已有运行中的事件循环，必须在线程中执行避免冲突。
    alembic_cfg = AlembicConfig(str(_ALEMBIC_CFG_PATH))
    alembic_cfg.set_main_option("script_location", str(_ALEMBIC_CFG_PATH.parent / "alembic"))
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    logger.info("数据库表结构已通过 Alembic 迁移初始化")

    # ---- 第二步：确保管理员账号至少存在一个 ----
    async with AsyncSessionLocal() as session:
        admin_exists = await session.execute(select(User).where(User.is_admin.is_(True)))
        if not admin_exists.scalars().first():
            logger.warning("未检测到管理员账号，正在创建默认管理员 ...")
            admin_user = User(
                username=settings.admin_default_username,
                email=settings.admin_default_email,
                hashed_password=hash_password(settings.admin_default_password),
                is_admin=True,
            )
            session.add(admin_user)
            try:
                await session.commit()
                logger.info("默认管理员创建完成：%s", settings.admin_default_username)
            except IntegrityError:
                await session.rollback()
                logger.exception("默认管理员创建失败，可能是并发启动导致，请检查数据库状态")

        # ---- 第三步：同步系统配置到数据库 ----
        for entry in SYSTEM_CONFIG_DEFAULTS:
            value = entry.value_getter(settings)
            if value is None:
                continue
            existing = await session.get(SystemConfig, entry.key)
            if existing:
                if entry.description and existing.description != entry.description:
                    existing.description = entry.description
                continue
            session.add(
                SystemConfig(
                    key=entry.key,
                    value=value,
                    description=entry.description,
                )
            )

        await _ensure_default_prompts(session)
        await session.commit()


def _patch_alembic_encoding() -> None:
    """Windows GBK locale 会导致 alembic 读取 alembic.ini 时乱码，补丁为 UTF-8。"""
    try:
        import alembic.util.compat as compat_module
        _orig_read = compat_module.read_config_parser

        def _utf8_read(file_config, files):
            return file_config.read(files, encoding="utf-8")

        compat_module.read_config_parser = _utf8_read
    except Exception:
        pass


async def _ensure_database_exists() -> None:
    """在首次连接前确认数据库存在，针对不同驱动做最小化准备工作。"""
    url = make_url(settings.sqlalchemy_database_uri)

    if url.get_backend_name() == "sqlite":
        db_path = Path(url.database or "").expanduser()
        if not db_path.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            db_path = (project_root / db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return

    database = (url.database or "").strip("/")
    if not database:
        return

    admin_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=None,
        query=url.query,
    )
    admin_engine = create_async_engine(
        admin_url.render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{database}`"))
    await admin_engine.dispose()


async def _ensure_default_prompts(session: AsyncSession) -> None:
    prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    if not prompts_dir.is_dir():
        return

    result = await session.execute(select(Prompt.name))
    existing_names = set(result.scalars().all())

    for prompt_file in sorted(prompts_dir.glob("*.md")):
        name = prompt_file.stem
        if name in existing_names:
            continue
        content = prompt_file.read_text(encoding="utf-8")
        session.add(Prompt(name=name, content=content))
