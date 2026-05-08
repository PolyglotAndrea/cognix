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
      <div className="flex items-center justify-between mb-8">
        <h2 className="text-2xl font-bold text-foreground tracking-tight">Billing & Subscriptions</h2>
        {currentPlan !== 'free' && (
          <button
            onClick={handlePortal}
            className="flex items-center gap-2 px-4 py-2 bg-muted border border-border rounded-xl hover:bg-muted/80 text-foreground transition-all active:scale-95 font-semibold text-sm shadow-sm"
          >
            <ExternalLink className="w-4 h-4" />
            Manage Subscription
          </button>
        )}
      </div>

      {/* Current usage */}
      {usage && (
        <div className="bg-muted/30 rounded-2xl p-8 border border-border mb-10 backdrop-blur-sm">
          <h3 className="text-lg font-bold text-foreground mb-6 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-primary" />
            Current Resource Usage
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {Object.entries(usage.usage || {}).map(([metric, used]) => {
              const limit = usage.limits?.[metric] || 1
              const percent = Math.min(((used as number) / limit) * 100, 100)
              return (
                <div key={metric}>
                  <div className="flex justify-between text-xs font-bold mb-3">
                    <span className="text-muted-foreground uppercase tracking-widest">{metric.replace('_', ' ')}</span>
                    <span className="text-foreground">{used as number} / {limit}</span>
                  </div>
                  <div className="w-full bg-background/50 rounded-full h-2.5 border border-border overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        percent > 80 ? 'bg-rose-500' : percent > 50 ? 'bg-amber-500' : 'bg-primary'
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
      <h3 className="text-lg font-bold text-foreground mb-6 uppercase tracking-widest text-[10px]">Select a Plan</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {plans?.map((plan: any) => {
          const isCurrent = plan.id === currentPlan
          const isEnterprise = plan.id === 'enterprise'

          return (
            <div
              key={plan.id}
              className={`bg-card rounded-2xl p-6 border-2 transition-all duration-300 relative overflow-hidden group ${
                isCurrent 
                  ? 'border-primary shadow-xl shadow-primary/10' 
                  : 'border-border hover:border-primary/40 hover:shadow-lg'
              }`}
            >
              {isCurrent && (
                <div className="absolute top-0 right-0">
                  <div className="bg-primary text-white text-[10px] font-bold px-3 py-1 rounded-bl-xl uppercase tracking-wider">
                    Active
                  </div>
                </div>
              )}
              <h4 className="text-xl font-bold text-foreground mb-1">{plan.name}</h4>
              <div className="mt-4 mb-8">
                {isEnterprise ? (
                  <p className="text-2xl font-extrabold text-foreground tracking-tight">Custom Pricing</p>
                ) : (
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-extrabold text-foreground tracking-tight">${plan.price_monthly}</span>
                    <span className="text-muted-foreground text-xs font-medium">/month</span>
                  </div>
                )}
              </div>

              <ul className="space-y-4 mb-8">
                {[
                  { label: `${plan.limits.max_agents} agents` },
                  { label: `${plan.limits.api_calls_monthly.toLocaleString()} API calls/mo` },
                  { label: `${plan.limits.tokens_monthly.toLocaleString()} tokens/mo` },
                  { label: 'Multi-agent orchestration', enabled: plan.features.orchestration },
                  { label: 'Workflow builder', enabled: plan.features.workflow_builder },
                ].map((feature, i) => (
                  feature.enabled !== false && (
                    <li key={i} className="flex items-center gap-3 text-xs font-medium text-foreground/80">
                      <div className="shrink-0 w-5 h-5 rounded-full bg-emerald-500/10 flex items-center justify-center">
                        <Check className="w-3 h-3 text-emerald-500" />
                      </div>
                      {feature.label}
                    </li>
                  )
                ))}
              </ul>

              {!isCurrent && (
                <button
                  onClick={() => isEnterprise ? null : handleCheckout(plan.id)}
                  className={`w-full py-3 rounded-xl font-bold text-xs uppercase tracking-widest transition-all active:scale-95 ${
                    isEnterprise
                      ? 'bg-muted text-muted-foreground hover:bg-muted/80'
                      : 'bg-primary text-white hover:opacity-90 shadow-lg shadow-primary/20'
                  }`}
                >
                  {isEnterprise ? 'Contact Sales' : 'Upgrade Now'}
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
