# Cognix

A Hermes Agent-based multi-agent collaboration platform built in Python. Cognix provides agent runtime, orchestration, scheduling, skills, and a full-stack web interface for building autonomous AI systems.

## Features

- **Agent Runtime** — Stateful agents with tool calling, memory, and event system
- **Human-in-the-loop Approvals** — `ask` and `plan` permission modes, approval requests, approve/reject/resume API, and SSE approval events
- **Multi-Agent Orchestration** — Sequential, Parallel, Router, and Loop patterns via YAML workflow DSL
- **Scheduled Tasks** — Cron, interval, and one-shot scheduling with APScheduler plus runtime leases, due-task claiming, DB-backed worker dispatch, and retry backoff
- **JSON-RPC 2.0** — Inter-service communication over HTTP and WebSocket
- **Skills + MCP Tools** — Local skills, workspace MCP server config, stdio MCP tool discovery/status caching, and Agent tool mounting
- **Claude Agent SDK Bridge** — Workspace-scoped Claude Agent SDK execution with permission mode, MCP config mapping, and approval callbacks
- **Remote Bot Bridge** — Lark/Feishu, DingTalk, and WeChat entry points with signature-aware webhook handling, async dispatch, and chat context binding
- **CLI + API** — Typer CLI and FastAPI REST/WebSocket API
- **OAuth2 Authentication** — Google and GitHub providers with JWT tokens and API keys
- **RBAC Permissions** — Admin, user, and viewer roles
- **Stripe Billing** — Subscription plans with usage tracking
- **Web Dashboard** — React 18 SPA for managing agents, tasks, skills, and billing

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Web Backend | FastAPI + Uvicorn |
| Web Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| CLI | Typer + Rich |
| Database | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy + Alembic |
| Scheduler | APScheduler |
| LLM | LiteLLM (OpenAI, Anthropic, local models) + Claude Agent SDK bridge |
| Config | Pydantic Settings (`COGNIX_` prefix) |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for web frontend)

### Install

```bash
git clone https://github.com/PolyglotAndrea/cognix.git
cd cognix
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configure

Create `.env`:

```bash
COGNIX_DEBUG=true
COGNIX_DEFAULT_MODEL=gpt-4o
COGNIX_LLM_API_KEY=sk-...
COGNIX_AUTH__SECRET_KEY=your-secret-key
```

### Run

```bash
# CLI
cognix --help

# API Server
cognix server start --port 8000

# Web Frontend
cd web && npm install && npm run dev
# Optional if your API server is not on 8000:
# VITE_API_TARGET=http://localhost:8001 npm run dev
```

## Usage

### Agent Management

```bash
cognix agent create --name my-agent --model gpt-4o
cognix agent list
cognix agent chat my-agent "Hello"
```

### Task Scheduling

```bash
cognix task add --name "daily-report" --cron "0 9 * * *" --agent reporter
cognix task list
```

### Skills

```bash
cognix skill list
cognix skill search "web search"
cognix skill install web_search
cognix skill create my-skill
```

### RPC

```bash
cognix rpc call agent.list
cognix rpc call agent.chat --params '{"agent_id":"test","message":"hi"}'
```

## Architecture

```
cognix/
├── core/           # Agent runtime, tools, events, memory, context
├── orchestrator/   # Multi-agent patterns (Sequential, Parallel, Router, Loop)
├── scheduler/      # APScheduler + DB-backed dispatcher with leases and retry backoff
├── rpc/            # JSON-RPC 2.0 server/client
├── skills/         # Skills system (local + marketplace)
├── mcp/            # MCP stdio client and Tool adapter
├── claude/         # Claude Agent SDK runtime bridge
├── local/          # Local-first ~/.cognix workspace storage
├── api/            # FastAPI REST + WebSocket API
├── cli/            # Typer CLI
├── auth/           # OAuth2, JWT, API keys, RBAC
├── billing/        # Stripe subscriptions + usage tracking
├── storage/        # SQLAlchemy models
└── web/            # React 18 SPA frontend
```

### Core Modules

| Module | Description |
|--------|------------|
| `agent.py` | Agent class — stateful runtime with IDLE/RUNNING/WAITING/ERROR states |
| `tool.py` | Tool class + `@tool` decorator — async callables with JSON Schema |
| `permissions.py` | Runtime permission policy for read-only, workspace-write, ask, plan, and unrestricted modes |
| `events.py` | EventBus — async pub/sub with well-known event types |
| `memory.py` | MemoryBackend — in-memory with TTL support |
| `context.py` | Context — carries conversation state through execution |
| `registry.py` | AgentRegistry — central registry for agent instances |

### API Endpoints

| Endpoint | Description |
|----------|------------|
| `GET /api/v1/agents` | List agents |
| `POST /api/v1/agents` | Create agent |
| `POST /api/v1/agents/{id}/chat` | Chat with agent (SSE streaming) |
| `GET /api/v1/approvals` | List pending or resolved human approval requests |
| `POST /api/v1/approvals/{id}/approve` | Approve a pending tool/action request |
| `POST /api/v1/approvals/{id}/respond` | Answer a pending human question request |
| `POST /api/v1/approvals/{id}/reject` | Reject a pending tool/action request |
| `POST /api/v1/approvals/{id}/resume` | Resume an approved Agent or Claude SDK tool call |
| `GET /api/v1/tasks` | List scheduled tasks |
| `POST /api/v1/tasks` | Create scheduled task |
| `GET /api/v1/skills` | List skills |
| `GET /api/v1/runtime/status` | Inspect scheduler and distributed task dispatcher status |
| `GET /api/v1/workspaces/{id}/mcp/servers/{server_id}/tools` | Discover MCP tools for a workspace server |
| `GET /api/v1/workspaces/{id}/mcp/servers/{server_id}/status` | Check or refresh MCP server discovery status |
| `POST /api/v1/workspaces/{id}/claude/stream` | Stream Claude Agent SDK execution events |
| `POST /rpc` | JSON-RPC endpoint |

### Streaming Events

Agent and workspace chat streaming use a stable data-only SSE JSON payload with:

- `delta`
- `tool_call`
- `tool_result`
- `approval_request`
- `error`
- `done`

`approval_request` is emitted when `permission_mode="ask"` or a dangerous tool needs human confirmation. Claude Agent SDK runs use the same approval channel through the SDK `can_use_tool` callback.

### Authentication

All endpoints (except `/health`, `/`, `/docs`) require:

1. **JWT Bearer token**: `Authorization: Bearer <jwt>`
2. **API Key**: `X-API-Key: cnx_xxxxx`

OAuth2 flow:
1. `GET /auth/login/google` or `/auth/login/github`
2. `GET /auth/callback/{provider}?code=...`
3. Frontend stores JWT for subsequent requests

### Billing (Stripe)

| Endpoint | Description |
|----------|------------|
| `GET /billing/plans` | List available plans |
| `GET /billing/subscription` | Current subscription |
| `POST /billing/checkout` | Create Stripe Checkout session |
| `POST /billing/portal` | Create Customer Portal session |
| `GET /billing/usage` | Current usage stats |
| `POST /billing/webhook` | Stripe webhook handler |

Plans: Free ($0), Starter ($29/mo), Pro ($99/mo), Enterprise (custom)

## Development

```bash
# Tests
pytest tests/ -v
pytest tests/unit/ -v --cov=cognix

# Linting
ruff check cognix/
ruff format cognix/

# Type checking
mypy cognix/
```

## License

[MIT](LICENSE)
