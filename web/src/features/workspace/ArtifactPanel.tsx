import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Archive,
  CheckCircle2,
  Clock,
  Database,
  FileText,
  Filter,
  GitBranch,
  NotebookTabs,
  Sparkles,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { ArtifactDetail } from './ArtifactDetail'

interface Artifact {
  id: string
  workspace_id: string
  task_id?: string | null
  agent_id?: string | null
  artifact_type: string
  title: string
  content: string
  metadata?: Record<string, unknown>
  version: number
  status: string
  source: string
  context_type?: string | null
  created_at: string
  updated_at: string
}

const STATUS_ICONS: Record<string, typeof FileText> = {
  draft: Clock,
  published: CheckCircle2,
  archived: Archive,
}

const TYPE_ICONS: Record<string, typeof FileText> = {
  report: FileText,
  plan: NotebookTabs,
  checklist: CheckCircle2,
  notebook: NotebookTabs,
  log: Database,
}

const STATUS_COLORS: Record<string, string> = {
  draft: 'text-amber-600 bg-amber-500/10 border-amber-500/20',
  published: 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20',
  archived: 'text-slate-500 bg-slate-500/10 border-slate-500/20',
}

const SOURCE_LABELS: Record<string, string> = {
  manual: 'Manual',
  plan_apply: 'Plan',
  task_executor: 'Task',
  browser_automation: 'Browser',
  chat: 'Chat',
  skill: 'Skill',
}

interface ArtifactPanelProps {
  workspaceId: string
}

export function ArtifactPanel({ workspaceId }: ArtifactPanelProps) {
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data: artifacts = [], isLoading } = useQuery<Artifact[]>({
    queryKey: ['artifacts', workspaceId, statusFilter],
    queryFn: () => {
      const params: Record<string, string> = {}
      if (statusFilter) params.status = statusFilter
      return api
        .get(`/workspaces/${workspaceId}/artifacts`, { params })
        .then((r) => r.data)
    },
    enabled: !!workspaceId,
  })

  const stats = useMemo(() => {
    const published = artifacts.filter((item) => item.status === 'published').length
    const browser = artifacts.filter((item) => item.source === 'browser_automation').length
    const latest = artifacts[0]?.updated_at
    return { total: artifacts.length, published, browser, latest }
  }, [artifacts])

  return (
    <div className="p-4 space-y-4">
      <section className="rounded-2xl border border-border bg-card/70 p-4 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-black text-foreground">Output Library</h3>
                <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  Reports, datasets, browser captures, and task results
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-3 gap-2">
          <Metric label="Total" value={stats.total} />
          <Metric label="Published" value={stats.published} />
          <Metric label="Browser" value={stats.browser} />
        </div>
      </section>

      <div className="flex items-center gap-2 overflow-x-auto scrollbar-hide">
        <Filter className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        {[null, 'draft', 'published', 'archived'].map((status) => (
          <button
            key={status ?? 'all'}
            onClick={() => setStatusFilter(status)}
            className={cn(
              'shrink-0 px-3 py-1.5 rounded-xl text-[10px] font-black uppercase tracking-widest border transition-all',
              statusFilter === status
                ? 'bg-primary text-primary-foreground border-primary shadow-sm shadow-primary/20'
                : 'bg-background text-muted-foreground border-border hover:text-foreground hover:bg-muted',
            )}
          >
            {status ?? 'All'}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="py-20 text-center">
          <FileText className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
            Loading Outputs
          </p>
        </div>
      ) : artifacts.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-muted/20 px-6 py-16 text-center">
          <FileText className="h-9 w-9 text-muted-foreground/30 mx-auto mb-4" />
          <p className="text-sm font-black text-foreground">No outputs yet</p>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            Finished tasks, browser captures, reports, and exported results will appear here.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {artifacts.map((artifact) => (
            <ArtifactCard
              key={artifact.id}
              artifact={artifact}
              selected={artifact.id === selectedId}
              onClick={() => setSelectedId(artifact.id)}
            />
          ))}
        </div>
      )}

      {selectedId && (
        <ArtifactDetail
          artifactId={selectedId}
          workspaceId={workspaceId}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-border bg-background/70 px-3 py-2">
      <div className="text-lg font-black text-foreground">{value}</div>
      <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
    </div>
  )
}

function ArtifactCard({
  artifact,
  selected,
  onClick,
}: {
  artifact: Artifact
  selected: boolean
  onClick: () => void
}) {
  const StatusIcon = STATUS_ICONS[artifact.status] ?? FileText
  const TypeIcon = TYPE_ICONS[artifact.artifact_type] ?? FileText
  const summary = artifactSummary(artifact)

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-2xl border p-4 transition-all duration-200 group',
        selected
          ? 'border-primary/40 bg-primary/5 shadow-sm shadow-primary/10'
          : 'border-border bg-card/50 hover:bg-card hover:border-primary/20',
      )}
    >
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-xl border border-border bg-background flex items-center justify-center shrink-0 group-hover:border-primary/30">
          <TypeIcon className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h4 className="line-clamp-2 text-sm font-black leading-snug text-foreground group-hover:text-primary">
              {artifact.title}
            </h4>
            <span
              className={cn(
                'shrink-0 flex items-center gap-1 px-2 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border',
                STATUS_COLORS[artifact.status] ?? STATUS_COLORS.draft,
              )}
            >
              <StatusIcon className="h-2.5 w-2.5" />
              {artifact.status}
            </span>
          </div>

          <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
            {summary}
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
            <Chip>{SOURCE_LABELS[artifact.source] ?? artifact.source}</Chip>
            <Chip>{artifact.artifact_type}</Chip>
            {artifact.task_id && <Chip>Task {artifact.task_id.slice(0, 6)}</Chip>}
            <span className="flex items-center gap-1">
              <GitBranch className="h-2.5 w-2.5" />
              v{artifact.version}
            </span>
            <span>{new Date(artifact.updated_at).toLocaleDateString()}</span>
          </div>
        </div>
      </div>
    </button>
  )
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-border bg-background/70 px-2 py-1">
      {children}
    </span>
  )
}

function artifactSummary(artifact: Artifact): string {
  const metadataSummary = artifact.metadata?.summary
  if (typeof metadataSummary === 'string' && metadataSummary.trim()) {
    return metadataSummary.trim()
  }
  const text = artifact.content
    .replace(/^# .+$/gm, '')
    .replace(/[#*_`>-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return text || 'Open this output to inspect the generated result and source details.'
}
