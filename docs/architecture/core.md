# Core Modules

The `cognix/core/` directory contains the fundamental building blocks of the platform.

## Agent (`core/agent.py`)

The `Agent` class is the central runtime entity.

```python
class Agent:
    id: str
    name: str
    model: str
    system_prompt: str
    temperature: float
    max_iterations: int
    state: AgentState  # IDLE, RUNNING, WAITING, ERROR
    tools: list[Tool]
    memory: MemoryBackend
```

### State Machine

```
IDLE ──start──→ RUNNING
RUNNING ──tool_call──→ WAITING ──tool_result──→ RUNNING
RUNNING ──complete──→ IDLE
RUNNING ──error──→ ERROR ──reset──→ IDLE
```

### Execution Loop

1. Receive user message
2. Build context (system prompt + conversation history + tools)
3. Call LLM via LiteLLM
4. If LLM returns tool calls → execute tools → go to step 3
5. If LLM returns text → emit response → go to IDLE

## Tool (`core/tool.py`)

Tools are async callables with JSON Schema parameters.

```python
from cognix.core.tool import tool

@tool(name="web_search", description="Search the web")
async def web_search(query: str) -> str:
    """Search the web for the given query."""
    return f"Results for: {query}"
```

Tools export OpenAI function-calling format automatically.

## EventBus (`core/events.py`)

Async pub/sub system for decoupled communication.

```python
from cognix.core.events import EventBus, Events

bus = EventBus()

# Subscribe
@bus.on(Events.AGENT_START)
async def on_agent_start(agent_id: str):
    print(f"Agent {agent_id} started")

# Emit
await bus.emit(Events.AGENT_START, agent_id="my-agent")
```

### Well-Known Events

| Event | Payload | Description |
|-------|---------|-------------|
| `agent.start` | `agent_id` | Agent begins execution |
| `agent.end` | `agent_id, result` | Agent completes |
| `agent.error` | `agent_id, error` | Agent encounters error |
| `tool.call` | `agent_id, tool_name, args` | Tool invocation |
| `tool.result` | `agent_id, tool_name, result` | Tool result |
| `task.run` | `task_id` | Scheduled task starts |
| `task.complete` | `task_id, result` | Scheduled task completes |
| `skill.install` | `skill_name` | Skill installed |
| `skill.uninstall` | `skill_name` | Skill removed |

## Memory (`core/memory.py`)

Abstract memory backend with TTL support.

```python
from cognix.core.memory import MemoryBackend, InMemoryBackend

class MemoryBackend(ABC):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: int | None = None): ...
    async def delete(self, key: str): ...
    async def keys(self) -> list[str]: ...
```

The `InMemoryBackend` is the default implementation. Redis backend available via `cognix[redis]` extra.

## Context (`core/context.py`)

Carries conversation state through agent execution.

```python
@dataclass
class Context:
    messages: list[dict]       # Conversation history
    variables: dict[str, Any]  # User-defined variables
    metadata: dict[str, Any]   # Execution metadata
    agent_id: str              # Current agent ID
    run_id: str                # Unique run identifier
```

## Registry (`core/registry.py`)

Central registry for agent instances.

```python
registry = AgentRegistry()
registry.register(agent)
registry.get("my-agent")  # Returns agent by ID or name
registry.list_all()       # Returns all registered agents
```
