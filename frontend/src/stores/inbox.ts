import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { createResource, toast } from 'frappe-ui'
import { conversationStatusOf } from '@/utils/conversationStatus'
import { errorText } from '@/utils/format'
import { sampleInbox, sampleLogs } from '@/mocks/sample'
import { isLiveSession } from '@/stores/session'
import { playSound } from '@/stores/sounds'
import type { Inbox, LogRow } from '@/types'

export type PresenceRow = { user: string; name: string; typing: boolean; viewing: boolean }

export const useInboxStore = defineStore('nudg-inbox', () => {
  const account = ref('all')
  const presence = ref<Record<string, PresenceRow[]>>({})
  const error = ref<string | null>(null)
  const loading = ref(true)
  const started = ref(false)
  let realtimeBound = false

  const inboxResource = createResource<Inbox>({
    url: 'nudg.api.get_inbox',
    cache: 'nudg:inbox',
    initialData: null,
    auto: false,
  })

  const logsResource = createResource<LogRow[]>({
    url: 'nudg.api.get_logs',
    cache: 'nudg:logs',
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

  function bindRealtime(onMessage: () => void) {
    if (realtimeBound || typeof window === 'undefined') return
    const realtime = (window as Window & { frappe?: { realtime?: { on: (event: string, cb: (data: unknown) => void) => void } } })
      .frappe?.realtime
    if (!realtime) return
    realtimeBound = true
    realtime.on('nudg_message', (data: unknown) => {
      const payload = data as { direction?: string; contact?: string; channel?: string }
      if (payload?.direction === 'Incoming') {
        playSound('receive')
        onMessage()
      }
    })
    realtime.on('whatsapp_inbox_update', () => {
      void refresh()
    })
    realtime.on('nudg_agent_typing', (data) => applyPresence(data as Record<string, unknown>, 'typing'))
    realtime.on('nudg_agent_viewing', (data) => applyPresence(data as Record<string, unknown>, 'viewing'))
  }

  async function load(onIncoming?: () => void) {
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
      bindRealtime(() => {
        onIncoming?.()
        void refresh()
      })
    } catch (caught) {
      error.value = errorText(caught)
    } finally {
      loading.value = false
      syncTabTitle()
    }
  }

  async function refresh() {
    if (!isLiveSession()) return
    try {
      await inboxResource.fetch({ account: accountArg() })
      syncTabTitle()
    } catch (caught) {
      toast.error(errorText(caught))
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
    load,
    refresh,
    setAccount,
  }
})
