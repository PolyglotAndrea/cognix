/** Shared workspace types used across TaskComposer, PlanCard, and other components. */

export interface PlanStep {
  id: string
  action: string
  description: string
  params: Record<string, unknown>
  depends_on: string[]
}

export interface WorkspacePlan {
  id: string
  workspace_id: string
  summary: string
  intent_type: string
  execution_mode: string
  steps: PlanStep[]
  required_skills: string[]
  required_connectors: string[]
  sandbox_permissions: string[]
  expected_artifacts: string[]
  recommended_agents: Array<Record<string, unknown>>
  recommended_skills: Array<Record<string, unknown>>
  recommended_mcp_tools: Array<Record<string, unknown>>
  scheduling: Record<string, unknown>
  capability_snapshot: Record<string, unknown>
  estimated_cost: string
  status: string
  step_statuses: Record<string, string>
  created_at: string
}

export interface ExecutionResult {
  task_id: string
  status?: string
  result?: string
  error?: string
  duration_ms?: number
}

export interface ApplyResult {
  plan_id: string
  status: string
  created: Record<string, string[]>
  execution_results?: ExecutionResult[]
  artifacts?: string[]
  code_projects?: string[]
  approval_ids?: string[]
  plan?: WorkspacePlan
}

/** Props for components that receive drag handle from SortablePanel. */
export interface DragHandleProps {
  onMouseDown?: (e: React.MouseEvent) => void
  onTouchStart?: (e: React.TouchEvent) => void
  onKeyDown?: (e: React.KeyboardEvent) => void
  [key: string]: unknown
}
