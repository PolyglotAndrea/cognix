import { useRef, useEffect } from 'react'
import {
  Terminal,
  FileJson,
  Wrench,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react'
import { useWorkspaceStore } from './store'
import { Panel, PanelHeader, PanelBody, Badge } from '@/shared/ui'

const TABS = [
  { key: 'results' as const, label: 'Results', icon: Wrench },
  { key: 'logs' as const, label: 'Logs', icon: Terminal },
  { key: 'json' as const, label: 'JSON', icon: FileJson },
]

export function RightPanel() {
  const { rightPanelTab, setRightPanelTab, rightPanelOpen, toggleRightPanel, toolResults, executionLogs } =
    useWorkspaceStore()
  const logsEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (rightPanelTab === 'logs') {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [executionLogs, rightPanelTab])

  if (!rightPanelOpen) {
    return (
      <button
        onClick={toggleRightPanel}
        className="w-10 shrink-0 border-l border-border bg-card flex flex-col items-center py-6 gap-8 hover:bg-muted transition-colors group"
        title="Open output panel"
      >
        <ChevronLeft className="h-5 w-5 text-muted-foreground group-hover:text-foreground transition-colors" />
        <div className="flex flex-col gap-6">
           <Wrench className="h-4 w-4 text-muted-foreground/30" />
           <Terminal className="h-4 w-4 text-muted-foreground/30" />
           <FileJson className="h-4 w-4 text-muted-foreground/30" />
        </div>
      </button>
    )
  }

  return (
    <Panel className="w-80 shrink-0 border-l border-border bg-card">
      <PanelHeader className="justify-between bg-muted/50 backdrop-blur-md px-4 h-14">
        <div className="flex bg-background/50 p-1 rounded-xl border border-border">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setRightPanelTab(tab.key)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all ${
                rightPanelTab === tab.key
                  ? 'bg-primary text-white shadow-lg shadow-primary/20'
                  : 'text-muted-foreground hover:text-foreground hover:bg-background'
              }`}
            >
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          ))}
        </div>
        <button onClick={toggleRightPanel} className="p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all">
          <ChevronRight className="h-4 w-4" />
        </button>
      </PanelHeader>

      <PanelBody className="p-0 scrollbar-hide bg-card">
        {/* Results Tab */}
        {rightPanelTab === 'results' && (
          <div className="p-4 space-y-3">
            {toolResults.length === 0 ? (
              <div className="py-20 text-center">
                 <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                   <Wrench className="h-8 w-8 text-muted-foreground/20" />
                 </div>
                 <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Results</p>
              </div>
            ) : (
              toolResults.map((r) => (
                <ToolResultCard key={r.id} result={r} />
              ))
            )}
          </div>
        )}

        {/* Logs Tab */}
        {rightPanelTab === 'logs' && (
          <div className="p-4 space-y-2 font-mono text-[11px]">
            {executionLogs.length === 0 ? (
              <div className="py-20 text-center">
                 <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                   <Terminal className="h-8 w-8 text-muted-foreground/20" />
                 </div>
                 <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Logs</p>
              </div>
            ) : (
              <div className="bg-muted/30 rounded-2xl p-4 border border-border">
                {executionLogs.map((log) => (
                  <div key={log.id} className="flex items-start gap-3 py-1.5 border-b border-border last:border-0 group">
                    <LogIcon level={log.level} />
                    <span className="text-muted-foreground/30 shrink-0 font-bold">
                      {new Date(log.timestamp).toLocaleTimeString([], { hour12: false })}
                    </span>
                    <span
                      className={`font-medium ${
                        log.level === 'error'
                          ? 'text-rose-500 dark:text-rose-400'
                          : log.level === 'warn'
                            ? 'text-amber-500 dark:text-amber-400'
                            : 'text-foreground/80'
                      }`}
                    >
                      {log.message}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div ref={logsEndRef} />
          </div>
        )}

        {/* JSON Tab */}
        {rightPanelTab === 'json' && (
          <div className="p-4">
            {toolResults.length === 0 ? (
               <div className="py-20 text-center">
                 <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mx-auto mb-4 border border-border">
                   <FileJson className="h-8 w-8 text-muted-foreground/20" />
                 </div>
                 <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">No Data</p>
              </div>
            ) : (
              <div className="relative group">
                <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity">
                   <Badge variant="primary">Raw JSON</Badge>
                </div>
                <pre className="text-[11px] text-emerald-600 dark:text-emerald-400/80 bg-muted/50 rounded-2xl p-5 overflow-auto max-h-[calc(100vh-12rem)] font-mono border border-border scrollbar-hide">
                  {JSON.stringify(toolResults[toolResults.length - 1], null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </PanelBody>
    </Panel>
  )
}

function ToolResultCard({ result }: { result: { name: string; timestamp: number; result: unknown } }) {
  const display =
    typeof result.result === 'string'
      ? result.result
      : JSON.stringify(result.result, null, 2)

  return (
    <div className="bg-muted/30 rounded-2xl p-4 border border-border hover:border-primary/20 transition-all group overflow-hidden relative">
      <div className="absolute top-0 right-0 w-24 h-24 bg-primary/5 blur-2xl -z-10 rounded-full" />
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 bg-primary/10 rounded-lg flex items-center justify-center border border-primary/20">
            <Wrench className="h-3.5 w-3.5 text-primary" />
          </div>
          <span className="text-xs font-bold text-foreground tracking-tight">{result.name}</span>
        </div>
        <Badge variant="success">Completed</Badge>
      </div>
      <pre className="text-[11px] text-muted-foreground bg-background/50 rounded-xl p-3 overflow-auto max-h-40 font-mono border border-border leading-relaxed">
        {display.length > 500 ? display.slice(0, 500) + '...' : display}
      </pre>
      <div className="mt-3 flex items-center justify-between">
         <span className="text-[9px] text-muted-foreground/40 font-bold uppercase tracking-widest">
            {new Date(result.timestamp).toLocaleTimeString()}
         </span>
         <button className="text-[10px] text-primary font-bold hover:underline opacity-0 group-hover:opacity-100 transition-opacity">
            Copy Result
         </button>
      </div>
    </div>
  )
}

function LogIcon({ level }: { level: string }) {
  if (level === 'error') return <div className="w-2 h-2 rounded-full bg-rose-500 mt-1.5 shadow-sm shadow-rose-500/50" />
  if (level === 'warn') return <div className="w-2 h-2 rounded-full bg-amber-500 mt-1.5 shadow-sm shadow-amber-500/50" />
  return <div className="w-2 h-2 rounded-full bg-sky-500 mt-1.5 shadow-sm shadow-sky-500/50" />
}
