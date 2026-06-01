# Arboris-Novel | 面向创作者的写作辅助工具

**[English](README-en.md)** | 中文

![GitHub stars](https://img.shields.io/github/stars/t59688/arboris-novel?style=social)
![GitHub forks](https://img.shields.io/github/forks/t59688/arboris-novel?style=social)
![GitHub issues](https://img.shields.io/github/issues/t59688/arboris-novel)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

如果你想使用命令行+编辑器的方式，可搭配使用 [novel-kit](https://github.com/t59688/novel-kit)。

写作时容易卡在「主角叫什么」「故事发生在哪」「下一章写什么」这类问题上。**Arboris** 在需要时帮你理清思路、记录设定、给出可选方向，让想法落成故事。

**在线体验：** [https://arboris.aozhiai.com](https://arboris.aozhiai.com)

<p align="center">
  <table align="center">
    <tr>
      <td align="center"><strong>交流群</strong><br/><img width="220" alt="交流群二维码" src="https://github.com/user-attachments/assets/6d4fe420-f8ae-4fe4-883d-235eb576c83b" /></td>
      <td align="center"><strong>作者公众号</strong><br/><img width="220" alt="作者公众号" src="https://picui.ogmua.cn/s1/2026/02/24/699d109e4ced2.webp" /></td>
    </tr>
  </table>
</p>

---

## 界面预览

<p align="center">
  <img width="1471" alt="主界面" src="https://github.com/user-attachments/assets/a52d0214-bc1b-4792-8a2b-267b09e47379" />
</p>
<p align="center">
  <img width="1375" alt="角色管理" src="https://github.com/user-attachments/assets/0673faad-43df-4479-83ae-cffa870199a3" />
</p>
<p align="center">
  <img width="1392" alt="大纲编辑" src="https://github.com/user-attachments/assets/b7a7af24-1689-4341-aa78-26b0d74bdddd" />
</p>
<p align="center">
  <img width="1255" alt="写作界面" src="https://github.com/user-attachments/assets/c831d746-8c1a-4ce8-aa1c-9b852da15c11" />
</p>

---

## 功能概览

### 设定管理
角色、地点、派系等设定集中记录，随时查阅，避免写到后期前后矛盾（如角色外貌、世界观规则等）。

### 大纲与故事线
零散的场景和灵感可交给 AI 梳理，生成从开头到结局的主线大纲。

### 写作辅助
状态不佳时可让 AI 先出草稿再按自己的风格修改；也可自己写开头，让 AI 续写以获取灵感。

### 多版本对比
支持一次生成多版内容，挑选最符合风格的部分，逐步让模型更贴合你的笔触。

---

## 项目初衷

目标是做一个**能记住你的世界、理解角色、随故事推进的写作伙伴**，而不是单纯的自动生成器。因此做了 Arboris 并选择开源，方便更多创作者使用。

---

## 快速开始

### 方式一：Docker 部署

```bash
# 1. 复制配置文件
cp deploy/.env.example .env

# 2. 编辑根目录 .env 中的必填项：
#    - SECRET_KEY: 随机字符串，用于 JWT 等
#    - OPENAI_API_KEY: 大模型 API Key
#    - EMBEDDING_API_KEY: 硅基流动 Embedding API Key
#    - ADMIN_DEFAULT_PASSWORD: 管理员密码（勿用默认值）

# 3. 启动（默认 SQLite，无需单独安装数据库）
docker compose -f deploy/docker-compose.yml up -d --build

# 启动后在浏览器访问 http://localhost:<端口>
```

也可以在配置好根目录 `.env` 后使用脚本部署：

```bash
bash deploy/scripts/deploy_docker.sh
```

### 方式二：使用 MySQL（Compose 内 MySQL）

```bash
# .env 中设置 DB_PROVIDER=mysql、MYSQL_PASSWORD、MYSQL_ROOT_PASSWORD，然后执行：
docker compose -f deploy/docker-compose.yml --profile mysql up -d --build
```

### 方式三：使用自有 MySQL

```bash
# 在 .env 中配置 DB_PROVIDER=mysql 以及外部数据库地址、用户名、密码后执行：
docker compose -f deploy/docker-compose.yml up -d --build
```

### 可选：启动异步任务 Worker

情感分析、异步任务执行和 Redis 缓存需要额外启用 `worker` profile：

```bash
docker compose -f deploy/docker-compose.yml --profile worker up -d --build

# 如果同时使用 Compose 内 MySQL：
docker compose -f deploy/docker-compose.yml --profile mysql --profile worker up -d --build
```

---

## 环境变量说明

常用配置如下（完整项见 `deploy/.env.example`，运行时请复制到根目录 `.env`）：

| 配置项 | 必填吗 | 说明 |
|--------|--------|------|
| `SECRET_KEY` | ✅ | JWT 加密密钥，需自行随机生成并妥善保管 |
| `OPENAI_API_KEY` | ✅ | 你的 LLM API Key（OpenAI 或兼容的） |
| `OPENAI_API_BASE_URL` | ❌ | API 地址，默认是 OpenAI 官方的 |
| `OPENAI_MODEL_NAME` | ❌ | 主要生成模型名称，建议显式填写 |
| `EMBEDDING_API_KEY` | ✅ | 硅基流动 Embedding API Key；若与主 LLM 同 Key 才可复用 |
| `EMBEDDING_BASE_URL` | ❌ | 默认 `https://api.siliconflow.cn/v1` |
| `EMBEDDING_MODEL` | ❌ | 默认 `Qwen/Qwen3-Embedding-8B` |
| `EMBEDDING_MODEL_VECTOR_SIZE` | ❌ | 默认 `1024`，需与嵌入模型维度一致 |
| `VECTOR_DB_URL` | ❌ | RAG 向量库地址，默认本地 libSQL 文件 `file:./storage/rag_vectors.db` |
| `DB_PROVIDER` | ❌ | `sqlite` 或 `mysql`，默认 `sqlite` |
| `MYSQL_*` | 使用 MySQL 时必填 | MySQL 主机、端口、用户、密码、数据库名 |
| `ADMIN_DEFAULT_PASSWORD` | ❌ | 管理员初始密码，部署后务必修改 |
| `ALLOW_USER_REGISTRATION` | ❌ | 是否开放注册，默认 `false` |
| `SMTP_SERVER` / `SMTP_USERNAME` | 开放注册时必填 | 邮件服务，用于发送验证码 |

> **数据存储：** 默认 SQLite，数据在 Docker 卷中。需映射到宿主机目录时，在 `.env` 中设置 `SQLITE_STORAGE_SOURCE=./storage`。

> **嵌入模型：** 当前默认使用硅基流动 OpenAI-compatible Embeddings API 的 `Qwen/Qwen3-Embedding-8B`，不是 Ollama 本地模型。只有在你明确设置 `EMBEDDING_PROVIDER=ollama` 时才需要部署 Ollama。

---

## 中间件与部署选型

当前代码状态下，推荐的部署组合如下：

| 组件 | 默认选型 | 是否必需 | 部署方式 |
|------|----------|----------|----------|
| 应用服务 | 单容器内 Nginx + FastAPI/Uvicorn + 前端静态文件 | ✅ | `deploy/Dockerfile` 构建，Compose 中 `app` 服务启动 |
| 关系数据库 | SQLite | ✅ | 默认使用 Docker volume `sqlite-data`，也可用 `SQLITE_STORAGE_SOURCE=./storage` 映射到宿主机 |
| MySQL | MySQL 8.0 | 可选 | 内置服务通过 `--profile mysql` 启用；外部 MySQL 只需配置 `MYSQL_HOST` 等变量 |
| 数据库迁移 | Alembic | ✅ | 应用启动时自动执行；也可运行 `bash deploy/scripts/run_migrations.sh` |
| 向量数据库 | libSQL 本地文件 | ✅（用于 RAG） | 默认 `file:./storage/rag_vectors.db`，随 `/app/storage` 持久化；也可改为远程 libSQL/Turso 地址 |
| 嵌入模型 | 硅基流动 `Qwen/Qwen3-Embedding-8B` | ✅（用于 RAG） | 远程 OpenAI-compatible API，配置 `EMBEDDING_API_KEY` 即可 |
| Redis | Redis 7 Alpine | 可选 | 通过 `--profile worker` 启用，供 Celery broker/result backend 和缓存使用 |
| Celery Worker | Celery 5 | 可选 | 通过 `--profile worker` 启用，执行异步任务 |
| SMTP | 任意 SMTP 服务 | 可选 | 开放注册或邮件验证码时配置 |

---

## 常见问题

### 基础使用

**Q: 不会用 Docker？**  
A: 安装 Docker Desktop（Windows/Mac）或 Docker Engine（Linux），按上文命令执行即可。

**Q: API Key 会泄露吗？**  
A: 不会。密钥仅存在于服务端 `.env`，不向前端或用户暴露。

**Q: 是否支持其他大模型？**  
A: 支持。只要提供 OpenAI 兼容接口，在 `.env` 中配置 `OPENAI_API_BASE_URL` 即可。

**Q: 修改了代码如何参与？**  
A: 欢迎提交 PR 或 Issue。

### 生成小说时的常见错误

**Q: 提示"未配置默认 LLM API Key"怎么办？**  
A: 检查 `.env` 文件中的 `OPENAI_API_KEY` 是否正确配置。如果是个人用户，也可以在个人设置中配置自定义 API Key。

**Q: 生成时提示"今日请求次数已达上限"？**  
A: 系统管理员可能设置了每日请求限制。解决方案：
- 等到明天再试
- 在个人设置中配置自己的 API Key（不受系统配额限制）
- 管理员调整配额限制（修改 `daily_request_limit` 配置）

**Q: 提示"AI 服务响应超时"或"无法连接到 AI 服务"？**  
A: 网络或 API 服务问题导致。可以：
- 检查网络连接是否正常
- 确认 `OPENAI_API_BASE_URL` 配置是否正确
- 如果使用自建服务，检查服务是否正常运行
- 稍后重试

**Q: 提示"AI 响应因长度限制被截断"？**  
A: 生成的内容超过了模型的输出限制。建议：
- 使用支持更长输出的模型

**Q: 提示"AI 未返回有效内容"或"AI 服务内部错误"？**  
A: AI 服务端出现问题。通常是暂时性的，可以：
- 大多是LLM服务的问题，尤其是逆向的API。
- 检查 API Key 是否有效且有足够余额
- 查看后端日志获取详细错误信息

**Q: 提示"蓝图中未找到对应章节纲要"？**  
A: 在生成章节内容前，需要先在蓝图（大纲）中创建对应章节的纲要。请先完善章节大纲再进行生成。

**Q: 提示"未配置摘要提示词"？**  
A: 系统缺少必要的 Prompt 配置。管理员需要在后台配置名为 `extraction` 的提示词模板，用于生成章节摘要。

**Q: 提示"AI 返回的内容格式不正确"或 JSON 解析错误？**（较常见）  
A: AI 返回内容无法解析为有效 JSON。可能原因与处理方式：
- **原因 1：模型能力不足** - 某些模型难以稳定输出结构化 JSON
  - 解决：切换到能力更强的模型
  - 或使用支持 structured output 的模型
- **原因 2：内容过长** - 某些逆向API可能无法支持长输出。

- **临时处理：** 重试几次，或更换 AI 模型

**Q: 生成的内容质量不理想怎么办？**  
A: 可以尝试：
- 完善角色、地点、派系等设定信息
- 优化章节纲要，提供更详细的指引
- 使用多版本生成功能，让 AI 生成多个版本后挑选最佳的
- 调整使用的模型，需要长上下文的

---

## 技术栈

- **后端：** Python + FastAPI
- **数据库：** SQLite（默认）或 MySQL 8.0，Alembic 管理迁移
- **向量检索：** libSQL 本地文件或远程 libSQL/Turso
- **前端：** Vue + TailwindCSS
- **异步任务：** Celery + Redis（可选 profile）
- **部署：** Docker + Docker Compose profiles
- **AI：** OpenAI-compatible LLM；默认嵌入为硅基流动 `Qwen/Qwen3-Embedding-8B`

---

## 面向开发者

### 环境准备

- Python 3.10+（建议使用虚拟环境）
- Node.js 18+ 与 npm
- pip / virtualenv（或你习惯的依赖管理工具）
- 可选：Docker 与 Docker Compose（用于一键部署与发布）

### 后端本地开发

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认会监听 `http://127.0.0.1:8000`，你可以通过 `--host`、`--port` 调整，或加上 `--reload` 保持热重载。

### 前端本地开发

```bash
cd frontend
npm install
npm run dev
```

开发服务器默认运行在 `http://127.0.0.1:5173`，可通过 `--host` 参数暴露给局域网设备。

### 打包与构建

- 前端：`npm run build`，构建产物位于 `frontend/dist/`
- 后端：确认依赖锁定后，可使用 `pip install -r requirements.txt` 安装到目标环境，或基于 `deploy/Dockerfile` 构建镜像
- 静态文件托管：生产环境下可用 Nginx 等服务托管 `dist` 目录，并由后端提供 API

### 发布与部署

推荐在根目录下使用 Compose 文件完成一体化部署：

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

如需推送镜像，可在 `deploy` 目录执行 `docker build -t <registry>/arboris:<tag> .`，测试后再 `docker push` 发布。

---

## 参与贡献

- Star 项目
- 在 Issues 中反馈 Bug 或建议
- 提交 PR 贡献代码
- 通过文首二维码加入交流群

---

## 反馈与致谢

使用 Arboris 写出作品后，欢迎与我们分享。祝写作顺利。

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

[![Star History Chart](https://api.star-history.com/svg?repos=t59688/arboris-novel&type=Date)](https://star-history.com/#t59688/arboris-novel&Date)
