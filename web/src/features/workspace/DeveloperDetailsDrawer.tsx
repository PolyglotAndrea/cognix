import { useState } from 'react'
import { X } from 'lucide-react'
import { LeftPanel } from './LeftPanel'
import { RightPanel } from './RightPanel'
import { cn } from '@/shared/lib/cn'

export function DeveloperDetailsDrawer({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const [tab, setTab] = useState<'workers' | 'system'>('system')

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[90]">
      <button
        type="button"
        className="absolute inset-0 bg-black/25 backdrop-blur-[2px]"
        onClick={onClose}
        aria-label="Close developer details"
      />
      <section className="absolute right-0 top-0 flex h-full w-full max-w-5xl flex-col border-l border-border bg-background shadow-2xl">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-5">
          <div>
            <h2 className="text-sm font-black text-foreground">Developer Details</h2>
            <p className="text-[11px] text-muted-foreground">
              Agents, runtime, tasks, policy, audit, MCP, and raw events.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex shrink-0 gap-2 border-b border-border px-5 py-3">
          <DrawerTab active={tab === 'system'} onClick={() => setTab('system')} label="System Panels" />
          <DrawerTab active={tab === 'workers'} onClick={() => setTab('workers')} label="Workers & Agents" />
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === 'system' ? (
            <RightPanel />
          ) : (
            <LeftPanel />
          )}
        </div>
      </section>
    </div>
  )
}

function DrawerTab({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full px-3 py-1.5 text-xs font-bold transition-colors',
        active ? 'bg-foreground text-background' : 'bg-muted text-muted-foreground hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}
