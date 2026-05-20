# Agent Management

Agents are the core runtime entities in Cognix. Each agent is a stateful instance with its own model, system prompt, tools, and memory.

## Agent Lifecycle

```
IDLE → RUNNING → IDLE (normal)
IDLE → RUNNING → WAITING → RUNNING → IDLE (with tool calls)
IDLE → RUNNING → ERROR (on failure)
```

## Create an Agent

=== "CLI"

    ```bash
    cognix agent create \
      --name "research-agent" \
      --model gpt-4o \
      --description "Research assistant with web search"
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/v1/agents \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "research-agent",
        "model": "gpt-4o",
        "description": "Research assistant with web search",
        "system_prompt": "You are a research assistant. Use web search to find information.",
        "temperature": 0.7,
        "max_iterations": 10
      }'
    ```

## Agent Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | — | Unique agent name |
| `model` | string | `gpt-4o` | LLM model identifier |
| `description` | string | `""` | Short description |
| `system_prompt` | string | `"You are a helpful assistant."` | System prompt |
| `temperature` | float | `0.7` | Sampling temperature (0–2) |
| `max_iterations` | int | `10` | Max tool-call loop iterations |
| `api_base` | string? | — | Custom LLM API base URL |

## Supported Models

Cognix uses [LiteLLM](https://docs.litellm.ai/) for model abstraction. Supported providers:

| Provider | Models |
|----------|--------|
| OpenAI | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo` |
| Anthropic | `claude-3.5-sonnet`, `claude-3-opus` |
| Custom/OpenAI-compatible | Models discovered from the configured provider |

Local mock models such as `echo`, `noop`, and `mock` are disabled in product execution paths.
Configure a real provider in Account Settings or Workspace Settings before running an Agent.

## Chat with an Agent

=== "CLI"

    ```bash
    # Single message
    cognix agent chat my-agent "What's the weather today?"

    # Interactive mode
    cognix agent chat my-agent
    ```

=== "API (Streaming)"

    ```bash
    curl -X POST http://localhost:8000/api/v1/agents/{id}/chat/stream \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"message": "What'\''s the weather today?"}'
    ```

    Response is Server-Sent Events (SSE):

    ```
    data: {"delta": "I'll"}
    data: {"delta": " check"}
    data: {"delta": " the"}
    data: {"delta": " weather"}
    data: {"type": "tool_call", "name": "web_search", "args": {"query": "weather today"}}
    data: {"type": "tool_result", "name": "web_search", "result": {...}}
    data: {"delta": " Today it's sunny..."}
    data: [DONE]
    ```

## Delete an Agent

=== "CLI"

    ```bash
    cognix agent delete my-agent
    ```

=== "API"

    ```bash
    curl -X DELETE http://localhost:8000/api/v1/agents/{id} \
      -H "Authorization: Bearer TOKEN"
    ```

## Web UI

The notebook-style workspace provides a full agent management interface:

- **Left Panel**: Agent selector, system prompt editor, model/temperature/iterations controls
- **Center Panel**: Chat interface with streaming support
- **Right Panel**: Tool results, execution logs, and raw JSON output
