import * as React from 'react'
import { X } from 'lucide-react'
import { cn } from '@/shared/lib/cn'

interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title?: string
  children: React.ReactNode
  className?: string
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  className,
  size = 'md',
}: ModalProps) {
  React.useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    if (isOpen) {
      document.body.style.overflow = 'hidden'
      window.addEventListener('keydown', handleEsc)
    }
    return () => {
      document.body.style.overflow = 'unset'
      window.removeEventListener('keydown', handleEsc)
    }
  }, [isOpen, onClose])

  if (!isOpen) return null

  const sizeClasses = {
    sm: 'max-w-md',
    md: 'max-w-2xl',
    lg: 'max-w-4xl',
    xl: 'max-w-6xl',
    full: 'max-w-[95vw] h-[90vh]',
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-background/80 backdrop-blur-sm animate-in fade-in duration-300" 
        onClick={onClose}
      />
      
      {/* Content */}
      <div 
        className={cn(
          "relative w-full bg-card border border-border shadow-2xl rounded-3xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-300",
          sizeClasses[size],
          className
        )}
      >
        {/* Header */}
        {title && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
            <h3 className="text-lg font-bold text-foreground">{title}</h3>
            <button 
              onClick={onClose}
              className="p-2 rounded-xl hover:bg-muted text-muted-foreground hover:text-foreground transition-all active:scale-95"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        )}
        
        {/* Body */}
        <div className="flex-1 overflow-auto p-6 scrollbar-hide">
          {children}
        </div>
      </div>
    </div>
  )
}
