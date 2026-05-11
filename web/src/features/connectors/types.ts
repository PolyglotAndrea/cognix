export interface ConnectorPlatform {
  platform: string
  display_name: string
  connected: boolean
  credentials: ConnectorCredential[]
}

export interface ConnectorCredential {
  id: string
  platform_username: string
  platform_user_id: string
  scopes: string
  workspace_id?: string | null
  created_at?: string | null
  token_expires_at?: string | null
}

export interface ConnectorTool {
  name: string
  original_name: string
  platform: string
  display_name: string
  description: string
  parameters: Record<string, any>
  access_level: 'read' | 'write' | 'dangerous'
  enabled: boolean
  connector_id?: string | null
}
