import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PlugZap, Puzzle, Server, Trash2, Wrench, type LucideIcon } from 'lucide-react'
import { api } from '@/shared/api/client'
import { Badge, Button, Input, Spinner } from '@/shared/ui'

interface WorkspaceInfo {
  id: string
  name: string
}

interface WorkspaceSkill {
  name: string
  version: string
  description?: string
  author?: string
  tags?: string
  tools: string[]
  enabled: boolean
}

interface MCPServer {
  id: string
  name: string
  command: string
  args: string[]
  env: Record<string, string>
  enabled: boolean
}

export default function SkillList() {
  const queryClient = useQueryClient()
  const [serverName, setServerName] = useState('')
  const [serverCommand, setServerCommand] = useState('')
  const [serverArgs, setServerArgs] = useState('')

  const { data: workspaces = [], isLoading: workspacesLoading } = useQuery<WorkspaceInfo[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get('/workspaces').then((r) => r.data),
  })
  const workspace = workspaces[0]

  const { data: skills = [], isLoading: skillsLoading } = useQuery<WorkspaceSkill[]>({
    queryKey: ['workspace-skills', workspace?.id],
    queryFn: () => api.get(`/workspaces/${workspace.id}/skills`).then((r) => r.data),
    enabled: !!workspace,
  })

  const { data: servers = [], isLoading: serversLoading } = useQuery<MCPServer[]>({
    queryKey: ['workspace-mcp-servers', workspace?.id],
    queryFn: () => api.get(`/workspaces/${workspace.id}/mcp/servers`).then((r) => r.data),
    enabled: !!workspace,
  })

  const toggleSkillMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api.put(`/workspaces/${workspace.id}/skills/${name}`, { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workspace-skills', workspace?.id] }),
  })

  const createServerMutation = useMutation({
    mutationFn: () =>
      api.post(`/workspaces/${workspace.id}/mcp/servers`, {
        name: serverName.trim(),
        command: serverCommand.trim(),
        args: splitArgs(serverArgs),
        enabled: true,
      }),
    onSuccess: () => {
      setServerName('')
      setServerCommand('')
      setServerArgs('')
      queryClient.invalidateQueries({ queryKey: ['workspace-mcp-servers', workspace?.id] })
    },
  })

  const deleteServerMutation = useMutation({
    mutationFn: (serverId: string) => api.delete(`/workspaces/${workspace.id}/mcp/servers/${serverId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workspace-mcp-servers', workspace?.id] }),
  })

  const isLoading = workspacesLoading || skillsLoading || serversLoading

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-6">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-primary">
            <PlugZap className="h-4 w-4" />
            Workspace Capabilities
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">Skills & MCP</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Configure reusable skills and MCP servers for {workspace?.name || 'the active workspace'}.
          </p>
        </div>
        {workspace && <Badge variant="primary">{workspace.name}</Badge>}
      </div>

      {!workspace && !workspacesLoading ? (
        <EmptyPanel icon={Puzzle} title="No Workspace" text="Create a workspace before configuring skills." />
      ) : isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Spinner />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <section className="rounded-2xl border border-border bg-card">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
                  <Puzzle className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">Workspace Skills</h3>
                  <p className="text-[11px] text-muted-foreground">{skills.length} installed packages</p>
                </div>
              </div>
            </div>

            <div className="divide-y divide-border">
              {skills.length === 0 ? (
                <EmptyPanel icon={Puzzle} title="No Skills Installed" text="Install package skills to enable them per workspace." />
              ) : (
                skills.map((skill) => (
                  <div key={skill.name} className="flex items-start justify-between gap-4 px-5 py-4">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-sm font-bold text-foreground">{skill.name}</h4>
                        <Badge variant={skill.enabled ? 'success' : 'default'}>
                          {skill.enabled ? 'Enabled' : 'Disabled'}
                        </Badge>
                        <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                          v{skill.version}
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        {skill.description || 'No description'}
                      </p>
                      {skill.tools.length > 0 && (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {skill.tools.map((tool) => (
                            <span
                              key={tool}
                              className="inline-flex items-center gap-1 rounded-lg border border-border bg-muted px-2 py-1 text-[10px] font-bold text-muted-foreground"
                            >
                              <Wrench className="h-3 w-3" />
                              {tool}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => toggleSkillMutation.mutate({ name: skill.name, enabled: !skill.enabled })}
                      disabled={toggleSkillMutation.isPending}
                      className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors ${
                        skill.enabled
                          ? 'border-primary/30 bg-primary'
                          : 'border-border bg-muted'
                      }`}
                      aria-label={`${skill.enabled ? 'Disable' : 'Enable'} ${skill.name}`}
                    >
                      <span
                        className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-white shadow transition-transform ${
                          skill.enabled ? 'translate-x-5' : 'translate-x-0.5'
                        }`}
                      />
                    </button>
                  </div>
                ))
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-border bg-card">
            <div className="border-b border-border px-5 py-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
                  <Server className="h-4 w-4 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">MCP Servers</h3>
                  <p className="text-[11px] text-muted-foreground">Workspace-scoped tool bridges</p>
                </div>
              </div>
            </div>

            <div className="space-y-3 p-5">
              <Input placeholder="Server name" value={serverName} onChange={(event) => setServerName(event.target.value)} />
              <Input placeholder="Command, e.g. npx" value={serverCommand} onChange={(event) => setServerCommand(event.target.value)} />
              <Input
                placeholder="Arguments, space separated"
                value={serverArgs}
                onChange={(event) => setServerArgs(event.target.value)}
              />
              <Button
                className="w-full"
                disabled={!serverName.trim() || !serverCommand.trim() || createServerMutation.isPending}
                onClick={() => createServerMutation.mutate()}
              >
                Add MCP Server
              </Button>
            </div>

            <div className="divide-y divide-border border-t border-border">
              {servers.length === 0 ? (
                <EmptyPanel icon={Server} title="No MCP Servers" text="Add a local or remote MCP server for this workspace." />
              ) : (
                servers.map((server) => (
                  <div key={server.id} className="flex items-start justify-between gap-4 px-5 py-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-bold text-foreground">{server.name}</h4>
                        <Badge variant={server.enabled ? 'success' : 'default'}>{server.enabled ? 'On' : 'Off'}</Badge>
                      </div>
                      <p className="mt-2 truncate font-mono text-xs text-muted-foreground">
                        {server.command} {server.args.join(' ')}
                      </p>
                    </div>
                    <button
                      onClick={() => deleteServerMutation.mutate(server.id)}
                      disabled={deleteServerMutation.isPending}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-rose-500 disabled:opacity-40"
                      aria-label={`Delete ${server.name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

function EmptyPanel({
  icon: Icon,
  title,
  text,
}: {
  icon: LucideIcon
  title: string
  text: string
}) {
  return (
    <div className="py-16 text-center">
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-muted">
        <Icon className="h-7 w-7 text-muted-foreground/30" />
      </div>
      <h3 className="text-sm font-bold text-foreground">{title}</h3>
      <p className="mx-auto mt-2 max-w-xs text-xs leading-5 text-muted-foreground">{text}</p>
    </div>
  )
}

function splitArgs(value: string) {
  return value
    .split(' ')
    .map((item) => item.trim())
    .filter(Boolean)
}
