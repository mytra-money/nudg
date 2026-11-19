import { describe, expect, it } from 'vitest'
import { applyConversation, applyThreadMessage, isNewIncoming } from '@/stores/inboxLive'
import { conversationStatusAt } from '@/utils/conversationStatus'
import type { Conversation, Thread } from '@/types'

function card(name: string, preview = 'Hello'): Conversation {
  return {
    profile: {
      name,
      profile_name: name,
      phone_number: '+1000',
      whatsapp_account: 'WA',
      status: 'Active',
    },
    preview: {
      name: `preview-${name}`,
      to: name,
      direction: 'Incoming',
      message: preview,
      creation: '2026-11-18T10:00:00',
    },
    window: { status: 'open', expires_at: '2026-11-19T10:00:00', last_incoming_at: '2026-11-18T10:00:00' },
    conversation_status: 'needs_reply',
    needs_reply: true,
    failed: false,
  }
}

function thread(messages: Thread['messages']): Thread {
  return {
    profile: card('prof').profile,
    messages,
    window: { status: 'open', expires_at: '2026-11-19T10:00:00', last_incoming_at: '2026-11-18T10:00:00' },
    references: [],
    links: [],
  }
}

describe('inbox live patches', () => {
  it('inserts a new conversation at the top', () => {
    const next = applyConversation([card('a')], { profile: 'b', bump: true, conversation: card('b') })
    expect(next.map((row) => row.profile.name)).toEqual(['b', 'a'])
  })

  it('updates a conversation in place when the change is not a new message', () => {
    const updated = card('a', 'Delivered')
    const next = applyConversation([card('a'), card('b')], { profile: 'a', bump: false, conversation: updated })
    expect(next.map((row) => row.profile.name)).toEqual(['a', 'b'])
    expect(next[0].preview?.message).toBe('Delivered')
  })

  it('moves an existing conversation to the top only for a new message', () => {
    const updated = card('b', 'New')
    const next = applyConversation([card('a'), card('b')], { profile: 'b', bump: true, conversation: updated })
    expect(next.map((row) => row.profile.name)).toEqual(['b', 'a'])
  })

  it('appends a message and replaces one that already exists', () => {
    const open = thread([
      { name: 'm1', to: 'prof', direction: 'Incoming', message: 'Hi', creation: '2026-11-18T09:00:00' },
    ])
    const added = applyThreadMessage(open, {
      profile: 'prof',
      message: { name: 'm2', to: 'prof', direction: 'Outgoing', message: 'Reply', creation: '2026-11-18T09:05:00', status: 'Sent' },
    })
    expect(added.messages.map((row) => row.name)).toEqual(['m1', 'm2'])

    const ticked = applyThreadMessage(added, {
      profile: 'prof',
      message: { name: 'm2', to: 'prof', direction: 'Outgoing', message: 'Reply', creation: '2026-11-18T09:05:00', status: 'Read' },
    })
    expect(ticked.messages).toHaveLength(2)
    expect(ticked.messages[1].status).toBe('Read')
  })

  it('keeps one bubble when the same WhatsApp message arrives again', () => {
    const open = thread([
      {
        name: 'm1',
        to: 'prof',
        direction: 'Incoming',
        message: 'hello',
        message_id: 'wamid.HELLO',
        creation: '2026-11-18T09:00:00',
      },
    ])
    const next = applyThreadMessage(open, {
      profile: 'prof',
      message: {
        name: 'm1-copy',
        to: 'prof',
        direction: 'Incoming',
        message: 'hello',
        message_id: 'wamid.HELLO',
        creation: '2026-11-18T09:00:01',
      },
    })
    expect(next.messages).toHaveLength(1)
    expect(next.messages[0].name).toBe('m1')
  })

  it('plays the receive sound only for a new incoming message', () => {
    const previous = card('prof')
    expect(
      isNewIncoming(previous, {
        profile: 'prof',
        bump: true,
        message: { name: 'm-new', to: 'prof', direction: 'Incoming', creation: '2026-11-18T10:01:00' },
      }),
    ).toBe(true)
    expect(
      isNewIncoming(previous, {
        profile: 'prof',
        bump: false,
        message: { name: 'm-new', to: 'prof', direction: 'Incoming', creation: '2026-11-18T10:01:00', status: 'Read' },
      }),
    ).toBe(false)
    expect(
      isNewIncoming(previous, {
        profile: 'prof',
        bump: true,
        message: { name: previous.preview!.name, to: 'prof', direction: 'Incoming', creation: '2026-11-18T10:00:00' },
      }),
    ).toBe(false)
  })

  it('closes a window locally once its expiry has passed', () => {
    const row = card('prof')
    expect(conversationStatusAt(row, new Date('2026-11-18T12:00:00').getTime())).toBe('needs_reply')
    const open = { ...row, conversation_status: 'window_open' as const, needs_reply: false }
    expect(conversationStatusAt(open, new Date('2026-11-18T12:00:00').getTime())).toBe('window_open')
    expect(conversationStatusAt(open, new Date('2026-11-19T10:00:01').getTime())).toBe('template_only')
  })
})
