import { useQuery } from '@tanstack/react-query'
import { OnboardingWizard } from './OnboardingWizard'
import { NotebookWorkspace } from './NotebookWorkspace'
import { api } from '@/shared/api/client'
import { useCurrentWorkspace } from './useCurrentWorkspace'

export function Workspace() {
  const { workspaceId } = useCurrentWorkspace()

  const { data: settings, refetch: refetchSettings } = useQuery({
    queryKey: ['workspace-settings', workspaceId],
    queryFn: () => api.get(`/workspaces/${workspaceId}/settings`).then((r) => r.data),
    enabled: !!workspaceId,
  })

  const onboardingCompleted = settings?.onboarding_completed ?? false

  if (workspaceId && !onboardingCompleted) {
    return (
      <OnboardingWizard
        workspaceId={workspaceId}
        onComplete={() => refetchSettings()}
      />
    )
  }

  if (!workspaceId) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#eef0fb] text-sm font-semibold text-muted-foreground">
        Select or create a workspace to continue.
      </div>
    )
  }

  return (
    <NotebookWorkspace
      workspaceId={workspaceId}
      onSwitchToAdvanced={() => refetchSettings()}
    />
  )
}
