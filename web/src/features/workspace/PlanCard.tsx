import {
  Bot,
  CheckCircle2,
  Clock,
  Cpu,
  FileText,
  Loader2,
  Play,
  Puzzle,
  Shield,
  X,
  XCircle,
  Zap,
} from 'lucide-react'
import type { WorkspacePlan } from './types'

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
  const stepStatuses = plan.step_statuses || {}
  const isExecuting = plan.status === 'executing' || isApplying
  const recommendedAgents = plan.recommended_agents || []
  const recommendedSkills = plan.recommended_skills || []
  const recommendedMcpTools = plan.recommended_mcp_tools || []
  const scheduling = plan.scheduling || {}
  const capabilitySnapshot = plan.capability_snapshot || {}
  const provider = (capabilitySnapshot.provider || {}) as Record<string, unknown>
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
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <PlanPill label={plan.intent_type || 'task'} />
              <PlanPill label={plan.execution_mode || 'once'} />
              {Boolean(provider.default_model) && <PlanPill label={String(provider.default_model)} muted />}
            </div>
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

      {/* Planner Decisions */}
      {(recommendedAgents.length > 0 || recommendedSkills.length > 0 || recommendedMcpTools.length > 0 || Boolean(scheduling.needed)) && (
        <div className="px-6 py-4 border-b border-border/50 bg-muted/10 grid grid-cols-1 gap-3">
          {recommendedAgents.length > 0 && (
            <DecisionRow
              icon={Bot}
              label="Agents"
              value={recommendedAgents
                .map((agent) => String(agent.name || agent.role || 'agent'))
                .join(', ')}
            />
          )}
          {recommendedSkills.length > 0 && (
            <DecisionRow
              icon={Puzzle}
              label="Skills"
              value={recommendedSkills
                .map((skill) => `${String(skill.name || 'skill')}${skill.available === false ? ' (recommended)' : ''}`)
                .join(', ')}
            />
          )}
          {recommendedMcpTools.length > 0 && (
            <DecisionRow
              icon={Cpu}
              label="MCP"
              value={recommendedMcpTools
                .map((tool) => `${String(tool.server || 'mcp')}/${String(tool.tool || 'tool')}`)
                .join(', ')}
            />
          )}
          {Boolean(scheduling.needed) && (
            <DecisionRow
              icon={Clock}
              label="Schedule"
              value={`${String(scheduling.kind || 'scheduled')} ${String(scheduling.expression || '')}`.trim()}
            />
          )}
        </div>
      )}

      {/* Steps */}
      <div className="px-6 py-4 space-y-3">
        <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">
          Steps
        </h4>
        {plan.steps.map((step, i) => {
          const Icon = ACTION_ICONS[step.action] || FileText
          const colorClass = ACTION_COLORS[step.action] || 'text-muted-foreground bg-muted border-border'
          const stepStatus = stepStatuses[step.id]
          const isStepExecuting = stepStatus === 'executing'
          const isStepCompleted = stepStatus === 'completed'
          const isStepFailed = stepStatus === 'failed'
          return (
            <div key={step.id} className="flex items-start gap-3">
              <div className="flex flex-col items-center gap-1 mt-0.5">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center border ${
                  isStepCompleted ? 'bg-emerald-500/10 border-emerald-500/20' :
                  isStepFailed ? 'bg-rose-500/10 border-rose-500/20' :
                  isStepExecuting ? 'bg-primary/10 border-primary/20' :
                  colorClass
                }`}>
                  {isStepCompleted ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> :
                   isStepFailed ? <XCircle className="h-3.5 w-3.5 text-rose-500" /> :
                   isStepExecuting ? <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" /> :
                   <Icon className={`h-3.5 w-3.5 ${isExecuting ? 'text-muted-foreground/30' : ''}`} />}
                </div>
                {i < plan.steps.length - 1 && (
                  <div className={`w-px h-4 ${isStepCompleted ? 'bg-emerald-500/30' : 'bg-border'}`} />
                )}
              </div>
              <div className="flex-1 min-w-0 pb-1">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-muted-foreground/40">
                    {step.id}
                  </span>
                  <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border ${
                    isStepCompleted ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20' :
                    isStepFailed ? 'text-rose-500 bg-rose-500/10 border-rose-500/20' :
                    isStepExecuting ? 'text-primary bg-primary/10 border-primary/20' :
                    colorClass
                  }`}>
                    {step.action.replace('_', ' ')}
                  </span>
                </div>
                <p className={`text-xs mt-0.5 ${isStepCompleted || isStepFailed ? 'text-foreground' : isExecuting ? 'text-foreground' : 'text-foreground'}`}>{step.description}</p>
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
        {plan.status === 'applied' ? (
          <div className="flex-1 h-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center gap-2 text-xs font-bold border border-emerald-500/20">
            <CheckCircle2 className="h-4 w-4" />
            Applied Successfully
          </div>
        ) : plan.status === 'failed' ? (
          <div className="flex-1 h-10 rounded-xl bg-rose-500/10 text-rose-500 flex items-center justify-center gap-2 text-xs font-bold border border-rose-500/20">
            <XCircle className="h-4 w-4" />
            Execution Failed
          </div>
        ) : (
          <>
            <button
              onClick={onApply}
              disabled={isExecuting}
              className="flex-1 h-10 rounded-xl bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-all shadow-lg shadow-primary/20 flex items-center justify-center gap-2 text-xs font-bold"
            >
              {isExecuting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Executing...
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
              disabled={isExecuting}
              className="h-10 px-4 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-all flex items-center gap-2 text-xs font-bold"
            >
              <X className="h-4 w-4" />
              Reject
            </button>
          </>
        )}
      </div>
    </div>
  )
}

function PlanPill({ label, muted = false }: { label: string; muted?: boolean }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${
      muted
        ? 'border-border bg-background text-muted-foreground'
        : 'border-primary/20 bg-primary/10 text-primary'
    }`}>
      {label}
    </span>
  )
}

function DecisionRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Bot
  label: string
  value: string
}) {
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <Icon className="h-3.5 w-3.5 text-primary/60" />
      <span className="font-bold uppercase tracking-wider text-muted-foreground/60">{label}</span>
      <span className="min-w-0 flex-1 truncate text-foreground/70">{value}</span>
    </div>
  )
}
