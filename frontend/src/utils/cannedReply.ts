export type QuickReplyRow = {
  name: string
  title?: string
  shortcut?: string
  body?: string
}

/** Detect a trailing slash-command in the composer draft (Whatomate-style `/greet`). */
export function slashCommand(draft: string): { open: boolean; query: string } | null {
  if (!draft) return null
  // Only the last line counts — multi-line drafts keep earlier text free of the picker.
  const line = draft.split('\n').pop() ?? ''
  const match = /(^|\s)\/([^\s]*)$/.exec(line)
  if (!match) return null
  return { open: true, query: match[2] || '' }
}

export function filterQuickReplies(rows: QuickReplyRow[], query: string): QuickReplyRow[] {
  const term = query.trim().toLowerCase()
  if (!term) return rows
  return rows.filter((row) => {
    const shortcut = String(row.shortcut || '').replace(/^\//, '').toLowerCase()
    return (
      shortcut.includes(term) ||
      (row.title || '').toLowerCase().includes(term) ||
      (row.body || '').toLowerCase().includes(term)
    )
  })
}

/** Replace the trailing `/query` token with the reply body. */
export function applyQuickReplyDraft(draft: string, body: string): string {
  const lines = draft.split('\n')
  const last = lines[lines.length - 1] ?? ''
  const nextLast = last.replace(/(^|\s)\/[^\s]*$/, `$1${body}`)
  lines[lines.length - 1] = nextLast
  return lines.join('\n')
}
