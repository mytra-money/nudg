import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { call, createResource, toast } from 'frappe-ui'
import { conversationStatusOf } from '@/utils/conversationStatus'
import { errorText } from '@/utils/format'
import { sampleInbox, sampleLogs } from '@/mocks/sample'
import { applyConversation, isNewIncoming, type InboxLiveEvent } from '@/stores/inboxLive'
import { isLiveSession } from '@/stores/session'
import { playSound } from '@/stores/sounds'
import { getSocket, onDeskEvent } from '@/socket'
import { accountArg as toAccountArg, chooseAccount, readSavedAccount, writeSavedAccount } from '@/utils/accountSelection'
import { deskCacheKey } from '@/utils/deskCache'
import type { Inbox, LogRow, Template } from '@/types'

export interface InboxLiveHandlers {
  onEvent?: (event: InboxLiveEvent) => void
  onReconnect?: () => void
}

export type PresenceRow = { user: string; name: string; typing: boolean; viewing: boolean }

export const useInboxStore = defineStore('nudg-inbox', () => {
  const account = ref(readSavedAccount() || '')
  const presence = ref<Record<string, PresenceRow[]>>({})
  const error = ref<string | null>(null)
  const loading = ref(true)
  const started = ref(false)
  let realtimeBound = false
  let catchUp = false
  let pollTimer: ReturnType<typeof setTimeout> | undefined
  let liveHandlers: InboxLiveHandlers = {}

  const inboxResource = createResource<Inbox | null>({
    url: 'nudg.api.get_inbox',
    cache: deskCacheKey('inbox'),
    initialData: null,
    auto: false,
  })

  const logsResource = createResource<LogRow[]>({
    url: 'nudg.api.get_logs',
    cache: deskCacheKey('logs'),
    initialData: [],
    auto: false,
  })

  const templatesResource = createResource<Template[]>({
    url: 'nudg.api.get_templates',
    cache: deskCacheKey('templates'),
    initialData: [],
    auto: false,
  })

  let conversationOffset = 0

  const inbox = computed({
    get: () => {
      const data = inboxResource.data
      if (!data) return data
      const templates = templatesResource.data
      if (Array.isArray(templates) && templates.length) return { ...data, templates }
      return data
    },
    set: (value) => {
      inboxResource.setData(value)
    },
  })

  const logs = computed({
    get: () => logsResource.data || [],
    set: (value) => {
      logsResource.setData(value)
    },
  })

  const mode = computed(() => inbox.value?.mode || (isLiveSession() ? 'live' : 'sample'))

  function accountArg() {
    return toAccountArg(account.value)
  }

  function fetchTemplates() {
    if (!isLiveSession()) return Promise.resolve()
    return templatesResource.fetch({ account: accountArg() }).catch(() => undefined)
  }

  function syncTabTitle() {
    if (typeof document === 'undefined') return
    const waiting = (inbox.value?.conversations || []).filter((row) => conversationStatusOf(row) === 'needs_reply')
      .length
    document.title = waiting ? `(${waiting}) Nudg` : 'Nudg'
  }

  function applyPresence(data: Record<string, unknown>, kind: 'typing' | 'viewing') {
    const id = String(data?.conversation_id || '')
    const actor = String(data?.user || '')
    if (!id || !actor || actor === window.user) return
    const current = presence.value[id] || []
    const others = current.filter((row) => row.user !== actor)
    if (data.active) {
      const previous = current.find((row) => row.user === actor)
      others.push({
        user: actor,
        name: String(data.user_fullname || actor),
        typing: kind === 'typing' ? true : Boolean(previous?.typing),
        viewing: kind === 'viewing' ? true : Boolean(previous?.viewing),
      })
    }
    presence.value = { ...presence.value, [id]: others }
  }

  function bindLive(handlers: InboxLiveHandlers) {
    liveHandlers = handlers
    bindRealtime()
  }

  function applyLive(event: InboxLiveEvent) {
    const current = inbox.value
    const card = event.conversation
    if (!current || !card?.profile?.name) return
    const account = card.profile.whatsapp_account
    if (account && !current.accounts.some((row) => row.name === account)) return
    const previous = current.conversations.find((row) => row.profile.name === card.profile.name)
    if (isNewIncoming(previous, event)) playSound('receive')
    inboxResource.setData({
      ...current,
      conversations: applyConversation(current.conversations, event),
    })
    syncTabTitle()
    liveHandlers.onEvent?.(event)
  }

  /**
   * Live updates arrive as `nudg_inbox` on the desk socket. Each event is one
   * conversation the server already computed, so the list and the open thread
   * change in place. A refetch runs only after the socket reconnects, to heal
   * events missed while the tab was offline, and it does not clear the screen.
   */
  function bindRealtime() {
    if (realtimeBound || typeof window === 'undefined') return
    const bound = onDeskEvent('nudg_inbox', (data) => applyLive(data as InboxLiveEvent))
    if (!bound) return
    realtimeBound = true
    onDeskEvent('nudg_agent_typing', (data) => applyPresence(data as Record<string, unknown>, 'typing'))
    onDeskEvent('nudg_agent_viewing', (data) => applyPresence(data as Record<string, unknown>, 'viewing'))
    getSocket()?.on('connect', () => {
      if (!catchUp) return
      void refresh({ silent: true })
      liveHandlers.onReconnect?.()
    })
    schedulePoll()
  }

  function socketIsLive() {
    return Boolean(getSocket()?.connected)
  }

  // The public tunnel does not carry Socket.IO, so a quiet refresh is what
  // brings a new message onto the open inbox.
  function schedulePoll() {
    if (pollTimer) clearTimeout(pollTimer)
    pollTimer = setTimeout(() => {
      if (catchUp && isLiveSession() && !socketIsLive()) {
        void refresh({ silent: true }).then(() => liveHandlers.onReconnect?.())
      }
      schedulePoll()
    }, 5000)
  }

  async function load() {
    bindRealtime()
    if (started.value && inbox.value) return
    started.value = true
    loading.value = true
    error.value = null
    try {
      if (!isLiveSession()) {
        inboxResource.setData(sampleInbox())
        logsResource.setData(sampleLogs())
        const next = chooseAccount(inboxResource.data?.accounts || [], readSavedAccount())
        account.value = next
        writeSavedAccount(next)
        return
      }
      const remembered = readSavedAccount()
      if (remembered) account.value = remembered
      await inboxResource.fetch({ account: accountArg() })
      conversationOffset = inboxResource.data?.conversations?.length || 0
      void fetchTemplates()
      const next = chooseAccount(inboxResource.data?.accounts || [], remembered)
      if (next !== account.value) {
        account.value = next
        writeSavedAccount(next)
        await inboxResource.fetch({ account: accountArg() })
        conversationOffset = inboxResource.data?.conversations?.length || 0
        void fetchTemplates()
      } else if (next) {
        writeSavedAccount(next)
      }
    } catch (caught) {
      error.value = errorText(caught)
    } finally {
      loading.value = false
      catchUp = isLiveSession()
      syncTabTitle()
    }
  }

  async function refresh(options?: { silent?: boolean }) {
    if (!isLiveSession()) return
    try {
      await inboxResource.fetch({ account: accountArg() })
      conversationOffset = inboxResource.data?.conversations?.length || 0
      void fetchTemplates()
      syncTabTitle()
    } catch (caught) {
      if (!options?.silent) toast.error(errorText(caught))
    }
  }

  function markRead(profileName: string) {
    const current = inbox.value
    if (!current) return
    inboxResource.setData({
      ...current,
      conversations: current.conversations.map((row) =>
        row.profile.name === profileName ? { ...row, unread_count: 0 } : row,
      ),
    })
  }

  async function setAccount(name: string) {
    const next = name && name !== 'all' ? name : chooseAccount(inbox.value?.accounts || [], null)
    if (!next) {
      account.value = ''
      writeSavedAccount('')
      return
    }
    account.value = next
    writeSavedAccount(account.value)
    const selected = accountArg()
    if (!isLiveSession() || !inbox.value) return
    try {
      await inboxResource.fetch({ account: selected })
      conversationOffset = inboxResource.data?.conversations?.length || 0
      void fetchTemplates()
      syncTabTitle()
    } catch (caught) {
      toast.error(errorText(caught))
    }
  }

  async function loadLogs() {
    if (!isLiveSession()) {
      logsResource.setData(sampleLogs())
      return
    }
    try {
      if (inbox.value && inbox.value.can_read_logs === false) return
      await logsResource.fetch({ account: accountArg() })
    } catch {
      // The logs page explains a permission error. Inbox startup does not wait on it.
    }
  }

  async function loadMoreConversations() {
    const current = inboxResource.data
    if (!current?.has_more || !isLiveSession()) return
    const page = await call<Inbox>('nudg.api.get_inbox', {
      account: accountArg(),
      start: conversationOffset,
      limit: 30,
    })
    const seen = new Set((current.conversations || []).map((row) => row.profile.name))
    const extra = (page?.conversations || []).filter((row) => row.profile?.name && !seen.has(row.profile.name))
    conversationOffset += page?.conversations?.length || 0
    inboxResource.setData({
      ...current,
      conversations: [...(current.conversations || []), ...extra],
      has_more: Boolean(page?.has_more),
    })
    syncTabTitle()
  }

  return {
    inbox,
    account,
    logs,
    loading,
    error,
    mode,
    presence,
    inboxResource,
    logsResource,
    templatesResource,
    accountArg,
    syncTabTitle,
    bindLive,
    load,
    loadLogs,
    refresh,
    markRead,
    setAccount,
    loadMoreConversations,
  }
})
