import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Plus,
  Settings,
  Sliders,
  Wrench,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { useWorkspaceStore } from './store'
import { Button, Input, Panel, PanelBody, Badge } from '@/shared/ui'

interface Agent {
  id: string
  name: string
  model: string
  description: string
  system_prompt: string
  temperature: number
  max_iterations: number
}

const MODELS = ['gpt-4o', 'gpt-4o-mini', 'claude-3.5-sonnet', 'echo']

export function LeftPanel() {
  const { selectedAgentId, setSelectedAgent } = useWorkspaceStore()
  const queryClient = useQueryClient()

  const { data: agents = [] } = useQuery<Agent[]>({
    queryKey: ['agents'],
    queryFn: () => api.get('/agents').then((r) => r.data),
  })

  const selected = agents.find((a) => a.id === selectedAgentId) || null

  // Create agent
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newModel, setNewModel] = useState('gpt-4o')

  const createMutation = useMutation({
    mutationFn: (data: { name: string; model: string }) => api.post('/agents', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setShowCreate(false)
      setNewName('')
    },
  })

  // Update agent
  const updateMutation = useMutation({
    mutationFn: (data: Partial<Agent>) =>
      api.put(`/agents/${selectedAgentId}`, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })

  // Sections
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    agent: true,
    prompt: true,
    params: true,
    tools: true,
  })

  const toggleSection = (key: string) =>
    setOpenSections((s) => ({ ...s, [key]: !s[key] }))

  return (
    <Panel className="w-80 shrink-0 border-r border-border bg-card">
      {/* Agent Selector */}
      <div className="border-b border-border">
        <button
          onClick={() => toggleSection('agent')}
          className="w-full px-6 py-4 flex items-center justify-between hover:bg-muted transition-colors group"
        >
          <div className="flex items-center gap-3 text-xs font-bold text-muted-foreground uppercase tracking-widest">
            <Bot className="h-4 w-4 text-primary" />
            Active Agents
          </div>
          {openSections.agent ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground group-hover:text-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground" />
          )}
        </button>
        {openSections.agent && (
          <div className="px-3 pb-4 space-y-1">
            {agents.map((agent) => (
              <button
                key={agent.id}
                onClick={() => setSelectedAgent(agent.id)}
                className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-200 group border ${
                  selectedAgentId === agent.id
                    ? 'bg-primary/10 text-foreground border-primary/20 shadow-sm shadow-primary/5'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted border-transparent'
                }`}
              >
                <div className="font-bold text-sm truncate mb-0.5">{agent.name}</div>
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50" />
                  <div className="text-[10px] opacity-60 font-medium uppercase tracking-tight truncate">{agent.model}</div>
                </div>
              </button>
            ))}

            {showCreate ? (
              <div className="p-4 bg-muted/50 rounded-2xl border border-border space-y-3 mt-2 animate-in fade-in zoom-in-95 duration-200">
                <Input
                  placeholder="Agent Name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="bg-background"
                />
                <select
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  className="w-full px-4 py-2 bg-background border border-border rounded-xl text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/20 transition-all appearance-none"
                  style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2364748b'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 1rem center', backgroundSize: '1rem' }}
                >
                  {MODELS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    className="flex-1"
                    disabled={!newName.trim() || createMutation.isPending}
                    onClick={() => createMutation.mutate({ name: newName, model: newModel })}
                  >
                    Create
                  </Button>
                  <Button size="sm" variant="ghost" className="flex-1" onClick={() => setShowCreate(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowCreate(true)}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-xs font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground hover:bg-muted border border-dashed border-border hover:border-primary/50 transition-all mt-2"
              >
                <Plus className="h-4 w-4" />
                New Agent
              </button>
            )}
          </div>
        )}
      </div>

      {/* No agent selected state */}
      {!selected && (
        <PanelBody className="flex items-center justify-center p-8 bg-card">
          <div className="text-center">
            <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
               <Bot className="h-8 w-8 text-muted-foreground/30" />
            </div>
            <h3 className="text-sm font-bold text-foreground mb-2">Agent Control Center</h3>
            <p className="text-xs text-muted-foreground max-w-[200px] mx-auto leading-relaxed">
              Select an agent from the list above to initialize the configuration and begin interaction.
            </p>
          </div>
        </PanelBody>
      )}

      {/* Agent Config (shown when agent selected) */}
      {selected && (
        <PanelBody className="bg-card scrollbar-hide">
          {/* System Prompt */}
          <div className="border-b border-border">
            <button
              onClick={() => toggleSection('prompt')}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-muted transition-colors group"
            >
              <div className="flex items-center gap-3 text-xs font-bold text-muted-foreground uppercase tracking-widest">
                <Settings className="h-4 w-4 text-primary/70 group-hover:text-primary transition-colors" />
                System Core
              </div>
              {openSections.prompt ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
            {openSections.prompt && (
              <div className="px-6 pb-6">
                <textarea
                  value={selected.system_prompt}
                  onChange={(e) =>
                    updateMutation.mutate({ system_prompt: e.target.value })
                  }
                  rows={8}
                  placeholder="Define the agent's behavior and constraints..."
                  className="w-full px-4 py-3 bg-muted/50 border border-border rounded-2xl text-xs text-foreground resize-none focus:ring-2 focus:ring-primary/20 focus:border-primary/40 focus:bg-background outline-none transition-all placeholder:text-muted-foreground/30 leading-relaxed font-mono"
                />
              </div>
            )}
          </div>

          {/* Parameters */}
          <div className="border-b border-border">
            <button
              onClick={() => toggleSection('params')}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-muted transition-colors group"
            >
              <div className="flex items-center gap-3 text-xs font-bold text-muted-foreground uppercase tracking-widest">
                <Sliders className="h-4 w-4 text-primary/70 group-hover:text-primary transition-colors" />
                Runtime Params
              </div>
              {openSections.params ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
            {openSections.params && (
              <div className="px-6 pb-6 space-y-6">
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Model</label>
                    <Badge variant="primary">Active</Badge>
                  </div>
                  <select
                    value={selected.model}
                    onChange={(e) => updateMutation.mutate({ model: e.target.value })}
                    className="w-full px-4 py-2.5 bg-muted/50 border border-border rounded-xl text-xs text-foreground outline-none focus:ring-2 focus:ring-primary/20 transition-all appearance-none"
                    style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2364748b'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 1rem center', backgroundSize: '1rem' }}
                  >
                    {MODELS.map((m) => (
                      <option key={m} value={m} className="bg-card text-foreground">
                        {m}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                      Temperature
                    </label>
                    <span className="text-xs font-mono text-primary font-bold">{selected.temperature.toFixed(1)}</span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={2}
                    step={0.1}
                    value={selected.temperature}
                    onChange={(e) =>
                      updateMutation.mutate({ temperature: parseFloat(e.target.value) })
                    }
                    className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-3">Max Iterations</label>
                  <Input
                    type="number"
                    min={1}
                    max={50}
                    value={selected.max_iterations}
                    onChange={(e) =>
                      updateMutation.mutate({ max_iterations: parseInt(e.target.value) || 10 })
                    }
                    className="bg-muted/50 font-mono text-xs"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Tools & Skills */}
          <div>
            <button
              onClick={() => toggleSection('tools')}
              className="w-full px-6 py-4 flex items-center justify-between hover:bg-muted transition-colors group"
            >
              <div className="flex items-center gap-3 text-xs font-bold text-muted-foreground uppercase tracking-widest">
                <Wrench className="h-4 w-4 text-primary/70 group-hover:text-primary transition-colors" />
                Capabilities
              </div>
              {openSections.tools ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </button>
            {openSections.tools && (
              <div className="px-6 pb-6">
                <div className="p-4 bg-muted/50 border border-border rounded-2xl">
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    Configure available tools and marketplace skills in the <span className="text-primary font-bold">Skills Portal</span> or use the global search to add new capabilities to this agent.
                  </p>
                </div>
              </div>
            )}
          </div>
        </PanelBody>
      )}
    </Panel>
  )
}
