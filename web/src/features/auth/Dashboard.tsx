import { useQuery } from '@tanstack/react-query'
import { api, billingApi } from '@/shared/api/client'
import { Bot, Clock, Activity, CreditCard } from 'lucide-react'

export default function Dashboard() {
  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: () => api.get('/agents').then((r) => r.data),
  })

  const { data: tasks } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => api.get('/tasks').then((r) => r.data),
  })

  const { data: usage } = useQuery({
    queryKey: ['usage'],
    queryFn: () => billingApi.get('/usage').then((r) => r.data),
  })

  const stats = [
    { label: 'Agents', value: agents?.length || 0, icon: Bot, color: 'bg-blue-500' },
    { label: 'Tasks', value: tasks?.length || 0, icon: Clock, color: 'bg-green-500' },
    { label: 'API Calls', value: usage?.usage?.api_calls || 0, icon: Activity, color: 'bg-purple-500' },
    { label: 'Plan', value: usage?.plan_id || 'free', icon: CreditCard, color: 'bg-orange-500' },
  ]

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h2>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{label}</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
              </div>
              <div className={`${color} p-3 rounded-lg`}>
                <Icon className="w-6 h-6 text-white" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Usage bars */}
      {usage?.usage && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 mb-8">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Monthly Usage</h3>
          <div className="space-y-4">
            {Object.entries(usage.usage).map(([metric, used]) => {
              const limit = usage.limits?.[metric] || 1
              const percent = Math.min((used as number) / limit * 100, 100)
              return (
                <div key={metric}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-600 capitalize">{metric.replace('_', ' ')}</span>
                    <span className="text-gray-900">{used as number} / {limit}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full ${percent > 80 ? 'bg-red-500' : 'bg-indigo-500'}`}
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Recent agents */}
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Agents</h3>
        {agents?.length ? (
          <div className="space-y-3">
            {agents.slice(0, 5).map((agent: any) => (
              <div key={agent.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <p className="font-medium text-gray-900">{agent.name}</p>
                  <p className="text-sm text-gray-500">{agent.model}</p>
                </div>
                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">Active</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-500">No agents yet. Create one to get started.</p>
        )}
      </div>
    </div>
  )
}
