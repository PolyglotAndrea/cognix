import { useQuery } from '@tanstack/react-query'
import { billingApi } from '@/shared/api/client'
import { Check, ExternalLink } from 'lucide-react'

export default function BillingPage() {
  const { data: plans } = useQuery({
    queryKey: ['plans'],
    queryFn: () => billingApi.get('/plans').then((r) => r.data),
  })

  const { data: subscription } = useQuery({
    queryKey: ['subscription'],
    queryFn: () => billingApi.get('/subscription').then((r) => r.data),
  })

  const { data: usage } = useQuery({
    queryKey: ['usage'],
    queryFn: () => billingApi.get('/usage').then((r) => r.data),
  })

  const handleCheckout = async (planId: string) => {
    try {
      const { data } = await billingApi.post('/checkout', { plan_id: planId })
      if (data.checkout_url) {
        window.location.href = data.checkout_url
      }
    } catch (error) {
      console.error('Checkout failed:', error)
    }
  }

  const handlePortal = async () => {
    try {
      const { data } = await billingApi.post('/portal', {
        return_url: window.location.href,
      })
      if (data.portal_url) {
        window.location.href = data.portal_url
      }
    } catch (error) {
      console.error('Portal failed:', error)
    }
  }

  const currentPlan = subscription?.plan?.id || 'free'

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Billing</h2>
        {currentPlan !== 'free' && (
          <button
            onClick={handlePortal}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <ExternalLink className="w-4 h-4" />
            Manage Subscription
          </button>
        )}
      </div>

      {/* Current usage */}
      {usage && (
        <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 mb-8">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Current Usage</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {Object.entries(usage.usage || {}).map(([metric, used]) => {
              const limit = usage.limits?.[metric] || 1
              const percent = Math.min(((used as number) / limit) * 100, 100)
              return (
                <div key={metric}>
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-600 capitalize">{metric.replace('_', ' ')}</span>
                    <span className="text-gray-900 font-medium">{used as number} / {limit}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3">
                    <div
                      className={`h-3 rounded-full transition-all ${
                        percent > 80 ? 'bg-red-500' : percent > 50 ? 'bg-yellow-500' : 'bg-indigo-500'
                      }`}
                      style={{ width: `${percent}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Plans */}
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Plans</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {plans?.map((plan: any) => {
          const isCurrent = plan.id === currentPlan
          const isEnterprise = plan.id === 'enterprise'

          return (
            <div
              key={plan.id}
              className={`bg-white rounded-xl p-6 shadow-sm border-2 transition-colors ${
                isCurrent ? 'border-indigo-500' : 'border-gray-100 hover:border-gray-200'
              }`}
            >
              {isCurrent && (
                <span className="inline-block px-2 py-1 bg-indigo-100 text-indigo-700 text-xs rounded-full mb-4">
                  Current Plan
                </span>
              )}
              <h4 className="text-xl font-bold text-gray-900">{plan.name}</h4>
              <div className="mt-2 mb-6">
                {isEnterprise ? (
                  <p className="text-2xl font-bold text-gray-900">Custom</p>
                ) : (
                  <>
                    <span className="text-3xl font-bold text-gray-900">${plan.price_monthly}</span>
                    <span className="text-gray-500">/month</span>
                  </>
                )}
              </div>

              <ul className="space-y-3 mb-6">
                <li className="flex items-center gap-2 text-sm text-gray-600">
                  <Check className="w-4 h-4 text-green-500" />
                  {plan.limits.max_agents} agents
                </li>
                <li className="flex items-center gap-2 text-sm text-gray-600">
                  <Check className="w-4 h-4 text-green-500" />
                  {plan.limits.api_calls_monthly.toLocaleString()} API calls/mo
                </li>
                <li className="flex items-center gap-2 text-sm text-gray-600">
                  <Check className="w-4 h-4 text-green-500" />
                  {plan.limits.tokens_monthly.toLocaleString()} tokens/mo
                </li>
                {plan.features.orchestration && (
                  <li className="flex items-center gap-2 text-sm text-gray-600">
                    <Check className="w-4 h-4 text-green-500" />
                    Multi-agent orchestration
                  </li>
                )}
                {plan.features.workflow_builder && (
                  <li className="flex items-center gap-2 text-sm text-gray-600">
                    <Check className="w-4 h-4 text-green-500" />
                    Workflow builder
                  </li>
                )}
              </ul>

              {!isCurrent && (
                <button
                  onClick={() => isEnterprise ? null : handleCheckout(plan.id)}
                  className={`w-full py-2 rounded-lg transition-colors ${
                    isEnterprise
                      ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                      : 'bg-indigo-600 text-white hover:bg-indigo-700'
                  }`}
                >
                  {isEnterprise ? 'Contact Sales' : 'Upgrade'}
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
