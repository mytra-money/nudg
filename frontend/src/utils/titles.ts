const SERIES_ID = /^(WA-CAMP|BULK-WA|WA-KWD|WA-AGT|WA-CHAT)-/
const HASH_ID = /^[a-z0-9]{10}$/

export function isDocumentId(value: string) {
  return SERIES_ID.test(value) || HASH_ID.test(value)
}

export function displayTitle(...candidates: Array<string | null | undefined>) {
  for (const candidate of candidates) {
    const text = String(candidate || '').trim()
    if (text && !isDocumentId(text)) return text
  }
  return ''
}
