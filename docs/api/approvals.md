# Approvals API

Human-in-the-loop (HITL) approval system for agent actions.

## Endpoints

### List Approvals

```
GET /api/v1/approvals?workspace_id=...&include_resolved=true
```

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `workspace_id` | string | ✅ | Workspace ID |
| `include_resolved` | bool | `false` | Include resolved approvals |

**Response (200):**

```json
[
  {
    "id": "approval123",
    "workspace_id": "ws-abc",
    "agent_id": "agent123",
    "action": "file_write",
    "description": "Write to src/config.py",
    "payload": {"path": "src/config.py", "content": "..."},
    "status": "pending",
    "metadata": {"runtime": "claude-agent-sdk"},
    "created_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### Approve

```
POST /api/v1/approvals/{approval_id}/approve
```

Approve the pending action.

**Response (200):**

```json
{
  "id": "approval123",
  "status": "approved"
}
```

---

### Reject

```
POST /api/v1/approvals/{approval_id}/reject
```

Reject the pending action.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `response` | string | ❌ | Rejection reason |

**Response (200):**

```json
{
  "id": "approval123",
  "status": "rejected"
}
```

---

### Resume (Claude Agent SDK)

```
POST /api/v1/approvals/{approval_id}/resume
```

Resume a Claude Agent SDK approval with an optional human response.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `response` | string | ❌ | Human response/instruction |

**Response:** Streaming response from the resumed agent.

---

### Respond

```
POST /api/v1/approvals/{approval_id}/respond
```

Send a human response to a waiting agent.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `response` | string | ✅ | Human response |

**Response (200):**

```json
{
  "id": "approval123",
  "status": "responded"
}
```
