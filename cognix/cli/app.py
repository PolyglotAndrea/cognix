"""CLI entry point using Typer."""

from __future__ import annotations

import typer
from rich.console import Console

from cognix import __version__

app = typer.Typer(
    name="cognix",
    help="Hermes Agent-based multi-agent collaboration platform",
    no_args_is_help=True,
)
console = Console()

# Sub-command groups
agent_app = typer.Typer(help="Manage agents", no_args_is_help=True)
task_app = typer.Typer(help="Manage scheduled tasks", no_args_is_help=True)
skill_app = typer.Typer(help="Manage skills", no_args_is_help=True)
workflow_app = typer.Typer(help="Manage workflows", no_args_is_help=True)
rpc_app = typer.Typer(help="JSON-RPC operations", no_args_is_help=True)
server_app = typer.Typer(help="Server management", no_args_is_help=True)

app.add_typer(agent_app, name="agent")
app.add_typer(task_app, name="task")
app.add_typer(skill_app, name="skill")
app.add_typer(workflow_app, name="workflow")
app.add_typer(rpc_app, name="rpc")
app.add_typer(server_app, name="server")


@app.command()
def version() -> None:
    """Show Cognix version."""
    console.print(f"cognix v{__version__}")


@app.command()
def init(
    directory: str = typer.Argument(".", help="Project directory"),
) -> None:
    """Initialize a new Cognix project."""
    import json
    from pathlib import Path

    project_dir = Path(directory)
    project_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "name": project_dir.name,
        "version": "0.1.0",
        "agents": [],
        "skills": [],
        "workflows": [],
    }
    config_path = project_dir / "cognix.json"
    if config_path.exists():
        console.print("[yellow]cognix.json already exists, skipping[/yellow]")
    else:
        config_path.write_text(json.dumps(config, indent=2))
        console.print(f"[green]Initialized project at {project_dir}[/green]")

    # Create subdirectories
    for subdir in ["agents", "skills", "workflows"]:
        (project_dir / subdir).mkdir(exist_ok=True)

    console.print("[green]Done![/green]")


# ── Agent commands ──────────────────────────────────────────────────


def _run_async(coro):
    """Run an async function from sync CLI context."""
    import asyncio

    return asyncio.run(coro)


@agent_app.command("create")
def agent_create(
    name: str = typer.Option(..., help="Agent name"),
    model: str = typer.Option("gpt-4o", help="LLM model"),
    system_prompt: str = typer.Option("You are a helpful assistant.", help="System prompt"),
    description: str = typer.Option("", help="Agent description"),
    api_base: str = typer.Option(None, help="Custom API base URL"),
) -> None:
    """Create a new agent."""

    async def _create():
        from cognix.core.agent import Agent
        from cognix.storage.database import get_session, init_db
        from cognix.storage.models import AgentModel

        await init_db()
        agent = Agent(
            name=name,
            model=model,
            system_prompt=system_prompt,
            description=description,
            api_base=api_base,
        )
        async with get_session() as session:
            db_agent = AgentModel(
                id=agent.id,
                name=agent.name,
                description=agent.description,
                model=agent.model,
                system_prompt=agent.system_prompt,
                temperature=agent.temperature,
                max_iterations=agent.max_iterations,
                api_base=api_base,
            )
            session.add(db_agent)

        console.print(f"[green]Agent '{name}' created[/green]")
        console.print(f"  ID:    {agent.id}")
        console.print(f"  Model: {model}")
        if api_base:
            console.print(f"  API:   {api_base}")

    _run_async(_create())


@agent_app.command("list")
def agent_list() -> None:
    """List all agents."""
    from rich.table import Table

    async def _list():
        from sqlalchemy import select

        from cognix.storage.database import get_session, init_db
        from cognix.storage.models import AgentModel

        await init_db()
        async with get_session() as session:
            result = await session.execute(select(AgentModel))
            agents = result.scalars().all()

        if not agents:
            console.print("[dim]No agents configured yet.[/dim]")
            return

        table = Table(title="Agents")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Model")
        table.add_column("Description")
        table.add_column("Created", style="dim")

        for a in agents:
            table.add_row(a.id, a.name, a.model, a.description or "-", str(a.created_at)[:19])

        console.print(table)

    _run_async(_list())


@agent_app.command("chat")
def agent_chat(
    name: str = typer.Argument(..., help="Agent name or ID"),
    message: str = typer.Argument(..., help="Message to send"),
) -> None:
    """Send a message to an agent."""

    async def _chat():
        from sqlalchemy import or_, select

        from cognix.core.agent import Agent
        from cognix.core.memory import SQLiteBackend
        from cognix.storage.database import get_session, init_db
        from cognix.storage.models import AgentModel

        await init_db()
        async with get_session() as session:
            result = await session.execute(
                select(AgentModel).where(
                    or_(AgentModel.name == name, AgentModel.id == name)
                )
            )
            db_agent = result.scalar_one_or_none()

        if not db_agent:
            console.print(f"[red]Agent '{name}' not found[/red]")
            raise typer.Exit(1)

        agent = Agent(
            id=db_agent.id,
            name=db_agent.name,
            model=db_agent.model,
            system_prompt=db_agent.system_prompt,
            temperature=db_agent.temperature,
            max_iterations=db_agent.max_iterations,
            memory=SQLiteBackend(agent_id=db_agent.id),
        )

        with console.status("[bold blue]Thinking..."):
            response = await agent.run(message)

        console.print(f"[bold green]{agent.name}:[/bold green] {response.content}")

    _run_async(_chat())


@agent_app.command("repl")
def agent_repl(
    name: str = typer.Argument(..., help="Agent name or ID"),
) -> None:
    """Start an interactive REPL with an agent."""

    async def _repl():
        from sqlalchemy import or_, select

        from cognix.core.agent import Agent
        from cognix.core.context import Context
        from cognix.core.memory import SQLiteBackend
        from cognix.storage.database import get_session, init_db
        from cognix.storage.models import AgentModel

        await init_db()
        async with get_session() as session:
            result = await session.execute(
                select(AgentModel).where(
                    or_(AgentModel.name == name, AgentModel.id == name)
                )
            )
            db_agent = result.scalar_one_or_none()

        if not db_agent:
            console.print(f"[red]Agent '{name}' not found[/red]")
            raise typer.Exit(1)

        agent = Agent(
            id=db_agent.id,
            name=db_agent.name,
            model=db_agent.model,
            system_prompt=db_agent.system_prompt,
            temperature=db_agent.temperature,
            max_iterations=db_agent.max_iterations,
            memory=SQLiteBackend(agent_id=db_agent.id),
        )

        ctx = Context()
        console.print(f"[bold green]Chatting with {agent.name}[/bold green]")
        console.print("[dim]Type 'quit' or 'exit' to end the conversation[/dim]")
        console.print()

        while True:
            try:
                user_input = input(f"[{agent.name}] You: ")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if user_input.strip().lower() in ("quit", "exit"):
                console.print("[dim]Goodbye![/dim]")
                break

            if not user_input.strip():
                continue

            with console.status("[bold blue]Thinking..."):
                response = await agent.run(user_input, context=ctx)

            console.print(f"[bold green]{agent.name}:[/bold green] {response.content}")
            console.print()

    _run_async(_repl())


@agent_app.command("delete")
def agent_delete(
    name: str = typer.Argument(..., help="Agent name or ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete an agent."""

    async def _delete():
        from sqlalchemy import delete, or_, select

        from cognix.storage.database import get_session, init_db
        from cognix.storage.models import AgentModel

        await init_db()
        async with get_session() as session:
            result = await session.execute(
                select(AgentModel).where(
                    or_(AgentModel.name == name, AgentModel.id == name)
                )
            )
            db_agent = result.scalar_one_or_none()

            if not db_agent:
                console.print(f"[red]Agent '{name}' not found[/red]")
                raise typer.Exit(1)

            if not force:
                typer.confirm(f"Delete agent '{db_agent.name}' ({db_agent.id})?", abort=True)

            await session.execute(delete(AgentModel).where(AgentModel.id == db_agent.id))

        console.print(f"[red]Agent '{db_agent.name}' deleted[/red]")

    _run_async(_delete())


# ── Task commands ───────────────────────────────────────────────────

@task_app.command("add")
def task_add(
    name: str = typer.Option(..., help="Task name"),
    cron: str = typer.Option(..., help="Cron expression"),
    task_type: str = typer.Option(
        "agent_call",
        help="Task type: agent_call, rpc_call, http_webhook, workflow",
    ),
    agent: str = typer.Option(None, help="Agent ID (for agent_call type)"),
    message: str = typer.Option("", help="Message for agent"),
    url: str = typer.Option(None, help="URL (for http_webhook type)"),
    workflow_path: str = typer.Option(None, help="Workflow path (for workflow type)"),
) -> None:
    """Add a scheduled task."""
    import uuid

    async def _add():
        from cognix.scheduler.store import TaskStore
        from cognix.storage.database import init_db
        from cognix.storage.models import TaskType as DBTaskType

        await init_db()
        task_id = uuid.uuid4().hex[:12]
        store = TaskStore()

        # Build payload based on task type
        payload = {"task_type": task_type}
        if task_type == "agent_call":
            if not agent:
                console.print("[red]--agent required for agent_call type[/red]")
                raise typer.Exit(1)
            payload["agent_id"] = agent
            payload["message"] = message
        elif task_type == "http_webhook":
            if not url:
                console.print("[red]--url required for http_webhook type[/red]")
                raise typer.Exit(1)
            payload["url"] = url
        elif task_type == "workflow":
            if not workflow_path:
                console.print("[red]--workflow-path required for workflow type[/red]")
                raise typer.Exit(1)
            payload["workflow_path"] = workflow_path

        db_task_type = DBTaskType(task_type)
        await store.create(
            task_id=task_id,
            name=name,
            task_type=db_task_type,
            schedule=cron,
            payload=payload,
        )

        console.print(f"[green]Task '{name}' created[/green]")
        console.print(f"  ID:       {task_id}")
        console.print(f"  Schedule: {cron}")
        console.print(f"  Type:     {task_type}")

    _run_async(_add())


@task_app.command("list")
def task_list() -> None:
    """List scheduled tasks."""
    from rich.table import Table

    async def _list():
        from cognix.scheduler.store import TaskStore
        from cognix.storage.database import init_db

        await init_db()
        store = TaskStore()
        tasks = await store.list_all()

        if not tasks:
            console.print("[dim]No tasks scheduled yet.[/dim]")
            return

        table = Table(title="Scheduled Tasks")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type")
        table.add_column("Schedule")
        table.add_column("State")
        table.add_column("Runs")

        for t in tasks:
            state_color = "green" if t.state.value == "active" else "yellow"
            table.add_row(
                t.id,
                t.name,
                t.task_type.value,
                t.schedule,
                f"[{state_color}]{t.state.value}[/{state_color}]",
                str(t.run_count),
            )

        console.print(table)

    _run_async(_list())


@task_app.command("pause")
def task_pause(task_id: str = typer.Argument(..., help="Task ID")) -> None:
    """Pause a scheduled task."""

    async def _pause():
        from cognix.scheduler.store import TaskStore
        from cognix.storage.database import init_db

        await init_db()
        store = TaskStore()
        if await store.update_state(task_id, "paused"):
            console.print(f"[yellow]Task '{task_id}' paused[/yellow]")
        else:
            console.print(f"[red]Task '{task_id}' not found[/red]")
            raise typer.Exit(1)

    _run_async(_pause())


@task_app.command("resume")
def task_resume(task_id: str = typer.Argument(..., help="Task ID")) -> None:
    """Resume a paused task."""

    async def _resume():
        from cognix.scheduler.store import TaskStore
        from cognix.storage.database import init_db

        await init_db()
        store = TaskStore()
        if await store.update_state(task_id, "active"):
            console.print(f"[green]Task '{task_id}' resumed[/green]")
        else:
            console.print(f"[red]Task '{task_id}' not found[/red]")
            raise typer.Exit(1)

    _run_async(_resume())


@task_app.command("trigger")
def task_trigger(task_id: str = typer.Argument(..., help="Task ID")) -> None:
    """Immediately trigger a task."""

    async def _trigger():
        import json

        from cognix.core.registry import AgentRegistry
        from cognix.scheduler.executor import TaskExecutor
        from cognix.scheduler.store import TaskStore
        from cognix.storage.database import init_db
        from cognix.storage.models import AgentModel

        await init_db()
        store = TaskStore()
        task = await store.get(task_id)
        if not task:
            console.print(f"[red]Task '{task_id}' not found[/red]")
            raise typer.Exit(1)

        # Load agents
        registry = AgentRegistry()
        from sqlalchemy import select

        from cognix.core.agent import Agent
        from cognix.storage.database import get_session

        async with get_session() as session:
            result = await session.execute(select(AgentModel))
            for row in result.scalars():
                agent = Agent(
                    id=row.id,
                    name=row.name,
                    model=row.model,
                    system_prompt=row.system_prompt,
                )
                registry.register(agent)

        executor = TaskExecutor(agent_registry=registry)
        payload = json.loads(task.payload) if isinstance(task.payload, str) else task.payload

        with console.status("[bold blue]Executing..."):
            result = await executor.execute(task_id, payload)

        status = result.get("status", "unknown")
        color = "green" if status == "success" else "red"
        console.print(f"[{color}]Task '{task_id}' executed: {status}[/{color}]")

        if result.get("result"):
            console.print(f"Result: {result['result'][:200]}")
        if result.get("error"):
            console.print(f"[red]Error: {result['error']}[/red]")

    _run_async(_trigger())


@task_app.command("logs")
def task_logs(
    task_id: str = typer.Argument(..., help="Task ID"),
    limit: int = typer.Option(20, help="Number of entries"),
) -> None:
    """View task execution logs."""
    from rich.table import Table

    async def _logs():
        from cognix.scheduler.store import TaskStore
        from cognix.storage.database import init_db

        await init_db()
        store = TaskStore()
        runs = await store.get_runs(task_id, limit=limit)

        if not runs:
            console.print(f"[dim]No logs for task '{task_id}'[/dim]")
            return

        table = Table(title=f"Task Logs: {task_id}")
        table.add_column("ID")
        table.add_column("Status")
        table.add_column("Duration")
        table.add_column("Started")
        table.add_column("Result/Error")

        for r in runs:
            status_color = "green" if r.status == "success" else "red"
            result_text = r.result[:50] if r.status == "success" else r.error[:50]
            table.add_row(
                str(r.id),
                f"[{status_color}]{r.status}[/{status_color}]",
                f"{r.duration_ms}ms",
                str(r.started_at)[:19] if r.started_at else "-",
                result_text or "-",
            )

        console.print(table)

    _run_async(_logs())


# ── Skill commands ──────────────────────────────────────────────────

@skill_app.command("list")
def skill_list(
    directory: str = typer.Option(None, help="Skills directory"),
) -> None:
    """List installed skills."""
    from rich.table import Table

    from cognix.skills.manager import SkillsManager

    manager = SkillsManager(local_dir=directory) if directory else SkillsManager()
    skills = manager.list_installed()

    if not skills:
        console.print("[dim]No skills installed yet.[/dim]")
        return

    table = Table(title="Installed Skills")
    table.add_column("Name", style="green")
    table.add_column("Version")
    table.add_column("Description")
    table.add_column("Author")
    table.add_column("Tools")

    for s in skills:
        table.add_row(
            s["name"],
            s["version"],
            s["description"] or "-",
            s["author"] or "-",
            ", ".join(s["tools"]) or "-",
        )

    console.print(table)


@skill_app.command("search")
def skill_search(
    query: str = typer.Argument(..., help="Search query"),
    directory: str = typer.Option(None, help="Skills directory"),
) -> None:
    """Search installed skills."""
    from cognix.skills.manager import SkillsManager

    manager = SkillsManager(local_dir=directory) if directory else SkillsManager()
    skills = manager.list_installed()

    results = [
        s for s in skills
        if query.lower() in s["name"].lower()
        or query.lower() in s["description"].lower()
        or any(query.lower() in t for t in s["tags"])
    ]

    if not results:
        console.print(f"[dim]No skills matching '{query}'[/dim]")
        return

    for s in results:
        console.print(f"[green]{s['name']}[/green] v{s['version']}")
        console.print(f"  {s['description']}")
        console.print(f"  Tools: {', '.join(s['tools'])}")
        console.print()


@skill_app.command("install")
def skill_install(
    source: str = typer.Argument(..., help="Skill directory path"),
    name: str = typer.Option(None, help="Override skill name"),
) -> None:
    """Install a skill from a local directory."""
    from pathlib import Path

    from cognix.skills.manager import SkillsManager

    source_path = Path(source)
    if not source_path.exists():
        console.print(f"[red]Source directory not found: {source}[/red]")
        raise typer.Exit(1)

    manager = SkillsManager()
    try:
        skill = manager.install(source_path, name=name)
        console.print(f"[green]Skill '{skill.name}' v{skill.version} installed[/green]")
    except Exception as e:
        console.print(f"[red]Failed to install skill: {e}[/red]")
        raise typer.Exit(1)


@skill_app.command("uninstall")
def skill_uninstall(name: str = typer.Argument(..., help="Skill name")) -> None:
    """Uninstall a skill."""
    from cognix.skills.manager import SkillsManager

    manager = SkillsManager()
    if manager.uninstall(name):
        console.print(f"[red]Skill '{name}' uninstalled[/red]")
    else:
        console.print(f"[red]Skill '{name}' not found[/red]")
        raise typer.Exit(1)


@skill_app.command("create")
def skill_create(
    name: str = typer.Argument(..., help="Skill name"),
    directory: str = typer.Option("./skills", help="Output directory"),
) -> None:
    """Create a new skill from scaffold."""
    from pathlib import Path

    skill_dir = Path(directory) / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    # skill.yaml
    (skill_dir / "skill.yaml").write_text(
        f"name: {name}\n"
        f"version: 0.1.0\n"
        f"description: TODO: describe {name}\n"
        f"author: you\n"
        f"tags: []\n"
        f"\n"
        f"runtime:\n"
        f"  python: '>=3.11'\n"
        f"  entrypoint: handler.py\n"
        f"\n"
        f"tools:\n"
        f"  - name: {name}\n"
        f"    description: TODO\n"
        f"    parameters:\n"
        f"      type: object\n"
        f"      properties: {{}}\n"
        f"      required: []\n"
    )

    # handler.py
    (skill_dir / "handler.py").write_text(
        '"""Skill handler."""\n'
        "\n"
        "async def run(**params) -> str:\n"
        '    """Entry point for the skill."""\n'
        f'    return "Hello from {name}"\n'
    )

    console.print(f"[green]Skill scaffold created at {skill_dir}[/green]")


# ── Workflow commands ───────────────────────────────────────────────

@workflow_app.command("run")
def workflow_run(
    file: str = typer.Argument(..., help="Workflow YAML file"),
    input_data: str = typer.Option("", help="Input text"),
) -> None:
    """Run a workflow from YAML file."""

    async def _run():
        from cognix.core.registry import AgentRegistry
        from cognix.orchestrator.workflow import execute_workflow, parse_workflow
        from cognix.storage.database import init_db
        from cognix.storage.models import AgentModel

        await init_db()

        # Load agents from DB into registry
        from sqlalchemy import select

        from cognix.core.agent import Agent
        from cognix.storage.database import get_session

        registry = AgentRegistry()
        async with get_session() as session:
            result = await session.execute(select(AgentModel))
            for row in result.scalars():
                agent = Agent(
                    id=row.id,
                    name=row.name,
                    model=row.model,
                    system_prompt=row.system_prompt,
                )
                registry.register(agent)

        try:
            workflow = parse_workflow(file)
        except Exception as e:
            console.print(f"[red]Failed to parse workflow: {e}[/red]")
            raise typer.Exit(1)

        console.print(f"[blue]Running workflow: {workflow.name}[/blue]")
        console.print(f"[dim]{workflow.description}[/dim]")
        console.print()

        with console.status("[bold blue]Executing..."):
            result = await execute_workflow(workflow, registry, initial_input=input_data)

        # Show results
        for step in result.steps:
            status = step.get("status", "unknown")
            color = "green" if status == "success" else "red" if status == "error" else "yellow"
            console.print(f"  [{color}]{step['step']}[/{color}]: {status}")

        console.print()
        console.print(f"[bold green]Result:[/bold green] {result.content[:200]}")

    _run_async(_run())


@workflow_app.command("list")
def workflow_list(
    directory: str = typer.Option("./workflows", help="Workflows directory"),
) -> None:
    """List available workflows."""
    from pathlib import Path

    from rich.table import Table

    from cognix.orchestrator.workflow import parse_workflow

    workflows_dir = Path(directory)
    if not workflows_dir.exists():
        console.print(f"[dim]No workflows directory found at {directory}[/dim]")
        return

    yaml_files = list(workflows_dir.glob("*.yaml")) + list(workflows_dir.glob("*.yml"))
    if not yaml_files:
        console.print("[dim]No workflow files found.[/dim]")
        return

    table = Table(title="Workflows")
    table.add_column("File", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Description")
    table.add_column("Steps")

    for f in sorted(yaml_files):
        try:
            wf = parse_workflow(f)
            table.add_row(f.name, wf.name, wf.description or "-", str(len(wf.steps)))
        except Exception as e:
            table.add_row(f.name, "[red]error[/red]", str(e), "-")

    console.print(table)


@workflow_app.command("validate")
def workflow_validate(file: str = typer.Argument(..., help="Workflow YAML file")) -> None:
    """Validate a workflow YAML file."""
    from pathlib import Path

    from cognix.orchestrator.workflow import validate_workflow

    path = Path(file)
    if not path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    errors = validate_workflow(file)
    if errors:
        console.print(f"[red]Validation failed for '{file}':[/red]")
        for err in errors:
            console.print(f"  - {err}")
        raise typer.Exit(1)
    else:
        console.print(f"[green]Workflow '{file}' is valid[/green]")


# ── RPC commands ────────────────────────────────────────────────────

@rpc_app.command("call")
def rpc_call(
    method: str = typer.Argument(..., help="RPC method name"),
    params: str = typer.Option("{}", help="JSON params"),
    endpoint: str = typer.Option("http://localhost:8001/rpc", help="RPC endpoint"),
) -> None:
    """Call a JSON-RPC method."""
    import json

    import httpx

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": json.loads(params),
        "id": 1,
    }
    try:
        resp = httpx.post(endpoint, json=payload, timeout=30)
        console.print_json(resp.text)
    except Exception as e:
        console.print(f"[red]RPC call failed: {e}[/red]")
        raise typer.Exit(1)


@rpc_app.command("serve")
def rpc_serve(
    port: int = typer.Option(8001, help="Port"),
    host: str = typer.Option("0.0.0.0", help="Host"),
) -> None:
    """Start JSON-RPC server."""
    console.print(f"[blue]Starting RPC server on {host}:{port}[/blue]")


# ── Server commands ─────────────────────────────────────────────────

@server_app.command("start")
def server_start(
    port: int = typer.Option(8000, help="Port"),
    host: str = typer.Option("0.0.0.0", help="Host"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on changes"),
) -> None:
    """Start the API server."""
    import uvicorn

    uvicorn.run(
        "cognix.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@server_app.command("config")
def server_config() -> None:
    """Show current configuration."""
    from cognix.config import get_settings

    settings = get_settings()
    console.print(f"Debug:       {settings.debug}")
    console.print(f"Log Level:   {settings.log_level}")
    console.print(f"Data Dir:    {settings.data_dir}")
    console.print(f"Database:    {settings.database.url}")
    console.print(f"Default LLM: {settings.default_model}")
    console.print(f"Server:      {settings.server.host}:{settings.server.port}")
    console.print(f"RPC:         {settings.rpc.transport}://{settings.rpc.host}:{settings.rpc.port}")
    console.print(f"Skills Dir:  {settings.skills.local_dir}")
    console.print(f"Registry:    {settings.skills.registry_url}")


if __name__ == "__main__":
    app()
