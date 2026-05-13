import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Server,
  Cpu,
  Clock,
  ArrowDownToLine,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

interface WorkerNode {
  id: string
  hostname: string
  ip_address: string
  capabilities: Record<string, unknown>
  max_concurrent: number
  current_load: number
  status: string
  last_heartbeat?: string | null
  registered_at?: string | null
}

interface DispatcherStatus {
  running: boolean
  node_id: string
  max_concurrent: number
  active_count: number
  active_task_ids: string[]
  metrics: Record<string, unknown>
}

interface RuntimePanelProps {
  workspaceId?: string
}

export function RuntimePanel(_props: RuntimePanelProps) {
  const queryClient = useQueryClient()

  const { data: workers = [], isLoading: workersLoading } = useQuery<WorkerNode[]>({
    queryKey: ['runtime-workers'],
    queryFn: () => api.get('/runtime/workers').then((r) => r.data),
    refetchInterval: 10000,
  })

  const { data: status } = useQuery<DispatcherStatus>({
    queryKey: ['runtime-status'],
    queryFn: () => api.get('/runtime/status').then((r) => r.data),
    refetchInterval: 5000,
  })

  const drainMutation = useMutation({
    mutationFn: (nodeId: string) =>
      api.post(`/runtime/workers/${nodeId}/drain`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runtime-workers'] })
    },
  })

  const statusColor = (s: string) => {
    if (s === 'active') return 'bg-emerald-500'
    if (s === 'draining') return 'bg-amber-500'
    return 'bg-slate-500'
  }

  return (
    <div className="p-4 space-y-4">
      {/* Dispatcher status */}
      {status && (
        <div className="rounded-xl border border-border bg-card/40 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Cpu className="h-3.5 w-3.5 text-primary" />
              <span className="text-xs font-bold text-foreground">Dispatcher</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div
                className={cn(
                  'w-2 h-2 rounded-full',
                  status.running ? 'bg-emerald-500' : 'bg-slate-500',
                )}
              />
              <span className="text-[10px] font-bold text-muted-foreground">
                {status.running ? 'Running' : 'Stopped'}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <div className="rounded-lg bg-muted/30 p-2 border border-border/50">
              <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                Active
              </div>
              <div className="text-sm font-black text-foreground">
                {status.active_count}/{status.max_concurrent}
              </div>
            </div>
            <div className="rounded-lg bg-muted/30 p-2 border border-border/50">
              <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                Node
              </div>
              <div className="font-mono text-[10px] text-foreground truncate">
                {status.node_id}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Worker nodes */}
      <h4 className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
        Worker Nodes
      </h4>

      {workersLoading ? (
        <div className="py-12 text-center">
          <Server className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto" />
        </div>
      ) : workers.length === 0 ? (
        <div className="py-12 text-center">
          <Server className="h-8 w-8 text-muted-foreground/20 mx-auto mb-3" />
          <p className="text-xs text-muted-foreground">No worker nodes registered.</p>
        </div>
      ) : (
        workers.map((node) => {
          const loadPct =
            node.max_concurrent > 0
              ? Math.round((node.current_load / node.max_concurrent) * 100)
              : 0
          return (
            <div
              key={node.id}
              className="rounded-xl border border-border bg-card/40 p-3 space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className={cn('w-2 h-2 rounded-full', statusColor(node.status))}
                  />
                  <span className="text-xs font-bold text-foreground truncate max-w-[140px]">
                    {node.hostname || node.id}
                  </span>
                </div>
                <span
                  className={cn(
                    'px-1.5 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border',
                    node.status === 'active'
                      ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20'
                      : node.status === 'draining'
                        ? 'text-amber-500 bg-amber-500/10 border-amber-500/20'
                        : 'text-slate-500 bg-slate-500/10 border-slate-500/20',
                  )}
                >
                  {node.status}
                </span>
              </div>

              {/* Load bar */}
              <div>
                <div className="flex items-center justify-between text-[9px] text-muted-foreground mb-1">
                  <span>Load</span>
                  <span>
                    {node.current_load}/{node.max_concurrent} ({loadPct}%)
                  </span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className={cn(
                      'h-full rounded-full transition-all duration-500',
                      loadPct > 80
                        ? 'bg-rose-500'
                        : loadPct > 50
                          ? 'bg-amber-500'
                          : 'bg-emerald-500',
                    )}
                    style={{ width: `${Math.min(loadPct, 100)}%` }}
                  />
                </div>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-[9px] text-muted-foreground">
                  {node.ip_address && (
                    <span className="font-mono">{node.ip_address}</span>
                  )}
                  {node.last_heartbeat && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-2.5 w-2.5" />
                      {new Date(node.last_heartbeat).toLocaleTimeString()}
                    </span>
                  )}
                </div>
                {node.status === 'active' && (
                  <button
                    onClick={() => drainMutation.mutate(node.id)}
                    className="flex items-center gap-1 text-[10px] font-bold text-amber-500 hover:underline"
                  >
                    <ArrowDownToLine className="h-3 w-3" />
                    Drain
                  </button>
                )}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}
