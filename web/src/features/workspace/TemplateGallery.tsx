import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Zap, BarChart3, Headphones, Workflow } from 'lucide-react'
import { api } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'

const TEMPLATES = [
  {
    id: 'social',
    name: 'Social Media Manager',
    description: 'Schedule posts, analyze engagement, manage replies across platforms.',
    icon: Zap,
    color: 'text-blue-500',
    bg: 'bg-blue-500/10',
    skills: ['web_search', 'social_posting'],
    model: 'gpt-4o',
  },
  {
    id: 'data',
    name: 'Data Analyst',
    description: 'Process datasets, generate reports, and visualize trends.',
    icon: BarChart3,
    color: 'text-emerald-500',
    bg: 'bg-emerald-500/10',
    skills: ['code_interpreter', 'file_ops'],
    model: 'gpt-4o',
  },
  {
    id: 'support',
    name: 'Customer Support',
    description: 'Answer FAQs, triage tickets, and escalate complex issues.',
    icon: Headphones,
    color: 'text-amber-500',
    bg: 'bg-amber-500/10',
    skills: ['web_search'],
    model: 'gpt-4o',
  },
  {
    id: 'workflow',
    name: 'Custom Workflow',
    description: 'Build multi-agent pipelines with sequential or parallel steps.',
    icon: Workflow,
    color: 'text-purple-500',
    bg: 'bg-purple-500/10',
    skills: [],
    model: 'gpt-4o',
  },
]

interface TemplateGalleryProps {
  workspaceId: string
  onClose: () => void
}

export function TemplateGallery({ workspaceId, onClose }: TemplateGalleryProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const applyMutation = useMutation({
    mutationFn: async (templateId: string) => {
      const template = TEMPLATES.find((t) => t.id === templateId)
      if (!template) return
      await api.patch(`/workspaces/${workspaceId}/settings`, {
        default_model: template.model,
        enabled_skills: template.skills,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace-settings', workspaceId] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-2xl bg-card border border-border rounded-3xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h3 className="text-lg font-bold text-foreground">Workspace Templates</h3>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 grid grid-cols-2 gap-3">
          {TEMPLATES.map((template) => (
            <button
              key={template.id}
              onClick={() => setSelected(template.id)}
              className={cn(
                'text-left rounded-2xl border p-4 transition-all duration-200',
                selected === template.id
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/20'
                  : 'border-border hover:border-primary/30 hover:bg-muted/30',
              )}
            >
              <div className="flex items-center gap-3 mb-2">
                <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center', template.bg)}>
                  <template.icon className={cn('h-4 w-4', template.color)} />
                </div>
                <span className="text-sm font-bold text-foreground">{template.name}</span>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{template.description}</p>
              {template.skills.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {template.skills.map((s) => (
                    <span
                      key={s}
                      className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-border"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </button>
          ))}
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => selected && applyMutation.mutate(selected)}
            disabled={!selected || applyMutation.isPending}
            className={cn(
              'px-6 py-2 rounded-xl text-xs font-bold transition-all active:scale-95',
              selected
                ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                : 'bg-muted text-muted-foreground cursor-not-allowed',
            )}
          >
            {applyMutation.isPending ? 'Applying...' : 'Apply Template'}
          </button>
        </div>
      </div>
    </div>
  )
}
