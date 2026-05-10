# Task Scheduling

Cognix includes a built-in task scheduler powered by APScheduler. Schedule agent calls, RPC calls, HTTP webhooks, skill executions, and workflows.

## Task Types

| Type | Description |
|------|-------------|
| `agent_call` | Send a message to an agent |
| `rpc_call` | Call an RPC method |
| `http_webhook` | Send an HTTP request |
| `skill_exec` | Execute a skill |
| `workflow` | Run a workflow |

## Schedule Types

| Type | Format | Example |
|------|--------|---------|
| Cron | Standard cron expression | `0 9 * * *` (daily at 9am) |
| Interval | ISO 8601 duration | `PT1H` (every hour) |
| One-shot | ISO 8601 datetime | `2026-06-01T10:00:00Z` |

## Create a Task

=== "CLI"

    ```bash
    # Cron schedule
    cognix task add \
      --name "daily-report" \
      --cron "0 9 * * *" \
      --agent my-agent \
      --type agent_call

    # Interval schedule
    cognix task add \
      --name "health-check" \
      --interval "PT30M" \
      --type http_webhook \
      --payload '{"url": "https://example.com/health"}'

    # One-shot schedule
    cognix task add \
      --name "one-time-task" \
      --at "2026-06-01T10:00:00Z" \
      --agent my-agent \
      --type agent_call
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/v1/tasks \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "name": "daily-report",
        "task_type": "agent_call",
        "schedule": "0 9 * * *",
        "payload": "{\"agent_id\": \"AGENT_ID\", \"message\": \"Generate daily report\"}"
      }'
    ```

## Task States

```
ACTIVE → PAUSED → ACTIVE (resume)
ACTIVE → COMPLETED (one-shot tasks)
ACTIVE → FAILED (after max retries)
```

## Manage Tasks

=== "CLI"

    ```bash
    # List tasks
    cognix task list

    # Pause a task
    cognix task pause TASK_ID

    # Resume a task
    cognix task resume TASK_ID

    # Delete a task
    cognix task delete TASK_ID
    ```

=== "API"

    ```bash
    # List tasks
    curl http://localhost:8000/api/v1/tasks -H "Authorization: Bearer TOKEN"

    # Get task runs
    curl http://localhost:8000/api/v1/tasks/{id}/runs -H "Authorization: Bearer TOKEN"
    ```

## Task Payload Examples

### Agent Call

```json
{
  "agent_id": "my-agent-id",
  "message": "Summarize today's news"
}
```

### HTTP Webhook

```json
{
  "url": "https://example.com/webhook",
  "method": "POST",
  "headers": {"Content-Type": "application/json"},
  "body": {"event": "scheduled"}
}
```

### Skill Execution

```json
{
  "skill_name": "web_search",
  "args": {"query": "latest AI news"}
}
```

## Distributed Scheduling

Cognix supports distributed task scheduling with lease-based locking:

| Field | Description |
|-------|-------------|
| `lease_owner` | ID of the server instance that owns the task |
| `lease_expires_at` | When the lease expires (heartbeat-based) |

This prevents duplicate execution when running multiple Cognix instances. Each node also applies
`COGNIX_SCHEDULER__DISPATCHER_BATCH_SIZE`,
`COGNIX_SCHEDULER__DISPATCHER_MAX_CONCURRENT`, and
`COGNIX_SCHEDULER__DISPATCHER_LEASE_TTL_SECONDS` to limit local worker pressure.
