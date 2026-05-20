import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AppWindow,
  ExternalLink,
  FileCode2,
  Play,
  Square,
  Terminal,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

interface CodeProject {
  id: string
  name: string
  description: string
  status: string
  preview_url: string
  port?: number | null
  pid?: number | null
  start_command: string
  path: string
  last_error: string
  updated_at: string
}

interface CodeProjectLog {
  project_id: string
  logs: string
}

export function CodeProjectsPanel({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient()

  const { data: projects = [], isLoading } = useQuery<CodeProject[]>({
    queryKey: ['code-projects', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/code-projects`).then((r) => r.data),
    enabled: !!workspaceId,
    refetchInterval: 4000,
  })

  const startMutation = useMutation({
    mutationFn: (projectId: string) =>
      api.post(`/workspaces/${workspaceId}/code-projects/${projectId}/start`, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['code-projects', workspaceId] }),
  })

  const stopMutation = useMutation({
    mutationFn: (projectId: string) =>
      api.post(`/workspaces/${workspaceId}/code-projects/${projectId}/stop`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['code-projects', workspaceId] }),
  })

  return (
    <div className="p-4 space-y-4">
      <section className="rounded-2xl border border-border bg-card/70 p-4">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
            <AppWindow className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-black text-foreground">Running Apps</h3>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Sandbox projects, previews, and app logs
            </p>
          </div>
        </div>
      </section>

      {isLoading ? (
        <div className="py-16 text-center">
          <AppWindow className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto" />
        </div>
      ) : projects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-muted/20 px-5 py-14 text-center">
          <FileCode2 className="h-9 w-9 text-muted-foreground/30 mx-auto mb-4" />
          <p className="text-sm font-black text-foreground">No app previews yet</p>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            When Cognix builds a code project in the workspace sandbox, its preview will appear here.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              workspaceId={workspaceId}
              starting={startMutation.isPending}
              stopping={stopMutation.isPending}
              onStart={() => startMutation.mutate(project.id)}
              onStop={() => stopMutation.mutate(project.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ProjectCard({
  project,
  workspaceId,
  starting,
  stopping,
  onStart,
  onStop,
}: {
  project: CodeProject
  workspaceId: string
  starting: boolean
  stopping: boolean
  onStart: () => void
  onStop: () => void
}) {
  const { data: log } = useQuery<CodeProjectLog>({
    queryKey: ['code-project-logs', workspaceId, project.id],
    queryFn: () =>
      api.get(`/workspaces/${workspaceId}/code-projects/${project.id}/logs`).then((r) => r.data),
    enabled: project.status === 'running' || project.status === 'failed',
    refetchInterval: project.status === 'running' ? 3000 : false,
  })

  const running = project.status === 'running'

  return (
    <div className="rounded-2xl border border-border bg-card/60 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                'h-2 w-2 rounded-full',
                running
                  ? 'bg-emerald-500'
                  : project.status === 'failed'
                    ? 'bg-rose-500'
                    : 'bg-slate-400',
              )}
            />
            <h4 className="truncate text-sm font-black text-foreground">{project.name}</h4>
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
            {project.description || project.path}
          </p>
        </div>
        <span className="rounded-full border border-border bg-background px-2 py-1 text-[9px] font-black uppercase tracking-widest text-muted-foreground">
          {project.status}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {running && project.preview_url ? (
          <a
            href={project.preview_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-[10px] font-black uppercase tracking-widest text-primary-foreground hover:bg-primary/90"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open Preview
          </a>
        ) : (
          <button
            onClick={onStart}
            disabled={starting}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-3 py-2 text-[10px] font-black uppercase tracking-widest text-foreground hover:bg-muted disabled:opacity-40"
          >
            <Play className="h-3.5 w-3.5" />
            Run
          </button>
        )}
        {running && (
          <button
            onClick={onStop}
            disabled={stopping}
            className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-3 py-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-40"
          >
            <Square className="h-3.5 w-3.5" />
            Stop
          </button>
        )}
      </div>

      {(log?.logs || project.last_error) && (
        <div className="rounded-xl border border-border bg-background/70 overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <Terminal className="h-3.5 w-3.5 text-primary" />
            <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">
              Runtime Log
            </span>
          </div>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap p-3 text-[11px] leading-5 text-foreground/80">
            {project.last_error || log?.logs}
          </pre>
        </div>
      )}
    </div>
  )
}
