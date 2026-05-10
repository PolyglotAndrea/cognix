# Authentication

Cognix supports multiple authentication methods: email/password, OAuth2 (Google, GitHub), JWT tokens, and API keys.

## Authentication Methods

### Email / Password

Register and login with email and password:

=== "Register"

    ```bash
    curl -X POST http://localhost:8000/auth/register \
      -H "Content-Type: application/json" \
      -d '{"email": "user@example.com", "password": "securepass123", "name": "User"}'
    ```

=== "Login"

    ```bash
    curl -X POST http://localhost:8000/auth/login \
      -H "Content-Type: application/json" \
      -d '{"email": "user@example.com", "password": "securepass123"}'
    ```

Both return a JWT token:

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {"id": "...", "email": "user@example.com", "name": "User", "role": "user"}
}
```

!!! note
    Passwords must be at least 8 characters with at least one letter and one number.

### OAuth2 (Google / GitHub)

1. Redirect user to `/auth/login/google` or `/auth/login/github`
2. User authenticates with the provider
3. Provider redirects back to `/auth/callback/{provider}?code=...`
4. Cognix exchanges code for user info and creates/updates user
5. User is redirected to frontend with JWT token

### JWT Bearer Token

Use the token from login/register/OAuth in subsequent requests:

```bash
curl http://localhost:8000/api/v1/agents \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### API Keys

API keys are for programmatic access (scripts, CI/CD, etc.):

=== "Create"

    ```bash
    curl -X POST http://localhost:8000/auth/api-keys \
      -H "Authorization: Bearer JWT_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"name": "my-script"}'
    ```

    Returns the full key **once**:

    ```json
    {
      "id": "...",
      "name": "my-script",
      "prefix": "cnx_abc12345...",
      "key": "cnx_abc1234567890abcdef..."
    }
    ```

=== "Use"

    ```bash
    curl http://localhost:8000/api/v1/agents \
      -H "X-API-Key: cnx_abc1234567890abcdef..."
    ```

=== "List"

    ```bash
    curl http://localhost:8000/auth/api-keys \
      -H "Authorization: Bearer JWT_TOKEN"
    ```

=== "Delete"

    ```bash
    curl -X DELETE http://localhost:8000/auth/api-keys/{id} \
      -H "Authorization: Bearer JWT_TOKEN"
    ```

## RBAC (Role-Based Access Control)

### Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access to everything |
| `user` | Read/write agents, tasks, skills |
| `viewer` | Read-only access to agents, tasks, skills |

### Permission Matrix

| Permission | Admin | User | Viewer |
|------------|:-----:|:----:|:------:|
| `agents:read` | ✅ | ✅ | ✅ |
| `agents:write` | ✅ | ✅ | ❌ |
| `agents:delete` | ✅ | ❌ | ❌ |
| `tasks:read` | ✅ | ✅ | ✅ |
| `tasks:write` | ✅ | ✅ | ❌ |
| `skills:read` | ✅ | ✅ | ✅ |
| `skills:write` | ✅ | ✅ | ❌ |
| `admin` | ✅ | ❌ | ❌ |

### Protected Endpoints

All endpoints except these require authentication:

| Endpoint | Auth Required |
|----------|:-------------:|
| `GET /health` | ❌ |
| `GET /` | ❌ |
| `GET /docs` | ❌ |
| `GET /openapi.json` | ❌ |
| `POST /auth/login` | ❌ |
| `POST /auth/register` | ❌ |
| `GET /auth/callback/*` | ❌ |
| `GET /billing/plans` | ❌ |
