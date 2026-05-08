import { cn } from '@/shared/lib/cn'
import type { ReactNode } from 'react'
import { GripVertical } from 'lucide-react'

interface PanelProps {
  children: ReactNode
  className?: string
}

interface PanelHeaderProps {
  children: ReactNode
  className?: string
  dragHandleProps?: any
}

interface PanelBodyProps {
  children: ReactNode
  className?: string
}

export function Panel({ children, className }: PanelProps) {
  return (
    <div className={cn('flex flex-col bg-card border-r border-border h-full overflow-hidden', className)}>
      {children}
    </div>
  )
}

export function PanelHeader({ children, className, dragHandleProps }: PanelHeaderProps) {
  return (
    <div className={cn('px-6 py-4 border-b border-border flex items-center gap-2 group/header relative', className)}>
      {dragHandleProps && (
        <div 
          {...dragHandleProps} 
          className="absolute left-1 top-1/2 -translate-y-1/2 opacity-0 group-hover/header:opacity-40 hover:!opacity-100 cursor-grab active:cursor-grabbing p-1 transition-all"
        >
          <GripVertical className="h-4 w-4" />
        </div>
      )}
      <div className={cn("flex-1 flex items-center gap-2", dragHandleProps && "pl-2")}>
        {children}
      </div>
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
