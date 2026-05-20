import { useState } from 'react'
import { SlidersHorizontal } from 'lucide-react'
import { TopBar } from './TopBar'
import { SourcesPanel } from './SourcesPanel'
import { SimpleMode } from './SimpleMode'
import { StudioPanel } from './StudioPanel'
import { DeveloperDetailsDrawer } from './DeveloperDetailsDrawer'
import { useWorkspaceStore } from './store'

export function NotebookWorkspace({
  workspaceId,
  onSwitchToAdvanced,
}: {
  workspaceId: string
  onSwitchToAdvanced: () => void
}) {
  const [developerOpen, setDeveloperOpen] = useState(false)
  const [requestedIntent, setRequestedIntent] = useState<{ id: number; text: string; autoSubmit?: boolean } | null>(null)
  const notebookSources = useWorkspaceStore((state) => state.notebookSources)

  const handleStudioIntent = (intent: string) => {
    const sourceLabel =
      notebookSources.length > 0
        ? ` Use the ${notebookSources.length} selected source${notebookSources.length > 1 ? 's' : ''}.`
        : ' Ask me for sources if more context is needed.'
    setRequestedIntent({
      id: Date.now(),
      text: `${intent}${sourceLabel}`,
      autoSubmit: false,
    })
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#eef0fb] text-foreground">
      <TopBar />

      <main className="grid min-h-0 flex-1 grid-cols-[minmax(260px,25vw)_minmax(420px,1fr)_minmax(300px,25vw)] gap-3 p-3">
        <SourcesPanel workspaceId={workspaceId} />

        <section className="flex min-w-0 flex-col overflow-hidden rounded-[1.35rem] border border-border/70 bg-card shadow-sm">
          <div className="flex h-14 shrink-0 items-center justify-between border-b border-border/70 px-5">
            <div>
              <h1 className="text-sm font-semibold text-foreground">Conversation</h1>
              <p className="text-[11px] text-muted-foreground">
                Ask a question or create something from selected sources.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setDeveloperOpen(true)}
                className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-background text-muted-foreground hover:text-foreground"
                title="Developer details"
              >
                <SlidersHorizontal className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1">
            <SimpleMode
              workspaceId={workspaceId}
              onSwitchToAdvanced={onSwitchToAdvanced}
              requestedIntent={requestedIntent}
              embedded
            />
          </div>
        </section>

        <StudioPanel workspaceId={workspaceId} onCreateFromStudio={handleStudioIntent} />
      </main>

      <DeveloperDetailsDrawer
        open={developerOpen}
        onClose={() => setDeveloperOpen(false)}
      />
    </div>
  )
}
