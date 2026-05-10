# Agents API

## Endpoints

### List Agents

```
GET /api/v1/agents
```

**Response (200):**

```json
[
  {
    "id": "agent123",
    "name": "my-assistant",
    "model": "gpt-4o",
    "description": "Research assistant",
    "system_prompt": "You are a helpful assistant.",
    "temperature": 0.7,
    "max_iterations": 10,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### Create Agent

```
POST /api/v1/agents
```

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | ✅ | — | Unique agent name |
| `model` | string | ❌ | `gpt-4o` | LLM model |
| `description` | string | ❌ | `""` | Short description |
| `system_prompt` | string | ❌ | `"You are a helpful assistant."` | System prompt |
| `temperature` | float | ❌ | `0.7` | Sampling temperature (0–2) |
| `max_iterations` | int | ❌ | `10` | Max tool-call iterations |

**Response (201):** Agent object.

**Errors:**

| Status | Detail |
|--------|--------|
| 400 | Invalid parameters |
| 409 | Agent name already exists |

---

### Get Agent

```
GET /api/v1/agents/{agent_id}
```

**Response (200):** Agent object.

**Errors:**

| Status | Detail |
|--------|--------|
| 404 | Agent not found |

---

### Update Agent

```
PUT /api/v1/agents/{agent_id}
```

**Request Body:** Any subset of agent fields.

**Response (200):** Updated agent object.

---

### Delete Agent

```
DELETE /api/v1/agents/{agent_id}
```

**Response (200):**

```json
{
  "deleted": "agent123"
}
```

---

### Chat (Non-Streaming)

```
POST /api/v1/agents/{agent_id}/chat
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | ✅ | User message |

**Response (200):**

```json
{
  "response": "Here's the answer...",
  "agent_id": "agent123",
  "model": "gpt-4o",
  "tokens_used": 150
}
```

---

### Chat (Streaming)

```
POST /api/v1/agents/{agent_id}/chat/stream
```

**Request Body:** Same as non-streaming.

**Response:** Server-Sent Events (SSE)

```
data: {"delta": "Here's"}
data: {"delta": " the"}
data: {"delta": " answer"}
data: {"type": "tool_call", "name": "web_search", "args": {"query": "..."}}
data: {"type": "tool_result", "name": "web_search", "result": {...}}
data: {"delta": " Based on my research..."}
data: [DONE]
```

**Event Types:**

| Type | Fields | Description |
|------|--------|-------------|
| `delta` | `content` | Text chunk |
| `tool_call` | `name`, `args` | Tool invocation |
| `tool_result` | `name`, `result` | Tool output |
| `log` | `level`, `message` | Log entry |
