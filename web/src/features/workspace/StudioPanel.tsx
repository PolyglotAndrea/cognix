import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  MessageSquareWarning,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { ArtifactPanel } from './ArtifactPanel'
import { useWorkspaceStore } from './store'

interface ApprovalRequest {
  id: string
  kind: string
  status: string
  reason: string
  tool_name: string
}

export function StudioPanel({
  workspaceId,
  onCreateFromStudio: _onCreateFromStudio,
}: {
  workspaceId: string
  onCreateFromStudio: (intent: string) => void
}) {
  const activeChatId = useWorkspaceStore((state) => state.activeNotebookChatId)
  const { data: approvals = [] } = useQuery<ApprovalRequest[]>({
    queryKey: ['approvals', workspaceId, activeChatId],
    queryFn: () =>
      api
        .get('/approvals', {
          params: {
            workspace_id: workspaceId,
            chat_id: activeChatId,
            include_resolved: false,
          },
        })
        .then((r) => r.data),
    enabled: !!workspaceId && !!activeChatId,
    refetchOnWindowFocus: false,
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
        </div>

        <div className="min-h-[420px] border-t border-border/60">
          <ArtifactPanel workspaceId={workspaceId} />
        </div>
      </div>
    </aside>
  )
}
