import { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  Check,
  Columns3,
  FileText,
  History,
  Image,
  MessageSquare,
  MessageSquarePlus,
  Paperclip,
  Save,
  Send,
  Settings,
  Sparkles,
  User,
  X,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { useWorkspaceStore } from './store'
import { TaskComposer } from './TaskComposer'
import { Spinner, Badge, RichMessage, Panel, PanelHeader } from '@/shared/ui'
import type { DragHandleProps } from './types'

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

interface ChatSession {
  id: string
  workspace_id: string
  title: string
  created_at: string
  updated_at: string
  system_prompt: string
  model_profiles: string[]
  metadata: Record<string, unknown>
}

interface StoredMessage {
  id: string
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  model?: string
  parent_id?: string
}

interface ChatResponse {
  model: string
  content: string
}

interface Message {
  id?: string
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

export function CenterPanel({ dragHandleProps }: { dragHandleProps?: DragHandleProps }) {
  const { selectedAgentId, setSelectedAgent, inputMode, setInputMode, addToolResult, addLog } = useWorkspaceStore()
  const queryClient = useQueryClient()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [chatId, setChatId] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [systemPrompt, setSystemPrompt] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [promptSaved, setPromptSaved] = useState(false)
  const ensuredWorkspaceRef = useRef(false)
  const creatingChatRef = useRef<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: agent } = useQuery<Agent>({
    queryKey: ['agent', selectedAgentId],
    queryFn: () => api.get(`/agents/${selectedAgentId}`).then((r) => r.data),
    enabled: !!selectedAgentId,
  })

  const {
    data: workspaces,
    isLoading: workspacesLoading,
    refetch: refetchWorkspaces,
  } = useQuery<WorkspaceInfo[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get('/workspaces').then((r) => r.data),
  })

  const workspaceId = workspaces?.[0]?.id || null
  const availableModels = Array.from(
    new Set([agent?.model || 'gpt-4o', 'gpt-4o-mini', 'gpt-4o', 'claude-3.5-sonnet'])
  )
  const activeModels = selectedModels.length > 0 ? selectedModels : [agent?.model || 'gpt-4o']

  const {
    data: chats,
    isLoading: chatsLoading,
    refetch: refetchChats,
  } = useQuery<ChatSession[]>({
    queryKey: ['workspace-chats', workspaceId, selectedAgentId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/chats`).then((r) => r.data),
    enabled: !!workspaceId && !!selectedAgentId,
  })

  const agentChats = useMemo(() => 
    (chats || []).filter((chat) => chat.metadata?.agent_id === selectedAgentId),
    [chats, selectedAgentId]
  )
  const activeChat = useMemo(() => 
    agentChats.find((chat) => chat.id === chatId) || null,
    [agentChats, chatId]
  )

  const { data: storedMessages } = useQuery<StoredMessage[]>({
    queryKey: ['workspace-chat-messages', workspaceId, chatId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/chats/${chatId}/messages`).then((r) => r.data),
    enabled: !!workspaceId && !!chatId && !isStreaming,
  })

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (workspacesLoading || ensuredWorkspaceRef.current || (workspaces && workspaces.length > 0)) return
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
  }, [addLog, refetchWorkspaces, workspaces?.length, workspacesLoading])

  useEffect(() => {
    setMessages([])
    setChatId(null)
    setAttachments([])
    setSelectedModels(agent ? [agent.model] : [])
    setSystemPrompt(agent?.system_prompt || '')
    setSettingsOpen(false)
  }, [agent, selectedAgentId])

  useEffect(() => {
    if (!agent || !workspaceId || chatsLoading || chatId) return
    const latest = agentChats[0]
    if (latest) {
      activateChat(latest)
      return
    }
    createChat()
  }, [agent, agentChats, chatId, chatsLoading, workspaceId])

  useEffect(() => {
    if (isStreaming || !storedMessages) return
    setMessages(storedToMessages(storedMessages))
  }, [isStreaming, storedMessages])

  useEffect(() => {
    if (!promptSaved) return
    const timeout = window.setTimeout(() => setPromptSaved(false), 1400)
    return () => window.clearTimeout(timeout)
  }, [promptSaved])

  const activateChat = (chat: ChatSession) => {
    setChatId(chat.id)
    setSystemPrompt(chat.system_prompt || agent?.system_prompt || '')
    setSelectedModels(chat.model_profiles.length > 0 ? chat.model_profiles : [agent?.model || 'gpt-4o'])
    setAttachments([])
  }

  const createChat = async () => {
    if (!agent || !workspaceId) return
    const key = `${workspaceId}:${agent.id}`
    if (creatingChatRef.current === key) return
    creatingChatRef.current = key

    try {
      const response = await api.post(`/workspaces/${workspaceId}/chats`, {
        title: `${agent.name} Session`,
        system_prompt: agent.system_prompt || '',
        model_profiles: [agent.model],
        metadata: { agent_id: agent.id },
      })
      await refetchChats()
      activateChat(response.data)
    } catch (err) {
      addLog({
        id: '',
        level: 'error',
        message: `Chat init error: ${err instanceof Error ? err.message : 'Unknown'}`,
        timestamp: Date.now(),
      })
    } finally {
      creatingChatRef.current = null
    }
  }

  const saveChatSettings = async () => {
    if (!workspaceId || !chatId) return
    try {
      await api.patch(`/workspaces/${workspaceId}/chats/${chatId}`, {
        system_prompt: systemPrompt,
        model_profiles: activeModels,
      })
      setPromptSaved(true)
      await refetchChats()
    } catch (err) {
      addLog({
        id: '',
        level: 'error',
        message: `Chat settings error: ${err instanceof Error ? err.message : 'Unknown'}`,
        timestamp: Date.now(),
      })
    }
  }

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
      if (
        activeChat &&
        (activeChat.system_prompt !== systemPrompt ||
          activeChat.model_profiles.join('|') !== activeModels.join('|'))
      ) {
        await api.patch(`/workspaces/${workspaceId}/chats/${chatId}`, {
          system_prompt: systemPrompt,
          model_profiles: activeModels,
        })
        await refetchChats()
      }

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
        if (!response.ok) {
          if (response.status === 402) {
            const detail = await response.json().catch(() => null)
            setMessages((prev) => [
              ...prev.slice(0, -1),
              {
                role: 'assistant',
                content:
                  '⚠️ **Model Provider Required**\n\n' +
                  (detail?.message || 'Configure a model provider or upgrade your plan to continue.') +
                  '\n\nGo to **Settings → Model Providers** to configure your workspace LLM provider.',
              },
            ])
            return
          }
          throw new Error(`HTTP ${response.status}`)
        }
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
        queryClient.invalidateQueries({ queryKey: ['workspace-chat-messages', workspaceId, chatId] })
        queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId, selectedAgentId] })
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

      if (!response.ok) {
        if (response.status === 402) {
          const detail = await response.json().catch(() => null)
          setMessages((prev) => [
            ...prev.slice(0, -1),
            {
              role: 'assistant',
              content:
                '⚠️ **Model Provider Required**\n\n' +
                (detail?.message || 'Configure a model provider or upgrade your plan to continue.') +
                '\n\nGo to **Settings → Model Providers** to configure your workspace LLM provider.',
            },
          ])
          return
        }
        throw new Error(`HTTP ${response.status}`)
      }

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
            } else if (event.type === 'approval_request') {
              useWorkspaceStore.getState().setRightPanelTab('approvals')
              addLog({
                id: '',
                level: 'warn',
                message: `Approval requested for ${event.name || event.tool}: ${event.reason}`,
                timestamp: Date.now(),
              })
              queryClient.invalidateQueries({ queryKey: ['approvals', workspaceId] })
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
      queryClient.invalidateQueries({ queryKey: ['workspace-chat-messages', workspaceId, chatId] })
      queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId, selectedAgentId] })
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
        if (!isImageLike(file)) {
          addLog({
            id: '',
            level: 'warn',
            message: `Skipped unsupported attachment: ${file.name}`,
            timestamp: Date.now(),
          })
          continue
        }
        next.push({
          id: crypto.randomUUID(),
          name: file.name,
          mime_type: file.type || 'image/png',
          size: file.size,
          kind: 'image',
          content: await readFileAsDataUrl(file),
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

  // Plan mode: show TaskComposer as primary view
  const mode: string = inputMode
  if (inputMode === 'plan' && workspaceId) {
    return (
      <Panel className="flex-1 flex flex-col min-w-0 bg-background relative h-full">
        <PanelHeader dragHandleProps={dragHandleProps} className="bg-card/50 backdrop-blur-md">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center border border-primary/20">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
              <div>
                <span className="text-sm font-bold text-foreground">Plan Mode</span>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-widest">
                  Describe what you need — Cognix will build it
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setInputMode('plan')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all ${
                  mode === 'plan'
                    ? 'bg-primary/10 text-primary border border-primary/20'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted border border-transparent'
                }`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                Plan
              </button>
              <button
                onClick={() => { if (selectedAgentId) setInputMode('chat') }}
                disabled={!selectedAgentId}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all ${
                  mode === 'chat'
                    ? 'bg-primary/10 text-primary border border-primary/20'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted border border-transparent disabled:opacity-30'
                }`}
              >
                <MessageSquare className="h-3.5 w-3.5" />
                Chat
              </button>
            </div>
          </div>
        </PanelHeader>
        <div className="flex-1 overflow-auto flex items-start justify-center p-8">
          <div className="w-full max-w-2xl pt-8">
            <div className="text-center mb-8">
              <h2 className="text-xl font-bold text-foreground mb-2">What do you want to do?</h2>
              <p className="text-sm text-muted-foreground">
                Describe your goal and Cognix will create agents, configure tools, and execute automatically.
              </p>
            </div>
            <TaskComposer
              workspaceId={workspaceId}
              onPlanApplied={(result) => {
                addLog({
                  id: '',
                  level: 'info',
                  message: `Plan applied: ${result.status}. Created ${result.created.agents?.length || 0} agents, ${result.created.tasks?.length || 0} tasks.`,
                  timestamp: Date.now(),
                })
              }}
              onAgentCreated={(agentId) => {
                setSelectedAgent(agentId)
                setInputMode('chat')
              }}
            />
          </div>
        </div>
      </Panel>
    )
  }

  if (!selectedAgentId) {
    return (
      <Panel className="flex-1 flex flex-col min-w-0 bg-background relative h-full">
        <PanelHeader dragHandleProps={dragHandleProps} className="bg-card/50 backdrop-blur-md">
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-primary/10 rounded-lg flex items-center justify-center border border-primary/20">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
              <div>
                <span className="text-sm font-bold text-foreground">Plan Mode</span>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-widest">
                  Describe what you need — Cognix will build it
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setInputMode('plan')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all ${
                  inputMode === 'plan'
                    ? 'bg-primary/10 text-primary border border-primary/20'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted border border-transparent'
                }`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                Plan
              </button>
              <button
                disabled
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold text-muted-foreground border border-transparent opacity-30"
              >
                <MessageSquare className="h-3.5 w-3.5" />
                Chat
              </button>
            </div>
          </div>
        </PanelHeader>
        <div className="flex-1 overflow-auto flex items-start justify-center p-8">
          <div className="w-full max-w-2xl pt-8">
            <div className="text-center mb-8">
              <h2 className="text-xl font-bold text-foreground mb-2">What do you want to do?</h2>
              <p className="text-sm text-muted-foreground">
                Describe your goal and Cognix will create agents, configure tools, and execute automatically.
              </p>
            </div>
            {workspaceId && (
              <TaskComposer
                workspaceId={workspaceId}
                onPlanApplied={(result) => {
                  addLog({
                    id: '',
                    level: 'info',
                    message: `Plan applied: ${result.status}. Created ${result.created.agents?.length || 0} agents, ${result.created.tasks?.length || 0} tasks.`,
                    timestamp: Date.now(),
                  })
                }}
                onAgentCreated={(agentId) => {
                  setSelectedAgent(agentId)
                  setInputMode('chat')
                }}
              />
            )}
          </div>
        </div>
      </Panel>
    )
  }

  return (
    <Panel className="flex-1 flex flex-col min-w-0 bg-background relative h-full">
      {/* Header */}
      <PanelHeader dragHandleProps={dragHandleProps} className="bg-card/50 backdrop-blur-md">
        <div className="flex items-center justify-between w-full">
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
          <div className="flex items-center gap-3">
            <button
              onClick={() => setInputMode('plan')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all ${
                inputMode === 'plan'
                  ? 'bg-primary/10 text-primary border border-primary/20'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted border border-transparent'
              }`}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Plan
            </button>
            <button
              onClick={() => setInputMode('chat')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all ${
                inputMode === 'chat'
                  ? 'bg-primary/10 text-primary border border-primary/20'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted border border-transparent'
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              Chat
            </button>
            <div className="w-px h-5 bg-border" />
            <button
              onClick={() => createChat()}
              disabled={!agent || !workspaceId}
              className="w-8 h-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-30 flex items-center justify-center transition-colors"
              aria-label="New chat"
              title="New chat"
            >
              <MessageSquarePlus className="h-4 w-4" />
            </button>
            <button
              onClick={() => setSettingsOpen((open) => !open)}
              className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
                settingsOpen
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
              }`}
              aria-label="Chat settings"
              title="Chat settings"
            >
              <Settings className="h-4 w-4" />
            </button>
            {activeModels.length > 1 && (
              <Badge variant="primary" className="h-6">
                Compare {activeModels.length}
              </Badge>
            )}
            <Badge variant="primary" className="h-6">
              {activeChat?.title || 'Session Active'}
            </Badge>
          </div>
        </div>
      </PanelHeader>

      <div className="px-6 py-3 border-b border-border bg-card/30 flex items-center gap-3 shrink-0 overflow-hidden">
        <div className="flex items-center gap-2 mr-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground shrink-0">
          <History className="h-3.5 w-3.5 text-primary" />
          Chats
        </div>
        <div className="flex gap-2 overflow-x-auto scrollbar-hide min-w-0">
          {agentChats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => activateChat(chat)}
              className={`max-w-[180px] px-3 py-1.5 rounded-lg border text-[11px] font-bold truncate transition-all ${
                chat.id === chatId
                  ? 'bg-primary/10 border-primary/30 text-primary'
                  : 'bg-background border-border text-muted-foreground hover:text-foreground'
              }`}
              title={chat.title}
            >
              {chat.title}
            </button>
          ))}
          {agentChats.length === 0 && (
            <span className="px-3 py-1.5 rounded-lg border border-dashed border-border text-[11px] font-bold text-muted-foreground">
              {chatsLoading ? 'Loading...' : 'New session'}
            </span>
          )}
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

      {settingsOpen && (
        <div className="px-6 py-4 border-b border-border bg-card/70 shrink-0">
          <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-3 items-end">
            <label className="block min-w-0">
              <span className="block mb-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                System Prompt
              </span>
              <textarea
                value={systemPrompt}
                onChange={(event) => setSystemPrompt(event.target.value)}
                rows={3}
                className="w-full px-4 py-3 bg-background border border-border rounded-xl text-xs text-foreground resize-none outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 font-mono leading-relaxed"
                placeholder="Define this chat's behavior and context rules..."
              />
            </label>
            <button
              onClick={saveChatSettings}
              disabled={!chatId}
              className="h-10 px-4 rounded-xl bg-primary text-white hover:bg-primary/90 disabled:opacity-30 transition-all shadow-lg shadow-primary/20 flex items-center justify-center gap-2 text-[11px] font-bold uppercase tracking-wider"
            >
              {promptSaved ? <Check className="h-4 w-4" /> : <Save className="h-4 w-4" />}
              {promptSaved ? 'Saved' : 'Save'}
            </button>
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-auto p-8 space-y-8 scrollbar-hide">
        {messages.map((msg, i) => (
          <div
            key={msg.id || `${msg.role}-${i}`}
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
                {msg.model && !msg.responses && (
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-widest text-primary">
                    {msg.model}
                  </div>
                )}
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
                {attachment.kind === 'image' ? (
                  <Image className="h-3.5 w-3.5 text-primary" />
                ) : (
                  <FileText className="h-3.5 w-3.5 text-primary" />
                )}
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
            accept="text/*,image/*,.md,.txt,.json,.csv,.yaml,.yml,.toml,.py,.ts,.tsx,.js,.jsx,.css,.html,.xml,.sql,.sh,.log"
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
    </Panel>
  )
}

function isTextLike(file: File) {
  if (file.type.startsWith('text/')) return true
  return /\.(md|txt|json|csv|ya?ml|toml|py|ts|tsx|js|jsx|css|html|xml|sql|sh|log)$/i.test(
    file.name
  )
}

function isImageLike(file: File) {
  return file.type.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp)$/i.test(file.name)
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('Failed to read file'))
    reader.readAsDataURL(file)
  })
}

function storedToMessages(storedMessages: StoredMessage[]): Message[] {
  const rendered: Message[] = []
  const compareByParent = new Map<string, Message>()

  for (const message of storedMessages) {
    if (message.role === 'user') {
      rendered.push({ id: message.id, role: 'user', content: message.content })
      continue
    }

    if (message.role !== 'assistant') continue

    if (message.parent_id) {
      const existing = compareByParent.get(message.parent_id)
      if (existing?.responses) {
        existing.responses.push({
          model: message.model || 'assistant',
          content: message.content,
        })
        continue
      }

      const grouped: Message = {
        id: `responses-${message.parent_id}`,
        role: 'assistant',
        content: '',
        responses: [
          {
            model: message.model || 'assistant',
            content: message.content,
          }
        ],
      }
      compareByParent.set(message.parent_id, grouped)
      rendered.push(grouped)
      continue
    }

    rendered.push({
      id: message.id,
      role: 'assistant',
      content: message.content,
      model: message.model,
    })
  }
  return rendered
}
