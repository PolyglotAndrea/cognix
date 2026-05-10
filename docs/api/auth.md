# Auth API

## Endpoints

### Register

```
POST /auth/register
```

Create a new user account with email and password.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✅ | Valid email address |
| `password` | string | ✅ | Min 8 chars, must contain letter + number |
| `name` | string | ❌ | Display name (defaults to email prefix) |

**Response (201):**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "abc123",
    "email": "user@example.com",
    "name": "User",
    "role": "user"
  }
}
```

**Errors:**

| Status | Detail |
|--------|--------|
| 400 | Password validation failed |
| 409 | Email already registered |

---

### Login

```
POST /auth/login
```

Login with email and password.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | ✅ | Registered email |
| `password` | string | ✅ | Account password |

**Response (200):**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "abc123",
    "email": "user@example.com",
    "name": "User",
    "role": "user"
  }
}
```

**Errors:**

| Status | Detail |
|--------|--------|
| 401 | Invalid email or password |
| 403 | Account is disabled |

---

### OAuth Login

```
GET /auth/login/{provider}
```

Redirect to OAuth provider for authentication.

**Providers:** `google`, `github`

**Response:** 302 redirect to provider's authorization URL.

---

### OAuth Callback

```
GET /auth/callback/{provider}?code=...
```

Handle OAuth callback, create/update user, return JWT.

**Response:** 302 redirect to frontend with `?token=...`.

---

### Get Current User

```
GET /auth/me
```

Get the authenticated user's info.

**Headers:** `Authorization: Bearer TOKEN` or `X-API-Key: cnx_...`

**Response (200):**

```json
{
  "id": "abc123",
  "email": "user@example.com",
  "name": "User",
  "role": "user",
  "auth_method": "jwt"
}
```

---

### Create API Key

```
POST /auth/api-keys
```

Create a new API key. The full key is only returned once.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ❌ | Key name (default: "default") |

**Response (201):**

```json
{
  "id": "key123",
  "name": "my-script",
  "prefix": "cnx_abc12345...",
  "key": "cnx_abc1234567890abcdef...",
  "created_at": "2026-01-01T00:00:00Z",
  "last_used_at": null
}
```

---

### List API Keys

```
GET /auth/api-keys
```

List all API keys for the authenticated user.

**Response (200):**

```json
[
  {
    "id": "key123",
    "name": "my-script",
    "prefix": "cnx_abc12345...",
    "created_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2026-01-02T12:00:00Z"
  }
]
```

---

### Delete API Key

```
DELETE /auth/api-keys/{key_id}
```

Revoke an API key.

**Response (200):**

```json
{
  "deleted": "key123"
}
```

**Errors:**

| Status | Detail |
|--------|--------|
| 404 | API key not found |
