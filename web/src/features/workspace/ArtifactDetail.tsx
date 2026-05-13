import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  X,
  GitBranch,
  Send,
  Archive,
  FileText,
  Clock,
  CheckCircle2,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

interface Artifact {
  id: string
  workspace_id: string
  task_id?: string | null
  agent_id?: string | null
  artifact_type: string
  title: string
  content: string
  version: number
  parent_id?: string | null
  status: string
  source: string
  context_type?: string | null
  metadata_json?: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface ArtifactDetailProps {
  artifactId: string
  workspaceId: string
  onClose: () => void
}

export function ArtifactDetail({ artifactId, workspaceId, onClose }: ArtifactDetailProps) {
  const queryClient = useQueryClient()

  const { data: artifact, isLoading } = useQuery<Artifact>({
    queryKey: ['artifact', artifactId],
    queryFn: () =>
      api
        .get(`/workspaces/${workspaceId}/artifacts/${artifactId}`)
        .then((r) => r.data),
    enabled: !!artifactId,
  })

  const { data: versions = [] } = useQuery<Artifact[]>({
    queryKey: ['artifact-versions', artifactId],
    queryFn: () =>
      api
        .get(`/workspaces/${workspaceId}/artifacts/${artifactId}/versions`)
        .then((r) => r.data),
    enabled: !!artifactId,
  })

  const publishMutation = useMutation({
    mutationFn: () =>
      api.post(`/workspaces/${workspaceId}/artifacts/${artifactId}/publish`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['artifact', artifactId] })
      queryClient.invalidateQueries({ queryKey: ['artifact-versions', artifactId] })
    },
  })

  const archiveMutation = useMutation({
    mutationFn: () =>
      api.post(`/workspaces/${workspaceId}/artifacts/${artifactId}/archive`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['artifact', artifactId] })
    },
  })

  if (!artifact && !isLoading) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[85vh] bg-card border border-border rounded-3xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
          <div className="min-w-0">
            <h3 className="text-lg font-bold text-foreground truncate">
              {artifact?.title ?? 'Loading...'}
            </h3>
            {artifact && (
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  {artifact.artifact_type}
                </span>
                <span className="w-1 h-1 rounded-full bg-border" />
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  <GitBranch className="h-2.5 w-2.5" />
                  v{artifact.version}
                </span>
                <span className="w-1 h-1 rounded-full bg-border" />
                <span className="text-[10px] text-muted-foreground">
                  {artifact.source}
                </span>
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-6 space-y-6">
          {isLoading ? (
            <div className="py-12 text-center">
              <FileText className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto" />
            </div>
          ) : artifact ? (
            <>
              {/* Content */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2">
                  Content
                </h4>
                <pre className="text-xs text-foreground/80 bg-muted/30 rounded-xl p-4 border border-border overflow-auto max-h-64 font-mono leading-relaxed">
                  {artifact.content || 'No content'}
                </pre>
              </div>

              {/* Version history */}
              {versions.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2">
                    Version History
                  </h4>
                  <div className="space-y-2">
                    {versions.map((v) => (
                      <div
                        key={v.id}
                        className="flex items-center gap-3 p-2 rounded-lg bg-muted/20 border border-border/50"
                      >
                        <GitBranch className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-xs font-bold text-foreground">v{v.version}</span>
                        <span className="text-[10px] text-muted-foreground">{v.title}</span>
                        <span className="ml-auto text-[9px] text-muted-foreground">
                          {new Date(v.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>

        {/* Actions */}
        {artifact && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-border shrink-0">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider border',
                  artifact.status === 'published'
                    ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20'
                    : artifact.status === 'archived'
                      ? 'text-slate-500 bg-slate-500/10 border-slate-500/20'
                      : 'text-amber-500 bg-amber-500/10 border-amber-500/20',
                )}
              >
                {artifact.status === 'published' ? (
                  <CheckCircle2 className="h-3 w-3" />
                ) : artifact.status === 'archived' ? (
                  <Archive className="h-3 w-3" />
                ) : (
                  <Clock className="h-3 w-3" />
                )}
                {artifact.status}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {artifact.status !== 'archived' && (
                <button
                  onClick={() => archiveMutation.mutate()}
                  disabled={archiveMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground border border-border hover:border-primary/30 transition-all"
                >
                  <Archive className="h-3 w-3" />
                  Archive
                </button>
              )}
              {artifact.status === 'draft' && (
                <button
                  onClick={() => publishMutation.mutate()}
                  disabled={publishMutation.isPending}
                  className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider bg-primary text-primary-foreground hover:bg-primary/90 transition-all active:scale-95"
                >
                  <Send className="h-3 w-3" />
                  Publish
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
