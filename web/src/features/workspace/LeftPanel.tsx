import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Plus,
  Zap,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { useWorkspaceStore } from './store'
import { Button, Input, Panel, PanelBody, Badge, PanelHeader } from '@/shared/ui'
import type { DragHandleProps } from './types'
import { useCurrentWorkspace } from './useCurrentWorkspace'

interface Agent {
  id: string
  name: string
  model: string
  description: string
  system_prompt: string
  temperature: number
  max_iterations: number
  workspace_id?: string | null
}

export function LeftPanel({ dragHandleProps }: { dragHandleProps?: DragHandleProps }) {
  const { selectedAgentId, setSelectedAgent } = useWorkspaceStore()
  const queryClient = useQueryClient()
  const { workspaceId } = useCurrentWorkspace()

  const { data: agents = [] } = useQuery<Agent[]>({
    queryKey: ['agents', workspaceId],
    queryFn: () => api.get('/agents', { params: { workspace_id: workspaceId } }).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const selected = agents.find((a) => a.id === selectedAgentId) || null

  // Fetch available models from the configured provider.
  const { data: availableModels = [] } = useQuery<string[]>({
    queryKey: ['models'],
    queryFn: () => api.get('/providers/models').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  })

  // Create agent
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newModel, setNewModel] = useState('')

  const createMutation = useMutation({
    mutationFn: (data: { name: string; model: string }) =>
      api.post('/agents', { ...data, workspace_id: workspaceId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', workspaceId] })
      setShowCreate(false)
      setNewName('')
    },
  })

  // Update agent
  const updateMutation = useMutation({
    mutationFn: (data: Partial<Agent>) =>
      api.put(`/agents/${selectedAgentId}`, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents', workspaceId] }),
  })

  // Workspace skills
  interface SkillInfo { name: string; description?: string; enabled: boolean }
  const { data: skills = [] } = useQuery<SkillInfo[]>({
    queryKey: ['workspace-skills', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/skills`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const toggleSkillMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api.put(`/workspaces/${workspaceId}/skills/${name}`, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workspace-skills', workspaceId] }),
  })

  // Sections — only agent list is open by default
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    agent: true,
    prompt: false,
    params: false,
    tools: false,
  })

  const toggleSection = (key: string) =>
    setOpenSections((s) => ({ ...s, [key]: !s[key] }))

  return (
    <Panel className="w-80 shrink-0 border-r border-border bg-card h-full">
      <PanelHeader dragHandleProps={dragHandleProps} className="bg-muted/30">
        <div className="flex items-center gap-2">
           <Bot className="h-4 w-4 text-primary" />
           <span className="text-xs font-bold uppercase tracking-widest text-foreground">Agent Manager</span>
        </div>
      </PanelHeader>

      <PanelBody className="scrollbar-hide">
        {/* Agent Selector */}
        <div className="border-b border-border">
          <button
            onClick={() => toggleSection('agent')}
            className="w-full px-6 py-4 flex items-center justify-between hover:bg-muted transition-colors group"
          >
            <div className="flex items-center gap-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
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
                    value={newModel || availableModels[0] || ''}
                    onChange={(e) => setNewModel(e.target.value)}
                    className="w-full px-4 py-2 bg-background border border-border rounded-xl text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/20 transition-all appearance-none"
                    style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2364748b'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'%3E%3C/path%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 1rem center', backgroundSize: '1rem' }}
                  >
                    {availableModels.length === 0 && (
                      <option value="">Configure provider models first</option>
                    )}
                    {availableModels.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      className="flex-1"
                      disabled={!workspaceId || !newName.trim() || !availableModels.length || createMutation.isPending}
                      onClick={() => createMutation.mutate({ name: newName, model: newModel || availableModels[0] })}
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
          <div className="flex items-center justify-center p-8">
            <div className="text-center">
              <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                 <Bot className="h-8 w-8 text-muted-foreground/30" />
              </div>
              <h3 className="text-sm font-bold text-foreground mb-2">Agent Control Center</h3>
              <p className="text-xs text-muted-foreground max-w-[200px] mx-auto leading-relaxed">
                Select an agent from the list above to initialize the configuration and begin interaction.
              </p>
            </div>
          </div>
        )}

        {/* Agent Config (shown when agent selected) */}
        {selected && (
          <>
            {/* System Prompt */}
            <div className="border-b border-border">
              <button
                onClick={() => toggleSection('prompt')}
                className="w-full px-6 py-4 flex items-center justify-between hover:bg-muted transition-colors group"
              >
                <div className="flex items-center gap-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
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
                <div className="flex items-center gap-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
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
                      {availableModels.map((m) => (
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
                <div className="flex items-center gap-3 text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                  Capabilities
                </div>
                {openSections.tools ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                )}
              </button>
              {openSections.tools && (
                <div className="px-6 pb-6 space-y-2">
                  {skills.length === 0 ? (
                    <div className="p-4 bg-muted/50 border border-border rounded-2xl">
                      <p className="text-[11px] text-muted-foreground leading-relaxed">
                        No skills installed yet. Use <span className="text-primary font-bold">cognix skill install</span> to add capabilities.
                      </p>
                    </div>
                  ) : (
                    skills.map((skill) => (
                      <div
                        key={skill.name}
                        className="flex items-center justify-between p-3 rounded-xl bg-muted/30 border border-border hover:border-primary/20 transition-all"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          <Zap className={`h-3.5 w-3.5 shrink-0 ${skill.enabled ? 'text-primary' : 'text-muted-foreground/40'}`} />
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-foreground truncate">{skill.name}</div>
                            {skill.description && (
                              <div className="text-[10px] text-muted-foreground truncate">{skill.description}</div>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => toggleSkillMutation.mutate({ name: skill.name, enabled: !skill.enabled })}
                          disabled={toggleSkillMutation.isPending}
                          className={`relative w-9 h-5 rounded-full transition-colors shrink-0 ml-2 ${
                            skill.enabled ? 'bg-primary' : 'bg-muted-foreground/20'
                          }`}
                        >
                          <div
                            className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${
                              skill.enabled ? 'translate-x-4' : 'translate-x-0.5'
                            }`}
                          />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </PanelBody>
    </Panel>
  )
}
