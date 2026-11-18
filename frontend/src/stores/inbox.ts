import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { createResource, toast } from 'frappe-ui'
import { conversationStatusOf } from '@/utils/conversationStatus'
import { errorText } from '@/utils/format'
import { sampleInbox, sampleLogs } from '@/mocks/sample'
import { applyConversation, isNewIncoming, type InboxLiveEvent } from '@/stores/inboxLive'
import { isLiveSession } from '@/stores/session'
import { playSound } from '@/stores/sounds'
import { getSocket } from '@/socket'
import { deskCacheKey } from '@/utils/deskCache'
import type { Inbox, LogRow } from '@/types'

export interface InboxLiveHandlers {
  onEvent?: (event: InboxLiveEvent) => void
  onReconnect?: () => void
}

export type PresenceRow = { user: string; name: string; typing: boolean; viewing: boolean }

export const useInboxStore = defineStore('nudg-inbox', () => {
  const account = ref('all')
  const presence = ref<Record<string, PresenceRow[]>>({})
  const error = ref<string | null>(null)
  const loading = ref(true)
  const started = ref(false)
  let realtimeBound = false
  let catchUp = false
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

  const inbox = computed({
    get: () => inboxResource.data,
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
    return account.value && account.value !== 'all' ? account.value : undefined
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
    const socket = getSocket()
    if (!socket) return
    realtimeBound = true
    socket.on('nudg_inbox', (data: InboxLiveEvent) => applyLive(data))
    socket.on('nudg_agent_typing', (data: Record<string, unknown>) => applyPresence(data, 'typing'))
    socket.on('nudg_agent_viewing', (data: Record<string, unknown>) => applyPresence(data, 'viewing'))
    socket.on('connect', () => {
      if (!catchUp) return
      void refresh({ silent: true })
      liveHandlers.onReconnect?.()
    })
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
        return
      }
      await inboxResource.fetch({ account: accountArg() })
      if (inboxResource.data?.can_read_logs) {
        await logsResource.fetch({ account: accountArg() })
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
      syncTabTitle()
    } catch (caught) {
      if (!options?.silent) toast.error(errorText(caught))
    }
  }

  async function setAccount(name: string) {
    account.value = name || 'all'
    const selected = accountArg()
    if (!isLiveSession() || !inbox.value) return
    try {
      await inboxResource.fetch({ account: selected })
      syncTabTitle()
      if (inboxResource.data?.can_read_logs) {
        await logsResource.fetch({ account: selected })
      }
    } catch (caught) {
      toast.error(errorText(caught))
    }
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
    accountArg,
    syncTabTitle,
    bindLive,
    load,
    refresh,
    setAccount,
  }
})
