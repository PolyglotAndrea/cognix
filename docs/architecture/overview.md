# Architecture Overview

Cognix is a modular, event-driven platform for building autonomous AI systems.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Web Frontend                           │
│              React 18 + Vite + TypeScript                   │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP / WebSocket
┌─────────────────────────▼───────────────────────────────────┐
│                      API Server                             │
│                   FastAPI + Uvicorn                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Auth     │ │ Agents   │ │ Tasks    │ │ Billing       │  │
│  │ Routes   │ │ Routes   │ │ Routes   │ │ Routes        │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                      Core Layer                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Agent    │ │ Tool     │ │ EventBus │ │ Memory        │  │
│  │ Runtime  │ │ System   │ │ Pub/Sub  │ │ Backend       │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │ Context  │ │ Registry │ │ Skills   │                    │
│  │ State    │ │ Central  │ │ Manager  │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Infrastructure                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ SQLite/  │ │ APSched  │ │ LiteLLM  │ │ JSON-RPC      │  │
│  │ Postgres │ │ uler     │ │ Provider │ │ Server/Client │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Module Map

| Directory | Purpose |
|-----------|---------|
| `cognix/core/` | Agent runtime, tools, events, memory, context, registry |
| `cognix/orchestrator/` | Multi-agent patterns (Sequential, Parallel, Router, Loop) |
| `cognix/scheduler/` | APScheduler-based task engine |
| `cognix/rpc/` | JSON-RPC 2.0 server/client |
| `cognix/skills/` | Skills system (local + marketplace) |
| `cognix/api/` | FastAPI REST + WebSocket API |
| `cognix/cli/` | Typer CLI |
| `cognix/auth/` | OAuth2, JWT, API keys, RBAC |
| `cognix/billing/` | Stripe subscriptions + usage tracking |
| `cognix/storage/` | SQLAlchemy models |
| `web/` | React 18 SPA frontend |

## Data Flow

```
User Request
     │
     ▼
API Server (FastAPI)
     │
     ├── Auth Middleware (JWT/API Key validation)
     │
     ▼
Agent Runtime
     │
     ├── LLM Call (via LiteLLM)
     │
     ├── Tool Call Loop
     │   ├── Tool Execution
     │   └── Result → Next LLM Call
     │
     ├── Memory Read/Write
     │
     └── Event Emission (EventBus)
         ├── agent.start / agent.end
         ├── tool.call / tool.result
         └── task.run / task.complete
```

## Key Design Decisions

1. **Agent = stateful runtime instance**, not a stateless function
2. **Tool vs Skill**: Tool is atomic; Skill is Tool + config + dependencies
3. **Event-driven**: modules decoupled via EventBus
4. **Progressive storage**: SQLite for dev (zero config), PostgreSQL for prod
5. **LLM abstraction**: LiteLLM provides unified interface; Agent falls back to echo if not configured

## Product Refactor Plan

See [Cognix Product Refactor Plan](product-refactor-plan.md) for the task-first workspace architecture, BYOK and entitlement flow, sandbox policy, memory router, artifact studio, and phased implementation roadmap.

See [Planner Orchestrator Refactor Plan](planner-orchestrator.md) for the intent-to-plan-to-execution product layer that turns a user goal into agents, skills, MCP usage, scheduled tasks, execution events, artifacts, and memory/playbook follow-up.
