# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Cognix is a **Hermes Agent-based multi-agent collaboration platform** built in Python. It provides:
- A custom Agent runtime (Hermes Core) with tool calling, memory, and event system
- Multi-agent orchestration (Sequential, Parallel, Router, Loop patterns)
- Scheduled task / API scheduling (cron, interval, one-shot)
- JSON-RPC 2.0 inter-service communication
- Skills system (local directory + remote marketplace)
- CLI interface (Typer) + REST/WebSocket API (FastAPI)
- **OAuth2 authentication** (Google, GitHub) with JWT tokens and API keys
- **RBAC permissions** (admin, user, viewer roles)

## Tech Stack

- **Language**: Python 3.11+
- **Web Backend**: FastAPI + Uvicorn
- **Web Frontend**: React 18 + Vite + TypeScript + Tailwind CSS
- **CLI**: Typer + Rich
- **Database**: SQLite (dev) / PostgreSQL (prod) via SQLAlchemy + Alembic
- **Scheduler**: APScheduler
- **LLM**: LiteLLM (unified interface for OpenAI/Anthropic/local models)
- **Config**: Pydantic Settings (env prefix: `COGNIX_`)

## Common Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Web UI (development)
cd web && npm install && npm run dev    # Starts on http://localhost:5173
cd web && npm run build                 # Production build

# Run CLI
cognix --help
cognix version
cognix init ./my-project

# Run API server
cognix server start --port 8000 --reload

# Agent management
cognix agent create --name my-agent --model gpt-4o
cognix agent list
cognix agent chat my-agent "Hello"

# Task management
cognix task add --name "daily-report" --cron "0 9 * * *" --agent reporter
cognix task list

# Skills
cognix skill list
cognix skill search "web search"
cognix skill install web_search
cognix skill create my-skill

# RPC
cognix rpc call agent.list
cognix rpc call agent.chat --params '{"agent_id":"test","message":"hi"}'

# Tests
pytest tests/ -v
pytest tests/unit/ -v --cov=cognix

# Linting
ruff check cognix/
ruff format cognix/

# Type checking
mypy cognix/
```

## Architecture

### Core Modules (`cognix/core/`)
- **agent.py** - `Agent` class: the fundamental runtime entity. Has tools, memory, state machine (IDLE/RUNNING/WAITING/ERROR). Handles LLM call + tool-call loops.
- **tool.py** - `Tool` class + `@tool` decorator. Tools are async callables with JSON Schema parameters. Export OpenAI function-calling format.
- **events.py** - `EventBus` async pub/sub. Well-known events in `Events` class (agent.*, tool.*, task.*, skill.*, workflow.*).
- **memory.py** - `MemoryBackend` ABC with `InMemoryBackend` implementation. TTL support.
- **context.py** - `Context` carries conversation state (messages, variables, metadata) through agent execution.
- **registry.py** - `AgentRegistry` central registry for agent instances.

### Orchestration (`cognix/orchestrator/`)
Multi-agent patterns: Sequential, Parallel, Router, Loop. YAML workflow DSL with Jinja2 templating.

### Scheduler (`cognix/scheduler/`)
APScheduler-based task engine. Supports cron/interval/one-shot schedules. Task types: agent_call, rpc_call, http_webhook, skill_exec, workflow.

### RPC (`cognix/rpc/`)
JSON-RPC 2.0 server/client. Methods registered via `@rpc_method` decorator. Supports HTTP and WebSocket transport.

### Skills (`cognix/skills/`)
Skills are packages with `skill.yaml` manifest + `handler.py` entrypoint. Local directory + remote marketplace.

### API (`cognix/api/`)
FastAPI app with REST endpoints at `/api/v1/*` and JSON-RPC at `/rpc`. Lifespan manages DB init/close.

### CLI (`cognix/cli/`)
Typer app with sub-command groups: agent, task, skill, workflow, rpc, server.

### Auth (`cognix/auth/`)
OAuth2 authentication with Google and GitHub providers. JWT tokens for sessions, bcrypt-hashed API keys for programmatic access. RBAC with admin/user/viewer roles. FastAPI dependencies: `get_current_user`, `require_admin`, `require_permission("perm")`.

### Billing (`cognix/billing/`)
Stripe-based subscription billing. Plans: Free, Starter ($29/mo), Pro ($99/mo), Enterprise (custom). Usage tracking for api_calls, tokens, agent_runs. Webhook handlers for subscription lifecycle events.

### Web Frontend (`web/`)
React 18 SPA with Vite, TypeScript, Tailwind CSS. Pages: Dashboard, Agents (list + chat), Tasks, Skills, Billing, Settings. Auth via JWT stored in Zustand. API proxy to backend on port 8000.

### Storage (`cognix/storage/`)
SQLAlchemy async models: UserModel, APIKeyModel, AgentModel, ScheduledTaskModel, TaskRunModel, SkillModel. SQLite default, PostgreSQL in production.

## Key Design Decisions

1. **Agent = stateful runtime instance**, not a stateless function
2. **Tool vs Skill**: Tool is atomic; Skill is Tool + config + dependencies
3. **Event-driven**: modules decoupled via EventBus
4. **Progressive storage**: SQLite for dev (zero config), PostgreSQL for prod (change connection string only)
5. **LLM abstraction**: LiteLLM provides unified interface; Agent falls back to echo if litellm not configured

## Configuration

Environment variables use `COGNIX_` prefix with `__` for nesting:
- `COGNIX_DEBUG=true`
- `COGNIX_DATABASE__URL=postgresql+asyncpg://...`
- `COGNIX_DEFAULT_MODEL=gpt-4o`
- `COGNIX_LLM_API_KEY=sk-...`
- `COGNIX_SERVER__PORT=8000`
- `COGNIX_AUTH__SECRET_KEY=your-secret-key`
- `COGNIX_AUTH__GOOGLE_CLIENT_ID=...`
- `COGNIX_AUTH__GOOGLE_CLIENT_SECRET=...`
- `COGNIX_AUTH__GITHUB_CLIENT_ID=...`
- `COGNIX_AUTH__GITHUB_CLIENT_SECRET=...`
- `COGNIX_BILLING__STRIPE_SECRET_KEY=sk_...`
- `COGNIX_BILLING__STRIPE_WEBHOOK_SECRET=whsec_...`
- `COGNIX_BILLING__STRIPE_PRICE_STARTER=price_...`
- `COGNIX_BILLING__STRIPE_PRICE_PRO=price_...`

## Authentication

All API endpoints (except `/health`, `/`, `/docs`) require authentication via:
1. **JWT Bearer token**: `Authorization: Bearer <jwt>`
2. **API Key**: `X-API-Key: cnx_xxxxx`

OAuth2 login flow:
1. `GET /auth/login/google` or `/auth/login/github` - redirects to provider
2. `GET /auth/callback/{provider}?code=...` - exchanges code for JWT
3. Frontend stores JWT and uses it for subsequent requests

API key management:
- `POST /auth/api-keys` - create new key (returns full key once)
- `GET /auth/api-keys` - list keys
- `DELETE /auth/api-keys/{id}` - revoke key

## Billing (Stripe)

Subscription management endpoints:
- `GET /billing/plans` - list available plans
- `GET /billing/subscription` - current subscription
- `POST /billing/checkout` - create Stripe Checkout session
- `POST /billing/portal` - create Customer Portal session
- `GET /billing/usage` - current usage stats
- `POST /billing/webhook` - Stripe webhook handler
