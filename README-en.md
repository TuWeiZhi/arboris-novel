# Arboris-Novel | Writing Assistant for Creators

[中文](11.md) | English

![GitHub stars](https://img.shields.io/github/stars/t59688/arboris-novel?style=social)
![GitHub forks](https://img.shields.io/github/forks/t59688/arboris-novel?style=social)
![GitHub issues](https://img.shields.io/github/issues/t59688/arboris-novel)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

For a CLI + editor workflow, you can use [novel-kit](https://github.com/t59688/novel-kit) alongside.

Writing often gets stuck on questions like “what’s the protagonist’s name,” “where does the story take place,” or “what happens in the next chapter.” **Arboris** helps you clarify ideas, keep track of settings, and explore directions when you need it.

**Try it online:** [https://arboris.aozhiai.com](https://arboris.aozhiai.com)

<p align="center">
  <table align="center">
    <tr>
      <td align="center"><strong>Community</strong><br/><img width="220" alt="Community QR code" src="https://github.com/user-attachments/assets/6d4fe420-f8ae-4fe4-883d-235eb576c83b" /></td>
      <td align="center"><strong>Author (WeChat)</strong><br/><img width="220" alt="Author WeChat public account" src="https://picui.ogmua.cn/s1/2026/02/24/699d109e4ced2.webp" /></td>
    </tr>
  </table>
</p>

---

## Screenshots

<p align="center">
  <img width="1471" alt="Main interface" src="https://github.com/user-attachments/assets/a52d0214-bc1b-4792-8a2b-267b09e47379" />
</p>
<p align="center">
  <img width="1375" alt="Character management" src="https://github.com/user-attachments/assets/0673faad-43df-4479-83ae-cffa870199a3" />
</p>
<p align="center">
  <img width="1392" alt="Outline editor" src="https://github.com/user-attachments/assets/b7a7af24-1689-4341-aa78-26b0d74bdddd" />
</p>
<p align="center">
  <img width="1255" alt="Writing interface" src="https://github.com/user-attachments/assets/c831d746-8c1a-4ce8-aa1c-9b852da15c11" />
</p>

---

## Features

### Setting management
Characters, locations, factions, and other settings are stored in one place so you can avoid contradictions later (e.g. character appearance, world rules).

### Outline & storylines
Scattered scenes and ideas can be handed to the AI to turn into a coherent outline from start to end.

### Writing assistance
When you’re not in the mood, the AI can draft first and you edit to your style; or you write the opening and let the AI continue for inspiration.

### Multi-version comparison
Generate several versions at once, pick the parts that fit your style best, and gradually tune the model to your voice.

---

## Why this project

The goal is a **writing partner that remembers your world, understands your characters, and moves the story forward with you**—not just an auto-generator. Hence Arboris was built and open-sourced for more creators to use.

---

## Quick start

### Option 1: Docker

```bash
# 1. Copy config
cp deploy/.env.example .env

# 2. Edit required fields in the repo-root .env:
#    - SECRET_KEY: random string for JWT etc.
#    - OPENAI_API_KEY: your LLM API key
#    - EMBEDDING_API_KEY: SiliconFlow embedding API key
#    - ADMIN_DEFAULT_PASSWORD: admin password (do not leave default)

# 3. Start (default SQLite, no separate DB install)
docker compose -f deploy/docker-compose.yml up -d --build

# Then open http://localhost:<port> in your browser
```

You can also deploy with the helper script after preparing the repo-root `.env`:

```bash
bash deploy/scripts/deploy_docker.sh
```

### Option 2: MySQL via Compose

```bash
# Set DB_PROVIDER=mysql, MYSQL_PASSWORD, and MYSQL_ROOT_PASSWORD in .env, then:
docker compose -f deploy/docker-compose.yml --profile mysql up -d --build
```

### Option 3: Your own MySQL

```bash
# Configure DB_PROVIDER=mysql plus external DB host/user/password in .env, then:
docker compose -f deploy/docker-compose.yml up -d --build
```

### Optional: start async workers

Emotion analysis, async jobs, and Redis-backed cache require the `worker` profile:

```bash
docker compose -f deploy/docker-compose.yml --profile worker up -d --build

# If you also use the Compose-managed MySQL service:
docker compose -f deploy/docker-compose.yml --profile mysql --profile worker up -d --build
```

---

## Environment variables

Common options (full list in `deploy/.env.example`; copy it to the repo-root `.env`):

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | JWT secret; generate randomly and keep safe |
| `OPENAI_API_KEY` | ✅ | Your LLM API key (OpenAI or compatible) |
| `OPENAI_API_BASE_URL` | ❌ | API base URL; default is OpenAI |
| `OPENAI_MODEL_NAME` | ❌ | Main generation model; set explicitly for your provider |
| `EMBEDDING_API_KEY` | ✅ | SiliconFlow embedding API key; reuse `OPENAI_API_KEY` only if both services share a key |
| `EMBEDDING_BASE_URL` | ❌ | Default `https://api.siliconflow.cn/v1` |
| `EMBEDDING_MODEL` | ❌ | Default `Qwen/Qwen3-Embedding-8B` |
| `EMBEDDING_MODEL_VECTOR_SIZE` | ❌ | Default `1024`; must match the embedding model dimension |
| `VECTOR_DB_URL` | ❌ | RAG vector store URL; default local libSQL file `file:./storage/rag_vectors.db` |
| `DB_PROVIDER` | ❌ | `sqlite` or `mysql`; default `sqlite` |
| `MYSQL_*` | If using MySQL | MySQL host, port, user, password, and database |
| `ADMIN_DEFAULT_PASSWORD` | ❌ | Initial admin password; change after deploy |
| `ALLOW_USER_REGISTRATION` | ❌ | Allow sign-up; default `false` |
| `SMTP_SERVER` / `SMTP_USERNAME` | If registration on | Mail config for verification emails |

> **Storage:** Default is SQLite in a Docker volume. To use a local path, set `SQLITE_STORAGE_SOURCE=./storage` in `.env`.

> **Embeddings:** The default embedding backend is SiliconFlow's OpenAI-compatible API with `Qwen/Qwen3-Embedding-8B`, not a local Ollama model. Deploy Ollama only if you explicitly set `EMBEDDING_PROVIDER=ollama`.

---

## Middleware and Deployment Choices

Recommended choices for the current codebase:

| Component | Default choice | Required | Deployment |
|-----------|----------------|----------|------------|
| App service | Single container with Nginx + FastAPI/Uvicorn + frontend static files | ✅ | Built from `deploy/Dockerfile`; started as the Compose `app` service |
| Relational DB | SQLite | ✅ | Default Docker volume `sqlite-data`; set `SQLITE_STORAGE_SOURCE=./storage` to bind-mount a host directory |
| MySQL | MySQL 8.0 | Optional | Enable the built-in service with `--profile mysql`, or point `MYSQL_HOST` etc. to an external MySQL |
| DB migrations | Alembic | ✅ | Runs during app startup; can also be run with `bash deploy/scripts/run_migrations.sh` |
| Vector store | Local libSQL file | ✅ for RAG | Default `file:./storage/rag_vectors.db`, persisted under `/app/storage`; can be changed to remote libSQL/Turso |
| Embedding model | SiliconFlow `Qwen/Qwen3-Embedding-8B` | ✅ for RAG | Remote OpenAI-compatible API; set `EMBEDDING_API_KEY` |
| Redis | Redis 7 Alpine | Optional | Enable with `--profile worker`; used for Celery broker/result backend and cache |
| Celery worker | Celery 5 | Optional | Enable with `--profile worker`; runs async jobs |
| SMTP | Any SMTP provider | Optional | Configure when sign-up/email verification is enabled |

---

## FAQ

### General

**Q: I’m not familiar with Docker.**  
A: Install Docker Desktop (Windows/Mac) or Docker Engine (Linux), then run the commands above.

**Q: Can my API key leak?**  
A: No. Keys live only in the server `.env` and are not exposed to the frontend or users.

**Q: Can I use other LLMs?**  
A: Yes. Any OpenAI-compatible API works; set `OPENAI_API_BASE_URL` in `.env`.

**Q: I changed the code. How do I contribute?**  
A: Open a PR or an Issue.

### Generation errors

**Q: “Default LLM API Key not configured”?**  
A: Check `OPENAI_API_KEY` in `.env`. Users can also set a personal API key in settings.

**Q: “Daily request limit reached”?**  
A: An admin may have set a daily limit. Options: wait until the next day; set your own API key in settings (not subject to quota); or ask the admin to change `daily_request_limit`.

**Q: “AI service timeout” or “Cannot connect to AI service”?**  
A: Usually network or API issues. Check connectivity, `OPENAI_API_BASE_URL`, and that any self-hosted service is running; then retry.

**Q: “AI response truncated due to length limit”?**  
A: Output exceeded the model’s limit. Use a model that supports longer output.

**Q: “AI returned no valid content” or “AI service error”?**  
A: Server-side AI issue, often temporary. Check API key and balance; inspect backend logs for details. Third-party/reverse APIs are a common source.

**Q: “Chapter outline not found in blueprint”?**  
A: Add the chapter outline in the blueprint (outline) before generating that chapter.

**Q: “Summary prompt not configured”?**  
A: The admin must configure a prompt template named `extraction` for chapter summaries.

**Q: “AI response format invalid” or JSON parse error?** (Common)  
A: The AI output isn’t valid JSON. Possible causes:
- **Model capability** — Some models don’t reliably output structured JSON. Use a stronger model or one with structured output.
- **Length** — Some APIs don’t support long outputs.

**Workaround:** Retry a few times or switch to another model.

**Q: Generated content quality is poor?**  
A: Try: filling in character/location/faction settings; improving chapter outlines; using multi-version generation and picking the best; or using a model with longer context.

---

## Tech stack

- **Backend:** Python + FastAPI
- **Database:** SQLite (default) or MySQL 8.0, with Alembic migrations
- **Vector retrieval:** Local libSQL file or remote libSQL/Turso
- **Frontend:** Vue + TailwindCSS
- **Async jobs:** Celery + Redis (optional profile)
- **Deploy:** Docker + Docker Compose profiles
- **AI:** OpenAI-compatible LLM; default embeddings use SiliconFlow `Qwen/Qwen3-Embedding-8B`

---

## For developers

### Prerequisites

- Python 3.10+ (virtualenv recommended)
- Node.js 18+ and npm
- pip / virtualenv (or your preferred tool)
- Optional: Docker & Docker Compose for one-command deploy

### Backend (local)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Server listens on `http://127.0.0.1:8000` by default; use `--host` / `--port` or `--reload` as needed.

### Frontend (local)

```bash
cd frontend
npm install
npm run dev
```

Dev server runs at `http://127.0.0.1:5173`; use `--host` to expose on the network.

### Build

- Frontend: `npm run build` → output in `frontend/dist/`
- Backend: `pip install -r requirements.txt` on target, or build from `deploy/Dockerfile`
- Production: serve `dist` with Nginx etc.; backend serves the API

### Deploy

From the repo root:

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

To push images: from `deploy`, run `docker build -t <registry>/arboris:<tag> .`, test, then `docker push`.

---

## Contributing

- Star the repo  
- Report bugs or ideas in Issues  
- Send PRs  
- Join the community via the QR codes above  

---

## Feedback

If you create something with Arboris, we’d love to hear about it. Happy writing.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

[![Star History Chart](https://api.star-history.com/svg?repos=t59688/arboris-novel&type=Date)](https://star-history.com/#t59688/arboris-novel&Date)
