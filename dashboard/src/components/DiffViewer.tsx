import { motion } from 'framer-motion'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'

export function DiffViewer({ diff, revision }: { diff: string; revision: number }) {
  const reducedMotion = usePrefersReducedMotion()

  if (!diff) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-sm text-[var(--color-fg-muted)]">
        Waiting for a proposed fix…
      </div>
    )
  }

  const lines = diff.split('\n')

  return (
    <div key={revision} className="h-full overflow-auto px-4 py-3 font-mono text-[13px] leading-relaxed">
      {lines.map((line, i) => (
        <motion.div
          key={i}
          initial={reducedMotion ? false : { opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reducedMotion ? { duration: 0 } : { duration: 0.25, delay: i * 0.035, ease: 'easeOut' }}
        >
          <SyntaxHighlighter
            language="diff"
            style={vscDarkPlus}
            PreTag="div"
            customStyle={{ background: 'transparent', margin: 0, padding: 0 }}
          >
            {line.length ? line : ' '}
          </SyntaxHighlighter>
        </motion.div>
      ))}
    </div>
  )
}
