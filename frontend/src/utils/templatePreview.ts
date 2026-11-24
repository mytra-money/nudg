/**
 * Local preview helpers for WA Template rows already returned by the desk inbox.
 *
 * Placeholders match the official app: `{{name}}` or `{{1}}`, with optional
 * spaces inside the braces. See `get_template_variables` in frappe/whatsapp.
 * The bubble uses the stored variable example. A placeholder with no example
 * stays visible; nothing is invented in code.
 * Sample edits in the preview stay local and never write the template.
 */

const VARIABLE = /\{\{\s*([^}]+?)\s*\}\}/g

const POSITIONAL_SAMPLES = ['Nag', 'ORD-001', '₹2,499', '10 November 2026']

const NAMED_SAMPLES: Record<string, string> = {
  name: 'Nag',
  customer: 'Nag',
  customer_name: 'Nag',
  first_name: 'Nag',
  full_name: 'Nag',
  order: 'ORD-001',
  order_id: 'ORD-001',
  order_number: 'ORD-001',
  amount: '₹2,499',
  total: '₹2,499',
  total_amount: '₹2,499',
  date: '10 November 2026',
  delivery_date: '10 November 2026',
}

export type HeaderKind = 'text' | 'image' | 'video' | 'document' | 'gif' | 'unsupported'

export type SampleSource = Map<string, string> | Record<string, string | undefined>

export interface PreviewVariable {
  variable_name?: string
  variable_example?: string
}

export interface PreviewTemplate {
  header_text?: string
  header_type?: string
  header_media?: string
  message?: string
  buttons?: { url?: string }[]
  template_variables?: PreviewVariable[] | null
}

export function variableNames(...texts: (string | undefined | null)[]): string[] {
  const names: string[] = []
  const seen = new Set<string>()
  for (const text of texts) {
    for (const match of (text ?? '').matchAll(VARIABLE)) {
      const name = match[1].trim()
      if (!name || seen.has(name)) continue
      seen.add(name)
      names.push(name)
    }
  }
  return names
}

/** Header text, body, URL buttons, then any stored rows the text does not mention. */
export function previewVariableNames(template: PreviewTemplate): string[] {
  const names = variableNames(
    template.header_text,
    template.message,
    ...(template.buttons || []).map((button) => button.url),
  )
  for (const row of template.template_variables || []) {
    const name = row.variable_name?.trim()
    if (name && !names.includes(name)) names.push(name)
  }
  return names
}

export function exampleMap(variables?: PreviewVariable[] | null): Map<string, string> {
  const map = new Map<string, string>()
  for (const row of variables || []) {
    const name = row.variable_name?.trim()
    if (name) map.set(name, row.variable_example || '')
  }
  return map
}

export function fallbackSample(name: string): string {
  if (/^\d+$/.test(name)) {
    const index = Number(name) - 1
    return index >= 0 && index < POSITIONAL_SAMPLES.length ? POSITIONAL_SAMPLES[index] : `Sample ${name}`
  }
  return NAMED_SAMPLES[name.toLowerCase()] || 'Sample'
}

/** Use the stored `variable_example`. An empty example leaves the placeholder in the bubble. */
export function resolveSampleValues(template: PreviewTemplate): Record<string, string> {
  const stored = exampleMap(template.template_variables)
  const values: Record<string, string> = {}
  for (const name of previewVariableNames(template)) {
    values[name] = stored.get(name)?.trim() || ''
  }
  return values
}

export function fillVariables(text: string | undefined | null, examples: SampleSource): string {
  return (text ?? '').replace(VARIABLE, (match, raw: string) => {
    const name = raw.trim()
    const value = examples instanceof Map ? examples.get(name) : examples[name]
    if (value == null || value === '') return match
    return value
  })
}

/** Public example media only. Private Frappe files and other schemes are not requested. */
export function publicMediaUrl(url?: string | null): string | null {
  if (!url) return null
  const value = url.trim()
  if (!value || value.includes('..')) return null
  if (/^data:image\/[a-z0-9.+-]+[;,]/i.test(value)) return value
  if (value.startsWith('/files/')) return value
  if (/^https?:\/\//i.test(value)) {
    try {
      const parsed = new URL(value)
      if (parsed.pathname.startsWith('/private/') || parsed.pathname.includes('/private/files/')) return null
      return value
    } catch {
      return null
    }
  }
  return null
}

export function headerKind(headerType?: string | null): HeaderKind {
  switch ((headerType || 'Text').trim()) {
    case 'Text':
      return 'text'
    case 'Image':
      return 'image'
    case 'Video':
      return 'video'
    case 'Document':
      return 'document'
    case 'GIF':
      return 'gif'
    default:
      return 'unsupported'
  }
}

export function mediaFileName(url?: string | null): string {
  if (!url) return 'Document'
  const path = url.split('?')[0]?.split('#')[0] || ''
  const base = path.split('/').pop() || ''
  if (!base) return 'Document'
  try {
    return decodeURIComponent(base) || 'Document'
  } catch {
    return base
  }
}

export function mediaTypeLabel(mime?: string | null, fileName?: string): string {
  if (mime === 'application/pdf') return 'PDF'
  if (mime) {
    const subtype = mime.split('/')[1]?.split('+')[0]
    if (subtype) return subtype.toUpperCase()
  }
  const ext = fileName?.includes('.') ? fileName.split('.').pop() : ''
  return ext ? ext.toUpperCase() : 'FILE'
}
