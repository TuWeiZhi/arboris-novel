#!/bin/bash
# 数据库迁移执行脚本：统一使用 Alembic，支持 SQLite 与 MySQL。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "========================================="
echo "数据库迁移执行脚本"
echo "========================================="

if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

DB_PROVIDER="${DB_PROVIDER:-sqlite}"
BACKUP_DIR="$PROJECT_ROOT/backups"

resolve_sqlite_path() {
    local sqlite_path="${SQLITE_DB_PATH:-storage/arboris.db}"
    if [[ "$sqlite_path" = /* ]]; then
        echo "$sqlite_path"
    else
        echo "$PROJECT_ROOT/backend/$sqlite_path"
    fi
}

echo "数据库提供方: $DB_PROVIDER"

if [ "$DB_PROVIDER" = "mysql" ]; then
    DB_HOST="${MYSQL_HOST:-localhost}"
    DB_PORT="${MYSQL_PORT:-3306}"
    DB_USER="${MYSQL_USER:-arboris}"
    DB_PASSWORD="${MYSQL_PASSWORD:-}"
    DB_NAME="${MYSQL_DATABASE:-arboris}"

    if [ -z "$DB_PASSWORD" ]; then
        echo "错误：DB_PROVIDER=mysql 时必须设置 MYSQL_PASSWORD 环境变量"
        exit 1
    fi
    if ! command -v mysql >/dev/null 2>&1; then
        echo "错误：未找到 mysql 客户端，无法检查 MySQL 连接"
        exit 1
    fi
    if ! command -v mysqldump >/dev/null 2>&1; then
        echo "错误：未找到 mysqldump，无法在迁移前创建备份"
        exit 1
    fi

    echo "数据库连接信息："
    echo "  主机: $DB_HOST"
    echo "  端口: $DB_PORT"
    echo "  用户: $DB_USER"
    echo "  数据库: $DB_NAME"
    echo ""

    echo "检查 MySQL 连接..."
    if ! mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "USE \`$DB_NAME\`; SELECT 1;" >/dev/null 2>&1; then
        echo "错误：无法连接到 MySQL 数据库 $DB_NAME"
        exit 1
    fi
    echo "✓ MySQL 连接成功"

    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/mysql_backup_$(date +%Y%m%d_%H%M%S).sql"
    echo "创建 MySQL 备份..."
    mysqldump -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" > "$BACKUP_FILE"
    echo "✓ 备份已保存到: $BACKUP_FILE"
elif [ "$DB_PROVIDER" = "sqlite" ]; then
    SQLITE_ABS_PATH="$(resolve_sqlite_path)"
    echo "SQLite 数据库: $SQLITE_ABS_PATH"
    if [ -f "$SQLITE_ABS_PATH" ]; then
        mkdir -p "$BACKUP_DIR"
        BACKUP_FILE="$BACKUP_DIR/sqlite_backup_$(date +%Y%m%d_%H%M%S).db"
        cp "$SQLITE_ABS_PATH" "$BACKUP_FILE"
        echo "✓ SQLite 备份已保存到: $BACKUP_FILE"
    else
        mkdir -p "$(dirname "$SQLITE_ABS_PATH")"
        echo "ℹ SQLite 数据库尚不存在，将由 Alembic 创建"
    fi
else
    echo "错误：DB_PROVIDER 仅支持 sqlite 或 mysql，当前为: $DB_PROVIDER"
    exit 1
fi

echo ""
echo "执行 Alembic 迁移..."
cd "$PROJECT_ROOT/backend"
python -m alembic upgrade head
python -m alembic current

echo ""
echo "========================================="
echo "迁移完成"
echo "========================================="
echo ""
echo "可运行验证脚本检查迁移结果："
echo "  bash deploy/scripts/verify_migration.sh"
