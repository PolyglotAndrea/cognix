# Configuration

Cognix uses Pydantic Settings for configuration. All environment variables use the `COGNIX_` prefix with `__` for nesting.

## Environment Variables

Create a `.env` file in the project root:

```bash
COGNIX_DEBUG=true
COGNIX_DEFAULT_MODEL=gpt-4o
COGNIX_LLM_API_KEY=sk-...
COGNIX_AUTH__SECRET_KEY=your-secret-key
```

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `COGNIX_DEBUG` | `false` | Enable debug mode |
| `COGNIX_DEFAULT_MODEL` | `gpt-4o` | Default LLM model for agents |
| `COGNIX_LLM_API_KEY` | — | API key for LLM provider |
| `COGNIX_LLM_API_BASE` | — | Custom LLM API base URL |

### Server Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `COGNIX_SERVER__HOST` | `0.0.0.0` | Server bind host |
| `COGNIX_SERVER__PORT` | `8000` | Server bind port |
| `COGNIX_SERVER__RELOAD` | `false` | Enable auto-reload (dev) |

### Database Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `COGNIX_DATABASE__URL` | `sqlite+aiosqlite:///cognix.db` | Database connection string |
| `COGNIX_DATABASE__ECHO` | `false` | Log SQL queries |

For production with PostgreSQL:

```bash
COGNIX_DATABASE__URL=postgresql+asyncpg://user:pass@localhost:5432/cognix
```

### Auth Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `COGNIX_AUTH__SECRET_KEY` | — | **Required.** JWT signing secret |
| `COGNIX_AUTH__TOKEN_EXPIRE_HOURS` | `24` | JWT token expiration |
| `COGNIX_AUTH__GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `COGNIX_AUTH__GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `COGNIX_AUTH__GITHUB_CLIENT_ID` | — | GitHub OAuth client ID |
| `COGNIX_AUTH__GITHUB_CLIENT_SECRET` | — | GitHub OAuth client secret |
| `COGNIX_AUTH__FRONTEND_URL` | `http://localhost:5173` | Frontend URL for OAuth redirects |

### Billing Settings (Stripe)

| Variable | Default | Description |
|----------|---------|-------------|
| `COGNIX_BILLING__STRIPE_SECRET_KEY` | — | Stripe secret key |
| `COGNIX_BILLING__STRIPE_WEBHOOK_SECRET` | — | Stripe webhook signing secret |
| `COGNIX_BILLING__STRIPE_PRICE_STARTER` | — | Stripe price ID for Starter plan |
| `COGNIX_BILLING__STRIPE_PRICE_PRO` | — | Stripe price ID for Pro plan |

## Config File

You can also use a `config.yaml` file:

```yaml
debug: true
default_model: gpt-4o
server:
  host: "0.0.0.0"
  port: 8000
auth:
  secret_key: "your-secret-key"
database:
  url: "sqlite+aiosqlite:///cognix.db"
```

!!! warning
    Never commit your `.env` file or secrets to version control. The `.gitignore` already excludes `.env` files.
