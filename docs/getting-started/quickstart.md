# Quick Start

Get Cognix running and create your first agent in under 5 minutes.

## 1. Start the Server

```bash
cd cognix
source .venv/bin/activate

# Set required config
export COGNIX_AUTH__SECRET_KEY="dev-secret-key-change-in-prod"
export COGNIX_LLM_API_KEY="sk-..."  # Your OpenAI/Anthropic key

# Start the API server
cognix server start --port 8000
```

The API is now available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## 2. Start the Web Frontend

In a separate terminal:

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. Register an account or log in with OAuth.

## 3. Create an Agent

=== "CLI"

    ```bash
    cognix agent create --name my-assistant --model gpt-4o
    cognix agent list
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/v1/agents \
      -H "Authorization: Bearer YOUR_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"name": "my-assistant", "model": "gpt-4o"}'
    ```

=== "Web UI"

    1. Open the workspace at `http://localhost:5173`
    2. Click **+ New Agent** in the left panel
    3. Enter a name and select a model
    4. Click **Create**

## 4. Chat with Your Agent

=== "CLI"

    ```bash
    cognix agent chat my-assistant "Hello! What can you help me with?"
    ```

=== "API (Streaming)"

    ```bash
    curl -X POST http://localhost:8000/api/v1/agents/AGENT_ID/chat/stream \
      -H "Authorization: Bearer YOUR_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"message": "Hello! What can you help me with?"}'
    ```

=== "Web UI"

    1. Select your agent in the left panel
    2. Type a message in the center chat panel
    3. Press Enter or click Send

## 5. Schedule a Task

=== "CLI"

    ```bash
    cognix task add \
      --name "morning-briefing" \
      --cron "0 9 * * *" \
      --agent my-assistant \
      --type agent_call
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/v1/tasks \
      -H "Authorization: Bearer YOUR_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "morning-briefing",
        "task_type": "agent_call",
        "schedule": "0 9 * * *",
        "payload": "{\"agent_id\": \"AGENT_ID\", \"message\": \"Good morning briefing\"}"
      }'
    ```

## 6. Install a Skill

=== "CLI"

    ```bash
    cognix skill search "web search"
    cognix skill install web_search
    cognix skill list
    ```

=== "Web UI"

    1. Use the skills search bar in the top navigation
    2. Find a skill and click **Install**

## Next Steps

- [Agent Management](../guides/agents.md) — Configure agents with custom system prompts, tools, and parameters
- [Task Scheduling](../guides/tasks.md) — Set up cron, interval, and one-shot scheduled tasks
- [Skills System](../guides/skills.md) — Browse, install, and create custom skills
- [Workflows](../guides/workflows.md) — Build multi-agent orchestration workflows
- [Authentication](../guides/authentication.md) — Set up OAuth, API keys, and RBAC
