import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ShieldQuestion,
  ShieldCheck,
  FileText,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { useWorkspaceStore } from './store'
import { Panel, PanelBody } from '@/shared/ui'
import { ArtifactPanel } from './ArtifactPanel'
import type { DragHandleProps } from './types'
import { useCurrentWorkspace } from './useCurrentWorkspace'

interface ApprovalRequest {
  id: string
  agent_id: string
  workspace_id?: string | null
  tool_name: string
  arguments: Record<string, unknown>
  access_level: string
  reason: string
  status: 'pending' | 'approved' | 'rejected' | 'completed'
  kind?: 'tool_permission' | 'plan_confirmation' | 'question'
  response?: string
  result?: string
  metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export function RightPanel({ dragHandleProps: _dragHandleProps }: { dragHandleProps?: DragHandleProps }) {
  const queryClient = useQueryClient()
  const {
    addLog,
    addToolResult,
  } = useWorkspaceStore()
  
  const { workspaceId } = useCurrentWorkspace()
  
  const { data: approvals = [] } = useQuery<ApprovalRequest[]>({
    queryKey: ['approvals', workspaceId],
    queryFn: () =>
      api
        .get('/approvals', { params: { workspace_id: workspaceId, include_resolved: true } })
        .then((r) => r.data),
    enabled: !!workspaceId,
    refetchInterval: 5000,
  })

  const approvalMutation = useMutation({
    mutationFn: async ({
      approval,
      action,
      response,
    }: {
      approval: ApprovalRequest
      action: 'approve' | 'reject' | 'respond'
      response?: string
    }): Promise<unknown> => {
      if (action === 'approve' || action === 'respond') {
        if (
          action === 'respond' &&
          approval.kind === 'question' &&
          approval.metadata?.source === 'plan_apply'
        ) {
          return api.post(
            `/approvals/${approval.id}/${action}`,
            response ? { response } : undefined,
          )
        }
        // Approve/respond, then auto-resume in one click
        await api.post(
          `/approvals/${approval.id}/${action}`,
          response ? { response } : undefined,
        )
        const resumeEndpoint =
          approval.metadata?.runtime === 'claude-agent-sdk'
            ? `/approvals/${approval.id}/resume/stream`
            : `/approvals/${approval.id}/resume-and-continue/stream`
        return streamResumeAfterApproval(
          resumeEndpoint,
          response,
          addLog,
          addToolResult,
        )
      }
      return api.post(`/approvals/${approval.id}/${action}`, response ? { response } : undefined)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approvals', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-events', workspaceId] })
    },
  })

  const pendingApprovals = approvals.filter((a) => a.status === 'pending')

  return (
    <Panel className="w-full min-w-0 shrink-0 border-l border-r-0 border-border bg-card/50 backdrop-blur-xl h-full flex flex-col shadow-2xl overflow-hidden p-0">
      {/* Main Content Pane */}
      <div className="flex-1 flex flex-col min-w-0 bg-transparent h-full overflow-hidden">
        {/* Header */}
        <div className="h-14 border-b border-border/50 px-4 flex items-center justify-between bg-card shrink-0 select-none">
          <div className="flex items-center gap-2.5">
            <FileText className="h-4.5 w-4.5 text-primary" />
            <span className="text-sm font-black uppercase tracking-wider text-foreground">Studio</span>
          </div>
          
          <div className="flex items-center gap-2">
            {/* Status Indicator */}
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" title="System Operational" />
          </div>
        </div>

        {/* Content Body */}
        <PanelBody className="flex-1 overflow-hidden p-0 bg-transparent">
          <div className="h-full overflow-y-auto scrollbar-hide flex flex-col">
            {/* Pending Approvals Inline Queue */}
            {pendingApprovals.length > 0 && (
              <div className="p-4 space-y-3 bg-amber-500/5 border-b border-border/50 shrink-0 animate-in fade-in slide-in-from-top duration-300">
                <div className="flex items-center gap-2">
                  <ShieldQuestion className="h-4 w-4 text-amber-500 animate-pulse" />
                  <span className="text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-400">
                    Action Required ({pendingApprovals.length})
                  </span>
                </div>
                <div className="space-y-3">
                  {pendingApprovals.map((approval) => (
                    <ApprovalCard
                      key={approval.id}
                      approval={approval}
                      busy={approvalMutation.isPending}
                      onAction={(action, response) =>
                        approvalMutation.mutate({ approval, action, response })
                      }
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Artifacts Panel (Outputs Stream / Notebook Guides Grid) */}
            {workspaceId && (
              <div className="flex-1 overflow-y-auto relative scrollbar-hide">
                <ArtifactPanel workspaceId={workspaceId} />
              </div>
            )}
          </div>
        </PanelBody>
      </div>
    </Panel>
  )
}



function ApprovalCard({
  approval,
  busy,
  onAction,
}: {
  approval: ApprovalRequest
  busy: boolean
  onAction: (action: 'approve' | 'reject' | 'respond', response?: string) => void
}) {
  const [response, setResponse] = useState(approval.response || '')
  const isPending = approval.status === 'pending'
  const isQuestion = approval.kind === 'question'
  const isPlan = approval.kind === 'plan_confirmation'
  const args = JSON.stringify(approval.arguments || {}, null, 2)
  const kindLabel = isQuestion ? 'Question' : isPlan ? 'Plan' : 'Tool'
  const statusLabel = approvalStatusLabel(approval, busy)
  const primaryLabel = isQuestion ? 'Answer' : isPlan ? 'Confirm Plan' : 'Approve Tool'
  
  return (
    <div className={`rounded-2xl border transition-all duration-300 p-4 shadow-sm hover:shadow-md ${
      isPending 
        ? 'border-amber-500/30 bg-amber-500/5 ring-1 ring-amber-500/10' 
        : 'border-border bg-card/40'
    }`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <div className={`p-1.5 rounded-lg ${isPlan ? 'bg-indigo-500/10 text-indigo-500' : 'bg-amber-500/10 text-amber-500'}`}>
              {isPlan ? <ShieldCheck className="h-4 w-4" /> : <ShieldQuestion className="h-4 w-4" />}
            </div>
            <span className="truncate text-sm font-bold text-foreground">{approval.tool_name}</span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-border">{approval.id}</span>
            <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground/60">
              {kindLabel}
            </span>
          </div>
        </div>
        <div className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-widest border ${
          approval.status === 'pending' ? 'bg-amber-500/10 text-amber-500 border-amber-500/20' :
          approval.status === 'approved' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' :
          'bg-muted text-muted-foreground border-border'
        }`}>
          {approval.status}
        </div>
      </div>

      <div className="mb-4 p-3 rounded-xl bg-background/50 border border-border/50">
        <div className="flex items-center gap-2 mb-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
          <div className="text-[10px] font-bold uppercase tracking-widest text-foreground/80">{statusLabel}</div>
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">{approval.reason}</p>
      </div>

      {isQuestion && isPending && (
        <div className="mb-4">
          <textarea
            value={response}
            onChange={(event) => setResponse(event.target.value)}
            className="min-h-24 w-full resize-none rounded-xl border border-border bg-background/80 p-3 text-xs leading-5 text-foreground outline-none transition-all focus:ring-2 focus:ring-primary/20 focus:border-primary shadow-inner"
            placeholder="Provide the information requested..."
          />
        </div>
      )}

      {!isPending && (approval.response || approval.result) && (
        <div className="mb-4 space-y-2">
          {approval.response && (
            <div className="p-3 rounded-xl bg-primary/5 border border-primary/10 text-xs text-primary font-medium">
              <span className="text-[9px] font-black uppercase tracking-widest block mb-1 opacity-60">Human Response</span>
              {approval.response}
            </div>
          )}
          {approval.result && (
            <pre className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/10 text-[10px] font-mono text-emerald-600 dark:text-emerald-400 overflow-auto max-h-32 scrollbar-hide">
              <span className="text-[9px] font-black uppercase tracking-widest block mb-1 opacity-60">Result</span>
              {approval.result}
            </pre>
          )}
        </div>
      )}

      {!isPending && approval.metadata && ((approval.metadata.resume_token as string) || (approval.metadata.session_id as string)) && (
        <div className="mb-4 p-3 rounded-xl bg-muted/30 border border-border/50">
          <div className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1.5">Resume Info</div>
          <div className="flex flex-wrap gap-2">
            {(approval.metadata.resume_token as string) && (
              <span className="font-mono text-[10px] text-muted-foreground bg-background px-1.5 py-0.5 rounded border border-border truncate max-w-[200px]">
                token: {String(approval.metadata.resume_token)}
              </span>
            )}
            {(approval.metadata.session_id as string) && (
              <span className="font-mono text-[10px] text-muted-foreground bg-background px-1.5 py-0.5 rounded border border-border truncate max-w-[200px]">
                session: {String(approval.metadata.session_id)}
              </span>
            )}
          </div>
        </div>
      )}

      {isPending && (
        <pre className="mb-4 max-h-32 overflow-auto rounded-xl border border-border bg-muted/30 p-3 font-mono text-[10px] leading-relaxed text-muted-foreground scrollbar-hide">
          <div className="text-[9px] font-black uppercase tracking-widest mb-1 opacity-60 border-b border-border/50 pb-1">Parameters</div>
          {args}
        </pre>
      )}

      {isPending && (
        <div className="flex items-center gap-2 mt-2">
          <button
            onClick={() => (isQuestion ? onAction('respond', response) : onAction('approve'))}
            disabled={busy || (isQuestion && !response.trim())}
            className="flex-1 h-9 rounded-xl bg-emerald-500 px-3 text-[11px] font-bold uppercase tracking-wider text-white transition-all hover:bg-emerald-600 active:scale-95 disabled:opacity-50 shadow-lg shadow-emerald-500/20"
          >
            {primaryLabel}
          </button>
          <button
            onClick={() => onAction('reject')}
            disabled={busy}
            className="flex-1 h-9 rounded-xl bg-rose-500 px-3 text-[11px] font-bold uppercase tracking-wider text-white transition-all hover:bg-rose-600 active:scale-95 disabled:opacity-50 shadow-lg shadow-rose-500/20"
          >
            Reject
          </button>
        </div>
      )}
    </div>
  )
}

function approvalStatusLabel(approval: ApprovalRequest, busy: boolean) {
  if (busy && approval.status === 'approved') return 'Continuing task from approval checkpoint'
  if (approval.status === 'completed') return 'Continuation completed'
  if (approval.status === 'rejected') return 'Rejected by human reviewer'
  if (approval.status === 'approved') return 'Approved and ready to resume'
  if (approval.kind === 'question') return 'Waiting for human answer'
  if (approval.kind === 'plan_confirmation') return 'Waiting for plan confirmation'
  return 'Waiting for tool permission'
}

async function streamResumeAfterApproval(
  resumeEndpoint: string,
  response: string | undefined,
  addLog: (log: { id: string; level: 'info' | 'warn' | 'error'; message: string; timestamp: number }) => void,
  addToolResult: (result: {
    id: string
    name: string
    args?: Record<string, unknown>
    result: unknown
    timestamp: number
  }) => void
) {
  const token = useAuthStore.getState().token
  const stream = await fetch(resumeEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(response ? { response } : {}),
  })
  if (!stream.ok) throw new Error(`HTTP ${stream.status}`)

  const reader = stream.body?.getReader()
  if (!reader) throw new Error('No approval resume stream')

  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const text = decoder.decode(value, { stream: true })
    for (const line of text.split('\n')) {
      if (!line.startsWith('data: ')) continue
      const jsonStr = line.slice(6).trim()
      if (!jsonStr) continue

      let event: { type?: string; delta?: string; name?: string; args?: Record<string, unknown>; result?: unknown; reason?: string; tool_name?: string; message?: string; error?: string }
      try {
        event = JSON.parse(jsonStr)
      } catch {
        continue
      }
      if (event.type === 'delta' && event.delta) {
        addLog({
          id: '',
          level: 'info',
          message: `Agent resumed: ${String(event.delta).slice(0, 140)}`,
          timestamp: Date.now(),
        })
      } else if (event.type === 'tool_call') {
        addLog({
          id: '',
          level: 'info',
          message: `Agent calling tool: ${event.name}`,
          timestamp: Date.now(),
        })
      } else if (event.type === 'tool_result') {
        addToolResult({
          id: '',
          name: event.name ?? '',
          args: event.args,
          result: event.result,
          timestamp: Date.now(),
        })
      } else if (event.type === 'approval_request') {
        addLog({
          id: '',
          level: 'warn',
          message: `Agent requested another approval: ${event.reason || event.tool_name || ''}`,
          timestamp: Date.now(),
        })
      } else if (event.type === 'error') {
        addLog({
          id: '',
          level: 'error',
          message: event.message || event.error || 'Agent resume failed',
          timestamp: Date.now(),
        })
      }
    }
  }
}
