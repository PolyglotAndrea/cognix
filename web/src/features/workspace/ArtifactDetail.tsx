import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import {
  Archive,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  GitBranch,
  Send,
  X,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
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
      <div className="w-full max-w-5xl max-h-[88vh] bg-card border border-border rounded-3xl shadow-2xl overflow-hidden flex flex-col">
        <div className="flex items-start justify-between gap-4 px-6 py-5 border-b border-border shrink-0">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {artifact && <StatusBadge status={artifact.status} />}
              {artifact && (
                <span className="rounded-full border border-border bg-muted/30 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                  {artifact.artifact_type}
                </span>
              )}
            </div>
            <h3 className="text-xl font-black leading-tight text-foreground">
              {artifact?.title ?? 'Loading output...'}
            </h3>
            {artifact && (
              <p className="mt-2 max-w-2xl text-xs leading-relaxed text-muted-foreground">
                {artifactSummary(artifact)}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
            aria-label="Close artifact detail"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_280px]">
          <div className="min-h-0 overflow-auto p-6">
            {isLoading ? (
              <div className="py-20 text-center">
                <FileText className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto" />
              </div>
            ) : artifact ? (
              <article className="rounded-2xl border border-border bg-background/60 p-5">
                <RichMessage content={artifact.content || 'No content generated yet.'} />
              </article>
            ) : null}
          </div>

          {artifact && (
            <aside className="border-t lg:border-t-0 lg:border-l border-border bg-muted/20 p-5 overflow-auto">
              <InfoSection title="Provenance">
                <InfoRow label="Source" value={sourceLabel(artifact.source)} />
                <InfoRow label="Version" value={`v${artifact.version}`} />
                <InfoRow label="Updated" value={new Date(artifact.updated_at).toLocaleString()} />
                {artifact.task_id && <InfoRow label="Task" value={artifact.task_id} mono />}
                {artifact.agent_id && <InfoRow label="Agent" value={artifact.agent_id} mono />}
              </InfoSection>

              <InfoSection title="Context">
                <InfoRow label="Type" value={artifact.context_type || artifact.artifact_type} />
                <InfoRow label="Status" value={artifact.status} />
                {typeof artifact.metadata?.url === 'string' && (
                  <a
                    href={artifact.metadata.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 flex items-center gap-2 rounded-xl border border-border bg-background px-3 py-2 text-xs font-bold text-primary hover:bg-primary/5"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open source URL
                  </a>
                )}
              </InfoSection>

              {versions.length > 0 && (
                <InfoSection title="Versions">
                  <div className="space-y-2">
                    {versions.map((version) => (
                      <div
                        key={version.id}
                        className="rounded-xl border border-border bg-background/70 p-3"
                      >
                        <div className="flex items-center gap-2">
                          <GitBranch className="h-3.5 w-3.5 text-primary" />
                          <span className="text-xs font-black text-foreground">
                            v{version.version}
                          </span>
                          <span className="ml-auto text-[9px] text-muted-foreground">
                            {new Date(version.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="mt-1 truncate text-[10px] text-muted-foreground">
                          {version.title}
                        </p>
                      </div>
                    ))}
                  </div>
                </InfoSection>
              )}
            </aside>
          )}
        </div>

        {artifact && (
          <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-border shrink-0">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Output ID {artifact.id}
            </span>
            <div className="flex items-center gap-2">
              {artifact.status !== 'archived' && (
                <button
                  onClick={() => archiveMutation.mutate()}
                  disabled={archiveMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest text-muted-foreground hover:text-foreground border border-border hover:border-primary/30 transition-all"
                >
                  <Archive className="h-3 w-3" />
                  Archive
                </button>
              )}
              {artifact.status === 'draft' && (
                <button
                  onClick={() => publishMutation.mutate()}
                  disabled={publishMutation.isPending}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest bg-primary text-primary-foreground hover:bg-primary/90 transition-all active:scale-95"
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

function StatusBadge({ status }: { status: string }) {
  const Icon =
    status === 'published' ? CheckCircle2 : status === 'archived' ? Archive : Clock
  return (
    <span
      className={cn(
        'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border',
        status === 'published'
          ? 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20'
          : status === 'archived'
            ? 'text-slate-500 bg-slate-500/10 border-slate-500/20'
            : 'text-amber-600 bg-amber-500/10 border-amber-500/20',
      )}
    >
      <Icon className="h-3 w-3" />
      {status}
    </span>
  )
}

function InfoSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-5">
      <h4 className="mb-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
        {title}
      </h4>
      <div className="space-y-2">{children}</div>
    </section>
  )
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="rounded-xl border border-border bg-background/70 px-3 py-2">
      <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          'mt-1 break-words text-xs font-bold text-foreground',
          mono && 'font-mono text-[11px]',
        )}
      >
        {value}
      </div>
    </div>
  )
}

function sourceLabel(source: string): string {
  return (
    {
      manual: 'Manual',
      plan_apply: 'Plan Apply',
      task_executor: 'Task Executor',
      browser_automation: 'Browser Automation',
      chat: 'Chat',
      skill: 'Skill',
    }[source] || source
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
  return text || 'Generated output with source, task, and agent provenance.'
}
