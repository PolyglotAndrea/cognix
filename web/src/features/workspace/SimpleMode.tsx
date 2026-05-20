import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquarePlus, Settings, Send, Loader2 } from 'lucide-react'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { RichMessage } from '@/shared/ui'

interface SimpleModeProps {
  workspaceId: string
  onSwitchToAdvanced: () => void
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
}

export function SimpleMode({ workspaceId, onSwitchToAdvanced }: SimpleModeProps) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([])
  const [streaming, setStreaming] = useState(false)
  const [streamSteps, setStreamSteps] = useState<StreamStep[]>([])
  const [activeChatId, setActiveChatId] = useState<string | null>(null)
  const queryClient = useQueryClient()

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
    setStreamSteps([])
  }, [workspaceId])

  useEffect(() => {
    if (activeChatId || chats.length === 0) return
    setActiveChatId(chats[0].id)
  }, [activeChatId, chats])

  useEffect(() => {
    if (streaming || !storedMessages) return
    setMessages(
      storedMessages
        .filter((message) => message.role === 'user' || message.role === 'assistant')
        .map((message) => ({ role: message.role, content: message.content }))
    )
  }, [storedMessages, streaming])

  const createChat = async () => {
    const created = await api
      .post(`/workspaces/${workspaceId}/chats`, {
        title: 'Simple Chat',
        metadata: { mode: 'simple' },
      })
      .then((r) => r.data as ChatSession)
    setActiveChatId(created.id)
    setMessages([])
    await queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
    return created.id
  }

  const handleSend = async () => {
    if (!input.trim() || streaming) return
    const userMsg = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }])

    let chatId = activeChatId
    try {
      chatId = chatId || (await createChat())
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Failed to initialize chat.' }])
      return
    }

    setStreaming(true)
    setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

    try {
      const token = useAuthStore.getState().token
      const resp = await fetch(`/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ content: userMsg }),
      })

      if (!resp.ok) {
        const errText = await resp.text()
        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = { role: 'assistant', content: `Error: ${errText}` }
          return updated
        })
        return
      }

      const reader = resp.body?.getReader()
      if (!reader) return
      const decoder = new TextDecoder()
      let assistantContent = ''
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
            if (event.type === 'delta' && event.delta) {
              assistantContent += event.delta
              setMessages((prev) => {
                const updated = [...prev]
                updated[updated.length - 1] = { role: 'assistant', content: assistantContent }
                return updated
              })
            } else if (event.type === 'todo' && Array.isArray(event.items)) {
              setStreamSteps(
                event.items.map((item: Partial<StreamStep>, index: number) => ({
                  id: item.id || `step-${index}`,
                  label: item.label || `Step ${index + 1}`,
                  status: item.status || 'pending',
                }))
              )
            } else if (event.type === 'error') {
              const error = event.error || event.message || 'Model stream failed.'
              setStreamSteps((items) =>
                items.map((item) =>
                  item.status === 'running' ? { ...item, status: 'failed' } : item
                )
              )
              setMessages((prev) => {
                const updated = [...prev]
                updated[updated.length - 1] = { role: 'assistant', content: `Error: ${error}` }
                return updated
              })
            }
          } catch {
            // skip malformed events
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { role: 'assistant', content: 'Connection error.' }
        return updated
      })
    } finally {
      setStreaming(false)
      setStreamSteps([])
      queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-chat-messages', workspaceId, chatId] })
    }
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-border bg-card/50 backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-sm font-bold text-foreground">Cognix</span>
          <span className="text-xs text-muted-foreground">Simple Mode</span>
        </div>
        <button
          type="button"
          onClick={() => switchModeMutation.mutate()}
          className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
        >
          <Settings className="h-3.5 w-3.5" />
          Switch to Advanced
        </button>
      </div>

      <div className="border-b border-border bg-card/30 px-6 py-2">
        <div className="mx-auto flex w-full max-w-2xl items-center gap-2 overflow-x-auto scrollbar-hide">
          <span className="shrink-0 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            Sessions
          </span>
          {chats.map((chat) => (
            <button
              key={chat.id}
              type="button"
              onClick={() => {
                setActiveChatId(chat.id)
                setMessages([])
                setStreamSteps([])
              }}
              className={`max-w-[160px] shrink-0 truncate rounded-lg border px-3 py-1.5 text-[11px] font-bold transition-all ${
                chat.id === activeChatId
                  ? 'border-primary/30 bg-primary/10 text-primary'
                  : 'border-border bg-background text-muted-foreground hover:text-foreground'
              }`}
              title={chat.title}
            >
              {chat.title}
            </button>
          ))}
          {chats.length === 0 && (
            <span className="shrink-0 rounded-lg border border-dashed border-border px-3 py-1.5 text-[11px] font-bold text-muted-foreground">
              {chatsLoading ? 'Loading...' : 'No sessions'}
            </span>
          )}
          <button
            type="button"
            onClick={() => createChat()}
            className="ml-auto flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-border bg-background px-3 text-[11px] font-bold text-muted-foreground transition-colors hover:text-foreground"
          >
            <MessageSquarePlus className="h-3.5 w-3.5" />
            New
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 max-w-2xl mx-auto w-full">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
              <Send className="h-7 w-7 text-primary" />
            </div>
            <h3 className="text-sm font-bold text-foreground mb-1">How can I help?</h3>
            <p className="text-xs text-muted-foreground max-w-xs">
              Type a message below to start a conversation with your AI assistant.
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted border border-border text-foreground'
              }`}
            >
              {msg.content ? (
                msg.role === 'assistant' ? (
                  <RichMessage content={msg.content} compact />
                ) : (
                  <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                )
              ) : streaming && i === messages.length - 1 ? (
                <div className="flex gap-1.5 py-1">
                  <div className="h-2 w-2 animate-bounce rounded-full bg-current opacity-40" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-current opacity-40 [animation-delay:0.2s]" />
                  <div className="h-2 w-2 animate-bounce rounded-full bg-current opacity-40 [animation-delay:0.4s]" />
                </div>
              ) : null}
            </div>
          </div>
        ))}
        {streaming && streamSteps.length > 0 && (
          <div className="rounded-2xl border border-border bg-card/70 px-4 py-3 text-xs text-muted-foreground">
            <div className="mb-2 font-bold uppercase tracking-widest text-foreground/70">
              Execution checklist
            </div>
            <div className="space-y-1.5">
              {streamSteps.map((step) => (
                <div key={step.id} className="flex items-center justify-between gap-3">
                  <span>{step.label}</span>
                  <span className="font-bold uppercase tracking-wider text-[10px]">{step.status}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border bg-card/50 backdrop-blur-xl p-4">
        <div className="max-w-2xl mx-auto flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Type a message..."
            disabled={streaming}
            className="flex-1 rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="w-10 h-10 rounded-xl bg-primary text-primary-foreground flex items-center justify-center hover:bg-primary/90 transition-all active:scale-95 disabled:opacity-50"
          >
            {streaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
