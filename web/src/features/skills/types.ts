export interface WorkspaceInfo {
  id: string
  name: string
}

export interface WorkspaceSkill {
  name: string
  version: string
  description?: string
  author?: string
  tags?: string
  tools: string[]
  enabled: boolean
}

export interface MCPServer {
  id: string
  name: string
  command: string
  args: string[]
  env: Record<string, string>
  enabled: boolean
}

export interface MCPServerStatus {
  server_id: string
  name: string
  enabled: boolean
  status: string
  tool_count: number
  error?: string
  stderr?: string
  checked_at?: number
}

export interface MCPTool {
  name: string
  original_name: string
  description: string
  parameters: Record<string, any>
  access_level: 'read' | 'write' | 'dangerous'
}
