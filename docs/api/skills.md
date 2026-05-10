# Skills API

## Endpoints

### List Skills

```
GET /api/v1/skills
```

**Response (200):**

```json
[
  {
    "id": 1,
    "name": "web_search",
    "version": "0.1.0",
    "description": "Search the web for information",
    "author": "cognix",
    "tags": "search,web",
    "installed_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### Search Skills

```
GET /api/v1/skills/search?q=web&tags=search
```

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | ❌ | Search query |
| `tags` | string | ❌ | Comma-separated tags |

**Response (200):** Array of matching skills.

---

### Install Skill

```
POST /api/v1/skills/install
```

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Skill name or path |

**Response (201):**

```json
{
  "name": "web_search",
  "version": "0.1.0",
  "status": "installed"
}
```

---

### Uninstall Skill

```
DELETE /api/v1/skills/{skill_name}
```

**Response (200):**

```json
{
  "uninstalled": "web_search"
}
```
