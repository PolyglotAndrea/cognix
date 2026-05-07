import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/lib/cn'

const badgeVariants = cva('inline-flex items-center rounded-lg px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider', {
  variants: {
    variant: {
      default: 'bg-muted text-muted-foreground border border-border',
      success: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20',
      warning: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20',
      error: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20',
      info: 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-500/20',
      indigo: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20',
      primary: 'bg-primary/10 text-primary border border-primary/20',
    },
  },
  defaultVariants: {
    variant: 'default',
  },
})

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
