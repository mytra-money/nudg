import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useInboxStore } from '@/stores/inbox'
import { useThreadStore } from '@/stores/thread'
import { deskCacheKey, threadAccountAllowed } from '@/utils/deskCache'
import type { Inbox, Thread } from '@/types'

function inboxFor(accounts: Inbox['accounts']): Inbox {
  return {
    mode: 'live',
    connected: true,
    user: 'test@meta.com',
    site: 'mytra-nudg',
    default_account: null,
    can_read_logs: false,
    accounts,
    templates: [],
    conversations: [],
  }
}

function cachedThread(): Thread {
  return {
    profile: {
      name: 'nagarajukodela',
      profile_name: 'nagarajukodela',
      phone_number: '+918465068862',
      whatsapp_account: 'WhatsApp 0564',
      status: 'Active',
    },
    messages: [],
    window: { status: 'closed', expires_at: null, last_incoming_at: null },
    references: [],
    links: [],
  }
}

describe('desk cache isolation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.user = 'test@meta.com'
    window.site_name = 'mytra-nudg'
    window.sitename = 'mytra-nudg'
  })

  it('keys saved inbox data by site and user', () => {
    expect(deskCacheKey('thread')).toBe('nudg:thread:mytra-nudg:test@meta.com')
    window.user = 'owner@example.com'
    expect(deskCacheKey('thread')).toBe('nudg:thread:mytra-nudg:owner@example.com')
  })

  it('hides a thread whose WhatsApp account is not on this inbox', () => {
    expect(threadAccountAllowed('WhatsApp 0564', [])).toBe(false)
    expect(threadAccountAllowed('WhatsApp 0564', undefined)).toBe(false)
    expect(threadAccountAllowed('WhatsApp 0564', [{ name: 'WhatsApp 1000' }])).toBe(false)
    expect(threadAccountAllowed('WhatsApp 0564', [{ name: 'WhatsApp 0564' }])).toBe(true)
    expect(threadAccountAllowed(undefined, [{ name: 'WhatsApp 0564' }])).toBe(false)
  })

  it('drops a restored thread when this user cannot access that WhatsApp account', async () => {
    const inbox = useInboxStore()
    const thread = useThreadStore()
    thread.thread = cachedThread()
    inbox.inbox = inboxFor([])
    await nextTick()
    expect(thread.thread).toBeNull()
    expect(thread.profile).toBeNull()
  })

  it('keeps a restored thread for an account on this inbox', async () => {
    const inbox = useInboxStore()
    const thread = useThreadStore()
    thread.thread = cachedThread()
    inbox.inbox = inboxFor([{ name: 'WhatsApp 0564', account_name: 'WhatsApp 0564', status: 'Active' }])
    await nextTick()
    expect(thread.thread?.profile.name).toBe('nagarajukodela')
  })
})
