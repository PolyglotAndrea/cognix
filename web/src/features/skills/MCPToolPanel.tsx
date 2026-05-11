import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, Wrench } from 'lucide-react'
import { api } from '@/shared/api/client'
import { Badge, Spinner } from '@/shared/ui'
import { MCPToolCallModal } from './MCPToolCallModal'
import type { MCPTool } from './types'

const accessBadge: Record<string, 'success' | 'warning' | 'error'> = {
  read: 'success',
  write: 'warning',
  dangerous: 'error',
}

export function MCPToolPanel({
  workspaceId,
  serverId,
}: {
  workspaceId: string
  serverId: string
}) {
  const queryClient = useQueryClient()
  const [testTool, setTestTool] = useState<MCPTool | null>(null)

  const toolsKey = ['workspace-mcp-tools', workspaceId, serverId]
  const { data: tools = [], isLoading } = useQuery<MCPTool[]>({
    queryKey: toolsKey,
    queryFn: () =>
      api
        .get(`/workspaces/${workspaceId}/mcp/servers/${serverId}/tools`)
        .then((r) => r.data),
    enabled: !!workspaceId && !!serverId,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ tool, enabled }: { tool: MCPTool; enabled: boolean }) =>
      api.put(
        `/workspaces/${workspaceId}/mcp/servers/${serverId}/tools/${tool.original_name}`,
        { tool_name: tool.original_name, enabled },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: toolsKey })
      queryClient.invalidateQueries({ queryKey: ['workspace-mcp-server-status', workspaceId, serverId] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Spinner />
      </div>
    )
  }

  if (tools.length === 0) {
    return (
      <div className="py-6 text-center">
        <p className="text-xs text-muted-foreground">No tools discovered</p>
      </div>
    )
  }

  return (
    <>
      <div className="divide-y divide-border">
        {tools.map((tool) => (
          <div
            key={tool.name}
            className="flex items-center gap-3 px-5 py-3"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-muted">
              <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-bold text-foreground">{tool.original_name}</span>
                <Badge variant={accessBadge[tool.access_level] || 'default'}>
                  {tool.access_level}
                </Badge>
              </div>
              {tool.description && (
                <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                  {tool.description.length > 100
                    ? tool.description.slice(0, 100) + '...'
                    : tool.description}
                </p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                onClick={() => setTestTool(tool)}
                className="flex h-7 items-center gap-1.5 rounded-lg border border-border px-2.5 text-[10px] font-bold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                title={`Test ${tool.original_name}`}
              >
                <FlaskConical className="h-3 w-3" />
                Test
              </button>
              <button
                onClick={() => toggleMutation.mutate({ tool, enabled: false })}
                disabled={toggleMutation.isPending}
                className="relative h-5 w-9 shrink-0 rounded-full border border-primary/30 bg-primary transition-colors disabled:opacity-50"
                aria-label={`Disable ${tool.original_name}`}
              >
                <span className="absolute top-0.5 left-[18px] h-[14px] w-[14px] rounded-full bg-white shadow transition-transform" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {testTool && (
        <MCPToolCallModal
          isOpen={!!testTool}
          onClose={() => setTestTool(null)}
          tool={testTool}
          workspaceId={workspaceId}
          serverId={serverId}
        />
      )}
    </>
  )
}
