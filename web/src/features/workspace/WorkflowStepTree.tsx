import { useState } from 'react'
import {
  ArrowDown,
  CheckCircle2,
  ChevronRight,
  GitBranch,
  RefreshCw,
  SkipForward,
  Split,
  XCircle,
} from 'lucide-react'
import { Badge } from '@/shared/ui'

export interface WorkflowStepResult {
  step: string
  agent: string
  status: 'success' | 'error' | 'skipped'
  output?: string
  error?: string
  reason?: string
  started_at?: string
  finished_at?: string
  duration_ms?: number
}

const statusConfig = {
  success: { icon: CheckCircle2, color: 'text-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', badge: 'success' as const },
  error: { icon: XCircle, color: 'text-rose-500', bg: 'bg-rose-500/10', border: 'border-rose-500/20', badge: 'error' as const },
  skipped: { icon: SkipForward, color: 'text-amber-500', bg: 'bg-amber-500/10', border: 'border-amber-500/20', badge: 'warning' as const },
}

const patternIcons: Record<string, typeof ArrowDown> = {
  sequential: ArrowDown,
  parallel: Split,
  router: GitBranch,
  loop: RefreshCw,
}

export function WorkflowStepTree({
  steps,
  pattern,
}: {
  steps: WorkflowStepResult[]
  pattern?: string
}) {
  if (!steps || steps.length === 0) {
    return (
      <div className="py-8 text-center text-xs text-muted-foreground">
        No step data available
      </div>
    )
  }

  const PatternIcon = patternIcons[pattern || 'sequential'] || ArrowDown

  return (
    <div className="space-y-1">
      <div className="mb-3 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
        <PatternIcon className="h-3.5 w-3.5" />
        {pattern || 'sequential'} workflow — {steps.length} steps
      </div>
      <div className="relative">
        {/* Vertical connector line */}
        <div className="absolute left-[15px] top-4 bottom-4 w-px bg-border" />
        <div className="space-y-2">
          {steps.map((step, i) => (
            <StepNode key={step.step || i} step={step} index={i} />
          ))}
        </div>
      </div>
    </div>
  )
}

function StepNode({ step, index }: { step: WorkflowStepResult; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const config = statusConfig[step.status] || statusConfig.success
  const StatusIcon = config.icon
  const hasContent = !!(step.output || step.error || step.reason)

  return (
    <div className="relative pl-10">
      {/* Status dot on the line */}
      <div className={`absolute left-2.5 top-3 z-10 flex h-5 w-5 items-center justify-center rounded-full ${config.bg} ${config.border} border`}>
        <StatusIcon className={`h-3 w-3 ${config.color}`} />
      </div>

      <div
        className={`rounded-xl border ${config.border} ${config.bg} px-4 py-3 ${
          hasContent ? 'cursor-pointer hover:border-primary/20' : ''
        } transition-colors`}
        onClick={() => hasContent && setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            {hasContent && (
              <ChevronRight
                className={`h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform ${
                  expanded ? 'rotate-90' : ''
                }`}
              />
            )}
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Step {index + 1}
            </span>
            <span className="truncate text-sm font-bold text-foreground">
              {step.agent}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {step.duration_ms != null && (
              <span className="font-mono text-[10px] text-muted-foreground">
                {formatDuration(step.duration_ms)}
              </span>
            )}
            <Badge variant={config.badge}>{step.status}</Badge>
          </div>
        </div>

        {step.status === 'skipped' && step.reason && (
          <p className="mt-1.5 text-[11px] text-muted-foreground">{step.reason}</p>
        )}

        {expanded && (
          <div className="mt-3 space-y-2">
            {step.output && (
              <div>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  Output
                </div>
                <pre className="max-h-48 overflow-auto rounded-lg bg-background/50 p-3 font-mono text-[11px] leading-5 text-foreground whitespace-pre-wrap break-all">
                  {step.output}
                </pre>
              </div>
            )}
            {step.error && (
              <div>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-rose-500">
                  Error
                </div>
                <pre className="max-h-32 overflow-auto rounded-lg bg-rose-500/5 p-3 font-mono text-[11px] leading-5 text-rose-600 dark:text-rose-300 whitespace-pre-wrap break-all">
                  {step.error}
                </pre>
              </div>
            )}
          </div>
        )}
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
