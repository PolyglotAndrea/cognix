# Skills System

Skills are reusable agent capabilities. Each skill has a `skill.yaml` manifest and a `handler.py` entrypoint.

## Skill Structure

```
my-skill/
├── skill.yaml      # Manifest (name, version, tools, config)
├── handler.py      # Entrypoint (async handler function)
└── requirements.txt # Optional dependencies
```

### skill.yaml

```yaml
name: web_search
version: 0.1.0
description: Search the web for information
author: cognix
tags: [search, web]

tools:
  - name: web_search
    description: Search the web
    parameters:
      type: object
      properties:
        query:
          type: string
          description: Search query
      required: [query]

config:
  api_key:
    type: string
    description: Search API key
    required: true
```

### handler.py

```python
async def web_search(query: str, config: dict) -> str:
    """Search the web for the given query."""
    api_key = config.get("api_key")
    # Implementation here
    return f"Results for: {query}"
```

## Install a Skill

=== "CLI"

    ```bash
    # From marketplace
    cognix skill install web_search

    # From local directory
    cognix skill install ./my-skill/

    # From URL
    cognix skill install https://github.com/user/skill-repo
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/v1/skills/install \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"name": "web_search"}'
    ```

## Search Skills

```bash
cognix skill search "web search"
cognix skill search "database" --tags db,sql
```

## List Installed Skills

=== "CLI"

    ```bash
    cognix skill list
    ```

=== "API"

    ```bash
    curl http://localhost:8000/api/v1/skills -H "Authorization: Bearer TOKEN"
    ```

## Create a Custom Skill

```bash
cognix skill create my-skill
```

This creates a scaffold:

```
my-skill/
├── skill.yaml
├── handler.py
└── requirements.txt
```

Edit the files, then install:

```bash
cd my-skill
cognix skill install .
```

## Uninstall a Skill

```bash
cognix skill uninstall web_search
```

## Skill Tags

Tags help categorize and discover skills:

```yaml
tags: [search, web, research]
```

Search by tag:

```bash
cognix skill search --tags search
```
