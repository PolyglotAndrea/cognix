# Workflows

Cognix supports multi-agent orchestration through YAML workflow DSL with Jinja2 templating.

## Workflow Patterns

### Sequential

Agents execute one after another. Output of each agent feeds into the next.

```yaml
name: research-and-write
pattern: sequential

steps:
  - agent: researcher
    prompt: "Research the topic: {{topic}}"
  - agent: writer
    prompt: "Write an article based on this research: {{steps[0].output}}"
```

### Parallel

Agents execute simultaneously. Results are collected and optionally merged.

```yaml
name: multi-perspective
pattern: parallel

steps:
  - agent: analyst
    prompt: "Analyze from a technical perspective: {{topic}}"
  - agent: marketer
    prompt: "Analyze from a marketing perspective: {{topic}}"

merge:
  agent: synthesizer
  prompt: "Combine these analyses: {{steps | map(attribute='output') | join('\\n\\n')}}"
```

### Router

Routes to different agents based on input classification.

```yaml
name: support-router
pattern: router

classifier:
  agent: classifier
  prompt: "Classify this request: {{input}}"

routes:
  technical:
    agent: tech-support
    prompt: "{{input}}"
  billing:
    agent: billing-support
    prompt: "{{input}}"
  general:
    agent: general-support
    prompt: "{{input}}"
```

### Loop

Iterates until a condition is met.

```yaml
name: iterative-refinement
pattern: loop

steps:
  - agent: writer
    prompt: "Improve this text: {{current}}"
  - agent: reviewer
    prompt: "Review this text. Reply APPROVED or suggest improvements: {{steps[0].output}}"

condition:
  type: contains
  value: "APPROVED"
  max_iterations: 5
```

## Run a Workflow

=== "CLI"

    ```bash
    cognix workflow run research-and-write --var topic="AI trends 2026"
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/v1/workflows/run \
      -H "Authorization: Bearer TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "workflow": "research-and-write",
        "variables": {"topic": "AI trends 2026"}
      }'
    ```

## Jinja2 Templating

Workflow prompts support Jinja2 templating with these variables:

| Variable | Description |
|----------|-------------|
| `{{input}}` | Original user input |
| `{{steps[N].output}}` | Output of step N |
| `{{steps[N].agent}}` | Agent name of step N |
| `{{variables.name}}` | Custom variables |

### Filters

```yaml
# Join multiple outputs
prompt: "{{steps | map(attribute='output') | join('\\n---\\n')}}"

# Truncate long output
prompt: "{{steps[0].output[:500]}}"

# Conditional content
prompt: "{% if steps[0].output %}Based on: {{steps[0].output}}{% endif %}"
```

## Workflow File Location

Store workflow files in the `workflows/` directory:

```
cognix/
├── workflows/
│   ├── research-and-write.yaml
│   ├── support-router.yaml
│   └── iterative-refinement.yaml
```
