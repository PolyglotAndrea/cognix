import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  FileText,
  GitBranch,
  Send,
  X,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { RichMessage } from '@/shared/ui'
import { cn } from '@/shared/lib/cn'

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

interface WorkflowNode {
  id: string
  title: string
  summary: string
  status: 'completed' | 'running' | 'failed' | 'pending'
  kind: string
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

  const workflowNodes = useMemo(
    () => (artifact ? buildWorkflowNodes(artifact) : []),
    [artifact],
  )

  if (!artifact && !isLoading) return null

  return (
    <div
      className="fixed inset-0 z-[100] bg-background/90 backdrop-blur-sm flex items-center justify-center p-6"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="relative w-full max-w-5xl max-h-[90vh] bg-card border border-border/60 rounded-3xl shadow-2xl shadow-black/20 flex flex-col overflow-hidden">

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
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground/70">
                <span>{new Date(artifact.updated_at).toLocaleDateString()}</span>
                <span className="h-1 w-1 rounded-full bg-muted-foreground/30" />
                <span>{artifact.source}</span>
                <span className="h-1 w-1 rounded-full bg-muted-foreground/30" />
                <span>v{artifact.version}</span>
              </div>
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

        {/* Content */}
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
            <div className="grid gap-6 lg:grid-cols-[0.95fr_1.35fr]">
              <section className="rounded-2xl border border-border/70 bg-muted/[0.18] p-4">
                <div className="mb-4 flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-primary/15 bg-primary/10 text-primary">
                    <GitBranch className="h-4 w-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-black uppercase tracking-widest text-foreground">
                      Workflow
                    </h3>
                    <p className="mt-0.5 text-[10px] font-semibold text-muted-foreground">
                      Node-to-node execution summary
                    </p>
                  </div>
                </div>

                <div className="space-y-0">
                  {workflowNodes.map((node, index) => (
                    <WorkflowNodeCard
                      key={node.id}
                      node={node}
                      index={index}
                      isLast={index === workflowNodes.length - 1}
                    />
                  ))}
                </div>
              </section>

              <section className="min-w-0 rounded-2xl border border-border/70 bg-background/70 p-5">
                <div className="mb-4 flex items-center gap-2">
                  <FileText className="h-4 w-4 text-primary" />
                  <h3 className="text-xs font-black uppercase tracking-widest text-foreground">
                    Output Content
                  </h3>
                </div>
                <article className="prose prose-sm dark:prose-invert max-w-none text-foreground leading-relaxed">
                  <RichMessage content={artifact.content || '_No content yet._'} />
                </article>
              </section>
            </div>
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

function WorkflowNodeCard({
  node,
  index,
  isLast,
}: {
  node: WorkflowNode
  index: number
  isLast: boolean
}) {
  const Icon =
    node.status === 'failed'
      ? AlertTriangle
      : node.status === 'running'
      ? Clock3
      : node.status === 'completed'
      ? CheckCircle2
      : Circle

  return (
    <div className="relative grid grid-cols-[2rem_1fr] gap-3 pb-4 last:pb-0">
      {!isLast && (
        <div className="absolute left-4 top-9 bottom-0 w-px bg-border" aria-hidden />
      )}
      <div
        className={cn(
          'relative z-10 flex h-8 w-8 items-center justify-center rounded-full border bg-card',
          node.status === 'failed'
            ? 'border-red-500/25 text-red-600'
            : node.status === 'running'
            ? 'border-amber-500/25 text-amber-600'
            : node.status === 'completed'
            ? 'border-emerald-500/25 text-emerald-600'
            : 'border-border text-muted-foreground',
        )}
      >
        <Icon className="h-4 w-4" />
      </div>
      <div className="rounded-2xl border border-border/60 bg-card/70 p-3 shadow-sm">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[9px] font-black uppercase tracking-widest text-muted-foreground/70">
              Node {index + 1} · {node.kind}
            </div>
            <h4 className="mt-1 text-sm font-black leading-snug text-foreground">
              {node.title}
            </h4>
          </div>
          <span
            className={cn(
              'shrink-0 rounded-full border px-2 py-1 text-[9px] font-black uppercase tracking-widest',
              node.status === 'failed'
                ? 'border-red-500/20 bg-red-500/10 text-red-600'
                : node.status === 'running'
                ? 'border-amber-500/20 bg-amber-500/10 text-amber-600'
                : node.status === 'completed'
                ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600'
                : 'border-border bg-muted/40 text-muted-foreground',
            )}
          >
            {node.status}
          </span>
        </div>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          {node.summary}
        </p>
      </div>
    </div>
  )
}

function buildWorkflowNodes(artifact: Artifact): WorkflowNode[] {
  const metadata = artifact.metadata || {}
  const explicit = firstNonEmpty(
    readNodes(metadata.steps, 'step'),
    readNodes(metadata.workflow_steps, 'workflow'),
    readNodes(metadata.execution_results, 'execution'),
    readNodes(metadata.step_statuses, 'step'),
  )
  if (explicit.length > 0) return explicit

  const sections = parseMarkdownSections(artifact.content || '')
  if (sections.length > 0) {
    return sections.slice(0, 8).map((section, index) => ({
      id: `section-${index}`,
      title: section.title,
      summary: summarizeText(section.body || section.title),
      status: inferStatus(`${section.title}\n${section.body}`),
      kind: 'section',
    }))
  }

  return [
    {
      id: 'created',
      title: 'Output generated',
      summary: String(metadata.summary || artifact.title || 'Cognix generated this output.'),
      status: inferStatus(`${artifact.title}\n${artifact.content}`),
      kind: artifact.source || 'artifact',
    },
    {
      id: 'artifact',
      title: 'Artifact saved',
      summary: `Saved as ${artifact.artifact_type} in this workspace for review and reuse.`,
      status: artifact.status === 'draft' ? 'pending' : 'completed',
      kind: 'artifact',
    },
  ]
}

function readNodes(value: unknown, defaultKind: string): WorkflowNode[] {
  if (!value) return []
  if (Array.isArray(value)) {
    return value
      .map((item, index) => nodeFromUnknown(item, index, defaultKind))
      .filter(Boolean) as WorkflowNode[]
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item], index) =>
        nodeFromUnknown({ id: key, value: item }, index, defaultKind),
      )
      .filter(Boolean) as WorkflowNode[]
  }
  return []
}

function firstNonEmpty(...groups: WorkflowNode[][]): WorkflowNode[] {
  return groups.find((group) => group.length > 0) || []
}

function nodeFromUnknown(item: unknown, index: number, defaultKind: string): WorkflowNode | null {
  if (!item) return null
  if (typeof item === 'string') {
    return {
      id: `${defaultKind}-${index}`,
      title: item,
      summary: summarizeText(item),
      status: inferStatus(item),
      kind: defaultKind,
    }
  }
  if (typeof item !== 'object') return null
  const row = item as Record<string, unknown>
  const title = String(
    row.title ||
      row.name ||
      row.description ||
      row.action ||
      row.id ||
      `Step ${index + 1}`,
  )
  const rawSummary = String(
    row.summary ||
      row.result ||
      row.output ||
      row.error ||
      row.value ||
      row.content ||
      title,
  )
  return {
    id: String(row.id || `${defaultKind}-${index}`),
    title,
    summary: summarizeText(rawSummary),
    status: inferStatus(String(row.status || row.state || rawSummary)),
    kind: String(row.kind || row.action || defaultKind),
  }
}

function parseMarkdownSections(content: string): Array<{ title: string; body: string }> {
  const lines = content.split(/\r?\n/)
  const sections: Array<{ title: string; body: string[] }> = []
  for (const line of lines) {
    const match = line.match(/^#{2,3}\s+(.+)$/)
    if (match) {
      sections.push({ title: match[1].trim(), body: [] })
    } else if (sections.length > 0) {
      sections[sections.length - 1].body.push(line)
    }
  }
  return sections
    .map((section) => ({
      title: section.title,
      body: section.body.join('\n').trim(),
    }))
    .filter((section) => section.title)
}

function summarizeText(text: string): string {
  const clean = text
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#*_>`|\[\]()]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!clean) return 'No additional detail captured for this node.'
  return clean.length > 150 ? `${clean.slice(0, 150).trim()}...` : clean
}

function inferStatus(text: string): WorkflowNode['status'] {
  const value = text.toLowerCase()
  if (/(failed|error|失败|异常|中断|denied|rejected)/i.test(value)) return 'failed'
  if (/(running|pending|waiting|等待|待处理|审批|approval)/i.test(value)) return 'pending'
  if (/(completed|success|done|created|saved|成功|完成|已生成|已保存)/i.test(value)) {
    return 'completed'
  }
  return 'completed'
}
