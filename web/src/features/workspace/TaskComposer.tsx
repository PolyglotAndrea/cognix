import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2, Send, Sparkles, XCircle } from 'lucide-react'
import { api } from '@/shared/api/client'
import { PlanCard } from './PlanCard'
import { useWorkspaceStore } from './store'
import type { WorkspacePlan, ApplyResult } from './types'

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
  const [applyingPlanId, setApplyingPlanId] = useState<string | null>(null)

  // Poll plan status during execution for step-by-step progress
  const { data: polledPlan } = useQuery<WorkspacePlan>({
    queryKey: ['plan-status', workspaceId, applyingPlanId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/plans/${applyingPlanId}`).then((r) => r.data),
    enabled: !!applyingPlanId && !!workspaceId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'executing' ? 500 : false
    },
  })

  // Update plan with polled data for live step progress
  const lastPolledRef = useRef<WorkspacePlan | null>(null)
  useEffect(() => {
    if (polledPlan && applyingPlanId) {
      lastPolledRef.current = polledPlan
      setPlan(polledPlan)
      if (polledPlan.status === 'applied' || polledPlan.status === 'failed') {
        setApplyingPlanId(null)
      }
    }
  }, [polledPlan, applyingPlanId])

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
    mutationFn: (planId: string) => {
      setApplyingPlanId(planId)
      return api.post(`/workspaces/${workspaceId}/plans/${planId}/apply`)
    },
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['agents', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-settings', workspaceId] })
      const result: ApplyResult = response.data
      setApplyResult(result)
      if (result.plan) {
        setPlan(result.plan)
      }
      onPlanApplied?.(result)
      const createdAgents = result.created?.agents
      if (createdAgents?.length > 0) {
        onAgentCreated?.(createdAgents[0])
      }
      if (result.artifacts && result.artifacts.length > 0) {
        const workspaceStore = useWorkspaceStore.getState()
        workspaceStore.setRightPanelTab('artifacts')
        workspaceStore.setRightPanelOpen(true)
      }
      setApplyingPlanId(null)
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'Failed to apply plan')
      setApplyingPlanId(null)
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
        <div className={`p-4 rounded-xl border space-y-3 ${
          applyResult.status === 'failed'
            ? 'border-rose-500/20 bg-rose-500/5'
            : 'border-emerald-500/20 bg-emerald-500/5'
        }`}>
          <div className={`flex items-center gap-2 text-xs font-bold ${
            applyResult.status === 'failed' ? 'text-rose-700' : 'text-emerald-700'
          }`}>
            {applyResult.status === 'failed' ? (
              <XCircle className="h-4 w-4" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )}
            {applyResult.status === 'failed' ? 'Plan applied with failures' : 'Plan applied successfully'}
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
                  {er.error || er.status === 'failure' ? (
                    <>
                      <XCircle className="h-3.5 w-3.5 text-rose-500 mt-0.5 shrink-0" />
                      <div>
                        <span className="font-bold text-rose-600">Task {er.task_id}: </span>
                        <span className="text-rose-500">{er.error || 'Execution failed'}</span>
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
          {applyResult.artifacts && applyResult.artifacts.length > 0 && (
            <div className="pt-2 border-t border-emerald-500/10">
              <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/50 mb-1">
                Artifacts
              </div>
              <div className="text-[11px] text-foreground/60">
                {applyResult.artifacts.length} artifact(s) saved — view in Artifacts panel
              </div>
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
          isApplying={applyPlanMutation.isPending || !!applyingPlanId}
        />
      )}
    </div>
  )
}
