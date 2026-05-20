import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/features/auth/store'
import { useWorkspaceStore } from './store'

export interface WorkspaceInfo {
  id: string
  name: string
  path: string
  description?: string
}

export function useCurrentWorkspace() {
  const userId = useAuthStore((s) => s.user?.id || null)
  const selectedWorkspaceId = useWorkspaceStore((s) => s.selectedWorkspaceId)
  const selectedWorkspaceUserId = useWorkspaceStore((s) => s.selectedWorkspaceUserId)
  const setSelectedWorkspace = useWorkspaceStore((s) => s.setSelectedWorkspace)
  const setWorkspaceOwner = useWorkspaceStore((s) => s.setWorkspaceOwner)

  const query = useQuery<WorkspaceInfo[]>({
    queryKey: ['workspaces', userId],
    queryFn: () => api.get('/workspaces').then((r) => r.data),
    enabled: !!userId,
  })

  const workspaces = query.data || []
  const selected =
    selectedWorkspaceUserId === userId
      ? workspaces.find((workspace) => workspace.id === selectedWorkspaceId)
      : null
  const workspace = selected || workspaces[0] || null

  useEffect(() => {
    if (!query.isSuccess) return
    if (selectedWorkspaceUserId !== userId) {
      setWorkspaceOwner(userId)
      setSelectedWorkspace(workspace?.id || null)
      return
    }
    if (workspace && workspace.id !== selectedWorkspaceId) {
      setSelectedWorkspace(workspace.id)
    }
    if (!workspace && selectedWorkspaceId) {
      setSelectedWorkspace(null)
    }
  }, [
    query.isSuccess,
    selectedWorkspaceId,
    selectedWorkspaceUserId,
    setSelectedWorkspace,
    setWorkspaceOwner,
    userId,
    workspace,
  ])

  return {
    ...query,
    workspaces,
    workspace,
    workspaceId: workspace?.id || null,
    setSelectedWorkspace,
  }
}
