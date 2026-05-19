# Cognix

A Hermes Agent-based multi-agent collaboration platform built in Python. Cognix provides agent runtime, orchestration, scheduling, skills, and a full-stack web interface for building autonomous AI systems.

## Features

- **Agent Runtime** — Stateful agents with tool calling, memory, and event system
- **Four-Pipeline Memory** — Hot `USER.md`/`MEMORY.md`, cold SQLite recall, procedural skill snippets, and optional deep user model injection
- **Inspectable Memory Vault** — Cold memories are indexed in SQLite and projected into Obsidian-compatible Markdown trees with source metadata
- **Human-in-the-loop Approvals** — `ask` and `plan` permission modes, approval requests, approve/reject/resume API, and SSE approval events
- **Multi-Agent Orchestration** — Sequential, Parallel, Router, and Loop patterns via YAML workflow DSL
- **Scheduled Tasks** — Cron, interval, and one-shot scheduling with APScheduler plus runtime leases, due-task claiming, DB-backed worker dispatch, and retry backoff
- **JSON-RPC 2.0** — Inter-service communication over HTTP and WebSocket
- **Skills + MCP Tools** — Local skills, workspace MCP server config, stdio MCP tool discovery/status caching, and Agent tool mounting
- **Claude Agent SDK Bridge** — Workspace-scoped Claude Agent SDK execution with permission mode, MCP config mapping, and approval callbacks
- **Remote Bot Bridge** — Lark/Feishu, DingTalk, and WeChat entry points with signature-aware webhook handling, async dispatch, chat context binding, and response callbacks
- **Channel Gateway** — Provider-neutral `ChannelEvent` and `MessageRouter` normalize remote messages before Agent or Task execution
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
COGNIX_AUTH__FRONTEND_URL=http://localhost:5173
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
├── channels/       # Unified external channel event and message routing layer
├── memory/         # Context routing, token budgets, cold memory, and vault projection
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
| `POST /api/v1/approvals/{id}/resume-and-continue` | Resume an approved Hermes Agent or Claude SDK run and continue to a final response |
| `POST /api/v1/approvals/{id}/resume-and-continue/stream` | Stream a resumed Hermes Agent or Claude SDK run |
| `POST /api/v1/approvals/{id}/resume/stream` | Stream a resumed Claude Agent SDK run |
| `GET /api/v1/tasks` | List scheduled tasks |
| `POST /api/v1/tasks` | Create scheduled task |
| `POST /api/v1/tasks/{id}/replay` | Replay a failed task immediately |
| `POST /api/v1/tasks/{id}/cancel` | Cancel a scheduled task and release any active lease |
| `GET /api/v1/skills` | List skills |
| `GET /api/v1/connectors/platforms` | List connector platforms and credential status |
| `GET /api/v1/connectors/tools` | List connector tools and effective access levels |
| `POST /api/v1/connectors/tools/{tool_name}/call` | Debug-call a connector tool with permission checks and approval gating |
| `GET /api/v1/runtime/status` | Inspect scheduler, distributed task dispatcher status, retry settings, and runtime metrics |
| `GET /api/v1/workspaces/{id}/mcp/servers/{server_id}/tools` | Discover MCP tools for a workspace server |
| `POST /api/v1/workspaces/{id}/mcp/servers/{server_id}/tools/{tool_name}/call` | Invoke a discovered MCP tool with permission checks for validation/debugging |
| `GET /api/v1/workspaces/{id}/mcp/servers/{server_id}/status` | Check or refresh MCP server discovery status, including stderr tail on errors |
| `POST /api/v1/workspaces/{id}/mcp/servers/{server_id}/restart` | Clear MCP cache and probe a server again |
| `POST /api/v1/workspaces/{id}/mcp/servers/{server_id}/stop` | Stop local MCP runtime cache for a server |
| `GET /api/v1/workspaces/{id}/orchestration/snapshots` | List unified orchestration run snapshots |
| `GET /api/v1/workspaces/{id}/orchestration/snapshots/{run_id}` | Inspect the latest snapshot for an intent/plan/task run |
| `POST /api/v1/workspaces/{id}/claude/stream` | Stream Claude Agent SDK execution events |
| `POST /rpc` | JSON-RPC endpoint |
| `WS /rpc/ws` | Authenticated JSON-RPC WebSocket endpoint |

### Streaming Events

Agent and workspace chat streaming use a stable data-only SSE JSON payload with:

- `delta`
- `tool_call`
- `tool_result`
- `approval_request`
- `error`
- `done`

`approval_request` is emitted when `permission_mode="ask"` or a dangerous tool needs human confirmation. Claude Agent SDK runs use the same approval channel through the SDK `can_use_tool` callback, preserve resume metadata when the SDK exposes it, and can continue through `/api/v1/approvals/{id}/resume/stream`.

### Permission Modes

Cognix normalizes Agent permission modes at runtime:

| Mode | Behavior |
|------|----------|
| `read-only` | Allows read tools only; write and dangerous tools are denied. |
| `workspace-write` | Allows read/write workspace tools; dangerous tools require approval. |
| `ask` | Read tools run directly; write and dangerous tools create approval requests. |
| `plan` | Read tools run directly; write and dangerous tools create plan confirmation requests. |
| `unrestricted` | Allows all tool access levels without approval. |

Approval requests are stored locally and can be typed as `tool_permission`, `plan_confirmation`, or `question`. Hermes Agent waiting snapshots are persisted into approval metadata so approved core tool calls can continue through `/api/v1/approvals/{id}/resume-and-continue/stream` after a runtime reload when the serialized context is still valid. Claude SDK approvals can resume as SSE through `/api/v1/approvals/{id}/resume/stream` or the shared resume-and-continue API.

Workspace policy is enforced on execution paths, not only displayed in the UI. File preview/write/delete APIs, MCP debug calls, connector debug calls, scheduled webhooks/skill execution, mounted MCP/connector Agent tools, and Claude SDK file/command/network/MCP tools all pass through `WorkspacePolicyService` before side effects run.

### Channel Gateway

External channels are normalized before they enter orchestration. Provider-specific adapters convert WeChat, Lark/Feishu, DingTalk, Telegram-style, web, or API payloads into a provider-neutral `ChannelEvent` with `channel`, `workspace_id`, `thread_id`, `sender_id`, `text`, attachments, raw payload, and metadata. `MessageRouter` then routes the event either directly to an Agent or into a one-shot scheduled Task.

Remote bot bridges now use this path while preserving existing bot callback and workspace event compatibility. This keeps OpenClaw-style channel integration separate from Hermes/Cognix orchestration and makes future providers a thin adapter instead of a new execution path.

### Memory Vault

Cold memory is stored in SQLite for retrieval and also projected into an Obsidian-compatible Markdown tree for human review. Workspace records are written under `~/.cognix/workspaces/{workspace_id}/memory/tree/{scope}/{kind}.md`; global records use `~/.cognix/memory/tree/{scope}/{kind}.md`. Each Markdown block includes the memory id, timestamps, scope, kind, source, metadata, and raw content.

`ContextBuilder` supports priority, greedy, routed, and balanced assembly. Routed/balanced modes use `MemoryRouter` to decide which memory stores to query, while balanced mode uses `ContextBudgetManager` to allocate token budget across hot, cold, procedural, and deep memory sources.

### Orchestration Protocol

Cognix emits a unified lifecycle across `Intent -> Plan -> Approval -> Execution -> Events -> Artifact -> Memory/Playbook`. Workspace events still live in `events.jsonl`, but each orchestration-aware event now includes normalized `orchestration` metadata with `event_id`, `stage`, `status`, and `run_id`. The latest state for each run is also persisted as a snapshot under `~/.cognix/workspaces/{workspace_id}/orchestration/snapshots/{run_id}.json`.

Planner, TaskExecutor, approval requests, artifact changes, and playbook extraction/promotion all publish through the same protocol. This gives the UI and remote channels one stable state model instead of stitching together unrelated logs.

### Provider Secrets

Global and workspace model provider keys are stored encrypted when saved. Existing plaintext keys remain readable for backward compatibility and are encrypted the next time they are updated. Masked values such as `sk-***` are treated as display-only placeholders, so saving settings, testing a provider, or listing models will not overwrite a real stored key with the masked value.

### Connectors

Connectors provide OAuth-backed tools for external platforms such as X and Instagram. Credentials are encrypted locally, expose expiry/reauthorization status, and validate missing OAuth scopes after callback. Connector tools are mounted into Agents through the shared runtime mount path.

Public posting, upload, delete, and reply tools are treated as `dangerous`, so `workspace-write`, `ask`, and `plan` modes create approval requests before execution. The connector debug-call API follows the same permission decision: when approval is required it returns an `approval_id`; after approval, repeat the call with the same arguments and `approval_id` to execute it.

### Claude Agent SDK Mode

Claude Agent SDK mode maps Cognix workspace settings into SDK options:

- Workspace files are scoped to the workspace file directory.
- `permission_mode` is translated to Claude SDK permission behavior.
- Workspace MCP servers are passed into the SDK MCP config.
- SDK `can_use_tool` callbacks create Cognix approval requests and preserve resume/session metadata when available.
- Human answers, plan confirmations, and approved tool calls use the same approval panel and stream protocol as Cognix core Agents.

### MCP Lifecycle

MCP servers are configured per workspace. Cognix starts stdio MCP processes for discovery/tool calls, caches discovered tools briefly, and records runtime status:

- `status`: `unknown`, `ready`, `error`, `stopped`, or `disabled`
- `tool_count`: number of discovered tools
- `error` / `stderr`: startup or protocol diagnostics

The API supports status refresh, restart, stop, delete, and permission-checked tool test calls. Server metadata can set `disabled_tools` to hide individual MCP tools from core Agent mounting. Workspace skills and MCP tools are adapted into core `Tool` instances through a shared runtime mount helper before REST, RPC, WebSocket, workspace chat, workflow, scheduled task, or remote bot execution.

### Distributed Scheduler

Scheduled tasks are stored in the database and coordinated with runtime leases:

- Runtime nodes claim due tasks with a lease owner and expiry.
- Successful runs release the lease and advance `next_run`.
- Failed runs retry with exponential backoff until `max_retries` is exhausted.
- Exhausted tasks are marked `failed` and removed from future dispatch.
- Tasks can set `max_execution_seconds`; dispatchers fail timed-out runs and apply the same retry policy.
- Failed tasks can be replayed, which clears leases and prior idempotency state before immediate re-execution.
- Active or paused tasks can be canceled; cancel clears `next_run` and active leases, and running dispatchers will not advance a canceled task after the current await returns.
- Optional `idempotency_key` payloads prevent a previously completed key from executing again for the same task.
- Each runtime node respects dispatcher capacity settings, including `dispatcher_batch_size` and `dispatcher_max_concurrent`.
- Runtime status exposes dispatcher metrics including active task ids, claimed, success, failure, retry, exhausted failure, and last error counters.

### Remote Bot Callbacks

Bot bridge configs can include metadata for asynchronous response writeback:

```json
{
  "dispatch_mode": "task",
  "task_max_retries": 1,
  "response_url": "https://example.com/bot/callback",
  "response_headers": {"Authorization": "Bearer ..."},
  "response_timeout": 10
}
```

When `dispatch_mode` is `task`, Cognix turns the bot message into a one-shot scheduled Agent task and immediately acknowledges the webhook. When `response_url` is configured, Cognix posts the Agent response, provider-specific formatted response, sender/chat identifiers, and session key to `response_url` after dispatch or scheduled task completion.

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
