#!/usr/bin/env bash
# One-command server deployment script.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/all666666all/AI-novel/main/deploy/scripts/server_deploy.sh | bash

set -euo pipefail

APP_NAME="AI-Novel"
REPO_URL="${REPO_URL:-https://github.com/all666666all/AI-novel.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/root/AI-novel}"
APP_PORT="${APP_PORT:-80}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() {
    echo ""
    echo -e "${BLUE}$1${NC}"
}

require_root() {
    if [ "$(id -u)" != "0" ]; then
        echo -e "${RED}Error: this script must be run as root.${NC}"
        exit 1
    fi
}

install_package() {
    local package_name="$1"
    if ! dpkg -s "$package_name" >/dev/null 2>&1; then
        apt-get update
        apt-get install -y "$package_name"
    fi
}

detect_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD=(docker compose)
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD=(docker-compose)
    else
        echo -e "${YELLOW}Docker Compose plugin is missing. Installing docker-compose-plugin...${NC}"
        install_package docker-compose-plugin
        if docker compose version >/dev/null 2>&1; then
            COMPOSE_CMD=(docker compose)
        else
            echo -e "${RED}Error: Docker Compose is not available after installation.${NC}"
            exit 1
        fi
    fi
}

ensure_dependencies() {
    install_package git
    install_package curl
    install_package openssl

    if ! command -v docker >/dev/null 2>&1; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com | bash
    fi

    systemctl start docker
    systemctl enable docker >/dev/null 2>&1 || true
    detect_compose
}

sync_project() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo "Updating existing project at $INSTALL_DIR..."
        git -C "$INSTALL_DIR" fetch origin "$REPO_BRANCH"
        git -C "$INSTALL_DIR" checkout "$REPO_BRANCH"
        git -C "$INSTALL_DIR" pull --ff-only origin "$REPO_BRANCH"
    elif [ -e "$INSTALL_DIR" ]; then
        echo -e "${RED}Error: $INSTALL_DIR exists but is not a Git repository.${NC}"
        exit 1
    else
        echo "Cloning project into $INSTALL_DIR..."
        git clone --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
    fi
}

create_env_file() {
    cd "$INSTALL_DIR"
    if [ -f ".env" ]; then
        echo -e "${GREEN}.env already exists.${NC}"
        return
    fi

    echo "Creating .env with local-deployment defaults..."
    local secret_key
    local mysql_password
    local mysql_root_password
    secret_key="$(openssl rand -hex 32)"
    mysql_password="AI-Novel-MySQL-$(openssl rand -hex 16)"
    mysql_root_password="AI-Novel-Root-$(openssl rand -hex 16)"

    cat > .env <<ENVEOF
# Application
SECRET_KEY=${secret_key}
ENVIRONMENT=production
DEBUG=false
LOGGING_LEVEL=INFO
APP_PORT=${APP_PORT}

# Database: SQLite by default for simple local deployment.
DB_PROVIDER=sqlite
SQLITE_STORAGE_SOURCE=sqlite-data

# MySQL settings are only used when DB_PROVIDER=mysql and the mysql compose profile is enabled.
MYSQL_HOST=db
MYSQL_PORT=3306
MYSQL_USER=arboris
MYSQL_PASSWORD=${mysql_password}
MYSQL_DATABASE=arboris
MYSQL_ROOT_PASSWORD=${mysql_root_password}

# Admin account
ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=Admin123456!
ADMIN_DEFAULT_EMAIL=admin@ai-novel.com

# Main LLM API. Replace these before using generation features.
OPENAI_API_KEY=sk-placeholder-please-replace-with-real-key
OPENAI_API_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_NAME=gpt-4o-mini
WRITER_CHAPTER_VERSION_COUNT=2

# Embeddings: SiliconFlow OpenAI-compatible API.
EMBEDDING_PROVIDER=openai
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=sk-placeholder-please-replace-with-siliconflow-key
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
EMBEDDING_MODEL_VECTOR_SIZE=1024

# Vector store
VECTOR_DB_URL=file:./storage/rag_vectors.db
VECTOR_DB_AUTH_TOKEN=
VECTOR_TOP_K_CHUNKS=5
VECTOR_TOP_K_SUMMARIES=3
VECTOR_CHUNK_SIZE=480
VECTOR_CHUNK_OVERLAP=120

# Registration and optional OAuth
ALLOW_USER_REGISTRATION=true
ENABLE_LINUXDO_LOGIN=false

# Optional SMTP
SMTP_SERVER=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=no-reply@example.com
SMTP_PASSWORD=
EMAIL_FROM=AI-Novel
ENVEOF

    echo -e "${GREEN}.env created.${NC}"
    echo -e "${YELLOW}Edit $INSTALL_DIR/.env and set OPENAI_API_KEY plus EMBEDDING_API_KEY before production use.${NC}"
}

deploy_containers() {
    cd "$INSTALL_DIR/deploy"
    echo "Stopping old containers..."
    "${COMPOSE_CMD[@]}" down 2>/dev/null || true

    echo "Building Docker images..."
    "${COMPOSE_CMD[@]}" build

    echo "Starting containers..."
    "${COMPOSE_CMD[@]}" up -d
}

wait_for_health() {
    local max_retries=30
    local retry=0
    local health_url="http://127.0.0.1:${APP_PORT}/api/health"

    echo "Waiting for service health at $health_url..."
    sleep 10
    while [ "$retry" -lt "$max_retries" ]; do
        if curl -fsS "$health_url" >/dev/null 2>&1; then
            echo -e "${GREEN}Health check passed.${NC}"
            return
        fi
        retry=$((retry + 1))
        echo "Waiting for service startup... ($retry/$max_retries)"
        sleep 2
    done

    echo -e "${RED}Health check failed.${NC}"
    echo "Recent app logs:"
    cd "$INSTALL_DIR/deploy"
    "${COMPOSE_CMD[@]}" logs --tail=80 app || true
    exit 1
}

print_summary() {
    local public_ip
    public_ip="$(curl -fsS https://ifconfig.me 2>/dev/null || echo "SERVER_IP")"

    echo ""
    echo "========================================="
    echo -e "${GREEN}${APP_NAME} deployment finished.${NC}"
    echo "========================================="
    echo "Frontend: http://${public_ip}:${APP_PORT}"
    echo "Local API docs: http://127.0.0.1:${APP_PORT}/api/docs"
    echo ""
    echo "Admin account:"
    echo "  Username: admin"
    echo "  Password: Admin123456!"
    echo ""
    echo "Next steps:"
    echo "  1. Edit API keys: nano $INSTALL_DIR/.env"
    echo "  2. Restart services: cd $INSTALL_DIR/deploy && ${COMPOSE_CMD[*]} restart"
    echo "  3. View logs: cd $INSTALL_DIR/deploy && ${COMPOSE_CMD[*]} logs -f app"
}

echo "========================================="
echo "${APP_NAME} server deployment"
echo "========================================="

require_root
log_step "1. Installing prerequisites..."
ensure_dependencies
log_step "2. Syncing project..."
sync_project
log_step "3. Preparing environment..."
create_env_file
log_step "4. Deploying Docker containers..."
deploy_containers
log_step "5. Running health check..."
wait_for_health
print_summary
