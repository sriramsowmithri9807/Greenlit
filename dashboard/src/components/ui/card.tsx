import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'hud rounded-xl border border-[var(--color-border)] shadow-[0_1px_0_0_rgba(255,255,255,0.04)_inset,0_20px_40px_-20px_rgba(0,0,0,0.6)]',
        className,
      )}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2.5',
        className,
      )}
      {...props}
    />
  )
}

export function CardTitle({ className, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn(
        'flex items-center gap-2 font-[family-name:var(--font-display)] text-xs font-semibold tracking-widest text-[var(--color-fg-muted)] uppercase',
        className,
      )}
      {...props}
    >
      <span aria-hidden className="h-1.5 w-1.5 shrink-0 rotate-45 bg-[var(--color-pass)] shadow-[0_0_8px_rgba(34,197,94,0.8)]" />
      <span className="min-w-0 truncate">{children}</span>
    </h2>
  )
}
