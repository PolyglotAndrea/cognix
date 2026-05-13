import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ScrollText, Filter, CheckCircle2, XCircle, Shield } from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

interface AuditEntry {
  id: number
  user_id?: string | null
  agent_id?: string | null
  operation: string
  access_level: string
  permission_mode: string
  decision: string
  reason: string
  created_at: string
}

interface AuditLogProps {
  workspaceId: string
}

export function AuditLog({ workspaceId }: AuditLogProps) {
  const [decisionFilter, setDecisionFilter] = useState<string | null>(null)

  const { data: entries = [], isLoading } = useQuery<AuditEntry[]>({
    queryKey: ['audit-log', workspaceId, decisionFilter],
    queryFn: () => {
      const params: Record<string, string | number> = { limit: 50 }
      if (decisionFilter) params.decision = decisionFilter
      return api
        .get(`/workspaces/${workspaceId}/audit-log`, { params })
        .then((r) => r.data)
    },
    enabled: !!workspaceId,
    refetchInterval: 10000,
  })

  return (
    <div className="p-4 space-y-3">
      {/* Filter */}
      <div className="flex items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-muted-foreground" />
        {[null, 'allowed', 'denied'].map((d) => (
          <button
            key={d ?? 'all'}
            onClick={() => setDecisionFilter(d)}
            className={cn(
              'px-2 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all',
              decisionFilter === d
                ? 'bg-primary/10 text-primary border border-primary/20'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted border border-transparent',
            )}
          >
            {d ?? 'All'}
          </button>
        ))}
      </div>

      {/* Entries */}
      {isLoading ? (
        <div className="py-20 text-center">
          <ScrollText className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
            Loading Audit Log
          </p>
        </div>
      ) : entries.length === 0 ? (
        <div className="py-20 text-center">
          <ScrollText className="h-8 w-8 text-muted-foreground/20 mx-auto mb-4" />
          <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
            No Audit Entries
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Policy decisions will appear here as agents perform operations.
          </p>
        </div>
      ) : (
        entries.map((entry) => (
          <div
            key={entry.id}
            className="rounded-xl border border-border bg-card/40 p-3 space-y-2"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {entry.decision === 'allowed' ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 text-rose-500" />
                )}
                <span className="text-xs font-bold text-foreground">{entry.operation}</span>
              </div>
              <span
                className={cn(
                  'px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border',
                  entry.decision === 'allowed'
                    ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20'
                    : 'text-rose-500 bg-rose-500/10 border-rose-500/20',
                )}
              >
                {entry.decision}
              </span>
            </div>
            <div className="flex items-center gap-3 text-[9px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <Shield className="h-2.5 w-2.5" />
                {entry.access_level}
              </span>
              <span>{entry.permission_mode}</span>
              {entry.agent_id && <span>agent: {entry.agent_id}</span>}
              <span className="ml-auto">
                {new Date(entry.created_at).toLocaleString()}
              </span>
            </div>
            {entry.reason && (
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                {entry.reason}
              </p>
            )}
          </div>
        ))
      )}
    </div>
  )
}
