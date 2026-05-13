import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  Brain,
  Check,
  Copy,
  Cpu,
  Eye,
  EyeOff,
  Key,
  Play,
  RadioTower,
  Search,
  Trash2,
  type LucideIcon,
  Wrench,
  Zap,
} from 'lucide-react'
import { api, authApi } from '@/shared/api/client'
import { Badge, Button, Input } from '@/shared/ui'

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
  metadata?: Record<string, unknown>
}

interface HotMemory {
  user: string
  global_memory: string
  workspace_memory: string
}

interface DeepMemory {
  content: string
  path: string
}

interface ColdMemory {
  id: string
  content: string
  summary: string
  kind: string
  scope: string
  created_at: string
}

const PROVIDERS = ['lark', 'feishu', 'dingtalk', 'wechat']

const SETTINGS_SECTIONS = [
  { id: 'memory', label: 'Memory Studio', icon: Brain, description: 'Knowledge & Context' },
  { id: 'llm', label: 'Model Providers', icon: Cpu, description: 'LLM Configuration' },
  { id: 'api', label: 'API Access', icon: Key, description: 'Keys & Authorization' },
  { id: 'bots', label: 'Integrations', icon: Bot, description: 'Remote Bridges' },
] as const

type SectionId = typeof SETTINGS_SECTIONS[number]['id']

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [activeSection, setActiveSection] = useState<SectionId>('memory')
  
  // State for Memory
  const [keyName, setKeyName] = useState('')
  const [copiedKey, setCopiedKey] = useState<string | null>(null)
  const [botName, setBotName] = useState('')
  const [botProvider, setBotProvider] = useState('lark')
  const [botSecret, setBotSecret] = useState('')
  const [botResponseUrl, setBotResponseUrl] = useState('')
  const [botRequireSignature, setBotRequireSignature] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [hotDraft, setHotDraft] = useState<HotMemory | null>(null)
  const [deepDraft, setDeepDraft] = useState<string | null>(null)
  const [memoryContent, setMemoryContent] = useState('')
  const [memorySummary, setMemorySummary] = useState('')
  const [memorySearch, setMemorySearch] = useState('')

  // State for LLM
  const [llmBaseUrl, setLlmBaseUrl] = useState('')
  const [llmApiKey, setLlmApiKey] = useState('')
  const [llmDefaultModel, setLlmDefaultModel] = useState('')
  const [llmInitialized, setLlmInitialized] = useState(false)
  const [llmKeyDirty, setLlmKeyDirty] = useState(false)
  const [showApiKey, setShowApiKey] = useState(false)
  const [testModel, setTestModel] = useState('')
  const [testResult, setTestResult] = useState<{ ok: boolean; latency_ms?: number; error?: string } | null>(null)
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([])

  const { data: apiKeys = [] } = useQuery({
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

  const { data: bots = [] } = useQuery<RemoteBot[]>({
    queryKey: ['remote-bots'],
    queryFn: () => api.get('/bots').then((r) => r.data),
  })

  const { data: hotMemory } = useQuery<HotMemory>({
    queryKey: ['hot-memory', workspace?.id],
    queryFn: () =>
      api.get('/memory/hot', { params: { workspace_id: workspace?.id } }).then((r) => r.data),
    enabled: !!workspace,
  })

  const { data: deepMemory } = useQuery<DeepMemory>({
    queryKey: ['deep-memory'],
    queryFn: () => api.get('/memory/deep').then((r) => r.data),
  })

  const { data: memoryResults = [], refetch: refetchMemory } = useQuery<ColdMemory[]>({
    queryKey: ['memory-search', workspace?.id, memorySearch],
    queryFn: () =>
      api
        .post('/memory/search', {
          query: memorySearch || 'conversation',
          workspace_id: workspace?.id,
          limit: 8,
        })
        .then((r) => r.data),
    enabled: !!workspace,
  })

  // LLM settings query
  const { data: llmConfig } = useQuery<{
    base_url?: string
    api_key?: string
    default_model?: string
  }>({
    queryKey: ['settings', 'llm'],
    queryFn: () => api.get('/settings/llm').then((r) => r.data),
  })

  if (llmConfig && !llmInitialized) {
    setLlmBaseUrl(llmConfig.base_url || '')
    setLlmApiKey(llmConfig.api_key || '')
    setLlmDefaultModel(llmConfig.default_model || 'gpt-4o')
    setLlmInitialized(true)
  }

  const saveLlmMutation = useMutation({
    mutationFn: () =>
      api.patch('/settings/llm', {
        base_url: llmBaseUrl.trim() || null,
        api_key: llmKeyDirty ? (llmApiKey.trim() || null) : undefined,
        default_model: llmDefaultModel.trim() || 'gpt-4o',
      }),
    onSuccess: () => {
      setLlmKeyDirty(false)
      queryClient.invalidateQueries({ queryKey: ['settings', 'llm'] })
    },
  })

  const testLlmMutation = useMutation({
    mutationFn: () =>
      api.post('/settings/llm/test', {
        model: testModel || llmDefaultModel || undefined,
      }),
    onSuccess: (response) => setTestResult(response.data),
    onError: () => setTestResult({ ok: false, error: 'Request failed' }),
  })

  const discoverModelsMutation = useMutation({
    mutationFn: () => api.post('/settings/llm/models', {}),
    onSuccess: (response) => setDiscoveredModels(response.data.models || []),
  })

  // Workspace-scoped LLM overrides
  const [wsLlmBaseUrl, setWsLlmBaseUrl] = useState('')
  const [wsLlmApiKey, setWsLlmApiKey] = useState('')
  const [wsLlmDefaultModel, setWsLlmDefaultModel] = useState('')
  const [wsLlmInitialized, setWsLlmInitialized] = useState(false)
  const [wsLlmKeyDirty, setWsLlmKeyDirty] = useState(false)
  const [showWsApiKey, setShowWsApiKey] = useState(false)

  const { data: workspaceSettings } = useQuery<{
    llm?: { base_url?: string | null; api_key?: string | null; default_model?: string | null }
    [key: string]: unknown
  }>({
    queryKey: ['workspace-settings', workspace?.id],
    queryFn: () => api.get(`/workspaces/${workspace!.id}/settings`).then((r) => r.data),
    enabled: !!workspace,
  })

  if (workspaceSettings?.llm && !wsLlmInitialized) {
    setWsLlmBaseUrl(workspaceSettings.llm.base_url || '')
    setWsLlmApiKey(workspaceSettings.llm.api_key || '')
    setWsLlmDefaultModel(workspaceSettings.llm.default_model || '')
    setWsLlmInitialized(true)
  }

  const saveWsLlmMutation = useMutation({
    mutationFn: () =>
      api.patch(`/workspaces/${workspace!.id}/settings`, {
        llm: {
          base_url: wsLlmBaseUrl.trim() || null,
          api_key: wsLlmKeyDirty ? (wsLlmApiKey.trim() || null) : undefined,
          default_model: wsLlmDefaultModel.trim() || null,
        },
      }),
    onSuccess: () => {
      setWsLlmKeyDirty(false)
      queryClient.invalidateQueries({ queryKey: ['workspace-settings', workspace?.id] })
    },
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
        metadata: {
          ...(botResponseUrl.trim() ? { response_url: botResponseUrl.trim() } : {}),
          require_signature: botRequireSignature,
        },
      }),
    onSuccess: () => {
      setBotName('')
      setBotSecret('')
      setBotResponseUrl('')
      setBotRequireSignature(false)
      queryClient.invalidateQueries({ queryKey: ['remote-bots'] })
    },
  })

  const deleteBotMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/bots/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['remote-bots'] }),
  })

  const saveHotMemoryMutation = useMutation({
    mutationFn: () =>
      api.patch('/memory/hot', hotDraft || hotMemory, { params: { workspace_id: workspace?.id } }),
    onSuccess: (response) => {
      setHotDraft(response.data)
      queryClient.invalidateQueries({ queryKey: ['hot-memory', workspace?.id] })
    },
  })

  const saveDeepMemoryMutation = useMutation({
    mutationFn: () =>
      api.patch('/memory/deep', {
        content: deepDraft ?? deepMemory?.content ?? '',
      }),
    onSuccess: (response) => {
      setDeepDraft(response.data.content)
      queryClient.invalidateQueries({ queryKey: ['deep-memory'] })
    },
  })

  const rememberMutation = useMutation({
    mutationFn: () =>
      api.post('/memory/remember', {
        content: memoryContent,
        summary: memorySummary,
        workspace_id: workspace?.id,
        scope: workspace?.id ? 'workspace' : 'global',
        kind: 'manual',
      }),
    onSuccess: () => {
      setMemoryContent('')
      setMemorySummary('')
      refetchMemory()
    },
  })


  const copyText = (id: string, value: string) => {
    navigator.clipboard.writeText(value)
    setCopiedKey(id)
    window.setTimeout(() => setCopiedKey(null), 2000)
  }

  const activeHot = hotDraft || hotMemory || {
    user: '',
    global_memory: '',
    workspace_memory: '',
  }
  const activeDeep = deepDraft ?? deepMemory?.content ?? ''

  return (
    <div className="flex h-[640px] -m-6 bg-background rounded-2xl overflow-hidden">
      {/* Sidebar Navigation */}
      <aside className="w-64 border-r border-border bg-muted/30 flex flex-col p-4 gap-2 shrink-0">
        <div className="px-3 py-2 mb-2">
          <h2 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/40">Configuration</h2>
        </div>
        {SETTINGS_SECTIONS.map((section) => (
          <button
            key={section.id}
            onClick={() => setActiveSection(section.id)}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 group ${
              activeSection === section.id
                ? 'bg-primary text-white shadow-lg shadow-primary/20 scale-[1.02]'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
          >
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-colors ${
              activeSection === section.id ? 'bg-white/20' : 'bg-primary/10 group-hover:bg-primary/20'
            }`}>
               <section.icon className={`h-4 w-4 ${activeSection === section.id ? 'text-white' : 'text-primary'}`} />
            </div>
            <div className="text-left flex-1">
              <div className="text-sm font-bold tracking-tight">{section.label}</div>
              <div className={`text-[10px] font-medium opacity-60 ${activeSection === section.id ? 'text-white' : ''}`}>
                {section.description}
              </div>
            </div>
          </button>
        ))}
        
        <div className="mt-auto p-4 rounded-2xl bg-gradient-to-br from-primary/10 to-indigo-500/10 border border-primary/10">
          <div className="flex items-center gap-2 mb-2">
            <RadioTower className="h-3.5 w-3.5 text-primary" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-primary">Runtime v0.8</span>
          </div>
          <p className="text-[10px] leading-relaxed text-muted-foreground font-medium">
            Dynamic context injection and remote messaging bridges are operational.
          </p>
        </div>
      </aside>

      {/* Content Area */}
      <main className="flex-1 overflow-y-auto p-8 scrollbar-hide">
        {activeSection === 'memory' && (
          <div className="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
             <div>
                <h3 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
                   Memory Studio
                   <Badge variant="info" className="text-[9px] uppercase tracking-widest">Active</Badge>
                </h3>
                <p className="text-sm text-muted-foreground mt-1">Configure runtime context and durable knowledge stores for your agents.</p>
             </div>

             <div className="grid grid-cols-1 gap-6">
               <div className="grid grid-cols-3 gap-4">
                 <MemoryEditor label="USER.md" value={activeHot.user} onChange={(v) => setHotDraft({ ...activeHot, user: v })} />
                 <MemoryEditor label="Global MEMORY.md" value={activeHot.global_memory} onChange={(v) => setHotDraft({ ...activeHot, global_memory: v })} />
                 <MemoryEditor label="Workspace MEMORY.md" value={activeHot.workspace_memory} onChange={(v) => setHotDraft({ ...activeHot, workspace_memory: v })} />
               </div>
               <div className="flex items-center gap-3">
                 <Button
                    className="h-10 px-6 shadow-lg shadow-primary/20"
                    disabled={!hotDraft || saveHotMemoryMutation.isPending}
                    onClick={() => saveHotMemoryMutation.mutate()}
                 >
                   {saveHotMemoryMutation.isPending ? 'Synchronizing...' : 'Update Context Memory'}
                 </Button>
                 <Button
                    variant="secondary"
                    className="h-10 px-6"
                    disabled={saveDeepMemoryMutation.isPending}
                    onClick={() => saveDeepMemoryMutation.mutate()}
                 >
                   Save Deep Memory
                 </Button>
               </div>
               <MemoryEditor
                 label="Deep User Model"
                 value={activeDeep}
                 onChange={setDeepDraft}
               />
             </div>

             <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-sm">
               <div className="p-5 border-b border-border bg-muted/20 flex items-center justify-between">
                 <div>
                    <h4 className="text-sm font-bold text-foreground">Durable Knowledge recall</h4>
                    <p className="text-[11px] text-muted-foreground mt-0.5 uppercase tracking-wider font-bold">Vector Database Search</p>
                 </div>
                 <div className="flex items-center gap-2">
                    <Input placeholder="Search keywords..." value={memorySearch} onChange={(e) => setMemorySearch(e.target.value)} className="w-64 h-9 bg-background" />
                    <Button variant="secondary" onClick={() => refetchMemory()} className="h-9 w-9 p-0"><Search className="h-4 w-4" /></Button>
                 </div>
               </div>
               <div className="p-5 grid grid-cols-2 gap-8">
                  <div className="space-y-4">
                     <textarea
                        value={memoryContent}
                        onChange={(e) => setMemoryContent(e.target.value)}
                        placeholder="Manually record a key insight or decision..."
                        className="w-full h-32 resize-none rounded-xl border border-border bg-muted/30 p-4 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all scrollbar-hide leading-relaxed"
                     />
                     <Button className="w-full h-10" disabled={!memoryContent.trim()} onClick={() => rememberMutation.mutate()}>Store In Cold Memory</Button>
                  </div>
                  <div className="space-y-4">
                     <div className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60">Recalled Entries</div>
                     <div className="max-h-[200px] overflow-y-auto space-y-3 pr-2 scrollbar-hide">
                        {memoryResults.length === 0 ? (
                           <div className="py-10 text-center border border-dashed border-border rounded-xl">
                              <Brain className="h-6 w-6 text-muted-foreground/20 mx-auto mb-2" />
                              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">No results</p>
                           </div>
                        ) : (
                           memoryResults.map(m => (
                             <div key={m.id} className="p-3 rounded-xl border border-border bg-muted/10 text-[11px] text-foreground/80 leading-relaxed group hover:border-primary/20 transition-all">
                               <div className="flex items-center justify-between mb-1.5">
                                 <span className="text-[9px] font-black uppercase text-primary/50">{new Date(m.created_at).toLocaleDateString()}</span>
                                 <Badge variant="default" className="text-[8px] h-4 px-1">{m.kind}</Badge>
                               </div>
                               {m.content}
                             </div>
                           ))
                        )}
                     </div>
                  </div>
               </div>
             </div>
          </div>
        )}

        {activeSection === 'llm' && (
          <div className="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
            <div>
              <h3 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
                Model Providers
                <Badge variant="info" className="text-[9px] uppercase tracking-widest">Global</Badge>
              </h3>
              <p className="text-sm text-muted-foreground mt-1">Configure default LLM provider, API credentials, and model selection.</p>
            </div>

            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm space-y-6">
              <div>
                <h4 className="text-sm font-bold text-foreground mb-4">Provider Settings</h4>
                <div className="grid grid-cols-1 gap-4">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">Base URL</label>
                    <Input
                      placeholder="https://api.openai.com/v1 (leave empty for default)"
                      value={llmBaseUrl}
                      onChange={(e) => setLlmBaseUrl(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">API Key</label>
                    <div className="relative">
                      <Input
                        type={showApiKey ? 'text' : 'password'}
                        placeholder="sk-..."
                        value={llmApiKey}
                        onChange={(e) => { setLlmApiKey(e.target.value); setLlmKeyDirty(true) }}
                        className="pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      >
                        {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">Default Model</label>
                    <Input
                      placeholder="gpt-4o"
                      value={llmDefaultModel}
                      onChange={(e) => setLlmDefaultModel(e.target.value)}
                    />
                  </div>
                </div>
                <div className="mt-4">
                  <Button
                    className="h-10 px-6 shadow-lg shadow-primary/20"
                    disabled={saveLlmMutation.isPending}
                    onClick={() => saveLlmMutation.mutate()}
                  >
                    {saveLlmMutation.isPending ? 'Saving...' : 'Save Configuration'}
                  </Button>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm space-y-4">
              <h4 className="text-sm font-bold text-foreground">Test Connection</h4>
              <p className="text-xs text-muted-foreground">Verify your API key works by sending a minimal request.</p>
              <div className="flex items-end gap-3">
                <div className="flex-1 space-y-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">Model</label>
                  <Input
                    placeholder={llmDefaultModel || 'gpt-4o'}
                    value={testModel}
                    onChange={(e) => setTestModel(e.target.value)}
                  />
                </div>
                <Button
                  className="h-10 px-5"
                  variant="secondary"
                  disabled={testLlmMutation.isPending}
                  onClick={() => { setTestResult(null); testLlmMutation.mutate() }}
                >
                  <Play className="h-3.5 w-3.5 mr-1.5" />
                  {testLlmMutation.isPending ? 'Testing...' : 'Test'}
                </Button>
              </div>
              {testResult && (
                <div className={`p-4 rounded-xl border ${testResult.ok ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-rose-500/5 border-rose-500/20'}`}>
                  <div className="flex items-center gap-2">
                    {testResult.ok ? (
                      <Check className="h-4 w-4 text-emerald-500" />
                    ) : (
                      <span className="w-4 h-4 rounded-full bg-rose-500 flex items-center justify-center text-white text-[10px] font-bold">!</span>
                    )}
                    <span className={`text-xs font-bold ${testResult.ok ? 'text-emerald-600' : 'text-rose-600'}`}>
                      {testResult.ok ? `Connected (${testResult.latency_ms}ms)` : 'Connection Failed'}
                    </span>
                  </div>
                  {testResult.error && <p className="mt-2 text-xs text-rose-500 font-mono">{testResult.error}</p>}
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-foreground">Available Models</h4>
                <Button
                  variant="secondary"
                  className="h-9 px-4"
                  disabled={discoverModelsMutation.isPending}
                  onClick={() => discoverModelsMutation.mutate()}
                >
                  {discoverModelsMutation.isPending ? 'Discovering...' : 'Discover Models'}
                </Button>
              </div>
              {discoveredModels.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {discoveredModels.map((model) => (
                    <button
                      key={model}
                      onClick={() => { setLlmDefaultModel(model); setTestModel(model) }}
                      className={`px-2.5 py-1 rounded-lg text-xs font-mono border transition-all ${
                        llmDefaultModel === model
                          ? 'bg-primary/10 border-primary/30 text-primary font-bold'
                          : 'bg-muted/30 border-border text-muted-foreground hover:border-primary/20 hover:text-foreground'
                      }`}
                    >
                      {model}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground/60">Click "Discover Models" to list available models from your provider.</p>
              )}
            </div>

            {/* Workspace-scoped provider override */}
            {workspace && (
              <div className="space-y-6 pt-4 border-t border-border">
                <div>
                  <h3 className="text-lg font-bold tracking-tight text-foreground flex items-center gap-2">
                    Workspace Provider
                    <Badge variant="warning" className="text-[9px] uppercase tracking-widest">Override</Badge>
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    Override the global provider for this workspace. Leave empty to use global defaults.
                  </p>
                </div>

                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm space-y-6">
                  <div className="grid grid-cols-1 gap-4">
                    <div className="space-y-2">
                      <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">
                        Base URL
                        {!wsLlmBaseUrl && llmBaseUrl && (
                          <span className="ml-2 text-muted-foreground/40 normal-case font-normal">
                            (inherits: {llmBaseUrl})
                          </span>
                        )}
                      </label>
                      <Input
                        placeholder="Leave empty to use global default"
                        value={wsLlmBaseUrl}
                        onChange={(e) => setWsLlmBaseUrl(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">
                        API Key
                        {!wsLlmApiKey && llmApiKey && (
                          <span className="ml-2 text-muted-foreground/40 normal-case font-normal">
                            (inherits global key)
                          </span>
                        )}
                      </label>
                      <div className="relative">
                        <Input
                          type={showWsApiKey ? 'text' : 'password'}
                          placeholder="Leave empty to use global default"
                          value={wsLlmApiKey}
                          onChange={(e) => setWsLlmApiKey(e.target.value)}
                          className="pr-10"
                        />
                        <button
                          type="button"
                          onClick={() => setShowWsApiKey(!showWsApiKey)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                        >
                          {showWsApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">
                        Default Model
                        {!wsLlmDefaultModel && llmDefaultModel && (
                          <span className="ml-2 text-muted-foreground/40 normal-case font-normal">
                            (inherits: {llmDefaultModel})
                          </span>
                        )}
                      </label>
                      <Input
                        placeholder="Leave empty to use global default"
                        value={wsLlmDefaultModel}
                        onChange={(e) => setWsLlmDefaultModel(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Button
                      className="h-10 px-6 shadow-lg shadow-primary/20"
                      disabled={saveWsLlmMutation.isPending}
                      onClick={() => saveWsLlmMutation.mutate()}
                    >
                      {saveWsLlmMutation.isPending ? 'Saving...' : 'Save Workspace Provider'}
                    </Button>
                    {(wsLlmBaseUrl || wsLlmApiKey || wsLlmDefaultModel) && (
                      <Button
                        variant="secondary"
                        className="h-10 px-4"
                        onClick={() => {
                          setWsLlmBaseUrl('')
                          setWsLlmApiKey('')
                          setWsLlmDefaultModel('')
                        }}
                      >
                        Clear Overrides
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeSection === 'api' && (
          <div className="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
             <div>
                <h3 className="text-2xl font-bold tracking-tight text-foreground">API Access Tokens</h3>
                <p className="text-sm text-muted-foreground mt-1">Authorization keys for headless agent execution and CLI integration.</p>
             </div>

             <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <div className="flex items-center gap-3 mb-8">
                   <div className="relative flex-1">
                      <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input placeholder="Key name (e.g. CI Pipeline)" value={keyName} onChange={(e) => setKeyName(e.target.value)} className="pl-10 h-11" />
                   </div>
                   <Button className="h-11 px-6 shadow-lg shadow-primary/20" disabled={!keyName.trim()} onClick={() => createKeyMutation.mutate(keyName)}>Generate Token</Button>
                </div>

                {createKeyMutation.data?.data?.key && (
                  <div className="mb-8 p-5 rounded-2xl bg-emerald-500/5 border border-emerald-500/20 animate-in zoom-in-95 duration-300">
                     <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                           <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                           <span className="text-xs font-bold uppercase tracking-widest text-emerald-600">New Token Generated</span>
                        </div>
                        <Badge variant="success" className="text-[9px] uppercase tracking-widest">Confidential</Badge>
                     </div>
                     <div className="flex items-center gap-2">
                        <code className="flex-1 font-mono text-xs bg-background/50 p-3 rounded-xl border border-emerald-500/10 truncate text-emerald-600 font-bold select-all">{createKeyMutation.data.data.key}</code>
                        <IconCopyButton active={copiedKey === createKeyMutation.data.data.id} onClick={() => copyText(createKeyMutation.data!.data.id, createKeyMutation.data!.data.key)} />
                     </div>
                     <p className="mt-3 text-[10px] text-emerald-600/60 font-medium italic">Make sure to copy this token now. You won't be able to see it again for security reasons.</p>
                  </div>
                )}

                <div className="space-y-3">
                   <h4 className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/40 px-1 mb-3">Your Platform Keys</h4>
                   {apiKeys.length === 0 ? (
                      <EmptyRow icon={Key} text="No API keys established" />
                   ) : (
                     <div className="grid grid-cols-1 gap-3">
                        {apiKeys.map((key: any) => (
                           <div key={key.id} className="flex items-center justify-between p-4 rounded-2xl border border-border bg-muted/20 group hover:bg-muted/40 hover:border-primary/20 transition-all">
                              <div className="flex items-center gap-4">
                                 <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center border border-primary/20 shadow-sm">
                                    <Key className="h-5 w-5 text-primary" />
                                 </div>
                                 <div>
                                    <div className="text-sm font-bold text-foreground">{key.name}</div>
                                    <div className="text-[10px] font-mono text-muted-foreground/60 mt-0.5">Prefix: <span className="font-bold">{key.prefix}</span></div>
                                 </div>
                              </div>
                              <button onClick={() => deleteKeyMutation.mutate(key.id)} className="p-2.5 rounded-xl text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-all opacity-0 group-hover:opacity-100" title="Revoke Key"><Trash2 className="h-4.5 w-4.5" /></button>
                           </div>
                        ))}
                     </div>
                   )}
                </div>
             </div>
          </div>
        )}

        {activeSection === 'bots' && (
          <div className="space-y-8 animate-in fade-in slide-in-from-right-4 duration-300">
             <div>
                <h3 className="text-2xl font-bold tracking-tight text-foreground">Message Bridge Gateways</h3>
                <p className="text-sm text-muted-foreground mt-1">Connect your local agents to corporate messaging systems via secure webhooks.</p>
             </div>

             <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <div className="grid grid-cols-2 gap-6 mb-8">
                   <div className="space-y-4">
                      <div className="space-y-2">
                        <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">Gateway Identity</label>
                        <Input placeholder="e.g. Slack Operations Bot" value={botName} onChange={(e) => setBotName(e.target.value)} />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                         <div className="space-y-2">
                           <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">Provider</label>
                           <select value={botProvider} onChange={(e) => setBotProvider(e.target.value)} className="w-full h-10 rounded-xl border border-border bg-muted px-3 py-2 text-sm outline-none focus:border-primary transition-colors appearance-none">
                              {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
                           </select>
                         </div>
                         <div className="space-y-2">
                            <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">Target Agent</label>
                            <select value={selectedAgentId} onChange={(e) => setSelectedAgentId(e.target.value)} className="w-full h-10 rounded-xl border border-border bg-muted px-3 py-2 text-sm outline-none focus:border-primary transition-colors appearance-none">
                               <option value="">Select Target...</option>
                               {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                            </select>
                         </div>
                      </div>
                   </div>
                   <div className="space-y-4">
                      <div className="space-y-2">
                        <label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/60 px-1">Security Secret</label>
                        <Input placeholder="Bridge verification secret" type="password" value={botSecret} onChange={(e) => setBotSecret(e.target.value)} />
                      </div>
                      <div className="pt-6">
                        <Button className="w-full h-11 shadow-lg shadow-indigo-500/20 bg-indigo-600 hover:bg-indigo-700" disabled={!botName.trim() || !botSecret} onClick={() => createBotMutation.mutate()}>
                           <Zap className="h-4 w-4 mr-2" />
                           Establish Gateway Bridge
                        </Button>
                      </div>
                   </div>
                </div>

                <div className="space-y-4">
                   <h4 className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/40 px-1 mb-1">Active Gateway Integrations</h4>
                   {bots.length === 0 ? (
                      <EmptyRow icon={Bot} text="No messaging bridges active" />
                   ) : (
                     <div className="grid grid-cols-1 gap-4">
                        {bots.map((bot) => (
                           <div key={bot.id} className="p-5 rounded-2xl border border-border bg-muted/10 group hover:border-indigo-500/30 hover:bg-muted/20 transition-all shadow-sm">
                              <div className="flex items-start justify-between mb-4">
                                 <div className="flex items-center gap-4">
                                    <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 flex items-center justify-center border border-indigo-500/20 text-indigo-500 shadow-inner">
                                       <Bot className="h-6 w-6" />
                                    </div>
                                    <div>
                                       <div className="flex items-center gap-2">
                                          <span className="text-base font-bold text-foreground tracking-tight">{bot.name}</span>
                                          <Badge variant={bot.enabled ? 'success' : 'default'} className="text-[10px] font-black uppercase tracking-widest">{bot.provider}</Badge>
                                       </div>
                                       <div className="text-[11px] text-muted-foreground mt-1 flex items-center gap-1.5">
                                          Routing to Agent: <span className="text-indigo-500 font-bold bg-indigo-500/10 px-1.5 py-0.5 rounded uppercase">{bot.agent_id}</span>
                                       </div>
                                    </div>
                                 </div>
                                 <button onClick={() => deleteBotMutation.mutate(bot.id)} className="p-2.5 rounded-xl text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-all" title="Delete Bridge"><Trash2 className="h-4.5 w-4.5" /></button>
                              </div>
                              <div className="flex items-center gap-3 bg-background/80 border border-border/50 p-3 rounded-xl shadow-inner">
                                 <div className="flex items-center gap-2 px-2 py-1 rounded bg-muted/50 text-[9px] font-bold text-muted-foreground uppercase border border-border/50">Endpoint</div>
                                 <code className="flex-1 font-mono text-[10px] text-muted-foreground truncate font-medium">{window.location.origin}{bot.webhook_path}</code>
                                 <IconCopyButton active={copiedKey === bot.id} onClick={() => copyText(bot.id, `${window.location.origin}${bot.webhook_path}`)} />
                              </div>
                           </div>
                        ))}
                     </div>
                   )}
                </div>
             </div>
          </div>
        )}
      </main>
    </div>
  )
}

function IconCopyButton({ active, onClick }: { active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground transition-all hover:bg-background hover:text-primary border border-transparent hover:border-border active:scale-90"
      aria-label="Copy"
    >
      {active ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
    </button>
  )
}

function MemoryEditor({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="space-y-2.5">
      <div className="text-[10px] font-black uppercase tracking-[0.1em] text-muted-foreground/60 flex items-center gap-2">
         <Wrench className="h-3 w-3" />
         {label}
      </div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full h-44 resize-none rounded-2xl border border-border bg-muted/20 p-4 font-mono text-[11px] leading-relaxed text-foreground focus:ring-2 focus:ring-primary/10 focus:border-primary outline-none transition-all scrollbar-hide shadow-inner"
      />
    </div>
  )
}

function EmptyRow({ icon: Icon, text }: { icon: LucideIcon; text: string }) {
  return (
    <div className="py-20 text-center bg-muted/5 rounded-3xl border-2 border-dashed border-border/30">
      <div className="w-16 h-16 rounded-full bg-muted/20 flex items-center justify-center mx-auto mb-4 border border-border shadow-inner">
        <Icon className="h-8 w-8 text-muted-foreground/10" />
      </div>
      <p className="text-[10px] font-black text-muted-foreground uppercase tracking-[0.2em]">{text}</p>
    </div>
  )
}
