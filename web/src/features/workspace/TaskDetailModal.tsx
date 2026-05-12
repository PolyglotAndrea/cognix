import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2,
  ChevronRight,
  Clock,
  Loader2,
  RefreshCw,
  ShieldQuestion,
  XCircle,
  Zap,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { Badge, Button, Modal, Spinner } from '@/shared/ui'
import { WorkflowStepTree, type WorkflowStepResult } from './WorkflowStepTree'

interface TaskInfo {
  id: string
  name: string
  task_type: string
  schedule: string
  state: string
  run_count: number
  max_retries?: number
  last_run?: string | null
  created_at?: string | null
  workspace_id?: string | null
}

interface TaskRun {
  id: number
  status: string
  result: string
  error: string
  duration_ms: number
  started_at?: string | null
  finished_at?: string | null
}

interface WorkspaceEvent {
  timestamp: string
  type: string
  [key: string]: any
}

const stateBadge: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  active: 'success',
  paused: 'warning',
  failed: 'error',
  canceled: 'error',
  completed: 'default',
}

const typeIcons: Record<string, string> = {
  agent_call: 'Agent',
  rpc_call: 'RPC',
  http_webhook: 'HTTP',
  skill_exec: 'Skill',
  workflow: 'Workflow',
}

export function TaskDetailModal({
  isOpen,
  onClose,
  task,
}: {
  isOpen: boolean
  onClose: () => void
  task: TaskInfo
}) {
  const queryClient = useQueryClient()
  const [expandedRun, setExpandedRun] = useState<number | null>(null)

  const { data: runs = [], isLoading: runsLoading } = useQuery<TaskRun[]>({
    queryKey: ['task-runs', task.id],
    queryFn: () => api.get(`/tasks/${task.id}/runs?limit=50`).then((r) => r.data),
    enabled: isOpen,
  })

  // Fetch workspace events for approval nodes
  const { data: events = [] } = useQuery<WorkspaceEvent[]>({
    queryKey: ['workspace-events', task.workspace_id],
    queryFn: () =>
      api
        .get(`/workspaces/${task.workspace_id}/events?limit=200`)
        .then((r) => r.data),
    enabled: isOpen && !!task.workspace_id,
  })

  const triggerMutation = useMutation({
    mutationFn: () => api.post(`/tasks/${task.id}/trigger`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['task-runs', task.id] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  const approvalEvents = events.filter(
    (e) => e.type === 'approval.requested' || e.type === 'approval.completed' || e.type === 'approval.rejected',
  )

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={task.name} size="xl">
      <div className="space-y-6">
        {/* Header info */}
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant={stateBadge[task.state] || 'default'}>{task.state}</Badge>
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Zap className="h-3.5 w-3.5" />
            {typeIcons[task.task_type] || task.task_type}
          </span>
          <span className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" />
            {task.schedule}
          </span>
          <span className="text-xs text-muted-foreground">
            {task.run_count} runs
          </span>
          {task.state === 'failed' && (
            <Button
              size="sm"
              variant="danger"
              className="gap-1.5"
              onClick={() => triggerMutation.mutate()}
              disabled={triggerMutation.isPending}
            >
              {triggerMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Retry Now
            </Button>
          )}
        </div>

        {/* Run Timeline */}
        <div>
          <h4 className="mb-3 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            Run Timeline
          </h4>
          {runsLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : runs.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">No runs yet</div>
          ) : (
            <div className="space-y-2">
              {runs.map((run) => (
                <RunNode
                  key={run.id}
                  run={run}
                  expanded={expandedRun === run.id}
                  onToggle={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
                  taskType={task.task_type}
                  onRetry={
                    run.status === 'failure'
                      ? () => triggerMutation.mutate()
                      : undefined
                  }
                  retrying={triggerMutation.isPending}
                />
              ))}
            </div>
          )}
        </div>

        {/* Human Intervention */}
        {approvalEvents.length > 0 && (
          <div>
            <h4 className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              <ShieldQuestion className="h-3.5 w-3.5" />
              Human Intervention ({approvalEvents.length})
            </h4>
            <div className="space-y-2">
              {approvalEvents.map((evt, i) => (
                <ApprovalEventNode key={i} event={evt} />
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

function RunNode({
  run,
  expanded,
  onToggle,
  taskType,
  onRetry,
  retrying,
}: {
  run: TaskRun
  expanded: boolean
  onToggle: () => void
  taskType: string
  onRetry?: () => void
  retrying: boolean
}) {
  const isSuccess = run.status === 'success'
  const StatusIcon = isSuccess ? CheckCircle2 : XCircle
  const statusColor = isSuccess ? 'text-emerald-500' : 'text-rose-500'
  const statusBg = isSuccess ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/20'

  // Try to parse workflow steps from result
  let steps: WorkflowStepResult[] | null = null
  let workflowMetadata: Record<string, any> | null = null
  if (taskType === 'workflow' && run.result) {
    try {
      const parsed = JSON.parse(run.result)
      if (Array.isArray(parsed.steps)) {
        steps = parsed.steps
        workflowMetadata = parsed.metadata || null
      }
    } catch {
      // Not JSON or no steps
    }
  }

  return (
    <div className={`rounded-xl border ${statusBg} transition-colors`}>
      <button
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={onToggle}
      >
        <StatusIcon className={`h-4 w-4 shrink-0 ${statusColor}`} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-foreground">
              Run #{run.id}
            </span>
            <Badge variant={isSuccess ? 'success' : 'error'}>{run.status}</Badge>
            {run.duration_ms != null && (
              <span className="font-mono text-[10px] text-muted-foreground">
                {formatDuration(run.duration_ms)}
              </span>
            )}
          </div>
          {run.started_at && (
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              {new Date(run.started_at).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {onRetry && (
            <button
              className="flex h-7 items-center gap-1 rounded-lg px-2 text-[10px] font-bold text-rose-500 transition-colors hover:bg-rose-500/10"
              onClick={(e) => {
                e.stopPropagation()
                onRetry()
              }}
              disabled={retrying}
              title="Retry this task"
            >
              <RefreshCw className={`h-3 w-3 ${retrying ? 'animate-spin' : ''}`} />
              Retry
            </button>
          )}
          <ChevronRight
            className={`h-4 w-4 text-muted-foreground transition-transform ${
              expanded ? 'rotate-90' : ''
            }`}
          />
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border/50 px-4 py-3 space-y-4">
          {/* Workflow Step Tree */}
          {steps && (
            <WorkflowStepTree
              steps={steps}
              pattern={workflowMetadata?.pattern}
            />
          )}

          {/* Output / Error */}
          {!steps && run.result && (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                Output
              </div>
              <pre className="max-h-48 overflow-auto rounded-lg bg-background/50 p-3 font-mono text-[11px] leading-5 text-foreground whitespace-pre-wrap break-all">
                {run.result}
              </pre>
            </div>
          )}
          {run.error && (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-rose-500">
                Error
              </div>
              <pre className="max-h-32 overflow-auto rounded-lg bg-rose-500/5 p-3 font-mono text-[11px] leading-5 text-rose-600 dark:text-rose-300 whitespace-pre-wrap break-all">
                {run.error}
              </pre>
              {onRetry && (
                <Button
                  size="sm"
                  variant="danger"
                  className="mt-2 gap-1.5"
                  onClick={onRetry}
                  disabled={retrying}
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${retrying ? 'animate-spin' : ''}`} />
                  Retry Failed Run
                </Button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ApprovalEventNode({ event }: { event: WorkspaceEvent }) {
  const isRequest = event.type === 'approval.requested'
  const isCompleted = event.type === 'approval.completed'
  const dotColor = isRequest
    ? 'bg-amber-500 shadow-amber-500/30'
    : isCompleted
      ? 'bg-emerald-500 shadow-emerald-500/30'
      : 'bg-rose-500 shadow-rose-500/30'

  return (
    <div className="flex items-start gap-3 rounded-xl border border-border px-4 py-3">
      <div className={`mt-1 h-2 w-2 shrink-0 rounded-full shadow-lg ${dotColor}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-foreground">
            {isRequest ? 'Approval Required' : isCompleted ? 'Approved' : 'Rejected'}
          </span>
          {event.tool && (
            <Badge variant="default">{event.tool}</Badge>
          )}
        </div>
        {event.reason && (
          <p className="mt-0.5 text-[11px] text-muted-foreground">{event.reason}</p>
        )}
        {event.arguments && (
          <pre className="mt-1.5 max-h-20 overflow-auto rounded-lg bg-muted/50 p-2 font-mono text-[10px] text-muted-foreground">
            {JSON.stringify(event.arguments, null, 2)}
          </pre>
        )}
        <p className="mt-1 text-[10px] text-muted-foreground">
          {new Date(event.timestamp).toLocaleString()}
        </p>
      </div>
    </div>
  )
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60000)
  const s = Math.round((ms % 60000) / 1000)
  return `${m}m${s}s`
}
