import { cn } from '@/shared/lib/cn'
import type { ReactNode } from 'react'

interface PanelProps {
  children: ReactNode
  className?: string
}

interface PanelHeaderProps {
  children: ReactNode
  className?: string
}

interface PanelBodyProps {
  children: ReactNode
  className?: string
}

export function Panel({ children, className }: PanelProps) {
  return (
    <div className={cn('flex flex-col bg-card border-border', className)}>
      {children}
    </div>
  )
}

export function PanelHeader({ children, className }: PanelHeaderProps) {
  return (
    <div className={cn('px-6 py-4 border-b border-border flex items-center gap-2', className)}>
      {children}
    </div>
  )
}

export function PanelBody({ children, className }: PanelBodyProps) {
  return (
    <div className={cn('flex-1 overflow-auto scrollbar-hide', className)}>
      {children}
    </div>
  )
}
