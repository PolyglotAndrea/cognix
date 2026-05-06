"""Agent registry for managing agent instances."""

from __future__ import annotations

import logging
from typing import Any

from cognix.core.agent import Agent
from cognix.core.events import EventBus

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Central registry for Agent instances."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._agents: dict[str, Agent] = {}
        self._event_bus = event_bus

    def register(self, agent: Agent) -> None:
        """Register an agent."""
        if self._event_bus:
            agent.set_event_bus(self._event_bus)
        self._agents[agent.id] = agent
        logger.info("Registered agent: %s (%s)", agent.name, agent.id)

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent by ID."""
        agent = self._agents.pop(agent_id, None)
        if agent:
            logger.info("Unregistered agent: %s (%s)", agent.name, agent.id)
            return True
        return False

    def get(self, agent_id: str) -> Agent | None:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def get_by_name(self, name: str) -> Agent | None:
        """Get an agent by name."""
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    def list_all(self) -> list[dict[str, Any]]:
        """List all registered agents as dicts."""
        return [a.to_dict() for a in self._agents.values()]

    def count(self) -> int:
        return len(self._agents)

    def clear(self) -> None:
        self._agents.clear()
