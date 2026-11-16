/** Format Meta / WhatsApp error payloads for the chat UI.
 * Keeps messages clean, concise, and non-intimidating for customer service agents.
 */

export function formatErrorMessage(raw?: string | null): string | undefined {
  if (!raw) return undefined
  const text = String(raw).trim()
  if (!text) return undefined

  try {
    let data: unknown = JSON.parse(text)
    if (Array.isArray(data)) data = data[0] ?? {}
    if (!data || typeof data !== 'object') {
      if (text.includes('190') || text.toLowerCase().includes('authentication')) {
        return 'Error sending'
      }
      return text.length > 50 ? 'Error sending' : text
    }

    const root = data as Record<string, unknown>
    const error = (root.error && typeof root.error === 'object' ? root.error : root) as Record<
      string,
      unknown
    >
    const code = Number(error.code ?? error.error_subcode)

    // Code 190 / OAuthException: Credentials invalid or expired
    if (code === 190 || String(error.type).toLowerCase() === 'oauthexception') {
      return 'Error sending'
    }

    // Code 131047: 24h customer window closed
    if (code === 131047) {
      return 'Template required'
    }

    // Code 131030: Phone number not allowed in sandbox/trial
    if (code === 131030) {
      return 'Recipient not in test list'
    }

    // Rate limit
    if (code === 80007 || code === 130429) {
      return 'Rate limit reached'
    }

    return 'Error sending'
  } catch {
    if (text.includes('190') || text.toLowerCase().includes('authentication')) {
      return 'Error sending'
    }
    return text.length > 50 ? 'Error sending' : text
  }
}

const RAW_ERROR = /unsupported post request|graph api|developers\.facebook|traceback|\bexception\b|object with id|<!doctype|<html|modulenotfound|https?:\/\/|fbtrace_id|oauthexception|"error"\s*:|"code"\s*:/i

function errorParts(error: unknown): string {
  const parts: string[] = []
  if (error && typeof error === 'object' && 'messages' in error) {
    const messages = (error as { messages?: unknown }).messages
    if (Array.isArray(messages)) {
      for (const message of messages) {
        if (message) parts.push(String(message))
      }
    }
  }
  if (!parts.length && error instanceof Error && error.message) parts.push(error.message)
  if (!parts.length && typeof error === 'string') parts.push(error)
  return parts
    .join(' ')
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Desk-facing text. Keeps a short Frappe message and hides Graph dumps and tracebacks. */
export function userFacingError(error: unknown, fallback = 'Something went wrong. Try again.'): string {
  const text = errorParts(error)
  if (!text || RAW_ERROR.test(text) || text.length > 180) return fallback
  return text
}
