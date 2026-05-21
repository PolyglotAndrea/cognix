"""Workspace-scoped browser automation runtime.

The service provides the internal capability behind the browser_automation skill:
MCP preset provisioning, isolated browser profiles, approval gating, optional
Playwright execution, and artifact persistence.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cognix.core.policy import WorkspacePolicyService
from cognix.local.approvals import ApprovalStore
from cognix.local.home import CognixHome
from cognix.local.workspace import WorkspaceManager
from cognix.local.workspace_config import MCPServerConfig, WorkspaceConfigStore
from cognix.orchestrator.protocol import OrchestrationEvent, emit_orchestration_event

BrowserEngine = Literal["playwright", "cdp", "browser_use"]


@dataclass(frozen=True)
class BrowserObservation:
    title: str = ""
    url: str = ""
    text: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    screenshot_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrowserAutomationRun:
    objective: str
    url: str
    engine: BrowserEngine = "playwright"
    profile: str = "default"
    selectors: dict[str, str] = field(default_factory=dict)
    extract_text: bool = True
    extract_links: bool = True
    extract_tables: bool = True
    screenshot: bool = False
    wait_for_selector: str = ""
    cdp_endpoint: str = ""
    permission_mode: str = "workspace-write"
    approval_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    plan_id: str = ""
    chat_id: str = ""


class BrowserAutomationService:
    """Internal browser automation capability for a workspace."""

    def __init__(self, workspace_id: str, *, home: CognixHome | None = None) -> None:
        self.home = (home or CognixHome.default()).ensure()
        self.workspace_id = workspace_id
        self.workspace_manager = WorkspaceManager(self.home)
        if not self.workspace_manager.get(workspace_id):
            raise FileNotFoundError(f"Workspace not found: {workspace_id}")
        self.config = WorkspaceConfigStore(workspace_id, home=self.home)

    @property
    def browser_dir(self) -> Path:
        path = self.workspace_manager.workspace_path(self.workspace_id) / "browser"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def profile_dir(self, profile: str = "default") -> Path:
        safe = "".join(ch for ch in profile if ch.isalnum() or ch in ("-", "_")).strip()
        safe = safe or "default"
        path = self.browser_dir / "profiles" / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def screenshot_dir(self) -> Path:
        path = self.browser_dir / "screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def profile_status(self, profile: str = "default") -> dict[str, Any]:
        path = self.profile_dir(profile)
        cookies = list(path.glob("**/Cookies"))
        return {
            "workspace_id": self.workspace_id,
            "profile": path.name,
            "path": str(path),
            "exists": path.exists(),
            "cookie_store_detected": bool(cookies),
            "cookie_store_count": len(cookies),
        }

    def ensure_mcp_preset(
        self,
        *,
        enabled: bool = True,
        profile: str = "default",
    ) -> MCPServerConfig:
        """Create or update the workspace Browser MCP preset."""
        profile_path = self.profile_dir(profile)
        actions = self.runtime_actions()
        mcp_tools = [
            {
                "name": "browser_navigate",
                "description": "Navigate an isolated browser page to a URL.",
                "access_level": "write",
                "canonical_action": "browser.goto",
            },
            {
                "name": "browser_snapshot",
                "description": "Read the current page accessibility snapshot.",
                "access_level": "read",
                "canonical_action": "browser.observe",
            },
            {
                "name": "browser_click",
                "description": "Click an element in the isolated browser page.",
                "access_level": "write",
                "canonical_action": "browser.click",
            },
            {
                "name": "browser_type",
                "description": "Type text into an element in the isolated browser page.",
                "access_level": "write",
                "canonical_action": "browser.fill",
            },
            {
                "name": "browser_select",
                "description": "Select an option in the isolated browser page.",
                "access_level": "write",
                "canonical_action": "browser.select",
            },
            {
                "name": "browser_wait",
                "description": "Wait for a selector, page state, or short delay.",
                "access_level": "read",
                "canonical_action": "browser.wait",
            },
            {
                "name": "browser_download",
                "description": "Download a file produced by the page into the workspace.",
                "access_level": "write",
                "canonical_action": "browser.download",
            },
            {
                "name": "browser_extract_table",
                "description": "Extract structured table data from the current page.",
                "access_level": "read",
                "canonical_action": "browser.extract_table",
            },
            {
                "name": "browser_take_screenshot",
                "description": "Capture a screenshot from the isolated browser page.",
                "access_level": "read",
                "canonical_action": "browser.screenshot",
            },
        ]
        return self.config.upsert_mcp_server(
            server_id="browser_playwright",
            name="browser-playwright",
            command="npx",
            args=[
                "-y",
                "@playwright/mcp@latest",
                "--isolated",
                "--user-data-dir",
                str(profile_path),
            ],
            enabled=enabled,
            metadata={
                "capability": "browser_automation",
                "preset": "playwright-mcp",
                "profile": profile_path.name,
                "profile_path": str(profile_path),
                "access_level": "write",
                "internal": True,
                "engines": ["playwright", "cdp", "browser_use"],
                "tool_access": {tool["name"]: tool["access_level"] for tool in mcp_tools},
                "action_access": {tool["name"]: tool["access_level"] for tool in actions},
                "actions": actions,
                "tools": mcp_tools,
            },
        )

    @staticmethod
    def runtime_actions() -> list[dict[str, str]]:
        """Canonical browser runtime actions exposed to planner/skills.

        These names are stable Cognix contracts. Individual engines may map them
        to Playwright MCP tool names, CDP calls, or browser-use instructions.
        """
        return [
            {
                "name": "browser.goto",
                "description": "Open a URL in the workspace browser profile.",
                "access_level": "write",
            },
            {
                "name": "browser.observe",
                "description": "Read page state, text, accessibility snapshot, links, and tables.",
                "access_level": "read",
            },
            {
                "name": "browser.click",
                "description": "Click a visible element by selector or observed label.",
                "access_level": "write",
            },
            {
                "name": "browser.fill",
                "description": "Fill a text field or editable input.",
                "access_level": "write",
            },
            {
                "name": "browser.select",
                "description": "Select an option from a dropdown or segmented control.",
                "access_level": "write",
            },
            {
                "name": "browser.wait",
                "description": "Wait for navigation, selector, download, or page idle state.",
                "access_level": "read",
            },
            {
                "name": "browser.download",
                "description": "Capture a user-authorized file download into workspace storage.",
                "access_level": "write",
            },
            {
                "name": "browser.extract_table",
                "description": "Extract visible table rows and columns into structured records.",
                "access_level": "read",
            },
            {
                "name": "browser.screenshot",
                "description": "Capture a screenshot for evidence or troubleshooting.",
                "access_level": "read",
            },
        ]

    async def run(
        self,
        request: BrowserAutomationRun,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Run browser automation or return an approval request."""
        approval = await self._approval_or_none(request, user_id=user_id)
        if approval:
            self._emit(
                "approval.requested",
                status="pending",
                run_id=request.plan_id or approval.id,
                approval_id=approval.id,
                data={
                    "tool_name": "browser_automation",
                    "reason": approval.reason,
                    "url": request.url,
                },
            )
            return {
                "status": "approval_required",
                "approval_id": approval.id,
                "reason": approval.reason,
            }

        self._emit(
            "tool_call",
            status="running",
            run_id=request.plan_id or request.task_id or uuid.uuid4().hex[:12],
            task_id=request.task_id,
            agent_id=request.agent_id,
            data={
                "tool": "browser_automation",
                "engine": request.engine,
                "url": request.url,
            },
        )

        try:
            if request.engine == "cdp":
                observation = await self._run_cdp(request)
            elif request.engine == "browser_use":
                observation = await self._run_browser_use(request)
            else:
                observation = await self._run_playwright(request)
        except Exception as exc:
            result = {
                "status": "failed",
                "error": str(exc),
                "recovery": (
                    "Install browser extras and browser binaries, configure a CDP endpoint, "
                    "or switch to another browser automation engine."
                ),
            }
            artifact_id = await self.create_artifact(
                request=request,
                observation=BrowserObservation(title="Browser automation failed", url=request.url),
                result=result,
                user_id=user_id,
                is_error=True,
            )
            result["artifact_id"] = artifact_id
            self._emit(
                "tool_result",
                status="failed",
                run_id=request.plan_id or request.task_id or artifact_id,
                task_id=request.task_id,
                agent_id=request.agent_id,
                artifact_id=artifact_id,
                data=result,
            )
            return result

        result = {
            "status": "completed",
            "observation": observation.to_dict(),
        }
        artifact_id = await self.create_artifact(
            request=request,
            observation=observation,
            result=result,
            user_id=user_id,
        )
        result["artifact_id"] = artifact_id
        self._emit(
            "tool_result",
            status="completed",
            run_id=request.plan_id or request.task_id or artifact_id,
            task_id=request.task_id,
            agent_id=request.agent_id,
            artifact_id=artifact_id,
            data={"artifact_id": artifact_id, "url": observation.url, "title": observation.title},
        )
        return result

    async def create_artifact(
        self,
        *,
        request: BrowserAutomationRun,
        observation: BrowserObservation,
        result: dict[str, Any],
        user_id: str | None = None,
        is_error: bool = False,
    ) -> str:
        """Persist a browser automation result artifact."""
        from cognix.storage.database import get_session
        from cognix.storage.models import ArtifactModel, ArtifactType

        artifact_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC)
        title = (
            f"{request.objective} - browser error"
            if is_error
            else f"{request.objective} - browser result"
        )
        summary = (
            result.get("error", "Browser automation failed.")
            if is_error
            else f"Collected browser observations from {observation.url or request.url}."
        )
        content = self._artifact_content(
            request=request,
            observation=observation,
            summary=summary,
            result=result,
        )
        artifact = ArtifactModel(
            id=artifact_id,
            workspace_id=self.workspace_id,
            task_id=request.task_id or None,
            agent_id=request.agent_id or None,
            artifact_type=ArtifactType.LOG if is_error else ArtifactType.REPORT,
            title=title[:256],
            content=content[:50000],
            source="browser_automation",
            context_type="browser",
            metadata_json={
                "source": "browser_automation",
                "summary": summary,
                "objective": request.objective,
                "url": request.url,
                "engine": request.engine,
                "profile": request.profile,
                "task_id": request.task_id,
                "agent_id": request.agent_id,
                "plan_id": request.plan_id,
                "chat_id": request.chat_id,
                "user_id": user_id or "",
                "is_error": is_error,
                "status": "failure" if is_error else result.get("status", "completed"),
            },
            created_at=now,
            updated_at=now,
        )
        async with get_session() as session:
            session.add(artifact)
        self._emit(
            "artifact.created",
            stage="artifact",
            status="created",
            run_id=request.plan_id or request.task_id or artifact_id,
            task_id=request.task_id,
            agent_id=request.agent_id,
            artifact_id=artifact_id,
            data={"title": artifact.title, "source": artifact.source},
        )
        return artifact_id

    async def _approval_or_none(
        self,
        request: BrowserAutomationRun,
        *,
        user_id: str | None,
    ):
        policy_result = await WorkspacePolicyService(self.workspace_id).check_network_access(
            request.url,
            permission_mode=request.permission_mode,
            user_id=user_id,
            agent_id=request.agent_id or None,
        )
        if policy_result.allowed:
            return None

        if request.approval_id:
            approval = ApprovalStore(self.home).get(request.approval_id)
            if (
                approval
                and approval.status in ("approved", "completed")
                and approval.workspace_id == self.workspace_id
                and approval.tool_name == "browser_automation"
                and approval.arguments.get("url") == request.url
            ):
                return None
            raise PermissionError("Browser automation approval is missing, rejected, or mismatched")

        if policy_result.requires_approval:
            # Fallback: check if we have a recent approved/completed/rejected approval
            # for this URL and workspace.
            recent_approvals = ApprovalStore(self.home).list_all(
                workspace_id=self.workspace_id, include_resolved=True
            )
            matching_approvals = [
                a
                for a in recent_approvals
                if a.tool_name == "browser_automation" and a.arguments.get("url") == request.url
            ]
            if matching_approvals:
                # list_all returns sorted newest first, so matching_approvals[0] is the most recent
                most_recent = matching_approvals[0]
                if most_recent.status in ("approved", "completed"):
                    return None
                elif most_recent.status == "rejected":
                    raise PermissionError(
                        f"Browser automation access to {request.url} "
                        "was rejected in a previous step"
                    )
                elif most_recent.status == "pending":
                    return most_recent

            return ApprovalStore(self.home).create(
                agent_id=request.agent_id or "browser-automation",
                workspace_id=self.workspace_id,
                tool_name="browser_automation",
                arguments={
                    "objective": request.objective,
                    "url": request.url,
                    "engine": request.engine,
                    "profile": request.profile,
                },
                access_level="write",
                reason=policy_result.reason
                or "Browser automation requires approval for network access.",
                metadata={
                    "runtime": "browser_automation",
                    "plan_id": request.plan_id,
                    "chat_id": request.chat_id,
                    "task_id": request.task_id,
                    "approval_type": "browser_automation",
                },
            )
        raise PermissionError(policy_result.reason or "Browser automation denied by policy")

    async def _run_playwright(self, request: BrowserAutomationRun) -> BrowserObservation:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise RuntimeError(
                "Playwright is not installed. Install optional dependency "
                "`cognix[browser]` and run `playwright install chromium`."
            ) from exc

        profile_path = self.profile_dir(request.profile)
        screenshot_path = ""
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=True,
            )
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto(request.url, wait_until="domcontentloaded")
                if request.wait_for_selector:
                    await page.wait_for_selector(request.wait_for_selector, timeout=15000)
                title = await page.title()
                current_url = page.url
                text = await page.locator("body").inner_text(timeout=15000)
                links: list[dict[str, str]] = []
                tables: list[list[list[str]]] = []
                if request.extract_links:
                    links = await page.locator("a").evaluate_all(
                        "(nodes) => nodes.slice(0, 100).map((a) => "
                        "({ text: (a.innerText || '').trim(), href: a.href || '' }))"
                    )
                if request.extract_tables:
                    tables = await page.locator("table").evaluate_all(
                        "(tables) => tables.slice(0, 20).map((table) => "
                        "Array.from(table.rows).map((row) => "
                        "Array.from(row.cells).map((cell) => (cell.innerText || '').trim())))"
                    )
                if request.screenshot:
                    screenshot = self.screenshot_dir() / f"{uuid.uuid4().hex[:12]}.png"
                    await page.screenshot(path=str(screenshot), full_page=True)
                    screenshot_path = str(screenshot)
                return BrowserObservation(
                    title=title,
                    url=current_url,
                    text=text[:20000] if request.extract_text else "",
                    links=links,
                    tables=tables,
                    screenshot_path=screenshot_path,
                )
            finally:
                await context.close()

    async def _run_cdp(self, request: BrowserAutomationRun) -> BrowserObservation:
        """Connect to an already-running Chromium instance over CDP."""
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise RuntimeError(
                "Playwright is required for CDP browser automation. Install optional "
                "dependency `cognix[browser]`."
            ) from exc

        endpoint = (
            request.cdp_endpoint
            or self.config.get_settings().get("browser", {}).get("cdp_endpoint")
            or ""
        )
        if not endpoint:
            raise RuntimeError(
                "CDP endpoint is not configured. Start Chrome with remote debugging, for "
                "example `--remote-debugging-port=9222`, then set browser.cdp_endpoint "
                "to `http://127.0.0.1:9222`."
            )

        screenshot_path = ""
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(endpoint)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto(request.url, wait_until="domcontentloaded")
                if request.wait_for_selector:
                    await page.wait_for_selector(request.wait_for_selector, timeout=15000)
                title = await page.title()
                current_url = page.url
                text = await page.locator("body").inner_text(timeout=15000)
                links: list[dict[str, str]] = []
                tables: list[list[list[str]]] = []
                if request.extract_links:
                    links = await page.locator("a").evaluate_all(
                        "(nodes) => nodes.slice(0, 100).map((a) => "
                        "({ text: (a.innerText || '').trim(), href: a.href || '' }))"
                    )
                if request.extract_tables:
                    tables = await page.locator("table").evaluate_all(
                        "(tables) => tables.slice(0, 20).map((table) => "
                        "Array.from(table.rows).map((row) => "
                        "Array.from(row.cells).map((cell) => (cell.innerText || '').trim())))"
                    )
                if request.screenshot:
                    screenshot = self.screenshot_dir() / f"{uuid.uuid4().hex[:12]}.png"
                    await page.screenshot(path=str(screenshot), full_page=True)
                    screenshot_path = str(screenshot)
                return BrowserObservation(
                    title=title,
                    url=current_url,
                    text=text[:20000] if request.extract_text else "",
                    links=links,
                    tables=tables,
                    screenshot_path=screenshot_path,
                )
            finally:
                await browser.close()

    async def _run_browser_use(self, request: BrowserAutomationRun) -> BrowserObservation:
        """Run browser-use for high-level browser tasks when its runtime is installed."""
        try:
            from browser_use import Agent as BrowserUseAgent
            from browser_use import Browser, BrowserConfig
            from langchain_openai import ChatOpenAI
        except Exception as exc:
            raise RuntimeError(
                "browser-use runtime is not fully installed. Install optional browser-use "
                "dependencies plus a LangChain-compatible LLM provider, or use playwright/cdp."
            ) from exc

        from cognix.providers.resolver import resolve_provider

        provider = resolve_provider(self.workspace_id)
        if not provider.api_key:
            raise RuntimeError("browser-use requires a configured model provider API key.")

        llm_kwargs: dict[str, Any] = {
            "model": provider.default_model,
            "api_key": provider.api_key,
        }
        if provider.base_url:
            llm_kwargs["base_url"] = provider.base_url
        llm = ChatOpenAI(**llm_kwargs)
        browser = Browser(
            config=BrowserConfig(
                headless=True,
                user_data_dir=str(self.profile_dir(request.profile)),
            )
        )
        task = f"{request.objective}\n\nTarget URL: {request.url}"
        agent = BrowserUseAgent(task=task, llm=llm, browser=browser)
        try:
            history = await agent.run()
        finally:
            close = getattr(browser, "close", None)
            if close:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        return BrowserObservation(
            title="browser-use run",
            url=request.url,
            text=str(history)[:20000],
        )

    def _artifact_content(
        self,
        *,
        request: BrowserAutomationRun,
        observation: BrowserObservation,
        summary: str,
        result: dict[str, Any],
    ) -> str:
        links = "\n".join(
            f"- [{item.get('text') or item.get('href')}]({item.get('href')})"
            for item in observation.links[:30]
            if item.get("href")
        )
        table_summary = f"{len(observation.tables)} table(s) extracted."
        extracted_text = observation.text or result.get("message") or result.get("error", "")
        return (
            f"# {request.objective}\n\n"
            f"## Summary\n{summary}\n\n"
            f"## Source\n- URL: {observation.url or request.url}\n"
            f"- Engine: {request.engine}\n"
            f"- Profile: {request.profile}\n\n"
            f"## Extracted Text\n{extracted_text}\n\n"
            f"## Links\n{links or 'No links extracted.'}\n\n"
            f"## Tables\n{table_summary}\n\n"
            f"## Screenshot\n{observation.screenshot_path or 'No screenshot captured.'}\n\n"
            f"## Provenance\n"
            f"- Source: browser_automation\n"
            f"- Task ID: {request.task_id}\n"
            f"- Agent ID: {request.agent_id}\n"
            f"- Plan ID: {request.plan_id}\n"
        )

    def _emit(
        self,
        event_type: str,
        *,
        status: str = "",
        stage: str = "",
        run_id: str = "",
        task_id: str = "",
        agent_id: str = "",
        approval_id: str = "",
        artifact_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        emit_orchestration_event(
            OrchestrationEvent(
                workspace_id=self.workspace_id,
                type=event_type,
                stage=stage,
                status=status,
                run_id=run_id or uuid.uuid4().hex[:12],
                task_id=task_id,
                agent_id=agent_id,
                approval_id=approval_id,
                artifact_id=artifact_id,
                data=data or {},
            )
        )
