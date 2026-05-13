import { useQuery } from '@tanstack/react-query'
import {
  Bot,
  Activity,
  AlertTriangle,
  MessageSquare,
  RefreshCw,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

interface BotHealth {
  bot_id: string
  message_count: number
  error_count: number
  error_rate: number
  avg_latency_ms: number
  p95_latency_ms: number
  last_success_at?: string | null
  last_error_at?: string | null
}

interface DeadLetter {
  id: number
  bot_id: string
  provider: string
  sender: string
  message_text: string
  error: string
  attempts: number
  status: string
  created_at: string
}

interface BotHealthPanelProps {
  workspaceId?: string
}

export function BotHealthPanel(_props: BotHealthPanelProps) {
  const { data: healthList = [], isLoading: healthLoading } = useQuery<BotHealth[]>({
    queryKey: ['bot-health'],
    queryFn: () => api.get('/bots/health').then((r) => r.data),
    refetchInterval: 10000,
  })

  const { data: deadLetters = [] } = useQuery<DeadLetter[]>({
    queryKey: ['bot-dead-letters'],
    queryFn: () => api.get('/bots/dead-letters').then((r) => r.data).catch(() => []),
    refetchInterval: 15000,
  })

  const retryMutation = async (dlqId: number) => {
    await api.post(`/bots/dead-letters/${dlqId}/retry`)
  }

  return (
    <div className="p-4 space-y-4">
      {/* Health metrics */}
      <h4 className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
        Bot Health
      </h4>

      {healthLoading ? (
        <div className="py-12 text-center">
          <Activity className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto" />
        </div>
      ) : healthList.length === 0 ? (
        <div className="py-12 text-center">
          <Bot className="h-8 w-8 text-muted-foreground/20 mx-auto mb-3" />
          <p className="text-xs text-muted-foreground">No bot health data yet.</p>
        </div>
      ) : (
        healthList.map((h) => (
          <div
            key={h.bot_id}
            className="rounded-xl border border-border bg-card/40 p-3 space-y-2"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bot className="h-3.5 w-3.5 text-primary" />
                <span className="text-xs font-bold text-foreground">{h.bot_id}</span>
              </div>
              <div
                className={cn(
                  'w-2 h-2 rounded-full',
                  h.error_rate > 0.5
                    ? 'bg-rose-500'
                    : h.error_rate > 0.1
                      ? 'bg-amber-500'
                      : 'bg-emerald-500',
                )}
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-lg bg-muted/30 p-2 border border-border/50">
                <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                  Messages
                </div>
                <div className="text-sm font-black text-foreground">
                  {h.message_count}
                </div>
              </div>
              <div className="rounded-lg bg-muted/30 p-2 border border-border/50">
                <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                  Error Rate
                </div>
                <div
                  className={cn(
                    'text-sm font-black',
                    h.error_rate > 0.5
                      ? 'text-rose-500'
                      : h.error_rate > 0.1
                        ? 'text-amber-500'
                        : 'text-emerald-500',
                  )}
                >
                  {(h.error_rate * 100).toFixed(1)}%
                </div>
              </div>
              <div className="rounded-lg bg-muted/30 p-2 border border-border/50">
                <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                  Avg Latency
                </div>
                <div className="text-sm font-black text-foreground">
                  {h.avg_latency_ms.toFixed(0)}ms
                </div>
              </div>
              <div className="rounded-lg bg-muted/30 p-2 border border-border/50">
                <div className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
                  P95 Latency
                </div>
                <div className="text-sm font-black text-foreground">
                  {h.p95_latency_ms.toFixed(0)}ms
                </div>
              </div>
            </div>

            {h.last_error_at && (
              <div className="flex items-center gap-1.5 text-[9px] text-rose-500">
                <AlertTriangle className="h-2.5 w-2.5" />
                Last error: {new Date(h.last_error_at).toLocaleString()}
              </div>
            )}
          </div>
        ))
      )}

      {/* Dead Letter Queue */}
      {deadLetters.length > 0 && (
        <>
          <h4 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mt-4">
            Dead Letter Queue
          </h4>
          {deadLetters.map((dl) => (
            <div
              key={dl.id}
              className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-3 space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-3.5 w-3.5 text-rose-500" />
                  <span className="text-xs font-bold text-foreground">{dl.bot_id}</span>
                  <span className="text-[9px] text-muted-foreground">{dl.provider}</span>
                </div>
                <button
                  onClick={() => retryMutation(dl.id)}
                  className="flex items-center gap-1 text-[10px] font-bold text-primary hover:underline"
                >
                  <RefreshCw className="h-3 w-3" />
                  Retry
                </button>
              </div>
              <p className="text-[10px] text-muted-foreground line-clamp-2">
                {dl.message_text}
              </p>
              <p className="text-[10px] text-rose-500/80">{dl.error}</p>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
