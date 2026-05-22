import { useCallback, useEffect, useMemo, useState } from 'react'
import { AssistantRuntimeProvider } from '@assistant-ui/react'
import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useExternalStoreRuntime,
  useMessage,
} from '@assistant-ui/react'
import type { AppendMessage, ThreadMessageLike } from '@assistant-ui/react'
import { CheckCircle2, Circle, Loader2, Send, Sparkles } from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { RichMessage } from '@/shared/ui'
import { useWorkspaceStore } from '../store'

interface CognixAssistantConversationProps {
  workspaceId: string
  requestedIntent?: { id: number; text: string; autoSubmit?: boolean } | null
}

interface ChatSession {
  id: string
  title: string
  system_prompt?: string
  model_profiles?: string[]
  metadata?: Record<string, unknown>
}

interface StoredMessage {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  created_at?: string
  metadata?: Record<string, unknown>
}

interface ApprovalRequest {
  id: string
  kind: string
  status: string
  reason: string
  tool_name?: string
  arguments?: Record<string, unknown>
  response?: string
  result?: string
  metadata?: Record<string, unknown>
}

interface ConversationRun {
  id: string
  state: string
  chat_id: string
  intent?: Record<string, unknown>
  requirements?: Array<Record<string, unknown>>
}

type AssistantMessage = ThreadMessageLike & {
  id: string
  role: 'system' | 'user' | 'assistant'
  content: string
  createdAt: Date
}

interface LoadingStep {
  id: string
  label: string
  status: 'pending' | 'running' | 'done' | 'failed'
}

interface LoadingState {
  title: string
  detail: string
  steps: LoadingStep[]
}

const defaultLoadingState: LoadingState = {
  title: 'Understanding your request',
  detail: 'Cognix is preparing workspace context and checking available capabilities.',
  steps: [
    { id: 'intent', label: 'Understand intent', status: 'running' },
    { id: 'context', label: 'Load workspace context', status: 'pending' },
    { id: 'execute', label: 'Generate response', status: 'pending' },
  ],
}

const sessionTitleFromIntent = (text: string) => {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (!normalized) return 'New Chat'
  return normalized.length > 28 ? `${normalized.slice(0, 28)}...` : normalized
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

const toAssistantMessage = (message: StoredMessage): AssistantMessage => ({
  id: message.id,
  role: message.role === 'tool' ? 'assistant' : message.role,
  content: message.content || '',
  createdAt: message.created_at ? new Date(message.created_at) : new Date(),
  status:
    message.role === 'assistant'
      ? {
          type: 'complete',
          reason: 'stop',
        }
      : undefined,
  metadata: {
    custom: message.metadata || {},
  },
})

const messageText = (message: AppendMessage) => {
  const content = message.content
  if (typeof content === 'string') return content
  return content
    .map((part) => {
      if (part.type === 'text') return part.text
      if (part.type === 'data') return JSON.stringify(part.data)
      return ''
    })
    .join('')
    .trim()
}

function CognixAssistantMessage() {
  const message = useMessage()
  const text = message.content
    .map((part) => {
      if (part.type === 'text' || part.type === 'reasoning') return part.text
      if (part.type === 'tool-call') return `Tool call: ${part.toolName}`
      return ''
    })
    .filter(Boolean)
    .join('\n\n')
  const isUser = message.role === 'user'
  const loading = message.metadata.custom?.loading as LoadingState | undefined
  const isLoading = !isUser && message.status?.type === 'running' && !text.trim()

  return (
    <MessagePrimitive.Root
      className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={
          isUser
            ? 'max-w-[72%] rounded-2xl bg-primary px-4 py-3 text-sm font-semibold leading-7 text-primary-foreground shadow-sm'
            : 'max-w-[78%] rounded-2xl border border-border/80 bg-card px-4 py-3 text-sm leading-7 text-foreground shadow-sm'
        }
      >
        <div className="mb-1 text-[10px] font-black uppercase tracking-widest opacity-70">
          {isUser ? 'You' : 'Cognix'}
        </div>
        {isUser ? (
          <div className="whitespace-pre-wrap">{text}</div>
        ) : isLoading ? (
          <ThinkingCard loading={loading || defaultLoadingState} />
        ) : (
          <RichMessage content={text || ' '} compact />
        )}
      </div>
    </MessagePrimitive.Root>
  )
}

function ThinkingCard({ loading }: { loading: LoadingState }) {
  return (
    <div className="min-w-[320px] max-w-[520px] py-1">
      <div className="flex items-start gap-3">
        <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Loader2 className="h-4 w-4 animate-spin" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-black text-foreground">{loading.title}</div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">{loading.detail}</div>
          <div className="mt-3 grid gap-2">
            {loading.steps.slice(0, 4).map((step) => {
              const active = step.status === 'running'
              const done = step.status === 'done'
              const failed = step.status === 'failed'
              return (
                <div
                  key={step.id}
                  className="flex items-center gap-2 rounded-xl border border-border/60 bg-background/60 px-3 py-2"
                >
                  {done ? (
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                  ) : active ? (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                  ) : failed ? (
                    <Circle className="h-3.5 w-3.5 shrink-0 fill-rose-500 text-rose-500" />
                  ) : (
                    <Circle className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                  )}
                  <span
                    className={`truncate text-[11px] font-bold ${
                      active
                        ? 'text-primary'
                        : failed
                        ? 'text-rose-600'
                        : done
                        ? 'text-foreground'
                        : 'text-muted-foreground'
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              )
            })}
          </div>
          <div className="mt-3 flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-primary">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
            Thinking
          </div>
        </div>
      </div>
    </div>
  )
}

function AssistantSurface({
  runtime,
  workflowPanel,
}: {
  runtime: ReturnType<typeof useExternalStoreRuntime>
  workflowPanel?: React.ReactNode
}) {
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col">
        <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
          <div className="mx-auto flex min-h-full w-full max-w-4xl flex-col gap-5">
            <ThreadPrimitive.Empty>
              <div className="flex min-h-[55vh] flex-col items-center justify-center text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Sparkles className="h-7 w-7" />
                </div>
                <h2 className="text-lg font-black text-foreground">Tell Cognix the outcome</h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                  This assistant-ui prototype uses the current workspace chat API and streaming
                  protocol while keeping Planner, Approvals, Artifacts, and Memory unchanged.
                </p>
              </div>
            </ThreadPrimitive.Empty>
            <ThreadPrimitive.Messages components={{ Message: CognixAssistantMessage }} />
            {workflowPanel}
          </div>
        </ThreadPrimitive.Viewport>
        <ThreadPrimitive.ViewportFooter className="border-t border-border/80 bg-background/95 px-5 py-4">
          <ComposerPrimitive.Root className="mx-auto flex w-full max-w-4xl items-end gap-3">
            <ComposerPrimitive.Input
              placeholder="Ask a question or describe the result you need..."
              className="min-h-[52px] flex-1 resize-none rounded-2xl border border-border bg-card px-4 py-3 text-sm leading-6 outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
            />
            <ComposerPrimitive.Send className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/20 transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50">
              <Send className="h-5 w-5" />
            </ComposerPrimitive.Send>
          </ComposerPrimitive.Root>
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  )
}

export function CognixAssistantConversation({
  workspaceId,
  requestedIntent = null,
}: CognixAssistantConversationProps) {
  const queryClient = useQueryClient()
  const activeChatId = useWorkspaceStore((state) => state.activeNotebookChatId)
  const setActiveChatId = useWorkspaceStore((state) => state.setActiveNotebookChatId)
  const notebookSources = useWorkspaceStore((state) => state.notebookSources)
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [isRunning, setIsRunning] = useState(false)

  const { data: chats = [] } = useQuery<ChatSession[]>({
    queryKey: ['workspace-chats', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/chats`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const { data: storedMessages } = useQuery<StoredMessage[]>({
    queryKey: ['workspace-chat-messages', workspaceId, activeChatId],
    queryFn: () =>
      api.get(`/workspaces/${workspaceId}/chats/${activeChatId}/messages`).then((r) => r.data),
    enabled: !!workspaceId && !!activeChatId && !isRunning,
  })

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

  const pendingApproval = approvals.find(
    (approval) =>
      approval.kind === 'question' &&
      (approval.status === 'pending' ||
        (approval.status === 'approved' && Boolean(approval.response) && !approval.result)),
  )

  const refreshWorkflowState = useCallback(
    async (chatId: string | null | undefined) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['approvals', workspaceId, chatId] }),
        queryClient.invalidateQueries({ queryKey: ['conversation-run-latest', workspaceId, chatId] }),
        queryClient.invalidateQueries({ queryKey: ['workspace-chat-messages', workspaceId, chatId] }),
        queryClient.invalidateQueries({ queryKey: ['artifacts', workspaceId, chatId] }),
        queryClient.invalidateQueries({ queryKey: ['workspace-events', workspaceId] }),
      ])
    },
    [queryClient, workspaceId],
  )

  const handleApprovalSubmit = useCallback(
    async (approval: ApprovalRequest, response: string) => {
      const question =
        approval.reason ||
        String(approval.arguments?.question || approval.metadata?.question || '')
      const match = question.match(/approval_id[：:]\s*`?([a-f0-9]+)`?/i)
      if (match) {
        await api.post(`/approvals/${match[1]}/approve`).catch(() => null)
      }
      const endpoint =
        approval.metadata?.source === 'plan_apply'
          ? `/approvals/${approval.id}/resume-and-continue`
          : `/approvals/${approval.id}/respond`
      await api.post(endpoint, { response })
      await refreshWorkflowState(activeChatId)
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'user',
          content: response,
          createdAt: new Date(),
          metadata: { custom: { local: true, approval_id: approval.id } },
        },
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: '我已收到补充信息，正在继续推进任务。',
          createdAt: new Date(),
          status: { type: 'complete', reason: 'stop' },
          metadata: { custom: { local: true, approval_id: approval.id } },
        },
      ])
    },
    [activeChatId, refreshWorkflowState],
  )

  useEffect(() => {
    if (!storedMessages || isRunning) return
    setMessages(
      storedMessages
        .filter((message) => message.role !== 'system')
        .map(toAssistantMessage),
    )
  }, [storedMessages, isRunning])

  useEffect(() => {
    if (activeChatId || chats.length === 0) return
    const firstSimpleChat =
      chats.find((chat) => chat.metadata?.mode === 'simple') || chats[0]
    if (firstSimpleChat?.id) setActiveChatId(firstSimpleChat.id)
  }, [activeChatId, chats, setActiveChatId])

  const createChat = useCallback(
    async (title: string) => {
      const created = await api
        .post(`/workspaces/${workspaceId}/chats`, {
          title: sessionTitleFromIntent(title),
          metadata: { mode: 'assistant-ui' },
        })
        .then((r) => r.data as ChatSession)
      setActiveChatId(created.id)
      await queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
      return created.id
    },
    [queryClient, setActiveChatId, workspaceId],
  )

  const buildSourceContext = useCallback(() => {
    if (notebookSources.length === 0) return ''
    const lines = notebookSources
      .slice(0, 20)
      .map((source) => `- [${source.kind}] ${source.title}: ${source.subtitle}`)
      .join('\n')
    return `\n\nSelected workspace sources:\n${lines}`
  }, [notebookSources])

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || isRunning) return

      let chatId = activeChatId
      if (!chatId) chatId = await createChat(trimmed)

      setIsRunning(true)
      const userMessage: AssistantMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: trimmed,
        createdAt: new Date(),
        metadata: { custom: { local: true, sources: notebookSources } },
      }
      const assistantId = crypto.randomUUID()
      const assistantMessage: AssistantMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        createdAt: new Date(),
        status: { type: 'running' },
        metadata: { custom: { local: true, loading: defaultLoadingState } },
      }
      setMessages((current) => [...current, userMessage, assistantMessage])

      try {
        await api
          .post(`/workspaces/${workspaceId}/runs`, {
            chat_id: chatId,
            raw_intent: trimmed,
            locale: browserLocale(),
            timezone: browserTimezone(),
            state: 'intent_received',
            sources: notebookSources,
            metadata: { surface: 'assistant_ui' },
          })
          .catch(() => null)

        const token = useAuthStore.getState().token
        const response = await fetch(
          `/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages/stream`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
              content: `${trimmed}${buildSourceContext()}`,
            }),
          },
        )

        if (!response.ok) {
          if (response.status === 402) {
            const detail = await response.json().catch(() => null)
            throw new Error(
              detail?.message || 'Configure a model provider or upgrade the workspace plan.',
            )
          }
          throw new Error(await response.text())
        }

        const reader = response.body?.getReader()
        if (!reader) throw new Error('No readable response body')
        const decoder = new TextDecoder()
        let buffer = ''
        let assistantContent = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const frames = buffer.split('\n\n')
          buffer = frames.pop() || ''

          for (const frame of frames) {
            const jsonStr = frame
              .split('\n')
              .filter((line) => line.startsWith('data: '))
              .map((line) => line.slice(6).trim())
              .join('')
            if (!jsonStr || jsonStr === '[DONE]') continue
            try {
              const event = JSON.parse(jsonStr)
              if (event.type === 'status') {
                const nextLoading: LoadingState = {
                  title:
                    event.stage === 'executing'
                      ? 'Generating the response'
                      : event.stage === 'saved'
                      ? 'Saving the result'
                      : 'Preparing the workspace',
                  detail:
                    event.message ||
                    'Cognix is preparing the model, workspace context, and selected sources.',
                  steps: defaultLoadingState.steps.map((step) => {
                    if (event.stage === 'executing') {
                      return step.id === 'execute'
                        ? { ...step, status: 'running' }
                        : { ...step, status: 'done' }
                    }
                    if (event.stage === 'saved') return { ...step, status: 'done' }
                    return step
                  }),
                }
                setMessages((current) =>
                  current.map((message) =>
                    message.id === assistantId
                      ? {
                          ...message,
                          metadata: {
                            ...message.metadata,
                            custom: { ...message.metadata?.custom, loading: nextLoading },
                          },
                        }
                      : message,
                  ),
                )
              } else if (event.type === 'todo' && Array.isArray(event.items)) {
                const nextLoading: LoadingState = {
                  title: 'Working through the request',
                  detail: 'Cognix is resolving context, provider, and execution steps.',
                  steps: event.items.map((item: Partial<LoadingStep>, index: number) => ({
                    id: item.id || `step-${index}`,
                    label: item.label || `Step ${index + 1}`,
                    status: item.status || 'pending',
                  })),
                }
                setMessages((current) =>
                  current.map((message) =>
                    message.id === assistantId
                      ? {
                          ...message,
                          metadata: {
                            ...message.metadata,
                            custom: { ...message.metadata?.custom, loading: nextLoading },
                          },
                        }
                      : message,
                  ),
                )
              } else if (event.type === 'delta' || event.delta) {
                assistantContent += event.delta || event.data?.delta || ''
                setMessages((current) =>
                  current.map((message) =>
                    message.id === assistantId
                      ? {
                          ...message,
                          content: assistantContent,
                          status: { type: 'running' },
                          metadata: {
                            ...message.metadata,
                            custom: {
                              ...message.metadata?.custom,
                              loading: {
                                title: 'Writing the response',
                                detail: 'The first tokens are streaming in now.',
                                steps: [
                                  { id: 'intent', label: 'Understand intent', status: 'done' },
                                  { id: 'context', label: 'Load workspace context', status: 'done' },
                                  { id: 'execute', label: 'Generate response', status: 'running' },
                                ],
                              },
                            },
                          },
                        }
                      : message,
                  ),
                )
              } else if (event.type === 'error') {
                throw new Error(event.error || event.message || 'Model stream failed.')
              }
            } catch (error) {
              if (error instanceof Error && error.message !== 'Unexpected end of JSON input') {
                throw error
              }
            }
          }
        }

        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  content: assistantContent,
                  status: { type: 'complete', reason: 'stop' },
                }
              : message,
          ),
        )
        await refreshWorkflowState(chatId)
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to send message.'
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  content: `Error: ${message}`,
                  status: {
                    type: 'incomplete',
                    reason: 'error',
                    error: message,
                  },
                }
              : item,
          ),
        )
      } finally {
        setIsRunning(false)
        queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
        queryClient.invalidateQueries({ queryKey: ['workspace-chat-messages', workspaceId, chatId] })
        refreshWorkflowState(chatId)
      }
    },
    [
      activeChatId,
      buildSourceContext,
      createChat,
      isRunning,
      notebookSources,
      queryClient,
      refreshWorkflowState,
      workspaceId,
    ],
  )

  useEffect(() => {
    if (!requestedIntent?.text || !requestedIntent.autoSubmit) return
    void sendMessage(requestedIntent.text)
  }, [requestedIntent?.id, requestedIntent?.text, requestedIntent?.autoSubmit, sendMessage])

  const runtime = useExternalStoreRuntime(
    useMemo(
      () => ({
        messages,
        isRunning,
        isDisabled: false,
        setMessages: (nextMessages: readonly AssistantMessage[]) =>
          setMessages([...nextMessages]),
        onNew: async (message: AppendMessage) => {
          const text = messageText(message)
          await sendMessage(text)
        },
        convertMessage: (message: AssistantMessage) => message,
      }),
      [isRunning, messages, sendMessage],
    ),
  )

  return (
    <AssistantSurface
      runtime={runtime}
      workflowPanel={
        <WorkflowStatePanel
          latestRun={latestRun}
          pendingApproval={pendingApproval}
          busy={isRunning}
          onSubmit={handleApprovalSubmit}
        />
      }
    />
  )
}

function WorkflowStatePanel({
  latestRun,
  pendingApproval,
  busy,
  onSubmit,
}: {
  latestRun?: ConversationRun | null
  pendingApproval?: ApprovalRequest
  busy: boolean
  onSubmit: (approval: ApprovalRequest, response: string) => Promise<void>
}) {
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    setValue('')
    setError('')
  }, [pendingApproval?.id])

  if (!pendingApproval) return null

  const question =
    pendingApproval.reason ||
    String(pendingApproval.arguments?.question || pendingApproval.metadata?.question || '') ||
    'Cognix needs more information before it can continue.'
  const isUrlQuestion = /url|网址|入口|后台|链接/i.test(question)
  const intentSummary =
    String(latestRun?.intent?.summary || latestRun?.intent?.description || '') ||
    '已识别你想让 Cognix 完成一个需要工作区能力支持的任务。'

  const handleContinue = async () => {
    const trimmed = value.trim()
    if (!trimmed) {
      setError(isUrlQuestion ? '请先填写目标页面 URL。' : '请先填写补充信息。')
      return
    }
    if (isUrlQuestion) {
      try {
        const parsed = new URL(trimmed)
        if (!['http:', 'https:'].includes(parsed.protocol)) {
          setError('URL 需要以 http:// 或 https:// 开头。')
          return
        }
      } catch {
        setError('请输入有效 URL，例如 https://example.com。')
        return
      }
    }
    setSubmitting(true)
    setError('')
    try {
      await onSubmit(pendingApproval, trimmed)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex w-full justify-start">
      <div className="w-full max-w-3xl rounded-3xl border border-amber-500/25 bg-amber-50/70 p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[10px] font-black uppercase tracking-widest text-amber-700">
              Needs input
            </div>
            <h3 className="mt-1 text-base font-black text-foreground">
              我先确认意图，再补齐执行信息
            </h3>
          </div>
          <span className="rounded-full border border-amber-500/30 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-widest text-amber-700">
            Pending
          </span>
        </div>

        <div className="mt-4 grid gap-3">
          <div className="rounded-2xl border border-border/70 bg-white/80 p-4">
            <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-emerald-700">
              <CheckCircle2 className="h-4 w-4" />
              Step 1 · Intent understood
            </div>
            <p className="mt-2 text-sm leading-6 text-foreground">{intentSummary}</p>
          </div>

          <div className="rounded-2xl border border-amber-500/25 bg-white p-4">
            <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-amber-700">
              <Loader2 className="h-4 w-4" />
              Step 2 · Missing information
            </div>
            <p className="mt-2 text-sm font-bold leading-6 text-foreground">
              {isUrlQuestion
                ? '为了安全执行浏览器自动化，我需要先确认目标入口。'
                : '继续前还需要你补充下面的信息。'}
            </p>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">{question}</p>
            <div className="mt-4 flex gap-2">
              <input
                value={value}
                onChange={(event) => {
                  setValue(event.target.value)
                  setError('')
                }}
                placeholder={isUrlQuestion ? '粘贴目标页面 URL' : '填写补充信息'}
                className="h-11 min-w-0 flex-1 rounded-xl border border-border bg-background px-3 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/15"
              />
              <button
                type="button"
                disabled={busy || submitting}
                onClick={handleContinue}
                className="inline-flex h-11 items-center gap-2 rounded-xl bg-primary px-4 text-xs font-black text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:opacity-40"
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Continue
              </button>
            </div>
            {error && <div className="mt-2 text-xs font-bold text-rose-600">{error}</div>}
          </div>

          <div className="rounded-2xl border border-border/70 bg-white/70 p-4">
            <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-muted-foreground">
              <Circle className="h-4 w-4" />
              Step 3 · Plan and execute
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              信息补齐后，Cognix 会继续生成或恢复执行计划，再根据需要调用浏览器、Skill、MCP、CLI 或其他内部能力。
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
