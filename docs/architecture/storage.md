# Storage Layer

Cognix uses SQLAlchemy 2.0 with async support for data persistence.

## Database Support

| Environment | Database | Driver |
|-------------|----------|--------|
| Development | SQLite | `aiosqlite` |
| Production | PostgreSQL | `asyncpg` |

Switch by changing `COGNIX_DATABASE__URL`:

```bash
# Dev (default)
COGNIX_DATABASE__URL=sqlite+aiosqlite:///cognix.db

# Production
COGNIX_DATABASE__URL=postgresql+asyncpg://user:pass@localhost:5432/cognix
```

## Models

All models are in `cognix/storage/models.py`.

### User (`users`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | String(36) | UUID primary key |
| `email` | String(256) | Unique email |
| `name` | String(128) | Display name |
| `password_hash` | String(256) | bcrypt hash (null for OAuth) |
| `oauth_provider` | String(32) | google/github (null for email/password) |
| `oauth_id` | String(128) | Provider user ID |
| `role` | Enum | admin, user, viewer |
| `is_active` | Boolean | Account active flag |

### Agent (`agents`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | String(32) | Primary key |
| `name` | String(128) | Unique agent name |
| `model` | String(128) | LLM model identifier |
| `system_prompt` | Text | System prompt |
| `temperature` | Float | Sampling temperature |
| `max_iterations` | Int | Max tool-call iterations |
| `workspace_id` | String(64) | Associated workspace |

### ScheduledTask (`scheduled_tasks`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | String(32) | Primary key |
| `name` | String(128) | Task name |
| `task_type` | Enum | agent_call, rpc_call, http_webhook, skill_exec, workflow |
| `schedule` | String(256) | Cron expression or ISO datetime |
| `state` | Enum | active, paused, completed, failed |
| `payload` | Text | JSON payload |
| `lease_owner` | String(128) | Distributed lock owner |
| `lease_expires_at` | DateTime | Lock expiration |

### APIKey (`api_keys`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | String(36) | UUID primary key |
| `user_id` | String(36) | Owner user ID |
| `name` | String(128) | Key name |
| `key_hash` | String(256) | bcrypt hash |
| `prefix` | String(16) | Display prefix (cnx_...) |

### Billing Models

- **Plan** (`plans`): Subscription plan definitions
- **Subscription** (`subscriptions`): User subscriptions with Stripe IDs
- **UsageRecord** (`usage_records`): API call/token/agent run tracking

## Session Management

```python
from cognix.storage.database import get_session

async with get_session() as session:
    result = await session.execute(select(UserModel))
    users = result.scalars().all()
```

## Migrations

Alembic is configured for database migrations:

```bash
# Generate migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

For development with SQLite, the schema is auto-created via `Base.metadata.create_all()` on startup.
