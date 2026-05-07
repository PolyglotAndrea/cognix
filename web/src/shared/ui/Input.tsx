import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => {
    return (
      <input
        className={cn(
          'w-full px-4 py-2 bg-muted border border-border rounded-xl text-sm transition-all',
          'focus:ring-2 focus:ring-primary/20 focus:border-primary/40 focus:bg-background outline-none text-foreground',
          'placeholder:text-muted-foreground/50',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = 'Input'
