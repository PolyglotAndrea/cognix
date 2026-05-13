import { useState, useRef, useEffect } from 'react'
import { cn } from '@/shared/lib/cn'

interface TooltipProps {
  content: string
  children: React.ReactNode
  side?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}

export function Tooltip({ content, children, side = 'top', className }: TooltipProps) {
  const [visible, setVisible] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>()

  const show = () => {
    timeoutRef.current = setTimeout(() => setVisible(true), 300)
  }

  const hide = () => {
    clearTimeout(timeoutRef.current)
    setVisible(false)
  }

  useEffect(() => () => clearTimeout(timeoutRef.current), [])

  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }

  return (
    <div className="relative inline-flex" onMouseEnter={show} onMouseLeave={hide}>
      {children}
      {visible && (
        <div
          className={cn(
            'absolute z-50 px-2.5 py-1.5 text-[10px] font-medium text-foreground bg-card border border-border rounded-lg shadow-lg whitespace-nowrap animate-in fade-in zoom-in-95 duration-150',
            positionClasses[side],
            className,
          )}
        >
          {content}
        </div>
      )}
    </div>
  )
}
