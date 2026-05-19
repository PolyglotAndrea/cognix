import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Sparkles, ArrowRight, Check } from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

const STEPS = ['purpose', 'ready'] as const
type Step = (typeof STEPS)[number]

export function OnboardingWizard({
  workspaceId,
  onComplete,
}: {
  workspaceId: string
  onComplete: () => void
}) {
  const [step, setStep] = useState<Step>('purpose')
  const [purpose, setPurpose] = useState('')

  const completeMutation = useMutation({
    mutationFn: async () => {
      await api.patch(`/workspaces/${workspaceId}/settings`, {
        onboarding_completed: true,
        ui_mode: 'simple',
        context: purpose ? { purpose } : undefined,
      })
    },
    onSuccess: onComplete,
  })

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="max-w-lg w-full space-y-8">
        <div className="text-center space-y-3">
          <div className="inline-flex p-3 rounded-xl bg-primary/10">
            <Sparkles className="h-8 w-8 text-primary" />
          </div>
          <h1 className="text-2xl font-bold text-foreground">Welcome to Cognix</h1>
          <p className="text-sm text-muted-foreground">
            A few words about what you want to build
          </p>
        </div>

        <div className="space-y-6">
          {step === 'purpose' && (
            <div className="space-y-4">
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                  What will you use Cognix for?
                </span>
                <textarea
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  placeholder="e.g. Automate data pipelines, build an AI assistant, manage project tasks..."
                  className={cn(
                    'mt-2 w-full bg-background border border-border rounded-xl p-4 text-sm resize-none h-28',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent'
                  )}
                />
              </label>
              <button
                onClick={() => setStep('ready')}
                className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
              >
                Continue <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          )}

          {step === 'ready' && (
            <div className="space-y-4">
              <div className="border border-border rounded-xl p-6 text-center space-y-3">
                <Check className="h-8 w-8 text-emerald-500 mx-auto" />
                <p className="text-sm text-muted-foreground">
                  {purpose
                    ? `Great! Cognix will help you with: ${purpose}`
                    : "You're all set to start using Cognix."}
                </p>
              </div>
              <button
                onClick={() => completeMutation.mutate()}
                disabled={completeMutation.isPending}
                className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {completeMutation.isPending ? 'Setting up...' : 'Get Started'}
                <Sparkles className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>

        <div className="flex justify-center gap-2">
          {STEPS.map((s, i) => (
            <div
              key={s}
              className={cn(
                'w-2 h-2 rounded-full transition-colors',
                i <= STEPS.indexOf(step) ? 'bg-primary' : 'bg-border'
              )}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
