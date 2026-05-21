import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CalendarClock,
  Check,
  Cpu,
  FileText,
  Globe2,
  History,
  Link2,
  ListChecks,
  MemoryStick,
  MessageSquarePlus,
  Plus,
  Search,
  Trash2,
  Wrench,
  Zap,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { useWorkspaceStore, type NotebookSource } from './store'

const EMPTY_FILES: WorkspaceFile[] = []
const EMPTY_TASKS: ScheduledTaskSource[] = []
const EMPTY_CHATS: ChatSession[] = []
const EMPTY_SKILLS: WorkspaceSkill[] = []
const EMPTY_MCP_SERVERS: MCPServer[] = []

interface WorkspaceSkill {
  name: string
  description?: string
  enabled: boolean
  author?: string
  version?: string
  displayName?: string
}

interface MCPServer {
  id: string
  name: string
  command: string
  args: string[]
  env: Record<string, string>
  enabled: boolean
  metadata?: Record<string, any>
}


interface WorkspaceFile {
  name: string
  path: string
  is_dir: boolean
  size?: number
  modified_at?: string
}

interface ScheduledTaskSource {
  id: string
  name: string
  workspace_id?: string
  task_type: string
  schedule: string
  state: string
  run_count?: number
}

interface ChatSession {
  id: string
  title: string
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

interface SourceItem {
  id: string
  kind: 'file' | 'url' | 'artifact' | 'memory'
  title: string
  subtitle: string
  selected: boolean
}

export function SourcesPanel({ workspaceId }: { workspaceId: string }) {
  const setNotebookSources = useWorkspaceStore((state) => state.setNotebookSources)
  const activeNotebookChatId = useWorkspaceStore((state) => state.activeNotebookChatId)
  const setActiveNotebookChatId = useWorkspaceStore((state) => state.setActiveNotebookChatId)
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'chats' | 'tasks' | 'sources' | 'skills' | 'mcp'>('chats')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const [urlSources, setUrlSources] = useState<SourceItem[]>([])
  const [urlInput, setUrlInput] = useState('')

  const [showAddMcp, setShowAddMcp] = useState(false)
  const [mcpForm, setMcpForm] = useState({ name: '', command: '', args: '', env: '' })
  const [mcpSubmitting, setMcpSubmitting] = useState(false)

  const { data: skills = EMPTY_SKILLS } = useQuery<WorkspaceSkill[]>({
    queryKey: ['workspace-skills', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/skills`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const { data: mcpServers = EMPTY_MCP_SERVERS } = useQuery<MCPServer[]>({
    queryKey: ['workspace-mcp', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/mcp/servers`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const { data: files = EMPTY_FILES } = useQuery<WorkspaceFile[]>({
    queryKey: ['workspace-files', workspaceId, 'notebook-sources'],
    queryFn: () => api.get(`/workspaces/${workspaceId}/files`, { params: { path: '' } }).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const { data: tasks = EMPTY_TASKS } = useQuery<ScheduledTaskSource[]>({
    queryKey: ['tasks', workspaceId, 'notebook-tasks'],
    queryFn: () => api.get('/tasks', { params: { workspace_id: workspaceId } }).then((r) => r.data),
    enabled: !!workspaceId,
    select: (rows) =>
      rows.filter(
        (task) =>
          task.schedule !== 'once' &&
          ['active', 'paused'].includes(String(task.state || '').toLowerCase()),
      ),
  })

  const { data: chats = EMPTY_CHATS, isLoading: chatsLoading } = useQuery<ChatSession[]>({
    queryKey: ['workspace-chats', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/chats`).then((r) => r.data),
    enabled: !!workspaceId,
    select: (rows) => rows.filter((chat) => chat.metadata?.mode === 'simple'),
  })

  const sources = useMemo<SourceItem[]>(() => {
    const fileSources = files
      .filter((file) => !file.is_dir)
      .map((file) => ({
        id: `file:${file.path}`,
        kind: 'file' as const,
        title: file.name,
        subtitle: file.path,
        selected: selected[`file:${file.path}`] ?? true,
      }))
    const memorySource: SourceItem = {
      id: 'memory:workspace',
      kind: 'memory',
      title: 'Workspace memory',
      subtitle: 'Hot, cold, procedural, and approved long-term context',
      selected: selected['memory:workspace'] ?? true,
    }
    return [memorySource, ...urlSources, ...fileSources]
  }, [files, selected, urlSources])

  const taskItems = useMemo(() => {
    const scheduledItems = tasks.slice(0, 10).map((task) => ({
      id: `task:${task.id}`,
      kind: 'task' as const,
      title: task.name || task.id,
      subtitle: `${task.task_type} · ${task.schedule}`,
      status: task.state,
      runCount: task.run_count || 0,
    }))
    return scheduledItems
  }, [tasks])

  const filtered = search.trim()
    ? sources.filter((source) =>
        `${source.title} ${source.subtitle}`.toLowerCase().includes(search.toLowerCase()),
      )
    : sources

  const selectedCount = sources.filter((source) => source.selected).length
  const taskCount = taskItems.length
  const chatCount = chats.length

  useEffect(() => {
    if (!workspaceId) return
    if (activeNotebookChatId && chats.some((chat) => chat.id === activeNotebookChatId)) return
    setActiveNotebookChatId(chats[0]?.id || null)
  }, [activeNotebookChatId, chats, setActiveNotebookChatId, workspaceId])

  useEffect(() => {
    const activeSources: NotebookSource[] = sources
      .filter((source) => source.selected)
      .map((source) => ({
        id: source.id,
        kind: source.kind,
        title: source.title,
        subtitle: source.subtitle,
      }))
    const currentSources = useWorkspaceStore.getState().notebookSources
    if (sameNotebookSources(currentSources, activeSources)) return
    setNotebookSources(activeSources)
  }, [setNotebookSources, sources])

  const addUrl = () => {
    const value = urlInput.trim()
    if (!value) return
    const item: SourceItem = {
      id: `url:${value}`,
      kind: 'url',
      title: value.replace(/^https?:\/\//, ''),
      subtitle: 'Web source for planning and browser automation',
      selected: true,
    }
    setUrlSources((current) => [item, ...current.filter((source) => source.id !== item.id)])
    setSelected((current) => ({ ...current, [item.id]: true }))
    setUrlInput('')
  }

  const createChat = async () => {
    const created = await api
      .post(`/workspaces/${workspaceId}/chats`, {
        title: 'New Chat',
        metadata: { mode: 'simple' },
      })
      .then((r) => r.data as ChatSession)
    setActiveNotebookChatId(created.id)
    await queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
  }

  const deleteChat = async (chatId: string) => {
    if (!window.confirm('Are you sure you want to delete this chat?')) return
    try {
      await api.delete(`/workspaces/${workspaceId}/chats/${chatId}`)
      await queryClient.invalidateQueries({ queryKey: ['workspace-chats', workspaceId] })
      if (activeNotebookChatId === chatId) {
        const remaining = chats.filter((c) => c.id !== chatId)
        setActiveNotebookChatId(remaining[0]?.id || null)
      }
    } catch (error) {
      console.error('Failed to delete chat:', error)
      alert('Failed to delete chat')
    }
  }

  const toggleSkill = async (skillName: string, currentEnabled: boolean) => {
    try {
      await api.put(`/workspaces/${workspaceId}/skills/${skillName}`, { enabled: !currentEnabled })
      await queryClient.invalidateQueries({ queryKey: ['workspace-skills', workspaceId] })
    } catch (error) {
      console.error('Failed to toggle skill:', error)
      alert('Failed to toggle skill')
    }
  }

  const toggleMcpServer = async (server: MCPServer) => {
    try {
      await api.post(`/workspaces/${workspaceId}/mcp/servers`, {
        id: server.id,
        name: server.name,
        command: server.command,
        args: server.args,
        env: server.env,
        enabled: !server.enabled,
        metadata: server.metadata || {},
      })
      await queryClient.invalidateQueries({ queryKey: ['workspace-mcp', workspaceId] })
    } catch (error) {
      console.error('Failed to toggle MCP server:', error)
      alert('Failed to toggle MCP server')
    }
  }

  const deleteMcpServer = async (serverId: string) => {
    if (!window.confirm('Are you sure you want to delete this MCP server?')) return
    try {
      await api.delete(`/workspaces/${workspaceId}/mcp/servers/${serverId}`)
      await queryClient.invalidateQueries({ queryKey: ['workspace-mcp', workspaceId] })
    } catch (error) {
      console.error('Failed to delete MCP server:', error)
      alert('Failed to delete MCP server')
    }
  }

  const addMcpServer = async () => {
    try {
      setMcpSubmitting(true)
      let envObj: Record<string, string> = {}
      if (mcpForm.env.trim()) {
        try {
          envObj = JSON.parse(mcpForm.env)
        } catch {
          alert('Invalid Env JSON format')
          setMcpSubmitting(false)
          return
        }
      }
      await api.post(`/workspaces/${workspaceId}/mcp/servers`, {
        name: mcpForm.name.trim(),
        command: mcpForm.command.trim(),
        args: mcpForm.args.split(',').map(a => a.trim()).filter(Boolean),
        env: envObj,
        enabled: true,
      })
      await queryClient.invalidateQueries({ queryKey: ['workspace-mcp', workspaceId] })
      setMcpForm({ name: '', command: '', args: '', env: '' })
      setShowAddMcp(false)
    } catch (error) {
      console.error('Failed to add MCP server:', error)
      alert('Failed to register MCP server')
    } finally {
      setMcpSubmitting(false)
    }
  }


  return (
    <aside className="flex h-full flex-col overflow-hidden rounded-[1.35rem] border border-border/70 bg-card shadow-sm">
      <div className="border-b border-border/70 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">
              {activeTab === 'chats'
                ? 'Chat Sessions'
                : activeTab === 'tasks'
                ? 'Tasks'
                : activeTab === 'sources'
                ? 'Sources'
                : activeTab === 'skills'
                ? 'Skills'
                : 'MCP Servers'}
            </h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {activeTab === 'chats'
                ? `${chatCount} conversations in this workspace`
                : activeTab === 'tasks'
                ? `${taskCount} plans and tasks`
                : activeTab === 'sources'
                ? `${selectedCount} selected for context`
                : activeTab === 'skills'
                ? `${skills.length} skills available`
                : `${mcpServers.length} MCP integrations`}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (activeTab === 'chats') void createChat()
              if (activeTab === 'sources') setActiveTab('sources')
              if (activeTab === 'mcp') setShowAddMcp((prev) => !prev)
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-background text-muted-foreground hover:text-foreground"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="border-b border-border/70 p-2">
        <div className="grid grid-cols-5 gap-0.5 rounded-2xl border border-border bg-background/75 p-1">
          <button
            type="button"
            onClick={() => setActiveTab('chats')}
            className={cn(
              'flex flex-col sm:flex-row h-9 items-center justify-center gap-1 rounded-xl text-[9px] font-black uppercase tracking-wider transition-colors',
              activeTab === 'chats'
                ? 'bg-foreground text-background shadow-sm'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground',
            )}
            title="Chat History"
          >
            <History className="h-3 w-3 shrink-0" />
            <span className="hidden min-[300px]:inline">Chats</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('tasks')}
            className={cn(
              'flex flex-col sm:flex-row h-9 items-center justify-center gap-1 rounded-xl text-[9px] font-black uppercase tracking-wider transition-colors',
              activeTab === 'tasks'
                ? 'bg-foreground text-background shadow-sm'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground',
            )}
            title="Tasks"
          >
            <ListChecks className="h-3 w-3 shrink-0" />
            <span className="hidden min-[300px]:inline">Tasks</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('sources')}
            className={cn(
              'flex flex-col sm:flex-row h-9 items-center justify-center gap-1 rounded-xl text-[9px] font-black uppercase tracking-wider transition-colors',
              activeTab === 'sources'
                ? 'bg-foreground text-background shadow-sm'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground',
            )}
            title="Sources"
          >
            <FileText className="h-3 w-3 shrink-0" />
            <span className="hidden min-[300px]:inline">Sources</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('skills')}
            className={cn(
              'flex flex-col sm:flex-row h-9 items-center justify-center gap-1 rounded-xl text-[9px] font-black uppercase tracking-wider transition-colors',
              activeTab === 'skills'
                ? 'bg-foreground text-background shadow-sm'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground',
            )}
            title="Skills"
          >
            <Zap className="h-3 w-3 shrink-0" />
            <span className="hidden min-[300px]:inline">Skills</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('mcp')}
            className={cn(
              'flex flex-col sm:flex-row h-9 items-center justify-center gap-1 rounded-xl text-[9px] font-black uppercase tracking-wider transition-colors',
              activeTab === 'mcp'
                ? 'bg-foreground text-background shadow-sm'
                : 'text-muted-foreground hover:bg-muted/70 hover:text-foreground',
            )}
            title="MCP Servers"
          >
            <Cpu className="h-3 w-3 shrink-0" />
            <span className="hidden min-[300px]:inline">MCP</span>
          </button>
        </div>
      </div>


      {activeTab === 'chats' && (
        <div className="border-b border-border/70 p-4">
          <button
            type="button"
            onClick={() => void createChat()}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-2xl border border-border bg-background text-xs font-black text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
          >
            <MessageSquarePlus className="h-4 w-4" />
            New Session
          </button>
        </div>
      )}

      {activeTab === 'sources' && (
      <div className="space-y-3 border-b border-border/70 p-4">
        <div className="rounded-2xl border border-border bg-background/80 p-2">
          <div className="flex items-center gap-2">
            <Globe2 className="h-4 w-4 text-muted-foreground" />
            <input
              value={urlInput}
              onChange={(event) => setUrlInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') addUrl()
              }}
              placeholder="Add URL as source"
              className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground/60"
            />
            <button
              type="button"
              onClick={addUrl}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-foreground text-background hover:opacity-90"
            >
              <Link2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search sources"
            className="h-9 w-full rounded-full border border-border bg-background pl-9 pr-3 text-xs outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/15"
          />
        </div>
      </div>
      )}

      <div className="flex-1 space-y-1 overflow-y-auto p-3 scrollbar-hide">
        {activeTab === 'chats' ? (
          chats.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border p-6 text-center">
              <History className="mx-auto mb-2 h-6 w-6 text-muted-foreground/30" />
              <p className="text-xs font-semibold text-muted-foreground">
                {chatsLoading ? 'Loading chat history...' : 'No chat history yet'}
              </p>
            </div>
          ) : (
            chats.map((chat, index) => (
              <div
                key={chat.id}
                className={cn(
                  'group flex w-full items-center gap-3 rounded-2xl px-2.5 py-2.5 text-left transition-colors',
                  chat.id === activeNotebookChatId
                    ? 'bg-primary/10 text-primary ring-1 ring-primary/25'
                    : 'hover:bg-muted/55',
                )}
              >
                <button
                  type="button"
                  onClick={() => setActiveNotebookChatId(chat.id)}
                  className="flex flex-1 items-center gap-3 min-w-0 text-left"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/8 text-primary">
                    <History className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-semibold text-foreground">
                      {chat.title || `Conversation ${index + 1}`}
                    </div>
                    <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
                      {formatChatTimestamp(chat.updated_at || chat.created_at) || `Session ${chat.id.slice(0, 8)}`}
                    </div>
                  </div>
                </button>
                <div className="flex items-center gap-1.5 shrink-0">
                  {chat.id === activeNotebookChatId && (
                    <span className="flex h-5 w-5 items-center justify-center rounded-md bg-primary text-primary-foreground group-hover:hidden">
                      <Check className="h-3.5 w-3.5" />
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      void deleteChat(chat.id)
                    }}
                    className="hidden group-hover:flex h-5 w-5 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                    title="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))
          )
        ) : activeTab === 'tasks' ? (
          taskItems.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border p-6 text-center">
              <ListChecks className="mx-auto mb-2 h-6 w-6 text-muted-foreground/30" />
              <p className="text-xs font-semibold text-muted-foreground">No plans or tasks yet</p>
              <p className="mt-1 text-[10px] leading-4 text-muted-foreground/70">
                Completed plans stay in chat. Confirm “save as task” after a run to keep it here as a scheduled or long-running task.
              </p>
            </div>
          ) : (
            taskItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className="flex w-full items-center gap-3 rounded-2xl px-2.5 py-2.5 text-left transition-colors hover:bg-muted/55"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/8 text-primary">
                  <CalendarClock className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-2 text-xs font-semibold leading-4 text-foreground">
                    {item.title}
                  </div>
                  <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
                    {item.subtitle}
                    {'runCount' in item ? ` · ${item.runCount} runs` : ''}
                  </div>
                </div>
                <span className="shrink-0 rounded-full border border-border bg-background px-2 py-1 text-[9px] font-black uppercase tracking-widest text-muted-foreground">
                  {item.status}
                </span>
              </button>
            ))
          )
        ) : activeTab === 'skills' ? (
          skills.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border p-6 text-center">
              <Zap className="mx-auto mb-2 h-6 w-6 text-muted-foreground/30" />
              <p className="text-xs font-semibold text-muted-foreground">No skills installed</p>
            </div>
          ) : (
            skills.map((skill) => (
              <div
                key={skill.name}
                className="flex w-full items-start gap-3 rounded-2xl px-2.5 py-2.5 text-left border border-border/40 bg-card/50 transition-colors hover:bg-muted/30"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/8 text-primary mt-0.5">
                  <Wrench className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-xs font-semibold text-foreground">
                      {skill.displayName || skill.name}
                    </span>
                    {skill.version && (
                      <span className="text-[9px] font-medium text-muted-foreground bg-muted px-1 py-0.5 rounded">
                        v{skill.version}
                      </span>
                    )}
                  </div>
                  {skill.description && (
                    <p className="mt-1 text-[10px] text-muted-foreground leading-normal line-clamp-2">
                      {skill.description}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => void toggleSkill(skill.name, skill.enabled)}
                  className={cn(
                    'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none mt-1',
                    skill.enabled ? 'bg-primary' : 'bg-muted-foreground/25',
                  )}
                >
                  <span
                    className={cn(
                      'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow ring-0 transition duration-200 ease-in-out',
                      skill.enabled ? 'translate-x-4' : 'translate-x-0',
                    )}
                  />
                </button>
              </div>
            ))
          )
        ) : activeTab === 'mcp' ? (
          <div className="space-y-3">
            {showAddMcp && (
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  void addMcpServer()
                }}
                className="space-y-2.5 rounded-2xl border border-primary/25 bg-primary/[0.02] p-3 shadow-inner"
              >
                <div className="text-[10px] font-black uppercase tracking-widest text-primary">
                  Register MCP Server
                </div>
                <div className="space-y-1.5">
                  <input
                    required
                    placeholder="Server Name (e.g. filesystem)"
                    value={mcpForm.name}
                    onChange={(e) => setMcpForm({ ...mcpForm, name: e.target.value })}
                    className="h-8 w-full rounded-lg border border-border bg-background px-2 text-xs outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/15"
                  />
                  <input
                    required
                    placeholder="Command (e.g. node, python, npx)"
                    value={mcpForm.command}
                    onChange={(e) => setMcpForm({ ...mcpForm, command: e.target.value })}
                    className="h-8 w-full rounded-lg border border-border bg-background px-2 text-xs outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/15"
                  />
                  <input
                    placeholder="Args (comma separated, e.g. -y, @mcp/server)"
                    value={mcpForm.args}
                    onChange={(e) => setMcpForm({ ...mcpForm, args: e.target.value })}
                    className="h-8 w-full rounded-lg border border-border bg-background px-2 text-xs outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/15"
                  />
                  <input
                    placeholder="Env JSON (optional, e.g. {&quot;KEY&quot;:&quot;VAL&quot;})"
                    value={mcpForm.env}
                    onChange={(e) => setMcpForm({ ...mcpForm, env: e.target.value })}
                    className="h-8 w-full rounded-lg border border-border bg-background px-2 text-xs outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/15"
                  />
                </div>
                <div className="flex justify-end gap-1.5">
                  <button
                    type="button"
                    onClick={() => setShowAddMcp(false)}
                    className="rounded-lg border border-border bg-background px-2.5 py-1 text-[10px] font-bold text-muted-foreground hover:text-foreground"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={mcpSubmitting}
                    className="rounded-lg bg-foreground px-2.5 py-1 text-[10px] font-black text-background hover:opacity-90 disabled:opacity-40"
                  >
                    {mcpSubmitting ? 'Adding...' : 'Register'}
                  </button>
                </div>
              </form>
            )}

            {mcpServers.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-border p-6 text-center">
                <Cpu className="mx-auto mb-2 h-6 w-6 text-muted-foreground/30" />
                <p className="text-xs font-semibold text-muted-foreground">No MCP servers registered</p>
              </div>
            ) : (
              mcpServers.map((server) => (
                <div
                  key={server.id}
                  className="group/mcp flex w-full items-start gap-3 rounded-2xl px-2.5 py-2.5 text-left border border-border/40 bg-card/50 transition-colors hover:bg-muted/30"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/8 text-primary mt-0.5">
                    <Cpu className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-xs font-semibold text-foreground">
                        {server.name}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate font-mono text-[9px] text-muted-foreground">
                      {server.command} {server.args.join(' ')}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <button
                      type="button"
                      onClick={() => void deleteMcpServer(server.id)}
                      className="hidden group-hover/mcp:flex h-5 w-5 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                      title="Remove MCP Server"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => void toggleMcpServer(server)}
                      className={cn(
                        'relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none',
                        server.enabled ? 'bg-primary' : 'bg-muted-foreground/25',
                      )}
                    >
                      <span
                        className={cn(
                          'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-background shadow ring-0 transition duration-200 ease-in-out',
                          server.enabled ? 'translate-x-4' : 'translate-x-0',
                        )}
                      />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border p-6 text-center">
            <FileText className="mx-auto mb-2 h-6 w-6 text-muted-foreground/30" />
            <p className="text-xs font-semibold text-muted-foreground">No sources found</p>
          </div>
        ) : (
          filtered.map((source) => (
            <button
              key={source.id}
              type="button"
              onClick={() => setSelected((current) => ({ ...current, [source.id]: !source.selected }))}
              className="flex w-full items-center gap-3 rounded-2xl px-2.5 py-2.5 text-left transition-colors hover:bg-muted/55"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/8 text-primary">
                <SourceIcon kind={source.kind} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-foreground">{source.title}</div>
                <div className="mt-0.5 truncate text-[10px] text-muted-foreground">{source.subtitle}</div>
              </div>
              <span
                className={cn(
                  'flex h-5 w-5 shrink-0 items-center justify-center rounded-md border',
                  source.selected
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-muted text-transparent',
                )}
              >
                <Check className="h-3.5 w-3.5" />
              </span>
            </button>
          ))
        )}
      </div>
    </aside>
  )
}

function sameNotebookSources(a: NotebookSource[], b: NotebookSource[]) {
  if (a.length !== b.length) return false
  return a.every((source, index) => {
    const other = b[index]
    return (
      source.id === other.id &&
      source.kind === other.kind &&
      source.title === other.title &&
      source.subtitle === other.subtitle
    )
  })
}

function formatChatTimestamp(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function SourceIcon({ kind }: { kind: SourceItem['kind'] }) {
  if (kind === 'url') return <Globe2 className="h-4 w-4" />
  if (kind === 'memory') return <MemoryStick className="h-4 w-4" />
  return <FileText className="h-4 w-4" />
}
