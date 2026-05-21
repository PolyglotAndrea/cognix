import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  AppWindow,
  BarChart3,
  BookOpen,
  BrainCircuit,
  ChevronRight,
  FileText,
  HelpCircle,
  LayoutDashboard,
  MessageSquareWarning,
  Presentation,
  Table2,
  Video,
  Volume2,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { ArtifactPanel } from './ArtifactPanel'
import { CodeProjectsPanel } from './CodeProjectsPanel'
import { PlaybookPanel } from './PlaybookPanel'
import { cn } from '@/shared/lib/cn'

interface ApprovalRequest {
  id: string
  kind: string
  status: string
  reason: string
  tool_name: string
}

const studioActions = [
  { label: 'Report', intent: 'Create a structured report from the selected sources.', icon: FileText, tone: 'bg-amber-500/10 text-amber-700 border-amber-500/15' },
  { label: 'Data Table', intent: 'Extract the selected sources into a clean data table with columns, summary, and exportable output.', icon: Table2, tone: 'bg-blue-500/10 text-blue-700 border-blue-500/15' },
  { label: 'Slide Deck', intent: 'Turn the selected sources into a concise slide deck outline with slide titles and speaker notes.', icon: Presentation, tone: 'bg-stone-500/10 text-stone-700 border-stone-500/15' },
  { label: 'Mind Map', intent: 'Create a mind map from the selected sources, grouping key concepts and relationships.', icon: BrainCircuit, tone: 'bg-fuchsia-500/10 text-fuchsia-700 border-fuchsia-500/15' },
  { label: 'Quiz', intent: 'Create a quiz from the selected sources with questions, answers, and explanations.', icon: HelpCircle, tone: 'bg-cyan-500/10 text-cyan-700 border-cyan-500/15' },
  { label: 'Audio Overview', intent: 'Draft an audio overview script from the selected sources.', icon: Volume2, tone: 'bg-indigo-500/10 text-indigo-700 border-indigo-500/15' },
  { label: 'Video Overview', intent: 'Draft a video overview outline from the selected sources.', icon: Video, tone: 'bg-emerald-500/10 text-emerald-700 border-emerald-500/15' },
  { label: 'App Preview', intent: 'Create a runnable sandbox app preview based on the selected sources and goal.', icon: AppWindow, tone: 'bg-violet-500/10 text-violet-700 border-violet-500/15' },
]

type StudioView = 'outputs' | 'apps' | 'playbooks'

export function StudioPanel({
  workspaceId,
  onCreateFromStudio,
}: {
  workspaceId: string
  onCreateFromStudio: (intent: string) => void
}) {
  const [view, setView] = useState<StudioView>('outputs')
  const { data: approvals = [] } = useQuery<ApprovalRequest[]>({
    queryKey: ['approvals', workspaceId],
    queryFn: () =>
      api
        .get('/approvals', { params: { workspace_id: workspaceId, include_resolved: true } })
        .then((r) => r.data),
    enabled: !!workspaceId,
    refetchInterval: 5000,
  })
  const pendingApprovals = approvals.filter((approval) => approval.status === 'pending')

  return (
    <aside className="flex h-full flex-col overflow-hidden rounded-[1.35rem] border border-border/70 bg-card shadow-sm">
      <div className="border-b border-border/70 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Studio</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              Outputs, previews, and reusable work
            </p>
          </div>
          <LayoutDashboard className="h-4 w-4 text-muted-foreground" />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hide">
        <div className="space-y-4 p-4">
          {pendingApprovals.length > 0 && (
            <section className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.06] p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                <MessageSquareWarning className="h-4 w-4 text-amber-600" />
                  <div className="min-w-0">
                    <div className="truncate text-xs font-black text-amber-700">
                      Needs input ({pendingApprovals.length})
                    </div>
                    <p className="truncate text-[10px] text-muted-foreground">
                      Continue in the chat flow.
                    </p>
                  </div>
                </div>
                <span className="shrink-0 rounded-full border border-amber-500/20 bg-background px-2 py-1 text-[9px] font-black uppercase tracking-widest text-amber-700">
                  Pending
                </span>
              </div>
            </section>
          )}

          <section className="grid grid-cols-2 gap-2">
            {studioActions.map((action) => {
              const Icon = action.icon
              return (
                <button
                  key={action.label}
                  type="button"
                  onClick={() => onCreateFromStudio(action.intent)}
                  className={cn(
                    'flex min-h-16 items-center justify-between rounded-2xl border p-3 text-left transition-transform hover:-translate-y-0.5',
                    action.tone,
                  )}
                >
                  <span className="flex items-center gap-2">
                    <Icon className="h-4 w-4" />
                    <span className="text-[11px] font-bold">{action.label}</span>
                  </span>
                  <ChevronRight className="h-4 w-4 opacity-60" />
                </button>
              )
            })}
          </section>

          <div className="flex rounded-full border border-border bg-background p-1">
            <StudioTab active={view === 'outputs'} onClick={() => setView('outputs')} icon={FileText} label="Outputs" />
            <StudioTab active={view === 'apps'} onClick={() => setView('apps')} icon={AppWindow} label="Apps" />
            <StudioTab active={view === 'playbooks'} onClick={() => setView('playbooks')} icon={BookOpen} label="Playbooks" />
          </div>
        </div>

        <div className="min-h-[420px] border-t border-border/60">
          {view === 'outputs' && <ArtifactPanel workspaceId={workspaceId} />}
          {view === 'apps' && <CodeProjectsPanel workspaceId={workspaceId} />}
          {view === 'playbooks' && <PlaybookPanel workspaceId={workspaceId} />}
        </div>
      </div>
    </aside>
  )
}

function StudioTab({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: typeof BarChart3
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-1 items-center justify-center gap-1.5 rounded-full px-2 py-1.5 text-[10px] font-bold transition-colors',
        active ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}
