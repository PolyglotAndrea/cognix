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

Browser automation is an internal capability selected by the planner. Cognix can
choose among three execution engines:

- `playwright`: deterministic isolated browser execution with a workspace profile.
- `cdp`: attaches to an already-running Chromium session through a configured
  Chrome DevTools Protocol endpoint, useful when the user has manually logged in.
- `browser_use`: delegates high-level multi-step browser work to browser-use when
  that optional runtime and a compatible model provider are configured.

The MCP preset endpoint remains available for explicit Browser MCP setup, but
planner/apply does not automatically bootstrap online CLI MCP processes.
`browser/run` applies workspace network policy, creates approval requests when
needed, runs the selected browser engine when allowed, and persists browser output
as an artifact.
Planner apply can emit a first-class `browser_run` step for authorized browser
work. That step creates a `browser_automation` scheduled task, ensures the
selected browser task executes through `TaskExecutor`, and links the resulting
browser artifact back to the plan/task. If the selected runtime is missing or
misconfigured, the run fails as a browser artifact with recovery guidance instead
of falling back to a text-only agent response.

---

### Code Project Sandbox

```
GET /api/v1/workspaces/{workspace_id}/code-projects
POST /api/v1/workspaces/{workspace_id}/code-projects
POST /api/v1/workspaces/{workspace_id}/code-projects/{project_id}/start
POST /api/v1/workspaces/{workspace_id}/code-projects/{project_id}/stop
GET /api/v1/workspaces/{workspace_id}/code-projects/{project_id}/logs
```

Code projects are written under the workspace sandbox directory. Static projects
run through a local Python preview server. Node projects with `package.json` use
`npm run dev -- --host 127.0.0.1 --port <port>` by default. The frontend shows
running previews in the workspace `Apps` output panel.

Planner apply can also create and start code projects with these internal
actions:

- `create_code_project`: writes files into the workspace sandbox and can
  auto-start a preview.
- `start_code_project`: starts an existing sandbox project by id or name.

These actions are intended for code app, page, prototype, and runnable artifact
requests so the user sees a live preview instead of only receiving code snippets.
