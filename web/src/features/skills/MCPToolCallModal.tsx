import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Play, Loader2 } from 'lucide-react'
import { api } from '@/shared/api/client'
import { Badge, Button, Input, Modal } from '@/shared/ui'
import type { MCPTool } from './types'

interface Props {
  isOpen: boolean
  onClose: () => void
  tool: MCPTool
  workspaceId: string
  serverId: string
}

const accessBadge: Record<string, 'success' | 'warning' | 'error'> = {
  read: 'success',
  write: 'warning',
  dangerous: 'error',
}

export function MCPToolCallModal({ isOpen, onClose, tool, workspaceId, serverId }: Props) {
  const schema = tool.parameters || {}
  const properties: Record<string, any> = schema.properties || {}
  const required: string[] = schema.required || []
  const fieldNames = Object.keys(properties)

  const [values, setValues] = useState<Record<string, any>>({})
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const callMutation = useMutation({
    mutationFn: () =>
      api
        .post(
          `/workspaces/${workspaceId}/mcp/servers/${serverId}/tools/${tool.original_name}/call`,
          { arguments: values, permission_mode: 'workspace-write' },
        )
        .then((r) => r.data),
    onSuccess: (data) => {
      setResult(typeof data.result === 'string' ? data.result : JSON.stringify(data.result, null, 2))
      setError(null)
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail || err.message || 'Call failed')
      setResult(null)
    },
  })

  function setValue(key: string, value: any) {
    setValues((prev) => ({ ...prev, [key]: value }))
  }

  function handleClose() {
    setResult(null)
    setError(null)
    onClose()
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={tool.original_name} size="lg">
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={accessBadge[tool.access_level] || 'default'}>{tool.access_level}</Badge>
          {tool.description && (
            <p className="text-sm text-muted-foreground">{tool.description}</p>
          )}
        </div>

        {fieldNames.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Parameters
            </h4>
            {fieldNames.map((key) => {
              const prop = properties[key]
              const isRequired = required.includes(key)
              return (
                <FormField
                  key={key}
                  name={key}
                  prop={prop}
                  required={isRequired}
                  value={values[key]}
                  onChange={(v) => setValue(key, v)}
                />
              )
            })}
          </div>
        )}

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
          {callMutation.isPending ? 'Calling...' : 'Call Tool'}
        </Button>

        {result !== null && (
          <div className="space-y-1">
            <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Result
            </h4>
            <pre className="max-h-72 overflow-auto rounded-xl border border-border bg-muted p-4 font-mono text-xs leading-5 text-foreground whitespace-pre-wrap break-all">
              {result}
            </pre>
          </div>
        )}

        {error !== null && (
          <div className="space-y-1">
            <h4 className="text-[10px] font-bold uppercase tracking-widest text-rose-500">
              Error
            </h4>
            <pre className="max-h-48 overflow-auto rounded-xl border border-rose-500/20 bg-rose-500/5 p-4 font-mono text-xs leading-5 text-rose-600 dark:text-rose-300 whitespace-pre-wrap break-all">
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
  prop,
  required,
  value,
  onChange,
}: {
  name: string
  prop: any
  required: boolean
  value: any
  onChange: (v: any) => void
}) {
  const type = prop.type || 'string'
  const label = prop.title || name
  const description = prop.description

  if (type === 'boolean') {
    return (
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border px-4 py-3">
        <div>
          <div className="text-sm font-medium text-foreground">
            {label}
            {required && <span className="ml-1 text-rose-500">*</span>}
          </div>
          {description && <p className="text-[11px] text-muted-foreground">{description}</p>}
        </div>
        <button
          type="button"
          onClick={() => onChange(!value)}
          className={`relative h-6 w-11 shrink-0 rounded-full border transition-colors ${
            value ? 'border-primary/30 bg-primary' : 'border-border bg-muted'
          }`}
        >
          <span
            className={`absolute top-0.5 h-[18px] w-[18px] rounded-full bg-white shadow transition-transform ${
              value ? 'translate-x-5' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>
    )
  }

  if (type === 'object' || type === 'array') {
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-foreground">
          {label}
          {required && <span className="ml-1 text-rose-500">*</span>}
        </label>
        {description && <p className="text-[11px] text-muted-foreground">{description}</p>}
        <textarea
          value={typeof value === 'string' ? value : value != null ? JSON.stringify(value, null, 2) : ''}
          onChange={(e) => {
            try {
              onChange(JSON.parse(e.target.value))
            } catch {
              onChange(e.target.value)
            }
          }}
          placeholder={type === 'array' ? '[ ]' : '{ }'}
          rows={4}
          className="w-full rounded-xl border border-border bg-muted px-4 py-3 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>
    )
  }

  // string, number, integer
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-foreground">
        {label}
        {required && <span className="ml-1 text-rose-500">*</span>}
        {prop.enum && (
          <span className="ml-2 text-[10px] text-muted-foreground">
            ({prop.enum.join(' | ')})
          </span>
        )}
      </label>
      {description && <p className="text-[11px] text-muted-foreground">{description}</p>}
      {prop.enum ? (
        <select
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-xl border border-border bg-muted px-4 py-3 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="">Select...</option>
          {prop.enum.map((opt: string) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : (
        <Input
          type={type === 'number' || type === 'integer' ? 'number' : 'text'}
          value={value ?? ''}
          onChange={(e) => {
            const raw = e.target.value
            if (type === 'number' || type === 'integer') {
              onChange(raw === '' ? undefined : Number(raw))
            } else {
              onChange(raw)
            }
          }}
          placeholder={prop.default != null ? String(prop.default) : name}
        />
      )}
    </div>
  )
}
