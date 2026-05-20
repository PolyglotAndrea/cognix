import { Brain, Bot, Wrench, Zap } from 'lucide-react'
import { Panel, PanelBody, PanelHeader } from '@/shared/ui'
import type { DragHandleProps } from './types'

export function LeftPanel({ dragHandleProps }: { dragHandleProps?: DragHandleProps }) {
  return (
    <Panel className="w-80 shrink-0 border-r border-border bg-card h-full">
      <PanelHeader dragHandleProps={dragHandleProps} className="bg-muted/30">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" />
          <span className="text-xs font-bold uppercase tracking-widest text-foreground">Workspace Guide</span>
        </div>
      </PanelHeader>

      <PanelBody className="scrollbar-hide">
        {/* Clean always-visible guide — no developer toggles */}
        <div className="p-5">
          <div className="rounded-2xl border border-border bg-muted/20 p-4">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                <Zap className="h-5 w-5 text-primary" />
              </div>
              <div>
                <div className="text-sm font-black text-foreground">Goal-driven workspace</div>
                <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
                  Internal workers stay hidden
                </div>
              </div>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              Describe the outcome you want in the chat. Cognix will answer directly, ask
              clarifying questions, or spin up workers as needed — all managed automatically.
            </p>
            <div className="mt-4 grid gap-2 text-xs">
              <GuideItem icon={Brain} label="Understands intent" />
              <GuideItem icon={Wrench} label="Selects internal capabilities" />
              <GuideItem icon={Bot} label="Creates workers only when needed" />
            </div>
          </div>
        </div>
      </PanelBody>
    </Panel>
  )
}

function GuideItem({ icon: Icon, label }: { icon: typeof Bot; label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-border bg-background/70 px-3 py-2 text-muted-foreground">
      <Icon className="h-3.5 w-3.5 text-primary" />
      <span className="font-bold">{label}</span>
    </div>
  )
}
