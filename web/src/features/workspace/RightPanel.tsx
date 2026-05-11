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
  Zap,
  ChevronRight,
  ChevronLeft,
  ShieldQuestion,
  ShieldCheck,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { useWorkspaceStore } from './store'
import { Panel, PanelHeader, PanelBody, Badge } from '@/shared/ui'
import { TaskDetailModal } from './TaskDetailModal'

const TABS = [
  { key: 'approvals' as const, label: 'Approval', icon: ShieldQuestion, color: 'text-amber-500' },
  { key: 'tasks' as const, label: 'Tasks', icon: Clock, color: 'text-blue-500' },
  { key: 'files' as const, label: 'Files', icon: Folder, color: 'text-indigo-500' },
  { key: 'events' as const, label: 'Events', icon: Activity, color: 'text-rose-500' },
  { key: 'results' as const, label: 'Results', icon: Wrench, color: 'text-emerald-500' },
  { key: 'logs' as const, label: 'Logs', icon: Terminal, color: 'text-slate-500' },
  { key: 'json' as const, label: 'JSON', icon: FileJson, color: 'text-purple-500' },
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
  const [selectedTask, setSelectedTask] = useState<TaskSummary | null>(null)
  
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
    <Panel className="w-80 shrink-0 border-l border-border bg-card/50 backdrop-blur-xl h-full flex flex-col shadow-2xl">
      <PanelHeader dragHandleProps={dragHandleProps} className="justify-between px-4 h-14 border-b border-border/50 shrink-0">
        <div className="flex bg-muted/50 p-1 rounded-xl border border-border/50 overflow-x-auto scrollbar-hide max-w-[230px] shadow-inner">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setRightPanelTab(tab.key)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all shrink-0 ${
                rightPanelTab === tab.key
                  ? 'bg-background text-foreground shadow-sm ring-1 ring-border'
                  : 'text-muted-foreground hover:text-foreground hover:bg-background/50'
              }`}
            >
              <tab.icon className={`h-3.5 w-3.5 ${rightPanelTab === tab.key ? tab.color : 'text-current'}`} />
              {tab.label}
            </button>
          ))}
        </div>
        <button onClick={toggleRightPanel} className="p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all shrink-0">
          <ChevronRight className="h-4 w-4" />
        </button>
      </PanelHeader>

      <PanelBody className="flex-1 overflow-hidden p-0 bg-transparent">
        <div className="h-full overflow-y-auto scrollbar-hide">
        {/* Approvals Tab */}
        {rightPanelTab === 'approvals' && (
          <div className="p-4 space-y-3">
            {approvalsLoading ? (
              <div className="py-20 text-center">
                <ShieldQuestion className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
                <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Loading Requests</p>
              </div>
            ) : approvals.length === 0 ? (
              <EmptyState icon={ShieldCheck} title="No Approval Requests" description="Your approval queue is clear. No pending tool or question requests." />
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
              <EmptyState icon={Clock} title="No Active Tasks" description="There are no scheduled tasks or background processes running currently." />
            ) : (
              tasks.map((task) => (
                <TaskStatusCard
                  key={task.id}
                  task={task}
                  onClick={() => setSelectedTask(task)}
                />
              ))
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
              <EmptyState icon={Folder} title="No Files Found" description="The current directory is empty or no files have been generated by the agent yet." />
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
              <EmptyState icon={Activity} title="No Events Recorded" description="Live event stream is currently empty. Start an agent run to see real-time updates." />
            ) : (
              [...events].reverse().map((event, index) => {
                const isError = event.type?.toLowerCase().includes('error') || event.level === 'error'
                const isTool = event.type?.toLowerCase().includes('tool')
                const isAgent = event.type?.toLowerCase().includes('agent')
                
                return (
                  <div key={`${event.timestamp}-${index}`} className="group bg-card/40 border border-border hover:border-primary/20 rounded-xl p-3 transition-all duration-200">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-1.5 h-1.5 rounded-full ${isError ? 'bg-rose-500 animate-pulse' : isTool ? 'bg-indigo-500' : isAgent ? 'bg-emerald-500' : 'bg-primary'}`} />
                        <span className="text-[10px] font-black uppercase tracking-widest text-foreground/70">{event.type}</span>
                      </div>
                      <span className="font-mono text-[9px] text-muted-foreground/50">
                        {new Date(event.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                    </div>
                    
                    {event.provider && (
                      <div className="flex items-center gap-2 mb-2 px-1.5 py-0.5 rounded-md bg-muted/50 w-fit border border-border/50">
                        <Zap className="h-2.5 w-2.5 text-primary" />
                        <span className="text-[9px] font-bold text-muted-foreground uppercase">{event.provider}</span>
                        {event.agent_id && (
                          <>
                            <span className="text-muted-foreground/30">|</span>
                            <span className="text-[9px] font-bold text-primary/80 uppercase">{event.agent_id}</span>
                          </>
                        )}
                      </div>
                    )}
                    
                    <p className={`text-[11px] leading-relaxed break-words ${isError ? 'text-rose-500/90 font-medium' : 'text-foreground/80'}`}>
                      {String(event.message || event.response || JSON.stringify(event))}
                    </p>
                  </div>
                )
              })
            )}
          </div>
        )}

        {/* Results Tab */}
        {rightPanelTab === 'results' && (
          <div className="p-4 space-y-3">
            {toolResults.length === 0 ? (
              <EmptyState icon={Wrench} title="No Tool Results" description="No results from tool executions have been captured in this session." />
            ) : (
              toolResults.map((r) => <ToolResultCard key={r.id} result={r} />)
            )}
          </div>
        )}

        {/* Logs Tab */}
        {rightPanelTab === 'logs' && (
          <div className="p-4 space-y-2 font-mono text-[11px]">
            {executionLogs.length === 0 ? (
              <EmptyState icon={Terminal} title="No Execution Logs" description="The agent has not produced any system or execution logs yet." />
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
              <EmptyState icon={FileJson} title="No Data Export" description="There is no tool execution data to export as JSON yet." />
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
        </div>
      </PanelBody>

      {selectedTask && (
        <TaskDetailModal
          isOpen={!!selectedTask}
          onClose={() => setSelectedTask(null)}
          task={selectedTask}
        />
      )}
    </Panel>
  )
}

function EmptyState({ icon: Icon, title, description }: { icon: any, title: string, description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-6 text-center animate-in fade-in zoom-in-95 duration-500">
      <div className="relative mb-6">
        <div className="absolute inset-0 bg-primary/10 blur-3xl rounded-full scale-150 animate-pulse" />
        <div className="relative w-20 h-20 bg-card/80 backdrop-blur-xl border border-border rounded-[2.5rem] flex items-center justify-center shadow-2xl group overflow-hidden">
           <div className="absolute inset-0 bg-gradient-to-tr from-primary/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
           <Icon className="h-9 w-9 text-muted-foreground/30 group-hover:text-primary/40 transition-colors group-hover:scale-110 duration-500" />
        </div>
      </div>
      <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-foreground mb-2">{title}</h3>
      {description && <p className="text-xs text-muted-foreground max-w-[200px] leading-relaxed font-medium">{description}</p>}
    </div>
  )
}

function TaskStatusCard({ task, onClick }: { task: TaskSummary; onClick?: () => void }) {
  const latestRun = task.runs[0]
  const hasError = latestRun?.status === 'failure' || !!latestRun?.error || task.state === 'failed'

  return (
    <div
      className="group bg-card/40 hover:bg-card border border-border hover:border-primary/20 rounded-2xl p-4 transition-all duration-300 shadow-sm hover:shadow-md cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <div className="text-sm font-bold text-foreground truncate group-hover:text-primary transition-colors">{task.name}</div>
          <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground font-bold uppercase tracking-wider">
            <span className="flex items-center gap-1">
              <Zap className="h-3 w-3" />
              {task.task_type}
            </span>
            <span className="w-1 h-1 rounded-full bg-border" />
            <span className="flex items-center gap-1 text-muted-foreground/60">
              <Clock className="h-3 w-3" />
              {task.schedule}
            </span>
          </div>
        </div>
        <div className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border transition-all ${
          task.state === 'active' 
            ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' 
            : task.state === 'paused' 
            ? 'bg-amber-500/10 text-amber-500 border-amber-500/20'
            : 'bg-muted text-muted-foreground border-border'
        }`}>
          {task.state}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="rounded-xl border border-border bg-background/30 p-3 hover:bg-background/50 transition-colors">
          <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Execution Count</div>
          <div className="text-xl font-black text-foreground tabular-nums">{task.run_count}</div>
        </div>
        <div className="rounded-xl border border-border bg-background/30 p-3 hover:bg-background/50 transition-colors">
          <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Last Status</div>
          <div className="flex items-center gap-2 text-xs font-bold text-foreground">
            {hasError ? (
              <div className="w-5 h-5 rounded-lg bg-rose-500/10 flex items-center justify-center">
                <AlertCircle className="h-3.5 w-3.5 text-rose-500" />
              </div>
            ) : latestRun ? (
              <div className="w-5 h-5 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
              </div>
            ) : (
              <div className="w-5 h-5 rounded-lg bg-muted flex items-center justify-center">
                <PlayCircle className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
            )}
            <span className="capitalize">{latestRun?.status || 'idle'}</span>
          </div>
        </div>
      </div>

      {latestRun && (
        <div className="relative group/console">
          <div className="absolute top-2 right-2 opacity-0 group-hover/console:opacity-100 transition-opacity">
            <Badge variant="default" className="text-[8px]">LOG</Badge>
          </div>
          <pre className="text-[10px] text-muted-foreground bg-muted/30 hover:bg-muted/50 rounded-xl p-3 overflow-auto max-h-32 font-mono border border-border/50 leading-relaxed scrollbar-hide transition-colors">
            {(latestRun.error || latestRun.result || 'No output recorded.').slice(0, 500)}
          </pre>
        </div>
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
  const isClaude = approval.metadata?.runtime === 'claude-agent-sdk'
  const args = JSON.stringify(approval.arguments || {}, null, 2)
  const kindLabel = isQuestion ? 'Question' : isPlan ? 'Plan' : 'Tool'
  const statusLabel = approvalStatusLabel(approval, busy)
  const primaryLabel = isQuestion ? 'Answer' : isPlan ? 'Confirm Plan' : 'Approve Tool'
  
  return (
    <div className={`rounded-2xl border transition-all duration-300 p-4 shadow-sm hover:shadow-md ${
      isPending 
        ? 'border-amber-500/30 bg-amber-500/5 ring-1 ring-amber-500/10' 
        : 'border-border bg-card/40'
    }`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <div className={`p-1.5 rounded-lg ${isPlan ? 'bg-indigo-500/10 text-indigo-500' : 'bg-amber-500/10 text-amber-500'}`}>
              {isPlan ? <ShieldCheck className="h-4 w-4" /> : <ShieldQuestion className="h-4 w-4" />}
            </div>
            <span className="truncate text-sm font-bold text-foreground">{approval.tool_name}</span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-border">{approval.id}</span>
            <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground/60">
              {kindLabel}
            </span>
          </div>
        </div>
        <div className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border ${
          approval.status === 'pending' ? 'bg-amber-500/10 text-amber-500 border-amber-500/20' :
          approval.status === 'approved' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' :
          'bg-muted text-muted-foreground border-border'
        }`}>
          {approval.status}
        </div>
      </div>

      <div className="mb-4 p-3 rounded-xl bg-background/50 border border-border/50">
        <div className="flex items-center gap-2 mb-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
          <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/80">{statusLabel}</div>
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">{approval.reason}</p>
      </div>

      {isQuestion && isPending && (
        <div className="mb-4">
          <textarea
            value={response}
            onChange={(event) => setResponse(event.target.value)}
            className="min-h-24 w-full resize-none rounded-xl border border-border bg-background/80 p-3 text-xs leading-5 text-foreground outline-none transition-all focus:ring-2 focus:ring-primary/20 focus:border-primary shadow-inner"
            placeholder="Provide the information requested..."
          />
        </div>
      )}

      {!isPending && (approval.response || approval.result) && (
        <div className="mb-4 space-y-2">
          {approval.response && (
            <div className="p-3 rounded-xl bg-primary/5 border border-primary/10 text-xs text-primary font-medium">
              <span className="text-[9px] font-black uppercase tracking-widest block mb-1 opacity-60">Human Response</span>
              {approval.response}
            </div>
          )}
          {approval.result && (
            <pre className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/10 text-[10px] font-mono text-emerald-600 dark:text-emerald-400 overflow-auto max-h-32 scrollbar-hide">
              <span className="text-[9px] font-black uppercase tracking-widest block mb-1 opacity-60">Result</span>
              {approval.result}
            </pre>
          )}
        </div>
      )}

      {isPending && (
        <pre className="mb-4 max-h-32 overflow-auto rounded-xl border border-border bg-muted/30 p-3 font-mono text-[10px] leading-relaxed text-muted-foreground scrollbar-hide">
          <div className="text-[9px] font-black uppercase tracking-widest mb-1 opacity-60 border-b border-border/50 pb-1">Parameters</div>
          {args}
        </pre>
      )}

      <div className="flex items-center gap-2 mt-2">
        {isPending ? (
          <>
            <button
              onClick={() => (isQuestion ? onAction('respond', response) : onAction('approve'))}
              disabled={busy || (isQuestion && !response.trim())}
              className="flex-1 h-9 rounded-xl bg-emerald-500 px-3 text-[11px] font-bold uppercase tracking-wider text-white transition-all hover:bg-emerald-600 active:scale-95 disabled:opacity-50 shadow-lg shadow-emerald-500/20"
            >
              {primaryLabel}
            </button>
            <button
              onClick={() => onAction('reject')}
              disabled={busy}
              className="flex-1 h-9 rounded-xl bg-rose-500 px-3 text-[11px] font-bold uppercase tracking-wider text-white transition-all hover:bg-rose-600 active:scale-95 disabled:opacity-50 shadow-lg shadow-rose-500/20"
            >
              Reject
            </button>
          </>
        ) : isApproved && (
          <button
            onClick={() => onAction('resume', response)}
            disabled={busy}
            className="w-full h-9 rounded-xl bg-primary px-3 text-[11px] font-bold uppercase tracking-wider text-white transition-all hover:bg-primary/90 active:scale-95 disabled:opacity-50 shadow-lg shadow-primary/20"
          >
            {busy ? 'Resuming...' : isClaude ? 'Resume Claude Session' : 'Continue Execution'}
          </button>
        )}
      </div>
    </div>
  )
}

function approvalStatusLabel(approval: ApprovalRequest, busy: boolean) {
  if (busy && approval.status === 'approved') return 'Continuing task from approval checkpoint'
  if (approval.status === 'completed') return 'Continuation completed'
  if (approval.status === 'rejected') return 'Rejected by human reviewer'
  if (approval.status === 'approved') return 'Approved and ready to resume'
  if (approval.kind === 'question') return 'Waiting for human answer'
  if (approval.kind === 'plan_confirmation') return 'Waiting for plan confirmation'
  return 'Waiting for tool permission'
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
