# DoKnow — AI Learning OS

> **DoKnow — Know what to learn. Learn how to do.**
> 知其然，知其所以然，最终做到知行合一。

DoKnow is a **full-managed AI autonomous learning system**. The learner defines a
learning goal; the AI takes over the entire learning process:

1. **Input a goal** → the AI builds the knowledge system (knowledge map).
2. The AI plans a **learning path** through the knowledge graph.
3. The AI **auto-generates courses and daily tasks**.
4. The learner **executes the learning** while the AI actively intervenes
   (Observe → Diagnose → Decide → Act → Evaluate).
5. The AI **assesses mastery** and continuously adjusts the plan.

Learning method: **学、练、用、讲、温** (Learn, Practice, Apply, Explain, Review).

---

## Tech stack

| Layer             | Technology                                   |
| ----------------- | -------------------------------------------- |
| Backend           | Python 3.12 + FastAPI (modular monolith)     |
| Database          | PostgreSQL 16 + **pgvector**                 |
| Agent framework   | **LangGraph** (Checkpoint persistence)       |
| Cache / lock      | Redis 7                                      |
| Document parsing  | **Docling** (primary) / MinerU (optional)    |
| Deployment        | Docker + docker-compose                      |
| Frontend          | Vue 3 + TypeScript + Vite + Pinia            |

> Note: The whitepaper suggests Spring Boot + MySQL as a *generic* recommendation.
> The project owner explicitly chose Python + FastAPI + PostgreSQL/pgvector +
> LangGraph + Docling/MinerU. That choice is authoritative for this repository.

## Architecture

Modular monolith following the whitepaper's 13 module boundaries:

```
Identity & User · Learning Goal · Knowledge · Curriculum · Learning Orchestration
· Teaching · Practice · Assessment · Review · Memory · Agent Runtime
· Content Quality · Observability & Cost
```

**AI / deterministic boundary** — the AI analyzes, generates and proposes; business
services own rules, state, permissions, transactions and execution results. Agents
never touch the database directly; they call the service layer.

See `docs/` (whitepaper) for the full product spec.

## Repository layout

```
backend/     FastAPI modular monolith (models, services, agents, api)
frontend/    Vue 3 + TypeScript SPA (miroFish-style learning interface)
docs/        Whitepaper and architecture notes
docker-compose.yml
```

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
# backend  → http://localhost:8000  (OpenAPI at /docs)
# frontend → http://localhost:5173
```

## Local development

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# requires Postgres + Redis, or use `docker compose up db redis`
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Phase 1 scope

Phase 1 validates **course quality + the learning loop**:
input goal → build knowledge map → generate & validate learning path →
generate courses/lessons → AI teaching → generate exercises & record results →
basic mastery assessment → persist learning state and events.
