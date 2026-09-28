import type { ChangedFile, Changes } from '@/types/events'

/** TS twin of greenlit/changes.py, so the scripted demo can send the same
 * change report the backend does. */
export function parseDiff(diff: string): ChangedFile[] {
  const files: ChangedFile[] = []
  let file: ChangedFile | null = null
  let hunk: ChangedFile['hunks'][number] | null = null
  let oldNo = 0
  let newNo = 0
  for (const raw of diff.split('\n')) {
    const header = raw.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/)
    if (raw.startsWith('--- ')) {
      file = { path: '', status: 'modified', added: 0, removed: 0, lines_changed: '', hunks: [] }
      files.push(file)
      hunk = null
    } else if (!file) {
      continue
    } else if (raw.startsWith('+++ ') && !hunk) {
      file.path = raw.slice(4).replace(/^b\//, '')
    } else if (header) {
      oldNo = Number(header[1])
      newNo = Number(header[2])
      hunk = { header: raw, lines: [] }
      file.hunks.push(hunk)
    } else if (!hunk) {
      continue
    } else if (raw.startsWith('+')) {
      hunk.lines.push({ kind: 'add', old: null, new: newNo++, text: raw.slice(1) })
      file.added += 1
    } else if (raw.startsWith('-')) {
      hunk.lines.push({ kind: 'del', old: oldNo++, new: null, text: raw.slice(1) })
      file.removed += 1
    } else {
      hunk.lines.push({ kind: 'ctx', old: oldNo++, new: newNo++, text: raw.slice(1) })
    }
  }
  for (const f of files) {
    // Drop the trailing empty context line a template literal leaves behind.
    for (const h of f.hunks) if (h.lines.at(-1)?.kind === 'ctx' && h.lines.at(-1)?.text === '') h.lines.pop()
    const points = new Set<number>()
    for (const h of f.hunks) {
      h.lines.forEach((line, i) => {
        if (line.kind === 'add') points.add(line.new!)
        if (line.kind === 'del') points.add(h.lines.slice(i + 1).find((l) => l.new !== null)?.new ?? line.old!)
      })
    }
    const ranges: [number, number][] = []
    for (const n of [...points].sort((a, b) => a - b)) {
      const last = ranges.at(-1)
      if (last && n === last[1] + 1) last[1] = n
      else ranges.push([n, n])
    }
    f.lines_changed = ranges.map(([a, b]) => (a === b ? `${a}` : `${a}-${b}`)).join(', ')
  }
  return files
}

export function summarize(fixes: { key: string; title: string; location: string | null; diff: string }[]): Changes {
  const out = fixes.map(({ key, title, location, diff }) => ({ key, title, location, files: parseDiff(diff) }))
  const all = out.flatMap((fix) => fix.files)
  return {
    fixes: out,
    totals: {
      fixes: out.length,
      files: new Set(all.map((f) => f.path)).size,
      added: all.reduce((n, f) => n + f.added, 0),
      removed: all.reduce((n, f) => n + f.removed, 0),
    },
  }
}
