# Arboris-Novel 部署文档

本文档是 Arboris-Novel 的主部署说明，覆盖本地开发、快速部署、手动部署、中间件选择、配置参数、日志、迁移和常见维护操作。

## 部署架构

生产镜像由 `deploy/Dockerfile` 构建：

1. 使用 Node 20 构建 `frontend/` 静态资源。
2. 使用 Python 3.11 安装 `backend/requirements.txt`。
3. 将前端产物复制到 Nginx 静态目录。
4. 容器内通过 Supervisor 同时运行：
   - Nginx：监听容器 `80` 端口，托管前端并代理 `/api`。
   - Uvicorn：监听容器本地 `127.0.0.1:8000`。

Docker Compose 默认只启动 `app` 服务。MySQL、Redis 和 Celery Worker 通过 profile 按需启用。

## 环境要求

### Docker 部署

- Linux 服务器、Windows Docker Desktop 或 macOS Docker Desktop。
- Docker 20.10+。
- Docker Compose v2 推荐。
- 至少 2 CPU、4 GB 内存、20 GB 可用磁盘。
- 可访问你的 LLM API 与 Embedding API。

### 本地开发

- Python 3.11 推荐。
- Node.js `^20.19.0` 或 `>=22.12.0`。
- npm。
- 可选：MySQL 8.0、Redis 7、Ollama。

## 配置文件

部署时从示例文件创建根目录 `.env`：

```bash
cp deploy/.env.example .env
```

`docker-compose.yml` 会读取根目录 `.env`。建议启动命令显式带上 `--env-file .env`，避免从其他目录执行时读错配置。

最少需要检查这些配置：

```env
APP_PORT=8088
SECRET_KEY=replace-with-a-random-secret
ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=replace-with-a-strong-password

DB_PROVIDER=sqlite

OPENAI_API_KEY=sk-your-key
OPENAI_API_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_NAME=gpt-4o-mini

EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=sk-your-embedding-key
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
EMBEDDING_MODEL_VECTOR_SIZE=1024

VECTOR_DB_URL=file:./storage/rag_vectors.db
```

`SECRET_KEY` 是唯一严格必需的启动密钥；LLM 与 Embedding 配置决定生成、评审、RAG 和章节定稿是否可用。生产环境不应使用示例密码。

## 快速部署

### 默认 SQLite

适合个人使用、体验环境和小规模部署。

```bash
cp deploy/.env.example .env

# 编辑 .env 后启动
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
```

访问：

```text
http://localhost:8088
```

如果修改了 `APP_PORT`，访问对应端口。

检查状态：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env ps
curl http://localhost:8088/api/health
```

### 使用 Compose 内置 MySQL

适合希望使用 MySQL，但不想单独维护数据库服务的部署。

`.env`：

```env
DB_PROVIDER=mysql
MYSQL_HOST=db
MYSQL_PORT=3306
MYSQL_USER=arboris
MYSQL_PASSWORD=replace-with-strong-password
MYSQL_DATABASE=arboris
MYSQL_ROOT_PASSWORD=replace-with-root-password
```

启动：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env --profile mysql up -d --build
```

### 使用外部 MySQL

适合已有云数据库、RDS 或宿主机 MySQL。

`.env`：

```env
DB_PROVIDER=mysql
MYSQL_HOST=your-db-host
MYSQL_PORT=3306
MYSQL_USER=your-db-user
MYSQL_PASSWORD=your-db-password
MYSQL_DATABASE=arboris
```

启动时不需要 `mysql` profile：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
```

如果 MySQL 在宿主机，Linux 下通常需要使用宿主机网关地址；Docker Desktop 可尝试 `host.docker.internal`。

### 启用 Redis 和 Celery Worker

默认应用可以不启用 Worker。需要后台异步任务、Redis 缓存或将耗时任务拆出时再启用。

```bash
docker compose -f deploy/docker-compose.yml --env-file .env --profile worker up -d --build
```

同时启用内置 MySQL 和 Worker：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env --profile mysql --profile worker up -d --build
```

## 使用部署脚本

项目包含 `deploy/scripts/deploy_docker.sh`，适合已经在项目根目录准备好 `.env` 后执行：

```bash
cp deploy/.env.example .env
# 编辑 .env
bash deploy/scripts/deploy_docker.sh
```

注意：

- 脚本必须在项目根目录执行。
- 脚本会校验 `SECRET_KEY`、`OPENAI_API_KEY`，MySQL 模式下还会校验 `MYSQL_PASSWORD`。
- 脚本会根据 `DB_PROVIDER=mysql` 自动带上 `mysql` profile。
- 如果还没有 `.env`，请手动从 `deploy/.env.example` 复制；不要依赖脚本自动复制。

`deploy/scripts/server_deploy.sh` 是服务器一键安装脚本，但默认仓库地址和安装目录可能不符合当前仓库。使用前请显式指定：

```bash
REPO_URL=https://github.com/TuWeiZhi/arboris-novel.git \
INSTALL_DIR=/root/arboris-novel \
APP_PORT=80 \
bash deploy/scripts/server_deploy.sh
```

`deploy/scripts/quick_deploy.sh` 内含固定服务器 IP 和旧项目路径，仅适合定制后内部使用。

## 手动部署

### 方式一：手动 Compose 部署

```bash
git clone https://github.com/TuWeiZhi/arboris-novel.git
cd arboris-novel

cp deploy/.env.example .env
nano .env

docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
docker compose -f deploy/docker-compose.yml --env-file .env logs -f app
```

更新：

```bash
git pull
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
```

停止：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env down
```

### 方式二：本机开发运行

后端：

```bash
cd backend
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

开发态前端访问 `http://127.0.0.1:5173`。Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

本机开发也需要环境变量。可以在项目根目录、`backend/.env` 或 shell 环境中设置，优先级见 `backend/app/core/config.py`。

### 方式三：非 Docker 生产部署

不推荐作为首选，但可以用于已有服务器栈。

1. 构建前端：

   ```bash
   cd frontend
   npm install
   npm run build
   ```

2. 准备后端：

   ```bash
   cd ../backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python -m alembic upgrade head
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

3. 配置 Nginx：

   - 静态目录指向 `frontend/dist`。
   - `/api/` 反向代理到 `http://127.0.0.1:8000`。
   - SPA 路由使用 `try_files $uri $uri/ /index.html`。
   - 长时间 AI 请求建议 `proxy_read_timeout 600s`。

4. 使用 systemd、supervisor 或进程管理工具守护 Uvicorn。

Docker 镜像中的参考配置位于 `deploy/nginx.conf` 和 `deploy/supervisord.conf`。

## 中间件选择

| 组件 | 默认 | 是否必需 | 何时启用 | 配置 |
| --- | --- | --- | --- | --- |
| Nginx | 应用容器内置 | 必需 | 生产镜像默认启用 | `deploy/nginx.conf` |
| Uvicorn | 应用容器内置 | 必需 | FastAPI 服务 | `deploy/supervisord.conf` |
| SQLite | 默认数据库 | 必需其一 | 个人、小规模、快速部署 | `DB_PROVIDER=sqlite` |
| MySQL 8 | 可选 | 必需其一 | 多用户、长期生产、便于备份 | `DB_PROVIDER=mysql` |
| Alembic | 内置 | 必需 | 管理数据库结构 | 应用启动自动运行 |
| libSQL 向量库 | 默认本地文件 | RAG 需要 | 长篇记忆、章节定稿、上下文检索 | `VECTOR_DB_URL` |
| Embedding API | 默认 OpenAI-compatible | RAG 需要 | 向量化和检索 | `EMBEDDING_*` |
| Ollama | 可选 | 否 | 本地嵌入模型 | `EMBEDDING_PROVIDER=ollama` |
| Redis | 可选 | 否 | Worker、缓存、异步任务 | `--profile worker` |
| Celery Worker | 可选 | 否 | 后台任务执行 | `--profile worker` |
| SMTP | 可选 | 否 | 邮件验证码、注册流程 | `SMTP_*` |
| Linux.do OAuth | 可选 | 否 | 第三方登录 | `ENABLE_LINUXDO_LOGIN=true` |
| 外层 HTTPS 代理 | 可选但推荐 | 否 | 生产公网访问 | Caddy/Nginx/负载均衡 |

### 选型建议

- 个人试用：SQLite + 默认本地 libSQL + 远程 LLM/Embedding。
- 小团队：MySQL + 默认本地 libSQL + 远程 LLM/Embedding。
- 生产公网：MySQL + 宿主机/云端备份 + HTTPS 反代 + 关闭默认密码 + 按需启用 Worker。
- 本地隐私优先：SQLite/MySQL + Ollama 嵌入模型 + 自托管 OpenAI-compatible LLM。

## 参数说明

### 应用与安全

| 参数 | 默认 | 必填 | 说明 |
| --- | --- | --- | --- |
| `APP_PORT` | `8088` 示例值，Compose 默认 `80` | 否 | 映射到宿主机的 HTTP 端口 |
| `SECRET_KEY` | 无 | 是 | JWT 加密密钥，使用 `openssl rand -hex 32` 生成 |
| `ENVIRONMENT` | `production` | 否 | 环境标识 |
| `DEBUG` | `false` | 否 | 生产环境保持 `false` |
| `LOGGING_LEVEL` | `INFO` | 否 | `CRITICAL`、`ERROR`、`WARNING`、`INFO`、`DEBUG`、`NOTSET` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | 否 | JWT 过期时间，单位分钟 |

### 管理员

| 参数 | 默认 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ADMIN_DEFAULT_USERNAME` | `admin` | 否 | 首次启动时创建默认管理员 |
| `ADMIN_DEFAULT_PASSWORD` | `ChangeMe123!` | 强烈建议设置 | 生产环境必须修改 |
| `ADMIN_DEFAULT_EMAIL` | `admin@example.com` | 否 | 管理员邮箱 |

只有数据库中不存在任何管理员时，启动过程才会创建默认管理员。

### 数据库

| 参数 | 默认 | 必填 | 说明 |
| --- | --- | --- | --- |
| `DATABASE_URL` | 空 | 否 | 完整 SQLAlchemy 异步连接串；设置后覆盖下方数据库配置 |
| `DB_PROVIDER` | Compose 默认 `sqlite` | 否 | `sqlite` 或 `mysql` |
| `SQLITE_DB_PATH` | `/app/storage/arboris.db` | SQLite 时否 | 容器内 SQLite 文件路径 |
| `SQLITE_STORAGE_SOURCE` | `sqlite-data` volume | 否 | SQLite 持久化来源，可设为 `./storage` |
| `MYSQL_HOST` | `db` | MySQL 时是 | 内置 MySQL 用 `db`，外部 MySQL 填真实地址 |
| `MYSQL_PORT` | `3306` | 否 | MySQL 端口 |
| `MYSQL_USER` | `arboris` | MySQL 时是 | MySQL 用户 |
| `MYSQL_PASSWORD` | 空 | MySQL 时是 | MySQL 密码 |
| `MYSQL_DATABASE` | `arboris` | MySQL 时是 | 数据库名 |
| `MYSQL_ROOT_PASSWORD` | 示例值 | 内置 MySQL 时是 | MySQL root 密码 |

### LLM

| 参数 | 默认 | 必填 | 说明 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | 空 | 生成时需要 | 默认 LLM API Key |
| `OPENAI_API_BASE_URL` | `https://api.openai.com/v1` | 否 | OpenAI-compatible Base URL |
| `OPENAI_MODEL_NAME` | Compose 默认 `gpt-3.5-turbo` | 否 | 默认生成模型 |
| `WRITER_CHAPTER_VERSION_COUNT` | `2` | 否 | 每次生成章节的候选版本数量 |

模型配置也会初始化进 `system_configs`，后续可在后台管理中调整。

### Embedding 与向量库

| 参数 | 默认 | 必填 | 说明 |
| --- | --- | --- | --- |
| `EMBEDDING_PROVIDER` | `openai` | RAG 时需要 | `openai` 或 `ollama` |
| `EMBEDDING_BASE_URL` | `https://api.siliconflow.cn/v1` | OpenAI-compatible 嵌入时需要 | 嵌入 API Base URL |
| `EMBEDDING_API_KEY` | 默认可复用 `OPENAI_API_KEY` | OpenAI-compatible 嵌入时需要 | 嵌入 API Key |
| `EMBEDDING_MODEL` | `Qwen/Qwen3-Embedding-8B` | RAG 时需要 | 嵌入模型名称 |
| `EMBEDDING_MODEL_VECTOR_SIZE` | `1024` | RAG 时需要 | 嵌入维度，必须和模型一致 |
| `OLLAMA_EMBEDDING_BASE_URL` | `http://localhost:11434` | Ollama 时需要 | Docker 中通常用 `http://host.docker.internal:11434` |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text:latest` | Ollama 时需要 | Ollama 模型名 |
| `VECTOR_DB_URL` | `file:./storage/rag_vectors.db` | RAG 时需要 | 本地或远程 libSQL 地址 |
| `VECTOR_DB_AUTH_TOKEN` | 空 | 远程 libSQL 时需要 | 远程向量库令牌 |
| `VECTOR_TOP_K_CHUNKS` | `5` | 否 | 检索剧情 chunk 数 |
| `VECTOR_TOP_K_SUMMARIES` | `3` | 否 | 检索章节摘要数 |
| `VECTOR_CHUNK_SIZE` | `480` | 否 | 分块目标字数 |
| `VECTOR_CHUNK_OVERLAP` | `120` | 否 | 分块重叠字数 |

更换嵌入模型后，如果维度不同，需要修改 `EMBEDDING_MODEL_VECTOR_SIZE` 并重建向量索引。

### 注册、邮件与 OAuth

| 参数 | 默认 | 必填 | 说明 |
| --- | --- | --- | --- |
| `ALLOW_USER_REGISTRATION` | 示例中为 `false` | 否 | 是否允许自助注册 |
| `SMTP_SERVER` | 示例值 | 开放邮件验证码时需要 | SMTP 服务地址 |
| `SMTP_PORT` | `465` 示例值 | 邮件时需要 | SMTP 端口 |
| `SMTP_USERNAME` | 示例值 | 邮件时需要 | SMTP 用户名 |
| `SMTP_PASSWORD` | 空 | 邮件时需要 | SMTP 密码 |
| `EMAIL_FROM` | `Arboris` | 否 | 邮件发件人显示 |
| `ENABLE_LINUXDO_LOGIN` | `false` | 否 | 是否启用 Linux.do OAuth |
| `LINUXDO_CLIENT_ID` | 空 | OAuth 时需要 | Client ID |
| `LINUXDO_CLIENT_SECRET` | 空 | OAuth 时需要 | Client Secret |
| `LINUXDO_REDIRECT_URI` | 空 | OAuth 时需要 | 回调地址 |

## 数据持久化

### SQLite

默认使用 Docker volume：

```env
SQLITE_STORAGE_SOURCE=sqlite-data
SQLITE_DB_PATH=/app/storage/arboris.db
VECTOR_DB_URL=file:./storage/rag_vectors.db
```

如需直接在宿主机看到数据库文件：

```env
SQLITE_STORAGE_SOURCE=./storage
```

这样应用数据库和本地向量库都会落在宿主机 `./storage` 目录。

### MySQL

内置 MySQL 使用 Docker volume `mysql-data`。生产环境建议配合定期备份，或直接使用外部云数据库。

## 数据库迁移

应用启动时会自动执行：

```bash
python -m alembic upgrade head
```

也可以手动执行迁移：

```bash
cd backend
python -m alembic upgrade head
python -m alembic current
```

项目脚本：

```bash
bash deploy/scripts/run_migrations.sh
bash deploy/scripts/verify_migration.sh
```

注意：

- 脚本在宿主机执行，需要已安装 Python 依赖。
- MySQL 模式下脚本还需要 `mysql` 和 `mysqldump` 客户端。
- Docker 部署通常不必手动跑迁移，除非你要在上线前单独验证。

## 日志与排查

### 查看容器状态

```bash
docker compose -f deploy/docker-compose.yml --env-file .env ps
```

### 应用日志

```bash
docker compose -f deploy/docker-compose.yml --env-file .env logs -f app
docker compose -f deploy/docker-compose.yml --env-file .env logs --tail=100 app
```

后端日志输出到容器 stdout/stderr，受 `LOGGING_LEVEL` 控制。

### Nginx 日志

容器内路径：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env exec app tail -f /var/log/nginx/access.log
docker compose -f deploy/docker-compose.yml --env-file .env exec app tail -f /var/log/nginx/error.log
```

### Supervisor 状态

```bash
docker compose -f deploy/docker-compose.yml --env-file .env exec app supervisorctl status
```

### MySQL 日志

```bash
docker compose -f deploy/docker-compose.yml --env-file .env --profile mysql logs -f db
```

### Redis 和 Worker 日志

```bash
docker compose -f deploy/docker-compose.yml --env-file .env --profile worker logs -f redis
docker compose -f deploy/docker-compose.yml --env-file .env --profile worker logs -f worker
```

### 健康检查

```bash
curl http://localhost:8088/api/health
```

正常响应类似：

```json
{
  "status": "healthy",
  "app": "AI Novel Generator API",
  "version": "1.0.0"
}
```

如果改了 `APP_PORT`，把 `8088` 替换为实际端口。

## 备份与恢复

### SQLite 备份

如果使用宿主机目录：

```bash
mkdir -p backups
cp storage/arboris.db backups/arboris_$(date +%Y%m%d_%H%M%S).db
cp storage/rag_vectors.db backups/rag_vectors_$(date +%Y%m%d_%H%M%S).db
```

如果使用 Docker volume，可直接从容器复制：

```bash
mkdir -p backups
docker compose -f deploy/docker-compose.yml --env-file .env cp app:/app/storage/arboris.db backups/arboris.db
docker compose -f deploy/docker-compose.yml --env-file .env cp app:/app/storage/rag_vectors.db backups/rag_vectors.db
```

恢复前先停止服务，再覆盖数据库文件。

### MySQL 备份

内置 MySQL：

```bash
mkdir -p backups
docker compose -f deploy/docker-compose.yml --env-file .env --profile mysql exec -T db \
  sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  > backups/arboris_$(date +%Y%m%d_%H%M%S).sql
```

外部 MySQL 请使用你的数据库平台备份能力，或在可访问数据库的机器上运行 `mysqldump`。

### 回滚脚本

`deploy/scripts/rollback.sh` 主要面向 MySQL `.sql` 备份，且使用 `docker-compose` 命令。SQLite 恢复建议手动停止服务后替换 `.db` 文件。

## HTTPS 与反向代理

应用容器只提供 HTTP。公网生产建议在外层放 Caddy、Nginx、Traefik 或云负载均衡，并终止 HTTPS。

外层反代应转发到宿主机 `APP_PORT`：

```nginx
location / {
    proxy_pass http://127.0.0.1:8088;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
}
```

## 常见问题

### 容器启动后马上退出

查看日志：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env logs --tail=100 app
```

常见原因：

- `SECRET_KEY` 未设置。
- `.env` 路径不对，Compose 没读到变量。
- MySQL 参数错误。
- 端口被占用。
- 外部 API 地址无法访问。

### 访问前端正常，但生成失败

检查：

- `OPENAI_API_KEY` 是否有效。
- `OPENAI_API_BASE_URL` 是否为 OpenAI-compatible API。
- `OPENAI_MODEL_NAME` 是否存在。
- 后台系统配置是否覆盖了 `.env` 初始值。
- 日志中是否有超时、余额不足或 JSON 解析错误。

### RAG 或定稿时报嵌入错误

检查：

- `EMBEDDING_PROVIDER` 是否为 `openai` 或 `ollama`。
- OpenAI-compatible 嵌入服务是否可访问。
- `EMBEDDING_API_KEY` 是否正确。
- `EMBEDDING_MODEL_VECTOR_SIZE` 是否与模型实际维度一致。
- `VECTOR_DB_URL` 是否可写。

### MySQL 连接失败

检查：

```bash
docker compose -f deploy/docker-compose.yml --env-file .env --profile mysql ps
docker compose -f deploy/docker-compose.yml --env-file .env --profile mysql logs --tail=100 db
```

如果使用外部 MySQL，确认应用容器能访问数据库地址，防火墙和白名单已放行。

### 管理员密码没有按 `.env` 更新

默认管理员只会在“数据库中没有任何管理员”时创建。已有管理员后，修改 `.env` 不会覆盖数据库中的密码。请在后台修改密码，或在确认数据可丢弃后清空数据库重新初始化。

### 前端路由刷新 404

生产镜像内置 Nginx 已配置 SPA fallback。非 Docker 部署时需要在自己的 Nginx 中配置：

```nginx
try_files $uri $uri/ /index.html;
```

### AI 请求超时

内置 Nginx 已将 API 代理超时设置为 600 秒。外层反向代理也需要同步设置较长的 `proxy_read_timeout`。

## 生产建议

- 使用强随机 `SECRET_KEY`。
- 修改默认管理员密码。
- 关闭不需要的自助注册：`ALLOW_USER_REGISTRATION=false`。
- 使用 HTTPS。
- 持久化 `storage`，并定期备份数据库和向量库。
- MySQL 密码不要包含未转义的特殊 shell 字符，或确保 `.env` 写法正确。
- 不要把 `.env` 提交到 Git。
- 需要多用户长期运行时优先使用 MySQL。
- 需要后台任务时再启用 `worker` profile，避免不必要的 Redis 维护成本。
- 更换嵌入模型后重建向量索引。

## 维护命令速查

```bash
# 启动
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build

# 启动 MySQL profile
docker compose -f deploy/docker-compose.yml --env-file .env --profile mysql up -d --build

# 启动 Worker profile
docker compose -f deploy/docker-compose.yml --env-file .env --profile worker up -d --build

# 查看状态
docker compose -f deploy/docker-compose.yml --env-file .env ps

# 查看日志
docker compose -f deploy/docker-compose.yml --env-file .env logs -f app

# 重启应用
docker compose -f deploy/docker-compose.yml --env-file .env restart app

# 停止
docker compose -f deploy/docker-compose.yml --env-file .env down

# 进入容器
docker compose -f deploy/docker-compose.yml --env-file .env exec app bash

# 健康检查
curl http://localhost:8088/api/health
```
