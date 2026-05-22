import { useEffect, useMemo, useState, useRef } from 'react'
import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CircleHelp,
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
  Sparkles,
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

interface ApprovalRequest {
  id: string
  kind: string
  status: string
  reason: string
  tool_name: string
  arguments?: Record<string, unknown>
  response?: string
  result?: string
  metadata?: Record<string, unknown>
}

interface ApprovalSuggestion {
  approval_id: string
  response: string
  reason: string
  score: number
  created_at: string
  source: string
}

interface ConversationRun {
  id: string
  state: string
  chat_id: string
  plan_id?: string
  artifact_ids?: string[]
  intent?: Record<string, unknown>
  requirements?: RunRequirement[]
  updated_at?: string
}

interface RunRequirement {
  id: string
  label: string
  kind: string
  required: boolean
  status: 'pending' | 'answered' | 'skipped'
  approval_id?: string
  step_id?: string
  prompt?: string
  reason?: string
  value?: string
}

export function SimpleMode({
  workspaceId,
  onSwitchToAdvanced,
  embedded = false,
  requestedIntent = null,
}: SimpleModeProps) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [planInputValues, setPlanInputValues] = useState<Record<string, string>>({})
  const [streaming, setStreaming] = useState(false)
  const queryClient = useQueryClient()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const notebookSources = useWorkspaceStore((state) => state.notebookSources)
  const activeChatId = useWorkspaceStore((state) => state.activeNotebookChatId)
  const setActiveChatId = useWorkspaceStore((state) => state.setActiveNotebookChatId)

  const { data: chats = [] } = useQuery<ChatSession[]>({
    queryKey: ['workspace-chats', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/chats`).then((r) => r.data),
    enabled: !!workspaceId,
  })
  const activeChat = chats.find((chat) => chat.id === activeChatId) || null

  const { data: storedMessages } = useQuery<StoredMessage[]>({
    queryKey: ['workspace-chat-messages', workspaceId, activeChatId],
    queryFn: () =>
      api.get(`/workspaces/${workspaceId}/chats/${activeChatId}/messages`).then((r) => r.data),
    enabled: !!workspaceId && !!activeChatId && !streaming,
  })

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
  const pendingQuestions = approvals.filter(
    (approval) =>
      approval.kind === 'question' &&
      (approval.status === 'pending' ||
        (approval.metadata?.source === 'plan_apply' &&
          approval.status === 'approved' &&
          !approval.result)),
  )
  const pendingRequirements = useMemo(
    () => pendingQuestions.map(requirementFromApproval),
    [pendingQuestions],
  )

  const { data: latestRun } = useQuery<ConversationRun | null>({
    queryKey: ['conversation-run-latest', workspaceId, activeChatId],
    queryFn: () =>
      api
        .get(`/workspaces/${workspaceId}/runs/latest`, { params: { chat_id: activeChatId } })
        .then((r) => r.data)
        .catch((error) => {
          if (error?.response?.status === 404) return null
          throw error
        }),
    enabled: !!workspaceId && !!activeChatId,
    refetchOnWindowFocus: false,
  })

  const respondApprovalMutation = useMutation({
    mutationFn: async ({
      approval,
      response,
    }: {
      approval: ApprovalRequest
      response: string
    }) => {
      // Auto approve referenced browser permission first if it is pending
      const question =
        approval.reason ||
        String(approval.arguments?.question || approval.metadata?.question || '')
      const match = question.match(/approval_id[：:]\s*`?([a-f0-9]+)`?/i)
      if (match) {
        const refId = match[1]
        try {
          await api.post(`/approvals/${refId}/approve`)
        } catch (e) {
          console.warn('Failed to auto-approve referenced browser permission', e)
        }
      }

      const endpoint =
        approval.metadata?.source === 'plan_apply'
          ? `/approvals/${approval.id}/resume-and-continue`
          : `/approvals/${approval.id}/respond`
      return api.post(endpoint, { response }).then((r) => r.data)
    },
    onSuccess: async (data) => {
      queryClient.invalidateQueries({ queryKey: ['approvals', workspaceId, activeChatId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-events', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId, activeChatId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })

      if (data?.plan_id) {
        const result = data as ApplyResult
        const runId = latestRun?.plan_id === result.plan_id ? latestRun.id : null
        await updateRun(runId, runPatchFromApplyResult(result)).catch(() => null)
        const failed = result.status === 'failed'
        const needsInput =
          result.status === 'needs_input' || Boolean(result.approval_ids?.length)
        const executionText =
          result.execution_results?.[0]?.error ||
          result.execution_results?.[0]?.result ||
          ''
        const content = failed
          ? `I tried to continue the task, but it still needs attention.\n\n${executionText || 'The resumed task failed.'}`
          : needsInput
          ? `I continued the task and still need one more input.\n\n${executionText}`
          : `I continued the task with your answers.\n\n${executionText || 'The task completed.'}`

        if (activeChatId) {
          try {
            await api.post(`/workspaces/${workspaceId}/chats/${activeChatId}/messages/raw`, {
              role: 'assistant',
              content,
              metadata: {
                type: 'executed',
                applyResult: result,
              },
            })
          } catch (err) {
            console.error('Failed to persist resumed planner result:', err)
          }
        }

        setMessages((prev) => [
          ...prev,
          {
            role: 'executed',
            content,
            applyResult: result,
          },
        ])

        if (result.artifacts?.length) {
          const workspaceStore = useWorkspaceStore.getState()
          workspaceStore.setRightPanelTab('artifacts')
          workspaceStore.setRightPanelOpen(true)
        }
      }
    },
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
  }, [setActiveChatId, workspaceId])

  useEffect(() => {
    if (activeChatId || chats.length === 0) return
    const simpleChats = chats.filter((c) => c.metadata?.mode === 'simple')
    if (simpleChats.length > 0) {
      setActiveChatId(simpleChats[0].id)
    } else {
      setActiveChatId(chats[0].id)
    }
  }, [activeChatId, chats, setActiveChatId])

  useEffect(() => {
    if (!streaming) setMessages([])
  }, [activeChatId, streaming])

  useEffect(() => {
    if (streaming || !storedMessages) return
    setMessages(
      storedMessages
        .filter((message) => {
          if (message.role !== 'user' && message.role !== 'assistant') return false
          if (message.role === 'assistant' && !message.content.trim() && !message.metadata?.type) {
            return false
          }
          return true
        })
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

  const createChat = async (title?: string) => {
    const created = await api
      .post(`/workspaces/${workspaceId}/chats`, {
        title: title ? sessionTitleFromIntent(title) : 'New Chat',
        metadata: { mode: 'simple' },
      })
      .then((r) => r.data as ChatSession)
    setActiveChatId(created.id)
    setMessages([])
    await queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
    return created.id
  }

  const maybeRenameCurrentChat = async (chatId: string, firstMessage: string) => {
    const currentTitle = String(activeChat?.title || '')
    const isGeneric =
      !currentTitle ||
      ['New Chat', 'Planner Orchestrator Session'].includes(currentTitle) ||
      /^Conversation\s+\d+$/i.test(currentTitle)
    if (!isGeneric || (storedMessages && storedMessages.length > 0)) return
    await api.patch(`/workspaces/${workspaceId}/chats/${chatId}`, {
      title: sessionTitleFromIntent(firstMessage),
      metadata: { mode: 'simple' },
    })
    await queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
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

  const browserLocale = () => {
    if (typeof navigator === 'undefined') return ''
    return navigator.language || ''
  }

  const browserTimezone = () => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || ''
    } catch {
      return ''
    }
  }

  const updateRun = async (
    runId: string | null | undefined,
    patch: Record<string, unknown>,
  ) => {
    if (!runId) return null
    const updated = await api
      .patch(`/workspaces/${workspaceId}/runs/${runId}`, patch)
      .then((r) => r.data as ConversationRun)
    queryClient.invalidateQueries({ queryKey: ['conversation-run-latest', workspaceId, activeChatId] })
    return updated
  }

  useEffect(() => {
    if (!latestRun?.id || pendingRequirements.length === 0) return
    if (
      latestRun.state === 'needs_input' &&
      sameRequirements(latestRun.requirements || [], pendingRequirements)
    ) {
      return
    }
    void updateRun(latestRun.id, {
      state: 'needs_input',
      requirements: pendingRequirements,
      event_type: 'run.input_requested',
      event_data: {
        approval_ids: pendingRequirements.map((item) => item.approval_id).filter(Boolean),
      },
    }).catch((error) => console.warn('Failed to sync run requirements:', error))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestRun?.id, latestRun?.state, pendingRequirements])

  const handleSend = async (override?: string) => {
    const currentInput = override ?? input
    if (!currentInput.trim() || streaming) return
    const userMsg = currentInput.trim()
    const plannerIntent = `${userMsg}${buildSourceContext()}`
    setInput('')

    let chatId = activeChatId
    try {
      chatId = chatId || (await createChat(userMsg))
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Failed to initialize chat session.' }])
      return
    }

    let runId: string | null = null
    try {
      const run = await api
        .post(`/workspaces/${workspaceId}/runs`, {
          chat_id: chatId,
          raw_intent: userMsg,
          locale: browserLocale(),
          timezone: browserTimezone(),
          state: 'intent_received',
          sources: notebookSources,
          metadata: { surface: 'simple_mode' },
        })
        .then((r) => r.data as ConversationRun)
      runId = run.id
      await updateRun(runId, {
        state: 'context_resolving',
        intent: { confirmed: true, summary: userMsg },
        event_type: 'run.intent_confirmed',
        event_data: { summary: userMsg },
      })
    } catch (err) {
      console.error('Failed to initialize conversation run:', err)
    }

    // Persist user intent message
    try {
      await maybeRenameCurrentChat(chatId, userMsg)
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

    // Add visible loading placeholder
    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '正在分析需求，并准备可执行方案...' },
    ])

    try {
      const planRes = await api.post(`/workspaces/${workspaceId}/plans`, {
        intent: plannerIntent,
        chat_id: chatId,
        run_id: runId,
      })
      const plan = planRes.data as WorkspacePlan
      const planRequirements = requirementsFromPlan(plan)
      await updateRun(runId, {
        state: planRequirements.length > 0 ? 'needs_input' : 'plan_proposed',
        plan_id: plan.id,
        intent: {
          summary: plan.summary,
          intent_type: plan.intent_type,
          execution_mode: plan.execution_mode,
          confirmed: true,
        },
        capabilities: [
          ...(plan.recommended_skills || []).map((skill: any) => ({
            id: skill.name || skill.id || 'skill',
            kind: 'skill',
            selected: true,
          })),
          ...(plan.recommended_mcp_tools || []).map((tool: any) => ({
            id: tool.name || tool.id || 'mcp_tool',
            kind: 'mcp_tool',
            selected: true,
          })),
        ],
        promotion_candidates: {
          task: plan.execution_mode === 'scheduled' || plan.execution_mode === 'long_running',
          source: Boolean(plan.expected_artifacts?.length),
          skill: Boolean(plan.recommended_skills?.length),
          memory: true,
        },
        requirements: planRequirements.length > 0 ? planRequirements : undefined,
        event_type: planRequirements.length > 0 ? 'run.input_requested' : 'run.plan_proposed',
        event_data: { plan_id: plan.id, summary: plan.summary },
      })

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
      await updateRun(runId, {
        state: 'failed',
        event_type: 'run.failed',
        event_data: { error: errMsg },
      }).catch(() => null)
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

  const handleConfirmPlan = async (plan: WorkspacePlan, initialResponse?: string) => {
    if (streaming || !activeChatId) return
    setStreaming(true)
    const runId = latestRun?.plan_id === plan.id ? latestRun.id : null
    const answeredRequirements = initialResponse?.trim()
      ? markRequirementsAnswered(latestRun?.requirements || [], initialResponse.trim())
      : undefined
    await updateRun(runId, {
      state: 'approved',
      requirements: answeredRequirements,
      event_type: 'run.approved',
      event_data: { plan_id: plan.id },
    }).catch(() => null)

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
      await updateRun(runId, {
        state: 'running',
        event_type: 'run.started',
        event_data: { plan_id: plan.id },
      }).catch(() => null)

      if (initialResponse?.trim()) {
        const applyRes = await api.post(`/workspaces/${workspaceId}/plans/${plan.id}/apply`)
        let finalApplyResult = applyRes.data as ApplyResult
        const approvalId = finalApplyResult.approval_ids?.[0]
        if (approvalId) {
          const resumeRes = await api.post(`/approvals/${approvalId}/resume-and-continue`, {
            response: initialResponse.trim(),
          })
          finalApplyResult = resumeRes.data as ApplyResult
        }
        const resultContent = resultContentFromApplyResult(finalApplyResult)
        await updateRun(runId, runPatchFromApplyResult(finalApplyResult)).catch(() => null)

        await api.post(`/workspaces/${workspaceId}/chats/${activeChatId}/messages/raw`, {
          role: 'assistant',
          content: resultContent,
          metadata: {
            type: 'executed',
            applyResult: finalApplyResult,
          },
        })

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
        queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId, activeChatId] })
        queryClient.invalidateQueries({ queryKey: ['approvals', workspaceId, activeChatId] })
        queryClient.invalidateQueries({ queryKey: ['workspace-chat-messages', workspaceId, activeChatId] })
        return
      }

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
            } else if (event.type === 'plan.step.failed') {
              stepId = event.data?.action
                ? `plan-step-${event.data.action}-${event.step_id || event.task_id || 'failed'}`
                : `plan-step-${event.step_id || event.task_id || 'failed'}`
              stepLabel = event.data?.error
                ? `Plan step failed: ${event.data.error}`
                : 'Plan step failed'
              status = 'failed'
            } else if (event.type === 'task.created') {
              stepId = `task-${event.task_id || 'new'}`
              stepLabel = 'Prepared the execution task'
            } else if (event.type === 'browser_run.created') {
              stepId = `browser-${event.task_id || 'new'}`
              stepLabel = 'Prepared the browser automation run'
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
              const stepErrors = event.data?.failed_step_errors || {}
              const firstStepError =
                typeof stepErrors === 'object'
                  ? Object.values(stepErrors).find(Boolean)
                  : ''
              stepLabel = `Execution error: ${event.error || firstStepError || 'unknown error'}`
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
        failed_steps: finalApplyResultFromStream?.failed_steps || [],
        failed_step_errors: finalApplyResultFromStream?.failed_step_errors || {},
        plan: finalApplyResultFromStream?.plan || updatedPlan,
      }
      const failed = finalApplyResult.status === 'failed'
      const needsInput =
        finalApplyResult.status === 'needs_input' ||
        Boolean(finalApplyResult.approval_ids?.length)
      const firstError =
        finalApplyResult.execution_results?.find((item) => item.error)?.error ||
        Object.values(finalApplyResult.failed_step_errors || {}).find(Boolean) ||
        stepsList.find((step) => step.status === 'failed')?.label ||
        (failed ? 'The workflow could not complete with the current configuration.' : '')
      const resultContent = failed
        ? `Execution needs attention.\n\n${firstError}\n\nRecommended next step: review the highlighted issue, adjust the source/provider/capability access if needed, then run the plan again.`
        : needsInput
        ? `I need a bit more information before continuing.\n\n${finalResultText}\n\nOpen Needs Input on the right and provide the requested details.`
        : `Execution completed.\n\n${finalResultText}`
      await updateRun(runId, runPatchFromApplyResult(finalApplyResult)).catch(() => null)

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
      queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId, activeChatId] })
      queryClient.invalidateQueries({ queryKey: ['code-projects', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['approvals', workspaceId, activeChatId] })
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
      await updateRun(runId, {
        state: 'failed',
        event_type: 'run.failed',
        event_data: { plan_id: plan.id, error: errMsg },
      }).catch(() => null)
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
      const runId = latestRun?.plan_id === plan.id ? latestRun.id : null
      await updateRun(runId, {
        state: 'closed',
        event_type: 'run.closed',
        event_data: { plan_id: plan.id, reason: 'plan_rejected' },
      }).catch(() => null)
      
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

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8 space-y-6 max-w-4xl mx-auto w-full scrollbar-thin">
        {latestRun && (
          <div className="mx-auto flex w-full max-w-3xl items-center justify-between rounded-2xl border border-border/70 bg-card/80 px-4 py-3 shadow-sm">
            <div>
              <div className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                Conversation Run
              </div>
              <div className="mt-0.5 text-sm font-bold text-foreground">
                {runStateLabel(latestRun.state)}
              </div>
            </div>
            <span className="rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[10px] font-black uppercase tracking-widest text-primary">
              {latestRun.state}
            </span>
          </div>
        )}

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
              <div key={i} className="flex justify-end gap-2">
                <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-3 text-sm leading-relaxed text-primary-foreground font-semibold shadow-sm">
                  <div className="mb-1 text-[10px] font-black uppercase tracking-widest text-primary-foreground/70">
                    You
                  </div>
                  <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                </div>
              </div>
            )
          }

          if (msg.role === 'assistant') {
            if (!msg.content?.trim()) return null
            return (
              <div key={i} className="flex justify-start gap-2">
                <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-black text-primary">
                  C
                </div>
                <div className="max-w-[80%] rounded-2xl bg-card border border-border px-4 py-3 text-sm leading-relaxed text-foreground shadow-sm">
                  <div className="mb-1 text-[10px] font-black uppercase tracking-widest text-muted-foreground">
                    Cognix
                  </div>
                  <RichMessage content={msg.content} compact />
                </div>
              </div>
            )
          }

          if (msg.role === 'plan' && msg.plan) {
            const plan = msg.plan
            const requestInputStep = plan.steps.find((step) => step.action === 'request_input')
            const requestInputValue = planInputValues[plan.id] || ''
            const expectedOutputs = (plan.expected_artifacts || []).filter(
              (output) => !requestInputStep || !String(output).toLowerCase().includes('confirmation'),
            )
            const visibleSteps = plan.steps.filter((step) => step.action !== 'request_input')
            const summary = cleanPlanText(plan.summary)
            const inputQuestion = cleanPlanText(
              String(requestInputStep?.params?.question || requestInputStep?.description || '请补充继续执行所需的信息。'),
            )
            const inputReason = cleanPlanText(
              String(requestInputStep?.params?.reason || ''),
            )
            return (
              <div key={i} className="flex justify-start w-full">
                <div className="w-full max-w-3xl bg-card border border-border/80 backdrop-blur-md rounded-2xl p-5 shadow-lg space-y-4 hover:border-primary/20 transition-all duration-300">
                  <div className="flex items-start justify-between border-b border-border/60 pb-3">
                    <div>
                      <h4 className="text-sm font-black tracking-tight text-foreground">
                        {requestInputStep ? '需要补充信息' : '建议方案'}
                      </h4>
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        {requestInputStep
                          ? '补齐后我会继续执行，不需要去右侧审批面板操作。'
                          : '请确认 Cognix 的执行思路。'}
                      </p>
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-wider bg-primary/10 text-primary px-2.5 py-1 rounded-full border border-primary/20">
                      {plan.intent_type || 'Automation'}
                    </span>
                  </div>

                  {!requestInputStep && (
                    <div className="rounded-xl border border-border/60 bg-background/60 p-3.5">
                      <div className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-1.5">
                        AI 判断
                      </div>
                      <p className="text-sm text-foreground/95 leading-relaxed font-semibold">{summary}</p>
                    </div>
                  )}

                  {requestInputStep && (
                    <div className="rounded-xl border border-amber-300/50 bg-amber-50/70 p-4 space-y-3">
                      <div className="flex items-start gap-3">
                        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500/10 text-amber-700">
                          <CircleHelp className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-[10px] font-black uppercase tracking-widest text-amber-700 mb-1">
                            待补充
                          </div>
                          <p className="text-sm font-semibold text-foreground">
                            {inputQuestion}
                          </p>
                          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                            {inputReason || '需要目标页面链接，确认后我会继续创建浏览器自动化任务。'}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-col gap-2 sm:flex-row">
                        <input
                          value={requestInputValue}
                          onChange={(event) =>
                            setPlanInputValues((prev) => ({
                              ...prev,
                              [plan.id]: event.target.value,
                            }))
                          }
                          placeholder="粘贴目标页面 URL"
                          className="h-10 min-w-0 flex-1 rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/15"
                        />
                        <button
                          type="button"
                          onClick={() => handleConfirmPlan(plan, requestInputValue)}
                          disabled={streaming || !requestInputValue.trim()}
                          className="inline-flex h-10 items-center justify-center gap-1.5 rounded-xl bg-primary px-4 text-xs font-black text-primary-foreground transition-opacity hover:bg-primary/95 disabled:opacity-45"
                        >
                          <Play className="h-3.5 w-3.5 fill-current" />
                          继续执行
                        </button>
                      </div>
                    </div>
                  )}

                  {visibleSteps.length > 0 && (
                    <div className="rounded-xl border border-border/60 bg-background/50 p-3">
                      <div className="text-[10px] font-black uppercase tracking-widest text-muted-foreground mb-2">
                        执行步骤
                      </div>
                      <div className="space-y-2">
                        {visibleSteps.map((step, idx) => (
                          <div key={step.id} className="flex gap-2 text-xs leading-relaxed">
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[10px] font-black text-primary">
                              {idx + 1}
                            </span>
                            <span className="font-medium text-foreground/90">{step.description}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Components discovered & recommended */}
                  {!requestInputStep && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 pt-1">
                    {/* Recommended work mode */}
                    {plan.recommended_agents && plan.recommended_agents.length > 0 && (
                      <div className="rounded-xl border border-border/60 bg-background/50 p-3">
                        <div className="flex items-center gap-1.5 text-xs font-black text-muted-foreground mb-2 uppercase tracking-wider">
                          <Cpu className="h-3.5 w-3.5 text-primary" />
                          工作方式
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
                          可用能力
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
                  )}

                  {!requestInputStep && expectedOutputs.length > 0 && (
                    <div className="rounded-xl border border-border/60 bg-background/50 p-3">
                      <div className="flex items-center gap-1.5 text-xs font-black text-muted-foreground mb-2 uppercase tracking-wider">
                        <FileText className="h-3.5 w-3.5 text-primary" />
                        预期输出
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {expectedOutputs.map((output, idx) => (
                          <span key={idx} className="rounded-md border border-border bg-card px-2 py-1 text-[10px] font-semibold text-foreground/80">
                            {String(output)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Scheduling if applicable */}
                  {plan.scheduling && Boolean(plan.scheduling.needed || plan.scheduling.reason) && (
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
                  {!requestInputStep && (
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
                  )}
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
        {pendingQuestions.map((approval) => (
          <InlineApprovalQuestion
            key={approval.id}
            approval={approval}
            allApprovals={approvals}
            busy={respondApprovalMutation.isPending}
            onSubmit={(response) => {
              if (latestRun?.id) {
                void updateRun(latestRun.id, {
                  state: 'running',
                  requirements: markRequirementAnswered(
                    latestRun.requirements || [],
                    approval.id,
                    response,
                  ),
                  event_type: 'run.input_answered',
                  event_data: { approval_id: approval.id },
                }).catch((error) => console.warn('Failed to mark requirement answered:', error))
              }
              respondApprovalMutation.mutate({ approval, response })
            }}
          />
        ))}
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

function getSuggestions(currentApproval: ApprovalRequest, allApprovals: ApprovalRequest[]) {
  const currentReason =
    currentApproval.reason ||
    String(currentApproval.arguments?.question || currentApproval.metadata?.question || '') ||
    ''
  const currentTool = currentApproval.tool_name || ''

  const candidates = allApprovals.filter((app) => {
    if (app.id === currentApproval.id) return false
    if (app.kind !== 'question') return false
    if (app.status === 'pending') return false
    if (!app.response || !app.response.trim()) return false
    return true
  })

  const scored = candidates.map((app) => {
    let score = 0
    if (currentTool && app.tool_name === currentTool) {
      score += 10
    }
    const appReason =
      app.reason || String(app.arguments?.question || app.metadata?.question || '') || ''
    const w1 = new Set(currentReason.toLowerCase().split(/\s+/).filter(Boolean))
    const w2 = new Set(appReason.toLowerCase().split(/\s+/).filter(Boolean))
    if (w1.size > 0 && w2.size > 0) {
      const intersection = new Set([...w1].filter((x) => w2.has(x)))
      const jaccard = intersection.size / new Set([...w1, ...w2]).size
      score += jaccard * 20
    }
    if (currentReason && appReason === currentReason) {
      score += 50
    }
    return {
      response: app.response!.trim(),
      score,
    }
  })

  scored.sort((a, b) => b.score - a.score)

  const uniqueResponses: string[] = []
  for (const item of scored) {
    if (!uniqueResponses.includes(item.response)) {
      uniqueResponses.push(item.response)
    }
    if (uniqueResponses.length >= 5) break
  }

  return uniqueResponses
}

function resultContentFromApplyResult(result: ApplyResult) {
  const failed = result.status === 'failed'
  const needsInput = result.status === 'needs_input' || Boolean(result.approval_ids?.length)
  const stepSummary =
    result.plan?.steps
      ?.map((step) => `• **${step.description}**: ${result.plan?.step_statuses?.[step.id] || 'pending'}`)
      .join('\n') || ''
  const firstError =
    result.execution_results?.find((item) => item.error)?.error ||
    Object.values(result.failed_step_errors || {}).find(Boolean) ||
    ''
  const executionText =
    result.execution_results?.[0]?.error ||
    result.execution_results?.[0]?.result ||
    ''

  if (failed) {
    return `Execution needs attention.\n\n${firstError || executionText || 'The workflow could not complete with the current configuration.'}\n\nRecommended next step: review the highlighted issue, adjust the source/provider/capability access if needed, then run the plan again.`
  }
  if (needsInput) {
    return `I need a bit more information before continuing.\n\n${stepSummary || executionText}`
  }
  return `Execution completed.\n\n${stepSummary || executionText || 'The task completed.'}`
}

function requirementFromApproval(approval: ApprovalRequest): RunRequirement {
  const prompt =
    approval.reason ||
    String(approval.arguments?.question || approval.metadata?.question || '') ||
    'Cognix needs more information before it can continue.'
  return {
    id: `approval:${approval.id}`,
    approval_id: approval.id,
    kind: approval.kind || 'question',
    label: requirementLabel(prompt),
    prompt,
    reason: prompt,
    required: true,
    status: approval.response ? 'answered' : 'pending',
    value: approval.response || '',
  }
}

function requirementsFromPlan(plan: WorkspacePlan): RunRequirement[] {
  return plan.steps
    .filter((step) => step.action === 'request_input')
    .map((step) => {
      const prompt = cleanPlanText(
        String(step.params?.question || step.description || '请补充继续执行所需的信息。'),
      )
      return {
        id: `step:${step.id}`,
        step_id: step.id,
        kind: 'missing_input',
        label: requirementLabel(prompt),
        prompt,
        reason: cleanPlanText(String(step.params?.reason || '')),
        required: true,
        status: 'pending',
        value: '',
      }
    })
}

function requirementLabel(prompt: string) {
  if (/url|网址|入口|后台|链接/i.test(prompt)) return '目标入口 URL'
  if (/授权|批准|approval|permission/i.test(prompt)) return '授权确认'
  if (/登录|验证码|扫码|二次验证/i.test(prompt)) return '登录方式'
  if (/字段|field/i.test(prompt)) return '输出字段'
  if (/范围|时间|日期|scope/i.test(prompt)) return '数据范围'
  return '补充信息'
}

function markRequirementAnswered(
  requirements: RunRequirement[],
  approvalId: string,
  response: string,
) {
  if (requirements.length === 0) {
    return [
      {
        id: `approval:${approvalId}`,
        approval_id: approvalId,
        kind: 'question',
        label: '补充信息',
        required: true,
        status: 'answered' as const,
        value: response,
      },
    ]
  }
  return requirements.map((item) =>
    item.approval_id === approvalId || item.id === `approval:${approvalId}`
      ? { ...item, status: 'answered' as const, value: response }
      : item,
  )
}

function markRequirementsAnswered(requirements: RunRequirement[], response: string) {
  return requirements.map((item) =>
    item.status === 'pending' ? { ...item, status: 'answered' as const, value: response } : item,
  )
}

function sameRequirements(a: RunRequirement[], b: RunRequirement[]) {
  if (a.length !== b.length) return false
  return a.every((item, index) => {
    const other = b[index]
    return (
      item.id === other.id &&
      item.status === other.status &&
      item.value === other.value &&
      item.prompt === other.prompt
    )
  })
}

function runPatchFromApplyResult(result: ApplyResult) {
  const failed = result.status === 'failed'
  const needsInput = result.status === 'needs_input' || Boolean(result.approval_ids?.length)
  const artifacts = result.artifacts || []
  const state = failed ? 'failed' : needsInput ? 'needs_input' : 'completed'
  return {
    state,
    artifact_ids: artifacts,
    promotion_candidates: {
      task:
        result.plan?.execution_mode === 'scheduled' ||
        result.plan?.execution_mode === 'long_running',
      source: artifacts.length > 0,
      skill: false,
      memory: artifacts.length > 0,
    },
    event_type: failed
      ? 'run.failed'
      : needsInput
      ? 'run.input_requested'
      : 'run.completed',
    event_data: {
      plan_id: result.plan_id,
      artifacts,
      approval_ids: result.approval_ids || [],
      status: result.status,
    },
  }
}

function runStateLabel(state: string) {
  const labels: Record<string, string> = {
    intent_received: '已收到目标',
    intent_confirming: '正在确认意图',
    context_resolving: '正在匹配上下文和能力',
    needs_input: '等待补充信息',
    plan_proposed: '已生成建议方案',
    plan_revision_requested: '正在调整方案',
    approved: '已确认执行',
    running: '正在执行',
    blocked: '执行被阻塞',
    completed: '已完成',
    failed: '执行失败',
    reviewing_output: '等待复盘输出',
    promoted_to_task: '已转为长期任务',
    promoted_to_source: '已转为输入源',
    promoted_to_skill: '已转为技能',
    memory_write_pending: '等待记忆写入确认',
    closed: '已关闭',
  }
  return labels[state] || state
}

function cleanPlanText(value: string) {
  return value
    .replace(/Selected workspace sources:[\s\S]*$/i, '')
    .replace(/Original request:[\s\S]*$/i, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function parseBrowserFormResponse(responseStr: string) {
  const form = {
    targetUrl: '',
    menuEntry: '',
    authorizationConfirmed: false,
    loginMode: '',
    loginNotes: '',
    scope: '',
    outputFields: '',
    browserAccessApproved: false,
    exportFormat: 'structured-table',
    notes: '',
  }

  const targetUrlMatch = responseStr.match(/1\.\s*目标入口[：:]\s*(.*)/)
  if (targetUrlMatch) form.targetUrl = targetUrlMatch[1].trim()

  const menuEntryMatch = responseStr.match(/2\.\s*菜单入口[：:]\s*(.*)/)
  if (menuEntryMatch) {
    const val = menuEntryMatch[1].trim()
    form.menuEntry = val === '未指定，请按页面实际入口判断' ? '' : val
  }

  if (responseStr.includes('3. 合法授权：我确认已获得合法授权')) {
    form.authorizationConfirmed = true
  }

  const loginModeMatch = responseStr.match(/4\.\s*登录方式[：:]\s*(.*)/)
  if (loginModeMatch) form.loginMode = loginModeMatch[1].trim()

  const loginNotesMatch = responseStr.match(/5\.\s*登录补充说明[：:]\s*(.*)/)
  if (loginNotesMatch) {
    const val = loginNotesMatch[1].trim()
    form.loginNotes = val === '无' ? '' : val
  }

  const scopeMatch = responseStr.match(/6\.\s*拉取范围[：:]\s*(.*)/)
  if (scopeMatch) form.scope = scopeMatch[1].trim()

  const outputFieldsMatch = responseStr.match(/7\.\s*输出字段[：:]\s*(.*)/)
  if (outputFieldsMatch) {
    const val = outputFieldsMatch[1].trim()
    form.outputFields = val.startsWith('默认字段') ? '' : val
  }

  if (responseStr.includes('8. 操作批准：我批准')) {
    form.browserAccessApproved = true
  }

  const exportFormatMatch = responseStr.match(/9\.\s*输出格式[：:]\s*(.*)/)
  if (exportFormatMatch) form.exportFormat = exportFormatMatch[1].trim()

  const notesMatch = responseStr.match(/10\.\s*其他说明[：:]\s*(.*)/)
  if (notesMatch) {
    const val = notesMatch[1].trim()
    form.notes = val === '无' ? '' : val
  }

  return form
}

function InlineApprovalQuestion({
  approval,
  allApprovals = [],
  busy,
  onSubmit,
}: {
  approval: ApprovalRequest
  allApprovals?: ApprovalRequest[]
  busy: boolean
  onSubmit: (response: string) => void
}) {
  const question =
    approval.reason ||
    String(approval.arguments?.question || approval.metadata?.question || '') ||
    'Cognix needs more information before it can continue this task.'
  const isApprovalContinuation =
    /已批准，继续|审批弹窗|审批后|允许后|approval/i.test(question)
  const [response, setResponse] = useState(() => {
    return isApprovalContinuation ? '已批准，继续' : ''
  })
  const [browserForm, setBrowserForm] = useState({
    targetUrl: '',
    menuEntry: '',
    authorizationConfirmed: false,
    loginMode: '',
    loginNotes: '',
    scope: '',
    outputFields: '',
    browserAccessApproved: false,
    exportFormat: 'structured-table',
    notes: '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const shouldUseBrowserForm =
    !isApprovalContinuation &&
    /浏览器|登录|授权|URL|网址|后台|入口|拉取|采集|爬取|导出/.test(question)
  const readyToResume =
    approval.status === 'approved' && Boolean(approval.response) && !approval.result
  const { data: approvalSuggestions = [] } = useQuery<ApprovalSuggestion[]>({
    queryKey: ['approval-suggestions', approval.id],
    queryFn: () => api.get(`/approvals/${approval.id}/suggestions`).then((r) => r.data),
    enabled: approval.status === 'pending',
  })
  const suggestions =
    approvalSuggestions.length > 0
      ? approvalSuggestions.map((item) => item.response)
      : getSuggestions(approval, allApprovals)
  const match = question.match(/approval_id[：:]\s*`?([a-f0-9]+)`?/i)
  const refApprovalId = match ? match[1] : null
  const refApproval = refApprovalId ? allApprovals.find((a) => a.id === refApprovalId) : null

  useEffect(() => {
    const isCont = /已批准，继续|审批弹窗|审批后|允许后|approval/i.test(question)
    setResponse(isCont ? '已批准，继续' : '')
    setErrors({})
    setBrowserForm({
      targetUrl: '',
      menuEntry: '',
      authorizationConfirmed: false,
      loginMode: '',
      loginNotes: '',
      scope: '',
      outputFields: '',
      browserAccessApproved: false,
      exportFormat: 'structured-table',
      notes: '',
    })
  }, [approval.id, question])

  const updateBrowserForm = (
    field: keyof typeof browserForm,
    value: string | boolean,
  ) => {
    setBrowserForm((current) => ({ ...current, [field]: value }))
    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  const validateBrowserForm = () => {
    const nextErrors: Record<string, string> = {}
    const url = browserForm.targetUrl.trim()

    if (!url) {
      nextErrors.targetUrl = '请填写后台地址或目标入口 URL'
    } else {
      try {
        const parsed = new URL(url)
        if (!['http:', 'https:'].includes(parsed.protocol)) {
          nextErrors.targetUrl = 'URL 必须以 http:// 或 https:// 开头'
        }
      } catch {
        nextErrors.targetUrl = '请输入有效 URL，例如 https://example.com'
      }
    }

    if (!browserForm.authorizationConfirmed) {
      nextErrors.authorizationConfirmed = '必须确认你拥有合法授权'
    }
    if (!browserForm.loginMode) {
      nextErrors.loginMode = '请选择登录方式'
    }
    if (!browserForm.scope.trim()) {
      nextErrors.scope = '请说明本次需要拉取的数据范围'
    }
    if (!browserForm.browserAccessApproved) {
      nextErrors.browserAccessApproved = '必须明确批准浏览器访问和站内操作'
    }

    setErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  const submitBrowserForm = () => {
    if (!validateBrowserForm()) return

    onSubmit(
      [
        '已补充本次任务所需信息：',
        '',
        `1. 目标入口：${browserForm.targetUrl.trim()}`,
        `2. 菜单入口：${browserForm.menuEntry.trim() || '未指定，请按页面实际入口判断'}`,
        '3. 合法授权：我确认已获得合法授权，可访问并提取目标系统内的券码数据。',
        `4. 登录方式：${browserForm.loginMode}`,
        `5. 登录补充说明：${browserForm.loginNotes.trim() || '无'}`,
        `6. 拉取范围：${browserForm.scope.trim()}`,
        `7. 输出字段：${browserForm.outputFields.trim() || '默认字段：券码、状态、批次/活动名称、创建时间/领取时间、有效期'}`,
        '8. 操作批准：我批准 Cognix 使用浏览器自动化访问目标站点、站内操作。',
        `9. 输出格式：${browserForm.exportFormat}`,
        `10. 其他说明：${browserForm.notes.trim() || '无'}`,
      ].join('\n'),
    )
  }

  return (
    <div className="flex justify-start w-full">
      <div className="w-full max-w-3xl rounded-2xl border border-amber-500/25 bg-amber-500/[0.04] p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-amber-500/10 text-amber-600">
              <CircleHelp className="h-4 w-4" />
            </div>
            <div>
              <div className="text-sm font-black text-foreground">Cognix needs more information</div>
              <div className="text-[10px] font-bold uppercase tracking-widest text-amber-700/70">
                Continue this task in chat
              </div>
            </div>
          </div>
          <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-amber-700">
            Pending
          </span>
        </div>

        {readyToResume ? (
          <div className="space-y-3">
            <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-black text-emerald-700">
                <Check className="h-4 w-4" />
                Your answers were saved
              </div>
              <div className="max-h-48 overflow-auto rounded-lg border border-border bg-background/95 p-3 text-xs leading-5 text-foreground">
                <RichMessage content={approval.response || ''} />
              </div>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => onSubmit(approval.response || '')}
                disabled={busy}
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-foreground px-5 text-xs font-black uppercase tracking-wider text-background transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                Continue Task
              </button>
            </div>
          </div>
        ) : shouldUseBrowserForm ? (
          <BrowserApprovalForm
            form={browserForm}
            errors={errors}
            busy={busy}
            onChange={updateBrowserForm}
            onSubmit={submitBrowserForm}
            suggestions={suggestions.filter((s) => s.includes('目标入口') && s.includes('登录方式'))}
            onUseSuggestion={(value) => onSubmit(value)}
            onAutofill={(fields: BrowserApprovalFormProps) => {
              setBrowserForm(fields)
              setErrors({})
            }}
          />
        ) : isApprovalContinuation ? (
          <div className="space-y-3">
            <div className="rounded-xl border border-border bg-background/95 p-4 text-sm leading-6 text-foreground">
              <RichMessage content={question} />
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => setResponse('已批准，继续')}
                disabled={busy}
                className="h-10 rounded-xl border border-border bg-background px-4 text-xs font-black text-foreground transition-colors hover:bg-muted disabled:opacity-40"
              >
                填入
              </button>
              <button
                type="button"
                onClick={() => onSubmit('已批准，继续')}
                disabled={busy}
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-foreground px-5 text-xs font-black uppercase tracking-wider text-background transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                已批准，继续
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="rounded-xl border border-border bg-background/95 p-4 text-sm leading-6 text-foreground">
              <RichMessage content={question} />
            </div>

            {refApproval && refApproval.status === 'pending' && (
              <div className="mt-3 rounded-xl border border-amber-500/20 bg-amber-500/[0.03] p-3 text-xs">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-bold text-foreground flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-500 animate-pulse" />
                    关联浏览器访问审批 / Associated Browser Access Request
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-widest bg-amber-500/10 text-amber-500 border border-amber-500/20">
                    Pending
                  </span>
                </div>
                <div className="mt-2 space-y-1.5 text-muted-foreground leading-relaxed">
                  <div>
                    <span className="font-semibold text-foreground">目标页面 / Target URL: </span>
                    <code className="text-[10px] break-all bg-background/50 px-1 py-0.5 rounded border border-border text-foreground">
                      {String(refApproval.arguments?.url || 'Unknown URL')}
                    </code>
                  </div>
                  {Boolean(refApproval.arguments?.objective) && (
                    <div>
                      <span className="font-semibold text-foreground">执行目标 / Objective: </span>
                      <span className="text-foreground">{String(refApproval.arguments?.objective || '')}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {suggestions.length > 0 && (
              <div className="mt-3 space-y-1.5">
                <div className="flex items-center gap-1.5 text-[10px] font-bold text-amber-700/80 dark:text-amber-400/80">
                  <Sparkles className="h-3 w-3" />
                  <span>Suggestions from past answers</span>
                </div>
                <div className="space-y-2">
                  {suggestions.map((s, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-amber-500/20 bg-amber-500/[0.035] p-3"
                    >
                      <div className="max-h-[4.75rem] overflow-hidden text-[11px] leading-5 text-foreground">
                        {s}
                      </div>
                      <div className="mt-2 flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setResponse(s)}
                          className="h-8 rounded-lg border border-border bg-background px-3 text-[10px] font-black uppercase tracking-wider text-foreground hover:bg-muted"
                        >
                          填入
                        </button>
                        <button
                          type="button"
                          onClick={() => onSubmit(s)}
                          disabled={busy}
                          className="h-8 rounded-lg bg-foreground px-3 text-[10px] font-black uppercase tracking-wider text-background disabled:opacity-40"
                        >
                          一键继续
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-3 flex items-end gap-2">
              <textarea
                value={response}
                onChange={(event) => setResponse(event.target.value)}
                placeholder="Reply with the missing details, authorization, login status, scope, or fields to extract..."
                className="min-h-24 flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-xs leading-5 text-foreground outline-none focus:border-amber-500/40 focus:ring-2 focus:ring-amber-500/15"
              />
              <button
                type="button"
                onClick={() => {
                  if (response.trim()) onSubmit(response.trim())
                }}
                disabled={busy || !response.trim()}
                className="h-10 shrink-0 rounded-xl bg-foreground px-4 text-xs font-black text-background transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function BrowserApprovalForm({
  form,
  errors,
  busy,
  onChange,
  onSubmit,
  suggestions = [],
  onUseSuggestion,
  onAutofill,
}: {
  form: {
    targetUrl: string
    menuEntry: string
    authorizationConfirmed: boolean
    loginMode: string
    loginNotes: string
    scope: string
    outputFields: string
    browserAccessApproved: boolean
    exportFormat: string
    notes: string
  }
  errors: Record<string, string>
  busy: boolean
  onChange: (field: keyof BrowserApprovalFormProps, value: string | boolean) => void
  onSubmit: () => void
  suggestions?: string[]
  onUseSuggestion?: (response: string) => void
  onAutofill?: (fields: BrowserApprovalFormProps) => void
}) {
  return (
    <div className="space-y-4">
      {suggestions.length > 0 && onAutofill && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.03] p-3">
          <div className="flex items-center gap-1.5 text-xs font-bold text-amber-700/80 dark:text-amber-400/80 mb-2">
            <Sparkles className="h-3.5 w-3.5" />
            <span>历史填写记录 (点击一键填充) / History (Click to autofill)</span>
          </div>
          <div className="space-y-2">
            {suggestions.map((s, idx) => {
              const parsed = parseBrowserFormResponse(s)
              const displayUrl = parsed.targetUrl || '未知 URL'
              return (
                <div
                  key={idx}
                  className="rounded-xl border border-amber-500/20 bg-background/70 p-3"
                >
                  <div className="text-[11px] font-bold text-foreground">
                    {displayUrl}
                  </div>
                  <div className="mt-1 text-[10px] text-muted-foreground">
                    {parsed.loginMode || '无登录方式'}
                  </div>
                  <div className="mt-2 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onAutofill(parsed)}
                      className="h-8 rounded-lg border border-border bg-background px-3 text-[10px] font-black uppercase tracking-wider text-foreground hover:bg-muted"
                    >
                      填入
                    </button>
                    {onUseSuggestion && (
                      <button
                        type="button"
                        onClick={() => onUseSuggestion(s)}
                        disabled={busy}
                        className="h-8 rounded-lg bg-foreground px-3 text-[10px] font-black uppercase tracking-wider text-background disabled:opacity-40"
                      >
                        一键继续
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="rounded-xl border border-border bg-background/95 p-4">
        <div className="mb-4 flex items-start gap-3">
          <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600">
            <AlertCircle className="h-4 w-4" />
          </div>
          <div>
            <div className="text-sm font-black text-foreground">需要你确认下面的信息后继续</div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              每项都会合并成一次确认回复。带 * 的项目必须填写，通过校验后 Cognix 才会继续执行浏览器访问、登录后操作或数据导出。
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <FieldShell label="目标入口 URL *" error={errors.targetUrl} className="md:col-span-2">
            <input
              value={form.targetUrl}
              onChange={(event) => onChange('targetUrl', event.target.value)}
              placeholder="https://..."
              className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/15"
            />
          </FieldShell>

          <FieldShell label="菜单入口 / 页面位置">
            <input
              value={form.menuEntry}
              onChange={(event) => onChange('menuEntry', event.target.value)}
              placeholder="例如：营销中心 > 券码管理"
              className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/15"
            />
          </FieldShell>

          <FieldShell label="登录方式 *" error={errors.loginMode}>
            <select
              value={form.loginMode}
              onChange={(event) => onChange('loginMode', event.target.value)}
              className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/15"
            >
              <option value="">请选择</option>
              <option value="我会先手动登录，Cognix 使用已登录会话继续">我先手动登录</option>
              <option value="当前浏览器已有可用登录态">已有登录态</option>
              <option value="遇到短信、扫码或二次验证时暂停等待我处理">需要验证码时暂停</option>
              <option value="其他登录方式，见补充说明">其他</option>
            </select>
          </FieldShell>

          <FieldShell label="拉取范围 *" error={errors.scope} className="md:col-span-2">
            <textarea
              value={form.scope}
              onChange={(event) => onChange('scope', event.target.value)}
              placeholder="例如：近 30 天全部券码；或某个店铺/活动/批次"
              className="min-h-20 w-full resize-none rounded-lg border border-border bg-card px-3 py-2 text-sm leading-5 text-foreground outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/15"
            />
          </FieldShell>

          <FieldShell label="输出字段">
            <textarea
              value={form.outputFields}
              onChange={(event) => onChange('outputFields', event.target.value)}
              placeholder="默认：券码、状态、活动名、创建/领取时间、有效期"
              className="min-h-20 w-full resize-none rounded-lg border border-border bg-card px-3 py-2 text-sm leading-5 text-foreground outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/15"
            />
          </FieldShell>

          <FieldShell label="登录补充说明">
            <textarea
              value={form.loginNotes}
              onChange={(event) => onChange('loginNotes', event.target.value)}
              placeholder="例如：扫码登录、短信验证、账号角色限制"
              className="min-h-20 w-full resize-none rounded-lg border border-border bg-card px-3 py-2 text-sm leading-5 text-foreground outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/15"
            />
          </FieldShell>

          <FieldShell label="输出格式">
            <select
              value={form.exportFormat}
              onChange={(event) => onChange('exportFormat', event.target.value)}
              className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/15"
            >
              <option value="structured-table">结构化表格 + 摘要说明</option>
              <option value="xlsx">Excel 文件</option>
              <option value="csv">CSV 文件</option>
              <option value="markdown-report">Markdown 报告</option>
            </select>
          </FieldShell>

          <FieldShell label="其他说明">
            <input
              value={form.notes}
              onChange={(event) => onChange('notes', event.target.value)}
              placeholder="可选"
              className="h-10 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/15"
            />
          </FieldShell>
        </div>

        <div className="mt-4 space-y-2 rounded-xl border border-border/70 bg-card/60 p-3">
          <label className="flex items-start gap-2 text-xs leading-5 text-foreground">
            <input
              type="checkbox"
              checked={form.authorizationConfirmed}
              onChange={(event) => onChange('authorizationConfirmed', event.target.checked)}
              className="mt-1 h-4 w-4 rounded border-border text-amber-600 focus:ring-amber-500"
            />
            <span>我确认已获得合法授权，可访问并提取目标系统内的数据。*</span>
          </label>
          {errors.authorizationConfirmed && (
            <p className="pl-6 text-[11px] font-bold text-red-600">{errors.authorizationConfirmed}</p>
          )}

          <label className="flex items-start gap-2 text-xs leading-5 text-foreground">
            <input
              type="checkbox"
              checked={form.browserAccessApproved}
              onChange={(event) => onChange('browserAccessApproved', event.target.checked)}
              className="mt-1 h-4 w-4 rounded border-border text-amber-600 focus:ring-amber-500"
            />
            <span>我批准 Cognix 使用浏览器自动化访问目标站点，并在站内查询、筛选、分页和导出可用数据。*</span>
          </label>
          {errors.browserAccessApproved && (
            <p className="pl-6 text-[11px] font-bold text-red-600">{errors.browserAccessApproved}</p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        {Object.keys(errors).length > 0 && (
          <span className="mr-auto text-xs font-bold text-red-600">请先补齐标红项目</span>
        )}
        <button
          type="button"
          onClick={onSubmit}
          disabled={busy}
          className="inline-flex h-11 items-center gap-2 rounded-xl bg-foreground px-5 text-xs font-black uppercase tracking-wider text-background transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          Confirm and Continue
        </button>
      </div>
    </div>
  )
}

type BrowserApprovalFormProps = {
  targetUrl: string
  menuEntry: string
  authorizationConfirmed: boolean
  loginMode: string
  loginNotes: string
  scope: string
  outputFields: string
  browserAccessApproved: boolean
  exportFormat: string
  notes: string
}

function sessionTitleFromIntent(intent: string) {
  const compact = intent.replace(/\s+/g, ' ').trim()
  if (!compact) return 'New Chat'
  return compact.length > 36 ? `${compact.slice(0, 36)}...` : compact
}

function FieldShell({
  label,
  error,
  className = '',
  children,
}: {
  label: string
  error?: string
  className?: string
  children: ReactNode
}) {
  return (
    <label className={`block space-y-1.5 ${className}`}>
      <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground">
        {label}
      </span>
      {children}
      {error && <span className="block text-[11px] font-bold text-red-600">{error}</span>}
    </label>
  )
}
