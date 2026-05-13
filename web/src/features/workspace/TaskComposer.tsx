import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2, Send, Sparkles, XCircle } from 'lucide-react'
import { api } from '@/shared/api/client'
import { PlanCard } from './PlanCard'

interface PlanStep {
  id: string
  action: string
  description: string
  params: Record<string, unknown>
  depends_on: string[]
}

interface WorkspacePlan {
  id: string
  workspace_id: string
  summary: string
  steps: PlanStep[]
  required_skills: string[]
  required_connectors: string[]
  sandbox_permissions: string[]
  expected_artifacts: string[]
  estimated_cost: string
  status: string
  created_at: string
}

interface ExecutionResult {
  task_id: string
  result?: string
  error?: string
}

interface ApplyResult {
  plan_id: string
  status: string
  created: Record<string, string[]>
  execution_results?: ExecutionResult[]
}

export function TaskComposer({
  workspaceId,
  onPlanApplied,
  onAgentCreated,
}: {
  workspaceId: string
  onPlanApplied?: (result: ApplyResult) => void
  onAgentCreated?: (agentId: string) => void
}) {
  const queryClient = useQueryClient()
  const [intent, setIntent] = useState('')
  const [plan, setPlan] = useState<WorkspacePlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [applyResult, setApplyResult] = useState<ApplyResult | null>(null)

  const createPlanMutation = useMutation({
    mutationFn: (intentText: string) =>
      api.post(`/workspaces/${workspaceId}/plans`, { intent: intentText }),
    onSuccess: (response) => {
      setPlan(response.data)
      setError(null)
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'Failed to generate plan')
    },
  })

  const applyPlanMutation = useMutation({
    mutationFn: (planId: string) =>
      api.post(`/workspaces/${workspaceId}/plans/${planId}/apply`),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['workspace-settings', workspaceId] })
      const result: ApplyResult = response.data
      setApplyResult(result)
      onPlanApplied?.(result)
      const createdAgents = result.created?.agents
      if (createdAgents?.length > 0) {
        onAgentCreated?.(createdAgents[0])
      }
      setPlan(null)
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'Failed to apply plan')
    },
  })

  const rejectPlanMutation = useMutation({
    mutationFn: (planId: string) =>
      api.post(`/workspaces/${workspaceId}/plans/${planId}/reject`),
    onSuccess: () => {
      setPlan(null)
    },
  })

  const handleSubmit = () => {
    if (!intent.trim()) return
    setError(null)
    createPlanMutation.mutate(intent.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="space-y-4">
      {/* Composer */}
      <div className="relative">
        <div className="absolute top-4 left-4 pointer-events-none">
          <Sparkles className="h-5 w-5 text-primary/30" />
        </div>
        <textarea
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe what you want done... (e.g. 'Create a daily report agent that summarizes our GitHub activity')"
          rows={3}
          className="w-full pl-12 pr-24 py-4 bg-card border border-border rounded-2xl text-sm text-foreground resize-none outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 placeholder:text-muted-foreground/40 shadow-sm"
          disabled={createPlanMutation.isPending}
        />
        <div className="absolute right-3 bottom-3">
          <button
            onClick={handleSubmit}
            disabled={!intent.trim() || createPlanMutation.isPending}
            className="h-9 px-4 rounded-xl bg-primary text-white hover:bg-primary/90 disabled:opacity-30 transition-all shadow-lg shadow-primary/20 flex items-center gap-2 text-xs font-bold"
          >
            {createPlanMutation.isPending ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Planning...
              </>
            ) : (
              <>
                <Send className="h-3.5 w-3.5" />
                Plan
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 rounded-xl border border-rose-500/20 bg-rose-500/5 text-xs text-rose-600">
          {error}
        </div>
      )}

      {/* Apply Result */}
      {applyResult && (
        <div className="p-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 space-y-3">
          <div className="flex items-center gap-2 text-xs font-bold text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            Plan applied successfully
          </div>
          <div className="space-y-1 text-[11px] text-foreground/70">
            {applyResult.created.agents?.length > 0 && (
              <div>Created {applyResult.created.agents.length} agent(s)</div>
            )}
            {applyResult.created.tasks?.length > 0 && (
              <div>Created {applyResult.created.tasks.length} task(s)</div>
            )}
            {applyResult.created.skills?.length > 0 && (
              <div>Installed {applyResult.created.skills.length} skill(s)</div>
            )}
            {applyResult.created.mcp_servers?.length > 0 && (
              <div>Configured {applyResult.created.mcp_servers.length} MCP server(s)</div>
            )}
          </div>
          {applyResult.execution_results && applyResult.execution_results.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-emerald-500/10">
              <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/50">
                Execution Results
              </div>
              {applyResult.execution_results.map((er, i) => (
                <div
                  key={er.task_id || i}
                  className="flex items-start gap-2 text-[11px]"
                >
                  {er.error ? (
                    <>
                      <XCircle className="h-3.5 w-3.5 text-rose-500 mt-0.5 shrink-0" />
                      <div>
                        <span className="font-bold text-rose-600">Task {er.task_id}: </span>
                        <span className="text-rose-500">{er.error}</span>
                      </div>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 mt-0.5 shrink-0" />
                      <div>
                        <span className="font-bold text-emerald-600">Task {er.task_id}: </span>
                        <span className="text-foreground/60 line-clamp-3">
                          {er.result || 'Completed'}
                        </span>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
          <button
            onClick={() => { setApplyResult(null); setIntent('') }}
            className="text-[11px] font-bold text-primary hover:underline"
          >
            Start over
          </button>
        </div>
      )}

      {/* Plan Card */}
      {plan && (
        <PlanCard
          plan={plan}
          onApply={() => applyPlanMutation.mutate(plan.id)}
          onReject={() => rejectPlanMutation.mutate(plan.id)}
          isApplying={applyPlanMutation.isPending}
        />
      )}
    </div>
  )
}
