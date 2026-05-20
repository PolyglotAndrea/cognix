import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  FileText,
  NotebookTabs,
  Database,
  CheckCircle2,
  Loader2,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { ArtifactDetail } from './ArtifactDetail'
import { useWorkspaceStore } from './store'

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

const TYPE_ICONS: Record<string, typeof FileText> = {
  report: FileText,
  plan: NotebookTabs,
  checklist: CheckCircle2,
  notebook: NotebookTabs,
  log: Database,
}

const SOURCE_LABELS: Record<string, string> = {
  manual: 'Manual',
  plan_apply: 'Plan Output',
  task_executor: 'Task Result',
  browser_automation: 'Automation',
  chat: 'Conversation',
  skill: 'Tool Skill',
}

interface ArtifactPanelProps {
  workspaceId: string
}

export function ArtifactPanel({ workspaceId }: ArtifactPanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { isAgentRunning } = useWorkspaceStore()

  const { data: artifacts = [], isLoading } = useQuery<Artifact[]>({
    queryKey: ['artifacts', workspaceId],
    queryFn: () =>
      api
        .get(`/workspaces/${workspaceId}/artifacts`)
        .then((r) => r.data),
    enabled: !!workspaceId,
    refetchInterval: isAgentRunning ? 3000 : false,
  })

  return (
    <div className="flex flex-col h-full bg-transparent">
      {/* Header */}
      <div className="px-4 py-3 shrink-0 flex items-center justify-between">
        <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">
          Generated Outputs ({artifacts.length})
        </span>
        {isAgentRunning && (
          <div className="flex items-center gap-1.5 text-[9px] font-black uppercase tracking-widest text-primary animate-pulse">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>Working…</span>
          </div>
        )}
      </div>

      {/* Artifacts List */}
      <div className="flex-1 overflow-y-auto px-4 pb-6 scrollbar-hide">
        {/* Loading skeleton — shown while agent is actively running */}
        {isAgentRunning && (
          <div className="mb-3 p-3.5 rounded-2xl border border-primary/20 bg-primary/3 flex items-start gap-3.5 animate-pulse">
            <div className="w-8 h-8 rounded-xl bg-primary/10 border border-primary/15 shrink-0 flex items-center justify-center">
              <Loader2 className="h-4 w-4 text-primary/40 animate-spin" />
            </div>
            <div className="flex-1 min-w-0 space-y-2 pt-0.5">
              <div className="h-3 bg-primary/10 rounded-lg w-3/5" />
              <div className="h-2.5 bg-muted/60 rounded-lg w-2/5" />
            </div>
          </div>
        )}

        {isLoading && !isAgentRunning ? (
          <div className="py-20 text-center">
            <FileText className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-3" />
            <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">
              Loading artifacts...
            </p>
          </div>
        ) : artifacts.length === 0 && !isAgentRunning ? (
          <div className="rounded-2xl border border-dashed border-border/80 bg-muted/5 px-4 py-16 text-center select-none">
            <FileText className="h-8 w-8 text-muted-foreground/20 mx-auto mb-3" />
            <p className="text-xs font-black text-foreground uppercase tracking-wider">No outputs yet</p>
            <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground/75 font-medium">
              Artifacts generated during execution will appear here.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {artifacts.map((artifact) => {
              const selected = artifact.id === selectedId
              const TypeIcon = TYPE_ICONS[artifact.artifact_type] ?? FileText

              return (
                <button
                  key={artifact.id}
                  onClick={() => setSelectedId(artifact.id)}
                  className={cn(
                    "w-full text-left p-3.5 rounded-2xl border transition-all duration-200 flex items-start gap-3.5 group relative overflow-hidden",
                    selected
                      ? "bg-primary/5 border-primary/30 shadow-md shadow-primary/5 ring-1 ring-primary/20"
                      : "bg-card/40 border-border/60 hover:bg-card/90 hover:border-border/100 hover:shadow-sm"
                  )}
                >
                  {/* Left accent */}
                  <div className={cn(
                    "absolute left-0 top-0 bottom-0 w-1 transition-all duration-200",
                    selected ? "bg-primary" : "bg-transparent group-hover:bg-muted-foreground/20"
                  )} />

                  {/* Icon */}
                  <div className={cn(
                    "w-8 h-8 rounded-xl flex items-center justify-center shrink-0 border transition-colors",
                    selected
                      ? "bg-primary/10 border-primary/20 text-primary"
                      : "bg-muted/40 border-border/50 text-muted-foreground/70 group-hover:text-primary group-hover:bg-primary/5 group-hover:border-primary/10"
                  )}>
                    <TypeIcon className="h-4 w-4" />
                  </div>

                  {/* Meta */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <h4 className={cn(
                        "text-xs font-black leading-tight tracking-tight truncate transition-colors",
                        selected ? "text-primary" : "text-foreground group-hover:text-primary"
                      )}>
                        {artifact.title}
                      </h4>
                      <span className="shrink-0 text-[8px] font-black uppercase tracking-widest text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded border border-border/40">
                        v{artifact.version}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 text-[9px] font-bold text-muted-foreground/60 mt-1">
                      <span>{SOURCE_LABELS[artifact.source] ?? artifact.source}</span>
                      <span>•</span>
                      <span>{new Date(artifact.updated_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </div>

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
