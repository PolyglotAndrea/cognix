import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Send, Sparkles } from 'lucide-react'
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

export function TaskComposer({
  workspaceId,
  onPlanApplied,
}: {
  workspaceId: string
  onPlanApplied?: (result: { plan_id: string; status: string; created: Record<string, string[]> }) => void
}) {
  const queryClient = useQueryClient()
  const [intent, setIntent] = useState('')
  const [plan, setPlan] = useState<WorkspacePlan | null>(null)
  const [error, setError] = useState<string | null>(null)

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
      onPlanApplied?.(response.data)
      setPlan(null)
      setIntent('')
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
