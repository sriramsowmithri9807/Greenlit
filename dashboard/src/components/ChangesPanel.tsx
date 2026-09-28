import { motion } from 'framer-motion'
import { FileCode2 } from 'lucide-react'
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion'
import type { ChangedFile, Changes } from '@/types/events'

const ROW: Record<'add' | 'del' | 'ctx', { sign: string; className: string }> = {
  add: { sign: '+', className: 'bg-[var(--color-pass)]/[0.10] text-[#b7f5c8]' },
  del: { sign: '-', className: 'bg-[var(--color-fail)]/[0.10] text-[#fbc4c4]' },
  ctx: { sign: ' ', className: 'text-[var(--color-fg-muted)]' },
}

function FileBlock({ file }: { file: ChangedFile }) {
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-xs">
        <FileCode2 size={13} className="text-[var(--color-done)]" />
        <span className="font-mono font-semibold text-[var(--color-fg)]">{file.path}</span>
        {file.status !== 'modified' && <span className="text-[var(--color-amber)]">{file.status}</span>}
        <span className="font-mono text-[var(--color-pass)]">+{file.added}</span>
        <span className="-ml-2 font-mono text-[var(--color-fail)]">-{file.removed}</span>
        {file.lines_changed && <span className="ml-auto font-mono text-[var(--color-fg-muted)]">lines {file.lines_changed}</span>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-mono text-[12px] leading-[1.6]">
          <tbody>
            {file.hunks.map((hunk, h) => [
              <tr key={`h${h}`} className="bg-[var(--color-done)]/[0.06] text-[var(--color-done)]/80">
                <td colSpan={4} className="px-3 py-0.5">
                  {hunk.header}
                </td>
              </tr>,
              ...hunk.lines.map((line, i) => (
                <tr key={`${h}-${i}`} className={ROW[line.kind].className}>
                  <td className="w-10 px-2 text-right text-[var(--color-fg-muted)]/60 select-none">{line.old ?? ''}</td>
                  <td className="w-10 px-2 text-right text-[var(--color-fg-muted)]/60 select-none">{line.new ?? ''}</td>
                  <td className="w-4 select-none">{ROW[line.kind].sign}</td>
                  <td className="pr-3 whitespace-pre">{line.text || ' '}</td>
                </tr>
              )),
            ])}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** Every verified fix: which files it touched, at which lines, and the code. */
export function ChangesPanel({ changes }: { changes: Changes }) {
  const reducedMotion = usePrefersReducedMotion()
  return (
    <div className="h-full space-y-4 overflow-y-auto px-4 py-3">
      {changes.fixes.map((fix, n) => (
        <motion.section
          key={fix.key}
          className="space-y-2"
          initial={reducedMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reducedMotion ? { duration: 0 } : { duration: 0.3, delay: n * 0.08 }}
        >
          <h3 className="flex items-baseline gap-2 text-sm">
            <span className="font-mono text-xs text-[var(--color-fg-muted)]">[{n + 1}]</span>
            <span className="font-medium">{fix.title}</span>
            {fix.location && <span className="truncate font-mono text-[11px] text-[var(--color-fg-muted)]">{fix.location}</span>}
          </h3>
          {fix.files.map((file) => (
            <FileBlock key={file.path} file={file} />
          ))}
        </motion.section>
      ))}
    </div>
  )
}
