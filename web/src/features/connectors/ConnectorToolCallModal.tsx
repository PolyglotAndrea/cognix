import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Loader2, Play } from 'lucide-react'
import { api } from '@/shared/api/client'
import { Badge, Button, Input, Modal } from '@/shared/ui'
import type { ConnectorTool } from './types'

export function ConnectorToolCallModal({
  isOpen,
  onClose,
  tool,
  workspaceId,
}: {
  isOpen: boolean
  onClose: () => void
  tool: ConnectorTool
  workspaceId?: string
}) {
  const [args, setArgs] = useState<Record<string, any>>({})
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [approvalId, setApprovalId] = useState<string | null>(null)

  const callMutation = useMutation({
    mutationFn: () => {
      const params = new URLSearchParams()
      if (workspaceId) params.set('workspace_id', workspaceId)
      const qs = params.toString()
      return api
        .post(`/connectors/tools/${tool.name}/call${qs ? `?${qs}` : ''}`, {
          arguments: args,
          permission_mode: 'workspace-write',
          approval_id: approvalId,
        })
        .then((r) => r.data)
    },
    onSuccess: (data) => {
      if (data.approval_required) {
        setApprovalId(data.approval_id)
        setResult(data)
      } else {
        setApprovalId(null)
        setResult(data.result)
      }
      setError(null)
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail || err.message || 'Call failed')
      setResult(null)
    },
  })

  const properties = tool.parameters?.properties || {}
  const required = new Set(tool.parameters?.required || [])

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Test: ${tool.original_name}`} size="lg">
      <div className="space-y-5">
        <div className="flex items-center gap-2">
          <Badge variant="default">{tool.platform}</Badge>
          <Badge variant={tool.access_level === 'read' ? 'success' : tool.access_level === 'write' ? 'warning' : 'error'}>
            {tool.access_level}
          </Badge>
          <span className="text-xs text-muted-foreground">{tool.description}</span>
        </div>

        {/* Dynamic form fields from JSON Schema */}
        {Object.keys(properties).length > 0 && (
          <div className="space-y-3">
            <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Parameters
            </h4>
            {Object.entries(properties).map(([key, schema]: [string, any]) => (
              <FormField
                key={key}
                name={key}
                schema={schema}
                required={required.has(key)}
                value={args[key]}
                onChange={(val) => setArgs((prev) => ({ ...prev, [key]: val }))}
              />
            ))}
          </div>
        )}

        {/* Call button */}
        <Button
          onClick={() => callMutation.mutate()}
          disabled={callMutation.isPending}
          className="gap-2"
        >
          {callMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {approvalId ? 'Execute Approved Call' : 'Execute'}
        </Button>

        {/* Result */}
        {result && (
          <div>
            <h4 className="mb-1 text-[10px] font-bold uppercase tracking-widest text-emerald-500">
              Result
            </h4>
            <pre className="max-h-64 overflow-auto rounded-lg bg-emerald-500/5 p-3 font-mono text-[11px] leading-5 text-foreground whitespace-pre-wrap break-all">
              {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}

        {error && (
          <div>
            <h4 className="mb-1 text-[10px] font-bold uppercase tracking-widest text-rose-500">
              Error
            </h4>
            <pre className="max-h-32 overflow-auto rounded-lg bg-rose-500/5 p-3 font-mono text-[11px] leading-5 text-rose-600 dark:text-rose-300 whitespace-pre-wrap break-all">
              {error}
            </pre>
          </div>
        )}
      </div>
    </Modal>
  )
}

function FormField({
  name,
  schema,
  required,
  value,
  onChange,
}: {
  name: string
  schema: any
  required: boolean
  value: any
  onChange: (val: any) => void
}) {
  const type = schema.type
  const label = schema.description || name

  if (type === 'boolean') {
    return (
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onChange(!value)}
          className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
            value ? 'bg-primary' : 'bg-muted'
          }`}
        >
          <div
            className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
              value ? 'left-[18px]' : 'left-0.5'
            }`}
          />
        </button>
        <span className="text-xs text-foreground">
          {name}
          {required && <span className="text-rose-500 ml-0.5">*</span>}
        </span>
      </div>
    )
  }

  if (type === 'string' && schema.enum) {
    return (
      <div>
        <label className="mb-1 block text-xs font-medium text-foreground">
          {name}
          {required && <span className="text-rose-500 ml-0.5">*</span>}
        </label>
        <select
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-xl border border-border bg-muted px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
        >
          <option value="">Select...</option>
          {schema.enum.map((opt: string) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        {label !== name && <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>}
      </div>
    )
  }

  if (type === 'object' || type === 'array') {
    return (
      <div>
        <label className="mb-1 block text-xs font-medium text-foreground">
          {name}
          {required && <span className="text-rose-500 ml-0.5">*</span>}
        </label>
        <textarea
          value={typeof value === 'string' ? value : value ? JSON.stringify(value, null, 2) : ''}
          onChange={(e) => {
            try {
              onChange(JSON.parse(e.target.value))
            } catch {
              onChange(e.target.value)
            }
          }}
          placeholder={type === 'object' ? '{"key": "value"}' : '[item1, item2]'}
          rows={3}
          className="w-full rounded-xl border border-border bg-muted px-3 py-2 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/20"
        />
        {label !== name && <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>}
      </div>
    )
  }

  // Default: string/number/integer input
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-foreground">
        {name}
        {required && <span className="text-rose-500 ml-0.5">*</span>}
      </label>
      <Input
        type={type === 'integer' || type === 'number' ? 'number' : 'text'}
        value={value ?? ''}
        onChange={(e) => onChange(type === 'integer' || type === 'number' ? Number(e.target.value) : e.target.value)}
        placeholder={schema.default != null ? String(schema.default) : label}
      />
      {label !== name && <p className="mt-0.5 text-[10px] text-muted-foreground">{label}</p>}
    </div>
  )
}
