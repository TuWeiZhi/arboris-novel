#!/bin/bash
# Docker 部署脚本

set -euo pipefail

echo "========================================="
echo "AI-Novel Docker 部署脚本"
echo "========================================="

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ ! -f "deploy/docker-compose.yml" ]; then
    echo -e "${RED}错误：请在项目根目录执行此脚本${NC}"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}警告：未找到 .env 文件${NC}"
    echo "是否使用示例配置创建 .env 文件？(y/n)"
    read -r response
    if [ "$response" = "y" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            echo -e "${GREEN}✓ 已创建 .env 文件，请编辑后重新运行脚本${NC}"
            exit 0
        fi
        echo -e "${RED}错误：未找到 .env.example 文件${NC}"
        exit 1
    fi
    echo -e "${RED}部署已取消${NC}"
    exit 1
fi

set -a
source .env
set +a

DB_PROVIDER="${DB_PROVIDER:-sqlite}"
EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-openai}"

REQUIRED_VARS=("SECRET_KEY" "OPENAI_API_KEY")
if [ "$DB_PROVIDER" = "mysql" ]; then
    REQUIRED_VARS+=("MYSQL_PASSWORD")
fi
if [ "$EMBEDDING_PROVIDER" != "ollama" ] && [ -z "${EMBEDDING_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
    REQUIRED_VARS+=("EMBEDDING_API_KEY")
fi

echo ""
echo "检查必需的环境变量..."
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo -e "${RED}✗ 缺少环境变量: $var${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ $var 已设置${NC}"
done

echo ""
echo "检查 Docker 环境..."
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}错误：未安装 Docker${NC}"
    echo "请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi
echo -e "${GREEN}✓ Docker 已安装${NC}"

if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
else
    echo -e "${RED}错误：未安装 Docker Compose${NC}"
    echo "请先安装 Docker Compose"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose 已安装${NC}"

echo ""
echo "数据库配置："
echo "  提供商: $DB_PROVIDER"
if [ "$DB_PROVIDER" = "mysql" ]; then
    COMPOSE_PROFILES=(--profile mysql)
    echo "  MySQL 主机: ${MYSQL_HOST:-db}"
    echo "  MySQL 端口: ${MYSQL_PORT:-3306}"
    echo "  MySQL 数据库: ${MYSQL_DATABASE:-arboris}"
else
    COMPOSE_PROFILES=()
    echo "  SQLite 路径: ${SQLITE_DB_PATH:-/app/storage/arboris.db}"
fi

if [ "$DB_PROVIDER" = "mysql" ]; then
    echo ""
    echo -e "${YELLOW}是否执行数据库迁移？(y/n)${NC}"
    read -r response
    if [ "$response" = "y" ]; then
        echo "执行数据库迁移..."
        bash deploy/scripts/run_migrations.sh
        echo -e "${GREEN}✓ 数据库迁移完成${NC}"
    fi
fi

echo ""
echo "停止旧容器..."
cd deploy
"${COMPOSE_CMD[@]}" "${COMPOSE_PROFILES[@]}" down || true

echo ""
echo "构建 Docker 镜像..."
"${COMPOSE_CMD[@]}" "${COMPOSE_PROFILES[@]}" build --no-cache

echo ""
echo "启动容器..."
"${COMPOSE_CMD[@]}" "${COMPOSE_PROFILES[@]}" up -d

echo ""
echo "等待服务启动..."
sleep 10

echo ""
echo "检查容器状态..."
"${COMPOSE_CMD[@]}" "${COMPOSE_PROFILES[@]}" ps

echo ""
echo "检查服务健康状态..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ "$RETRY_COUNT" -lt "$MAX_RETRIES" ]; do
    if "${COMPOSE_CMD[@]}" "${COMPOSE_PROFILES[@]}" exec -T app curl -f http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        echo -e "${GREEN}✓ 服务健康检查通过${NC}"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "等待服务启动... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done

if [ "$RETRY_COUNT" -eq "$MAX_RETRIES" ]; then
    echo -e "${RED}✗ 服务健康检查失败${NC}"
    echo "查看日志："
    "${COMPOSE_CMD[@]}" "${COMPOSE_PROFILES[@]}" logs --tail=50 app
    exit 1
fi

cd ..

echo ""
echo "========================================="
echo -e "${GREEN}部署成功！${NC}"
echo "========================================="
echo ""
echo "访问地址："
echo "  前端: http://localhost:${APP_PORT:-80}"
echo "  后端 API: http://localhost:${APP_PORT:-80}/api"
echo "  健康检查: http://localhost:${APP_PORT:-80}/api/health"
echo ""
echo "管理员账号："
echo "  用户名: ${ADMIN_DEFAULT_USERNAME:-admin}"
echo "  密码: ${ADMIN_DEFAULT_PASSWORD:-ChangeMe123!}"
echo ""
echo "查看日志："
echo "  ${COMPOSE_CMD[*]} -f deploy/docker-compose.yml ${COMPOSE_PROFILES[*]} logs -f"
echo ""
echo "停止服务："
echo "  ${COMPOSE_CMD[*]} -f deploy/docker-compose.yml ${COMPOSE_PROFILES[*]} down"
echo ""
