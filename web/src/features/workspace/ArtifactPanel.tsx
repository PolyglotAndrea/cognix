import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FileText,
  Clock,
  CheckCircle2,
  Archive,
  GitBranch,
  Filter,
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

const STATUS_COLORS: Record<string, string> = {
  draft: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  published: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  archived: 'text-slate-500 bg-slate-500/10 border-slate-500/20',
}

const SOURCE_LABELS: Record<string, string> = {
  manual: 'Manual',
  plan_apply: 'Plan',
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

  return (
    <div className="p-4 space-y-3">
      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-muted-foreground" />
        {[null, 'draft', 'published', 'archived'].map((s) => (
          <button
            key={s ?? 'all'}
            onClick={() => setStatusFilter(s)}
            className={cn(
              'px-2 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all',
              statusFilter === s
                ? 'bg-primary/10 text-primary border border-primary/20'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted border border-transparent',
            )}
          >
            {s ?? 'All'}
          </button>
        ))}
      </div>

      {/* List */}
      {isLoading ? (
        <div className="py-20 text-center">
          <FileText className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
            Loading Artifacts
          </p>
        </div>
      ) : artifacts.length === 0 ? (
        <div className="py-20 text-center">
          <FileText className="h-8 w-8 text-muted-foreground/20 mx-auto mb-4" />
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
            No Artifacts
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Artifacts are created from agent outputs and plan results.
          </p>
        </div>
      ) : (
        artifacts.map((artifact) => {
          const StatusIcon = STATUS_ICONS[artifact.status] ?? FileText
          return (
            <button
              key={artifact.id}
              onClick={() => setSelectedId(artifact.id)}
              className="w-full text-left rounded-xl border border-border bg-card/40 hover:bg-card hover:border-primary/20 p-3 transition-all duration-200 group"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <div className="text-xs font-bold text-foreground truncate group-hover:text-primary transition-colors">
                    {artifact.title}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">
                      {artifact.artifact_type}
                    </span>
                    {artifact.source !== 'manual' && (
                      <span className="text-[9px] font-bold text-primary/60 uppercase">
                        {SOURCE_LABELS[artifact.source] ?? artifact.source}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span
                    className={cn(
                      'flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border',
                      STATUS_COLORS[artifact.status] ?? STATUS_COLORS.draft,
                    )}
                  >
                    <StatusIcon className="h-2.5 w-2.5" />
                    {artifact.status}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 text-[9px] text-muted-foreground">
                <GitBranch className="h-2.5 w-2.5" />
                <span>v{artifact.version}</span>
                <span className="w-1 h-1 rounded-full bg-border" />
                <span>{new Date(artifact.updated_at).toLocaleDateString()}</span>
              </div>
            </button>
          )
        })
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
