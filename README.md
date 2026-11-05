<div align="center">

# 🐠 DoKnow — AI Learning OS

**Know what to learn. Learn how to do.**
*知其然，知其所以然，最终做到知行合一。*

A fully-managed **AI autonomous learning system** — state a goal, and the AI builds the
knowledge graph, plans the path, generates courses, assigns daily tasks, assesses mastery,
and continuously reinforces your weak spots.

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-agent-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)](https://vuejs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## What is DoKnow?

Most learning tools give you content. DoKnow gives you a **system**.

You describe *what you want to learn*; an AI manager takes over the entire learning
process and actively manages it from start to mastery:

1. **Input a goal** → the AI builds a **knowledge graph** of the domain.
2. It plans an ordered **learning path** through prerequisite relationships.
3. It **auto-generates courses, lessons and exercises**.
4. It assigns **daily tasks** (学 · 练 · 讲) sized to your progress.
5. While you learn, it **observes → diagnoses → decides → acts → evaluates**,
   intervening proactively when you stall, plateau or forget.
6. It **assesses mastery** per knowledge point and runs **spaced review** (温) to
   defeat the forgetting curve.

The result is a closed loop — **学 (learn) · 练 (practice) · 用 (apply) · 讲 (explain) · 温 (review)** —
where the AI plans, you execute, and the AI keeps re-planning based on evidence.

## ✨ Features

- **AI knowledge graph** — auto-built per goal, with prerequisite edges, rendered as an
  interactive **3D force-directed graph** with mastery-state coloring.
- **Learning path planning** — a sequenced path over the graph, re-planned as you progress.
- **Course & lesson generation** — AI-authored curriculum mapped to knowledge points.
- **Daily tasks (学练讲)** — learn material, practice exercises, and *explain in your own
  words* (the fastest way to expose shallow understanding).
- **Mastery assessment** — per-point state machine
  (`NOT_STARTED → IN_PROGRESS → COMPLETED → REVIEW_REQUIRED → MASTERED`).
- **Spaced review (温)** — SM-2-style intervals plus weakness-driven reinforcement.
- **Human-in-the-loop planning** — the AI *proposes* plan adjustments; you accept or reject.
- **Document ingestion** — upload PDF/DOCX/PPTX/MD, parsed via **Docling** (or MinerU) into
  the vector store for grounded generation.
- **Proactive AI manager** — background cycles that detect stalls and intervene, with a
  visible activity feed.
- **Agent runtime** — persisted runs, heartbeats, retries and cost tracking.

## 🧠 The AI / deterministic boundary

A core design principle: **agents propose, services decide.**

```
┌───────────────────────────── Agent layer (LangGraph) ─────────────────────────────┐
│  Learning Manager · Course Agent · Teaching · Exercise · Assessment · Review ...  │
│  → analyze, generate, PROPOSE                                                     │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        │  calls (never touches DB directly)
┌───────────────────────────────────────▼───────────────────────────────────────────┐
│                     Service layer (deterministic business rules)                  │
│  Identity · Goal · Knowledge · Curriculum · Orchestration · Teaching · Practice   │
│  · Assessment · Review · Memory · Content Quality                                 │
│  → own state, permissions, transactions, execution results                        │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        │
              PostgreSQL (pgvector) ◄────┴────► Redis (cache / locks)
```

The AI analyzes, generates and proposes; business services own the rules, state,
permissions and transactions. Agents never touch the database directly — they call the
service layer.

## Tech stack

| Layer             | Technology                                          |
| ----------------- | --------------------------------------------------- |
| Backend           | Python 3.12 + FastAPI (modular monolith)            |
| Database          | PostgreSQL 16 + **pgvector** (vector search)        |
| Agent framework   | **LangGraph** (Postgres checkpoint persistence)     |
| Cache / lock      | Redis 7                                             |
| ORM / migrations  | SQLAlchemy 2 + Alembic                              |
| Document parsing  | **Docling** (primary) / MinerU (optional)           |
| Frontend          | Vue 3 + TypeScript + Vite + Pinia + three.js (3D graph) |
| Deployment        | Docker + docker-compose                             |

> The original whitepaper suggests Spring Boot + MySQL as a *generic* recommendation.
> This repository's owner explicitly chose Python + FastAPI + PostgreSQL/pgvector +
> LangGraph + Docling/MinerU. That choice is authoritative here.

## 📁 Repository layout

```
backend/
  app/
    agents/        LangGraph graphs, prompts, state schemas, runtime
    api/           FastAPI routers + schemas + error mapping
    core/          config, database, redis, logging, events
    models/        SQLAlchemy domain models
    services/      deterministic business logic (12 services)
    workflows/     orchestration workflows
frontend/
  src/
    api/           typed HTTP client + endpoint modules
    components/    AppShell, KnowledgeGraph3D, PlanningPanel, cards ...
    views/         Auth, Home (graph + planner), Tasks, Goal, Course, Practice ...
    stores/        Pinia stores (auth, goal, toast)
    styles/        design system
docker-compose.yml
.env.example
```

## 🚀 Quick start (Docker)

> **Prereq:** Docker Desktop / OrbStack running.

```bash
# 1. Configure environment
cp .env.example .env
```

```bash
# 2. Bring up the full stack (db + redis + backend + frontend)
docker compose up --build
```

```text
frontend → http://localhost:5173
backend  → http://localhost:8000   (OpenAPI docs at /docs)
```

### 🔑 Configure the LLM (required for AI features)

The app boots fine without a key, but the **AI generation** (knowledge graph, path,
courses, tasks) needs a working OpenAI-compatible key. Edit `.env`:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-your-real-key
LLM_BASE_URL=https://api.openai.com/v1
```

Any OpenAI-compatible gateway works (DeepSeek, Moonshot, Qwen, a local Ollama via
`http://host:11434/v1`, etc.) — just set `LLM_BASE_URL` and `LLM_MODEL` accordingly.
Then recreate the backend so it picks up the new env:

```bash
docker compose up -d --force-recreate backend
```

## 🛠 Local development

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# uses Postgres + Redis, or start just those via Docker:
docker compose up db redis
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + production build
```

## ⚙️ Environment variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `doknow` | Postgres credentials |
| `POSTGRES_PORT` | `5432` | Exposed Postgres port |
| `DATABASE_URL` | `postgresql+psycopg://…@localhost:5432/doknow` | Backend DB DSN |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis DSN |
| `SECRET_KEY` | `change-me-in-production` | **Change in production** (JWT signing) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | Access-token lifetime (7 days) |
| `LLM_PROVIDER` | `openai` | LLM provider |
| `LLM_MODEL` | `gpt-4o-mini` | Model name |
| `LLM_API_KEY` | — | **Required for AI features** |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings for vector search / memory |
| `PARSER_BACKEND` | `docling` | `docling` or `mineru` |
| `LOG_LEVEL` | `INFO` | Logging level |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend → backend base URL (build-time) |

## 🧭 Core concepts

- **Goal** — what you want to learn; one is *active* at a time.
- **Knowledge point** — an atomic unit of the domain, typed as concept / fact /
  procedure / principle / skill, with difficulty and prerequisite edges.
- **Learning path** — an ordered traversal of knowledge points.
- **Task (学练讲)** — a concrete unit of daily work.
- **Review (温)** — a scheduled reinforcement, spaced by recall performance.
- **Mastery** — per-point state driven by exercise and explanation performance.

## 🗺 Roadmap

- [x] Auth, goals, knowledge graph, path planning
- [x] Course/lesson + exercise generation and grading
- [x] Daily tasks (学练讲) + spaced review (温)
- [x] Human-in-the-loop plan adjustment
- [x] 3D interactive knowledge-graph UI
- [ ] Assessment center & richer mastery analytics
- [ ] Memory / personalization (learner profile-driven adaptation)
- [ ] Content quality scoring & auto-improvement
- [ ] Observability & cost dashboards

## 🤝 Contributing

Issues and pull requests are welcome. For larger changes, please open an issue first to
discuss the approach. Keep the **AI / deterministic boundary** intact: agents propose,
services decide.

## 📄 License

Released under the [MIT License](LICENSE).