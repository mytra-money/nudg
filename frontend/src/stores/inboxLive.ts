import type { ChatMessage, Conversation, Thread } from '@/types'

/** One conversation the server already computed. The client inserts it; it does not refetch. */
export interface InboxLiveEvent {
  profile: string
  /** New visible message: move the conversation to the top. Status and assignment stay put. */
  bump?: boolean
  conversation?: Conversation | null
  message?: ChatMessage | null
}

export function applyConversation(conversations: Conversation[], event: InboxLiveEvent): Conversation[] {
  const card = event.conversation
  const name = card?.profile?.name
  if (!card || !name) return conversations
  const index = conversations.findIndex((row) => row.profile.name === name)
  if (index < 0) return [card, ...conversations]
  const next = conversations.slice()
  next[index] = card
  if (event.bump && index > 0) {
    next.splice(index, 1)
    next.unshift(card)
  }
  return next
}

export function applyThreadMessage(thread: Thread, event: InboxLiveEvent): Thread {
  const incoming = event.message
  if (!incoming?.name || thread.profile.name !== event.profile) return thread
  const messages = thread.messages.slice()
  const index = messages.findIndex((row) => row.name === incoming.name)
  if (index >= 0) messages[index] = { ...messages[index], ...incoming }
  else messages.push(incoming)
  messages.sort((a, b) => (a.creation || '').localeCompare(b.creation || '') || a.name.localeCompare(b.name))
  return {
    ...thread,
    profile: event.conversation?.profile || thread.profile,
    window: event.conversation?.window || thread.window,
    messages,
  }
}

/** Play the receive sound once per new incoming message, not on delivery ticks or duplicates. */
export function isNewIncoming(previous: Conversation | undefined, event: InboxLiveEvent): boolean {
  if (!event.bump) return false
  const message = event.message
  if (!message || message.direction !== 'Incoming' || !message.name) return false
  return previous?.preview?.name !== message.name
}
