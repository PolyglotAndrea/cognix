import { create } from 'zustand'
import { persist } from 'zustand/middleware'

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

type RightPanelTab =
  | 'approvals'
  | 'tasks'
  | 'apps'
  | 'files'
  | 'events'
  | 'results'
  | 'artifacts'
  | 'playbooks'
  | 'policy'
  | 'audit'
  | 'bots'
  | 'runtime'
  | 'logs'
  | 'json'

interface WorkspaceState {
  selectedWorkspaceId: string | null
  selectedWorkspaceUserId: string | null
  selectedAgentId: string | null
  rightPanelTab: RightPanelTab
  rightPanelOpen: boolean
  inputMode: 'plan' | 'chat'
  toolResults: ToolResult[]
  executionLogs: LogEntry[]
  setSelectedWorkspace: (id: string | null) => void
  setSelectedAgent: (id: string | null) => void
  setRightPanelTab: (tab: RightPanelTab) => void
  setRightPanelOpen: (open: boolean) => void
  setInputMode: (mode: 'plan' | 'chat') => void
  addToolResult: (result: ToolResult) => void
  addLog: (log: LogEntry) => void
  clearResults: () => void
  toggleRightPanel: () => void
  setWorkspaceOwner: (userId: string | null) => void
}

const uid = () => crypto.randomUUID()

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      selectedWorkspaceId: null,
      selectedWorkspaceUserId: null,
      selectedAgentId: null,
      rightPanelTab: 'artifacts',
      rightPanelOpen: true,
      inputMode: 'plan',
      toolResults: [],
      executionLogs: [],
      setSelectedWorkspace: (id) =>
        set({ selectedWorkspaceId: id, selectedAgentId: null, toolResults: [], executionLogs: [] }),
      setWorkspaceOwner: (userId) => set({ selectedWorkspaceUserId: userId }),
      setSelectedAgent: (id) => set({ selectedAgentId: id }),
      setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
      setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
      setInputMode: (mode) => set({ inputMode: mode }),
      addToolResult: (result) =>
        set((s) => ({ toolResults: [...s.toolResults, { ...result, id: result.id || uid() }] })),
      addLog: (log) =>
        set((s) => ({ executionLogs: [...s.executionLogs, { ...log, id: log.id || uid() }] })),
      clearResults: () => set({ toolResults: [], executionLogs: [] }),
      toggleRightPanel: () => set((s) => ({ rightPanelOpen: !s.rightPanelOpen })),
    }),
    {
      name: 'cognix-workspace-ui',
      partialize: (state) => ({
        selectedWorkspaceId: state.selectedWorkspaceId,
        selectedWorkspaceUserId: state.selectedWorkspaceUserId,
        rightPanelTab: state.rightPanelTab,
        rightPanelOpen: state.rightPanelOpen,
        inputMode: state.inputMode,
      }),
    }
  )
)
