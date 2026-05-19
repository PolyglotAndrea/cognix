import { Fragment, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, FileCode2, Pause, Play, Plus, RotateCw, Trash2, XCircle, type LucideIcon } from 'lucide-react'
import { api } from '@/shared/api/client'
import { Badge, Button, Input, Spinner } from '@/shared/ui'
import { useCurrentWorkspace } from '@/features/workspace/useCurrentWorkspace'

interface ScheduledTask {
  id: string
  name: string
  task_type: string
  schedule: string
  state: string
  run_count: number
  workspace_id?: string | null
  last_run?: string | null
}

interface WorkspaceWorkflow {
  id: string
  name: string
  description: string
  step_count: number
  errors: string[]
}

const DEFAULT_WORKFLOW = `name: Research Team
description: Sequential multi-agent research workflow.
steps:
  - id: research
    agent: researcher
    input: "{{ input }}"
    output: research
  - id: summarize
    agent: writer
    input: "{{ research }}"
    output: summary
`

export default function TaskList() {
  const queryClient = useQueryClient()
  const [showWorkflowForm, setShowWorkflowForm] = useState(false)
  const [workflowName, setWorkflowName] = useState('Research Team')
  const [workflowDefinition, setWorkflowDefinition] = useState(DEFAULT_WORKFLOW)
  const [runInput, setRunInput] = useState('Summarize the current workspace status.')
  const [runOutput, setRunOutput] = useState<Record<string, string>>({})
  const [taskRunOutput, setTaskRunOutput] = useState<Record<string, string>>({})

  const { workspace } = useCurrentWorkspace()

  const { data: tasks = [], isLoading: tasksLoading } = useQuery<ScheduledTask[]>({
    queryKey: ['tasks'],
    queryFn: () => api.get('/tasks').then((r) => r.data),
  })

  const { data: workflows = [], isLoading: workflowsLoading } = useQuery<WorkspaceWorkflow[]>({
    queryKey: ['workspace-workflows', workspace?.id],
    queryFn: () => api.get(`/workspaces/${workspace.id}/workflows`).then((r) => r.data),
    enabled: !!workspace,
  })

  const saveWorkflowMutation = useMutation({
    mutationFn: () =>
      api.post(`/workspaces/${workspace.id}/workflows`, {
        name: workflowName,
        definition: workflowDefinition,
      }),
    onSuccess: () => {
      setShowWorkflowForm(false)
      queryClient.invalidateQueries({ queryKey: ['workspace-workflows', workspace?.id] })
    },
  })

  const runWorkflowMutation = useMutation({
    mutationFn: (workflowId: string) =>
      api.post(`/workspaces/${workspace.id}/workflows/${workflowId}/run`, { input: runInput }),
    onSuccess: (response, workflowId) => {
      setRunOutput((current) => ({ ...current, [workflowId]: response.data.content || 'Completed.' }))
    },
  })

  const deleteWorkflowMutation = useMutation({
    mutationFn: (workflowId: string) => api.delete(`/workspaces/${workspace.id}/workflows/${workflowId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workspace-workflows', workspace?.id] }),
  })

  const triggerTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.post(`/tasks/${taskId}/trigger`),
    onSuccess: (response, taskId) => {
      setTaskRunOutput((current) => ({ ...current, [taskId]: formatTaskRunOutput(response.data) }))
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  const pauseTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.post(`/tasks/${taskId}/pause`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  })

  const resumeTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.post(`/tasks/${taskId}/resume`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  })

  const cancelTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.post(`/tasks/${taskId}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['tasks'] }),
  })

  const deleteTaskMutation = useMutation({
    mutationFn: (taskId: string) => api.delete(`/tasks/${taskId}`),
    onSuccess: (_, taskId) => {
      setTaskRunOutput((current) => {
        const next = { ...current }
        delete next[taskId]
        return next
      })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  return (
    <div className="space-y-8 animate-in fade-in duration-500 font-outfit">
      <div className="flex items-center justify-between gap-6">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">Agent Teams & Tasks</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Monitor scheduled jobs and define workspace-scoped multi-agent workflows.
          </p>
        </div>
        <Button onClick={() => setShowWorkflowForm((open) => !open)}>
          <Plus className="h-4 w-4" />
          Workflow
        </Button>
      </div>

      {showWorkflowForm && (
        <section className="rounded-2xl border border-border bg-card p-5 shadow-xl">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
            <div className="space-y-4">
              <Input value={workflowName} onChange={(event) => setWorkflowName(event.target.value)} />
              <Input value={runInput} onChange={(event) => setRunInput(event.target.value)} />
              <Button
                className="w-full"
                disabled={!workspace || !workflowName.trim() || !workflowDefinition.trim() || saveWorkflowMutation.isPending}
                onClick={() => saveWorkflowMutation.mutate()}
              >
                Save Workflow
              </Button>
            </div>
            <textarea
              value={workflowDefinition}
              onChange={(event) => setWorkflowDefinition(event.target.value)}
              rows={10}
              className="w-full resize-none rounded-xl border border-border bg-muted/50 px-4 py-3 font-mono text-xs leading-6 text-foreground outline-none transition-all focus:border-primary/40 focus:bg-background focus:ring-2 focus:ring-primary/20"
            />
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h3 className="text-sm font-bold text-foreground">Workspace Workflows</h3>
            <p className="text-[11px] text-muted-foreground">{workspace?.name || 'No workspace selected'}</p>
          </div>
          <Badge variant="primary">{workflows.length} definitions</Badge>
        </div>

        {workflowsLoading ? (
          <LoadingState text="Loading workflows..." />
        ) : workflows.length === 0 ? (
          <EmptyState icon={FileCode2} title="No Workflows" text="Create a YAML workflow to coordinate multiple agents." />
        ) : (
          <div className="divide-y divide-border">
            {workflows.map((workflow) => (
              <div key={workflow.id} className="px-6 py-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-sm font-bold text-foreground">{workflow.name}</h4>
                      <Badge variant={workflow.errors.length ? 'error' : 'success'}>
                        {workflow.errors.length ? 'Invalid' : `${workflow.step_count} steps`}
                      </Badge>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      {workflow.description || workflow.id}
                    </p>
                    {workflow.errors.length > 0 && (
                      <p className="mt-2 text-xs font-medium text-rose-500">{workflow.errors.join(', ')}</p>
                    )}
                    {runOutput[workflow.id] && (
                      <pre className="mt-3 max-h-32 overflow-auto rounded-xl border border-border bg-muted/50 p-3 text-xs text-muted-foreground">
                        {runOutput[workflow.id]}
                      </pre>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      onClick={() => runWorkflowMutation.mutate(workflow.id)}
                      disabled={workflow.errors.length > 0 || runWorkflowMutation.isPending}
                      className="flex h-9 w-9 items-center justify-center rounded-xl border border-transparent text-muted-foreground transition-all hover:border-emerald-500/20 hover:bg-emerald-500/10 hover:text-emerald-500 disabled:opacity-40"
                      aria-label={`Run ${workflow.name}`}
                    >
                      <Play className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => deleteWorkflowMutation.mutate(workflow.id)}
                      disabled={deleteWorkflowMutation.isPending}
                      className="flex h-9 w-9 items-center justify-center rounded-xl border border-transparent text-muted-foreground transition-all hover:border-rose-500/20 hover:bg-rose-500/10 hover:text-rose-500 disabled:opacity-40"
                      aria-label={`Delete ${workflow.name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-border bg-card">
        <div className="border-b border-border px-6 py-4">
          <h3 className="text-sm font-bold text-foreground">Scheduled Tasks</h3>
          <p className="text-[11px] text-muted-foreground">APScheduler-backed recurring and one-shot jobs</p>
        </div>

        {tasksLoading ? (
          <LoadingState text="Synchronizing task scheduler..." />
        ) : tasks.length === 0 ? (
          <EmptyState icon={Clock} title="No Scheduled Tasks" text="Create one-shot or recurring task schedules through the API or CLI." />
        ) : (
          <div className="overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Schedule</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Runs</TableHead>
                  <TableHead align="right">Actions</TableHead>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {tasks.map((task) => (
                  <Fragment key={task.id}>
                    <tr className="group transition-colors hover:bg-muted/30">
                      <td className="px-6 py-5">
                        <div className="flex items-center gap-4">
                          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-muted transition-colors group-hover:border-primary/30">
                            <Clock className="h-5 w-5 text-primary/70 group-hover:text-primary" />
                          </div>
                          <div className="min-w-0">
                            <span className="block truncate font-bold text-foreground transition-colors group-hover:text-primary">
                              {task.name}
                            </span>
                            {task.last_run && (
                              <span className="mt-1 block text-[11px] text-muted-foreground">
                                Last run {new Date(task.last_run).toLocaleString()}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-5"><Badge>{task.task_type}</Badge></td>
                      <td className="px-6 py-5 font-mono text-sm font-medium text-muted-foreground">{task.schedule}</td>
                      <td className="px-6 py-5">
                        <Badge variant={task.state === 'active' ? 'success' : task.state === 'paused' ? 'warning' : task.state === 'canceled' ? 'error' : 'default'}>
                          {task.state}
                        </Badge>
                      </td>
                      <td className="px-6 py-5 text-sm font-bold text-foreground">{task.run_count}</td>
                      <td className="px-6 py-5 text-right">
                        <div className="flex items-center justify-end gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                          <IconButton
                            icon={RotateCw}
                            label={`Trigger ${task.name}`}
                            onClick={() => triggerTaskMutation.mutate(task.id)}
                            disabled={task.state === 'canceled' || triggerTaskMutation.isPending}
                          />
                          <IconButton
                            icon={task.state === 'active' ? Pause : Play}
                            label={task.state === 'active' ? `Pause ${task.name}` : `Resume ${task.name}`}
                            onClick={() =>
                              task.state === 'active'
                                ? pauseTaskMutation.mutate(task.id)
                                : resumeTaskMutation.mutate(task.id)
                            }
                            disabled={
                              task.state === 'canceled'
                              || pauseTaskMutation.isPending
                              || resumeTaskMutation.isPending
                            }
                          />
                          <IconButton
                            icon={XCircle}
                            label={`Cancel ${task.name}`}
                            onClick={() => cancelTaskMutation.mutate(task.id)}
                            disabled={
                              task.state === 'canceled'
                              || task.state === 'failed'
                              || task.state === 'completed'
                              || cancelTaskMutation.isPending
                            }
                            danger
                          />
                          <IconButton
                            icon={Trash2}
                            label={`Delete ${task.name}`}
                            onClick={() => deleteTaskMutation.mutate(task.id)}
                            disabled={deleteTaskMutation.isPending}
                            danger
                          />
                        </div>
                      </td>
                    </tr>
                    {taskRunOutput[task.id] && (
                      <tr key={`${task.id}-output`} className="border-t border-border/60 bg-muted/20">
                        <td colSpan={6} className="px-6 py-4">
                          <pre className="max-h-44 overflow-auto rounded-xl border border-border bg-background p-3 text-xs leading-6 text-muted-foreground">
                            {taskRunOutput[task.id]}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function TableHead({ children, align = 'left' }: { children: React.ReactNode; align?: 'left' | 'right' }) {
  return (
    <th
      className={`px-6 py-4 text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground ${
        align === 'right' ? 'text-right' : 'text-left'
      }`}
    >
      {children}
    </th>
  )
}

function LoadingState({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20">
      <Spinner />
      <p className="mt-4 text-sm font-medium text-muted-foreground">{text}</p>
    </div>
  )
}

function EmptyState({
  icon: Icon,
  title,
  text,
}: {
  icon: LucideIcon
  title: string
  text: string
}) {
  return (
    <div className="py-20 text-center">
      <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-border bg-muted">
        <Icon className="h-8 w-8 text-muted-foreground/25" />
      </div>
      <h3 className="text-lg font-bold text-foreground">{title}</h3>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{text}</p>
    </div>
  )
}

function IconButton({
  icon: Icon,
  label,
  onClick,
  disabled = false,
  danger = false,
}: {
  icon: LucideIcon
  label: string
  onClick: () => void
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex h-9 w-9 items-center justify-center rounded-xl border border-transparent text-muted-foreground transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
        danger
          ? 'hover:border-rose-500/20 hover:bg-rose-500/10 hover:text-rose-500'
          : 'hover:border-primary/20 hover:bg-primary/10 hover:text-primary'
      }`}
      aria-label={label}
      title={label}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}

function formatTaskRunOutput(run: unknown) {
  if (!run || typeof run !== 'object') return String(run ?? 'Completed.')

  const data = run as Record<string, unknown>
  const result = data.result
  if (typeof result === 'string') return result
  if (result) return JSON.stringify(result, null, 2)
  return JSON.stringify(data, null, 2)
}
