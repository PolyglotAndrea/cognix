# Notebook-Style UI Migration Plan

This plan migrates Cognix from an expert-facing agent console to a
NotebookLM-style workspace interface while keeping the Hermes runtime, planner,
MCP, skills, scheduler, approvals, memory, and artifact APIs intact.

The migration is a product shell change, not a runtime rewrite.

## 1. Target Experience

The default workspace should have three primary columns:

1. **Sources**
   - Workspace files, URLs, uploaded documents, selected memories, and connected
     source collections.
   - Search and add-source entry points.
   - Source selection controls for each run.

2. **Conversation**
   - One intent/chat composer.
   - The system can answer directly, propose a plan, ask for missing input, or
     run an approved plan.
   - Plan, execution, approvals, and final responses appear as conversational
     cards instead of separate expert panels.

3. **Studio**
   - Output creation shortcuts such as Report, Data Table, Slide Deck, Mind Map,
     Quiz, Browser Capture, Code/App Preview, and Playbook.
   - Artifact library and artifact detail preview.
   - Pending user input appears only when needed.

The user-facing mental model is:

> Add sources, ask Cognix, receive structured outputs.

The hidden implementation remains:

> Intent -> Context -> CapabilityResolver -> Plan -> Approval -> Hermes/Claude/MCP/Skill/CLI/Scheduler -> Events -> Artifact -> Memory/Playbook.

## 2. What Stays Unchanged

The following backend layers should remain stable:

- `cognix/planner/service.py`
- `cognix/planner/capabilities.py`
- `cognix/core/*`
- Hermes Agent runtime
- Claude Agent SDK bridge
- MCP runtime and tool adapter
- Skills registry and skill execution
- SchedulerEngine, TaskExecutor, distributed lease model
- Approval APIs
- Artifact APIs
- Workspace settings and policy APIs
- Provider resolver and secret storage

UI migration should call existing APIs and only add thin aggregation endpoints
when the UI needs a simpler view model.

## 3. Navigation And Information Architecture

### 3.1 Default User Surface

| Target surface | Current source | Migration action |
| --- | --- | --- |
| Sources column | Files, Memory, Connectors, URL inputs | Merge into `SourcesPanel` |
| Conversation column | `SimpleMode`, `TaskComposer`, chat history, plan cards | Replace with `ConversationPanel` |
| Studio column | `ArtifactPanel`, `CodeProjectsPanel`, `PlaybookPanel`, Approvals | Merge into `StudioPanel` |
| Top bar | Workspace selector, search, settings, user menu | Keep, simplify labels |

### 3.2 Hidden By Default

Move these behind **Developer Details**:

- Agent list and agent runtime parameters
- Raw MCP server configuration
- Raw skill manifests
- Scheduler cron/task table
- Runtime nodes and dispatcher status
- Policy JSON
- Audit logs
- Raw SSE/events/logs
- API access tokens
- Provider override internals
- Connector credential internals

These features still exist. They should not be the default visual model.

### 3.3 Settings Boundaries

Split settings into clear scopes:

- **Account Settings**
  - Profile
  - Global provider keys, if supported
  - API access tokens
  - Billing
  - Global message bridge gateways

- **Workspace Settings**
  - Workspace provider selection or override
  - Workspace sources
  - Workspace memory
  - Enabled skills/capabilities
  - Enabled MCP profiles
  - Workspace policy preset
  - Workspace schedules/playbooks

- **Developer Details**
  - Raw runtime, scheduler, MCP, policy, agents, and event diagnostics.

## 4. Component Migration

### Phase 1: Shell And Visibility

Goal: make the product look and behave like the target without changing backend
contracts.

Create:

- `NotebookWorkspace.tsx`
- `SourcesPanel.tsx`
- `ConversationPanel.tsx`
- `StudioPanel.tsx`
- `StudioActionGrid.tsx`
- `SourcePicker.tsx`
- `DeveloperDetailsDrawer.tsx`

Keep existing components but remount them under the new shell:

- `ArtifactPanel` -> Studio output library
- `ArtifactDetail` -> Studio detail drawer
- `CodeProjectsPanel` -> Studio "Apps / Browser Captures"
- `PlaybookPanel` -> Studio "Playbooks"
- `RightPanel` advanced tabs -> Developer Details
- `LeftPanel` agents/runtime -> Developer Details
- `TaskComposer` and `SimpleMode` logic -> Conversation flow

Acceptance:

- Default workspace shows Sources, Conversation, Studio.
- Expert panels are not visible by default.
- Existing plan/apply/artifact flow still works.

### Phase 2: Source-Centric Context

Goal: make files, URLs, memory snippets, and connector records the user's main
context primitives.

Add a source view model:

```json
{
  "id": "source_123",
  "kind": "file|url|memory|connector|artifact",
  "title": "Interview notes.docx",
  "summary": "Optional extracted summary",
  "selected": true,
  "metadata": {
    "path": "...",
    "connector": "...",
    "token_estimate": 1200
  }
}
```

Implementation:

- Reuse workspace file APIs for local files.
- Reuse artifact APIs for generated outputs as future sources.
- Reuse memory APIs for selected memories.
- Add a thin `GET /api/v1/workspaces/{workspace_id}/sources` endpoint only if
  composing this on the frontend becomes too complex.
- Pass selected source ids into plan/chat requests as context hints.

Acceptance:

- User can add/select sources before asking.
- Planner receives selected sources and mentions them in plan/artifact provenance.

### Phase 3: Conversation As Control Plane

Goal: one chat-like flow controls direct answers, plans, approvals, long tasks,
and outputs.

Conversation message types:

- `user_message`
- `assistant_answer`
- `plan_proposal`
- `execution_timeline`
- `approval_request`
- `needs_input`
- `artifact_ready`
- `error_recovery`

Rules:

- If a request is simple and safe, answer directly.
- If execution is required, show a plan card.
- If required data is missing, show an inline question and mirror it in Studio
  "Needs Input".
- If execution completes, open the artifact in Studio.
- If execution fails, show a recoverable error with the exact next action.

Acceptance:

- Users do not need to switch between Plan and Chat.
- Plan is an inline assistant card, not a separate mode.
- `needs_input` no longer looks like success.

### Phase 4: Studio Output Model

Goal: Studio becomes the output factory and library.

Studio cards:

- Report
- Data Table
- Slide Deck
- Mind Map
- Quiz
- Audio Overview
- Video Overview
- Browser Capture
- Code/App Preview
- Playbook

Each card maps to an internal capability:

| Studio action | Internal route |
| --- | --- |
| Report | Planner + Artifact |
| Data Table | Planner + file/parser/browser/MCP + Artifact |
| Slide Deck | Skill or future exporter |
| Mind Map | Artifact transform |
| Quiz | Artifact transform |
| Browser Capture | Browser automation skill/MCP + Artifact |
| Code/App Preview | Code sandbox project |
| Playbook | Artifact -> Playbook promotion |

Acceptance:

- Right side defaults to output actions and output library.
- Apps and browser captures are output subtypes, not a separate technical panel.
- Pending approvals appear above outputs only when pending.

### Phase 5: Developer Details Consolidation

Goal: preserve power-user functionality without exposing it to non-expert users.

Move these current panels into a drawer or route:

- Runtime
- Agents
- Tasks
- Scheduler
- Policy
- Audit
- Bots
- MCP
- Skills
- Raw files
- Raw logs
- JSON/event stream

Acceptance:

- Default user can complete a task without seeing agent ids, runtime nodes,
  permission modes, raw logs, or cron syntax.
- Developer can still inspect and debug the full runtime.

## 5. Backend Compatibility Strategy

No runtime refactor is required for the first migration.

Use current APIs:

- `/api/v1/workspaces/{workspace_id}/plans`
- `/api/v1/workspaces/{workspace_id}/plans/{plan_id}/apply`
- `/api/v1/workspaces/{workspace_id}/plans/{plan_id}/apply/stream`
- `/api/v1/workspaces/{workspace_id}/chats`
- `/api/v1/workspaces/{workspace_id}/files`
- `/api/v1/artifacts`
- `/api/v1/approvals`
- `/api/v1/skills`
- `/api/v1/workspaces/{workspace_id}/mcp/*`
- `/api/v1/workspaces/{workspace_id}/code-projects`

Optional aggregation endpoints:

- `GET /api/v1/workspaces/{workspace_id}/sources`
- `POST /api/v1/workspaces/{workspace_id}/sources`
- `POST /api/v1/workspaces/{workspace_id}/studio/actions`
- `GET /api/v1/workspaces/{workspace_id}/studio`

Aggregation endpoints should not own core state. They should compose existing
storage and services.

## 6. State Mapping

| Existing state | New UI label |
| --- | --- |
| `plan.status = draft` | Suggested plan |
| `plan.status = executing` | Working |
| `plan.status = needs_input` | Needs input |
| `plan.status = applied` | Completed |
| `plan.status = failed` | Needs attention |
| approval pending | Needs input |
| artifact draft | Output draft |
| artifact published | Published output |
| code project running | App preview |
| scheduled task active | Scheduled workflow |
| runtime node | Developer runtime detail |

## 7. Visual Direction

Use the reference layout as direction, not as a clone:

- Light neutral background.
- Three rounded panels with subtle borders.
- Top bar with workspace name, create/action button, analytics/share/settings,
  and account menu.
- Sources list uses compact document rows and selection state.
- Conversation column prioritizes readable long-form output.
- Composer is fixed near bottom of center panel.
- Studio cards are colored but restrained.
- Artifact cards are compact and preview-driven.
- Technical badges should be plain language:
  - "Browser automation" instead of `mcp.browser.*`
  - "Needs confirmation" instead of `approval_request`
  - "App preview" instead of `code_project`

Avoid:

- Agent ids in default UI.
- Runtime nodes in default UI.
- Large technical side rails.
- Plan/Chat mode confusion.
- Showing mock or stale failed artifacts as current state.

## 8. Rollout Plan

### Milestone A: Notebook Shell

- Add `NotebookWorkspace`.
- Route simple mode to notebook shell.
- Keep advanced mode accessible.
- Mount old panels in new slots.

### Milestone B: Sources Panel

- Implement source list from workspace files and artifacts.
- Add URL/source input.
- Persist source selection in workspace UI state.
- Pass selected sources to planner/chat metadata.

### Milestone C: Unified Conversation

- Merge chat and plan composer.
- Render plan proposals inline.
- Render `needs_input` inline and in Studio.
- Auto-open output artifact after completion.

### Milestone D: Studio Panel

- Replace current right panel default with Studio.
- Add output action grid.
- Merge Apps, Artifacts, Playbooks into Studio sections.
- Move advanced tabs into Developer Details.

### Milestone E: Cleanup And Guardrails

- Remove remaining mock/default hardcoded rows from user-facing UI.
- Add dev-only cleanup for stale local state.
- Add workspace-scoped filtering checks for sources, artifacts, apps, tasks.
- Add screenshot verification for desktop and narrow layouts.

## 9. Risks And Controls

| Risk | Control |
| --- | --- |
| Hiding too much blocks debugging | Keep Developer Details one click away |
| Source abstraction duplicates backend state | Treat Sources as a view model, not a new owner |
| Plan/chat logic diverges | Conversation panel must use existing planner/chat APIs |
| Studio actions become fake buttons | Each action must map to an existing capability or be disabled with clear copy |
| Old artifacts confuse users | Filter by workspace and add local dev cleanup |
| Runtime changes sneak in | Keep migration PRs UI-only unless an aggregation endpoint is explicitly needed |

## 10. First Implementation Slice

The first code slice should be:

1. Add `NotebookWorkspace.tsx`.
2. Switch default `ui_mode=simple` rendering from `SimpleMode` to `NotebookWorkspace`.
3. Create placeholder `SourcesPanel`, `ConversationPanel`, and `StudioPanel`.
4. Reuse current `SimpleMode` execution logic inside `ConversationPanel`.
5. Reuse current `ArtifactPanel` inside `StudioPanel`.
6. Move `RightPanel` advanced content behind `DeveloperDetailsDrawer`.
7. Keep all backend APIs unchanged.

This gives the correct product shape first, then each panel can be refined
without touching the runtime base.
