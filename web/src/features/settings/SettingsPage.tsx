import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi } from '@/shared/api/client'
import { Key, Trash2, Plus, Copy, Check } from 'lucide-react'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [keyName, setKeyName] = useState('')
  const [copiedKey, setCopiedKey] = useState<string | null>(null)

  const { data: apiKeys } = useQuery({
    queryKey: ['api-keys'],
    queryFn: () => authApi.get('/api-keys').then((r) => r.data),
  })

  const createKeyMutation = useMutation({
    mutationFn: (name: string) => authApi.post('/api-keys', { name }),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      setKeyName('')
      // Auto-copy the new key
      if (response.data.key) {
        navigator.clipboard.writeText(response.data.key)
        setCopiedKey(response.data.id)
        setTimeout(() => setCopiedKey(null), 3000)
      }
    },
  })

  const deleteKeyMutation = useMutation({
    mutationFn: (id: string) => authApi.delete(`/api-keys/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['api-keys'] }),
  })

  const copyKey = (key: string) => {
    navigator.clipboard.writeText(key)
    setCopiedKey(key)
    setTimeout(() => setCopiedKey(null), 2000)
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Settings</h2>

      {/* API Keys section */}
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">API Keys</h3>
            <p className="text-sm text-gray-500 mt-1">
              Use API keys to authenticate programmatic access
            </p>
          </div>
        </div>

        {/* Create key form */}
        <div className="flex gap-4 mb-6">
          <input
            type="text"
            placeholder="Key name (e.g., CI/CD, Script)"
            value={keyName}
            onChange={(e) => setKeyName(e.target.value)}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          <button
            onClick={() => keyName && createKeyMutation.mutate(keyName)}
            disabled={!keyName || createKeyMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <Plus className="w-4 h-4" />
            {createKeyMutation.isPending ? 'Creating...' : 'Create Key'}
          </button>
        </div>

        {createKeyMutation.data?.data?.key && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
            <p className="text-sm text-green-800 font-medium mb-2">
              API Key created! Copy it now - it won't be shown again.
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-white px-3 py-2 rounded text-sm font-mono text-gray-900 border">
                {createKeyMutation.data.data.key}
              </code>
              <button
                onClick={() => copyKey(createKeyMutation.data!.data.key)}
                className="px-3 py-2 bg-green-600 text-white rounded hover:bg-green-700"
              >
                {copiedKey === createKeyMutation.data.data.id ? (
                  <Check className="w-4 h-4" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
        )}

        {/* Key list */}
        {apiKeys?.length ? (
          <div className="space-y-3">
            {apiKeys.map((key: any) => (
              <div
                key={key.id}
                className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <Key className="w-4 h-4 text-gray-400" />
                  <div>
                    <p className="font-medium text-gray-900">{key.name}</p>
                    <p className="text-sm text-gray-500 font-mono">{key.prefix}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  {key.last_used_at && (
                    <span className="text-xs text-gray-500">
                      Last used: {new Date(key.last_used_at).toLocaleDateString()}
                    </span>
                  )}
                  <button
                    onClick={() => deleteKeyMutation.mutate(key.id)}
                    className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-center text-gray-500 py-8">No API keys yet</p>
        )}
      </div>
    </div>
  )
}
