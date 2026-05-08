import { create } from 'zustand'

export interface ToolResult {
  id: string
  name: string
  args?: Record<string, unknown>
  result: unknown
  timestamp: number
}

export interface LogEntry {
  id: string
  level: 'info' | 'warn' | 'error'
  message: string
  timestamp: number
}

interface WorkspaceState {
  selectedAgentId: string | null
  rightPanelTab: 'tasks' | 'files' | 'events' | 'results' | 'logs' | 'json'
  rightPanelOpen: boolean
  toolResults: ToolResult[]
  executionLogs: LogEntry[]
  setSelectedAgent: (id: string | null) => void
  setRightPanelTab: (tab: 'tasks' | 'files' | 'events' | 'results' | 'logs' | 'json') => void
  addToolResult: (result: ToolResult) => void
  addLog: (log: LogEntry) => void
  clearResults: () => void
  toggleRightPanel: () => void
}

let _id = 0
const uid = () => String(++_id)

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedAgentId: null,
  rightPanelTab: 'tasks',
  rightPanelOpen: true,
  toolResults: [],
  executionLogs: [],
  setSelectedAgent: (id) => set({ selectedAgentId: id }),
  setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
  addToolResult: (result) =>
    set((s) => ({ toolResults: [...s.toolResults, { ...result, id: result.id || uid() }] })),
  addLog: (log) =>
    set((s) => ({ executionLogs: [...s.executionLogs, { ...log, id: log.id || uid() }] })),
  clearResults: () => set({ toolResults: [], executionLogs: [] }),
  toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
}))
