import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/shared/api/client'
import { Plus, Bot, Trash2, MessageSquare } from 'lucide-react'

export default function AgentList() {
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [model, setModel] = useState('gpt-4o')

  const { data: agents, isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.get('/agents').then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; model: string }) =>
      api.post('/agents', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setShowCreate(false)
      setName('')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/agents/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Agents</h2>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Agent
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 mb-6">
          <h3 className="text-lg font-semibold mb-4">New Agent</h3>
          <div className="flex gap-4">
            <input
              type="text"
              placeholder="Agent name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            />
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500"
            >
              <option value="gpt-4o">GPT-4o</option>
              <option value="gpt-4o-mini">GPT-4o Mini</option>
              <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
              <option value="echo">Echo (test)</option>
            </select>
            <button
              onClick={() => createMutation.mutate({ name, model })}
              disabled={!name || createMutation.isPending}
              className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
            >
              {createMutation.isPending ? 'Creating...' : 'Create'}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Agent list */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : agents?.length ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {agents.map((agent: any) => (
            <div key={agent.id} className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center">
                    <Bot className="w-5 h-5 text-indigo-600" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{agent.name}</h3>
                    <p className="text-sm text-gray-500">{agent.model}</p>
                  </div>
                </div>
                <button
                  onClick={() => deleteMutation.mutate(agent.id)}
                  className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
              <p className="text-sm text-gray-600 mb-4 line-clamp-2">
                {agent.description || 'No description'}
              </p>
              <div className="flex gap-2">
                <Link
                  to={`/agents/${agent.id}`}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-indigo-50 text-indigo-600 rounded-lg hover:bg-indigo-100 transition-colors text-sm"
                >
                  <MessageSquare className="w-4 h-4" />
                  Chat
                </Link>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 bg-white rounded-xl border border-gray-100">
          <Bot className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">No agents yet</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 text-indigo-600 hover:text-indigo-700 font-medium"
          >
            Create your first agent
          </button>
        </div>
      )}
    </div>
  )
}
