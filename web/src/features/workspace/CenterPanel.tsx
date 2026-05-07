import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bot, Columns3, FileText, Paperclip, Send, User, X, Zap } from 'lucide-react'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { useWorkspaceStore } from './store'
import { Spinner, Badge, RichMessage } from '@/shared/ui'

interface Agent {
  id: string
  name: string
  model: string
  system_prompt?: string
}

interface WorkspaceInfo {
  id: string
  name: string
}

interface ChatResponse {
  model: string
  content: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  model?: string
  responses?: ChatResponse[]
}

interface PendingAttachment {
  id: string
  name: string
  mime_type: string
  size: number
  kind: string
  content: string
}

export function CenterPanel() {
  const { selectedAgentId, addToolResult, addLog } = useWorkspaceStore()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [chatId, setChatId] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const ensuredWorkspaceRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: agent } = useQuery<Agent>({
    queryKey: ['agent', selectedAgentId],
    queryFn: () => api.get(`/agents/${selectedAgentId}`).then((r) => r.data),
    enabled: !!selectedAgentId,
  })

  const {
    data: workspaces = [],
    isLoading: workspacesLoading,
    refetch: refetchWorkspaces,
  } = useQuery<WorkspaceInfo[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get('/workspaces').then((r) => r.data),
  })

  const workspaceId = workspaces[0]?.id || null
  const availableModels = Array.from(
    new Set([agent?.model || 'echo', 'echo', 'gpt-4o-mini', 'gpt-4o', 'claude-3.5-sonnet'])
  )
  const activeModels = selectedModels.length > 0 ? selectedModels : [agent?.model || 'echo']

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (workspacesLoading || ensuredWorkspaceRef.current || workspaces.length > 0) return
    ensuredWorkspaceRef.current = true
    api
      .post('/workspaces', { name: 'Default Workspace' })
      .then(() => refetchWorkspaces())
      .catch((err) => {
        addLog({
          id: '',
          level: 'error',
          message: `Workspace init error: ${err instanceof Error ? err.message : 'Unknown'}`,
          timestamp: Date.now(),
        })
      })
  }, [addLog, refetchWorkspaces, workspaces.length, workspacesLoading])

  // Reset and create a local-first chat when agent changes.
  useEffect(() => {
    let cancelled = false
    setMessages([])
    setChatId(null)
    setAttachments([])
    setSelectedModels(agent ? [agent.model] : [])

    if (!selectedAgentId || !agent || !workspaceId) return

    api
      .post(`/workspaces/${workspaceId}/chats`, {
        title: `${agent.name} Session`,
        system_prompt: agent.system_prompt || '',
        model_profiles: [agent.model],
        metadata: { agent_id: agent.id },
      })
      .then((response) => {
        if (!cancelled) setChatId(response.data.id)
      })
      .catch((err) => {
        addLog({
          id: '',
          level: 'error',
          message: `Chat init error: ${err instanceof Error ? err.message : 'Unknown'}`,
          timestamp: Date.now(),
        })
      })

    return () => {
      cancelled = true
    }
  }, [addLog, agent, selectedAgentId, workspaceId])

  const sendMessage = async () => {
    if (!input.trim() || !selectedAgentId || !workspaceId || !chatId || isStreaming) return

    const userMsg: Message = { role: 'user', content: input.trim() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    const outgoingAttachments = attachments
    setAttachments([])
    setIsStreaming(true)

    const token = useAuthStore.getState().token
    const requestBody = {
      content: userMsg.content,
      models: activeModels,
      attachments: outgoingAttachments.map((attachment) => ({
        id: attachment.id,
        name: attachment.name,
        path: `browser://${attachment.name}`,
        mime_type: attachment.mime_type,
        size: attachment.size,
        kind: attachment.kind,
        content: attachment.content,
      })),
    }

    try {
      if (activeModels.length > 1) {
        const response = await fetch(
          `/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify(requestBody),
          }
        )
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const data = await response.json()
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: '',
            responses: data.assistant_messages.map((message: { model: string; content: string }) => ({
              model: message.model,
              content: message.content,
            })),
          },
        ])
        return
      }

      const response = await fetch(
        `/api/v1/workspaces/${workspaceId}/chats/${chatId}/messages/stream`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(requestBody),
        }
      )

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No reader')

      const decoder = new TextDecoder()
      let assistantContent = ''
      setMessages((prev) => [...prev, { role: 'assistant', content: '' }])

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const text = decoder.decode(value, { stream: true })
        const lines = text.split('\n')

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const jsonStr = line.slice(6).trim()
          if (!jsonStr || jsonStr === '[DONE]') continue

          try {
            const event = JSON.parse(jsonStr)

            if (event.type === 'tool_call') {
              addLog({
                id: '',
                level: 'info',
                message: `Calling tool: ${event.name}`,
                timestamp: Date.now(),
              })
            } else if (event.type === 'tool_result') {
              addToolResult({
                id: '',
                name: event.name,
                args: event.args,
                result: event.result,
                timestamp: Date.now(),
              })
              addLog({
                id: '',
                level: 'info',
                message: `Tool ${event.name} completed`,
                timestamp: Date.now(),
              })
            } else if (event.type === 'log') {
              addLog({
                id: '',
                level: event.level || 'info',
                message: event.message,
                timestamp: Date.now(),
              })
            } else if (event.delta) {
              assistantContent += event.delta
              setMessages((prev) => {
                const updated = [...prev]
                updated[updated.length - 1] = {
                  role: 'assistant',
                  content: assistantContent,
                }
                return updated
              })
            }
          } catch {
            // skip malformed JSON
          }
        }
      }
    } catch (err) {
      addLog({
        id: '',
        level: 'error',
        message: `Chat error: ${err instanceof Error ? err.message : 'Unknown'}`,
        timestamp: Date.now(),
      })
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: 'assistant', content: 'Error: Failed to get response.' },
      ])
    } finally {
      setIsStreaming(false)
    }
  }

  const toggleModel = (model: string) => {
    setSelectedModels((current) => {
      if (current.includes(model)) {
        return current.length === 1 ? current : current.filter((item) => item !== model)
      }
      return [...current, model]
    })
  }

  const attachFiles = async (files: FileList | null) => {
    if (!files?.length) return
    const next: PendingAttachment[] = []
    for (const file of Array.from(files)) {
      if (!isTextLike(file)) {
        addLog({
          id: '',
          level: 'warn',
          message: `Skipped unsupported attachment: ${file.name}`,
          timestamp: Date.now(),
        })
        continue
      }
      const content = await file.text()
      next.push({
        id: crypto.randomUUID(),
        name: file.name,
        mime_type: file.type || 'text/plain',
        size: file.size,
        kind: 'file',
        content,
      })
    }
    setAttachments((prev) => [...prev, ...next])
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((attachment) => attachment.id !== id))
  }

  if (!selectedAgentId) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background relative overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary/5 blur-[120px] rounded-full" />
        <div className="relative text-center z-10">
          <div className="w-20 h-20 bg-muted rounded-[2rem] flex items-center justify-center mx-auto mb-6 border border-border shadow-2xl">
            <Zap className="h-10 w-10 text-primary fill-current" />
          </div>
          <h2 className="text-2xl font-bold text-foreground mb-3">Cognix Runtime</h2>
          <p className="text-muted-foreground max-w-xs mx-auto leading-relaxed">
            Initialize an agent session from the sidebar to begin multi-agent orchestration and task execution.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-background relative">
      {/* Header */}
      <div className="h-14 px-6 border-b border-border bg-card/50 backdrop-blur-md flex items-center justify-between shrink-0 z-20">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center border border-primary/20">
            <Bot className="h-4 w-4 text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-foreground">{agent?.name || 'Agent'}</span>
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-sm shadow-emerald-500/50" />
            </div>
            <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-widest">{agent?.model}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {activeModels.length > 1 && (
            <Badge variant="primary" className="h-6">
              Compare {activeModels.length}
            </Badge>
          )}
          <Badge variant="primary" className="h-6">Session Active</Badge>
        </div>
      </div>

      <div className="px-6 py-3 border-b border-border bg-card/30 flex items-center gap-2 shrink-0">
        <div className="flex items-center gap-2 mr-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          <Columns3 className="h-3.5 w-3.5 text-primary" />
          Models
        </div>
        <div className="flex flex-wrap gap-2">
          {availableModels.map((model) => (
            <button
              key={model}
              onClick={() => toggleModel(model)}
              className={`px-3 py-1.5 rounded-lg border text-[11px] font-bold transition-all ${
                activeModels.includes(model)
                  ? 'bg-primary/10 border-primary/30 text-primary'
                  : 'bg-background border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              {model}
            </button>
          ))}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto p-8 space-y-8 scrollbar-hide">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center py-12 animate-in fade-in duration-700">
            <div className="w-20 h-20 bg-muted rounded-full flex items-center justify-center mb-6 border border-border relative">
               <div className="absolute inset-0 bg-primary/10 blur-xl rounded-full animate-pulse" />
               <Bot className="h-10 w-10 text-muted-foreground/40 relative z-10" />
            </div>
            <h3 className="text-lg font-bold text-foreground mb-2">Awaiting Instructions</h3>
            <p className="text-sm text-muted-foreground max-w-[260px] text-center leading-relaxed font-medium">
              Start a high-context conversation with <span className="text-primary">{agent?.name || 'the agent'}</span> to begin problem solving.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : 'animate-in slide-in-from-left-2 duration-300'}`}
          >
            <div
              className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border transition-all ${
                msg.role === 'user'
                  ? 'bg-primary/10 border-primary/20 shadow-lg shadow-primary/5'
                  : 'bg-muted border-border'
              }`}
            >
              {msg.role === 'user' ? (
                <User className="h-4 w-4 text-primary" />
              ) : (
                <Bot className="h-4 w-4 text-muted-foreground" />
              )}
            </div>
            <div
              className={`${
                msg.responses ? 'max-w-[92%] w-full' : 'max-w-[75%]'
              } px-5 py-3.5 rounded-[1.5rem] text-sm leading-relaxed shadow-xl ${
                msg.role === 'user'
                  ? 'bg-primary text-white rounded-tr-sm shadow-primary/10'
                  : 'bg-muted/50 text-foreground border border-border rounded-tl-sm backdrop-blur-sm'
              }`}
            >
              <div className="font-medium">
                {msg.content || (isStreaming && i === messages.length - 1 ? (
                  <div className="flex gap-1.5 py-1">
                    <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce" />
                    <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce [animation-delay:0.2s]" />
                    <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce [animation-delay:0.4s]" />
                  </div>
                ) : msg.responses ? (
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                    {msg.responses.map((response) => (
                      <div
                        key={response.model}
                        className="rounded-2xl border border-border bg-background/70 p-4 min-w-0"
                      >
                        <div className="mb-3 flex items-center justify-between gap-2">
                          <span className="text-[10px] font-bold uppercase tracking-widest text-primary">
                            {response.model}
                          </span>
                        </div>
                        <RichMessage content={response.content} />
                      </div>
                    ))}
                  </div>
                ) : (
                  <RichMessage content={msg.content} compact={msg.role === 'user'} />
                ))}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-6 bg-gradient-to-t from-background via-background to-transparent shrink-0 z-20">
        {attachments.length > 0 && (
          <div className="max-w-4xl mx-auto mb-3 flex flex-wrap gap-2">
            {attachments.map((attachment) => (
              <div
                key={attachment.id}
                className="flex items-center gap-2 px-3 py-2 bg-card border border-border rounded-xl text-xs text-muted-foreground shadow-sm"
              >
                <FileText className="h-3.5 w-3.5 text-primary" />
                <span className="max-w-[180px] truncate font-medium">{attachment.name}</span>
                <button
                  onClick={() => removeAttachment(attachment.id)}
                  className="p-0.5 hover:text-destructive transition-colors"
                  aria-label={`Remove ${attachment.name}`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="max-w-4xl mx-auto flex gap-3 p-2 bg-card border border-border rounded-2xl shadow-2xl focus-within:border-primary/40 focus-within:ring-4 focus-within:ring-primary/10 transition-all">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => attachFiles(event.target.files)}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming}
            className="w-11 h-11 text-muted-foreground rounded-xl flex items-center justify-center hover:bg-muted hover:text-foreground disabled:opacity-30 transition-all"
            aria-label="Attach files"
          >
            <Paperclip className="h-5 w-5" />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
            placeholder="Instruct the agent..."
            disabled={isStreaming}
            className="flex-1 px-4 py-3 bg-transparent text-sm text-foreground outline-none disabled:opacity-50 placeholder:text-muted-foreground/40 font-medium"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming || !chatId}
            className="w-11 h-11 bg-primary text-white rounded-xl flex items-center justify-center hover:bg-primary/90 disabled:opacity-30 disabled:grayscale transition-all shadow-lg shadow-primary/20 active:scale-95"
          >
            {isStreaming ? <Spinner size="sm" className="text-white" /> : <Send className="h-5 w-5" />}
          </button>
        </div>
        <p className="text-center mt-4 text-[10px] text-muted-foreground/50 font-bold uppercase tracking-widest">
          {activeModels.length > 1
            ? 'Multi-model comparison active'
            : 'Multi-agent orchestration active • Tool calling enabled'}
        </p>
      </div>
    </div>
  )
}

function isTextLike(file: File) {
  if (file.type.startsWith('text/')) return true
  return /\.(md|txt|json|csv|ya?ml|toml|py|ts|tsx|js|jsx|css|html|xml|sql|sh|log)$/i.test(
    file.name
  )
}
