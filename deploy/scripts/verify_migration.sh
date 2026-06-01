#!/bin/bash
# 数据库迁移验证脚本：验证 Alembic 版本与关键表结构。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "========================================="
echo "数据库迁移验证脚本"
echo "========================================="

if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

DB_PROVIDER="${DB_PROVIDER:-sqlite}"
echo "数据库提供方: $DB_PROVIDER"

echo ""
echo "1. 检查 Alembic 当前版本..."
cd "$PROJECT_ROOT/backend"
python -m alembic current

echo ""
echo "2. 检查关键表与字段..."
python - <<'PY'
import asyncio
import sys

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

EXPECTED_TABLES = [
    "users",
    "admin_settings",
    "system_configs",
    "llm_configs",
    "prompts",
    "novel_projects",
    "novel_conversations",
    "novel_blueprints",
    "blueprint_characters",
    "blueprint_relationships",
    "chapter_outlines",
    "chapters",
    "chapter_versions",
    "chapter_evaluations",
    "project_memories",
    "chapter_snapshots",
    "chapter_blueprints",
    "blueprint_templates",
    "character_states",
    "timeline_events",
    "causal_chains",
    "story_time_trackers",
    "foreshadowings",
    "foreshadowing_resolutions",
    "foreshadowing_reminders",
    "foreshadowing_status_history",
    "foreshadowing_analysis",
    "novel_constitutions",
    "writer_personas",
    "factions",
    "faction_members",
    "faction_relationships",
    "faction_relationship_history",
]

EXPECTED_COLUMNS = {
    "chapter_outlines": ["metadata"],
    "foreshadowings": [
        "status",
        "resolved_chapter_number",
        "target_reveal_chapter",
        "related_foreshadowings",
    ],
    "chapter_blueprints": ["involved_foreshadowings", "mission_constraints"],
    "novel_constitutions": ["core_theme", "pov_character", "world_rules"],
}


def inspect_schema(sync_conn):
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    missing_tables = [table for table in EXPECTED_TABLES if table not in tables]
    missing_columns = []
    for table, expected_columns in EXPECTED_COLUMNS.items():
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        for column in expected_columns:
            if column not in columns:
                missing_columns.append(f"{table}.{column}")
    return missing_tables, missing_columns


async def main() -> int:
    engine = create_async_engine(settings.sqlalchemy_database_uri)
    try:
        async with engine.connect() as conn:
            missing_tables, missing_columns = await conn.run_sync(inspect_schema)
    finally:
        await engine.dispose()

    if missing_tables:
        print("缺少关键表:")
        for table in missing_tables:
            print(f"  - {table}")
    else:
        print("✓ 关键表检查通过")

    if missing_columns:
        print("缺少关键字段:")
        for column in missing_columns:
            print(f"  - {column}")
    else:
        print("✓ 关键字段检查通过")

    if missing_tables or missing_columns:
        return 1
    return 0


sys.exit(asyncio.run(main()))
PY

echo ""
echo "========================================="
echo "验证完成"
echo "========================================="
