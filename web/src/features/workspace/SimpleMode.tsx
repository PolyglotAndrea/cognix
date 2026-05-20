import { useEffect, useState, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  MessageSquarePlus,
  Settings,
  Send,
  Loader2,
  Check,
  X,
  Play,
  Cpu,
  Wrench,
  Calendar,
  AlertCircle,
  FileText,
  ChevronRight,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { RichMessage } from '@/shared/ui'
import { WorkspacePlan, ApplyResult } from './types'
import { useWorkspaceStore } from './store'

interface SimpleModeProps {
  workspaceId: string
  onSwitchToAdvanced: () => void
  embedded?: boolean
  requestedIntent?: { id: number; text: string; autoSubmit?: boolean } | null
}

interface StreamStep {
  id: string
  label: string
  status: 'pending' | 'running' | 'done' | 'failed'
}

interface ChatSession {
  id: string
  title: string
  system_prompt: string
  model_profiles: string[]
  metadata: Record<string, unknown>
}

interface StoredMessage {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  metadata?: {
    type?: 'plan' | 'executing' | 'executed'
    plan?: WorkspacePlan
    steps?: StreamStep[]
    applyResult?: ApplyResult
  }
}

interface UIMessage {
  id?: string
  role: 'user' | 'assistant' | 'plan' | 'executing' | 'executed' | 'system' | 'tool'
  content?: string
  plan?: WorkspacePlan
  steps?: StreamStep[]
  applyResult?: ApplyResult
}

export function SimpleMode({
  workspaceId,
  onSwitchToAdvanced,
  embedded = false,
  requestedIntent = null,
}: SimpleModeProps) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const notebookSources = useWorkspaceStore((state) => state.notebookSources)

  const { data: chats = [], isLoading: chatsLoading } = useQuery<ChatSession[]>({
    queryKey: ['workspace-chats', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/chats`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const { data: storedMessages } = useQuery<StoredMessage[]>({
    queryKey: ['workspace-chat-messages', workspaceId, activeChatId],
    queryFn: () =>
      api.get(`/workspaces/${workspaceId}/chats/${activeChatId}/messages`).then((r) => r.data),
    enabled: !!workspaceId && !!activeChatId && !streaming,
  })

  const switchModeMutation = useMutation({
    mutationFn: () =>
      api.patch(`/workspaces/${workspaceId}/settings`, { ui_mode: 'advanced' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace-settings', workspaceId] })
      onSwitchToAdvanced()
    },
  })

  useEffect(() => {
    setActiveChatId(null)
    setMessages([])
  }, [workspaceId])

  useEffect(() => {
    if (activeChatId || chats.length === 0) return
    const simpleChats = chats.filter((c) => c.metadata?.mode === 'simple')
    if (simpleChats.length > 0) {
      setActiveChatId(simpleChats[0].id)
    } else {
      setActiveChatId(chats[0].id)
    }
  }, [activeChatId, chats])

  useEffect(() => {
    if (streaming || !storedMessages) return
    setMessages(
      storedMessages
        .filter((message) => message.role === 'user' || message.role === 'assistant')
        .map((message) => {
          if (message.metadata?.type === 'plan') {
            return {
              id: message.id,
              role: 'plan',
              plan: message.metadata.plan,
            }
          }
          if (message.metadata?.type === 'executing') {
            return {
              id: message.id,
              role: 'executing',
              plan: message.metadata.plan,
              steps: message.metadata.steps || [],
            }
          }
          if (message.metadata?.type === 'executed') {
            return {
              id: message.id,
              role: 'executed',
              content: message.content,
              applyResult: message.metadata.applyResult,
            }
          }
          return { id: message.id, role: message.role, content: message.content }
        })
    )
  }, [storedMessages, streaming])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const createChat = async () => {
    const created = await api
      .post(`/workspaces/${workspaceId}/chats`, {
        title: 'Planner Orchestrator Session',
        metadata: { mode: 'simple' },
      })
      .then((r) => r.data as ChatSession)
    setActiveChatId(created.id)
    setMessages([])
    await queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
    return created.id
  }

  useEffect(() => {
    if (!requestedIntent?.text) return
    setInput(requestedIntent.text)
    if (requestedIntent.autoSubmit) {
      void handleSend(requestedIntent.text)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedIntent?.id])

  const buildSourceContext = () => {
    if (notebookSources.length === 0) return ''
    const lines = notebookSources
      .slice(0, 20)
      .map((source) => `- [${source.kind}] ${source.title}: ${source.subtitle}`)
      .join('\n')
    return `\n\nSelected workspace sources:\n${lines}`
  }

  const handleSend = async (override?: string) => {
    const currentInput = override ?? input
    if (!currentInput.trim() || streaming) return
    const userMsg = currentInput.trim()
    const plannerIntent = `${userMsg}${buildSourceContext()}`
    setInput('')

    let chatId = activeChatId
    try {
      chatId = chatId || (await createChat())
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Failed to initialize chat session.' }])
      return
    }

    // Persist user intent message
    try {
      await api.post(`/workspaces/${workspaceId}/chats/${chatId}/messages/raw`, {
        role: 'user',
        content: userMsg,
        metadata: {
          sources: notebookSources,
        },
      })
    } catch (err) {
      console.error('Failed to persist user message:', err)
    }

    setMessages((prev) => [...prev, { role: 'user', content: userMsg }])
    setStreaming(true)

    // Add loading placeholder
    setMessages((prev) => [...prev, { role: 'assistant', content: 'Analyzing your intent and generating execution plan...' }])

    try {
      const planRes = await api.post(`/workspaces/${workspaceId}/plans`, { intent: plannerIntent })
      const plan = planRes.data as WorkspacePlan

      // Save plan message persistently
      await api.post(`/workspaces/${workspaceId}/chats/${chatId}/messages/raw`, {
        role: 'assistant',
        content: `Proposed plan: ${plan.summary}`,
        metadata: {
          type: 'plan',
          plan,
        },
      })

      // Replace loading state with the plan card
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'plan',
          plan,
        }
        return updated
      })
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail?.reason || err?.message || 'Failed to generate plan.'
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'assistant',
          content: `Planning failed: ${errMsg}`,
        }
        return updated
      })
    } finally {
      setStreaming(false)
    }
  }

  const handleConfirmPlan = async (plan: WorkspacePlan) => {
    if (streaming || !activeChatId) return
    setStreaming(true)

    // Add executing checklist placeholder
    setMessages((prev) => {
      // Find the plan message and turn it into 'executing'
      return prev.map((msg) => {
        if (msg.role === 'plan' && msg.plan?.id === plan.id) {
          return {
            role: 'executing',
            plan,
            steps: [],
          }
        }
        return msg
      })
    })

    const token = useAuthStore.getState().token
    const stepsList: StreamStep[] = []
    let finalApplyResultFromStream: ApplyResult | null = null

    try {
      const resp = await fetch(`/api/v1/workspaces/${workspaceId}/plans/${plan.id}/apply/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      })

      if (!resp.ok) {
        throw new Error(await resp.text())
      }

      const reader = resp.body?.getReader()
      if (!reader) throw new Error('No readable body stream')
      const decoder = new TextDecoder()
      let streamBuffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        streamBuffer += decoder.decode(value, { stream: true })
        const frames = streamBuffer.split('\n\n')
        streamBuffer = frames.pop() || ''

        for (const frame of frames) {
          const jsonStr = frame
            .split('\n')
            .filter((line) => line.startsWith('data: '))
            .map((line) => line.slice(6).trim())
            .join('')
          if (!jsonStr || jsonStr === '[DONE]') continue
          try {
            const event = JSON.parse(jsonStr)
            
            // Map event to visible checklist step
            let stepLabel = ''
            let stepId = ''
            let status: 'pending' | 'running' | 'done' | 'failed' = 'done'

            if (event.type === 'agent.created') {
              stepId = `agent-${event.agent_id || 'new'}`
              stepLabel = 'Prepared a workspace worker for this request'
            } else if (event.type === 'task.created') {
              stepId = `task-${event.task_id || 'new'}`
              stepLabel = 'Prepared the execution task'
            } else if (event.type === 'code_project.created') {
              const projectId = event.data?.id || 'new'
              stepId = `code-project-${projectId}`
              stepLabel = event.data?.preview_url
                ? 'Created and started a runnable app preview'
                : 'Created a sandbox code project'
              status = event.data?.status === 'failed' ? 'failed' : 'done'
            } else if (event.type === 'code_project.started') {
              const projectId = event.data?.id || 'new'
              stepId = `code-project-${projectId}`
              stepLabel = 'Started the app preview'
              status = event.data?.status === 'failed' ? 'failed' : 'done'
            } else if (event.type === 'task.started') {
              stepId = `task-run-${event.task_id || 'run'}`
              stepLabel = 'Running the task'
              status = 'running'
            } else if (event.type === 'tool_call') {
              stepId = `tool-${event.tool}`
              stepLabel = `Using capability: ${event.tool}`
              status = 'running'
            } else if (event.type === 'tool_result') {
              stepId = `tool-${event.tool}`
              stepLabel = `Capability completed: ${event.tool}`
              status = 'done'
            } else if (event.type === 'tool_error') {
              stepId = `tool-${event.tool}`
              stepLabel = `Capability failed: ${event.tool}`
              status = 'failed'
            } else if (event.type === 'execution.completed') {
              stepId = 'execution-done'
              stepLabel = event.result?.status === 'failed'
                ? 'Execution finished with recoverable errors'
                : event.result?.status === 'needs_input'
                ? 'Waiting for your input to continue'
                : 'Execution completed'
              status = event.result?.status === 'failed' ? 'failed' : 'done'
              finalApplyResultFromStream = event.result
            } else if (event.type === 'execution.failed') {
              stepId = 'execution-failed'
              stepLabel = `Execution error: ${event.error || 'unknown error'}`
              status = 'failed'
            }

            if (stepId) {
              const existingIdx = stepsList.findIndex((s) => s.id === stepId)
              if (existingIdx >= 0) {
                stepsList[existingIdx].status = status
                if (stepLabel) stepsList[existingIdx].label = stepLabel
              } else {
                stepsList.push({ id: stepId, label: stepLabel, status })
              }

              // Update the executing message state
              setMessages((prev) =>
                prev.map((msg) => {
                  if (msg.role === 'executing' && msg.plan?.id === plan.id) {
                    return {
                      ...msg,
                      steps: [...stepsList],
                    }
                  }
                  return msg
                })
              )
            }
          } catch {
            // ignore JSON parse errors
          }
        }
      }

      // Query database/plan again or display success execution result
      const applyResultRes = await api.get(`/workspaces/${workspaceId}/plans/${plan.id}`)
      const updatedPlan = applyResultRes.data as WorkspacePlan

      const finalResultText = updatedPlan.steps
        .map((s) => `• **${s.description}**: ${updatedPlan.step_statuses[s.id] || 'pending'}`)
        .join('\n')

      const finalApplyResult: ApplyResult = {
        plan_id: plan.id,
        status: finalApplyResultFromStream?.status || updatedPlan.status,
        created: finalApplyResultFromStream?.created || {},
        execution_results: finalApplyResultFromStream?.execution_results || [],
        artifacts: finalApplyResultFromStream?.artifacts || [],
        code_projects: finalApplyResultFromStream?.created?.code_projects || [],
        approval_ids: finalApplyResultFromStream?.approval_ids || [],
        plan: finalApplyResultFromStream?.plan || updatedPlan,
      }
      const failed = finalApplyResult.status === 'failed'
      const needsInput =
        finalApplyResult.status === 'needs_input' ||
        Boolean(finalApplyResult.approval_ids?.length)
      const firstError =
        finalApplyResult.execution_results?.find((item) => item.error)?.error ||
        (failed ? 'The workflow could not complete with the current configuration.' : '')
      const resultContent = failed
        ? `Execution needs attention.\n\n${firstError}\n\nRecommended next step: review the highlighted issue, adjust the source/provider/capability access if needed, then run the plan again.`
        : needsInput
        ? `I need a bit more information before continuing.\n\n${finalResultText}\n\nOpen Needs Input on the right and provide the requested details.`
        : `Execution completed.\n\n${finalResultText}`

      // Save raw final result to backend
      await api.post(`/workspaces/${workspaceId}/chats/${activeChatId}/messages/raw`, {
        role: 'assistant',
        content: resultContent,
        metadata: {
          type: 'executed',
          applyResult: finalApplyResult,
        },
      })

      // Replace executing checklist with completed details
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.role === 'executing' && msg.plan?.id === plan.id) {
            return {
              role: 'executed',
              content: resultContent,
              applyResult: finalApplyResult,
            }
          }
          return msg
        })
      )
      queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['code-projects', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['approvals', workspaceId] })
      if (needsInput) {
        const workspaceStore = useWorkspaceStore.getState()
        workspaceStore.setRightPanelTab('approvals')
        workspaceStore.setRightPanelOpen(true)
      } else if (finalApplyResult.artifacts && finalApplyResult.artifacts.length > 0) {
        const workspaceStore = useWorkspaceStore.getState()
        workspaceStore.setRightPanelTab('artifacts')
        workspaceStore.setRightPanelOpen(true)
      } else if (finalApplyResult.code_projects && finalApplyResult.code_projects.length > 0) {
        const workspaceStore = useWorkspaceStore.getState()
        workspaceStore.setRightPanelTab('apps')
        workspaceStore.setRightPanelOpen(true)
      }
    } catch (err: any) {
      const errMsg = err?.message || 'Plan execution failed.'
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.role === 'executing' && msg.plan?.id === plan.id) {
            return {
              role: 'assistant',
              content: `Plan execution failed: ${errMsg}`,
            }
          }
          return msg
        })
      )
    } finally {
      setStreaming(false)
      // Refresh workspace data
      queryClient.invalidateQueries({ queryKey: ['workspace-settings', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-chat-messages', workspaceId, activeChatId] })
    }
  }

  const handleRejectPlan = async (plan: WorkspacePlan) => {
    if (streaming || !activeChatId) return
    try {
      await api.post(`/workspaces/${workspaceId}/plans/${plan.id}/reject`)
      
      // Update persistent chat
      await api.post(`/workspaces/${workspaceId}/chats/${activeChatId}/messages/raw`, {
        role: 'assistant',
        content: 'Proposed execution plan rejected.',
      })

      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.role === 'plan' && msg.plan?.id === plan.id) {
            return {
              role: 'assistant',
              content: 'Execution plan rejected.',
            }
          }
          return msg
        })
      )
    } catch (err) {
      console.error(err)
    }
  }

  return (
    <div className={`${embedded ? 'h-full' : 'h-screen'} flex flex-col bg-background text-foreground overflow-hidden`}>
      {/* Header */}
      {!embedded && (
      <div className="flex items-center justify-between px-6 py-4 border-b border-border/80 bg-card/60 backdrop-blur-xl shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
          </div>
          <div>
            <span className="text-sm font-black tracking-tight text-foreground">Cognix Command Center</span>
            <span className="text-[10px] ml-2 font-semibold uppercase tracking-wider text-primary bg-primary/10 px-2 py-0.5 rounded-full">
              Intent First
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => switchModeMutation.mutate()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border bg-background hover:bg-card/50 text-xs font-bold text-muted-foreground hover:text-foreground transition-all duration-200"
        >
          <Settings className="h-3.5 w-3.5" />
          Switch to Advanced
        </button>
      </div>
      )}

      {/* Chat Tabs / Sessions */}
      <div className="border-b border-border/60 bg-card/30 px-6 py-2.5 shrink-0">
        <div className="mx-auto flex w-full max-w-3xl items-center gap-3 overflow-x-auto scrollbar-hide">
          <span className="shrink-0 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            Sessions
          </span>
          {chats
            .filter((chat) => chat.metadata?.mode === 'simple')
            .map((chat) => (
              <button
                key={chat.id}
                type="button"
                onClick={() => {
                  setActiveChatId(chat.id)
                  setMessages([])
                }}
                className={`max-w-[160px] shrink-0 truncate rounded-xl border px-3.5 py-1.5 text-xs font-bold transition-all ${
                  chat.id === activeChatId
                    ? 'border-primary/45 bg-primary/10 text-primary shadow-sm'
                    : 'border-border bg-background/50 text-muted-foreground hover:text-foreground hover:bg-background'
                }`}
                title={chat.title}
              >
                {chat.title}
              </button>
            ))}
          {chats.filter((chat) => chat.metadata?.mode === 'simple').length === 0 && (
            <span className="shrink-0 rounded-xl border border-dashed border-border px-3.5 py-1.5 text-xs font-bold text-muted-foreground/60">
              {chatsLoading ? 'Loading sessions...' : 'No orchestrator sessions'}
            </span>
          )}
          <button
            type="button"
            onClick={() => createChat()}
            className="ml-auto flex h-8 shrink-0 items-center gap-1.5 rounded-xl border border-border bg-background px-3 text-xs font-bold text-muted-foreground transition-colors hover:text-foreground hover:bg-card"
          >
            <MessageSquarePlus className="h-4 w-4" />
            New Session
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-8 space-y-6 max-w-3xl mx-auto w-full scrollbar-thin">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-[70%] text-center max-w-md mx-auto">
            <div className="w-16 h-16 rounded-3xl bg-primary/10 flex items-center justify-center mb-5 animate-pulse">
              <Cpu className="h-8 w-8 text-primary" />
            </div>
            <h3 className="text-base font-black text-foreground mb-2">What is your goal?</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Describe the outcome you need. Cognix will analyze the request, choose the right internal capabilities, ask for confirmation when needed, and return a structured result.
            </p>
          </div>
        )}

        {messages.map((msg, i) => {
          if (msg.role === 'user') {
            return (
              <div key={i} className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-3 text-sm leading-relaxed text-primary-foreground font-semibold shadow-sm">
                  <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                </div>
              </div>
            )
          }

          if (msg.role === 'assistant') {
            return (
              <div key={i} className="flex justify-start">
                <div className="max-w-[80%] rounded-2xl bg-card border border-border px-4 py-3 text-sm leading-relaxed text-foreground shadow-sm">
                  {msg.content ? (
                    <RichMessage content={msg.content} compact />
                  ) : (
                    <div className="flex gap-1.5 py-1.5 items-center">
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      <span className="text-xs text-muted-foreground animate-pulse">Thinking...</span>
                    </div>
                  )}
                </div>
              </div>
            )
          }

          if (msg.role === 'plan' && msg.plan) {
            const plan = msg.plan
            return (
              <div key={i} className="flex justify-start w-full">
                <div className="w-full max-w-2xl bg-card border border-border/80 backdrop-blur-md rounded-2xl p-5 shadow-lg space-y-4 hover:border-primary/20 transition-all duration-300">
                  <div className="flex items-start justify-between border-b border-border/60 pb-3">
                    <div>
                      <h4 className="text-sm font-black tracking-tight text-foreground">Recommended Approach</h4>
                      <p className="text-[10px] text-muted-foreground mt-0.5">Review what Cognix will do before running.</p>
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-wider bg-primary/10 text-primary px-2.5 py-1 rounded-full border border-primary/20">
                      {plan.intent_type || 'Automation'}
                    </span>
                  </div>

                  <p className="text-sm text-foreground/95 leading-relaxed font-semibold">{plan.summary}</p>

                  {/* Components discovered & recommended */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 pt-1">
                    {/* Recommended work mode */}
                    {plan.recommended_agents && plan.recommended_agents.length > 0 && (
                      <div className="rounded-xl border border-border/60 bg-background/50 p-3">
                        <div className="flex items-center gap-1.5 text-xs font-black text-muted-foreground mb-2 uppercase tracking-wider">
                          <Cpu className="h-3.5 w-3.5 text-primary" />
                          Work Mode
                        </div>
                        <div className="space-y-2">
                          {plan.recommended_agents.map((agent: any, idx: number) => (
                            <div key={idx} className="flex flex-col gap-0.5 p-2 bg-card rounded-lg border border-border/40">
                              <span className="text-xs font-bold text-foreground">
                                {agent.role || agent.name || 'Workspace operator'}
                              </span>
                              <span className="text-[10px] text-muted-foreground leading-normal">
                                {agent.reason || agent.description || 'Handles planning, execution, and output preparation.'}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Capabilities & Skills & MCP */}
                    {((plan.recommended_skills && plan.recommended_skills.length > 0) ||
                      (plan.recommended_mcp_tools && plan.recommended_mcp_tools.length > 0)) && (
                      <div className="rounded-xl border border-border/60 bg-background/50 p-3">
                        <div className="flex items-center gap-1.5 text-xs font-black text-muted-foreground mb-2 uppercase tracking-wider">
                          <Wrench className="h-3.5 w-3.5 text-primary" />
                          Available Help
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {plan.recommended_skills?.map((skill: any, idx: number) => (
                            <span key={idx} className="text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 px-2 py-0.5 rounded-md">
                              {skill.name}
                            </span>
                          ))}
                          {plan.recommended_mcp_tools?.map((tool: any, idx: number) => (
                            <span key={idx} className="text-[10px] font-semibold bg-amber-500/10 text-amber-600 border border-amber-500/20 px-2 py-0.5 rounded-md">
                              {tool.name || tool.tool || tool.server}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Scheduling if applicable */}
                  {plan.scheduling && Object.keys(plan.scheduling).length > 0 && (
                    <div className="flex items-center gap-2 p-2.5 bg-primary/5 rounded-xl border border-primary/10 text-xs">
                      <Calendar className="h-4 w-4 text-primary shrink-0" />
                      <div>
                        <span className="font-bold text-foreground">Timing: </span>
                        <span className="text-muted-foreground">
                          {String(plan.scheduling.cron || plan.scheduling.interval || 'Once')} - {String(plan.scheduling.reason || '')}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div className="flex items-center gap-2 pt-2 border-t border-border/60">
                    <button
                      onClick={() => handleConfirmPlan(plan)}
                      disabled={streaming}
                      className="flex-1 flex items-center justify-center gap-1.5 bg-primary hover:bg-primary/95 disabled:opacity-50 text-primary-foreground font-black text-xs px-4 py-2.5 rounded-xl transition-all shadow-sm active:scale-95"
                    >
                      <Play className="h-3.5 w-3.5 fill-current" />
                      Run this plan
                    </button>
                    <button
                      onClick={() => handleRejectPlan(plan)}
                      disabled={streaming}
                      className="flex items-center justify-center gap-1.5 border border-border hover:bg-card/80 disabled:opacity-50 text-foreground font-black text-xs px-4 py-2.5 rounded-xl transition-all active:scale-95"
                    >
                      <X className="h-3.5 w-3.5" />
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            )
          }

          if (msg.role === 'executing' && msg.plan) {
            return (
              <div key={i} className="flex justify-start w-full">
                <div className="w-full max-w-2xl bg-card border border-border rounded-2xl p-5 shadow-md space-y-4">
                  <div className="flex items-center justify-between border-b border-border/60 pb-3">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      <h4 className="text-sm font-black text-foreground">Working on it</h4>
                    </div>
                    <span className="text-[10px] text-muted-foreground">Live progress</span>
                  </div>

                  <div className="space-y-2.5">
                    {msg.steps && msg.steps.length > 0 ? (
                      msg.steps.map((step) => (
                        <div key={step.id} className="flex items-center justify-between gap-3 text-xs p-2 rounded-lg bg-background border border-border/40">
                          <span className="font-semibold text-foreground/90">{step.label}</span>
                          <span className="shrink-0 flex items-center">
                            {step.status === 'running' && (
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                            )}
                            {step.status === 'done' && (
                              <Check className="h-3.5 w-3.5 text-emerald-500 font-bold" />
                            )}
                            {step.status === 'failed' && (
                              <AlertCircle className="h-3.5 w-3.5 text-red-500" />
                            )}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="text-xs text-muted-foreground py-2 text-center">
                        Preparing the workspace and starting the run...
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          }

          if (msg.role === 'executed' && msg.applyResult) {
            const result = msg.applyResult
            const isFailed = result.status === 'failed'

            return (
              <div key={i} className="flex justify-start w-full">
                <div className="w-full max-w-2xl bg-card border border-border/80 rounded-2xl p-5 shadow-lg space-y-4">
                  <div className="flex items-center justify-between border-b border-border/60 pb-3">
                    <div className="flex items-center gap-2">
                      {isFailed ? (
                        <AlertCircle className="h-5 w-5 text-red-500" />
                      ) : (
                        <div className="h-5 w-5 rounded-full bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
                          <Check className="h-3 w-3 text-emerald-600 font-bold" />
                        </div>
                      )}
                      <h4 className="text-sm font-black text-foreground">
                        {isFailed ? 'Execution Interrupted' : 'Execution Completed'}
                      </h4>
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="text-sm leading-relaxed whitespace-pre-wrap font-semibold text-foreground/90">
                      {isFailed
                        ? msg.content || 'The run needs attention. Review the issue below and retry after fixing the configuration or source access.'
                        : msg.content || 'The requested work completed and the output is ready.'}
                    </div>

                    {/* Step statuses */}
                    {result.plan && result.plan.step_statuses && (
                      <div className="rounded-xl border border-border/60 bg-background/50 p-3 space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">Run Summary</span>
                        <div className="space-y-1.5">
                          {result.plan.steps.map((step) => {
                            const status = result.plan?.step_statuses[step.id] || 'pending'
                            return (
                              <div key={step.id} className="flex items-center justify-between text-xs py-1 px-1.5 rounded hover:bg-card">
                                <span className="text-muted-foreground font-medium">{step.description}</span>
                                <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-full ${
                                  status === 'completed' || status === 'success'
                                    ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20'
                                    : status === 'failed'
                                    ? 'bg-red-500/10 text-red-600 border border-red-500/20'
                                    : 'bg-muted text-muted-foreground'
                                }`}>
                                  {status}
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    {/* Artifact output Section */}
                    {result.artifacts && result.artifacts.length > 0 && (
                      <div className="rounded-xl border border-border/60 bg-background/50 p-3.5 space-y-3">
                        <div className="flex items-center gap-1.5 text-xs font-black text-foreground uppercase tracking-wider">
                          <FileText className="h-4 w-4 text-primary" />
                          Output Artifacts
                        </div>
                        <div className="grid grid-cols-1 gap-2">
                          {result.artifacts.map((artifact, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => {
                                const workspaceStore = useWorkspaceStore.getState()
                                workspaceStore.setRightPanelTab('artifacts')
                                workspaceStore.setRightPanelOpen(true)
                              }}
                              className="flex items-center justify-between p-2.5 bg-card hover:bg-card/85 rounded-lg border border-border/40 text-xs font-bold text-primary transition-all active:scale-[0.99] group shadow-sm"
                            >
                              <div className="flex items-center gap-2 truncate">
                                <FileText className="h-4 w-4 text-muted-foreground" />
                                <span className="truncate text-foreground group-hover:text-primary transition-colors">{artifact}</span>
                              </div>
                              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground group-hover:translate-x-0.5 transition-transform" />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          }

          return null
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="border-t border-border/60 bg-card/60 backdrop-blur-xl p-4 shrink-0">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Describe your workspace automation goal..."
            disabled={streaming}
            className="flex-1 rounded-xl border border-border/80 bg-background px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground/60 outline-none focus:ring-2 focus:ring-primary/25 focus:border-primary disabled:opacity-60 shadow-inner"
          />
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || streaming}
            className="w-11 h-11 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:bg-primary/95 transition-all active:scale-95 disabled:opacity-50 shadow-md shadow-primary/10 shrink-0"
          >
            {streaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4.5 w-4.5 fill-current" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
