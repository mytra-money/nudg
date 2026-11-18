/** Inbox filter values. Must match nudg.utils.conversation_status. */

export type ConversationStatus =
  | 'blocked'
  | 'failed'
  | 'needs_reply'
  | 'window_open'
  | 'template_only'

export const CONVERSATION_STATUS_FILTERS: {
  label: string
  value: 'all' | ConversationStatus
}[] = [
  { label: 'All', value: 'all' },
  { label: 'Needs reply', value: 'needs_reply' },
  { label: 'Window open', value: 'window_open' },
  { label: 'Template only', value: 'template_only' },
  { label: 'Failed', value: 'failed' },
  { label: 'Blocked', value: 'blocked' },
]

export const CONVERSATION_STATUS_LABEL: Record<ConversationStatus, string> = {
  blocked: 'Blocked',
  failed: 'Failed',
  needs_reply: 'Needs reply',
  window_open: 'Window open',
  template_only: 'Template only',
}

export function conversationStatusOf(row: {
  conversation_status?: string | null
  needs_reply?: boolean
  failed?: boolean
  profile?: { status?: string }
  window?: { status?: string; expires_at?: string | null }
}): ConversationStatus {
  const direct = row.conversation_status
  if (
    direct === 'blocked' ||
    direct === 'failed' ||
    direct === 'needs_reply' ||
    direct === 'window_open' ||
    direct === 'template_only'
  ) {
    return direct
  }
  if (row.profile?.status === 'Blocked') return 'blocked'
  if (row.failed) return 'failed'
  if (row.needs_reply) return 'needs_reply'
  if (row.window?.status === 'open') return 'window_open'
  return 'template_only'
}

/** Window expiry is local. The list flips to template-only when `expires_at` passes, without a refetch. */
export function conversationStatusAt(
  row: Parameters<typeof conversationStatusOf>[0],
  now = Date.now(),
): ConversationStatus {
  const status = conversationStatusOf(row)
  if (status !== 'window_open') return status
  const expires = row.window?.expires_at
  if (!expires) return status
  return new Date(expires).getTime() <= now ? 'template_only' : status
}
