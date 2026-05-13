import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bot, Plug, Sparkles, ChevronRight, Check } from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

const STEPS = [
  {
    key: 'purpose',
    icon: Bot,
    title: 'What do you want to automate?',
    description: 'Choose a template or start from scratch.',
    options: [
      { label: 'Social Media Management', value: 'social', desc: 'Schedule posts, analyze engagement, manage replies' },
      { label: 'Data Analysis', value: 'data', desc: 'Process datasets, generate reports, visualize trends' },
      { label: 'Customer Support', value: 'support', desc: 'Answer FAQs, triage tickets, escalate issues' },
      { label: 'Custom Workflow', value: 'custom', desc: 'Build your own multi-agent pipeline' },
    ],
  },
  {
    key: 'provider',
    icon: Plug,
    title: 'Connect an AI provider',
    description: 'Bring your own key or use our managed service.',
    options: [
      { label: 'OpenAI', value: 'openai', desc: 'GPT-4o, GPT-4 Turbo, GPT-3.5' },
      { label: 'Anthropic', value: 'anthropic', desc: 'Claude Opus, Sonnet, Haiku' },
      { label: 'Local / Self-hosted', value: 'local', desc: 'Ollama, vLLM, or any OpenAI-compatible API' },
      { label: 'Skip for now', value: 'skip', desc: 'Use echo mode (no real LLM calls)' },
    ],
  },
  {
    key: 'ready',
    icon: Sparkles,
    title: 'Your workspace is ready!',
    description: 'Start chatting with your AI assistant.',
    options: [],
  },
]

interface OnboardingWizardProps {
  workspaceId: string
  onComplete: () => void
}

export function OnboardingWizard({ workspaceId, onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(0)
  const [selections, setSelections] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()

  const completeMutation = useMutation({
    mutationFn: async () => {
      // Save template selection as metadata
      await api.patch(`/workspaces/${workspaceId}/settings`, {
        ui_mode: 'simple',
      })
      await api.post(`/workspaces/${workspaceId}/onboarding/complete`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace-settings', workspaceId] })
      onComplete()
    },
  })

  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  const handleSelect = (value: string) => {
    setSelections((s) => ({ ...s, [current.key]: value }))
  }

  const handleNext = () => {
    if (isLast) {
      completeMutation.mutate()
    } else {
      setStep((s) => s + 1)
    }
  }

  const canProceed = isLast || selections[current.key]

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-background/95 backdrop-blur-xl">
      <div className="w-full max-w-lg mx-4">
        {/* Progress dots */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((s, i) => (
            <div
              key={s.key}
              className={cn(
                'w-2 h-2 rounded-full transition-all duration-300',
                i === step ? 'bg-primary w-6' : i < step ? 'bg-primary/50' : 'bg-muted',
              )}
            />
          ))}
        </div>

        {/* Card */}
        <div className="bg-card border border-border rounded-3xl p-8 shadow-2xl">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
              <current.icon className="h-5 w-5 text-primary" />
            </div>
            <h2 className="text-lg font-bold text-foreground">{current.title}</h2>
          </div>
          <p className="text-sm text-muted-foreground mb-6 ml-[52px]">{current.description}</p>

          {/* Options */}
          {current.options.length > 0 && (
            <div className="space-y-2 mb-6">
              {current.options.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => handleSelect(opt.value)}
                  className={cn(
                    'w-full text-left rounded-xl border p-4 transition-all duration-200',
                    selections[current.key] === opt.value
                      ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                      : 'border-border hover:border-primary/30 hover:bg-muted/50',
                  )}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold text-foreground">{opt.label}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">{opt.desc}</div>
                    </div>
                    {selections[current.key] === opt.value && (
                      <Check className="h-4 w-4 text-primary shrink-0" />
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Ready step */}
          {isLast && (
            <div className="text-center py-6">
              <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 flex items-center justify-center mx-auto mb-4">
                <Sparkles className="h-8 w-8 text-emerald-500" />
              </div>
              <p className="text-sm text-muted-foreground">
                You're all set. Your workspace is configured and ready to go.
              </p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between mt-4">
            {step > 0 && (
              <button
                onClick={() => setStep((s) => s - 1)}
                className="text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
              >
                Back
              </button>
            )}
            <div className="ml-auto">
              <button
                onClick={handleNext}
                disabled={!canProceed || completeMutation.isPending}
                className={cn(
                  'flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold transition-all active:scale-95',
                  canProceed
                    ? 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-lg shadow-primary/20'
                    : 'bg-muted text-muted-foreground cursor-not-allowed',
                )}
              >
                {isLast ? 'Get Started' : 'Continue'}
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Skip link */}
        {!isLast && (
          <button
            onClick={() => setStep(STEPS.length - 1)}
            className="block mx-auto mt-4 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Skip setup
          </button>
        )}
      </div>
    </div>
  )
}
