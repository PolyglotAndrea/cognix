# Assistant UI Chat Migration

## Goal

Use `assistant-ui` for the visible chat/thread/composer layer without replacing Cognix runtime state.
Hermes runtime, Planner, Approvals, Artifacts, Scheduler, Memory, MCP, Skills, and Browser runtime stay behind existing APIs.

## Current Implementation

The migration is introduced as a feature-flagged prototype:

- Enable with `VITE_COGNIX_ASSISTANT_UI=true`.
- Default UI continues to use the existing `SimpleMode`.
- The prototype renders the center Conversation with `@assistant-ui/react` primitives and a custom external-store runtime.
- It calls the existing workspace chat APIs:
  - `GET /api/v1/workspaces/{workspace_id}/chats`
  - `GET /api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages`
  - `POST /api/v1/workspaces/{workspace_id}/chats/{chat_id}/messages/stream`
- It records a lightweight conversation run through the existing `/runs` API, but does not own Planner state.

## Boundary

Assistant UI should own:

- Thread rendering
- Composer behavior
- Message state projection
- Streaming text display
- Future inline tool/HITL components

Cognix should continue to own:

- Chat/session persistence
- Intent to plan orchestration
- Approval and resume protocol
- Artifact/source/skill promotion
- Browser automation and sandbox execution
- Memory routing and write approval

## Next Migration Steps

1. Add a Planner adapter so assistant-ui messages can render `intent_confirm`, `needs_input`, `plan_proposed`, `running`, and `artifact_ready` as typed components.
2. Move HITL cards into assistant-ui tool-call/interrupt parts, while keeping `/approvals` as the source of truth.
3. Add thread-list support backed by workspace chat sessions so refresh/re-entry works from the left Sources/Tasks rail.
4. Add attachment/source chips to the composer and map selected sources into the existing planner/chat request body.
5. Once parity is reached, flip the default from `SimpleMode` to assistant-ui and keep the old mode behind a developer flag.

## Rollback

Unset `VITE_COGNIX_ASSISTANT_UI` or set it to any value other than `true`. No backend data migration is required.
