"""Multi-agent orchestration patterns."""

from __future__ import annotations

import asyncio
import enum
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from cognix.core.agent import Agent, AgentResponse
from cognix.core.context import Context

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    """Result from an orchestration pattern."""

    content: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Pattern(ABC):
    """Base class for orchestration patterns."""

    @abstractmethod
    async def run(self, message: str, context: Context | None = None) -> OrchestrationResult: ...


class Sequential(Pattern):
    """Run agents one after another. Output of each becomes input to the next."""

    def __init__(self, agents: list[Agent], name: str = "sequential") -> None:
        self.agents = agents
        self.name = name

    async def run(self, message: str, context: Context | None = None) -> OrchestrationResult:
        ctx = context or Context()
        current_input = message
        steps: list[dict[str, Any]] = []

        for i, agent in enumerate(self.agents):
            logger.info("Sequential step %d/%d: agent=%s", i + 1, len(self.agents), agent.name)
            await _prepare_agent(agent)
            response = await agent.run(current_input, context=ctx)

            steps.append({
                "step": i,
                "agent": agent.name,
                "input": current_input,
                "output": response.content,
            })

            current_input = response.content

        return OrchestrationResult(
            content=current_input,
            steps=steps,
            metadata={"pattern": self.name, "agent_count": len(self.agents)},
        )


class Parallel(Pattern):
    """Run agents concurrently and collect all results."""

    def __init__(self, agents: list[Agent], name: str = "parallel") -> None:
        self.agents = agents
        self.name = name

    async def run(self, message: str, context: Context | None = None) -> OrchestrationResult:
        ctx = context or Context()

        async def _run_agent(agent: Agent) -> dict[str, Any]:
            await _prepare_agent(agent)
            response = await agent.run(message, context=ctx)
            return {
                "agent": agent.name,
                "output": response.content,
            }

        results = await asyncio.gather(*[_run_agent(a) for a in self.agents])

        # Combine all outputs
        combined = "\n\n".join(
            f"**{r['agent']}**: {r['output']}" for r in results
        )

        return OrchestrationResult(
            content=combined,
            steps=results,
            metadata={"pattern": self.name, "agent_count": len(self.agents)},
        )


class Router(Pattern):
    """Route to an agent based on a classifier's decision."""

    def __init__(
        self,
        agents: dict[str, Agent],
        classifier: Agent,
        name: str = "router",
    ) -> None:
        self.agents = agents
        self.classifier = classifier
        self.name = name

    async def run(self, message: str, context: Context | None = None) -> OrchestrationResult:
        ctx = context or Context()

        # Build classification prompt
        agent_names = list(self.agents.keys())
        classify_prompt = (
            f"Given the following user message, choose the most appropriate agent from: "
            f"{', '.join(agent_names)}\n\n"
            f"User message: {message}\n\n"
            f"Reply with ONLY the agent name, nothing else."
        )

        # Classify
        await _prepare_agent(self.classifier)
        classify_response = await self.classifier.run(classify_prompt, context=ctx)
        chosen = classify_response.content.strip().lower()

        # Find matching agent (fuzzy match)
        target_agent = None
        for name, agent in self.agents.items():
            if name.lower() in chosen or chosen in name.lower():
                target_agent = agent
                chosen = name
                break

        if not target_agent:
            # Fallback to first agent
            chosen = agent_names[0]
            target_agent = self.agents[chosen]
            logger.warning("Router classifier didn't match, falling back to '%s'", chosen)

        logger.info("Router selected agent: %s", chosen)

        # Run chosen agent
        await _prepare_agent(target_agent)
        response = await target_agent.run(message, context=ctx)

        return OrchestrationResult(
            content=response.content,
            steps=[
                {"step": "classify", "agent": self.classifier.name, "output": chosen},
                {"step": "execute", "agent": target_agent.name, "output": response.content},
            ],
            metadata={"pattern": self.name, "chosen_agent": chosen},
        )


LoopCondition = Callable[[AgentResponse, int], bool]


class Loop(Pattern):
    """Run an agent repeatedly until a condition is met."""

    def __init__(
        self,
        agent: Agent,
        condition: LoopCondition | None = None,
        max_iterations: int = 10,
        name: str = "loop",
    ) -> None:
        self.agent = agent
        self.condition = condition or (lambda resp, i: i < max_iterations)
        self.max_iterations = max_iterations
        self.name = name

    async def run(self, message: str, context: Context | None = None) -> OrchestrationResult:
        ctx = context or Context()
        current_input = message
        steps: list[dict[str, Any]] = []

        for i in range(self.max_iterations):
            logger.info("Loop iteration %d/%d: agent=%s", i + 1, self.max_iterations, self.agent.name)
            await _prepare_agent(self.agent)
            response = await self.agent.run(current_input, context=ctx)

            steps.append({
                "iteration": i,
                "agent": self.agent.name,
                "input": current_input,
                "output": response.content,
            })

            # Check condition
            if not self.condition(response, i + 1):
                logger.info("Loop condition met after %d iterations", i + 1)
                break

            # Use output as next input
            current_input = response.content

        return OrchestrationResult(
            content=current_input,
            steps=steps,
            metadata={"pattern": self.name, "iterations": len(steps)},
        )


async def _prepare_agent(agent: Agent) -> None:
    if not getattr(agent, "workspace_id", None):
        return
    from cognix.core.mounts import attach_workspace_runtime_tools

    await attach_workspace_runtime_tools(agent)
