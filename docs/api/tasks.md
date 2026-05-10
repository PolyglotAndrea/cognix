# Tasks API

## Endpoints

### List Tasks

```
GET /api/v1/tasks
```

**Response (200):**

```json
[
  {
    "id": "task123",
    "name": "daily-report",
    "task_type": "agent_call",
    "schedule": "0 9 * * *",
    "state": "active",
    "max_retries": 3,
    "run_count": 15,
    "last_run": "2026-01-15T09:00:00Z",
    "next_run": "2026-01-16T09:00:00Z",
    "created_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### Create Task

```
POST /api/v1/tasks
```

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | ✅ | — | Task name |
| `task_type` | string | ✅ | — | `agent_call`, `rpc_call`, `http_webhook`, `skill_exec`, `workflow` |
| `schedule` | string | ✅ | — | Cron expression, ISO 8601 duration, or ISO 8601 datetime |
| `payload` | string | ❌ | `"{}"` | JSON payload |
| `max_retries` | int | ❌ | `3` | Max retry attempts |

**Response (201):** Task object.

---

### Get Task

```
GET /api/v1/tasks/{task_id}
```

**Response (200):** Task object.

---

### Delete Task

```
DELETE /api/v1/tasks/{task_id}
```

**Response (200):**

```json
{
  "deleted": "task123"
}
```

---

### Get Task Runs

```
GET /api/v1/tasks/{task_id}/runs?limit=10
```

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | `10` | Max runs to return |

**Response (200):**

```json
[
  {
    "id": 1,
    "task_id": "task123",
    "status": "success",
    "result": "Report generated",
    "error": "",
    "duration_ms": 2500,
    "started_at": "2026-01-15T09:00:00Z",
    "finished_at": "2026-01-15T09:00:02Z"
  }
]
```
