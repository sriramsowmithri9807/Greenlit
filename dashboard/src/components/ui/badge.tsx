import { type VariantProps, cva } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium tracking-wide uppercase',
  {
    variants: {
      variant: {
        neutral: 'border-[var(--color-border)] bg-[var(--color-surface-raised)] text-[var(--color-fg-muted)]',
        fail: 'border-[var(--color-fail)]/40 bg-[var(--color-fail-dim)]/40 text-[var(--color-fail)]',
        amber: 'border-[var(--color-amber)]/40 bg-[var(--color-amber)]/10 text-[var(--color-amber)]',
        pass: 'border-[var(--color-pass)]/40 bg-[var(--color-pass-dim)]/40 text-[var(--color-pass)]',
      },
    },
    defaultVariants: { variant: 'neutral' },
  },
)

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
