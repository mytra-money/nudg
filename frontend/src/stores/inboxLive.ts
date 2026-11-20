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

export function eventTargets(openProfile: string | null | undefined, event: InboxLiveEvent): boolean {
  if (!openProfile) return false
  return [event.profile, event.conversation?.profile?.name, event.message?.to, event.conversation?.preview?.to].includes(
    openProfile,
  )
}

/** Insert the socket message into the open thread. The list card's preview is the same message when the payload omits it. */
export function mergeLiveThread(thread: Thread, openProfile: string, event: InboxLiveEvent): Thread {
  if (thread.profile.name !== openProfile || !eventTargets(openProfile, event)) return thread
  let next = applyThreadMessage(thread, { ...event, profile: openProfile })
  const preview = event.conversation?.preview
  if (!preview?.name || next.messages.some((row) => row.name === preview.name)) return next
  return applyThreadMessage(next, { profile: openProfile, message: preview })
}

export function applyThreadMessage(thread: Thread, event: InboxLiveEvent): Thread {
  const incoming = event.message
  const target = event.profile || incoming?.to
  if (!incoming?.name || thread.profile.name !== target) return thread
  const messages = thread.messages.slice()
  let index = messages.findIndex((row) => row.name === incoming.name)
  if (index < 0 && incoming.message_id) {
    index = messages.findIndex((row) => row.message_id && row.message_id === incoming.message_id)
  }
  if (index >= 0) messages[index] = { ...messages[index], ...incoming, name: messages[index].name }
  else messages.push(incoming)
  messages.sort((a, b) => (a.creation || '').localeCompare(b.creation || '') || a.name.localeCompare(b.name))
  const incomingProfile = event.conversation?.profile
  return {
    ...thread,
    profile: incomingProfile?.whatsapp_account ? incomingProfile : thread.profile,
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
