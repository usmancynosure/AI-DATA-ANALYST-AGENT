# AI Data Analyst Agent

Upload a CSV/Excel file or connect a Postgres/MySQL database, ask questions in plain
English, and get **SQL**, **Python analysis**, and **charts** back. An AI agent plans the
analysis, calls tools (query, run code, make charts), interprets the results, and answers.

> Showcases: AI agents, tool calling, sandboxed code execution, and data analysis.

## Architecture

```
┌─────────────┐   HTTP / SSE   ┌──────────────────┐   Claude API   ┌──────────┐
│  Next.js UI │◄──────────────►│  FastAPI backend │◄──────────────►│  Claude  │
│  chat +     │   file upload  │  agent loop +    │  tool calling  │  Opus 4.8│
│  charts     │                │  tool dispatch   │                │          │
└─────────────┘                └───────┬──────────┘                └──────────┘
                                        │ dispatches tools
                 ┌──────────────────────┼───────────────────────┐
                 ▼                      ▼                        ▼
          ┌────────────┐        ┌───────────────┐        ┌──────────────┐
          │  SQL tool  │        │  Python exec  │        │ chart render │
          │ DuckDB /   │        │  Docker       │        │ (matplotlib /│
          │ PG / MySQL │        │  sandbox      │        │  Vega spec)  │
          └────────────┘        └───────────────┘        └──────────────┘
```

Uploaded files are loaded into a per-session **DuckDB** database, so files and databases
share one uniform SQL interface. Generated Python runs in an isolated **Docker sandbox**
(no network, CPU/memory limits, timeout). All SQL passes a **read-only guard**.

## Repo layout

```
backend/          FastAPI: data layer, agent orchestrator, sandbox runner
frontend/         Next.js (App Router) + Tailwind chat UI
sandbox-image/    Dockerfile for the code-execution sandbox
docker-compose.yml
```

## Quick start (local, without Docker)

**Backend** (Python 3.11/3.12 via [uv](https://docs.astral.sh/uv/)):

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY when you reach the agent phase
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload      # http://localhost:8000/docs
uv run pytest                             # run the test suite
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev                               # http://localhost:3000
```

## Quick start (Docker)

```bash
cp .env.example .env
docker build -t ai-analyst-sandbox:latest ./sandbox-image   # code-exec sandbox
docker compose up --build                                   # backend :8000, frontend :3000
```

## Build status

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Monorepo scaffold, health wiring | ✅ done |
| 1 | Data layer: uploads → DuckDB, PG/MySQL, read-only SQL, schema | ✅ done |
| 2 | Docker sandbox for generated Python | ✅ done |
| 3 | Claude agent loop + tools | ⏳ next |
| 4 | Streaming (SSE) API | ⏳ |
| 5 | Chat UI, uploads, charts | ⏳ |
| 6 | Hardening, CI, demo | ⏳ |

## Safety

- **SQL:** only single read-only `SELECT`/`WITH` statements; row + time limits; prefer a
  read-only DB user for external connections.
- **Code execution:** never in the API process — always in a throwaway Docker container
  with `--network none`, memory/CPU/pid limits, and a wall-clock timeout.
- **Untrusted data:** tool results (including data contents) are treated as untrusted and
  cannot change tool permissions.

## License

MIT
