import {
  Bot,
  Clock,
  Cpu,
  FileText,
  Loader2,
  Play,
  Puzzle,
  Shield,
  X,
  Zap,
} from 'lucide-react'

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

const ACTION_ICONS: Record<string, typeof Bot> = {
  create_agent: Bot,
  create_task: Clock,
  install_skill: Puzzle,
  configure_mcp: Cpu,
}

const ACTION_COLORS: Record<string, string> = {
  create_agent: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  create_task: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  install_skill: 'text-violet-500 bg-violet-500/10 border-violet-500/20',
  configure_mcp: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
}

const COST_COLORS: Record<string, string> = {
  low: 'text-emerald-500',
  medium: 'text-amber-500',
  high: 'text-rose-500',
}

export function PlanCard({
  plan,
  onApply,
  onReject,
  isApplying,
}: {
  plan: WorkspacePlan
  onApply: () => void
  onReject: () => void
  isApplying: boolean
}) {
  return (
    <div className="rounded-2xl border border-border bg-card shadow-lg overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-300">
      {/* Header */}
      <div className="px-6 py-4 bg-gradient-to-r from-primary/5 to-transparent border-b border-border">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Zap className="h-4 w-4 text-primary" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-primary">
                Execution Plan
              </span>
            </div>
            <p className="text-sm font-semibold text-foreground">{plan.summary}</p>
          </div>
          <span
            className={`text-xs font-bold font-mono ${
              COST_COLORS[plan.estimated_cost] || 'text-muted-foreground'
            }`}
          >
            ~{plan.estimated_cost} cost
          </span>
        </div>
      </div>

      {/* Steps */}
      <div className="px-6 py-4 space-y-3">
        <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
          Steps
        </h4>
        {plan.steps.map((step, i) => {
          const Icon = ACTION_ICONS[step.action] || FileText
          const colorClass = ACTION_COLORS[step.action] || 'text-muted-foreground bg-muted border-border'
          return (
            <div key={step.id} className="flex items-start gap-3">
              <div className="flex flex-col items-center gap-1 mt-0.5">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center border ${colorClass}`}>
                  <Icon className="h-3.5 w-3.5" />
                </div>
                {i < plan.steps.length - 1 && (
                  <div className="w-px h-4 bg-border" />
                )}
              </div>
              <div className="flex-1 min-w-0 pb-1">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-muted-foreground/40">
                    {step.id}
                  </span>
                  <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${colorClass}`}>
                    {step.action.replace('_', ' ')}
                  </span>
                </div>
                <p className="text-xs text-foreground mt-0.5">{step.description}</p>
              </div>
            </div>
          )
        })}
      </div>

      {/* Permissions & Artifacts */}
      {(plan.sandbox_permissions.length > 0 || plan.expected_artifacts.length > 0) && (
        <div className="px-6 py-3 border-t border-border/50 bg-muted/20 space-y-2">
          {plan.sandbox_permissions.length > 0 && (
            <div className="flex items-center gap-2">
              <Shield className="h-3 w-3 text-muted-foreground/40" />
              <span className="text-[10px] text-muted-foreground">
                Access: {plan.sandbox_permissions.join(', ')}
              </span>
            </div>
          )}
          {plan.expected_artifacts.length > 0 && (
            <div className="flex items-center gap-2">
              <FileText className="h-3 w-3 text-muted-foreground/40" />
              <span className="text-[10px] text-muted-foreground">
                Outputs: {plan.expected_artifacts.join(', ')}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="px-6 py-4 border-t border-border flex items-center gap-3">
        <button
          onClick={onApply}
          disabled={isApplying}
          className="flex-1 h-10 rounded-xl bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-all shadow-lg shadow-primary/20 flex items-center justify-center gap-2 text-xs font-bold"
        >
          {isApplying ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Applying...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              Apply & Run
            </>
          )}
        </button>
        <button
          onClick={onReject}
          disabled={isApplying}
          className="h-10 px-4 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-all flex items-center gap-2 text-xs font-bold"
        >
          <X className="h-4 w-4" />
          Reject
        </button>
      </div>
    </div>
  )
}
