export function Header() {
  return (
    <header className="flex items-baseline gap-3 px-6 pt-6 pb-4">
      <h1 className="text-xl font-bold tracking-tight text-[var(--color-fg)]">
        Green<span className="text-[var(--color-pass)]">lit</span>
      </h1>
      <p className="text-sm text-[var(--color-fg-muted)]">
        Red test goes in. It doesn't come out until it's green.
      </p>
    </header>
  )
}
