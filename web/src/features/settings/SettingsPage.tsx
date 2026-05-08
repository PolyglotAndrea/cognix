import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Check, Copy, Key, Plus, RadioTower, Trash2, type LucideIcon } from 'lucide-react'
import { api, authApi } from '@/shared/api/client'
import { Badge, Button, Input, Spinner } from '@/shared/ui'

interface WorkspaceInfo {
  id: string
  name: string
}

interface AgentInfo {
  id: string
  name: string
  model: string
}

interface RemoteBot {
  id: string
  name: string
  provider: string
  workspace_id: string
  agent_id: string
  enabled: boolean
  webhook_path: string
}

const PROVIDERS = ['lark', 'feishu', 'dingtalk', 'wechat']

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [keyName, setKeyName] = useState('')
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [botName, setBotName] = useState('')
  const [botProvider, setBotProvider] = useState('lark')
  const [botSecret, setBotSecret] = useState('')
  const [selectedAgentId, setSelectedAgentId] = useState('')

  const { data: apiKeys = [], isLoading: keysLoading } = useQuery({
    queryKey: ['api-keys'],
    queryFn: () => authApi.get('/api-keys').then((r) => r.data),
  })

  const { data: workspaces = [] } = useQuery<WorkspaceInfo[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get('/workspaces').then((r) => r.data),
  })
  const workspace = workspaces[0]

  const { data: agents = [] } = useQuery<AgentInfo[]>({
    queryKey: ['agents'],
    queryFn: () => api.get('/agents').then((r) => r.data),
  })

  const { data: bots = [], isLoading: botsLoading } = useQuery<RemoteBot[]>({
    queryKey: ['remote-bots'],
    queryFn: () => api.get('/bots').then((r) => r.data),
  })

  const createKeyMutation = useMutation({
    mutationFn: (name: string) => authApi.post('/api-keys', { name }),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      setKeyName('')
      if (response.data.key) {
        navigator.clipboard.writeText(response.data.key)
        setCopiedKey(response.data.id)
        window.setTimeout(() => setCopiedKey(null), 3000)
      }
    },
  })

  const deleteKeyMutation = useMutation({
    mutationFn: (id: string) => authApi.delete(`/api-keys/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['api-keys'] }),
  })

  const createBotMutation = useMutation({
    mutationFn: () =>
      api.post('/bots', {
        name: botName.trim(),
        provider: botProvider,
        workspace_id: workspace?.id,
        agent_id: selectedAgentId || agents[0]?.id,
        secret: botSecret,
        enabled: true,
      }),
    onSuccess: () => {
      setBotName('')
      setBotSecret('')
      queryClient.invalidateQueries({ queryKey: ['remote-bots'] })
    },
  })

  const deleteBotMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/bots/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['remote-bots'] }),
  })

  const copyText = (id: string, value: string) => {
    navigator.clipboard.writeText(value)
    setCopiedKey(id)
    window.setTimeout(() => setCopiedKey(null), 2000)
  }

  return (
    <div className="space-y-8">
      <div>
        <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-primary">
          <RadioTower className="h-4 w-4" />
          Runtime Access
        </div>
        <h2 className="text-3xl font-bold tracking-tight text-foreground">Settings</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          Manage programmatic access and remote robot bridges into local Agent workflows.
        </p>
      </div>

      <section className="rounded-2xl border border-border bg-card">
        <SectionHeader icon={Key} title="API Keys" subtitle="JWT-backed programmatic access" />
        <div className="border-b border-border p-5">
          <div className="flex flex-col gap-3 md:flex-row">
            <Input
              placeholder="Key name, e.g. CI/CD or Script"
              value={keyName}
              onChange={(event) => setKeyName(event.target.value)}
            />
            <Button
              disabled={!keyName.trim() || createKeyMutation.isPending}
              onClick={() => createKeyMutation.mutate(keyName)}
            >
              <Plus className="h-4 w-4" />
              Create Key
            </Button>
          </div>
        </div>

        {createKeyMutation.data?.data?.key && (
          <div className="border-b border-border bg-emerald-500/5 p-5">
            <p className="mb-3 text-sm font-bold text-emerald-600 dark:text-emerald-400">
              API key created. It is shown once.
            </p>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 rounded-xl border border-border bg-background px-3 py-2 font-mono text-xs text-foreground">
                {createKeyMutation.data.data.key}
              </code>
              <IconCopyButton
                active={copiedKey === createKeyMutation.data.data.id}
                onClick={() => copyText(createKeyMutation.data!.data.id, createKeyMutation.data!.data.key)}
              />
            </div>
          </div>
        )}

        <div className="divide-y divide-border">
          {keysLoading ? (
            <LoadingRow />
          ) : apiKeys.length === 0 ? (
            <EmptyRow icon={Key} text="No API keys yet" />
          ) : (
            apiKeys.map((key: any) => (
              <div key={key.id} className="flex items-center justify-between gap-4 px-5 py-4">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-muted">
                    <Key className="h-4 w-4 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-foreground">{key.name}</p>
                    <p className="font-mono text-xs text-muted-foreground">{key.prefix}</p>
                  </div>
                </div>
                <button
                  onClick={() => deleteKeyMutation.mutate(key.id)}
                  className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-rose-500/10 hover:text-rose-500"
                  aria-label={`Delete ${key.name}`}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card">
        <SectionHeader icon={Bot} title="Remote Bots" subtitle="Lark, Feishu, DingTalk and WeChat bridge entries" />
        <div className="grid grid-cols-1 gap-3 border-b border-border p-5 lg:grid-cols-[1fr_150px_1fr_1fr_auto]">
          <Input placeholder="Bot name" value={botName} onChange={(event) => setBotName(event.target.value)} />
          <select
            value={botProvider}
            onChange={(event) => setBotProvider(event.target.value)}
            className="rounded-xl border border-border bg-muted px-4 py-2 text-sm text-foreground outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/20"
          >
            {PROVIDERS.map((provider) => (
              <option key={provider} value={provider}>{provider}</option>
            ))}
          </select>
          <select
            value={selectedAgentId}
            onChange={(event) => setSelectedAgentId(event.target.value)}
            className="rounded-xl border border-border bg-muted px-4 py-2 text-sm text-foreground outline-none focus:border-primary/40 focus:ring-2 focus:ring-primary/20"
          >
            <option value="">Select agent</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>{agent.name}</option>
            ))}
          </select>
          <Input
            placeholder="Webhook secret"
            type="password"
            value={botSecret}
            onChange={(event) => setBotSecret(event.target.value)}
          />
          <Button
            disabled={!workspace || !botName.trim() || !botSecret || !(selectedAgentId || agents[0]?.id)}
            onClick={() => createBotMutation.mutate()}
          >
            Add
          </Button>
        </div>

        <div className="divide-y divide-border">
          {botsLoading ? (
            <LoadingRow />
          ) : bots.length === 0 ? (
            <EmptyRow icon={Bot} text="No remote bot bridges configured" />
          ) : (
            bots.map((bot) => {
              const webhook = `${window.location.origin}${bot.webhook_path}?secret=YOUR_SECRET`
              return (
                <div key={bot.id} className="px-5 py-4">
                  <div className="mb-3 flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-bold text-foreground">{bot.name}</p>
                        <Badge variant={bot.enabled ? 'success' : 'default'}>{bot.provider}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">Agent: {bot.agent_id}</p>
                    </div>
                    <button
                      onClick={() => deleteBotMutation.mutate(bot.id)}
                      className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-rose-500/10 hover:text-rose-500"
                      aria-label={`Delete ${bot.name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="flex items-center gap-2 rounded-xl border border-border bg-muted/50 p-2">
                    <code className="min-w-0 flex-1 truncate px-2 font-mono text-xs text-muted-foreground">
                      {webhook}
                    </code>
                    <IconCopyButton active={copiedKey === bot.id} onClick={() => copyText(bot.id, webhook)} />
                  </div>
                </div>
              )
            })
          )}
        </div>
      </section>
    </div>
  )
}

function SectionHeader({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: LucideIcon
  title: string
  subtitle: string
}) {
  return (
    <div className="flex items-center gap-3 border-b border-border px-5 py-4">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <div>
        <h3 className="text-sm font-bold text-foreground">{title}</h3>
        <p className="text-[11px] text-muted-foreground">{subtitle}</p>
      </div>
    </div>
  )
}

function IconCopyButton({ active, onClick }: { active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-background hover:text-primary"
      aria-label="Copy"
    >
      {active ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
    </button>
  )
}

function LoadingRow() {
  return (
    <div className="flex items-center justify-center py-12">
      <Spinner />
    </div>
  )
}

function EmptyRow({ icon: Icon, text }: { icon: LucideIcon; text: string }) {
  return (
    <div className="py-12 text-center">
      <Icon className="mx-auto mb-3 h-8 w-8 text-muted-foreground/30" />
      <p className="text-sm font-medium text-muted-foreground">{text}</p>
    </div>
  )
}
