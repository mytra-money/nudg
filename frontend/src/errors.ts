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
