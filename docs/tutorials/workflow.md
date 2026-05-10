# Build a Workflow

This tutorial shows how to create a multi-agent workflow that researches a topic, writes an article, and edits it.

## Prerequisites

- Cognix server running
- Three agents created: `researcher`, `writer`, `editor`

## Step 1: Create the Agents

```bash
# Researcher
cognix agent create --name researcher --model gpt-4o
cognix agent update researcher \
  --system-prompt "You are a research specialist. Find comprehensive information on the given topic. Provide key facts, statistics, and sources."

# Writer
cognix agent create --name writer --model gpt-4o
cognix agent update writer \
  --system-prompt "You are a professional writer. Create engaging, well-structured articles based on the research provided."

# Editor
cognix agent create --name editor --model gpt-4o
cognix agent update editor \
  --system-prompt "You are a senior editor. Review and improve articles for clarity, grammar, and flow. Provide the final polished version."
```

## Step 2: Define the Workflow

Create `workflows/content-pipeline.yaml`:

```yaml
name: content-pipeline
description: Research, write, and edit content on any topic
pattern: sequential

steps:
  - agent: researcher
    prompt: |
      Research the following topic thoroughly:
      {{input}}
      
      Provide:
      1. Key facts and statistics
      2. Major developments
      3. Expert opinions
      4. Sources and references

  - agent: writer
    prompt: |
      Write a comprehensive article based on this research:
      
      {{steps[0].output}}
      
      Requirements:
      - Engaging introduction
      - Clear section headers
      - 800-1200 words
      - Conclusion with key takeaways

  - agent: editor
    prompt: |
      Edit and improve this article:
      
      {{steps[1].output}}
      
      Focus on:
      - Grammar and spelling
      - Clarity and flow
      - Factual accuracy
      - Professional tone
```

## Step 3: Run the Workflow

=== "CLI"

    ```bash
    cognix workflow run content-pipeline \
      --var input="The future of renewable energy in 2026"
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/v1/workflows/run \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "workflow": "content-pipeline",
        "variables": {
          "input": "The future of renewable energy in 2026"
        }
      }'
    ```

## Step 4: Review the Output

The workflow executes sequentially:

1. **Researcher** gathers information → output passed to step 2
2. **Writer** creates article draft → output passed to step 3
3. **Editor** polishes final version → returned as result

## Parallel Workflow Example

For tasks that can run simultaneously:

```yaml
name: multi-analysis
pattern: parallel

steps:
  - agent: tech-analyst
    prompt: "Analyze from a technical perspective: {{input}}"
  - agent: market-analyst
    prompt: "Analyze from a market perspective: {{input}}"
  - agent: risk-analyst
    prompt: "Analyze from a risk perspective: {{input}}"

merge:
  agent: synthesizer
  prompt: |
    Combine these analyses into a comprehensive report:
    
    Technical: {{steps[0].output}}
    Market: {{steps[1].output}}
    Risk: {{steps[2].output}}
```

## Router Workflow Example

Route to the right agent based on input:

```yaml
name: smart-support
pattern: router

classifier:
  agent: classifier
  prompt: |
    Classify this support request into one of: technical, billing, general
    Request: {{input}}

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

## Next Steps

- [Develop a Skill](custom-skill.md) — Create reusable capabilities for your agents
- [Deploy to Production](deployment.md) — Take your workflows to production
