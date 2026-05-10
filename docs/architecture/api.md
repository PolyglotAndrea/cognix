# API Server

The Cognix API is a FastAPI application providing REST and WebSocket endpoints.

## Application Structure

```
cognix/api/
├── app.py              # FastAPI app creation, middleware, router registration
├── state.py            # Shared application state (agent runtime, scheduler)
├── lifespan.py         # Startup/shutdown lifecycle (DB init, scheduler start)
├── middleware.py        # CORS, logging, error handling
└── routes/
    ├── auth.py         # /auth/* — OAuth, email/password, API keys
    ├── agents.py       # /api/v1/agents/* — Agent CRUD + chat
    ├── tasks.py        # /api/v1/tasks/* — Scheduled task management
    ├── skills.py       # /api/v1/skills/* — Skill install/search/list
    ├── workspaces.py   # /api/v1/workspaces/* — Workspace management
    ├── approvals.py    # /api/v1/approvals/* — HITL approval flow
    ├── billing.py      # /billing/* — Stripe subscriptions
    ├── rpc.py          # /rpc — JSON-RPC 2.0 endpoint
    ├── bots.py         # /api/v1/bots/* — Bot management
    ├── memory.py       # /api/v1/memory/* — Memory operations
    └── runtime.py      # /api/v1/runtime/* — Runtime operations
```

## Lifespan Events

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()           # Create tables
    await scheduler.start()   # Start APScheduler
    yield
    # Shutdown
    await scheduler.stop()
    await close_db()
```

## Router Registration

All routers are registered in `app.py`:

```python
app.include_router(auth_router)       # /auth/*
app.include_router(agents_router)     # /api/v1/agents/*
app.include_router(tasks_router)      # /api/v1/tasks/*
app.include_router(skills_router)     # /api/v1/skills/*
app.include_router(workspaces_router) # /api/v1/workspaces/*
app.include_router(approvals_router)  # /api/v1/approvals/*
app.include_router(billing_router)    # /billing/*
app.include_router(rpc_router)        # /rpc
```

## Middleware

- **CORS**: Enabled for frontend origin
- **Authentication**: JWT Bearer token or API Key on all protected routes
- **Error Handling**: Global exception handler returns structured errors

## Streaming

Agent chat uses Server-Sent Events (SSE) for streaming responses:

```python
@router.post("/agents/{agent_id}/chat/stream")
async def chat_stream(agent_id: str, body: ChatRequest, ...):
    async def event_generator():
        async for chunk in agent.run_stream(body.message):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## JSON-RPC 2.0

The `/rpc` endpoint supports JSON-RPC 2.0:

```bash
curl -X POST http://localhost:8000/rpc \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "agent.list",
    "id": 1
  }'
```

Methods are registered via the `@rpc_method` decorator in `cognix/rpc/`.

## Interactive API Docs

FastAPI auto-generates interactive documentation:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`
