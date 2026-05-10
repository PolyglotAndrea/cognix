# RPC API

JSON-RPC 2.0 endpoint for inter-service communication.

## Endpoint

```
POST /rpc
```

## Request Format

```json
{
  "jsonrpc": "2.0",
  "method": "method.name",
  "params": {"key": "value"},
  "id": 1
}
```

## Response Format

**Success:**

```json
{
  "jsonrpc": "2.0",
  "result": {...},
  "id": 1
}
```

**Error:**

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32600,
    "message": "Invalid Request"
  },
  "id": 1
}
```

## Available Methods

### agent.list

List all registered agents.

```bash
curl -X POST http://localhost:8000/rpc \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "agent.list", "id": 1}'
```

### agent.get

Get agent by ID.

```json
{
  "jsonrpc": "2.0",
  "method": "agent.get",
  "params": {"agent_id": "agent123"},
  "id": 1
}
```

### agent.chat

Send a message to an agent.

```json
{
  "jsonrpc": "2.0",
  "method": "agent.chat",
  "params": {
    "agent_id": "agent123",
    "message": "Hello!"
  },
  "id": 1
}
```

### task.list

List scheduled tasks.

### task.create

Create a scheduled task.

### skill.list

List installed skills.

### skill.install

Install a skill.

## Error Codes

| Code | Message | Description |
|------|---------|-------------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid Request | Missing required fields |
| -32601 | Method not found | Unknown method |
| -32602 | Invalid params | Invalid parameters |
| -32603 | Internal error | Server-side error |

## Transports

### HTTP

Standard HTTP POST to `/rpc`.

### WebSocket

Connect to `ws://localhost:8000/rpc/ws` for bidirectional JSON-RPC communication.

```javascript
const ws = new WebSocket('ws://localhost:8000/rpc/ws')
ws.send(JSON.stringify({
  jsonrpc: '2.0',
  method: 'agent.list',
  id: 1
}))
```
