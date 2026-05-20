import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Send } from 'lucide-react'
import { api } from '@/shared/api/client'
import { RichMessage } from '@/shared/ui'

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
  parent_id?: string | null
  status: string
  source: string
  context_type?: string | null
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

  const publishMutation = useMutation({
    mutationFn: () =>
      api.post(`/workspaces/${workspaceId}/artifacts/${artifactId}/publish`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['artifact', artifactId] })
    },
  })

  if (!artifact && !isLoading) return null

  return (
    <div
      className="fixed inset-0 z-[100] bg-background/90 backdrop-blur-sm flex items-center justify-center p-6"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="relative w-full max-w-3xl max-h-[90vh] bg-card border border-border/60 rounded-3xl shadow-2xl shadow-black/20 flex flex-col overflow-hidden">

        {/* Header — title + close only */}
        <div className="flex items-start justify-between gap-4 px-8 pt-7 pb-5 shrink-0">
          <div className="min-w-0 flex-1">
            {isLoading ? (
              <div className="h-7 w-48 bg-muted animate-pulse rounded-xl" />
            ) : (
              <h2 className="text-xl font-black text-foreground leading-tight tracking-tight">
                {artifact?.title}
              </h2>
            )}
            {artifact && (
              <p className="mt-1.5 text-xs text-muted-foreground font-medium">
                {new Date(artifact.updated_at).toLocaleDateString('en', {
                  month: 'long', day: 'numeric', year: 'numeric'
                })}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="mt-0.5 p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all shrink-0"
            aria-label="Close"
          >
            <X className="h-4.5 w-4.5" />
          </button>
        </div>

        {/* Divider */}
        <div className="h-px bg-border/50 mx-8 shrink-0" />

        {/* Content — the whole point */}
        <div className="flex-1 overflow-y-auto px-8 py-6 scrollbar-hide">
          {isLoading ? (
            <div className="space-y-3 animate-pulse">
              <div className="h-4 bg-muted rounded-lg w-full" />
              <div className="h-4 bg-muted rounded-lg w-5/6" />
              <div className="h-4 bg-muted rounded-lg w-4/6" />
              <div className="h-4 bg-muted rounded-lg w-full mt-6" />
              <div className="h-4 bg-muted rounded-lg w-3/4" />
            </div>
          ) : artifact ? (
            <article className="prose prose-sm dark:prose-invert max-w-none text-foreground leading-relaxed">
              <RichMessage content={artifact.content || '_No content yet._'} />
            </article>
          ) : null}
        </div>

        {/* Footer — only show "Publish" if draft, nothing else */}
        {artifact?.status === 'draft' && (
          <>
            <div className="h-px bg-border/50 mx-8 shrink-0" />
            <div className="px-8 py-4 flex items-center justify-end shrink-0">
              <button
                onClick={() => publishMutation.mutate()}
                disabled={publishMutation.isPending}
                className="flex items-center gap-2 px-5 py-2.5 rounded-2xl text-xs font-black uppercase tracking-widest bg-primary text-primary-foreground hover:bg-primary/90 transition-all active:scale-95 shadow-md shadow-primary/25 disabled:opacity-50"
              >
                <Send className="h-3.5 w-3.5" />
                {publishMutation.isPending ? 'Publishing…' : 'Publish Output'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
