import { useRef, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Activity,
  Terminal,
  FileJson,
  FileText,
  Folder,
  PlayCircle,
  Wrench,
  ChevronRight,
  ChevronLeft,
  ShieldQuestion,
  ShieldCheck,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { useWorkspaceStore } from './store'
import { Panel, PanelHeader, PanelBody, Badge } from '@/shared/ui'

const TABS = [
  { key: 'approvals' as const, label: 'Ask', icon: ShieldQuestion },
  { key: 'tasks' as const, label: 'Tasks', icon: Clock },
  { key: 'files' as const, label: 'Files', icon: Folder },
  { key: 'events' as const, label: 'Events', icon: Activity },
  { key: 'results' as const, label: 'Results', icon: Wrench },
  { key: 'logs' as const, label: 'Logs', icon: Terminal },
  { key: 'json' as const, label: 'JSON', icon: FileJson },
]

interface TaskSummary {
  id: string
  name: string
  task_type: string
  schedule: string
  state: string
  run_count: number
  last_run?: string | null
  runs: TaskRun[]
}

interface TaskRun {
  id: number
  status: string
  result: string
  error?: string
  duration_ms?: number
  started_at?: string | null
}

interface WorkspaceInfo {
  id: string
  name: string
}

interface WorkspaceFile {
  path: string
  name: string
  kind: 'file' | 'directory'
  size: number
  updated_at: string
}

interface WorkspaceEvent {
  timestamp: string
  type: string
  message?: string
  response?: string
  provider?: string
  agent_id?: string
  [key: string]: unknown
}

interface ApprovalRequest {
  id: string
  agent_id: string
  workspace_id?: string | null
  tool_name: string
  arguments: Record<string, unknown>
  access_level: string
  reason: string
  status: 'pending' | 'approved' | 'rejected' | 'completed'
  kind?: 'tool_permission' | 'plan_confirmation' | 'question'
  response?: string
  result?: string
  metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export function RightPanel({ dragHandleProps }: { dragHandleProps?: any }) {
  const queryClient = useQueryClient()
  const {
    rightPanelTab,
    setRightPanelTab,
    rightPanelOpen,
    toggleRightPanel,
    toolResults,
    executionLogs,
    addLog,
    addToolResult,
  } =
    useWorkspaceStore()
  const logsEndRef = useRef<HTMLDivElement>(null)
  const [currentDir, setCurrentDir] = useState('')
  const [previewPath, setPreviewPath] = useState<string | null>(null)
  
  const { data: workspaces = [] } = useQuery<WorkspaceInfo[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get('/workspaces').then((r) => r.data),
  })
  
  const workspaceId = workspaces[0]?.id
  
  const { data: tasks = [], isLoading: tasksLoading } = useQuery<TaskSummary[]>({
    queryKey: ['workspace-task-status'],
    queryFn: async () => {
      const response = await api.get('/tasks')
      const taskRows = response.data as Omit<TaskSummary, 'runs'>[]
      return Promise.all(
        taskRows.slice(0, 8).map(async (task) => {
          const runs = await api
            .get(`/tasks/${task.id}/runs`, { params: { limit: 3 } })
            .then((r) => r.data as TaskRun[])
            .catch(() => [])
          return { ...task, runs }
        })
      )
    },
    refetchInterval: 5000,
  })
  
  const { data: files = [], isLoading: filesLoading } = useQuery<WorkspaceFile[]>({
    queryKey: ['workspace-files', workspaceId, currentDir],
    queryFn: () => api.get(`/workspaces/${workspaceId}/files`, { params: { path: currentDir } }).then((r) => r.data),
    enabled: !!workspaceId,
  })
  
  const { data: preview } = useQuery<{ path: string; content: string }>({
    queryKey: ['workspace-file-preview', workspaceId, previewPath],
    queryFn: () => api.get(`/workspaces/${workspaceId}/files/preview`, { params: { path: previewPath } }).then((r) => r.data),
    enabled: !!workspaceId && !!previewPath,
  })
  
  const { data: events = [], isLoading: eventsLoading } = useQuery<WorkspaceEvent[]>({
    queryKey: ['workspace-events', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/events`, { params: { limit: 50 } }).then((r) => r.data),
    enabled: !!workspaceId,
    refetchInterval: 5000,
  })

  const { data: approvals = [], isLoading: approvalsLoading } = useQuery<ApprovalRequest[]>({
    queryKey: ['approvals', workspaceId],
    queryFn: () =>
      api
        .get('/approvals', { params: { workspace_id: workspaceId, include_resolved: true } })
        .then((r) => r.data),
    enabled: !!workspaceId,
    refetchInterval: 5000,
  })

  const approvalMutation = useMutation({
    mutationFn: ({
      approval,
      action,
      response,
    }: {
      approval: ApprovalRequest
      action: 'approve' | 'reject' | 'resume' | 'respond'
      response?: string
    }): Promise<unknown> => {
      if (action === 'resume' && approval.metadata?.runtime === 'claude-agent-sdk') {
        return streamClaudeApprovalResume(approval, response, addLog, addToolResult)
      }
      return api.post(`/approvals/${approval.id}/${action}`, response ? { response } : undefined)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-events', workspaceId] })
    },
  })

  useEffect(() => {
    if (rightPanelTab === 'logs') {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [executionLogs, rightPanelTab])

  if (!rightPanelOpen) {
    return (
      <button
        onClick={toggleRightPanel}
        className="w-10 shrink-0 border-l border-border bg-card flex flex-col items-center py-6 gap-8 hover:bg-muted transition-colors group h-full"
        title="Open output panel"
      >
        <ChevronLeft className="h-5 w-5 text-muted-foreground group-hover:text-foreground transition-colors" />
        <div className="flex flex-col gap-6">
           <ShieldQuestion className="h-4 w-4 text-muted-foreground/30" />
           <Clock className="h-4 w-4 text-muted-foreground/30" />
           <Folder className="h-4 w-4 text-muted-foreground/30" />
           <Activity className="h-4 w-4 text-muted-foreground/30" />
           <Wrench className="h-4 w-4 text-muted-foreground/30" />
           <Terminal className="h-4 w-4 text-muted-foreground/30" />
           <FileJson className="h-4 w-4 text-muted-foreground/30" />
        </div>
      </button>
    )
  }

  return (
    <Panel className="w-80 shrink-0 border-l border-border bg-card h-full">
      <PanelHeader dragHandleProps={dragHandleProps} className="justify-between bg-muted/50 backdrop-blur-md px-4 h-14">
        <div className="flex bg-background/50 p-1 rounded-xl border border-border overflow-x-auto scrollbar-hide max-w-[220px]">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setRightPanelTab(tab.key)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all shrink-0 ${
                rightPanelTab === tab.key
                  ? 'bg-primary text-white shadow-lg shadow-primary/20'
                  : 'text-muted-foreground hover:text-foreground hover:bg-background'
              }`}
            >
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          ))}
        </div>
        <button onClick={toggleRightPanel} className="p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all shrink-0">
          <ChevronRight className="h-4 w-4" />
        </button>
      </PanelHeader>

      <PanelBody className="p-0 scrollbar-hide bg-card">
        {/* Approvals Tab */}
        {rightPanelTab === 'approvals' && (
          <div className="p-4 space-y-3">
            {approvalsLoading ? (
              <div className="py-20 text-center">
                <ShieldQuestion className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Loading Requests</p>
              </div>
            ) : approvals.length === 0 ? (
              <div className="py-20 text-center">
                <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                  <ShieldCheck className="h-8 w-8 text-muted-foreground/20" />
                </div>
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Approval Requests</p>
              </div>
            ) : (
              approvals.map((approval) => (
                <ApprovalCard
                  key={approval.id}
                  approval={approval}
                  busy={approvalMutation.isPending}
                  onAction={(action, response) =>
                    approvalMutation.mutate({ approval, action, response })
                  }
                />
              ))
            )}
          </div>
        )}

        {/* Tasks Tab */}
        {rightPanelTab === 'tasks' && (
          <div className="p-4 space-y-3">
            {tasksLoading ? (
              <div className="py-20 text-center">
                <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                  <Clock className="h-8 w-8 text-muted-foreground/20 animate-pulse" />
                </div>
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Loading Tasks</p>
              </div>
            ) : tasks.length === 0 ? (
              <div className="py-20 text-center">
                <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                  <Clock className="h-8 w-8 text-muted-foreground/20" />
                </div>
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Tasks</p>
              </div>
            ) : (
              tasks.map((task) => <TaskStatusCard key={task.id} task={task} />)
            )}
          </div>
        )}

        {/* Files Tab */}
        {rightPanelTab === 'files' && (
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <button
                onClick={() => {
                  setCurrentDir(parentDir(currentDir))
                  setPreviewPath(null)
                }}
                disabled={!currentDir}
                className="rounded-lg px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-30"
              >
                Up
              </button>
              <span className="truncate font-mono text-[10px] text-muted-foreground">
                /{currentDir}
              </span>
            </div>

            {filesLoading ? (
              <div className="py-20 text-center">
                <Folder className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Loading Files</p>
              </div>
            ) : files.length === 0 ? (
              <div className="py-20 text-center">
                <Folder className="h-8 w-8 text-muted-foreground/20 mx-auto mb-4" />
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Files</p>
              </div>
            ) : (
              <div className="space-y-2">
                {files.map((file) => (
                  <button
                    key={file.path}
                    onClick={() => {
                      if (file.kind === 'directory') {
                        setCurrentDir(file.path)
                        setPreviewPath(null)
                      } else {
                        setPreviewPath(file.path)
                      }
                    }}
                    className={`w-full rounded-xl border p-3 text-left transition-all ${
                      previewPath === file.path
                        ? 'border-primary/30 bg-primary/10'
                        : 'border-border bg-muted/30 hover:border-primary/20'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      {file.kind === 'directory' ? (
                        <Folder className="h-4 w-4 text-primary" />
                      ) : (
                        <FileText className="h-4 w-4 text-primary" />
                      )}
                      <div className="min-w-0">
                        <div className="truncate text-xs font-bold text-foreground">{file.name}</div>
                        <div className="mt-0.5 text-[10px] text-muted-foreground">
                          {file.kind === 'directory' ? 'Directory' : formatBytes(file.size)}
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}

            {previewPath && (
              <div className="rounded-2xl border border-border bg-muted/40 overflow-hidden">
                <div className="border-b border-border px-3 py-2 font-mono text-[10px] text-muted-foreground truncate">
                  {previewPath}
                </div>
                <pre className="max-h-80 overflow-auto p-3 text-[11px] leading-5 text-foreground/80">
                  {preview?.content || 'Loading preview...'}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* Events Tab */}
        {rightPanelTab === 'events' && (
          <div className="p-4 space-y-2">
            {eventsLoading ? (
              <div className="py-20 text-center">
                <Activity className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Loading Events</p>
              </div>
            ) : events.length === 0 ? (
              <div className="py-20 text-center">
                <Activity className="h-8 w-8 text-muted-foreground/20 mx-auto mb-4" />
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Events</p>
              </div>
            ) : (
              [...events].reverse().map((event, index) => (
                <div key={`${event.timestamp}-${index}`} className="rounded-2xl border border-border bg-muted/30 p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <Badge variant="info">{event.type}</Badge>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {new Date(event.timestamp).toLocaleTimeString([], { hour12: false })}
                    </span>
                  </div>
                  {event.provider && (
                    <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-primary">
                      {event.provider} · {event.agent_id || 'agent'}
                    </div>
                  )}
                  <p className="text-xs leading-5 text-foreground/80">
                    {String(event.message || event.response || JSON.stringify(event))}
                  </p>
                </div>
              ))
            )}
          </div>
        )}

        {/* Results Tab */}
        {rightPanelTab === 'results' && (
          <div className="p-4 space-y-3">
            {toolResults.length === 0 ? (
              <div className="py-20 text-center">
                 <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                   <Wrench className="h-8 w-8 text-muted-foreground/20" />
                 </div>
                 <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Results</p>
              </div>
            ) : (
              toolResults.map((r) => (
                <ToolResultCard key={r.id} result={r} />
              ))
            )}
          </div>
        )}

        {/* Logs Tab */}
        {rightPanelTab === 'logs' && (
          <div className="p-4 space-y-2 font-mono text-[11px]">
            {executionLogs.length === 0 ? (
              <div className="py-20 text-center">
                 <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                   <Terminal className="h-8 w-8 text-muted-foreground/20" />
                 </div>
                 <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Logs</p>
              </div>
            ) : (
              <div className="bg-muted/30 rounded-2xl p-4 border border-border">
                {executionLogs.map((log) => (
                  <div key={log.id} className="flex items-start gap-3 py-1.5 border-b border-border last:border-0 group">
                    <LogIcon level={log.level} />
                    <span className="text-muted-foreground/30 shrink-0 font-bold">
                      {new Date(log.timestamp).toLocaleTimeString([], { hour12: false })}
                    </span>
                    <span
                      className={`font-medium ${
                        log.level === 'error'
                          ? 'text-rose-500 dark:text-rose-400'
                          : log.level === 'warn'
                            ? 'text-amber-500 dark:text-amber-400'
                            : 'text-foreground/80'
                      }`}
                    >
                      {log.message}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div ref={logsEndRef} />
          </div>
        )}

        {/* JSON Tab */}
        {rightPanelTab === 'json' && (
          <div className="p-4">
            {toolResults.length === 0 ? (
               <div className="py-20 text-center">
                 <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                   <FileJson className="h-8 w-8 text-muted-foreground/20" />
                 </div>
                 <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Data</p>
              </div>
            ) : (
              <div className="relative group">
                <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                   <Badge variant="primary">Raw JSON</Badge>
                </div>
                <pre className="text-[11px] text-emerald-600 dark:text-emerald-400/80 bg-muted/50 rounded-2xl p-5 overflow-auto max-h-[calc(100vh-12rem)] font-mono border border-border scrollbar-hide">
                  {JSON.stringify(toolResults[toolResults.length - 1], null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </PanelBody>
    </Panel>
  )
}

function TaskStatusCard({ task }: { task: TaskSummary }) {
  const latestRun = task.runs[0]
  const hasError = latestRun?.status === 'failure' || !!latestRun?.error || task.state === 'failed'

  return (
    <div className="bg-muted/30 rounded-2xl p-4 border border-border hover:border-primary/20 transition-all overflow-hidden">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="text-xs font-bold text-foreground truncate">{task.name}</div>
          <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground font-bold uppercase tracking-wider">
            <span>{task.task_type}</span>
            <span className="w-1 h-1 rounded-full bg-muted-foreground/30" />
            <span>{task.schedule}</span>
          </div>
        </div>
        <Badge variant={task.state === 'active' ? 'success' : task.state === 'paused' ? 'warning' : 'default'}>
          {task.state}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="rounded-xl border border-border bg-background/50 p-3">
          <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Runs</div>
          <div className="text-lg font-bold text-foreground">{task.run_count}</div>
        </div>
        <div className="rounded-xl border border-border bg-background/50 p-3">
          <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Latest</div>
          <div className="flex items-center gap-1.5 text-xs font-bold text-foreground">
            {hasError ? (
              <AlertCircle className="h-3.5 w-3.5 text-rose-500" />
            ) : latestRun ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            ) : (
              <PlayCircle className="h-3.5 w-3.5 text-muted-foreground" />
            )}
            {latestRun?.status || 'waiting'}
          </div>
        </div>
      </div>

      {latestRun && (
        <pre className="text-[11px] text-muted-foreground bg-background/50 rounded-xl p-3 overflow-auto max-h-36 font-mono border border-border leading-relaxed">
          {(latestRun.error || latestRun.result || 'No output.').slice(0, 500)}
        </pre>
      )}
    </div>
  )
}

function ApprovalCard({
  approval,
  busy,
  onAction,
}: {
  approval: ApprovalRequest
  busy: boolean
  onAction: (action: 'approve' | 'reject' | 'resume' | 'respond', response?: string) => void
}) {
  const [response, setResponse] = useState(approval.response || '')
  const isPending = approval.status === 'pending'
  const isApproved = approval.status === 'approved'
  const isQuestion = approval.kind === 'question'
  const isPlan = approval.kind === 'plan_confirmation'
  const args = JSON.stringify(approval.arguments || {}, null, 2)
  const kindLabel = isQuestion ? 'Question' : isPlan ? 'Plan' : 'Tool'

  return (
    <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4 transition-all hover:border-amber-500/30">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <ShieldQuestion className="h-4 w-4 text-amber-500" />
            <span className="truncate text-xs font-bold text-foreground">{approval.tool_name}</span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <span className="font-mono text-[10px] text-muted-foreground">{approval.id}</span>
            <span className="rounded-full border border-border bg-background/60 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
              {kindLabel}
            </span>
          </div>
        </div>
        <Badge variant={approval.status === 'rejected' ? 'error' : approval.status === 'completed' ? 'success' : 'warning'}>
          {approval.status}
        </Badge>
      </div>

      <p className="mb-3 text-xs leading-5 text-foreground/80">{approval.reason}</p>

      {isQuestion && isPending && (
        <textarea
          value={response}
          onChange={(event) => setResponse(event.target.value)}
          className="mb-3 min-h-24 w-full resize-none rounded-xl border border-border bg-background/80 p-3 text-xs leading-5 text-foreground outline-none transition-all focus:border-primary"
          placeholder="Answer the Agent question..."
        />
      )}

      {approval.response && (
        <div className="mb-3 rounded-xl border border-primary/20 bg-primary/5 p-3 text-xs leading-5 text-foreground">
          {approval.response}
        </div>
      )}

      <div className="mb-3 grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-border bg-background/50 p-2">
          <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Access</div>
          <div className="mt-1 text-xs font-bold text-foreground">{approval.access_level}</div>
        </div>
        <div className="rounded-xl border border-border bg-background/50 p-2">
          <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Agent</div>
          <div className="mt-1 truncate font-mono text-xs text-foreground">{approval.agent_id}</div>
        </div>
      </div>

      <pre className="mb-3 max-h-28 overflow-auto rounded-xl border border-border bg-background/60 p-3 font-mono text-[11px] leading-5 text-muted-foreground">
        {args}
      </pre>

      {approval.result && (
        <pre className="mb-3 max-h-28 overflow-auto rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3 font-mono text-[11px] leading-5 text-emerald-600 dark:text-emerald-400">
          {approval.result}
        </pre>
      )}

      <div className="flex items-center gap-2">
        {isPending && (
          <>
            <button
              onClick={() => (isQuestion ? onAction('respond', response) : onAction('approve'))}
              disabled={busy || (isQuestion && !response.trim())}
              className="flex-1 rounded-xl bg-emerald-500 px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-white transition-all hover:bg-emerald-600 disabled:opacity-50"
            >
              {isQuestion ? 'Answer' : isPlan ? 'Confirm' : 'Approve'}
            </button>
            <button
              onClick={() => onAction('reject')}
              disabled={busy}
              className="flex-1 rounded-xl bg-rose-500 px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-white transition-all hover:bg-rose-600 disabled:opacity-50"
            >
              Reject
            </button>
          </>
        )}
        {isApproved && (
          <button
            onClick={() => onAction('resume', response)}
            disabled={busy}
            className="w-full rounded-xl bg-primary px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-white transition-all hover:bg-primary/90 disabled:opacity-50"
          >
            Resume Agent
          </button>
        )}
      </div>
    </div>
  )
}

async function streamClaudeApprovalResume(
  approval: ApprovalRequest,
  response: string | undefined,
  addLog: (log: { id: string; level: 'info' | 'warn' | 'error'; message: string; timestamp: number }) => void,
  addToolResult: (result: {
    id: string
    name: string
    args?: Record<string, unknown>
    result: unknown
    timestamp: number
  }) => void
) {
  const token = useAuthStore.getState().token
  const stream = await fetch(`/api/v1/approvals/${approval.id}/resume/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(response ? { response } : {}),
  })
  if (!stream.ok) throw new Error(`HTTP ${stream.status}`)

  const reader = stream.body?.getReader()
  if (!reader) throw new Error('No approval resume stream')

  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const text = decoder.decode(value, { stream: true })
    for (const line of text.split('\n')) {
      if (!line.startsWith('data: ')) continue
      const jsonStr = line.slice(6).trim()
      if (!jsonStr) continue

      const event = JSON.parse(jsonStr)
      if (event.type === 'delta' && event.delta) {
        addLog({
          id: '',
          level: 'info',
          message: `Claude resumed: ${String(event.delta).slice(0, 140)}`,
          timestamp: Date.now(),
        })
      } else if (event.type === 'tool_call') {
        addLog({
          id: '',
          level: 'info',
          message: `Claude calling tool: ${event.name}`,
          timestamp: Date.now(),
        })
      } else if (event.type === 'tool_result') {
        addToolResult({
          id: '',
          name: event.name,
          args: event.args,
          result: event.result,
          timestamp: Date.now(),
        })
      } else if (event.type === 'approval_request') {
        addLog({
          id: '',
          level: 'warn',
          message: `Claude requested another approval: ${event.reason}`,
          timestamp: Date.now(),
        })
      } else if (event.type === 'error') {
        addLog({
          id: '',
          level: 'error',
          message: event.message || event.error || 'Claude resume failed',
          timestamp: Date.now(),
        })
      }
    }
  }
}

function ToolResultCard({ result }: { result: { name: string; timestamp: number; result: unknown } }) {
  const display =
    typeof result.result === 'string'
      ? result.result
      : JSON.stringify(result.result, null, 2)

  return (
    <div className="bg-muted/30 rounded-2xl p-4 border border-border hover:border-primary/20 transition-all group overflow-hidden relative">
      <div className="absolute top-0 right-0 w-24 h-24 bg-primary/5 blur-2xl -z-10 rounded-full" />
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 bg-primary/10 rounded-lg flex items-center justify-center border border-primary/20">
            <Wrench className="h-3.5 w-3.5 text-primary" />
          </div>
          <span className="text-xs font-bold text-foreground tracking-tight">{result.name}</span>
        </div>
        <Badge variant="success">Completed</Badge>
      </div>
      <pre className="text-[11px] text-muted-foreground bg-background/50 rounded-xl p-3 overflow-auto max-h-40 font-mono border border-border leading-relaxed">
        {display.length > 500 ? display.slice(0, 500) + '...' : display}
      </pre>
      <div className="mt-3 flex items-center justify-between">
         <span className="text-[9px] text-muted-foreground/40 font-bold uppercase tracking-widest">
            {new Date(result.timestamp).toLocaleTimeString()}
         </span>
         <button className="text-[10px] text-primary font-bold hover:underline opacity-0 group-hover:opacity-100 transition-opacity">
            Copy Result
         </button>
      </div>
    </div>
  )
}

function LogIcon({ level }: { level: string }) {
  if (level === 'error') return <div className="w-2 h-2 rounded-full bg-rose-500 mt-1.5 shadow-sm shadow-rose-500/50" />
  if (level === 'warn') return <div className="w-2 h-2 rounded-full bg-amber-500 mt-1.5 shadow-sm shadow-amber-500/50" />
  return <div className="w-2 h-2 rounded-full bg-sky-500 mt-1.5 shadow-sm shadow-sky-500/50" />
}

function parentDir(path: string) {
  const parts = path.split('/').filter(Boolean)
  parts.pop()
  return parts.join('/')
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
