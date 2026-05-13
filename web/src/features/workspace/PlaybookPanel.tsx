import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  BookOpen,
  Rocket,
  ArrowRight,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

interface Playbook {
  id: string
  workspace_id: string
  name: string
  description: string
  source_artifact_id?: string | null
  source_task_id?: string | null
  status: string
  usage_count: number
  created_at: string
  updated_at: string
}

const STATUS_COLORS: Record<string, string> = {
  draft: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  validated: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  promoted: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
}

interface PlaybookPanelProps {
  workspaceId: string
}

export function PlaybookPanel({ workspaceId }: PlaybookPanelProps) {
  const queryClient = useQueryClient()
  const [promotingId, setPromotingId] = useState<string | null>(null)

  const { data: playbooks = [], isLoading } = useQuery<Playbook[]>({
    queryKey: ['playbooks', workspaceId],
    queryFn: () =>
      api.get(`/workspaces/${workspaceId}/playbooks`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const promoteMutation = useMutation({
    mutationFn: (playbookId: string) =>
      api.post(`/playbooks/${playbookId}/promote`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks', workspaceId] })
      setPromotingId(null)
    },
  })

  return (
    <div className="p-4 space-y-3">
      {isLoading ? (
        <div className="py-20 text-center">
          <BookOpen className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
            Loading Playbooks
          </p>
        </div>
      ) : playbooks.length === 0 ? (
        <div className="py-20 text-center">
          <BookOpen className="h-8 w-8 text-muted-foreground/20 mx-auto mb-4" />
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
            No Playbooks
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Extract playbooks from successful artifacts to reuse workflows.
          </p>
        </div>
      ) : (
        playbooks.map((playbook) => (
          <div
            key={playbook.id}
            className="rounded-xl border border-border bg-card/40 p-3 space-y-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-xs font-bold text-foreground truncate">
                  {playbook.name}
                </div>
                {playbook.description && (
                  <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2">
                    {playbook.description}
                  </p>
                )}
              </div>
              <span
                className={cn(
                  'flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border shrink-0',
                  STATUS_COLORS[playbook.status] ?? STATUS_COLORS.draft,
                )}
              >
                {playbook.status}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[9px] text-muted-foreground">
                <span>Used {playbook.usage_count}x</span>
                <span className="w-1 h-1 rounded-full bg-border" />
                <span>{new Date(playbook.updated_at).toLocaleDateString()}</span>
              </div>
              {playbook.status !== 'promoted' && (
                <button
                  onClick={() => {
                    setPromotingId(playbook.id)
                    promoteMutation.mutate(playbook.id)
                  }}
                  disabled={promotingId === playbook.id}
                  className="flex items-center gap-1 text-[10px] font-bold text-primary hover:underline"
                >
                  <Rocket className="h-3 w-3" />
                  Promote to Skill
                  <ArrowRight className="h-2.5 w-2.5" />
                </button>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
