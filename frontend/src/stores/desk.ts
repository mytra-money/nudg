import { storeToRefs } from 'pinia'
import { useInboxStore } from '@/stores/inbox'
import { useThreadStore } from '@/stores/thread'

export { isManager } from '@/stores/session'
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

  async function load() {
    await inboxStore.load(() => {
      const current = threadStore.profile
      if (current) void threadStore.openProfile(current)
    })
  }

  async function refresh() {
    await inboxStore.refresh()
    if (threadStore.profile) {
      await threadStore.openProfile(threadStore.profile)
    }
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
    setAccount,
    refresh,
    openProfile: threadStore.openProfile,
    sendText: threadStore.sendText,
    sendMedia: threadStore.sendMedia,
    sendTemplate: threadStore.sendTemplate,
    react: threadStore.react,
    simulateReply: threadStore.simulateReply,
    announceTyping: threadStore.announceTyping,
  }
}
