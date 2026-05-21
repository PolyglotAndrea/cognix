# Cognix Agentic Product Direction

This document defines the target product path for Cognix after the notebook-style
UI migration. It is based on the current codebase capability check and is meant
to guide implementation sequencing.

## 1. Target User Flow

The default product flow should be:

```mermaid
flowchart TD
    A["User describes intent"] --> B["Intent confirmation"]
    B --> C["Capability and context resolution"]
    C --> D["Missing information collection"]
    D --> E["Plan proposal"]
    E --> F["User approval"]
    F --> G["Execution"]
    G --> H["Events and progress"]
    H --> I["Artifact output"]
    I --> J["Promote artifact to source"]
    I --> K["Promote plan to long task"]
    I --> L["Promote workflow to playbook or skill"]
    J --> C
    K --> H
    L --> C
```

The user should not need to understand agents, MCP, skills, scheduler, memory,
or sandbox details. These are internal capability choices.

User-facing concepts:

- **Conversation**: the only primary entry point.
- **Sources**: selected context used by the run.
- **Tasks**: confirmed recurring or long-running jobs.
- **Studio / Outputs**: reports, datasets, browser captures, code apps, files,
  playbooks, and reusable outputs.
- **Needs Input**: typed forms or approval buttons when the run is blocked.

Advanced concepts such as raw agents, runtime nodes, policy logs, MCP servers,
and raw task payloads should stay under developer details.

## 2. Current Support Matrix

| Capability | Current support | Code references | Gap |
|---|---:|---|---|
| Intent to plan | Partial | `cognix/planner/service.py` | Planner mixes intent confirmation, missing input, plan generation, and execution preparation. |
| Capability resolver | Partial | `cognix/planner/capabilities.py` | Resolver exposes skills, MCP, connectors, browser, sandbox, memory, but ranking and policy-aware capability selection are still shallow. |
| Human-in-loop | Partial | `cognix/local/approvals.py`, `cognix/planner/service.py`, `web/src/features/workspace/SimpleMode.tsx` | Lacks durable typed question schemas, answer suggestions from memory, and clean re-entry after every state transition. |
| Browser automation | Partial | `cognix/browser/service.py`, `docs/architecture/browser-automation-layering.md` | Runtime supports Playwright, CDP, and browser-use contracts, but optional dependencies, profile management, action-level execution, and UI recovery are not product-complete. |
| Plan to one-shot task | Supported | `PlannerService._apply_create_task`, `TaskExecutor` | Needs better status model and user-facing progress. |
| Plan to scheduled task | Partial | `SchedulerEngine`, `TaskStore`, `ScheduledTaskModel` | Scheduler can run cron/interval, but there is no first-class "promote this successful plan to recurring task" product flow. |
| Browser task scheduling | Partial | `PlannerService._apply_browser_run`, `TaskType.BROWSER_AUTOMATION` | Can create scheduled browser tasks, but the UI does not present recurring browser runs as a safe confirmed task template. |
| Artifact output | Supported | `ArtifactModel`, `cognix/api/routes/artifacts.py` | Artifact exists, but artifact-to-source is not yet a first-class backend contract. |
| Artifact to playbook/skill | Partial | `cognix/api/routes/playbooks.py`, `PlaybookModel` | Extraction and promotion exist, but need review gates, validation, and marketplace/local hub UX. |
| Artifact to source | Partial | `SourcesPanel.tsx` source model supports `artifact`, but current source list mainly includes memory, URLs, files, and scheduled tasks. | Need backend source registry and source lineage. |
| Code output and preview | Partial | `cognix/local/code_sandbox.py`, workspace code-project routes | Can create and start projects, but isolation is process-level, not a hardened sandbox. Needs policy, dependency install strategy, logs, previews, and cleanup. |
| Multi-agent orchestration | Supported at runtime layer | `cognix/orchestrator/*`, Hermes Agent runtime | Planner does not yet consistently map complex user goals into agent teams and task DAGs. |
| MCP and skills | Partial to supported | `cognix/mcp/*`, `cognix/skills/*`, workspace routes | Tool discovery and workspace config exist. Product should hide raw config and expose capability presets. |
| Memory and RAG | Partial | `cognix/core/memory.py`, `CapabilityResolver.memory` | Needs MemoryRouter, context budget, source attribution, memory write approval, and answer suggestion for repeated HITL questions. |
| Multi-language | Missing | no frontend i18n framework detected | Need locale detection, user/workspace language settings, backend localized prompts, and translated UI strings. |

## 3. Product State Machine

The center conversation should be driven by a durable run state. Recommended
states:

| State | Meaning | User sees |
|---|---|---|
| `intent_received` | Raw user request captured. | User message. |
| `intent_confirming` | System summarizes what it thinks the user wants. | "I understand you want..." with confirm/edit buttons. |
| `collecting_context` | Sources, memory, skills, MCP, browser, scheduler, and sandbox are resolved. | Short status, not raw technical details. |
| `needs_input` | Missing required information or approval. | Typed form or explicit approve/reject buttons. |
| `plan_proposed` | System has a concrete approach. | Human-readable plan, outputs, risk, cost, schedule. |
| `approved` | User approved execution. | Run begins. |
| `running` | Execution active. | Timeline with steps and events. |
| `blocked` | Execution cannot continue without user action or configuration. | Recovery card with specific next step. |
| `completed` | Outputs produced. | Artifact cards and suggested follow-ups. |
| `failed` | Run ended with unrecovered error. | Error summary and retry path. |
| `promoted_to_task` | Plan converted into long-running or scheduled job. | Task appears in left Tasks tab. |
| `promoted_to_source` | Artifact can be reused as context. | Source appears in left Sources tab. |

This state should be persisted independently of chat messages so refresh and
session switching can re-enter the exact run state.

## 4. Plan to Long Task

The product should support converting a successful or reviewed plan into a
long-running or scheduled task.

Recommended API:

```http
POST /api/v1/workspaces/{workspace_id}/plans/{plan_id}/promote-task
```

Request shape:

```json
{
  "name": "Daily coupon code export",
  "schedule": "every 24h",
  "timezone": "Asia/Shanghai",
  "source_policy": {
    "reuse_selected_sources": true,
    "include_memory": true,
    "include_latest_artifacts": false
  },
  "execution_policy": {
    "require_approval_before_external_access": true,
    "require_approval_before_file_write": false,
    "max_runtime_seconds": 1800
  },
  "output_policy": {
    "artifact_type": "report",
    "publish": false,
    "notify_on_completion": true
  }
}
```

Implementation notes:

- Store a normalized plan snapshot, not only the original prompt.
- Persist selected capabilities and source references.
- Store `user_id`, `workspace_id`, provider route, policy mode, timezone, and
  approval rules in the task payload.
- Scheduled execution should create new artifacts per run and link them to the
  task and originating plan.
- The UI should only show tasks after the user confirms promotion. Draft plans
  should stay in the conversation, not in the Tasks tab.

Current code already supports scheduled task primitives through
`ScheduledTaskModel`, `TaskStore`, `SchedulerEngine`, and `TaskExecutor`. The
missing piece is the product-level promotion contract and UI.

## 5. Artifact to Source

Outputs should be reusable context. This is important for a notebook-like product
because every useful result can become future input.

Recommended API:

```http
POST /api/v1/workspaces/{workspace_id}/artifacts/{artifact_id}/promote-source
```

Source shape:

```json
{
  "id": "artifact:abc123:v1",
  "kind": "artifact",
  "title": "Coupon export report",
  "summary": "Extracted yesterday's coupon data from LinKe.",
  "artifact_id": "abc123",
  "version": 1,
  "context_type": "browser",
  "source": "browser_automation",
  "lineage": {
    "plan_id": "plan123",
    "task_id": "task123",
    "agent_id": "agent123"
  },
  "retrieval": {
    "mode": "summary_first",
    "max_tokens": 1200
  }
}
```

Implementation notes:

- A source should not inject the whole artifact by default.
- Use a summary-first context pack, then load full content only when required.
- Preserve artifact version, provenance, source URL/file path, and task lineage.
- The left Sources panel should show artifact sources beside files, URLs, memory,
  and task outputs.
- The planner should receive selected artifact sources through the same source
  contract it receives files and URLs.

Current frontend source types already include `artifact`, but artifact listing is
not wired as a first-class source registry. This should be added before memory
features become deeper, otherwise context will remain implicit and hard to
debug.

## 6. Code Output and Sandbox

Some outputs are code: scripts, apps, browser automations, data pipelines, API
clients, or generated dashboards. These should not be plain chat text.

Target behavior:

1. Planner recognizes code-producing intent.
2. It creates a code project in the workspace sandbox.
3. The sandbox runs only after policy checks.
4. UI shows preview URL, logs, files, and generated artifacts.
5. The final output links to the code project and any produced reports/files.

Current implementation:

- `CodeSandboxStore` creates project directories under the workspace.
- It can start simple `npm`, `node`, or `python` preview commands.
- It captures process logs and preview URL.

Required hardening:

- Use an execution boundary stronger than raw local subprocess for untrusted code.
- Add dependency install policy. For example, allow `npm install` only after
  approval or inside a disposable environment.
- Add filesystem scope enforcement, network policy, runtime timeouts, and cleanup.
- Add per-project artifact production, such as generated files, screenshots, logs,
  and preview metadata.
- Add UI states: created, installing, running, failed, stopped, completed.
- Add "promote code project to source" for generated documentation or output files,
  not for arbitrary source code unless explicitly selected.

Recommended direction:

- Short term: keep local subprocess sandbox for trusted local development.
- Medium term: add Docker or lightweight isolated worktree runner.
- Long term: support pluggable execution backends, such as local, Docker, remote
  worker, or cloud sandbox.

## 7. Browser Automation Direction

Browser automation should remain split into three layers:

- **Browser MCP Runtime**: real executor, hidden from ordinary users.
- **Browser Automation Skill**: generic SOP and safety contract.
- **Domain Skill**: site-specific workflow such as `life_partner_coupon_codes`.

Runtime engines:

- `playwright`: deterministic isolated browser automation.
- `cdp`: attach to user-owned browser/login session.
- `browser_use`: agentic browser operation for ambiguous pages.

Product contract:

- Planner should generate `browser_run` when browser work is required.
- If URL or authorization is missing, ask a typed question.
- If external access requires approval, show an approval button, not a text box.
- If runtime dependencies are missing, produce a recoverable runtime artifact,
  not a chat response telling the user to switch environments.
- Browser results should become artifacts with extracted text, tables, screenshot,
  downloads, URL, engine, profile, and limitations.

Current code supports the core runtime path in `BrowserAutomationService`, but
needs stronger action-level execution and user-facing recovery.

## 8. Memory and Context Budget

Memory should be treated as a source with routing, not as an unlimited prompt
appendix.

Required services:

- `MemoryRouter`: decides hot, cold, procedural, and deep memory retrieval.
- `ContextBudgetManager`: enforces max context and compression strategy.
- `SourceAttributionService`: records which source influenced the plan/output.
- `MemoryWriteApproval`: asks before writing long-term preferences or sensitive
  facts.
- `AnswerSuggestionService`: suggests answers for repeated missing-input prompts
  based on recent approvals, similar tasks, artifact metadata, and memory.

For HITL questions, the UI should show:

- required fields
- suggested answer cards
- source of suggestion
- confidence
- one-click fill
- manual override
- final confirm button

Retrieval order:

1. Current conversation state.
2. Selected sources.
3. Recent task answers in this workspace.
4. Similar prior approvals and form responses.
5. Artifact summaries.
6. Long-term memory.

Vector retrieval is useful here, but should not be the first dependency. Start
with structured recent answer reuse, then add embeddings for semantic matching.

## 9. Multi-Agent and Hermes Direction

Hermes should remain the control plane. Claude Agent SDK, Browser MCP, Codex/CLI,
MCP tools, connectors, and skills should be execution backends.

Responsibilities:

| Layer | Owns |
|---|---|
| Hermes control plane | workspace, policy, approvals, run state, events, artifacts, scheduling, memory routing |
| Planner | intent confirmation, capability selection, plan proposal, team/task decomposition |
| Agent runtime | tool calling, memory-aware execution, stateful agent loop |
| Claude Agent SDK backend | workspace-isolated coding and agentic file operations |
| Browser runtime | browser page execution and capture |
| Scheduler | once, long-running, interval, cron, retry, lease |
| Artifact system | durable user-facing outputs and lineage |
| Source system | reusable context for future runs |

For complex tasks, Planner should decide:

- single direct answer
- one-shot execution
- long-running task
- scheduled task
- multi-agent task graph
- code project
- browser workflow
- research workflow

The user should see "who is doing what" only as simple progress, not raw agent
node internals.

## 10. Multi-Language Product Plan

Current code does not show a real i18n layer. Multi-language support should be a
first-class product capability.

Locale priority:

1. User language setting.
2. Workspace language setting.
3. Browser locale from `navigator.language`.
4. Backend default locale.
5. `en-US`.

Frontend plan:

- Add `i18next` or a lightweight dictionary layer.
- Store user language in account settings.
- Store workspace default language in workspace settings.
- Detect browser locale on first login only, then allow manual override.
- Do not hardcode product strings in components.
- Keep technical event/status codes stable and translate display text in the UI.

Backend plan:

- Add `locale` to chat, planner, approval, and artifact requests.
- Planner prompts should receive `locale` and generate user-facing copy in that
  language.
- Backend API errors should return stable `code` plus fallback English/Chinese
  message.
- Artifact metadata should store `locale`.
- System templates for approvals, browser recovery, task summaries, and artifact
  generation should be locale-aware.

Recommended API extension:

```json
{
  "locale": "zh-CN",
  "timezone": "Asia/Shanghai"
}
```

This should be carried through Planner, Scheduler payloads, Browser runs, and
Artifact generation.

## 11. Missing Product and Runtime Capabilities

P0 gaps:

- Durable conversation run state separate from chat messages.
- Clear intent confirmation step before plan generation.
- Typed missing-input schema with validation and suggestion cards.
- Plan proposal cards that explain what will happen, required access, expected
  outputs, and whether it is one-shot or recurring.
- Plan-to-task promotion API and UI.
- Artifact-to-source promotion API and source registry.
- Runtime recovery contract for missing browser/code dependencies.
- Locale detection and user/workspace language preference.

P1 gaps:

- ContextBudgetManager and source attribution.
- Answer suggestion from prior approvals and artifacts.
- Better browser runtime action execution beyond simple page observation.
- Code sandbox hardening and preview lifecycle.
- Multi-agent plan decomposition UI and task graph summary.
- Artifact detail modal with node-to-node workflow summary.
- Playbook validation before skill promotion.

P2 gaps:

- Vector memory for semantic answer and source matching.
- Remote/distributed worker assignment for long tasks.
- Connector marketplaces and account-level connector presets.
- Enterprise admin templates for skills, MCP, policies, and providers.
- Full i18n coverage for docs, UI, prompts, and artifacts.

## 12. Implementation Sequence

### Phase 1: Run State and Intent Confirmation

- Add `ConversationRun` or equivalent persisted run snapshot.
- Split intent confirmation from plan proposal.
- UI shows user message, Cognix intent summary, confirm/edit buttons.
- Refresh should restore the same run state.

### Phase 2: Typed Input and Approval Flow

- Replace free-text approval prompts with typed fields and validation.
- Add suggestion cards from recent workspace answers.
- Distinguish `missing_input`, `approval`, `runtime_blocked`, and `policy_denied`.
- Approval confirmation uses buttons, not text commands.

### Phase 3: Plan Proposal Contract

- Normalize Planner output into user-facing cards:
  - objective
  - proposed approach
  - required sources/capabilities
  - access and risk
  - expected outputs
  - execution mode
  - cost estimate
- Hide raw agent/MCP/skill details by default.

### Phase 4: Plan to Task Promotion

- Add backend promotion endpoint.
- Store immutable plan snapshot and source references.
- Add UI "Run once", "Make recurring", "Run as long task".
- Confirm schedule, timezone, approval rules, and output policy.

### Phase 5: Artifact to Source

- Add source registry.
- Add artifact promotion endpoint.
- Add artifact source listing in Sources panel.
- Add summary-first context injection for artifact sources.

### Phase 6: Sandbox and Browser Recovery

- Add runtime readiness checks for Playwright, CDP, browser-use, and code sandbox.
- Add recovery artifacts for missing runtime dependencies.
- Add sandbox policy checks before command execution.
- Add generated code project output to Studio.

### Phase 7: Memory and Self-Evolution

- Add MemoryRouter and ContextBudgetManager.
- Add source attribution.
- Add artifact-to-playbook-to-skill confirmation flow.
- Add memory write approval for durable preferences and SOPs.

### Phase 8: Multi-Language

- Add locale persistence and browser locale detection.
- Add frontend translation layer.
- Add backend locale propagation.
- Localize planner, approval, artifact, and error templates.

## 13. Near-Term Recommendation

The next implementation should not add more panels. It should stabilize the
conversation state machine and promotion contracts:

1. Persist run state.
2. Make intent confirmation explicit.
3. Make missing input typed and resumable.
4. Add plan-to-task promotion.
5. Add artifact-to-source promotion.
6. Add locale detection and settings.

These changes turn the existing Hermes runtime, Scheduler, Browser runtime,
Skills, MCP, Artifacts, and Memory pieces into a coherent product path without
rewriting the runtime foundation.
