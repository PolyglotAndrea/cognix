import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Shield, Save, RotateCcw } from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

interface PolicySettings {
  file_write: string
  network_access: string
  mcp_tools: string
  connector_access: string
  max_file_size_mb: number
  allowed_domains: string[]
  blocked_commands: string[]
}

const ACCESS_LEVELS = ['ask', 'workspace-read', 'workspace-write', 'full']

interface PolicyPanelProps {
  workspaceId: string
}

export function PolicyPanel({ workspaceId }: PolicyPanelProps) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<PolicySettings | null>(null)

  const { data: policy, isLoading } = useQuery<PolicySettings>({
    queryKey: ['workspace-policy', workspaceId],
    queryFn: () =>
      api.get(`/workspaces/${workspaceId}/policy`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const updateMutation = useMutation({
    mutationFn: (updates: Partial<PolicySettings>) =>
      api.patch(`/workspaces/${workspaceId}/policy`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace-policy', workspaceId] })
      setEditing(null)
    },
  })

  const current = editing ?? policy

  const handleChange = (key: keyof PolicySettings, value: string | number | string[]) => {
    if (!current) return
    setEditing({ ...current, [key]: value })
  }

  if (isLoading) {
    return (
      <div className="p-4 py-20 text-center">
        <Shield className="h-8 w-8 text-muted-foreground/20 animate-pulse mx-auto mb-4" />
        <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">
          Loading Policy
        </p>
      </div>
    )
  }

  if (!current) return null

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
          Sandbox Policy
        </h4>
        {editing && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => setEditing(null)}
              className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => updateMutation.mutate(editing)}
              disabled={updateMutation.isPending}
              className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <Save className="h-3 w-3" />
              Save
            </button>
          </div>
        )}
      </div>

      {/* Permission selectors */}
      {(['file_write', 'network_access', 'mcp_tools', 'connector_access'] as const).map((key) => (
        <div key={key} className="space-y-1.5">
          <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
            {key.replace(/_/g, ' ')}
          </label>
          <div className="flex gap-1">
            {ACCESS_LEVELS.map((level) => (
              <button
                key={level}
                onClick={() => handleChange(key, level)}
                className={cn(
                  'flex-1 px-2 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all border',
                  current[key] === level
                    ? 'bg-primary/10 text-primary border-primary/20'
                    : 'text-muted-foreground border-transparent hover:bg-muted hover:border-border',
                )}
              >
                {level.replace('workspace-', '')}
              </button>
            ))}
          </div>
        </div>
      ))}

      {/* Max file size */}
      <div className="space-y-1.5">
        <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          Max file size (MB)
        </label>
        <input
          type="number"
          value={current.max_file_size_mb}
          onChange={(e) => handleChange('max_file_size_mb', Number(e.target.value))}
          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-foreground outline-none focus:ring-2 focus:ring-primary/20"
        />
      </div>

      {/* Allowed domains */}
      <div className="space-y-1.5">
        <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          Allowed domains
        </label>
        <input
          type="text"
          value={current.allowed_domains.join(', ')}
          onChange={(e) =>
            handleChange(
              'allowed_domains',
              e.target.value
                .split(',')
                .map((d) => d.trim())
                .filter(Boolean),
            )
          }
          placeholder="example.com, api.openai.com"
          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-foreground outline-none focus:ring-2 focus:ring-primary/20"
        />
        <p className="text-[9px] text-muted-foreground">Comma-separated. Empty = allow all.</p>
      </div>

      {/* Blocked commands */}
      <div className="space-y-1.5">
        <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          Blocked commands
        </label>
        <input
          type="text"
          value={current.blocked_commands.join(', ')}
          onChange={(e) =>
            handleChange(
              'blocked_commands',
              e.target.value
                .split(',')
                .map((c) => c.trim())
                .filter(Boolean),
            )
          }
          placeholder="rm -rf, sudo"
          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-foreground outline-none focus:ring-2 focus:ring-primary/20"
        />
      </div>
    </div>
  )
}
