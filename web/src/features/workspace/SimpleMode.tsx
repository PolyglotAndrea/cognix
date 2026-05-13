import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Send, Loader2 } from 'lucide-react'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'

interface SimpleModeProps {
  workspaceId: string
  onSwitchToAdvanced: () => void
}

export function SimpleMode({ workspaceId, onSwitchToAdvanced }: SimpleModeProps) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([])
  const [streaming, setStreaming] = useState(false)
  const queryClient = useQueryClient()

  const switchModeMutation = useMutation({
    mutationFn: () =>
      api.patch(`/workspaces/${workspaceId}/settings`, { ui_mode: 'advanced' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace-settings', workspaceId] })
      onSwitchToAdvanced()
    },
  })

  const handleSend = async () => {
    if (!input.trim() || streaming) return
    const userMsg = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }])

    // Get or create a chat
    let chatId: string
    try {
      const chats = await api.get(`/workspaces/${workspaceId}/chats`).then((r) => r.data)
      if (chats.length > 0) {
        chatId = chats[0].id
      } else {
        const created = await api
          .post(`/workspaces/${workspaceId}/chats`, { title: 'Simple Chat' })
          .then((r) => r.data)
        chatId = created.id
      }
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

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value, { stream: true })
        for (const line of text.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === 'delta' && event.delta) {
              assistantContent += event.delta
              setMessages((prev) => {
                const updated = [...prev]
                updated[updated.length - 1] = { role: 'assistant', content: assistantContent }
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
          onClick={() => switchModeMutation.mutate()}
          className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
        >
          <Settings className="h-3.5 w-3.5" />
          Switch to Advanced
        </button>
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
              {msg.content || (streaming && i === messages.length - 1 ? '...' : '')}
            </div>
          </div>
        ))}
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
