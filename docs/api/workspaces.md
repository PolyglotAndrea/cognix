# Workspaces API

## Endpoints

### List Workspaces

```
GET /api/v1/workspaces
```

**Response (200):**

```json
[
  {
    "id": "ws-abc123",
    "name": "Default Workspace"
  }
]
```

---

### Create Workspace

```
POST /api/v1/workspaces
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Workspace name |

**Response (201):** Workspace object.

---

### List Chats

```
GET /api/v1/workspaces/{workspace_id}/chats
```

**Response (200):** Array of chat sessions.

---

### Create Chat

```
POST /api/v1/workspaces/{workspace_id}/chats
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | ❌ | Chat title |
| `system_prompt` | string | ❌ | Override system prompt |
| `model_profiles` | string[] | ❌ | Models to use |
| `metadata` | object | ❌ | Custom metadata (e.g., `agent_id`) |

**Response (201):** Chat session object.

---

### Get Chat Messages

```
GET /api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages
```

**Response (200):** Array of stored messages.

---

### Send Message (Streaming)

```
POST /api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | ✅ | Message content |
| `model_profiles` | string[] | ❌ | Models to use for this message |

**Response:** Server-Sent Events (SSE).

---

### Update Chat Settings

```
PATCH /api/v1/workspaces/{workspace_id}/chats/{chat_id}
```

**Request Body:** Partial update of chat fields.

---

### List Workspace Files

```
GET /api/v1/workspaces/{workspace_id}/files?path=
```

**Response (200):**

```json
[
  {
    "path": "src/main.py",
    "name": "main.py",
    "kind": "file",
    "size": 1234,
    "updated_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### Preview File

```
GET /api/v1/workspaces/{workspace_id}/files/preview?path=src/main.py
```

**Response (200):**

```json
{
  "path": "src/main.py",
  "content": "# File contents..."
}
```

---

### List Workspace Events

```
GET /api/v1/workspaces/{workspace_id}/events?limit=50
```

**Response (200):** Array of workspace events.

---

### MCP Tools

```
GET /api/v1/workspaces/{workspace_id}/mcp/servers/{server_id}/tools
POST /api/v1/workspaces/{workspace_id}/mcp/servers/{server_id}/tools/{tool_name}/call
```

Tool calls require skills write permission and apply `permission_mode` checks before execution.
Set `metadata.disabled_tools` on a workspace MCP server to hide individual tools from Agent mounting and debug calls.

---

### Browser Automation

```
POST /api/v1/workspaces/{workspace_id}/browser/mcp-preset
GET /api/v1/workspaces/{workspace_id}/browser/profile?profile=default
POST /api/v1/workspaces/{workspace_id}/browser/run
```

Browser automation is an internal capability selected by the planner. The MCP
preset provisions a Playwright MCP server with a workspace-scoped browser profile.
`browser/run` applies workspace network policy, creates approval requests when
needed, runs Playwright when allowed, and persists browser output as an artifact.
