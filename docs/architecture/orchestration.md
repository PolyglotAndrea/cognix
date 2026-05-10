# Orchestration

Cognix supports multi-agent orchestration through four patterns: Sequential, Parallel, Router, and Loop.

## Patterns

### Sequential

Agents execute in order. Each agent's output feeds into the next.

```python
from cognix.orchestrator import SequentialOrchestrator

orch = SequentialOrchestrator(agents=[researcher, writer, editor])
result = await orch.run(topic="AI trends")
```

### Parallel

Agents execute simultaneously. Results are collected and optionally merged.

```python
from cognix.orchestrator import ParallelOrchestrator

orch = ParallelOrchestrator(
    agents=[analyst, marketer, engineer],
    merger=synthesizer  # Optional: combines results
)
result = await orch.run(topic="product launch")
```

### Router

Routes input to the most appropriate agent based on classification.

```python
from cognix.orchestrator import RouterOrchestrator

orch = RouterOrchestrator(
    classifier=classifier_agent,
    routes={
        "technical": tech_agent,
        "billing": billing_agent,
        "general": general_agent,
    }
)
result = await orch.run(input="How do I reset my password?")
```

### Loop

Iterates until a condition is met or max iterations reached.

```python
from cognix.orchestrator import LoopOrchestrator

orch = LoopOrchestrator(
    agents=[writer, reviewer],
    condition=lambda output: "APPROVED" in output,
    max_iterations=5
)
result = await orch.run(text="Draft article...")
```

## YAML Workflow DSL

Define workflows in YAML files:

```yaml
name: content-pipeline
pattern: sequential

steps:
  - agent: researcher
    prompt: "Research: {{topic}}"
  - agent: writer
    prompt: "Write based on: {{steps[0].output}}"
  - agent: editor
    prompt: "Edit and improve: {{steps[1].output}}"
```

### Template Variables

| Variable | Description |
|----------|-------------|
| `{{input}}` | Original user input |
| `{{steps[N].output}}` | Output of step N |
| `{{steps[N].agent}}` | Agent name of step N |
| `{{variables.name}}` | Custom variables passed at runtime |

## Orchestrator Base Class

All orchestrators extend `BaseOrchestrator`:

```python
class BaseOrchestrator(ABC):
    agents: list[Agent]
    
    @abstractmethod
    async def run(self, **kwargs) -> OrchestrationResult:
        ...
    
    async def _execute_agent(self, agent: Agent, prompt: str) -> str:
        # Common execution logic
        ...
```

## Orchestration Result

```python
@dataclass
class OrchestrationResult:
    output: str                          # Final output
    steps: list[StepResult]              # Per-step results
    total_tokens: int                    # Token usage
    duration_ms: int                     # Execution time
    agent_calls: int                     # Number of LLM calls
```
