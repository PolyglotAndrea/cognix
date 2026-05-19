import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { useWorkspaceStore } from './store'

export interface WorkspaceInfo {
  id: string
  name: string
  path: string
  description?: string
}

export function useCurrentWorkspace() {
  const selectedWorkspaceId = useWorkspaceStore((s) => s.selectedWorkspaceId)
  const setSelectedWorkspace = useWorkspaceStore((s) => s.setSelectedWorkspace)

  const query = useQuery<WorkspaceInfo[]>({
    queryKey: ['workspaces'],
    queryFn: () => api.get('/workspaces').then((r) => r.data),
  })

  const workspaces = query.data || []
  const selected = workspaces.find((workspace) => workspace.id === selectedWorkspaceId)
  const workspace = selected || workspaces[0] || null

  useEffect(() => {
    if (!query.isSuccess) return
    if (workspace && workspace.id !== selectedWorkspaceId) {
      setSelectedWorkspace(workspace.id)
    }
    if (!workspace && selectedWorkspaceId) {
      setSelectedWorkspace(null)
    }
  }, [query.isSuccess, selectedWorkspaceId, setSelectedWorkspace, workspace])

  return {
    ...query,
    workspaces,
    workspace,
    workspaceId: workspace?.id || null,
    setSelectedWorkspace,
  }
}
