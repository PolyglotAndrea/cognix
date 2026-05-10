# Create Your First Agent

This tutorial walks you through creating, configuring, and chatting with your first Cognix agent.

## Prerequisites

- Cognix installed ([Installation Guide](../getting-started/installation.md))
- API server running
- An LLM API key (OpenAI or Anthropic)

## Step 1: Start the Server

```bash
cd cognix
source .venv/bin/activate

export COGNIX_AUTH__SECRET_KEY="dev-secret-key"
export COGNIX_LLM_API_KEY="sk-..."

cognix server start --port 8000
```

## Step 2: Register an Account

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpass123", "name": "Your Name"}'
```

Save the returned token:

```bash
export TOKEN="eyJhbGciOiJIUzI1NiIs..."
```

## Step 3: Create an Agent

=== "CLI"

    ```bash
    cognix agent create \
      --name "research-assistant" \
      --model gpt-4o \
      --description "A helpful research assistant"
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/v1/agents \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "research-assistant",
        "model": "gpt-4o",
        "description": "A helpful research assistant"
      }'
    ```

## Step 4: Configure the Agent

Set a custom system prompt to give your agent a personality and expertise:

=== "CLI"

    ```bash
    cognix agent update research-assistant \
      --system-prompt "You are a research assistant specializing in technology and science. Always cite your sources and provide structured answers."
    ```

=== "API"

    ```bash
    curl -X PUT http://localhost:8000/api/v1/agents/AGENT_ID \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "system_prompt": "You are a research assistant specializing in technology and science. Always cite your sources and provide structured answers."
      }'
    ```

## Step 5: Chat with Your Agent

=== "CLI"

    ```bash
    cognix agent chat research-assistant "What are the latest developments in quantum computing?"
    ```

=== "API (Streaming)"

    ```bash
    curl -X POST http://localhost:8000/api/v1/agents/AGENT_ID/chat/stream \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"message": "What are the latest developments in quantum computing?"}'
    ```

=== "Web UI"

    1. Open `http://localhost:5173`
    2. Log in with your credentials
    3. Select "research-assistant" in the left panel
    4. Type your message in the center chat panel

## Step 6: Adjust Parameters

Experiment with different settings:

| Parameter | Effect |
|-----------|--------|
| `temperature: 0.1` | More focused, deterministic responses |
| `temperature: 0.9` | More creative, varied responses |
| `max_iterations: 5` | Limit tool-call loops |
| `max_iterations: 20` | Allow more complex tool usage |

## Next Steps

- [Task Scheduling](../guides/tasks.md) — Schedule your agent to run daily
- [Skills System](../guides/skills.md) — Give your agent new capabilities
- [Build a Workflow](workflow.md) — Connect multiple agents
