"""Unit tests for core modules."""

import asyncio

import pytest

from cognix.core.agent import Agent, AgentState
from cognix.core.context import Context
from cognix.core.events import EventBus, Events
from cognix.core.memory import InMemoryBackend
from cognix.core.registry import AgentRegistry
from cognix.core.tool import Tool, tool


class TestAgent:
    def test_create_agent(self):
        agent = Agent(name="test", model="echo")
        assert agent.name == "test"
        assert agent.model == "echo"
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_agent_run_echo(self):
        agent = Agent(name="test", model="echo")
        response = await agent.run("Hello")
        assert "Echo: Hello" in response.content
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_agent_with_tool(self):
        @tool(name="greet", description="Greet someone")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        agent = Agent(name="greeter", model="echo", tools=[greet])
        assert "greet" in [t.name for t in agent.tools]

        response = await agent.run("Greet Alice")
        assert "Echo: Greet Alice" in response.content

    def test_agent_to_dict(self):
        agent = Agent(name="test", model="gpt-4o")
        d = agent.to_dict()
        assert d["name"] == "test"
        assert d["model"] == "gpt-4o"
        assert "id" in d


class TestTool:
    def test_tool_decorator(self):
        @tool(name="add", description="Add two numbers")
        async def add(a: int, b: int) -> int:
            return a + b

        assert add.name == "add"
        assert add.description == "Add two numbers"

    @pytest.mark.asyncio
    async def test_tool_execute(self):
        @tool(name="multiply", description="Multiply")
        async def multiply(a: int, b: int) -> int:
            return a * b

        result = await multiply.execute(a=3, b=4)
        assert result == 12

    def test_tool_schema(self):
        @tool(name="search", description="Search")
        async def search(query: str, limit: int = 10) -> str:
            return ""

        schema = search.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "search"
        assert "query" in schema["function"]["parameters"]["properties"]


class TestEventBus:
    @pytest.mark.asyncio
    async def test_emit_and_on(self):
        bus = EventBus()
        received = []

        async def handler(event, **kwargs):
            received.append((event, kwargs))

        bus.on("test.event", handler)
        await bus.emit("test.event", {"key": "value"})
        assert len(received) == 1
        assert received[0] == ("test.event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_off(self):
        bus = EventBus()
        received = []

        async def handler(event, data=None):
            received.append(event)

        bus.on("test", handler)
        bus.off("test", handler)
        await bus.emit("test")
        assert len(received) == 0


class TestMemory:
    @pytest.mark.asyncio
    async def test_set_get(self):
        mem = InMemoryBackend()
        await mem.set("key1", "value1")
        entry = await mem.get("key1")
        assert entry is not None
        assert entry.value == "value1"

    @pytest.mark.asyncio
    async def test_delete(self):
        mem = InMemoryBackend()
        await mem.set("key1", "value1")
        assert await mem.delete("key1") is True
        assert await mem.get("key1") is None

    @pytest.mark.asyncio
    async def test_search(self):
        mem = InMemoryBackend()
        await mem.set("greeting", "hello world")
        await mem.set("farewell", "goodbye world")
        results = await mem.search("world")
        assert len(results) == 2


class TestRegistry:
    def test_register_and_get(self):
        bus = EventBus()
        registry = AgentRegistry(event_bus=bus)
        agent = Agent(name="test", model="echo")
        registry.register(agent)
        assert registry.get(agent.id) is agent
        assert registry.count() == 1

    def test_get_by_name(self):
        registry = AgentRegistry()
        agent = Agent(name="my-agent", model="echo")
        registry.register(agent)
        assert registry.get_by_name("my-agent") is agent

    def test_list_all(self):
        registry = AgentRegistry()
        registry.register(Agent(name="a", model="echo"))
        registry.register(Agent(name="b", model="echo"))
        assert len(registry.list_all()) == 2
