import { storeToRefs } from 'pinia'
import { useInboxStore } from '@/stores/inbox'
import { useThreadStore } from '@/stores/thread'

export { isManager, isSiteAdmin } from '@/stores/session'
export { playSound } from '@/stores/sounds'

/**
 * Compatibility facade over Pinia inbox/thread stores.
 * Pages keep using `useDesk()` and `.value` refs the same way as before.
 */
export function useDesk() {
  const inboxStore = useInboxStore()
  const threadStore = useThreadStore()

  const { inbox, account, logs, loading, error, mode, presence } = storeToRefs(inboxStore)
  const { thread, profile, threadLoading, sending, windowState } = storeToRefs(threadStore)

  inboxStore.bindLive({
    onEvent: (event) => threadStore.applyLive(event),
    onReconnect: () => {
      if (threadStore.profile) void threadStore.syncOpen()
    },
  })

  async function load() {
    await inboxStore.load()
  }

  async function loadLogs() {
    await inboxStore.loadLogs()
  }

  async function refresh() {
    await inboxStore.refresh()
    if (threadStore.profile) await threadStore.syncOpen()
  }

  async function setAccount(name: string) {
    const selected = name && name !== 'all' ? name : undefined
    if (threadStore.thread && selected && threadStore.thread.profile.whatsapp_account !== selected) {
      await threadStore.openProfile(null)
    }
    await inboxStore.setAccount(name)
  }

  return {
    inbox,
    account,
    thread,
    logs,
    profile,
    loading,
    threadLoading,
    sending,
    error,
    mode,
    windowState,
    presence,
    load,
    loadLogs,
    setAccount,
    refresh,
    openProfile: threadStore.openProfile,
    loadMoreConversations: inboxStore.loadMoreConversations,
    loadOlder: threadStore.loadOlder,
    setThreadNotes: threadStore.setThreadNotes,
    sendText: threadStore.sendText,
    sendMedia: threadStore.sendMedia,
    sendTemplate: threadStore.sendTemplate,
    react: threadStore.react,
    simulateReply: threadStore.simulateReply,
    announceTyping: threadStore.announceTyping,
  }
}
