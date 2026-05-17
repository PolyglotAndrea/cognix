"""YAML workflow definition and execution engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from cognix.core.context import Context
from cognix.core.registry import AgentRegistry
from cognix.orchestrator.patterns import Loop, OrchestrationResult, Parallel, Sequential

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """A single step in a workflow."""

    id: str
    agent: str
    input: str = ""
    output: str = ""
    pattern: str = "sequential"  # sequential, parallel, router, loop
    condition: str | None = None
    max_iterations: int = 10
    on_error: str | None = None
    parallel: bool = False


@dataclass
class Workflow:
    """A workflow definition."""

    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)


def parse_workflow(yaml_path: str | Path) -> Workflow:
    """Parse a YAML workflow file."""
    path = Path(yaml_path)
    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {yaml_path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid workflow format: expected dict, got {type(data)}")

    name = data.get("name", path.stem)
    description = data.get("description", "")
    variables = data.get("variables", {})

    steps = []
    for step_data in data.get("steps", []):
        step = WorkflowStep(
            id=step_data.get("id", f"step_{len(steps)}"),
            agent=step_data.get("agent", ""),
            input=step_data.get("input", ""),
            output=step_data.get("output", ""),
            pattern=step_data.get("pattern", "sequential"),
            condition=step_data.get("condition"),
            max_iterations=step_data.get("max_iterations", 10),
            on_error=step_data.get("on_error"),
            parallel=step_data.get("parallel", False),
        )
        steps.append(step)

    return Workflow(
        name=name,
        description=description,
        steps=steps,
        variables=variables,
    )


def validate_workflow(yaml_path: str | Path) -> list[str]:
    """Validate a workflow file and return list of errors."""
    errors = []

    try:
        workflow = parse_workflow(yaml_path)
    except Exception as e:
        return [str(e)]

    if not workflow.name:
        errors.append("Workflow must have a name")

    if not workflow.steps:
        errors.append("Workflow must have at least one step")

    step_ids = set()
    for i, step in enumerate(workflow.steps):
        if not step.id:
            errors.append(f"Step {i} must have an id")
        elif step.id in step_ids:
            errors.append(f"Duplicate step id: {step.id}")
        else:
            step_ids.add(step.id)

        if not step.agent:
            errors.append(f"Step '{step.id}' must specify an agent")

    return errors


def _render_template(template: str, variables: dict[str, Any]) -> str:
    """Render a Jinja2 template string."""
    try:
        from jinja2 import Template

        return Template(template).render(**variables)
    except Exception:
        # Fallback: simple string substitution
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result


async def execute_workflow(
    workflow: Workflow,
    registry: AgentRegistry,
    initial_input: str = "",
    context: Context | None = None,
    *,
    workspace_id: str | None = None,
) -> OrchestrationResult:
    """Execute a workflow."""
    ctx = context or Context()
    variables = {**workflow.variables, "input": initial_input}
    steps_results: list[dict[str, Any]] = []
    workflow_start = datetime.now(UTC)

    # Resolve workspace_id from context metadata if not provided
    if not workspace_id:
        workspace_id = ctx.metadata.get("workspace_id")

    for step in workflow.steps:
        logger.info("Executing workflow step: %s (agent=%s)", step.id, step.agent)

        # Resolve agent
        agent = registry.get_by_name(step.agent) or registry.get(step.agent)
        if not agent:
            error_msg = f"Agent '{step.agent}' not found for step '{step.id}'"
            logger.error(error_msg)
            if step.on_error:
                variables[step.on_error] = error_msg
                steps_results.append({
                    "step": step.id,
                    "agent": step.agent,
                    "status": "skipped",
                    "reason": error_msg,
                })
                continue
            raise ValueError(error_msg)

        # Resolve input
        step_input = _render_template(step.input, variables) if step.input else initial_input

        # Check condition
        if step.condition:
            condition_str = _render_template(step.condition, variables)
            if condition_str.lower() in ("false", "0", "no", ""):
                logger.info("Skipping step '%s': condition not met", step.id)
                step_result = {
                    "step": step.id,
                    "agent": step.agent,
                    "status": "skipped",
                    "reason": "condition not met",
                }
                steps_results.append(step_result)
                _emit_step_event(workspace_id, workflow.name, step_result)
                continue

        # Execute based on pattern
        step_start = datetime.now(UTC)
        try:
            if step.pattern == "parallel" or step.parallel:
                pattern = Parallel(agents=[agent])
            elif step.pattern == "loop":
                pattern = Loop(agent=agent, max_iterations=step.max_iterations)
            else:
                pattern = Sequential(agents=[agent])

            result = await pattern.run(step_input, context=ctx)
            step_end = datetime.now(UTC)

            # Store output in variables
            output_key = step.output or step.id
            variables[output_key] = result.content

            step_result = {
                "step": step.id,
                "agent": step.agent,
                "status": "success",
                "output": result.content,
                "started_at": step_start.isoformat(),
                "finished_at": step_end.isoformat(),
                "duration_ms": int((step_end - step_start).total_seconds() * 1000),
            }
            steps_results.append(step_result)
            _emit_step_event(workspace_id, workflow.name, step_result)

        except Exception as e:
            step_end = datetime.now(UTC)
            error_msg = f"Step '{step.id}' failed: {e}"
            logger.error(error_msg)
            step_result = {
                "step": step.id,
                "agent": step.agent,
                "status": "error",
                "error": error_msg,
                "started_at": step_start.isoformat(),
                "finished_at": step_end.isoformat(),
                "duration_ms": int((step_end - step_start).total_seconds() * 1000),
            }
            if step.on_error:
                variables[step.on_error] = error_msg
                steps_results.append(step_result)
                _emit_step_event(workspace_id, workflow.name, step_result)
                continue
            steps_results.append(step_result)
            _emit_step_event(workspace_id, workflow.name, step_result)
            raise

    workflow_end = datetime.now(UTC)

    # Final output is the last step's output or the last variable set
    final_output = ""
    if steps_results:
        last_success = next(
            (r for r in reversed(steps_results) if r["status"] == "success"),
            None,
        )
        if last_success:
            final_output = last_success.get("output", "")

    return OrchestrationResult(
        content=final_output,
        steps=steps_results,
        metadata={
            "workflow": workflow.name,
            "step_count": len(workflow.steps),
            "variables": {k: v for k, v in variables.items() if k != "input"},
            "started_at": workflow_start.isoformat(),
            "finished_at": workflow_end.isoformat(),
            "duration_ms": int((workflow_end - workflow_start).total_seconds() * 1000),
        },
    )


def _emit_step_event(
    workspace_id: str | None,
    workflow_name: str,
    step_result: dict[str, Any],
) -> None:
    """Emit a workflow step event to the workspace events file."""
    if not workspace_id:
        return
    try:
        from cognix.local.home import CognixHome
        from cognix.local.workspace import WorkspaceManager

        home = CognixHome.default().ensure()
        wm = WorkspaceManager(home)
        wm.append_event(workspace_id, {
            "type": "workflow.step.completed",
            "workflow": workflow_name,
            "step": step_result.get("step"),
            "agent": step_result.get("agent"),
            "status": step_result.get("status"),
            "duration_ms": step_result.get("duration_ms"),
            "error": step_result.get("error"),
        })
    except Exception:
        logger.debug("Failed to emit workflow step event", exc_info=True)
