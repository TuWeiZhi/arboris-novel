# Arboris-Novel

Arboris-Novel 是一个面向长篇小说创作者的 Web 写作辅助系统。它不是单纯的“自动续写器”，而是围绕小说项目、世界设定、角色状态、章节蓝图、长程记忆和 AI 评审搭建的创作工作台，帮助作者把灵感整理成可持续推进的作品。

当前项目采用前后端分离开发，生产镜像内置前端静态资源、Nginx 和 FastAPI 服务。默认使用 SQLite 即可启动，也可以切换到 MySQL、Redis/Celery 和外部向量/嵌入服务。

## 核心功能

### 小说项目管理

- 创建、导入、查看和删除小说项目。
- 维护作品名称、类型、简介、蓝图、大纲、章节和版本。
- 支持管理员查看所有小说项目，普通用户只管理自己的作品。

### 灵感到蓝图

- 通过灵感对话把零散设想整理成项目方向。
- 自动生成或手动编辑小说蓝图。
- 支持角色、关系、地点、世界观规则、章节大纲等结构化信息。

### 写作台

- 按章节生成正文，支持一次生成多个候选版本。
- 支持选择版本、编辑章节、快速修改章节和删除章节。
- 章节生成会结合项目设定、章节目标、上下文记忆、伏笔信息和写作人格。
- 支持章节定稿流程，定稿后更新项目记忆、角色状态、章节快照和向量索引。

### 长篇一致性

- 小说宪法：记录核心主题、叙事边界、POV、世界规则等硬约束。
- 作者人格：维护作品语气、叙述偏好、禁用写法和风格要求。
- 项目记忆：维护全局摘要、剧情线、时间线和章节快照。
- 角色状态：跟踪角色位置、能力、关系、知识边界和情绪状态。
- 设定条目：通过 canon 管理固定事实，降低前后矛盾。

### 伏笔与势力

- 创建、追踪、分析和回收伏笔。
- 支持伏笔提醒、状态历史、相关伏笔和目标回收章节。
- 支持派系、成员关系、阵营关系和关系变化历史。

### RAG 与知识检索

- 每章定稿后可将章节文本分块、向量化并写入 libSQL 向量库。
- 生成新章节时检索相关剧情 chunk、章节摘要和项目记忆。
- 支持 OpenAI-compatible Embeddings，也支持 Ollama 本地嵌入模型。
- 默认向量库为本地 libSQL 文件，生产环境可切换到远程 libSQL/Turso。

### 分析与评审

- 情绪曲线、故事轨迹、节奏建议和伏笔分析。
- 六维评审与一致性检查，辅助发现逻辑、角色、节奏和文风问题。
- 分层优化器可针对心理、环境、节奏、对话等维度给出修改建议。

### 账户、配置与后台

- 用户注册、登录、JWT 鉴权和管理员账户。
- 可关闭自助注册，或启用 Linux.do OAuth 登录。
- 支持邮件验证码配置。
- 管理员后台可管理用户、提示词、系统配置、更新日志、默认模型与每日请求限制。
- 用户可配置个人 LLM 参数；系统也可提供默认 LLM 配置。

## 使用流程

1. 管理员首次登录

   部署后使用 `.env` 中的 `ADMIN_DEFAULT_USERNAME` 和 `ADMIN_DEFAULT_PASSWORD` 登录。首次上线请立即修改默认管理员密码。

2. 配置模型

   在 `.env` 或后台系统配置中设置 LLM API Key、Base URL、模型名称、嵌入模型和 SMTP 等参数。OpenAI-compatible 服务可通过 `OPENAI_API_BASE_URL` 接入。

3. 创建小说项目

   进入工作区创建项目，也可以通过导入文本创建。先补充作品简介、世界观、角色、派系、地点和初始大纲。

4. 生成蓝图和章节大纲

   使用灵感对话或蓝图生成能力整理主线、章节目标和关键冲突。章节生成前建议先确认对应章节大纲。

5. 写作与评审

   在写作台生成章节，选择候选版本，手动编辑后定稿。需要时运行六维评审、一致性检查、伏笔分析或分层优化。

6. 长篇推进

   定稿后的章节会沉淀为项目记忆、章节快照和向量检索材料，后续章节会继续引用这些信息，帮助保持上下文连续。

## 快速开始

推荐使用 Docker Compose，默认 SQLite 无需单独安装数据库。

```bash
cp deploy/.env.example .env

# 编辑 .env，至少设置：
# - SECRET_KEY
# - ADMIN_DEFAULT_PASSWORD
# - OPENAI_API_KEY / OPENAI_API_BASE_URL / OPENAI_MODEL_NAME
# - EMBEDDING_API_KEY（使用 RAG/章节定稿向量化时需要）

docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
```

启动后访问：

- 前端：`http://localhost:${APP_PORT}`，默认 `http://localhost:8088`
- 健康检查：`http://localhost:${APP_PORT}/api/health`
- 本地后端开发 API 文档：`http://127.0.0.1:8000/docs`

完整部署、开发环境、MySQL、Redis/Celery、日志和配置说明见 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)。

## 本地开发

### 后端

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

后端启动时会自动执行 Alembic 迁移，并初始化管理员、系统配置和默认提示词。

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器默认运行在 `http://127.0.0.1:5173`。开发态 `/api` 会由 Vite 代理到 `http://127.0.0.1:8000`。

### 常用命令

```bash
# 后端迁移
cd backend
python -m alembic upgrade head

# 后端测试
cd backend
pytest

# 前端类型检查与构建
cd frontend
npm run build

# 前端格式化
npm run format
```

## 技术架构

### 前端

- Vue 3
- TypeScript
- Vite 7
- Vue Router
- Pinia
- Naive UI
- Tailwind CSS
- Chart.js
- marked

### 后端

- Python 3.11 推荐
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic Settings
- OpenAI Python SDK
- libSQL client
- LangChain text splitters
- Celery + Redis（可选）
- MySQL asyncmy 或 SQLite aiosqlite

### 部署

- Docker multi-stage build
- Node 20 构建前端
- Python 3.11 运行后端
- Nginx 托管前端并代理 `/api`
- Supervisor 管理 Nginx 与 Uvicorn
- Docker Compose profiles 管理可选 MySQL、Redis 和 Celery Worker

## 项目结构

```text
.
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/routers/     # REST API 路由
│   │   ├── core/            # 配置、依赖和安全
│   │   ├── db/              # 数据库会话、初始化和默认配置
│   │   ├── models/          # SQLAlchemy ORM 模型
│   │   ├── repositories/    # 数据访问层
│   │   ├── schemas/         # Pydantic 请求/响应模型
│   │   └── services/        # 写作、记忆、评审、RAG 等业务服务
│   ├── alembic/             # 数据库迁移
│   └── prompts/             # 默认提示词模板
├── frontend/                # Vue 前端
│   └── src/
│       ├── api/             # API 客户端
│       ├── components/      # 页面组件与写作台组件
│       ├── router/          # 路由
│       ├── stores/          # Pinia 状态
│       └── views/           # 页面视图
├── deploy/                  # Docker、Nginx、Supervisor 和部署脚本
├── docs/                    # 设计补充材料
├── README.md                # 项目说明
└── DEPLOYMENT_GUIDE.md      # 部署说明
```

## 主要 API 模块

- `/api/auth`：注册、登录、当前用户、登录选项、Linux.do OAuth。
- `/api/novels`：小说项目、导入、章节、灵感对话、蓝图生成与保存。
- `/api/writer`：章节生成、多版本选择、评审、章节编辑、定稿。
- `/api/projects`：小说宪法、作者人格、项目记忆、canon、角色状态、派系和向量重建。
- `/api/analytics`：情绪曲线、伏笔分析、增强分析和故事轨迹。
- `/api/optimizer`：分层优化建议与应用。
- `/api/review`：六维评审和一致性检查。
- `/api/admin`：用户、项目、提示词、系统配置、更新日志和请求限制。
- `/api/llm-config`：用户级 LLM 配置和模型探测。
- `/api/updates`：更新日志查询。
- `/api/health`：健康检查。

## 配置概览

常用配置位于根目录 `.env`，示例见 `deploy/.env.example`。

| 配置项 | 说明 |
| --- | --- |
| `APP_PORT` | Docker 部署时暴露的 HTTP 端口 |
| `SECRET_KEY` | JWT 加密密钥，生产环境必须使用随机长字符串 |
| `DB_PROVIDER` | `sqlite` 或 `mysql` |
| `SQLITE_STORAGE_SOURCE` | SQLite 持久化位置，默认 Docker volume |
| `MYSQL_*` | MySQL 连接参数，使用 MySQL 时配置 |
| `OPENAI_API_KEY` | 默认 LLM API Key |
| `OPENAI_API_BASE_URL` | OpenAI-compatible API Base URL |
| `OPENAI_MODEL_NAME` | 默认生成模型 |
| `WRITER_CHAPTER_VERSION_COUNT` | 每次章节生成的候选版本数量 |
| `EMBEDDING_PROVIDER` | `openai` 或 `ollama` |
| `EMBEDDING_*` | RAG 嵌入模型配置 |
| `VECTOR_DB_URL` | libSQL 向量库地址 |
| `ALLOW_USER_REGISTRATION` | 是否允许自助注册 |
| `ENABLE_LINUXDO_LOGIN` | 是否启用 Linux.do 登录 |
| `SMTP_*` | 邮件验证码相关配置 |

## 常见问题

### 提示未配置 LLM API Key

检查 `.env` 中的 `OPENAI_API_KEY`，或在后台系统配置/个人设置中配置可用的 OpenAI-compatible API Key。

### 生成质量不稳定

优先补全项目设定、章节大纲、人物关系和小说宪法；再调整模型、Base URL、章节候选版本数量和提示词模板。

### JSON 解析失败

部分模型不擅长稳定输出结构化 JSON。可以重试、换模型、缩短输入，或使用结构化输出能力更好的模型。

### RAG 或章节定稿失败

检查 `EMBEDDING_PROVIDER`、`EMBEDDING_API_KEY`、`EMBEDDING_MODEL_VECTOR_SIZE` 和 `VECTOR_DB_URL`。更换嵌入模型时，向量维度必须与 `EMBEDDING_MODEL_VECTOR_SIZE` 一致。

### 今日请求次数已达上限

管理员可能设置了每日请求限制。可以等待额度刷新、配置个人 API Key，或由管理员调整后台限制。

## 贡献

欢迎提交 Issue 和 Pull Request。提交前建议先运行：

```bash
cd backend
pytest

cd ../frontend
npm run build
```

如只修改文档，可至少确认 Markdown 链接和命令路径仍然准确。
