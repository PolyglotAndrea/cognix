import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ExternalLink,
  Link2,
  Loader2,
  Plug,
  Unplug,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import { Badge, Button, Spinner } from '@/shared/ui'
import { ConnectorToolCallModal } from './ConnectorToolCallModal'
import type { ConnectorPlatform, ConnectorTool } from './types'

const platformIcons: Record<string, string> = {
  x: '𝕏',
  instagram: '📷',
}

export default function ConnectorsPage() {
  const queryClient = useQueryClient()
  const [testTool, setTestTool] = useState<ConnectorTool | null>(null)
  const [connecting, setConnecting] = useState<string | null>(null)

  const { data: platforms = [], isLoading: platformsLoading } = useQuery<ConnectorPlatform[]>({
    queryKey: ['connectors', 'platforms'],
    queryFn: () => api.get('/connectors/platforms').then((r) => r.data),
  })

  const { data: tools = [] } = useQuery<ConnectorTool[]>({
    queryKey: ['connectors', 'tools'],
    queryFn: () => api.get('/connectors/tools').then((r) => r.data),
  })

  const connectMutation = useMutation({
    mutationFn: (platform: string) =>
      api.post(`/connectors/oauth/${platform}/authorize`).then((r) => r.data),
    onSuccess: (data, platform) => {
      setConnecting(null)
      // Store platform so the callback page can use it
      sessionStorage.setItem('connector_oauth_platform', platform)
      window.location.href = data.url
    },
    onError: () => setConnecting(null),
  })

  const disconnectMutation = useMutation({
    mutationFn: (credentialId: string) =>
      api.delete(`/connectors/credentials/${credentialId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectors'] })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ toolName, enabled }: { toolName: string; enabled: boolean }) =>
      api.put(`/connectors/tools/${toolName}`, { tool_name: toolName, enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectors', 'tools'] })
    },
  })

  if (platformsLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-6">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-primary">
            <Plug className="h-4 w-4" />
            INTEGRATIONS
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">Connectors</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Connect external platforms so your agents can post, read, and interact on your behalf.
          </p>
        </div>
      </div>

      {/* Platform Cards */}
      <section className="rounded-2xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
              <Link2 className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-foreground">Platforms</h3>
              <p className="text-[11px] text-muted-foreground">Connect your social accounts</p>
            </div>
          </div>
        </div>
        <div className="divide-y divide-border">
          {platforms.map((p) => (
            <PlatformRow
              key={p.platform}
              platform={p}
              connecting={connecting === p.platform}
              onConnect={() => {
                setConnecting(p.platform)
                connectMutation.mutate(p.platform)
              }}
              onDisconnect={(credId) => disconnectMutation.mutate(credId)}
            />
          ))}
          {platforms.length === 0 && (
            <div className="px-5 py-12 text-center text-xs text-muted-foreground">
              No platforms available
            </div>
          )}
        </div>
      </section>

      {/* Connector Tools */}
      {tools.length > 0 && (
        <section className="rounded-2xl border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
                <Plug className="h-4 w-4 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-foreground">Tools</h3>
                <p className="text-[11px] text-muted-foreground">
                  {tools.length} tools from connected platforms
                </p>
              </div>
            </div>
          </div>
          <div className="divide-y divide-border">
            {tools.map((tool) => (
              <ToolRow
                key={tool.name}
                tool={tool}
                onTest={() => setTestTool(tool)}
                onToggle={(enabled) =>
                  toggleMutation.mutate({ toolName: tool.name, enabled })
                }
              />
            ))}
          </div>
        </section>
      )}

      {/* Test Modal */}
      {testTool && (
        <ConnectorToolCallModal
          isOpen={!!testTool}
          onClose={() => setTestTool(null)}
          tool={testTool}
        />
      )}
    </div>
  )
}

function PlatformRow({
  platform,
  connecting,
  onConnect,
  onDisconnect,
}: {
  platform: ConnectorPlatform
  connecting: boolean
  onConnect: () => void
  onDisconnect: (credId: string) => void
}) {
  const icon = platformIcons[platform.platform] || '🔗'
  const cred = platform.credentials[0]

  return (
    <div className="flex items-center justify-between px-5 py-4">
      <div className="flex items-center gap-3">
        <span className="text-xl">{icon}</span>
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-foreground">{platform.display_name}</span>
            {platform.connected ? (
              <Badge variant="success">Connected</Badge>
            ) : (
              <Badge variant="default">Not connected</Badge>
            )}
          </div>
          {cred && (
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              @{cred.platform_username}
              {cred.scopes && (
                <span className="ml-2 text-[10px] text-muted-foreground/60">
                  scopes: {cred.scopes}
                </span>
              )}
            </p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {platform.connected && cred ? (
          <Button
            size="sm"
            variant="danger"
            onClick={() => onDisconnect(cred.id)}
            className="gap-1.5"
          >
            <Unplug className="h-3.5 w-3.5" />
            Disconnect
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={onConnect}
            disabled={connecting}
            className="gap-1.5"
          >
            {connecting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ExternalLink className="h-3.5 w-3.5" />
            )}
            Connect
          </Button>
        )}
      </div>
    </div>
  )
}

function ToolRow({
  tool,
  onTest,
  onToggle,
}: {
  tool: ConnectorTool
  onTest: () => void
  onToggle: (enabled: boolean) => void
}) {
  const accessBadge =
    tool.access_level === 'read'
      ? 'success'
      : tool.access_level === 'write'
        ? 'warning'
        : 'error'

  return (
    <div className="flex items-center gap-4 px-5 py-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Badge variant="default">{tool.platform}</Badge>
          <span className="text-sm font-bold text-foreground">{tool.original_name}</span>
          <Badge variant={accessBadge as any}>{tool.access_level}</Badge>
        </div>
        <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{tool.description}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          onClick={onTest}
          className="flex h-7 items-center gap-1 rounded-lg px-2 text-[10px] font-bold text-primary transition-colors hover:bg-primary/10"
        >
          Test
        </button>
        <button
          type="button"
          onClick={() => onToggle(!tool.enabled)}
          className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
            tool.enabled ? 'bg-primary' : 'bg-muted'
          }`}
        >
          <div
            className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
              tool.enabled ? 'left-[18px]' : 'left-0.5'
            }`}
          />
        </button>
      </div>
    </div>
  )
}
