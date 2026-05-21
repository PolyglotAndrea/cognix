# Cognix

<div class="grid cards" markdown>

- :material-rocket-launch:{ .lg .middle } **Get Started**

    ---

    Install Cognix and create your first agent in minutes.

    [:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

- :material-book-open-variant:{ .lg .middle } **Guides**

    ---

    Learn how to use agents, tasks, skills, and workflows.

    [:octicons-arrow-right-24: Guides](guides/agents.md)

- :material-cog:{ .lg .middle } **Architecture**

    ---

    Understand how Cognix works under the hood.

    [:octicons-arrow-right-24: Architecture](architecture/overview.md)

    [:octicons-arrow-right-24: Agentic Product Direction](architecture/agentic-product-direction.md)

- :material-api:{ .lg .middle } **API Reference**

    ---

    Complete REST and RPC API documentation.

    [:octicons-arrow-right-24: API Reference](api/auth.md)

</div>

## What is Cognix?

Cognix is a **Hermes Agent-based multi-agent collaboration platform** built in Python. It provides everything you need to build, orchestrate, and deploy autonomous AI systems.

### Key Features

- **Agent Runtime** — Stateful agents with tool calling, memory, and event system
- **Multi-Agent Orchestration** — Sequential, Parallel, Router, and Loop patterns via YAML workflow DSL
- **Scheduled Tasks** — Cron, interval, and one-shot scheduling with APScheduler
- **JSON-RPC 2.0** — Inter-service communication over HTTP and WebSocket
- **Skills System** — Local directory + remote marketplace for reusable agent capabilities
- **Web Dashboard** — React 18 SPA with notebook-style workspace for managing agents, tasks, and skills
- **Authentication** — OAuth2 (Google, GitHub), email/password, JWT tokens, and API keys
- **Billing** — Stripe subscriptions with usage tracking

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Web Backend | FastAPI + Uvicorn |
| Web Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| CLI | Typer + Rich |
| Database | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy + Alembic |
| Scheduler | APScheduler |
| LLM | LiteLLM (OpenAI, Anthropic, local models) |
| Config | Pydantic Settings (`COGNIX_` prefix) |

## Quick Example

```bash
# Create an agent
cognix agent create --name my-agent --model gpt-4o

# Chat with it
cognix agent chat my-agent "Hello, what can you do?"

# Schedule a task
cognix task add --name "daily-report" --cron "0 9 * * *" --agent my-agent
```
